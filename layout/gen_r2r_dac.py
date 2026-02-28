#!/usr/bin/env python3
"""
Generate 8-bit R-2R DAC layout for IHP SG13G2 130nm.

Architecture:
  Vref (VDD) ─── R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬── Vout
                     │     │     │     │     │     │     │     │
                    2R    2R    2R    2R    2R    2R    2R    2R
                     │     │     │     │     │     │     │     │
                    SW7   SW6   SW5   SW4   SW3   SW2   SW1   SW0
                     ↕     ↕     ↕     ↕     ↕     ↕     ↕     ↕
                  Vdd/Vss (selected by d[n])

Resistors: rhigh (high-ohmic poly, ~1300 Ω/sq) for compact layout.
  R = 2 kΩ → 1.54 squares at W=2µm → L=3.08µm
  2R = 4 kΩ → L=6.15µm
  Series chain of 8 R: ~8 × 4.3µm (with pads) = ~34µm total → fits in 45µm

Switches: sg13_lv_nmos, L=0.13µm, W=2µm

Layout:
  Top row:    series R chain (horizontal, y≈48)
  Middle row: 2R shunt resistors (vertical, dropping from junctions)
  Bottom row: NMOS switches
  Metal2:     d[7:0] input pins (left edge), vout pin (right edge)
  Metal3:     VDD (top), VSS (bottom) power rails

Macro size: 45 × 60 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
RHIGH_SHEET_R = 1300.0  # Ω/sq
R_TARGET  = 2000.0      # Ω per unit R
R_WIDTH   = 2.0         # µm (wide for matching)
R_LENGTH  = R_TARGET / RHIGH_SHEET_R * R_WIDTH  # ~3.08 µm
R2_LENGTH = R_LENGTH * 2  # ~6.15 µm for 2R

NMOS_W    = 2.0         # switch width
NMOS_L    = 0.13        # gate length (min for 1.2V)

NBITS     = 8
MACRO_W   = 45.0
MACRO_H   = 60.0

# Derived: resistor total length (body + contact pads + SalBlock clearance)
PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY  # ~0.30 µm
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
R2_TOTAL  = PAD_W + SAL_SPACE_CONT + R2_LENGTH + SAL_SPACE_CONT + PAD_W
PITCH_X   = R_TOTAL + 0.5  # pitch per bit (series R + gap)

# ===========================================================================
# Layout helpers
# ===========================================================================

def draw_resistor_h(cell, layout, x, y, length, width=R_WIDTH):
    """
    Draw a horizontal rhigh resistor at (x,y).
    Returns (left_contact_center, right_contact_center, total_length).
    """
    li_gp  = layout.layer(*L_GATPOLY)
    li_psd = layout.layer(*L_PSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_l = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    # GatPoly body
    cell.shapes(li_gp).insert(rect(x, y, x + total_l, y + width))

    # pSD implant
    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))

    # SalBlock over resistor body
    sal_x1 = x + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_x2 = x + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                     sal_x2, y + width + SAL_ENC_GATPOLY))

    # Left contact + Metal1
    cx_l = x + pad / 2 - CONT_SIZE / 2
    cy   = y + width / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx_l, cy, cx_l + CONT_SIZE, cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx_l - CONT_ENC_M1, cy - CONT_ENC_M1,
                                    cx_l + CONT_SIZE + CONT_ENC_M1,
                                    cy + CONT_SIZE + CONT_ENC_M1))

    # Right contact + Metal1
    cx_r = x + total_l - pad / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx_r, cy, cx_r + CONT_SIZE, cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx_r - CONT_ENC_M1, cy - CONT_ENC_M1,
                                    cx_r + CONT_SIZE + CONT_ENC_M1,
                                    cy + CONT_SIZE + CONT_ENC_M1))

    lc = (x + pad / 2, y + width / 2)
    rc = (x + total_l - pad / 2, y + width / 2)
    return lc, rc, total_l


def draw_resistor_v(cell, layout, x, y, length, width=R_WIDTH):
    """
    Draw a vertical rhigh resistor at (x,y) — body runs in Y direction.
    Bottom contact at (x, y), top contact at (x, y + total_height).
    Returns (bottom_contact_center, top_contact_center, total_height).
    """
    li_gp  = layout.layer(*L_GATPOLY)
    li_psd = layout.layer(*L_PSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_h = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    # GatPoly body (vertical: width in X, length in Y)
    cell.shapes(li_gp).insert(rect(x, y, x + width, y + total_h))

    # pSD implant
    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + width + enc, y + total_h + enc))

    # SalBlock
    sal_y1 = y + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_y2 = y + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(x - SAL_ENC_GATPOLY, sal_y1,
                                     x + width + SAL_ENC_GATPOLY, sal_y2))

    # Bottom contact + Metal1
    cx = x + width / 2 - CONT_SIZE / 2
    cy_b = y + pad / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx, cy_b, cx + CONT_SIZE, cy_b + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx - CONT_ENC_M1, cy_b - CONT_ENC_M1,
                                    cx + CONT_SIZE + CONT_ENC_M1,
                                    cy_b + CONT_SIZE + CONT_ENC_M1))

    # Top contact + Metal1
    cy_t = y + total_h - pad / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx, cy_t, cx + CONT_SIZE, cy_t + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx - CONT_ENC_M1, cy_t - CONT_ENC_M1,
                                    cx + CONT_SIZE + CONT_ENC_M1,
                                    cy_t + CONT_SIZE + CONT_ENC_M1))

    bc = (x + width / 2, y + pad / 2)
    tc = (x + width / 2, y + total_h - pad / 2)
    return bc, tc, total_h


def draw_nmos(cell, layout, x, y, w=NMOS_W, l=NMOS_L):
    """Draw NMOS transistor. Returns pin centers dict."""
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
        'width':  act_len,
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


# ===========================================================================
# Main: build the R-2R DAC
# ===========================================================================
def build_r2r_dac():
    layout = new_layout()
    top = layout.create_cell("r2r_dac_8bit")

    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)

    layout2 = new_layout()
    top2 = layout2.create_cell("r2r_dac_8bit")
    li_m1  = layout2.layer(*L_METAL1)
    li_m2  = layout2.layer(*L_METAL2)
    li_m3  = layout2.layer(*L_METAL3)
    wire_w = M1_WIDTH  # min width — keeps clearance to NMOS source pad

    # --- Pass 1: compute series chain positions ---
    r_total = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
    r2_total_h = PAD_W + SAL_SPACE_CONT + R2_LENGTH + SAL_SPACE_CONT + PAD_W
    gap = 0.3  # gap between consecutive series R

    chain_width = NBITS * r_total + (NBITS - 1) * gap
    x_start = (MACRO_W - chain_width) / 2  # center the chain

    series_y = 50.0  # Y for series chain

    # --- Pass 2: draw everything ---
    x_cursor = x_start
    vref_contact = None
    vout_contact = None

    for i, bit in enumerate(range(NBITS - 1, -1, -1)):
        # Series R
        r_lc, r_rc, _ = draw_resistor_h(top2, layout2, x=x_cursor, y=series_y,
                                          length=R_LENGTH)
        if i == 0:
            vref_contact = r_lc  # leftmost = Vref
        vout_contact = r_rc  # rightmost = Vout (updated each iteration)

        jx, jy = r_rc

        # 2R shunt (vertical, top aligned just below junction)
        r2_y = jy - r2_total_h - 0.5
        r2_x = jx - R_WIDTH / 2
        r2_bc, r2_tc, _ = draw_resistor_v(top2, layout2, x=r2_x, y=r2_y,
                                           length=R2_LENGTH)

        # M1 wire: junction → 2R top contact
        top2.shapes(li_m1).insert(rect(jx - wire_w / 2, r2_tc[1],
                                        jx + wire_w / 2, jy))

        # NMOS switch below 2R — align drain center with junction x
        sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV  # 0.32 µm
        sw_x = jx - (sd_ext + NMOS_L + sd_ext / 2)  # drain at jx
        sw_y_pos = r2_y - 4.5
        sw = draw_nmos(top2, layout2, x=sw_x, y=sw_y_pos)

        # M1 wire: 2R bottom contact → switch drain
        top2.shapes(li_m1).insert(rect(r2_bc[0] - wire_w / 2, sw['drain'][1],
                                        r2_bc[0] + wire_w / 2, r2_bc[1]))

        # Via1 on gate → Metal2 for d[bit] input
        gv_x = sw['gate'][0]
        gv_y = sw['gate'][1] - 0.5
        draw_via1(top2, layout2, gv_x, gv_y)

        # Metal2 route: left edge pin → gate via
        pin_y = 4.0 + bit * 6.0
        top2.shapes(li_m2).insert(rect(0.0, pin_y - M2_WIDTH,
                                        gv_x + 0.2, pin_y + M2_WIDTH))
        # Vertical jog on M2
        top2.shapes(li_m2).insert(rect(gv_x - M2_WIDTH, min(pin_y, gv_y) - 0.1,
                                        gv_x + M2_WIDTH, max(pin_y, gv_y) + 0.1))

        x_cursor += r_total + gap

    # --- Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS) ---
    # Taps distributed along the switch row (y ≈ 36-40)
    for xt in [3.0, 10.0, 17.0, 24.0, 31.0, 38.0]:
        draw_ptap(top2, layout2, xt, 36.0)

    # --- Vout pin (right edge, Metal2) ---
    vout_via_x = vout_contact[0]
    vout_via_y = vout_contact[1]
    draw_via1(top2, layout2, vout_via_x, vout_via_y)
    vout_pin_y = 30.0
    top2.shapes(li_m2).insert(rect(vout_via_x - 0.1, vout_pin_y - 0.5,
                                    MACRO_W, vout_pin_y + 0.5))
    top2.shapes(li_m2).insert(rect(vout_via_x - M2_WIDTH,
                                    min(vout_via_y, vout_pin_y),
                                    vout_via_x + M2_WIDTH,
                                    max(vout_via_y, vout_pin_y)))

    # --- VDD rail (top, Metal3) ---
    top2.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top2.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # --- Pin labels ---
    for bit in range(NBITS):
        pin_y = 4.0 + bit * 6.0
        add_pin_label(top2, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, pin_y - 0.5, 0.5, pin_y + 0.5),
                      f"d[{bit}]", layout2)

    add_pin_label(top2, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 0.5, MACRO_W, vout_pin_y + 0.5),
                  "vout", layout2)

    add_pin_label(top2, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H), "vdd", layout2)

    add_pin_label(top2, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 2.0), "vss", layout2)

    # --- PR Boundary (IHP SG13G2: layer 189/0) ---
    li_bnd = layout2.layer(189, 0)
    top2.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout2, top2


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "r2r_dac_8bit.gds")

    layout, top = build_r2r_dac()
    layout.write(outpath)

    r_total = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
    chain_w = NBITS * r_total + (NBITS - 1) * 0.3
    print(f"Wrote {outpath}")
    print(f"  R = {R_TARGET:.0f} Ω  (rhigh: W={R_WIDTH} µm, L={R_LENGTH:.2f} µm)")
    print(f"  2R = {R_TARGET*2:.0f} Ω  (L={R2_LENGTH:.2f} µm)")
    print(f"  Series R unit length: {r_total:.2f} µm, chain: {chain_w:.1f} µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
