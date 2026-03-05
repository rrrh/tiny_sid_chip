#!/usr/bin/env python3
"""
Direct CACE simulation runner — bypasses CACE CLI netlist regeneration.

Reads CACE YAML datasheets, substitutes template variables, runs ngspice,
and applies postprocessing scripts to extract results. Generates plots.
"""

import os
import sys
import re
import subprocess
import importlib.util
import tempfile
import itertools
import math
import yaml

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


VERIFICATION_DIR = os.path.dirname(os.path.abspath(__file__))
PLOT_DIR = os.path.join(VERIFICATION_DIR, 'plots')


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
        return m.group(0)
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
            vals = [float(x) for x in parts]
            for i, var in enumerate(variables):
                if var is not None and i < len(vals):
                    results[var].append(vals[i])
    return results


def run_parameter(macro_name, cace_dir, param_name, param_def, netlist_path, default_conditions):
    """Run all condition combinations for a single parameter.
    Returns (n_pass, n_fail, results_list).
    Each result: (cond_dict, raw_data, processed_data, spec_ok)
    """
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

    conditions = {}
    if 'conditions' in param_def:
        conditions = param_def['conditions']

    all_conds = dict(default_conditions)
    all_conds.update(conditions)

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

        subs = dict(cond_dict)
        subs['DUT_path'] = netlist_path

        with tempfile.TemporaryDirectory() as tmpdir:
            subs['simpath'] = tmpdir
            subs['filename'] = f'{macro_name}_{param_name}'
            subs['N'] = combo_idx

            spice_text = substitute_template(template_text, subs)
            spice_path = os.path.join(tmpdir, f'sim_{combo_idx}.spice')
            with open(spice_path, 'w') as f:
                f.write(spice_text)

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

            data_file = os.path.join(tmpdir, f'{subs["filename"]}_{combo_idx}.data')
            if not os.path.isfile(data_file):
                data_files = [f for f in os.listdir(tmpdir) if f.endswith('.data')]
                if data_files:
                    data_file = os.path.join(tmpdir, data_files[0])
                else:
                    print(f"    NO OUTPUT: {cond_dict}")
                    n_fail += 1
                    continue

            try:
                raw_results = parse_ngspice_data(data_file, variables)
            except Exception as e:
                print(f"    PARSE ERROR: {e}")
                n_fail += 1
                continue

            try:
                processed = postprocess(raw_results, cond_dict)
            except Exception as e:
                print(f"    POSTPROCESS ERROR: {e}")
                n_fail += 1
                continue

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

            cond_str = ', '.join(f'{k}={v}' for k, v in zip(keys, combo)) if keys else 'typical'

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
            all_results.append((cond_dict, raw_results, processed, spec_ok))

    return n_pass, n_fail, all_results


