#!/usr/bin/env python3
"""Add TopMetal1 power straps + via stacks (Metal3→TopMetal1) to macro GDS files.

For each macro, adds:
  - TopMetal1 power straps over vdd (top) and vss (bottom) rails
  - Via stack: Metal3 → Via3 → Metal4 → Via4 → Metal5 → TopVia1 → TopMetal1
  - Via arrays at regular intervals along the power rails
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

import klayout.db as pya

# Via stack layer pairs: (via_layer, lower_metal, upper_metal, via_size, enc_lower, enc_upper)
VIA_STACK = [
    (L_VIA3,    L_METAL3, L_METAL4, VIA3_SIZE,    VIA3_ENC_M3,    VIA3_ENC_M4),
    (L_VIA4,    L_METAL4, L_METAL5, VIA4_SIZE,    VIA4_ENC_M4,    VIA4_ENC_M5),
    (L_TOPVIA1, L_METAL5, L_TOPMETAL1, TOPVIA1_SIZE, TOPVIA1_ENC_M5, TOPVIA1_ENC_TM1),
]

# Macro definitions: (gds_path, cell_name, width, height, vdd_rect, vss_rect)
# vdd_rect / vss_rect = (x1, y1, x2, y2) of Metal3 power pin
MACROS = {
    "r2r_dac_8bit": {
        "gds": "../macros/gds/r2r_dac_8bit.gds",
        "width": 36.0, "height": 30.0,
        "vdd": (0.0, 28.5, 36.0, 30.0),  # Metal3 top rail
        "vss": (0.0, 0.0, 36.0, 1.5),    # Metal3 bottom rail
    },
    "svf_2nd": {
        "gds": "../macros/gds/svf_2nd.gds",
        "width": 64.0, "height": 67.0,
        "vdd": (0.0, 65.0, 64.0, 67.0),
        "vss": (0.0, 0.0, 64.0, 2.0),
        # TM1 strap y overrides: push VSS strap down to clear cap TM1 at y=3.5
        # (need ≥1.64 µm gap → strap top ≤ 1.36)
        "tm1_vss": (-0.28, 1.36),
    },
    "sar_adc_8bit": {
        "gds": "../macros/gds/sar_adc_8bit.gds",
        "width": 42.0, "height": 42.0,
        "vdd": (0.0, 40.0, 42.0, 42.0),
        "vss": (0.0, 0.0, 42.0, 2.0),
    },
}


def add_via_array(cell, layout, x_start, x_end, y_center, rail_height):
    """Add a row of via stacks from Metal3 to TopMetal1 along a power rail.

    Places via stacks at regular intervals from x_start to x_end,
    centered at y_center within a rail of given height.
    """
    # TopVia1 is the largest via (0.42µm) with largest enclosure (0.42µm on TM1)
    # Total pad needed on TopMetal1: 0.42 + 2*0.42 = 1.26 µm
    # Via pitch: at least via_size + space = 0.42 + 0.42 = 0.84 for TopVia1
    # Use 2.0 µm pitch for comfortable spacing of the full stack
    via_pitch = 2.0

    # Inset from rail edges to keep vias inside
    x_margin = 1.0
    x = x_start + x_margin

    while x + 0.5 < x_end - x_margin:
        # Place via stack at (x, y_center)
        for via_layer, lower_metal, upper_metal, via_size, enc_lower, enc_upper in VIA_STACK:
            li_via = layout.layer(*via_layer)
            li_lower = layout.layer(*lower_metal)
            li_upper = layout.layer(*upper_metal)

            # Via centered at (x, y_center)
            vx1 = x - via_size / 2
            vy1 = y_center - via_size / 2
            vx2 = x + via_size / 2
            vy2 = y_center + via_size / 2
            cell.shapes(li_via).insert(rect(vx1, vy1, vx2, vy2))

            # Metal pads (enclosures) — only add intermediate metals (Metal4, Metal5)
            # Metal3 already exists as power rail; TopMetal1 will be added as full strap
            if lower_metal not in (L_METAL3,):
                pad_x1 = vx1 - enc_lower
                pad_y1 = vy1 - enc_lower
                pad_x2 = vx2 + enc_lower
                pad_y2 = vy2 + enc_lower
                cell.shapes(li_lower).insert(rect(pad_x1, pad_y1, pad_x2, pad_y2))

            if upper_metal not in (L_TOPMETAL1,):
                pad_x1 = vx1 - enc_upper
                pad_y1 = vy1 - enc_upper
                pad_x2 = vx2 + enc_upper
                pad_y2 = vy2 + enc_upper
                cell.shapes(li_upper).insert(rect(pad_x1, pad_y1, pad_x2, pad_y2))

        x += via_pitch


def process_macro(name, info):
    """Add TopMetal1 power straps and via stacks to a macro GDS."""
    gds_path = os.path.join(os.path.dirname(__file__), info["gds"])
    gds_path = os.path.normpath(gds_path)

    print(f"Processing {name}: {gds_path}")

    layout = pya.Layout()
    layout.read(gds_path)

    # Find the top cell
    top_cell = layout.top_cell()
    if top_cell is None:
        # Try finding by name
        for ci in range(layout.cells()):
            c = layout.cell(ci)
            if c.name == name or name in c.name:
                top_cell = c
                break

    if top_cell is None:
        print(f"  ERROR: Could not find top cell in {gds_path}")
        return False

    print(f"  Top cell: {top_cell.name}")

    li_tm1 = layout.layer(*L_TOPMETAL1)

    # Add TopMetal1 straps over vdd and vss rails
    for rail_name, rail_rect in [("vdd", info["vdd"]), ("vss", info["vss"])]:
        x1, y1, x2, y2 = rail_rect
        rail_height = y2 - y1
        y_center = (y1 + y2) / 2

        # Check for per-rail TM1 y override (to avoid TM1.b spacing violations)
        tm1_override_key = f"tm1_{rail_name}"
        if tm1_override_key in info:
            tm1_y1, tm1_y2 = info[tm1_override_key]
        else:
            # TopMetal1 strap: same x extent as Metal3 rail, slightly inset in y
            # to avoid extending past the macro boundary
            tm1_margin = 0.1  # small inset from rail edges
            tm1_y1 = y1 + tm1_margin
            tm1_y2 = y2 - tm1_margin

            # Ensure minimum TopMetal1 width (TM1.a min = 1.64 µm)
            tm1_width = tm1_y2 - tm1_y1
            if tm1_width < 1.64:
                macro_h = info.get("height", 1e6)
                if y_center < macro_h / 2:
                    # Bottom rail: align to bottom, extend upward
                    tm1_y1 = y1
                    tm1_y2 = y1 + 1.64
                else:
                    # Top rail: align to top, extend downward
                    tm1_y2 = y2
                    tm1_y1 = y2 - 1.64

        print(f"  Adding TopMetal1 strap for {rail_name}: ({x1:.1f}, {tm1_y1:.2f}) - ({x2:.1f}, {tm1_y2:.2f})")
        top_cell.shapes(li_tm1).insert(rect(x1, tm1_y1, x2, tm1_y2))

        # Add via array along the rail — center vias within TM1 strap
        via_y_center = (tm1_y1 + tm1_y2) / 2
        add_via_array(top_cell, layout, x1, x2, via_y_center, rail_height)
        print(f"  Added via stack array for {rail_name}")

    # Write back
    layout.write(gds_path)
    print(f"  Wrote {gds_path}")
    return True


def main():
    ok = True
    for name, info in MACROS.items():
        if not process_macro(name, info):
            ok = False

    if ok:
        print("\nAll macros updated successfully.")
    else:
        print("\nSome macros failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
