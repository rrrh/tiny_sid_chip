#!/usr/bin/env python3
"""
Direct CACE simulation runner — bypasses CACE CLI netlist regeneration.

Reads CACE YAML datasheets, substitutes template variables, runs ngspice,
and applies postprocessing scripts to extract results.
"""

import os
import sys
import re
import subprocess
import importlib.util
import tempfile
import itertools
import yaml


VERIFICATION_DIR = os.path.dirname(os.path.abspath(__file__))


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_postprocess_script(script_path):
    spec = importlib.util.spec_from_file_location("postprocess_module", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.postprocess


def substitute_template(template_text, substitutions):
    """Replace CACE{key} with value."""
    def replacer(m):
        key = m.group(1)
        if key in substitutions:
            return str(substitutions[key])
        return m.group(0)  # leave unsubstituted
    return re.sub(r'CACE\{(\w+)\}', replacer, template_text)


def parse_ngspice_data(data_path, variables):
    """Parse ngspice wrdata output. Returns dict of variable -> list of values."""
    results = {v: [] for v in variables if v is not None}
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('*'):
                continue
            parts = line.split()
            if len(parts) < 1:
                continue
            # wrdata format: index col1 col2 ...
            # For DC: index=x_var, col1=v(vout), ...
            # For AC: index=freq, col1=real(v(vout)), col2=imag(v(vout)), ...
            # For TRAN: index=time, col1=v(outp), col2=..., ...
            vals = [float(x) for x in parts]
            for i, var in enumerate(variables):
                if var is not None and i < len(vals):
                    results[var].append(vals[i])
    return results


def run_parameter(macro_name, cace_dir, param_name, param_def, netlist_path, default_conditions):
    """Run all condition combinations for a single parameter."""
    print(f"\n  Parameter: {param_name}")

    tool_cfg = param_def['tool']['ngspice']
    template_name = tool_cfg['template']
    template_path = os.path.join(cace_dir, 'templates', template_name)
    variables = tool_cfg['variables']
    script_name = tool_cfg['script']
    script_path = os.path.join(cace_dir, 'scripts', script_name)
    script_vars = tool_cfg['script_variables']

    with open(template_path) as f:
        template_text = f.read()

    postprocess = load_postprocess_script(script_path)

    # Build condition combinations
    conditions = {}
    if 'conditions' in param_def:
        conditions = param_def['conditions']

    # Merge with defaults
    all_conds = dict(default_conditions)
    all_conds.update(conditions)

    # Separate enumerated vs single-value conditions
    enum_conds = {}
    fixed_conds = {}
    for k, v in all_conds.items():
        if isinstance(v, dict):
            if 'enumerate' in v:
                enum_conds[k] = v['enumerate']
            elif 'typical' in v:
                fixed_conds[k] = v['typical']
        else:
            fixed_conds[k] = v

    # Generate all combinations
    if enum_conds:
        keys = list(enum_conds.keys())
        vals_lists = [enum_conds[k] for k in keys]
        combos = list(itertools.product(*vals_lists))
    else:
        keys = []
        combos = [()]

    all_results = []
    n_pass = 0
    n_fail = 0

    for combo_idx, combo in enumerate(combos):
        cond_dict = dict(fixed_conds)
        for k, v in zip(keys, combo):
            cond_dict[k] = v

        # Build substitution dict
        subs = dict(cond_dict)
        subs['DUT_path'] = netlist_path

        # Create temp directory for this run
        with tempfile.TemporaryDirectory() as tmpdir:
            subs['simpath'] = tmpdir
            subs['filename'] = f'{macro_name}_{param_name}'
            subs['N'] = combo_idx

            # Substitute template
            spice_text = substitute_template(template_text, subs)

            # Write spice file
            spice_path = os.path.join(tmpdir, f'sim_{combo_idx}.spice')
            with open(spice_path, 'w') as f:
                f.write(spice_text)

            # Run ngspice
            try:
                result = subprocess.run(
                    ['ngspice', '-b', spice_path],
                    capture_output=True, text=True, timeout=120,
                    cwd=tmpdir
                )
            except subprocess.TimeoutExpired:
                print(f"    TIMEOUT: {cond_dict}")
                n_fail += 1
                continue

            if result.returncode != 0:
                print(f"    NGSPICE ERROR: {cond_dict}")
                for line in result.stderr.split('\n')[-5:]:
                    if line.strip():
                        print(f"      {line}")
                n_fail += 1
                continue

            # Find output data file
            data_file = os.path.join(tmpdir, f'{subs["filename"]}_{combo_idx}.data')
            if not os.path.isfile(data_file):
                # Try to find any .data file
                data_files = [f for f in os.listdir(tmpdir) if f.endswith('.data')]
                if data_files:
                    data_file = os.path.join(tmpdir, data_files[0])
                else:
                    print(f"    NO OUTPUT: {cond_dict}")
                    n_fail += 1
                    continue

            # Parse data
            try:
                raw_results = parse_ngspice_data(data_file, variables)
            except Exception as e:
                print(f"    PARSE ERROR: {e}")
                n_fail += 1
                continue

            # Run postprocessing
            try:
                processed = postprocess(raw_results, cond_dict)
            except Exception as e:
                print(f"    POSTPROCESS ERROR: {e}")
                n_fail += 1
                continue

            # Check specs
            spec_ok = True
            spec_results = {}
            if 'spec' in param_def:
                for sv in script_vars:
                    if sv in processed and sv in param_def['spec']:
                        val = processed[sv][0]
                        spec = param_def['spec'][sv]
                        status = "PASS"
                        if 'maximum' in spec and spec['maximum'].get('value') not in [None, 'any']:
                            if val > float(spec['maximum']['value']):
                                status = "FAIL"
                                spec_ok = False
                        if 'minimum' in spec and spec['minimum'].get('value') not in [None, 'any']:
                            if val < float(spec['minimum']['value']):
                                status = "FAIL"
                                spec_ok = False
                        spec_results[sv] = (val, status)

            # Format condition string
            cond_str = ', '.join(f'{k}={v}' for k, v in zip(keys, combo)) if keys else 'typical'

            # Print results
            result_parts = []
            for sv in script_vars:
                if sv in processed:
                    val = processed[sv][0]
                    if sv in spec_results:
                        _, status = spec_results[sv]
                        result_parts.append(f'{sv}={val:.4g} [{status}]')
                    else:
                        result_parts.append(f'{sv}={val:.4g}')

            status_icon = "PASS" if spec_ok else "FAIL"
            if spec_ok:
                n_pass += 1
            else:
                n_fail += 1

            print(f"    [{status_icon}] {cond_str}: {', '.join(result_parts)}")
            all_results.append((cond_dict, processed, spec_ok))

    return n_pass, n_fail, all_results


def run_macro(macro_name):
    """Run all CACE parameters for a macro."""
    cace_dir = os.path.join(VERIFICATION_DIR, macro_name, 'cace')
    yaml_path = os.path.join(cace_dir, f'{macro_name}.yaml')
    netlist_path = os.path.join(VERIFICATION_DIR, macro_name, 'netlist', f'{macro_name}.spice')

    if not os.path.isfile(yaml_path):
        print(f"  ERROR: YAML not found: {yaml_path}")
        return 0, 0

    datasheet = load_yaml(yaml_path)

    print(f"\n{'='*60}")
    print(f"  {datasheet['name']} — {datasheet['description']}")
    print(f"{'='*60}")

    default_conditions = {}
    if 'default_conditions' in datasheet:
        for k, v in datasheet['default_conditions'].items():
            if isinstance(v, dict) and 'typical' in v:
                default_conditions[k] = v['typical']

    total_pass = 0
    total_fail = 0

    for param_name, param_def in datasheet.get('parameters', {}).items():
        n_pass, n_fail, _ = run_parameter(
            macro_name, cace_dir, param_name, param_def,
            netlist_path, default_conditions
        )
        total_pass += n_pass
        total_fail += n_fail

    return total_pass, total_fail


def main():
    macros = ['r2r_dac_8bit', 'svf_2nd', 'sar_adc_8bit']

    # Allow selecting specific macros via CLI
    if len(sys.argv) > 1:
        macros = sys.argv[1:]

    grand_pass = 0
    grand_fail = 0

    for macro in macros:
        n_pass, n_fail = run_macro(macro)
        grand_pass += n_pass
        grand_fail += n_fail

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {grand_pass} passed, {grand_fail} failed")
    print(f"  Total: {grand_pass + grand_fail} test points")
    print(f"{'='*60}")

    return 0 if grand_fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
