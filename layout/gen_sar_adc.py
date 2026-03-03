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

Macro size target: 42 × 42 µm
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
MACRO_H   = 42.0

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
    # TopMetal1 top plate — enforce TM1 min width 1.64µm
    TM1_MIN = 1.64
    tm1_side = max(side + 0.2, TM1_MIN)
    tm1_enc = (tm1_side - side) / 2
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

    # Offset gate contact 0.10µm beyond GatPoly extension for Cnt.e clearance
    gc_offset = 0.10
    return {
        'gate':   (gp_x1 + l / 2, y + w + GATPOLY_EXT + gc_offset),
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

    # Offset gate contact 0.10µm beyond GatPoly extension for Cnt.e clearance
    gc_offset = 0.10
    return {
        'gate':   (gp_x1 + l / 2, y - GATPOLY_EXT - gc_offset),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
    }


def draw_via1(cell, layout, x, y):
    """Via1 with M1+M2 pads."""
    li_v1 = layout.layer(*L_VIA1)
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    hs = VIA1_SIZE / 2
    cell.shapes(li_v1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e1 = VIA1_ENC_M1 + hs
    cell.shapes(li_m1).insert(rect(x - e1, y - e1, x + e1, y + e1))
    e2 = VIA1_ENC_M2 + hs
    cell.shapes(li_m2).insert(rect(x - e2, y - e2, x + e2, y + e2))


def draw_via2(cell, layout, x, y):
    """Via2 with M2+M3 pads."""
    li_v2 = layout.layer(*L_VIA2)
    li_m2 = layout.layer(*L_METAL2)
    li_m3 = layout.layer(*L_METAL3)
    hs = VIA2_SIZE / 2
    cell.shapes(li_v2).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e2 = VIA2_ENC_M2 + hs
    cell.shapes(li_m2).insert(rect(x - e2, y - e2, x + e2, y + e2))
    e3 = VIA2_ENC_M3 + hs
    cell.shapes(li_m3).insert(rect(x - e3, y - e3, x + e3, y + e3))


def draw_via3(cell, layout, x, y):
    """Via3 with M3+M4 pads."""
    li_v3 = layout.layer(*L_VIA3)
    li_m3 = layout.layer(*L_METAL3)
    li_m4 = layout.layer(*L_METAL4)
    hs = VIA3_SIZE / 2
    cell.shapes(li_v3).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e3 = VIA3_ENC_M3 + hs
    cell.shapes(li_m3).insert(rect(x - e3, y - e3, x + e3, y + e3))
    e4 = VIA3_ENC_M4 + hs
    cell.shapes(li_m4).insert(rect(x - e4, y - e4, x + e4, y + e4))


def draw_via4(cell, layout, x, y):
    """Via4 with M4+M5 pads."""
    li_v4 = layout.layer(*L_VIA4)
    li_m4 = layout.layer(*L_METAL4)
    li_m5 = layout.layer(*L_METAL5)
    hs = VIA4_SIZE / 2
    cell.shapes(li_v4).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e4 = VIA4_ENC_M4 + hs
    cell.shapes(li_m4).insert(rect(x - e4, y - e4, x + e4, y + e4))
    e5 = VIA4_ENC_M5 + hs
    cell.shapes(li_m5).insert(rect(x - e5, y - e5, x + e5, y + e5))


def draw_topvia1(cell, layout, x, y):
    """TopVia1 with M5+TM1 pads. TM1 pad enforces min width 1.64µm."""
    li_tv1 = layout.layer(*L_TOPVIA1)
    li_m5  = layout.layer(*L_METAL5)
    li_tm1 = layout.layer(*L_TOPMETAL1)
    hs = TOPVIA1_SIZE / 2
    cell.shapes(li_tv1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e5 = TOPVIA1_ENC_M5 + hs
    cell.shapes(li_m5).insert(rect(x - e5, y - e5, x + e5, y + e5))
    TM1_MIN_HALF = 1.64 / 2
    et = max(TOPVIA1_ENC_TM1 + hs, TM1_MIN_HALF)
    cell.shapes(li_tm1).insert(rect(x - et, y - et, x + et, y + et))


def draw_via_stack_m2_to_m5(cell, layout, x, y):
    """Full via stack M2->M3->M4->M5 at a single point."""
    draw_via2(cell, layout, x, y)
    draw_via3(cell, layout, x, y)
    draw_via4(cell, layout, x, y)


def draw_via_stack_m2_to_tm1(cell, layout, x, y):
    """Full via stack M2->M3->M4->M5->TM1 at a single point."""
    draw_via_stack_m2_to_m5(cell, layout, x, y)
    draw_topvia1(cell, layout, x, y)


def draw_gate_contact(cell, layout, x, y):
    """Place contact + M1 pad on GatPoly at (x,y) for gate connection.
    Also extends GatPoly to ensure min enclosure of contact (Cnt.d ≥ 0.07)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)
    hs = CONT_SIZE / 2
    gp_enc = CONT_ENC_GATPOLY  # 0.08 µm (includes margin over 0.07 min)
    # Extend GatPoly to enclose contact (merges with existing GatPoly)
    cell.shapes(li_gp).insert(rect(x - hs - gp_enc, y - hs - gp_enc,
                                     x + hs + gp_enc, y + hs + gp_enc))
    cell.shapes(li_cnt).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e = CONT_ENC_M1
    cell.shapes(li_m1).insert(rect(x - hs - e, y - hs - e, x + hs + e, y + hs + e))


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
        'p1': p1, 'p2': p2,
        'outp': n1['drain'], 'outn': n2['drain'],
        'clk': tail['gate'],
        'tail_source': tail['source'],
        'p1_source': p1['source'], 'p2_source': p2['source'],
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
        # Leave 2µm margin on right for perimeter ptaps (Gat.d, Cnt.g1 clearance)
        ncols = int((w - 2.0) / 1.5)
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

    # M2 vertical power straps (offset inward to avoid shorting to signal pins;
    # left strap starts at y+0.5 to clear bit 7 cap M2 jog at y=4.0)
    cell.shapes(li_m2).insert(rect(x + 0.3, y + 0.5, x + 0.3 + M2_WIDTH * 2, y + h))
    cell.shapes(li_m2).insert(rect(x + w - 1.2, y, x + w - 0.8, y + h))

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
        # TopMetal1 top plate — enforce TM1 min width 1.64µm in BOTH dimensions
        TM1_MIN = 1.64
        tm1_w = max(w_cap + 0.2, TM1_MIN)  # at least 1.64µm wide
        tm1_h = max(h_cap + 0.2, TM1_MIN)  # at least 1.64µm tall
        tm1_enc_w = (tm1_w - w_cap) / 2
        tm1_enc_h = (tm1_h - h_cap) / 2
        top.shapes(li_tm1).insert(rect(cx - tm1_enc_w, cy - tm1_enc_h,
                                        cx + w_cap + tm1_enc_w, cy + h_cap + tm1_enc_h))

        bit_areas.append({
            'bit': bit, 'nunits': nunits, 'area': area,
            'x': cx, 'y': cy, 'w': w_cap, 'h': h_cap,
            'center': (cx + w_cap / 2, cy + h_cap / 2),
        })

        cap_cursor_y += h_cap + MIM_SPACE + 2 * MIM_ENC_M5 + 1.5  # +1.5 (was 1.0) for TM1.b clearance

    # =====================================================================
    # Via stacks: connect cap plates to M2 routing
    # =====================================================================
    # Each cap's bottom plate (M5) gets a via stack down to M2 for SAR bit control.
    # Each cap's top plate (TM1) gets a via stack down to M2 for the common
    # sampling node (all top plates tied together).
    # Place via stacks at each cap for electrical connectivity.
    # Bottom plate (M5) via stacks at cap bottom edge (overlaps M5 plate).
    # Top plate (TM1) via stacks at cap top edge.
    # Sampling node (top plates) uses M2 bus — safe because the sampling bus
    # at y≈5.25 is well below the SAR bit M2 buses (y≥24).

    for idx, ba in enumerate(bit_areas):
        cx = ba['center'][0]
        # Bottom plate: via stack at bottom edge of M5 plate (merges with M5)
        bot_y = ba['y'] - MIM_ENC_M5
        draw_via_stack_m2_to_m5(top, layout, cx, bot_y)
        # Top plate: via stack at top edge of cap
        top_y = ba['y'] + ba['h'] + 0.1
        draw_via_stack_m2_to_tm1(top, layout, cx, top_y)

    # Common top-plate bus (sampling node) on M2
    if bit_areas:
        sampling_y = bit_areas[0]['y'] + bit_areas[0]['h'] + 0.1
        first_cx = bit_areas[0]['center'][0]
        last_cx = bit_areas[-1]['center'][0]
        top.shapes(li_m2).insert(rect(first_cx - M2_WIDTH/2, sampling_y - M2_WIDTH/2,
                                       first_cx + M2_WIDTH/2, sampling_y + M2_WIDTH/2))

    # =====================================================================
    # Fix 1: TM1 sampling-node strap
    # =====================================================================
    # Connect all cap top plates via TopMetal1 to form the sampling node.
    # Use one continuous TM1 strap per column (≥1.64µm wide) that overlaps
    # all cap TM1 plates, then bridge between columns. This avoids complex
    # per-gap shapes that create TM1.a/TM1.b violations from narrow notches.
    li_tm1 = layout.layer(*L_TOPMETAL1)
    TM1_MIN = 1.64  # µm

    # Group caps by column (column changes when cap_cursor_x advances)
    columns = {}
    for ba in bit_areas:
        col_x = round(ba['x'], 1)  # round to 0.1µm to group by column
        if col_x not in columns:
            columns[col_x] = []
        columns[col_x].append(ba)

    # Draw one continuous TM1 strap per column, wide enough to overlap all
    # cap TM1 plates AND topvia1 TM1 pads (avoids narrow gaps → TM1.b)
    strap_positions = []  # (x1, y1, x2, y2) for bridge routing
    for col_x in sorted(columns.keys()):
        caps = columns[col_x]
        # Find the full horizontal extent of TM1 in this column
        # (cap TM1 plates + topvia1 TM1 pads at cap center ± 0.82µm)
        TM1_ENC = 0.1  # cap TM1 extension beyond Cmim
        TV1_HALF = max(TOPVIA1_ENC_TM1 + TOPVIA1_SIZE / 2, TM1_MIN / 2)  # 0.82µm
        sx1 = col_x - TM1_ENC
        sx2 = col_x - TM1_ENC
        for cap in caps:
            cap_right = cap['x'] + cap['w'] + TM1_ENC
            via_right = cap['x'] + cap['w'] / 2 + TV1_HALF
            sx2 = max(sx2, cap_right, via_right)
        # Ensure min width ≥ TM1_MIN
        if sx2 - sx1 < TM1_MIN:
            sx2 = sx1 + TM1_MIN
        # Strap spans from first cap bottom to last cap top (with TM1 enc)
        first_y = caps[0]['y'] - TM1_ENC
        last_y = caps[-1]['y'] + caps[-1]['h'] + TM1_ENC
        top.shapes(li_tm1).insert(rect(sx1, first_y, sx2, last_y))
        strap_positions.append((sx1, first_y, sx2, last_y))

    # TM1 horizontal bridge connecting all columns at the bottom
    if len(strap_positions) >= 2:
        bridge_y = strap_positions[0][1]  # bottom of first column
        bridge_h = TM1_MIN + 0.2  # 1.84µm
        # Bridge from first column right edge to last column left edge
        bx1 = strap_positions[0][2]   # right edge of first column strap
        bx2 = strap_positions[-1][0]  # left edge of last column strap
        top.shapes(li_tm1).insert(rect(bx1, bridge_y, bx2, bridge_y + bridge_h))

    # =====================================================================
    # Sample switch (NMOS, left edge near vin pin)
    # =====================================================================
    sw_sample = draw_nmos_transistor(top, layout, x=2.0, y=20.0, w=3.0, l=0.13)

    # Connect sample switch drain to sampling node via M1 vertical + via1 at bus
    # Route on M1 to avoid M2 spacing conflicts with cap bottom-plate via pads.
    sw_drain_x, sw_drain_y = sw_sample['drain']
    if bit_areas:
        sampling_y = bit_areas[0]['y'] + bit_areas[0]['h'] + 0.1
        # M1 vertical from sample switch drain down to sampling bus y
        top.shapes(li_m1).insert(rect(sw_drain_x - M1_WIDTH/2, sampling_y,
                                       sw_drain_x + M1_WIDTH/2, sw_drain_y + M1_WIDTH/2))
        # via1 at sampling bus y to jump from M1 to M2
        draw_via1(top, layout, sw_drain_x, sampling_y)

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
    # Near sample switch (x=2, y=20)
    draw_ptap(top, layout, 2.0, 17.0)
    draw_ptap(top, layout, 6.0, 17.0)
    # Along comparator NMOS region (x=27-37, y=19-35)
    # y=22.0 clears SAR logic M1 rail at y=21.34 (M1.b ≥ 0.18µm)
    for xt in [26.0, 30.0, 34.0, 38.0]:
        draw_ptap(top, layout, xt, 22.0)
        draw_ptap(top, layout, xt, 31.0)
    # SAR logic perimeter taps (block at x=27-42, y=4-22)
    # Place outside the dense transistor grid to avoid Activ spacing issues
    for xt in [24.5, 31.0, 36.5, 41.5]:
        draw_ptap(top, layout, xt, 2.5)   # below SAR logic
        draw_ptap(top, layout, xt, 20.5)  # above SAR logic
    # Left/right perimeter of SAR logic
    for yt in [8.0, 14.0, 18.0]:
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
    # Base at 23.0 to avoid M2.b conflict with cap top-plate vias and comp inp route
    # End at 24.0: m3_x_positions max is 23.5, so bus only needs to cover via2 pads
    for bit in range(NBITS):
        bus_y = 23.0 + bit * 1.5
        top.shapes(li_m2).insert(rect(cap_region_x, bus_y - M2_WIDTH / 2,
                                       24.0, bus_y + M2_WIDTH / 2))

    # =====================================================================
    # Fix 2b: Route vin → sample switch source
    # =====================================================================
    # vin pin: M2 at (0, 19.5-20.5), center (0.25, 20.0)
    # sw source: M1 at sw_sample['source']
    sw_src_x, sw_src_y = sw_sample['source']
    vin_pin_y = 20.0
    # Extend M2 from vin pin to x near switch source
    top.shapes(li_m2).insert(rect(0.5, vin_pin_y - M2_WIDTH / 2,
                                   sw_src_x + 0.2, vin_pin_y + M2_WIDTH / 2))
    # via1 at (sw_src_x, vin_pin_y) to drop to M1
    draw_via1(top, layout, sw_src_x, vin_pin_y)
    # M1 vertical from via1 up to switch source
    top.shapes(li_m1).insert(rect(sw_src_x - M1_WIDTH / 2, vin_pin_y,
                                   sw_src_x + M1_WIDTH / 2, sw_src_y))

    # =====================================================================
    # Fix 2c: Route sampling node → comparator inp gate
    # =====================================================================
    # Sampling M2 bus at sampling_y. Comparator inp gate at comp['inp']['gate']
    # inp gate is at top of GatPoly extension: (x + l/2, y + w + GATPOLY_EXT)
    # comp placed at x=27.0, y=25.0; inp NMOS at (27.0, 25.0) w=2.0 l=0.50
    # gate top = (27.0 + 0.32 + 0.25, 25.0 + 2.0 + 0.18) = (27.57, 27.18)
    inp_gate_x = comp['inp']['gate'][0]
    inp_gate_y = comp['inp']['gate'][1]
    samp_y = sampling_y  # M2 sampling bus y-center

    # Route via M3 vertical (M3 is clear between y=2 and y=40)
    m3_x = 25.0  # x for M3 vertical run (offset from bit M3 routes for M3.b)
    # Extend M2 sampling bus rightward to m3_x
    top.shapes(li_m2).insert(rect(first_cx - M2_WIDTH / 2, samp_y - M2_WIDTH / 2,
                                   m3_x + M2_WIDTH / 2, samp_y + M2_WIDTH / 2))
    # via2 at (m3_x, samp_y) → M3
    draw_via2(top, layout, m3_x, samp_y)
    # M3 vertical from samp_y to inp_gate_y
    top.shapes(li_m3).insert(rect(m3_x - M2_WIDTH / 2, samp_y,
                                   m3_x + M2_WIDTH / 2, inp_gate_y + 0.2))
    # via2 at top → M2
    draw_via2(top, layout, m3_x, inp_gate_y)
    # M2 horizontal from m3_x to near inp gate
    top.shapes(li_m2).insert(rect(m3_x - M2_WIDTH / 2, inp_gate_y - M2_WIDTH / 2,
                                   inp_gate_x + 0.2, inp_gate_y + M2_WIDTH / 2))
    # via1 at inp gate x → M1
    draw_via1(top, layout, inp_gate_x, inp_gate_y)
    # Gate contact on GatPoly
    draw_gate_contact(top, layout, inp_gate_x, inp_gate_y)

    # =====================================================================
    # Fix 2d: Route comparator inn → VSS reference
    # =====================================================================
    inn_gate_x = comp['inn']['gate'][0]
    inn_gate_y = comp['inn']['gate'][1]
    # Gate contact at inn gate
    draw_gate_contact(top, layout, inn_gate_x, inn_gate_y)
    draw_via1(top, layout, inn_gate_x, inn_gate_y)
    draw_via2(top, layout, inn_gate_x, inn_gate_y)
    # M3 vertical from inn gate down to VSS rail (y=0-2)
    top.shapes(li_m3).insert(rect(inn_gate_x - M2_WIDTH / 2, 2.0,
                                   inn_gate_x + M2_WIDTH / 2, inn_gate_y))

    # =====================================================================
    # Fix 2e: Route comparator outputs → SAR logic
    # =====================================================================
    outp_x, outp_y = comp['outp']
    outn_x, outn_y = comp['outn']
    sar_top_y = 22.0  # SAR logic top edge
    # Offset M2 verticals right to clear SAR logic M2 straps (left strap at x=27-27.4)
    outp_m2_x = 28.2  # well right of SAR left M2 strap (27.4)
    outn_m2_x = 33.2  # well right of outp
    # outp: via1 at drain → M1 jog to outp_m2_x → via1 → M2 vertical
    draw_via1(top, layout, outp_x, outp_y)
    top.shapes(li_m2).insert(rect(outp_x - M2_WIDTH / 2, outp_y - M2_WIDTH / 2,
                                   outp_m2_x + M2_WIDTH / 2, outp_y + M2_WIDTH / 2))
    top.shapes(li_m2).insert(rect(outp_m2_x - M2_WIDTH / 2, sar_top_y,
                                   outp_m2_x + M2_WIDTH / 2, outp_y))
    # outn: via1 at drain → M2 jog to outn_m2_x → M2 vertical
    draw_via1(top, layout, outn_x, outn_y)
    top.shapes(li_m2).insert(rect(outn_x - M2_WIDTH / 2, outn_y - M2_WIDTH / 2,
                                   outn_m2_x + M2_WIDTH / 2, outn_y + M2_WIDTH / 2))
    top.shapes(li_m2).insert(rect(outn_m2_x - M2_WIDTH / 2, sar_top_y,
                                   outn_m2_x + M2_WIDTH / 2, outn_y))

    # =====================================================================
    # Fix 2f: Route M2 bit buses → cap bottom plates via M3
    # =====================================================================
    # M3 vertical routes at staggered x positions (clear of cap via stacks
    # and clk M3), with via2 at each end and M2 horizontal jog at the
    # bottom to reach each cap's bottom-plate M2 pad.
    m3_x_positions = [5.0, 6.0, 7.0, 8.0, 9.0, 20.0, 21.5, 23.5]  # was [6,6.5,7,7.5,8,20,21,26]; widened for M3.b
    # SAR bits 5 and 7: M3 must stop above clk M3 horizontal at y=3.5
    target_y_override = {5: 4.0, 7: 4.0}

    for sar_bit in range(NBITS):
        ba = bit_areas[sar_bit + 1]  # +1: bit_areas[0] is dummy cap
        cap_cx = ba['center'][0]
        cap_bot_y = ba['y'] - MIM_ENC_M5
        bus_y = 23.0 + sar_bit * 1.5
        m3_x = m3_x_positions[sar_bit]
        tgt_y = target_y_override.get(sar_bit, cap_bot_y)

        # via2 on existing M2 bus → M3
        draw_via2(top, layout, m3_x, bus_y)
        # M3 vertical from bus_y down to target_y
        top.shapes(li_m3).insert(rect(m3_x - M2_WIDTH / 2, tgt_y,
                                       m3_x + M2_WIDTH / 2, bus_y))
        # via2 at bottom of M3 → M2
        draw_via2(top, layout, m3_x, tgt_y)

        if sar_bit in target_y_override:
            # L-shape M2: horizontal at tgt_y, then vertical to cap_bot_y
            x_min = min(m3_x, cap_cx) - M2_WIDTH / 2
            x_max = max(m3_x, cap_cx) + M2_WIDTH / 2
            top.shapes(li_m2).insert(rect(x_min, tgt_y - M2_WIDTH / 2,
                                           x_max, tgt_y + M2_WIDTH / 2))
            top.shapes(li_m2).insert(rect(cap_cx - M2_WIDTH / 2, cap_bot_y - M2_WIDTH / 2,
                                           cap_cx + M2_WIDTH / 2, tgt_y + M2_WIDTH / 2))
        else:
            # Simple M2 horizontal jog from m3_x to cap_cx at cap_bot_y
            x_min = min(m3_x, cap_cx) - M2_WIDTH / 2
            x_max = max(m3_x, cap_cx) + M2_WIDTH / 2
            top.shapes(li_m2).insert(rect(x_min, cap_bot_y - M2_WIDTH / 2,
                                           x_max, cap_bot_y + M2_WIDTH / 2))

    # =====================================================================
    # Fix 2g: Route clk → comparator tail gate (via M3)
    # =====================================================================
    # Route M3 at y=3.5 (below cap top-plate via M3 pads at y≈5.25) to avoid M3.b.
    # Use x=30.0 for the vertical M3 run (away from tail source M3 at x≈28).
    clk_pin_y = 5.0
    tail_gate_x = comp['clk'][0]
    tail_gate_y = comp['clk'][1]
    m3_clk_y = 3.5   # M3 horizontal route y (below cap M3 at ~5.25)
    m3_clk_x = 30.0  # M3 vertical x (offset from tail source M3 at x≈28)
    # via2 at clk pin (0.25, 5.0) → M3
    draw_via2(top, layout, 0.25, clk_pin_y)
    # M3 vertical from via2 at y=5.0 down to y=3.5
    top.shapes(li_m3).insert(rect(0.25 - M2_WIDTH / 2, m3_clk_y,
                                   0.25 + M2_WIDTH / 2, clk_pin_y))
    # M3 horizontal at y=3.5 from x=0.25 to m3_clk_x
    top.shapes(li_m3).insert(rect(0.25 - M2_WIDTH / 2, m3_clk_y - M2_WIDTH / 2,
                                   m3_clk_x + M2_WIDTH / 2, m3_clk_y + M2_WIDTH / 2))
    # M3 vertical from y=3.5 up to tail_gate_y
    top.shapes(li_m3).insert(rect(m3_clk_x - M2_WIDTH / 2, m3_clk_y,
                                   m3_clk_x + M2_WIDTH / 2, tail_gate_y))
    # via2 → M2 → via1 → M1 at tail gate
    draw_via2(top, layout, m3_clk_x, tail_gate_y)
    draw_via1(top, layout, m3_clk_x, tail_gate_y)
    # M1 horizontal from via1 to gate contact
    top.shapes(li_m1).insert(rect(min(m3_clk_x, tail_gate_x) - M1_WIDTH / 2,
                                   tail_gate_y - M1_WIDTH / 2,
                                   max(m3_clk_x, tail_gate_x) + M1_WIDTH / 2,
                                   tail_gate_y + M1_WIDTH / 2))
    draw_gate_contact(top, layout, tail_gate_x, tail_gate_y)

    # =====================================================================
    # Fix 2h: Route rst_n, start → SAR logic boundary
    # =====================================================================
    # Cap via stacks place M2+M3 pads, blocking both M2 and M3 horizontal
    # routes through the cap region. Use M1 underpass (M1 is clear of cap vias).
    m1_bypass_end_x = 24.5  # right of all cap vias, left of sampling M3 at x=25.5

    # rst_n: pin M2 at (0.25, 9.0) → via1 → M1 → via1 → M2 to SAR logic
    draw_via1(top, layout, 0.25, 9.0)
    top.shapes(li_m1).insert(rect(0.25 - M1_WIDTH / 2, 9.0 - M1_WIDTH / 2,
                                   m1_bypass_end_x + M1_WIDTH / 2, 9.0 + M1_WIDTH / 2))
    draw_via1(top, layout, m1_bypass_end_x, 9.0)
    top.shapes(li_m2).insert(rect(m1_bypass_end_x - M2_WIDTH / 2, 9.0 - M2_WIDTH / 2,
                                   27.0, 9.0 + M2_WIDTH / 2))

    # start: pin M2 at (0.25, 13.0) → via1 → M1 → via1 → M2 to SAR logic
    draw_via1(top, layout, 0.25, 13.0)
    top.shapes(li_m1).insert(rect(0.25 - M1_WIDTH / 2, 13.0 - M1_WIDTH / 2,
                                   m1_bypass_end_x + M1_WIDTH / 2, 13.0 + M1_WIDTH / 2))
    draw_via1(top, layout, m1_bypass_end_x, 13.0)
    top.shapes(li_m2).insert(rect(m1_bypass_end_x - M2_WIDTH / 2, 13.0 - M2_WIDTH / 2,
                                   27.0, 13.0 + M2_WIDTH / 2))

    # =====================================================================
    # Fix 2i: Route dout/eoc from SAR logic boundary
    # =====================================================================
    # eoc pin at (41.5-42, 4.5-5.5) — M2 from SAR logic right edge (x=42) to pin
    top.shapes(li_m2).insert(rect(42.0 - 0.5, 5.0 - M2_WIDTH / 2,
                                   MACRO_W, 5.0 + M2_WIDTH / 2))
    # dout[0-7] pins at right edge
    for bit in range(NBITS):
        pin_y = 8.0 + bit * 3.5
        top.shapes(li_m2).insert(rect(42.0 - 0.5, pin_y - M2_WIDTH / 2,
                                       MACRO_W, pin_y + M2_WIDTH / 2))

    # =====================================================================
    # Fix 2j: Comparator power connections
    # =====================================================================
    # PMOS sources → VDD (via1→M2→via2→M3 vertical up to VDD rail)
    for ps_x, ps_y in [comp['p1_source'], comp['p2_source']]:
        draw_via1(top, layout, ps_x, ps_y)
        draw_via2(top, layout, ps_x, ps_y)
        # M3 vertical from source up to VDD rail (y=40-42)
        top.shapes(li_m3).insert(rect(ps_x - M2_WIDTH / 2, ps_y,
                                       ps_x + M2_WIDTH / 2, MACRO_H - 2.0))

    # Tail NMOS source → VSS (via1→M2→via2→M3 vertical down to VSS rail)
    # Offset M3 to x=28.0 to maintain M3.b spacing from clk M3 at x=30.0
    ts_x, ts_y = comp['tail_source']
    ts_m3_x = 28.0  # M3 vertical x, well separated from clk M3 at 30.0
    draw_via1(top, layout, ts_x, ts_y)
    # M2 horizontal jog from ts_x to ts_m3_x
    top.shapes(li_m2).insert(rect(min(ts_x, ts_m3_x) - M2_WIDTH / 2, ts_y - M2_WIDTH / 2,
                                   max(ts_x, ts_m3_x) + M2_WIDTH / 2, ts_y + M2_WIDTH / 2))
    draw_via2(top, layout, ts_m3_x, ts_y)
    top.shapes(li_m3).insert(rect(ts_m3_x - M2_WIDTH / 2, 2.0,
                                   ts_m3_x + M2_WIDTH / 2, ts_y))

    # =====================================================================
    # Fix 2k: SAR logic power (via2 from M2 straps to M3 rails)
    # =====================================================================
    # SAR logic has M2 vertical power straps at left (x=27-27.4) and right (x=39.6-42)
    # Place via2 at top and bottom of each strap to connect to M3 VDD/VSS rails
    sar_x = 27.0
    sar_y = 4.0
    # Left via2s at center of M2 strap (27.3-27.7) so M2 pads are fully interior
    sar_left_via_x = sar_x + 0.5   # 27.5 — center of left M2 strap
    sar_right_via_x = sar_x + SAR_W - 1.0  # 41.0 — center of right M2 strap
    hw = M2_WIDTH / 2

    # Bottom via2s → VSS rail (left via at y=5.0, fully inside strap starting at y=4.5)
    draw_via2(top, layout, sar_left_via_x, 5.0)
    draw_via2(top, layout, sar_right_via_x, sar_y + 0.5)
    # M3 vertical straps from SAR logic bottom to VSS rail
    top.shapes(li_m3).insert(rect(sar_left_via_x - hw, 2.0,
                                   sar_left_via_x + hw, 5.0))
    top.shapes(li_m3).insert(rect(sar_right_via_x - hw, 2.0,
                                   sar_right_via_x + hw, sar_y + 0.5))

    # Top via2s → VDD rail
    draw_via2(top, layout, sar_left_via_x, sar_y + SAR_H - 0.5)
    draw_via2(top, layout, sar_right_via_x, sar_y + SAR_H - 0.5)
    # Left VDD M3 strap: wider (x=27.1 to 27.6) to merge with comp p1 source M3
    # at x≈27.06-27.26 and reach via2 M3 pad at x=27.4-27.6
    top.shapes(li_m3).insert(rect(27.1, sar_y + SAR_H - 0.5,
                                   sar_left_via_x + hw, MACRO_H - 2.0))
    top.shapes(li_m3).insert(rect(sar_right_via_x - hw, sar_y + SAR_H - 0.5,
                                   sar_right_via_x + hw, MACRO_H - 2.0))

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
                  rect(0.0, 20.0 - 0.5, 0.5, 20.0 + 0.5), "vin", layout)

    # Right edge pins
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, 5.0 - 0.5, MACRO_W, 5.0 + 0.5), "eoc", layout)

    for bit in range(NBITS):
        pin_y = 8.0 + bit * 3.5
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