def generate_plots(macro_name, param_name, param_def, results, plot_dir):
    """Generate plots for a parameter from collected results."""
    if 'plot' not in param_def:
        return

    os.makedirs(plot_dir, exist_ok=True)
    tool_cfg = param_def['tool']['ngspice']
    variables = tool_cfg['variables']

    for plot_name, plot_cfg in param_def['plot'].items():
        plot_type = plot_cfg.get('type', 'xyplot')
        xaxis = plot_cfg.get('xaxis', None)
        yaxis = plot_cfg.get('yaxis', None)

        if xaxis is None or yaxis is None:
            continue

        fig, ax = plt.subplots(figsize=(8, 5))

        # Check if this is a "raw data" plot (xaxis/yaxis are variable names from wrdata)
        # or a "parameter" plot (xaxis/yaxis are condition/result names)
        is_raw_plot = xaxis in (variables or []) or xaxis == 'null'

        if is_raw_plot:
            # Plot raw simulation data (transfer functions, frequency responses)
            for cond_dict, raw_data, processed, spec_ok in results:
                x_data = raw_data.get(xaxis, list(range(len(raw_data.get(yaxis, [])))))
                y_data = raw_data.get(yaxis, [])

                if not x_data or not y_data:
                    continue

                # For AC data, compute magnitude if we have real/imag
                if yaxis.endswith('_re') and yaxis.replace('_re', '_im') in raw_data:
                    re_data = raw_data[yaxis]
                    im_data = raw_data[yaxis.replace('_re', '_im')]
                    y_data = [20 * math.log10(max(math.sqrt(r**2 + i**2), 1e-20))
                              for r, i in zip(re_data, im_data)]
                    yaxis_label = f'|{yaxis.replace("_re", "")}| (dB)'
                else:
                    yaxis_label = yaxis

                # Build legend label from varying conditions
                label_parts = []
                for k, v in cond_dict.items():
                    if k not in ('vdd', 'DUT_path', 'simpath', 'filename', 'N'):
                        label_parts.append(f'{k}={v}')
                label = ', '.join(label_parts) if label_parts else 'typical'

                if plot_type == 'loglog':
                    ax.loglog(x_data, y_data, label=label)
                elif plot_type == 'semilogx':
                    ax.semilogx(x_data, y_data, label=label)
                elif plot_type == 'semilogy':
                    ax.semilogy(x_data, y_data, label=label)
                else:
                    ax.plot(x_data, y_data, label=label)

                ax.set_xlabel(xaxis if xaxis != 'null' else 'Code')
                ax.set_ylabel(yaxis_label)

        else:
            # Plot processed results vs conditions
            # Group by non-xaxis conditions for multiple traces
            traces = {}  # group_key -> (x_vals, y_vals)

            for cond_dict, raw_data, processed, spec_ok in results:
                x_val = cond_dict.get(xaxis)
                y_val = processed.get(yaxis, [None])[0] if yaxis in processed else None

                if x_val is None or y_val is None:
                    continue

                # Group by non-x conditions
                group_parts = []
                for k, v in sorted(cond_dict.items()):
                    if k != xaxis and k not in ('vdd', 'DUT_path', 'simpath', 'filename', 'N'):
                        group_parts.append(f'{k}={v}')
                group_key = ', '.join(group_parts) if group_parts else 'typical'

                if group_key not in traces:
                    traces[group_key] = ([], [])
                traces[group_key][0].append(x_val)
                traces[group_key][1].append(y_val)

            for group_key, (x_vals, y_vals) in sorted(traces.items()):
                # Sort by x
                pairs = sorted(zip(x_vals, y_vals))
                x_sorted = [p[0] for p in pairs]
                y_sorted = [p[1] for p in pairs]

                # Convert string x values to indices for categorical axes
                if all(isinstance(x, str) for x in x_sorted):
                    ax.bar([str(x) for x in x_sorted], y_sorted, label=group_key, alpha=0.7)
                else:
                    if plot_type == 'loglog':
                        ax.loglog(x_sorted, y_sorted, 'o-', label=group_key)
                    elif plot_type == 'semilogx':
                        ax.semilogx(x_sorted, y_sorted, 'o-', label=group_key)
                    elif plot_type == 'semilogy':
                        ax.semilogy(x_sorted, y_sorted, 'o-', label=group_key)
                    else:
                        ax.plot(x_sorted, y_sorted, 'o-', label=group_key)

            ax.set_xlabel(xaxis)
            ax.set_ylabel(yaxis)

        # Add spec limits as horizontal lines
        if 'spec' in param_def and yaxis in param_def['spec']:
            spec = param_def['spec'][yaxis]
            if 'maximum' in spec and spec['maximum'].get('value') not in [None, 'any']:
                ax.axhline(y=float(spec['maximum']['value']), color='r',
                          linestyle='--', alpha=0.5, label=f'max={spec["maximum"]["value"]}')
            if 'minimum' in spec and spec['minimum'].get('value') not in [None, 'any']:
                ax.axhline(y=float(spec['minimum']['value']), color='r',
                          linestyle='--', alpha=0.5, label=f'min={spec["minimum"]["value"]}')

        ax.set_title(f'{macro_name} — {param_name}: {plot_name}')
        ax.legend(fontsize=7, loc='best')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        outpath = os.path.join(plot_dir, f'{macro_name}_{param_name}_{plot_name}.png')
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")


