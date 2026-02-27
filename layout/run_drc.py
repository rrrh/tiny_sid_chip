#!/usr/bin/env python3
"""
Standalone DRC checker for IHP SG13G2 130nm using klayout.db.
Implements key design rules from the PDK DRC deck without requiring
klayout batch mode (which segfaults on KLayout 0.26.2).

Usage: python3 run_drc.py <gds_file> [top_cell]
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import klayout.db as pya
from sg13g2_layers import *

# ===========================================================================
# DRC rule definitions (from IHP SG13G2 PDK rule decks)
# ===========================================================================
RULES = [
    # (name, description, layer, check_type, value_um)
    # --- Activ ---
    ("Act.a",  "Min Activ width",                  L_ACTIV,   "width",   0.15),
    ("Act.b",  "Min Activ spacing",                L_ACTIV,   "space",   0.21),
    # --- GatPoly ---
    ("Gat.a",  "Min GatPoly width",                L_GATPOLY, "width",   0.13),
    ("Gat.b",  "Min GatPoly spacing",              L_GATPOLY, "space",   0.18),
    # --- Cont ---
    ("Cnt.a",  "Min Cont size (width)",             L_CONT,    "width",   0.16),
    ("Cnt.b",  "Min Cont spacing",                  L_CONT,    "space",   0.18),
    # --- Metal1 ---
    ("M1.a",   "Min Metal1 width",                  L_METAL1,  "width",   0.16),
    ("M1.b",   "Min Metal1 spacing",                L_METAL1,  "space",   0.18),
    # --- Metal2 ---
    ("M2.a",   "Min Metal2 width",                  L_METAL2,  "width",   0.20),
    ("M2.b",   "Min Metal2 spacing",                L_METAL2,  "space",   0.21),
    # --- Metal3 ---
    ("M3.a",   "Min Metal3 width",                  L_METAL3,  "width",   0.20),
    ("M3.b",   "Min Metal3 spacing",                L_METAL3,  "space",   0.21),
    # --- Via1 ---
    ("V1.a",   "Min Via1 size (width)",              L_VIA1,    "width",   0.19),
    ("V1.b",   "Min Via1 spacing",                   L_VIA1,    "space",   0.22),
    # --- SalBlock ---
    ("Sal.a",  "Min SalBlock width",                L_SALBLOCK,"width",   0.50),
    # --- NWell ---
    ("NW.a",   "Min NWell width",                   L_NWELL,   "width",   0.62),
    ("NW.b",   "Min NWell spacing",                 L_NWELL,   "space",   0.62),
    # --- Metal5 ---
    ("M5.a",   "Min Metal5 width",                  L_METAL5,  "width",   0.20),
    ("M5.b",   "Min Metal5 spacing",                L_METAL5,  "space",   0.21),
    # --- Cmim ---
    ("MIM.a",  "Min Cmim size",                     L_CMIM,    "width",   1.14),
    ("MIM.b",  "Min Cmim spacing",                  L_CMIM,    "space",   0.60),
    # --- TopMetal1 ---
    ("TM1.a",  "Min TopMetal1 width",               L_TOPMETAL1,"width",  0.20),
    ("TM1.b",  "Min TopMetal1 spacing",             L_TOPMETAL1,"space",  0.21),
]

# Enclosure rules: (name, desc, inner_layer, outer_layer, min_enc_um)
ENC_RULES = [
    ("Cnt.c",  "Min Activ enclosure of Cont",       L_CONT,    L_ACTIV,   0.07),
    ("Cnt.d",  "Min GatPoly enclosure of Cont",     L_CONT,    L_GATPOLY, 0.07),
    ("V1.c",   "Min Metal1 enclosure of Via1",      L_VIA1,    L_METAL1,  0.01),
    ("M2.c",   "Min Metal2 enclosure of Via1",      L_VIA1,    L_METAL2,  0.005),
    ("NW.c",   "Min NWell enclosure of Activ(pSD)",  L_ACTIV,   L_NWELL,   0.31),
    ("MIM.c",  "Min Metal5 enclosure of Cmim",      L_CMIM,    L_METAL5,  0.60),
]


def run_drc(gds_path, topcell=None):
    """Run DRC checks. Returns list of (rule_name, description, count, markers)."""
    layout = pya.Layout()
    layout.read(gds_path)

    if topcell:
        top = layout.cell(topcell)
        if top is None:
            print(f"ERROR: Cell '{topcell}' not found")
            sys.exit(1)
    else:
        top = layout.top_cell()

    print(f"Running DRC on: {gds_path}")
    print(f"Top cell: {top.name}")
    print(f"Bounding box: {top.dbbox()}")
    print()

    results = []
    total_errors = 0

    # --- Width and spacing checks ---
    print(f"{'Rule':<8} {'Description':<42} {'Errors':>6}")
    print("-" * 60)

    for rule_name, desc, layer_def, check_type, value in RULES:
        li = layout.layer(*layer_def)
        region = pya.Region(top.begin_shapes_rec(li))

        if region.is_empty():
            # No shapes on this layer — skip
            continue

        value_dbu = int(round(value / layout.dbu))
        markers = pya.Region()

        if check_type == "width":
            markers = region.width_check(value_dbu)
        elif check_type == "space":
            markers = region.space_check(value_dbu)

        count = markers.size()
        status = "PASS" if count == 0 else f"FAIL"
        results.append((rule_name, desc, count, markers))
        total_errors += count

        if count > 0:
            print(f"{rule_name:<8} {desc:<42} {count:>6}  *** {status} ***")
        else:
            print(f"{rule_name:<8} {desc:<42} {count:>6}  {status}")

    # --- Enclosure checks ---
    print()
    print(f"{'Rule':<8} {'Description':<42} {'Errors':>6}")
    print("-" * 60)

    for rule_name, desc, inner_def, outer_def, min_enc in ENC_RULES:
        li_inner = layout.layer(*inner_def)
        li_outer = layout.layer(*outer_def)
        inner = pya.Region(top.begin_shapes_rec(li_inner))
        outer = pya.Region(top.begin_shapes_rec(li_outer))

        if inner.is_empty() or outer.is_empty():
            continue

        enc_dbu = int(round(min_enc / layout.dbu))

        # Only check inner shapes that actually overlap with outer
        # (e.g., only contacts inside Activ for Activ-enclosure rule,
        #  not contacts that sit on GatPoly resistors)
        inner_in_outer = inner & outer
        if inner_in_outer.is_empty():
            continue

        # Check: inner must be enclosed by outer with min_enc margin
        inner_grown = inner_in_outer.sized(enc_dbu)
        violations = inner_grown - outer
        count = violations.size()
        total_errors += count
        results.append((rule_name, desc, count, violations))

        if count > 0:
            print(f"{rule_name:<8} {desc:<42} {count:>6}  *** FAIL ***")
        else:
            print(f"{rule_name:<8} {desc:<42} {count:>6}  PASS")

    # --- Summary ---
    print()
    print("=" * 60)
    if total_errors == 0:
        print(f"DRC CLEAN — 0 violations")
    else:
        print(f"DRC ERRORS — {total_errors} total violations")
        print()
        print("Violations by rule:")
        for rule_name, desc, count, _ in results:
            if count > 0:
                print(f"  {rule_name}: {count} ({desc})")
    print("=" * 60)

    return results, total_errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <gds_file> [top_cell]")
        sys.exit(1)

    gds = sys.argv[1]
    cell = sys.argv[2] if len(sys.argv) > 2 else None
    results, errors = run_drc(gds, cell)
    sys.exit(0 if errors == 0 else 1)
