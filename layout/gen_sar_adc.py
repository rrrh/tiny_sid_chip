#!/usr/bin/env python3
"""
Generate 8-bit SAR ADC layout for IHP SG13G2 130nm.

Architecture:
  vin ──→ [Sample SW] ──→ [Binary Cap DAC] ──→ [Dynamic Comparator] ──→ SAR Logic ──→ dout[7:0]
                               ↑                                            │
                               └──── switch array ←─────────────────────────┘

Components:
  1. Sample-and-hold switch (NMOS, bootstrapped for linearity)
  2. Binary-weighted capacitive DAC (MIM caps)
     C_unit = 30 fF → 20 µm² each (MIM 1.5 fF/µm²)
     Array: 1C, 1C, 2C, 4C, 8C, 16C, 32C, 64C, 128C = 256 units total
     Total cap = 7.68 pF → 5120 µm²
  3. Dynamic latch comparator (StrongARM topology)
     - Input diff pair: NMOS W=2µm L=0.5µm (longer L for offset)
     - Latch: cross-coupled PMOS+NMOS inverters
     - ~12 transistors total
  4. SAR successive-approximation register
     - 8-bit shift register + control FSM
     - ~50 transistors (digital standard cells equivalent)

Macro size target: 42 × 45 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *
import math

# ===========================================================================
# Design parameters
# ===========================================================================
NBITS     = 8
C_UNIT    = 2.0        # fF per unit cap (kT/C noise ≈ 2.8 mV, ~7 bits)
C_UNIT_AREA = C_UNIT / MIM_CAP_DENSITY  # ~1.33 µm² per unit

MACRO_W   = 42.0
MACRO_H   = 45.0

# Cap sizes (MIM): each cap is rectangular
# For matching, use common-centroid or at least regular array
UNIT_SIDE = math.ceil(C_UNIT_AREA ** 0.5 * 10) / 10  # ~4.5 µm → round up
CAP_PITCH = UNIT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5  # pitch between unit caps

# Comparator area
COMP_W    = 15.0
COMP_H    = 20.0

# SAR logic area
SAR_W     = 15.0
SAR_H     = 18.0

# ===========================================================================
# Layout builders
# ===========================================================================

def draw_mim_unit(cell, layout, x, y, side):
    """Draw a single MIM unit cap. Returns center coordinates."""
    li_m5   = layout.layer(*L_METAL5)
    li_cmim = layout.layer(*L_CMIM)
    li_tm1  = layout.layer(*L_TOPMETAL1)

    # Cmim
    cell.shapes(li_cmim).insert(rect(x, y, x + side, y + side))
    # Metal5 bottom plate
    enc = MIM_ENC_M5
    cell.shapes(li_m5).insert(rect(x - enc, y - enc, x + side + enc, y + side + enc))
    # TopMetal1 top plate (min TM1 width = 1.64 µm)
    tm1_enc = max(0.1, (1.64 - side) / 2 + 0.01) if side < 1.44 else 0.1
    cell.shapes(li_tm1).insert(rect(x - tm1_enc, y - tm1_enc, x + side + tm1_enc, y + side + tm1_enc))

    return (x + side / 2, y + side / 2)


def draw_cap_array(cell, layout, x0, y0, num_units, side, cols=16):
    """
    Draw a binary-weighted cap as an array of unit caps.
    Arrange in rows of 'cols' columns.
    Returns bounding box (x1,y1,x2,y2) and list of unit centers.
    """
    pitch = side + MIM_SPACE + 2 * MIM_ENC_M5
    centers = []
    for i in range(num_units):
        col = i % cols
        row = i // cols
        cx = x0 + col * pitch
        cy = y0 + row * pitch
        c = draw_mim_unit(cell, layout, cx, cy, side)
        centers.append(c)

    # Bounding box
    max_col = min(num_units, cols)
    max_row = (num_units + cols - 1) // cols
    x2 = x0 + max_col * pitch
    y2 = y0 + max_row * pitch
    return (x0, y0, x2, y2), centers


def draw_nmos_transistor(cell, layout, x, y, w, l):
    """Draw NMOS transistor, return pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)
    li_nsd = layout.layer(*L_NSD)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    cell.shapes(li_nsd).insert(rect(x - 0.1, y - 0.1, x + act_len + 0.1, y + w + 0.1))

    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    # Source contact
    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    s_cy = y + w / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(s_cx, s_cy, s_cx + CONT_SIZE, s_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(s_cx - CONT_ENC_M1, s_cy - CONT_ENC_M1,
                                    s_cx + CONT_SIZE + CONT_ENC_M1,
                                    s_cy + CONT_SIZE + CONT_ENC_M1))

    # Drain contact
    d_cx = gp_x1 + l + (sd_ext - CONT_SIZE) / 2
    cell.shapes(li_cnt).insert(rect(d_cx, s_cy, d_cx + CONT_SIZE, s_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(d_cx - CONT_ENC_M1, s_cy - CONT_ENC_M1,
                                    d_cx + CONT_SIZE + CONT_ENC_M1,
                                    s_cy + CONT_SIZE + CONT_ENC_M1))

    return {
        'gate':   (gp_x1 + l / 2, y + w + GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
    }


def draw_pmos_transistor(cell, layout, x, y, w, l, draw_nwell=True):
    """Draw PMOS transistor (in NWell), return pin centers dict."""
    li_act  = layout.layer(*L_ACTIV)
    li_gp   = layout.layer(*L_GATPOLY)
    li_psd  = layout.layer(*L_PSD)
    li_nw   = layout.layer(*L_NWELL)
    li_cnt  = layout.layer(*L_CONT)
    li_m1   = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + l + sd_ext

    # NWell (enclose Activ) — can be skipped when a shared NWell is drawn
    if draw_nwell:
        nw_enc = NWELL_ENC_ACTIV
        cell.shapes(li_nw).insert(rect(x - nw_enc, y - nw_enc,
                                        x + act_len + nw_enc, y + w + nw_enc))

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    cell.shapes(li_psd).insert(rect(x - 0.1, y - 0.1, x + act_len + 0.1, y + w + 0.1))

    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    s_cy = y + w / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(s_cx, s_cy, s_cx + CONT_SIZE, s_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(s_cx - CONT_ENC_M1, s_cy - CONT_ENC_M1,
                                    s_cx + CONT_SIZE + CONT_ENC_M1,
                                    s_cy + CONT_SIZE + CONT_ENC_M1))

    d_cx = gp_x1 + l + (sd_ext - CONT_SIZE) / 2
    cell.shapes(li_cnt).insert(rect(d_cx, s_cy, d_cx + CONT_SIZE, s_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(d_cx - CONT_ENC_M1, s_cy - CONT_ENC_M1,
                                    d_cx + CONT_SIZE + CONT_ENC_M1,
                                    s_cy + CONT_SIZE + CONT_ENC_M1))

    return {
        'gate':   (gp_x1 + l / 2, y - GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
    }


def draw_strongarm_comparator(cell, layout, x, y):
    """
    Draw a StrongARM dynamic latch comparator.
    Topology: tail NMOS + input diff pair (NMOS) + cross-coupled latch (PMOS+NMOS)

    Transistors (12 total):
      M_tail:   NMOS W=4µm  (tail current, clocked)
      M_inp/inn: NMOS W=2µm L=0.5µm (input pair, longer L for lower offset)
      M_p1/p2:  PMOS W=2µm  (latch load)
      M_n1/n2:  NMOS W=1µm  (latch)
      M_pr1/pr2: PMOS W=1µm (precharge/reset)
      M_sr1/sr2: NMOS W=1µm (S-R latch output buffer)
    """
    # Input pair
    inp = draw_nmos_transistor(cell, layout, x, y, w=2.0, l=0.50)
    inn = draw_nmos_transistor(cell, layout, x + 5.0, y, w=2.0, l=0.50)

    # Tail NMOS (below input pair)
    tail = draw_nmos_transistor(cell, layout, x + 2.0, y - 4.0, w=4.0, l=0.13)

    # PMOS latch (above input pair)
    p1 = draw_pmos_transistor(cell, layout, x, y + 5.0, w=2.0, l=0.13)
    p2 = draw_pmos_transistor(cell, layout, x + 5.0, y + 5.0, w=2.0, l=0.13)

    # NMOS latch
    n1 = draw_nmos_transistor(cell, layout, x, y + 10.0, w=1.0, l=0.13)
    n2 = draw_nmos_transistor(cell, layout, x + 5.0, y + 10.0, w=1.0, l=0.13)

    # Reset PMOS
    pr1 = draw_pmos_transistor(cell, layout, x + 1.0, y + 13.0, w=1.0, l=0.13)
    pr2 = draw_pmos_transistor(cell, layout, x + 6.0, y + 13.0, w=1.0, l=0.13)

    return {
        'inp': inp, 'inn': inn, 'tail': tail,
        'outp': n1['drain'], 'outn': n2['drain'],
        'clk': tail['gate'],
        'bbox': (x - 0.5, y - 5.0, x + COMP_W, y + COMP_H),
    }


def draw_sar_logic_block(cell, layout, x, y, w, h):
    """
    Draw SAR logic as a block of standard-cell-like rows.
    For the hard macro, this contains the 8-bit shift register and FSM.
    Represented as rows of NMOS/PMOS pairs (inverters, NAND gates).

    Simplified: draw the bounding area with representative transistor rows
    to establish the physical presence. Full transistor-level layout would
    require a gate-level netlist.
    """
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    li_nw = layout.layer(*L_NWELL)

    row_h = 2.5   # standard cell row height
    nrows = int(h / row_h)

    for r in range(nrows):
        ry = y + r * row_h
        # Alternating NMOS/PMOS rows (simplified: just draw transistors)
        ncols = int(w / 1.5)
        for c in range(ncols):
            tx = x + c * 1.5
            if r % 2 == 0:
                draw_nmos_transistor(cell, layout, tx, ry + 0.2, w=0.8, l=0.13)
            else:
                draw_pmos_transistor(cell, layout, tx, ry + 0.2, w=0.8, l=0.13,
                                     draw_nwell=False)

        # Shared NWell for entire PMOS row (instead of per-transistor NWell)
        if r % 2 == 1:
            nw_enc = NWELL_ENC_ACTIV
            cell.shapes(li_nw).insert(rect(x - nw_enc, ry + 0.2 - nw_enc,
                                            x + (ncols - 1) * 1.5 + 0.77 + nw_enc,
                                            ry + 0.2 + 0.8 + nw_enc))

        # Power rails per row
        cell.shapes(li_m1).insert(rect(x, ry, x + w, ry + M1_WIDTH))
        cell.shapes(li_m1).insert(rect(x, ry + row_h - M1_WIDTH, x + w, ry + row_h))

    # M2 vertical power straps
    cell.shapes(li_m2).insert(rect(x, y, x + M2_WIDTH * 2, y + h))
    cell.shapes(li_m2).insert(rect(x + w - M2_WIDTH * 2, y, x + w, y + h))

    return {
        'bbox': (x, y, x + w, y + h),
    }


# ===========================================================================
# Main: build the SAR ADC
# ===========================================================================
def build_sar_adc():
    layout = new_layout()
    top = layout.create_cell("sar_adc_8bit")

    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)

    # =====================================================================
    # Binary-weighted capacitive DAC (lower-left, largest block)
    # =====================================================================
    # Cap array: 256 unit caps total (1+1+2+4+8+16+32+64+128)
    # Unit cap side ≈ 4.5 µm, pitch ≈ 4.5 + 0.6 + 1.2 = 6.3 µm
    # 16 columns × 16 rows = 256 units → 16 × 6.3 = ~101 µm wide
    # That's too wide. Use smaller unit or more rows.
    # With 12 columns: 22 rows needed → 22 × 6.3 = 139 µm tall (too tall)
    #
    # Optimization: merge unit caps into larger rectangles per bit.
    # Bit 0: 1C (4.5×4.5), Bit 1: 1C, Bit 2: 2C (4.5×9.0), ...
    # Bit 7: 128C → merge into one big cap: 128 × 20 = 2560 µm² → 50.6 × 50.6 µm
    #
    # Better: use larger unit cap side and merge per-bit.
    cap_region_x = 2.0
    cap_region_y = 4.0
    cap_cursor_x = cap_region_x
    cap_cursor_y = cap_region_y

    # Draw merged caps per bit (each bit = single rectangle for area efficiency)
    bit_areas = []
    for bit in range(NBITS + 1):  # +1 for LSB dummy cap
        if bit == 0:
            nunits = 1  # dummy LSB cap
        else:
            nunits = 2 ** (bit - 1)  # 1,1,2,4,8,16,32,64,128

        area = nunits * C_UNIT_AREA
        # Make each cap roughly square
        side = max(MIM_MIN_SIZE, area ** 0.5)
        # Ensure minimum dimensions
        w_cap = max(MIM_MIN_SIZE, side)
        h_cap = max(MIM_MIN_SIZE, area / w_cap)

        # Place caps in a column, stacking vertically
        if cap_cursor_y + h_cap + MIM_SPACE + 2 * MIM_ENC_M5 > MACRO_H - 6:
            # Move to next column
            cap_cursor_x += 12.0
            cap_cursor_y = cap_region_y

        li_m5   = layout.layer(*L_METAL5)
        li_cmim = layout.layer(*L_CMIM)
        li_tm1  = layout.layer(*L_TOPMETAL1)

        cx = cap_cursor_x
        cy = cap_cursor_y

        # Cmim
        top.shapes(li_cmim).insert(rect(cx, cy, cx + w_cap, cy + h_cap))
        # Metal5 bottom plate
        enc = MIM_ENC_M5
        top.shapes(li_m5).insert(rect(cx - enc, cy - enc,
                                       cx + w_cap + enc, cy + h_cap + enc))
        # TopMetal1 top plate (min TM1 width = 1.64 µm)
        tm1_enc_w = max(0.1, (1.64 - w_cap) / 2 + 0.01) if w_cap < 1.44 else 0.1
        tm1_enc_h = max(0.1, (1.64 - h_cap) / 2 + 0.01) if h_cap < 1.44 else 0.1
        top.shapes(li_tm1).insert(rect(cx - tm1_enc_w, cy - tm1_enc_h,
                                        cx + w_cap + tm1_enc_w, cy + h_cap + tm1_enc_h))

        bit_areas.append({
            'bit': bit, 'nunits': nunits, 'area': area,
            'x': cx, 'y': cy, 'w': w_cap, 'h': h_cap,
            'center': (cx + w_cap / 2, cy + h_cap / 2),
        })

        cap_cursor_y += h_cap + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0

    # =====================================================================
    # Sample switch (NMOS, left edge near vin pin)
    # =====================================================================
    sw_sample = draw_nmos_transistor(top, layout, x=2.0, y=22.0, w=3.0, l=0.13)

    # =====================================================================
    # Dynamic comparator (right side of macro)
    # =====================================================================
    comp = draw_strongarm_comparator(top, layout, x=27.0, y=25.0)

    # =====================================================================
    # SAR logic (right side, below comparator)
    # =====================================================================
    sar = draw_sar_logic_block(top, layout, x=27.0, y=4.0, w=SAR_W, h=SAR_H)

    # =====================================================================
    # Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS)
    # =====================================================================
    # Near sample switch (x=2, y=22)
    draw_ptap(top, layout, 2.0, 19.0)
    draw_ptap(top, layout, 6.0, 19.0)
    # Along comparator NMOS region (x=27-37, y=21-37)
    for xt in [26.0, 30.0, 34.0, 38.0]:
        draw_ptap(top, layout, xt, 23.0)
        draw_ptap(top, layout, xt, 33.0)
    # SAR logic perimeter taps (block at x=27-42, y=4-22)
    # Place outside the dense transistor grid to avoid Activ spacing issues
    for xt in [24.5, 31.0, 36.5, 41.5]:
        draw_ptap(top, layout, xt, 2.5)   # below SAR logic
        draw_ptap(top, layout, xt, 22.5)  # above SAR logic
    # Left/right perimeter of SAR logic
    for yt in [8.0, 14.0, 20.0]:
        draw_ptap(top, layout, 24.5, yt)
        draw_ptap(top, layout, 41.5, yt)
    # Near cap region
    for xt in [2.0, 10.0, 18.0]:
        draw_ptap(top, layout, xt, 2.5)

    # =====================================================================
    # Metal routing (simplified — key signal paths)
    # =====================================================================
    # Vin → sample switch gate → connected externally
    # Sample switch drain → cap DAC common node (top plates)
    # Comparator output → SAR logic input
    # SAR logic → cap DAC switch control (per-bit)

    # M2 horizontal bus for SAR bit outputs → cap switches
    for bit in range(NBITS):
        bus_y = 24.0 + bit * 1.5
        # From SAR logic to cap array
        top.shapes(li_m2).insert(rect(cap_region_x, bus_y - M2_WIDTH / 2,
                                       27.0, bus_y + M2_WIDTH / 2))

    # =====================================================================
    # Power rails
    # =====================================================================
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # Pin labels (Metal2, matching LEF)
    # =====================================================================
    # Left edge pins
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, 5.0 - 0.5, 0.5, 5.0 + 0.5), "clk", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, 9.0 - 0.5, 0.5, 9.0 + 0.5), "rst_n", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, 13.0 - 0.5, 0.5, 13.0 + 0.5), "start", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, 22.0 - 0.5, 0.5, 22.0 + 0.5), "vin", layout)

    # Right edge pins
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, 5.0 - 0.5, MACRO_W, 5.0 + 0.5), "eoc", layout)

    for bit in range(NBITS):
        pin_y = 9.0 + bit * 4.5
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(MACRO_W - 0.5, pin_y - 0.5, MACRO_W, pin_y + 0.5),
                      f"dout[{bit}]", layout)

    # Power pins
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H), "vdd", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 2.0), "vss", layout)

    # --- PR Boundary (IHP SG13G2: layer 189/0) ---
    li_bnd = layout.layer(189, 0)
    top.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout, top


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "sar_adc_8bit.gds")

    layout, top = build_sar_adc()
    layout.write(outpath)

    total_cap = sum(2**max(0, b-1) for b in range(NBITS+1)) * C_UNIT
    print(f"Wrote {outpath}")
    print(f"  Unit cap: {C_UNIT:.0f} fF ({C_UNIT_AREA:.0f} µm²)")
    print(f"  Total cap: {total_cap:.0f} fF ({total_cap/1000:.2f} pF)")
    print(f"  Comparator: StrongARM, {COMP_W}×{COMP_H} µm")
    print(f"  SAR logic: {SAR_W}×{SAR_H} µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