def generate_custom_plots(macro_name, all_param_results, plot_dir):
    """Generate additional custom plots per macro."""
    os.makedirs(plot_dir, exist_ok=True)

    if macro_name == 'r2r_dac_8bit' and 'static_linearity' in all_param_results:
        # DAC transfer function for typical corner
        results = all_param_results['static_linearity']
        for cond_dict, raw_data, processed, spec_ok in results:
            if cond_dict.get('corner') == 'mos_tt' and cond_dict.get('temperature') == 27:
                vout = raw_data.get('vout', [])
                if vout:
                    codes = list(range(len(vout)))
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))

                    # Transfer function
                    ax1.plot(codes, vout, 'b-', linewidth=0.8)
                    ax1.set_xlabel('Digital Code')
                    ax1.set_ylabel('Vout (V)')
                    ax1.set_title('R2R DAC Transfer Function (TT, 27°C)')
                    ax1.grid(True, alpha=0.3)

                    # INL/DNL
                    n = len(vout)
                    if n >= 2:
                        lsb = (vout[-1] - vout[0]) / (n - 1)
                        inl = [(vout[k] - (vout[0] + k * lsb)) / lsb for k in range(n)]
                        dnl = [(vout[k] - vout[k-1]) / lsb - 1.0 for k in range(1, n)]
                        ax2.plot(range(n), inl, 'b-', linewidth=0.8, label='INL')
                        ax2.plot(range(1, n), dnl, 'r-', linewidth=0.8, label='DNL')
                        ax2.axhline(y=1.0, color='k', linestyle='--', alpha=0.3)
                        ax2.axhline(y=-1.0, color='k', linestyle='--', alpha=0.3)
                        ax2.set_xlabel('Digital Code')
                        ax2.set_ylabel('LSB')
                        ax2.set_title('INL / DNL')
                        ax2.legend()
                        ax2.grid(True, alpha=0.3)

                    plt.tight_layout()
                    outpath = os.path.join(plot_dir, 'r2r_dac_transfer_inl_dnl.png')
                    fig.savefig(outpath, dpi=150)
                    plt.close(fig)
                    print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")
                break

    if macro_name == 'svf_2nd' and 'bp_response' in all_param_results:
        # BP frequency response for all f_clk at q_code=1
        results = all_param_results['bp_response']
        fig, ax = plt.subplots(figsize=(8, 5))
        for cond_dict, raw_data, processed, spec_ok in results:
            if cond_dict.get('q_code') == 1:
                freq = raw_data.get('freq', [])
                vout_re = raw_data.get('vout_re', [])
                vout_im = raw_data.get('vout_im', [])
                if freq and vout_re and vout_im:
                    mag_db = [20 * math.log10(max(math.sqrt(r**2 + i**2), 1e-20))
                              for r, i in zip(vout_re, vout_im)]
                    f_clk = cond_dict.get('f_clk', '?')
                    ax.semilogx(freq, mag_db, label=f'f_clk={f_clk} Hz')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Magnitude (dB)')
        ax.set_title('SVF Band-Pass Response (Q_code=1)')
        ax.legend()
        ax.grid(True, alpha=0.3, which='both')
        ax.set_ylim(-40, 5)
        plt.tight_layout()
        outpath = os.path.join(plot_dir, 'svf_bp_bode_q1.png')
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")

        # BP frequency response for all q_code at f_clk=93750
        fig, ax = plt.subplots(figsize=(8, 5))
        for cond_dict, raw_data, processed, spec_ok in results:
            if cond_dict.get('f_clk') == 93750:
                freq = raw_data.get('freq', [])
                vout_re = raw_data.get('vout_re', [])
                vout_im = raw_data.get('vout_im', [])
                if freq and vout_re and vout_im:
                    mag_db = [20 * math.log10(max(math.sqrt(r**2 + i**2), 1e-20))
                              for r, i in zip(vout_re, vout_im)]
                    q_code = cond_dict.get('q_code', '?')
                    ax.semilogx(freq, mag_db, label=f'Q_code={q_code}')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Magnitude (dB)')
        ax.set_title('SVF Band-Pass Response (f_clk=93.75 kHz)')
        ax.legend()
        ax.grid(True, alpha=0.3, which='both')
        ax.set_ylim(-40, 5)
        plt.tight_layout()
        outpath = os.path.join(plot_dir, 'svf_bp_bode_fclk93k.png')
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")

    if macro_name == 'svf_2nd' and 'lp_response' in all_param_results:
        # LP frequency response
        results = all_param_results['lp_response']
        fig, ax = plt.subplots(figsize=(8, 5))
        for cond_dict, raw_data, processed, spec_ok in results:
            freq = raw_data.get('freq', [])
            vout_re = raw_data.get('vout_re', [])
            vout_im = raw_data.get('vout_im', [])
            if freq and vout_re and vout_im:
                mag_db = [20 * math.log10(max(math.sqrt(r**2 + i**2), 1e-20))
                          for r, i in zip(vout_re, vout_im)]
                f_clk = cond_dict.get('f_clk', '?')
                ax.semilogx(freq, mag_db, label=f'f_clk={f_clk} Hz')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Magnitude (dB)')
        ax.set_title('SVF Low-Pass Response')
        ax.legend()
        ax.grid(True, alpha=0.3, which='both')
        ax.set_ylim(-40, 5)
        plt.tight_layout()
        outpath = os.path.join(plot_dir, 'svf_lp_bode.png')
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")

    if macro_name == 'sar_adc_8bit' and 'comp_resolve_time' in all_param_results:
        # Comparator waveform for one condition
        results = all_param_results['comp_resolve_time']
        for cond_dict, raw_data, processed, spec_ok in results:
            if (cond_dict.get('corner') == 'mos_tt' and
                cond_dict.get('temperature') == 27 and
                cond_dict.get('vdiff') == 10):
                time = raw_data.get('time', [])
                outp = raw_data.get('outp', [])
                outn = raw_data.get('outn', [])
                clk = raw_data.get('clk', [])
                if time and outp and outn:
                    time_ns = [t * 1e9 for t in time]
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6),
                                                    sharex=True, height_ratios=[3, 1])
                    ax1.plot(time_ns, outp, 'b-', label='outp', linewidth=0.8)
                    ax1.plot(time_ns, outn, 'r-', label='outn', linewidth=0.8)
                    ax1.set_ylabel('Voltage (V)')
                    ax1.set_title('StrongARM Comparator (TT, 27°C, Vdiff=10mV)')
                    ax1.legend()
                    ax1.grid(True, alpha=0.3)
                    if clk:
                        ax2.plot(time_ns, clk, 'g-', linewidth=0.8)
                        ax2.set_ylabel('CLK (V)')
                        ax2.set_xlabel('Time (ns)')
                        ax2.grid(True, alpha=0.3)
                    plt.tight_layout()
                    outpath = os.path.join(plot_dir, 'sar_comp_waveform.png')
                    fig.savefig(outpath, dpi=150)
                    plt.close(fig)
                    print(f"    Plot: {os.path.relpath(outpath, VERIFICATION_DIR)}")
                break


