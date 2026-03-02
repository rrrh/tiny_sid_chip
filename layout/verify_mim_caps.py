#!/usr/bin/env python3
"""
MIM Capacitor Verification for Analog Macros — IHP SG13G2 130nm

Verifies MIM cap values, layout geometry, and functional consistency
(behavioral models, SPICE parameters, design equations) across:
  - SC SVF  (svf_2nd.gds):      8 MIM caps
  - SAR ADC (sar_adc_8bit.gds): 9 binary-weighted cap groups (256 unit caps)

Usage: python3 layout/verify_mim_caps.py
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
import klayout.db as pya
from sg13g2_layers import (
    L_CMIM, L_METAL5, L_TOPMETAL1,
    MIM_CAP_DENSITY, MIM_MIN_SIZE, MIM_SPACE, MIM_ENC_M5,
)

# ===========================================================================
# Tolerance thresholds
# ===========================================================================
CAP_TOL   = 0.05   # ±5% for absolute capacitance values
RATIO_TOL = 0.01   # ±1% for capacitance ratios

# ===========================================================================
# Design targets
# ===========================================================================

# SC SVF targets (from gen_sc_svf.py, sc_svf_tb.spice, svf_2nd.v)
SVF_C_INT_FF     = 1100.0       # 1.1 pF = 1100 fF (27.1×27.1 µm)
SVF_C_SW_FF      = 73.5         # 73.5 fF (7×7 µm)
SVF_ALPHA        = 0.0668       # behavioral model: C_sw / C_int
SVF_F_CLK        = 93750.0      # 93.75 kHz switching clock
SVF_C_INT_COUNT  = 2
SVF_C_SW_COUNT   = 2
SVF_CQ_COUNT     = 4

# C_Q binary-weighted targets: bit0=1×, bit1=2×, bit2=4×, bit3=8× (approx)
SVF_CQ_TARGETS_FF = [
    73.5,    # bit 0: 7×7 µm
    147.0,   # bit 1: 7×14 µm
    294.0,   # bit 2: 14×14 µm
    600.0,   # bit 3: 20×20 µm (≈8.16× unit)
]

# SAR ADC targets (from gen_sar_adc.py, sar_adc_8bit.v)
ADC_C_UNIT_FF    = 2.0          # fF per unit cap
ADC_NBITS        = 8
ADC_WEIGHTS      = [1, 1, 2, 4, 8, 16, 32, 64, 128]  # 9 groups, 256 total units
ADC_TOTAL_UNITS  = 256
ADC_TOTAL_FF     = ADC_TOTAL_UNITS * ADC_C_UNIT_FF  # 512 fF
ADC_UNIT_SIDE    = 1.2          # µm (from math.ceil(sqrt(1.333)*10)/10)


# ===========================================================================
# Helpers
# ===========================================================================

class CheckResult:
    def __init__(self):
        self.checks = []
        self.fails = 0

    def check(self, name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        if not passed:
            self.fails += 1
        self.checks.append((name, status, detail))

    def print_report(self, header):
        print(f"\n{'='*70}")
        print(f"  {header}")
        print(f"{'='*70}")
        name_w = max((len(c[0]) for c in self.checks), default=30)
        for name, status, detail in self.checks:
            tag = f"  {status}  " if status == "PASS" else f"**{status}**"
            line = f"  {name:<{name_w}}  {tag}"
            if detail:
                line += f"  {detail}"
            print(line)
        print(f"{'='*70}")
        if self.fails == 0:
            print(f"  ALL {len(self.checks)} CHECKS PASSED")
        else:
            print(f"  {self.fails}/{len(self.checks)} CHECKS FAILED")
        print(f"{'='*70}\n")
        return self.fails == 0


def extract_mim_caps(gds_path):
    """
    Load GDS, extract Cmim shapes, compute capacitance from area.
    Returns (layout, top_cell, caps_list) where each cap is a dict with:
      bbox, w_um, h_um, area_um2, cap_fF
    """
    layout = pya.Layout()
    layout.read(gds_path)
    top = layout.top_cell()
    dbu = layout.dbu

    li_cmim = layout.layer(*L_CMIM)
    li_m5   = layout.layer(*L_METAL5)
    li_tm1  = layout.layer(*L_TOPMETAL1)

    # Collect Cmim regions
    cmim_region = pya.Region(top.begin_shapes_rec(li_cmim))
    m5_region   = pya.Region(top.begin_shapes_rec(li_m5))
    tm1_region  = pya.Region(top.begin_shapes_rec(li_tm1))

    # Merge touching/overlapping shapes
    cmim_region.merge()

    caps = []
    for poly in cmim_region.each():
        box = poly.bbox()
        w_um = box.width() * dbu
        h_um = box.height() * dbu
        area_um2 = w_um * h_um
        cap_fF = area_um2 * MIM_CAP_DENSITY
        caps.append({
            'bbox': box,
            'w_um': w_um,
            'h_um': h_um,
            'area_um2': area_um2,
            'cap_fF': cap_fF,
        })

    # Sort by area (ascending)
    caps.sort(key=lambda c: c['area_um2'])

    return layout, top, caps, cmim_region, m5_region, tm1_region


def check_drc_mim(layout, cmim_region, m5_region, results):
    """Run MIM-specific DRC checks: min size, spacing, M5 enclosure."""
    dbu = layout.dbu

    # MIM_MIN_SIZE: minimum width of Cmim shapes
    min_size_dbu = int(round(MIM_MIN_SIZE / dbu))
    width_markers = cmim_region.width_check(min_size_dbu)
    count = width_markers.size()
    results.check("MIM.a min size (≥1.14 µm)", count == 0,
                  f"{count} violations" if count > 0 else "")

    # MIM_SPACE: minimum spacing between Cmim shapes
    space_dbu = int(round(MIM_SPACE / dbu))
    space_markers = cmim_region.space_check(space_dbu)
    count = space_markers.size()
    results.check("MIM.b min spacing (≥0.60 µm)", count == 0,
                  f"{count} violations" if count > 0 else "")

    # MIM_ENC_M5: Metal5 must enclose Cmim by ≥0.60 µm
    enc_dbu = int(round(MIM_ENC_M5 / dbu))
    cmim_grown = cmim_region.sized(enc_dbu)
    violations = cmim_grown - m5_region
    count = violations.size()
    results.check("MIM.c M5 enclosure (≥0.60 µm)", count == 0,
                  f"{count} violations" if count > 0 else "")


def close_enough(actual, expected, tol):
    """Check if actual is within tol fraction of expected."""
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= tol


# ===========================================================================
# SC SVF Verification
# ===========================================================================

def verify_svf(gds_path):
    """Verify SC SVF MIM capacitors."""
    results = CheckResult()

    if not os.path.exists(gds_path):
        results.check("GDS file exists", False, gds_path)
        results.print_report("SC SVF — svf_2nd.gds")
        return False

    layout, top, caps, cmim_reg, m5_reg, tm1_reg = extract_mim_caps(gds_path)
    n_caps = len(caps)

    print(f"\n  SC SVF: found {n_caps} MIM capacitors in {os.path.basename(gds_path)}")
    print(f"  Top cell: {top.name}")

    # Print all caps
    for i, c in enumerate(caps):
        print(f"    Cap {i}: {c['w_um']:.2f} × {c['h_um']:.2f} µm² "
              f"= {c['area_um2']:.1f} µm² → {c['cap_fF']:.1f} fF")

    # --- Count check ---
    expected_total = SVF_C_INT_COUNT + SVF_C_SW_COUNT + SVF_CQ_COUNT  # 2+2+4=8
    results.check(f"Cap count = {expected_total}", n_caps == expected_total,
                  f"got {n_caps}")

    if n_caps != expected_total:
        # Can't do detailed checks with wrong count
        results.print_report("SC SVF — svf_2nd.gds")
        return False

    # --- Classify caps by area ---
    # Sort ascending: 2× C_sw (49 µm²), then C_Q bits, then 2× C_int (734 µm²)
    # Expected order by area:
    #   C_sw:  7×7 = 49 µm²  (2 caps)
    #   C_Q0:  7×7 = 49 µm²  (1 cap, same size as C_sw)
    #   C_Q1:  7×14 = 98 µm² (1 cap)
    #   C_Q2:  14×14 = 196 µm² (1 cap)
    #   C_Q3:  20×20 = 400 µm² (1 cap)
    #   C_int: 27.1×27.1 = 734 µm² (2 caps)
    #
    # Three caps at 49 µm² — identify by context:
    #   The two largest caps are C_int.
    #   The remaining 6, sorted ascending: first 3 at ~49 µm² (2×C_sw + C_Q0),
    #   then C_Q1, C_Q2, C_Q3.

    # C_int: the two largest
    c_int_caps = caps[-2:]
    # Remaining 6, sorted ascending
    remaining = caps[:-2]

    # Among the remaining, the 4 largest are C_Q (including C_Q0 at 49 µm²)
    # and the 2 smallest are C_sw.
    # But C_sw and C_Q0 have the same dimensions (7×7).
    # Since they're all 49 µm², we have 3 caps at ~49 µm².
    # We identify C_sw as the first 2 and C_Q0 as the third.
    # (In sorted order, they'll be grouped together.)
    c_sw_caps = remaining[:2]
    c_q_caps = remaining[2:]  # 4 caps: C_Q0 (49), C_Q1 (98), C_Q2 (196), C_Q3 (400)

    # --- C_int verification ---
    for i, c in enumerate(c_int_caps):
        results.check(f"C_int[{i}] ≈ {SVF_C_INT_FF:.0f} fF",
                      close_enough(c['cap_fF'], SVF_C_INT_FF, CAP_TOL),
                      f"{c['cap_fF']:.1f} fF ({c['w_um']:.2f}×{c['h_um']:.2f} µm)")

    # --- C_sw verification ---
    for i, c in enumerate(c_sw_caps):
        results.check(f"C_sw[{i}] ≈ {SVF_C_SW_FF:.1f} fF",
                      close_enough(c['cap_fF'], SVF_C_SW_FF, CAP_TOL),
                      f"{c['cap_fF']:.1f} fF ({c['w_um']:.2f}×{c['h_um']:.2f} µm)")

    # --- C_Q binary-weighted verification ---
    for i, c in enumerate(c_q_caps):
        target = SVF_CQ_TARGETS_FF[i]
        results.check(f"C_Q[{i}] ≈ {target:.1f} fF",
                      close_enough(c['cap_fF'], target, CAP_TOL),
                      f"{c['cap_fF']:.1f} fF ({c['w_um']:.2f}×{c['h_um']:.2f} µm)")

    # --- ALPHA cross-check (behavioral model) ---
    c_sw_avg  = sum(c['cap_fF'] for c in c_sw_caps) / len(c_sw_caps)
    c_int_avg = sum(c['cap_fF'] for c in c_int_caps) / len(c_int_caps)
    alpha_measured = c_sw_avg / c_int_avg
    results.check(f"ALPHA = C_sw/C_int ≈ {SVF_ALPHA}",
                  close_enough(alpha_measured, SVF_ALPHA, RATIO_TOL),
                  f"{alpha_measured:.6f} (model: {SVF_ALPHA})")

    # --- f₀ consistency ---
    # f₀ = f_clk × C_sw / (2π × C_int)
    f0_computed = SVF_F_CLK * c_sw_avg / (2 * math.pi * c_int_avg)
    f0_expected = SVF_F_CLK * SVF_C_SW_FF / (2 * math.pi * SVF_C_INT_FF)
    results.check(f"f₀ consistency (layout vs design)",
                  close_enough(f0_computed, f0_expected, RATIO_TOL),
                  f"layout: {f0_computed:.1f} Hz, design: {f0_expected:.1f} Hz")

    # --- SPICE parameter cross-check ---
    # sc_svf_tb.spice: c_sw=73.5e-15, c_int=1.1e-12
    results.check("C_sw matches SPICE (73.5 fF)",
                  close_enough(c_sw_avg, 73.5, CAP_TOL),
                  f"layout avg: {c_sw_avg:.1f} fF")
    results.check("C_int matches SPICE (1100 fF)",
                  close_enough(c_int_avg, 1100.0, CAP_TOL),
                  f"layout avg: {c_int_avg:.1f} fF")

    # --- DRC checks ---
    check_drc_mim(layout, cmim_reg, m5_reg, results)

    return results.print_report("SC SVF — svf_2nd.gds")


# ===========================================================================
# SAR ADC Verification
# ===========================================================================

def verify_adc(gds_path):
    """Verify SAR ADC binary-weighted MIM cap array.

    The generator draws each binary weight as a single scaled rectangle
    (area = weight × C_unit / MIM_CAP_DENSITY), giving 9 Cmim shapes
    with capacitances 1C,1C,2C,4C,8C,16C,32C,64C,128C (C_unit = 2 fF).
    """
    results = CheckResult()

    if not os.path.exists(gds_path):
        results.check("GDS file exists", False, gds_path)
        results.print_report("SAR ADC — sar_adc_8bit.gds")
        return False

    layout, top, caps, cmim_reg, m5_reg, tm1_reg = extract_mim_caps(gds_path)
    n_caps = len(caps)

    print(f"\n  SAR ADC: found {n_caps} MIM cap shapes in {os.path.basename(gds_path)}")
    print(f"  Top cell: {top.name}")

    for i, c in enumerate(caps):
        print(f"    Cap {i}: {c['w_um']:.3f} × {c['h_um']:.3f} µm² "
              f"= {c['area_um2']:.3f} µm² → {c['cap_fF']:.2f} fF")

    # --- Shape count = 9 (one per binary weight) ---
    n_weights = len(ADC_WEIGHTS)
    results.check(f"Cap shape count = {n_weights}", n_caps == n_weights,
                  f"got {n_caps}")

    if n_caps == 0:
        results.print_report("SAR ADC — sar_adc_8bit.gds")
        return False

    # --- Total capacitance = 256 × C_unit = 512 fF ---
    total_cap = sum(c['cap_fF'] for c in caps)
    results.check(f"Total cap ≈ {ADC_TOTAL_FF:.0f} fF",
                  close_enough(total_cap, ADC_TOTAL_FF, CAP_TOL),
                  f"{total_cap:.1f} fF")

    # --- Binary weight ratios ---
    # Sort caps by capacitance, then compare to expected weights
    caps_sorted = sorted(caps, key=lambda c: c['cap_fF'])
    weights_sorted = sorted(ADC_WEIGHTS)  # [1,1,2,4,8,16,32,64,128]
    expected_caps = [w * ADC_C_UNIT_FF for w in weights_sorted]

    if n_caps == n_weights:
        for i, (c, w, exp_fF) in enumerate(zip(caps_sorted, weights_sorted, expected_caps)):
            results.check(f"Weight {w}C ≈ {exp_fF:.1f} fF",
                          close_enough(c['cap_fF'], exp_fF, CAP_TOL),
                          f"{c['cap_fF']:.2f} fF ({c['w_um']:.3f}×{c['h_um']:.3f} µm)")

    # --- Binary ratio check (each weight ≈ 2× previous, skipping first pair) ---
    if n_caps == n_weights:
        for i in range(2, n_weights):  # start at index 2 (weight 2C)
            prev_cap = caps_sorted[i - 1]['cap_fF']
            this_cap = caps_sorted[i]['cap_fF']
            expected_ratio = weights_sorted[i] / weights_sorted[i - 1]
            actual_ratio = this_cap / prev_cap if prev_cap > 0 else 0
            results.check(f"Ratio {weights_sorted[i]}C/{weights_sorted[i-1]}C ≈ {expected_ratio:.0f}",
                          close_enough(actual_ratio, expected_ratio, RATIO_TOL),
                          f"{actual_ratio:.4f}")

    # --- 9-cycle conversion consistency ---
    results.check("9 weights sum to 256 units",
                  sum(ADC_WEIGHTS) == ADC_TOTAL_UNITS,
                  f"sum({ADC_WEIGHTS}) = {sum(ADC_WEIGHTS)}")

    # --- DRC checks ---
    check_drc_mim(layout, cmim_reg, m5_reg, results)

    return results.print_report("SAR ADC — sar_adc_8bit.gds")


# ===========================================================================
# Main
# ===========================================================================

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    svf_gds = os.path.join(base, "macros", "gds", "svf_2nd.gds")
    adc_gds = os.path.join(base, "macros", "gds", "sar_adc_8bit.gds")

    print("=" * 70)
    print("  MIM Capacitor Verification — IHP SG13G2 130nm")
    print("=" * 70)
    print(f"  MIM_CAP_DENSITY = {MIM_CAP_DENSITY} fF/µm²")
    print(f"  MIM_MIN_SIZE    = {MIM_MIN_SIZE} µm")
    print(f"  MIM_SPACE       = {MIM_SPACE} µm")
    print(f"  MIM_ENC_M5      = {MIM_ENC_M5} µm")

    all_pass = True

    # SC SVF
    if not verify_svf(svf_gds):
        all_pass = False

    # SAR ADC
    if not verify_adc(adc_gds):
        all_pass = False

    # Final summary
    print("\n" + "=" * 70)
    if all_pass:
        print("  OVERALL: ALL CHECKS PASSED")
    else:
        print("  OVERALL: SOME CHECKS FAILED — review above")
    print("=" * 70)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