def generate_datasheet(macro_name, datasheet, all_param_results, total_pass, total_fail, plot_dir):
    """Generate a Markdown datasheet summarizing all characterization results."""
    from datetime import datetime

    doc_dir = os.path.join(VERIFICATION_DIR, macro_name, 'doc')
    os.makedirs(doc_dir, exist_ok=True)
    ds_path = os.path.join(doc_dir, f'{macro_name}_datasheet.md')

    # Relative path from doc/ to plots/
    plots_rel = os.path.relpath(plot_dir, doc_dir)

    lines = []
    lines.append(f'# {datasheet["name"]} Datasheet')
    lines.append('')
    lines.append(f'**{datasheet["description"]}**')
    lines.append('')
    lines.append(f'| Field | Value |')
    lines.append(f'|-------|-------|')
    lines.append(f'| PDK | {datasheet.get("PDK", "N/A")} |')
    auth = datasheet.get('authorship', {})
    lines.append(f'| Designer | {auth.get("designer", "N/A")} |')
    lines.append(f'| Created | {auth.get("creation_date", "N/A")} |')
    lines.append(f'| License | {auth.get("license", "N/A")} |')
    lines.append(f'| Characterization Date | {datetime.now().strftime("%Y-%m-%d %H:%M")} |')
    lines.append(f'| Total Tests | {total_pass + total_fail} |')
    lines.append(f'| Passed | {total_pass} |')
    lines.append(f'| Failed | {total_fail} |')
    status = 'PASS' if total_fail == 0 else 'FAIL'
    lines.append(f'| **Overall** | **{status}** |')
    lines.append('')

    # Pin table
    if 'pins' in datasheet:
        lines.append('## Pin Description')
        lines.append('')
        lines.append('| Pin | Direction | Type | Description |')
        lines.append('|-----|-----------|------|-------------|')
        for pin_name, pin_info in datasheet['pins'].items():
            direction = pin_info.get('direction', '')
            ptype = pin_info.get('type', '')
            desc = pin_info.get('description', '')
            vrange = ''
            if 'Vmin' in pin_info and 'Vmax' in pin_info:
                vrange = f' ({pin_info["Vmin"]}..{pin_info["Vmax"]} V)'
            lines.append(f'| {pin_name} | {direction} | {ptype} | {desc}{vrange} |')
        lines.append('')

    # Default conditions
    if 'default_conditions' in datasheet:
        lines.append('## Default Conditions')
        lines.append('')
        lines.append('| Condition | Display | Typical | Unit |')
        lines.append('|-----------|---------|---------|------|')
        for cname, cinfo in datasheet['default_conditions'].items():
            if isinstance(cinfo, dict):
                display = cinfo.get('display', cname)
                typical = cinfo.get('typical', '')
                unit = cinfo.get('unit', '')
                lines.append(f'| {cname} | {display} | {typical} | {unit} |')
        lines.append('')

    # Parameter results
    lines.append('## Characterization Results')
    lines.append('')

    for param_name, param_def in datasheet.get('parameters', {}).items():
        display = param_def.get('display', param_name)
        desc = param_def.get('description', '')
        lines.append(f'### {display}')
        lines.append('')
        lines.append(f'{desc}')
        lines.append('')

        # Spec table
        if 'spec' in param_def:
            lines.append('**Specifications:**')
            lines.append('')
            lines.append('| Parameter | Display | Unit | Min | Max |')
            lines.append('|-----------|---------|------|-----|-----|')
            for sname, sinfo in param_def['spec'].items():
                sdisplay = sinfo.get('display', sname)
                sunit = sinfo.get('unit', '')
                smin = sinfo.get('minimum', {}).get('value', '')
                smax = sinfo.get('maximum', {}).get('value', '')
                lines.append(f'| {sname} | {sdisplay} | {sunit} | {smin} | {smax} |')
            lines.append('')

        # Results table
        if param_name in all_param_results:
            results = all_param_results[param_name]
            if results:
                # Get condition keys and script variables
                tool_cfg = param_def['tool']['ngspice']
                script_vars = tool_cfg.get('script_variables', [])

                # Build header from first result's conditions
                first_cond = results[0][0]
                cond_keys = [k for k in first_cond.keys()
                             if k not in ('DUT_path', 'simpath', 'filename', 'N')]

                header = '| ' + ' | '.join(cond_keys) + ' | '
                header += ' | '.join(script_vars) + ' | Status |'
                sep = '|' + '|'.join(['---'] * (len(cond_keys) + len(script_vars) + 1)) + '|'

                lines.append('**Results:**')
                lines.append('')
                lines.append(header)
                lines.append(sep)

                for cond_dict, raw_data, processed, spec_ok in results:
                    row = '| '
                    for k in cond_keys:
                        v = cond_dict.get(k, '')
                        row += f'{v} | '
                    for sv in script_vars:
                        if sv in processed:
                            val = processed[sv][0]
                            if abs(val) < 0.001 or abs(val) > 10000:
                                row += f'{val:.4e} | '
                            else:
                                row += f'{val:.4f} | '
                        else:
                            row += 'N/A | '
                    row += 'PASS |' if spec_ok else '**FAIL** |'
                    lines.append(row)
                lines.append('')

        # Plots
        plot_files = []
        if os.path.isdir(plot_dir):
            for f in sorted(os.listdir(plot_dir)):
                if f.endswith('.png') and param_name in f:
                    plot_files.append(f)

        if plot_files:
            lines.append('**Plots:**')
            lines.append('')
            for pf in plot_files:
                lines.append(f'![{pf}]({plots_rel}/{pf})')
                lines.append('')

    # Custom/composite plots
    if os.path.isdir(plot_dir):
        custom_plots = [f for f in sorted(os.listdir(plot_dir)) if f.endswith('.png')
                        and not any(pn in f for pn in datasheet.get('parameters', {}).keys())]
        if custom_plots:
            lines.append('## Composite Plots')
            lines.append('')
            for pf in custom_plots:
                title = pf.replace('.png', '').replace('_', ' ').title()
                lines.append(f'### {title}')
                lines.append('')
                lines.append(f'![{pf}]({plots_rel}/{pf})')
                lines.append('')

    lines.append('---')
    lines.append(f'*Generated by run_cace_sims.py on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*')
    lines.append('')

    with open(ds_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"    Datasheet: {os.path.relpath(ds_path, VERIFICATION_DIR)}")
    return ds_path


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
    all_param_results = {}

    plot_dir = os.path.join(PLOT_DIR, macro_name)

    for param_name, param_def in datasheet.get('parameters', {}).items():
        n_pass, n_fail, results = run_parameter(
            macro_name, cace_dir, param_name, param_def,
            netlist_path, default_conditions
        )
        total_pass += n_pass
        total_fail += n_fail
        all_param_results[param_name] = results

        # Generate YAML-defined plots
        generate_plots(macro_name, param_name, param_def, results, plot_dir)

    # Generate custom composite plots
    print(f"\n  Generating custom plots...")
    generate_custom_plots(macro_name, all_param_results, plot_dir)

    # Generate datasheet
    print(f"\n  Generating datasheet...")
    generate_datasheet(macro_name, datasheet, all_param_results,
                       total_pass, total_fail, plot_dir)

    return total_pass, total_fail


def main():
    macros = ['r2r_dac_8bit', 'svf_2nd', 'sar_adc_8bit', 'bias_dac_2ch']

    if len(sys.argv) > 1:
        macros = sys.argv[1:]

    os.makedirs(PLOT_DIR, exist_ok=True)
    grand_pass = 0
    grand_fail = 0

    for macro in macros:
        n_pass, n_fail = run_macro(macro)
        grand_pass += n_pass
        grand_fail += n_fail

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {grand_pass} passed, {grand_fail} failed")
    print(f"  Total: {grand_pass + grand_fail} test points")
    print(f"  Plots saved to: {os.path.relpath(PLOT_DIR, VERIFICATION_DIR)}/")
    print(f"{'='*60}")

    return 0 if grand_fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
