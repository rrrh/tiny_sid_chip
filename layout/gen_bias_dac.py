#!/usr/bin/env python3
"""
Generate dual-channel 4-bit R-2R bias DAC layout for IHP SG13G2 130nm.

Architecture:
  Two independent 4-bit R-2R ladders stacked vertically sharing VDD/VSS rails.
  Channel 1 (fc): d_fc[3:0] → vout_fc (bias voltage for SVF integrator OTAs)
  Channel 2 (q):  d_q[3:0]  → vout_q  (bias voltage for SVF damping OTA)

Resistors: rhigh (~1300 Ω/sq), R=2kΩ, 2R=4kΩ — same as 8-bit DAC.
Switches: sg13_lv_nmos, L=0.13µm, W=2µm

Macro size: 35 × 40 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters (same resistor values as gen_r2r_dac.py)
# ===========================================================================
RHIGH_SHEET_R = 1300.0
R_TARGET  = 2000.0
R_WIDTH   = 2.0
R_LENGTH  = R_TARGET / RHIGH_SHEET_R * R_WIDTH   # ~3.08 µm
R2_LENGTH = R_LENGTH * 2                          # ~6.15 µm

NMOS_W    = 2.0
NMOS_L    = 0.13

NBITS     = 4
MACRO_W   = 35.0
MACRO_H   = 40.0

PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
R2_TOTAL  = PAD_W + SAL_SPACE_CONT + R2_LENGTH + SAL_SPACE_CONT + PAD_W


# ===========================================================================
# Layout helpers (copied from gen_r2r_dac.py)
# ===========================================================================

def draw_resistor_h(cell, layout, x, y, length, width=R_WIDTH):
    """Draw a horizontal rhigh resistor. Returns (left_contact, right_contact, total_len)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_psd = layout.layer(*L_PSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_l = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    cell.shapes(li_gp).insert(rect(x, y, x + total_l, y + width))
    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))

    sal_x1 = x + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_x2 = x + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                     sal_x2, y + width + SAL_ENC_GATPOLY))

    cx_l = x + pad / 2 - CONT_SIZE / 2
    cy   = y + width / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx_l, cy, cx_l + CONT_SIZE, cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx_l - CONT_ENC_M1, cy - CONT_ENC_M1,
                                    cx_l + CONT_SIZE + CONT_ENC_M1,
                                    cy + CONT_SIZE + CONT_ENC_M1))

    cx_r = x + total_l - pad / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx_r, cy, cx_r + CONT_SIZE, cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx_r - CONT_ENC_M1, cy - CONT_ENC_M1,
                                    cx_r + CONT_SIZE + CONT_ENC_M1,
                                    cy + CONT_SIZE + CONT_ENC_M1))

    lc = (x + pad / 2, y + width / 2)
    rc = (x + total_l - pad / 2, y + width / 2)
    return lc, rc, total_l


def draw_resistor_v(cell, layout, x, y, length, width=R_WIDTH):
    """Draw a vertical rhigh resistor. Returns (bottom_contact, top_contact, total_h)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_psd = layout.layer(*L_PSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_h = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    cell.shapes(li_gp).insert(rect(x, y, x + width, y + total_h))
    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + width + enc, y + total_h + enc))

    sal_y1 = y + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_y2 = y + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(x - SAL_ENC_GATPOLY, sal_y1,
                                     x + width + SAL_ENC_GATPOLY, sal_y2))

    cx = x + width / 2 - CONT_SIZE / 2
    cy_b = y + pad / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cx, cy_b, cx + CONT_SIZE, cy_b + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cx - CONT_ENC_M1, cy_b - CONT_ENC_M1,
                                    cx + CONT_SIZE + CONT_ENC_M1,
                                    cy_b + CONT_SIZE + CONT_ENC_M1))

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


# ===========================================================================
# Build a single 4-bit R-2R channel
# ===========================================================================

def build_channel(cell, layout, x_start, series_y, pin_base_y, pin_prefix, nbits=4):
    """
    Build one 4-bit R-2R ladder channel.

    Args:
        x_start:    X origin for the series chain
        series_y:   Y position of the series resistor chain
        pin_base_y: Base Y for digital input pins (stacked at 4µm pitch)
        pin_prefix: Pin name prefix ('d_fc' or 'd_q')
        nbits:      Number of bits (4)

    Returns:
        vout_contact: (x, y) of the rightmost series chain junction (analog output)
        pin_rects:    list of (name, rect) for pin labels
    """
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    wire_w = M1_WIDTH

    r_total = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
    r2_total_h = PAD_W + SAL_SPACE_CONT + R2_LENGTH + SAL_SPACE_CONT + PAD_W
    gap = 0.3

    x_cursor = x_start
    vout_contact = None
    pin_rects = []

    for i, bit in enumerate(range(nbits - 1, -1, -1)):
        # Series R
        r_lc, r_rc, _ = draw_resistor_h(cell, layout, x=x_cursor, y=series_y,
                                          length=R_LENGTH)
        vout_contact = r_rc

        jx, jy = r_rc

        # 2R shunt (vertical, below junction)
        r2_y = jy - r2_total_h - 0.5
        r2_x = jx - R_WIDTH / 2
        r2_bc, r2_tc, _ = draw_resistor_v(cell, layout, x=r2_x, y=r2_y,
                                           length=R2_LENGTH)

        # M1: junction → 2R top contact
        cell.shapes(li_m1).insert(rect(jx - wire_w / 2, r2_tc[1],
                                        jx + wire_w / 2, jy))

        # NMOS switch below 2R
        sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
        sw_x = jx - (sd_ext + NMOS_L + sd_ext / 2)
        sw_y_pos = r2_y - 4.5
        sw = draw_nmos(cell, layout, x=sw_x, y=sw_y_pos)

        # M1: 2R bottom → switch drain
        cell.shapes(li_m1).insert(rect(r2_bc[0] - wire_w / 2, sw['drain'][1],
                                        r2_bc[0] + wire_w / 2, r2_bc[1]))

        # Via1 on gate → Metal2 for digital input
        gv_x = sw['gate'][0]
        gv_y = sw['gate'][1] - 0.5
        draw_via1(cell, layout, gv_x, gv_y)

        # Metal2 route: left edge pin → gate via
        pin_y = pin_base_y + bit * 3.5
        cell.shapes(li_m2).insert(rect(0.0, pin_y - M2_WIDTH,
                                        gv_x + 0.2, pin_y + M2_WIDTH))
        # Vertical jog on M2
        cell.shapes(li_m2).insert(rect(gv_x - M2_WIDTH, min(pin_y, gv_y) - 0.1,
                                        gv_x + M2_WIDTH, max(pin_y, gv_y) + 0.1))

        # Pin label info
        pin_rects.append((f"{pin_prefix}[{bit}]",
                          rect(0.0, pin_y - 0.5, 0.5, pin_y + 0.5)))

        x_cursor += r_total + gap

    return vout_contact, pin_rects


# ===========================================================================
# Main: build the dual-channel bias DAC
# ===========================================================================

def build_bias_dac():
    layout = new_layout()
    top = layout.create_cell("bias_dac_2ch")

    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    li_m3 = layout.layer(*L_METAL3)

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # Channel layout (two 4-bit ladders stacked):
    #   y=38..40  : VDD rail
    #   y=28..32  : fc channel (series R at y≈30, shunts + switches below)
    #   y=8..12   : q channel (series R at y≈10, shunts + switches below)
    #   y=0..2    : VSS rail
    # =====================================================================

    # fc channel (upper) — series chain at y=30
    fc_series_y = 30.0
    fc_x_start = 3.0
    fc_vout, fc_pins = build_channel(top, layout,
                                      x_start=fc_x_start,
                                      series_y=fc_series_y,
                                      pin_base_y=24.0,
                                      pin_prefix="d_fc",
                                      nbits=NBITS)

    # q channel (lower) — series chain at y=12
    q_series_y = 12.0
    q_x_start = 3.0
    q_vout, q_pins = build_channel(top, layout,
                                    x_start=q_x_start,
                                    series_y=q_series_y,
                                    pin_base_y=4.0,
                                    pin_prefix="d_q",
                                    nbits=NBITS)

    # =====================================================================
    # Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS)
    # =====================================================================
    # fc channel switches (y ≈ 18)
    for xt in [5.0, 12.0, 19.0, 26.0]:
        draw_ptap(top, layout, xt, 16.0)
    # q channel switches (y ≈ 2, near VSS rail)
    for xt in [5.0, 12.0, 19.0, 26.0]:
        draw_ptap(top, layout, xt, 2.5)

    # =====================================================================
    # Vout pins (right edge, Metal2)
    # =====================================================================

    # vout_fc
    vout_fc_via_x = fc_vout[0]
    vout_fc_via_y = fc_vout[1]
    draw_via1(top, layout, vout_fc_via_x, vout_fc_via_y)
    vout_fc_pin_y = 30.0
    top.shapes(li_m2).insert(rect(vout_fc_via_x - 0.1, vout_fc_pin_y - 0.5,
                                   MACRO_W, vout_fc_pin_y + 0.5))
    top.shapes(li_m2).insert(rect(vout_fc_via_x - M2_WIDTH,
                                   min(vout_fc_via_y, vout_fc_pin_y),
                                   vout_fc_via_x + M2_WIDTH,
                                   max(vout_fc_via_y, vout_fc_pin_y)))

    # vout_q
    vout_q_via_x = q_vout[0]
    vout_q_via_y = q_vout[1]
    draw_via1(top, layout, vout_q_via_x, vout_q_via_y)
    vout_q_pin_y = 12.0
    top.shapes(li_m2).insert(rect(vout_q_via_x - 0.1, vout_q_pin_y - 0.5,
                                   MACRO_W, vout_q_pin_y + 0.5))
    top.shapes(li_m2).insert(rect(vout_q_via_x - M2_WIDTH,
                                   min(vout_q_via_y, vout_q_pin_y),
                                   vout_q_via_x + M2_WIDTH,
                                   max(vout_q_via_y, vout_q_pin_y)))

    # =====================================================================
    # Pin labels
    # =====================================================================
    for name, r in fc_pins:
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL, r, name, layout)

    for name, r in q_pins:
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL, r, name, layout)

    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_fc_pin_y - 0.5, MACRO_W, vout_fc_pin_y + 0.5),
                  "vout_fc", layout)

    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_q_pin_y - 0.5, MACRO_W, vout_q_pin_y + 0.5),
                  "vout_q", layout)

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
    outpath = os.path.join(outdir, "bias_dac_2ch.gds")

    layout, top = build_bias_dac()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  Channels: 2 × {NBITS}-bit R-2R")
    print(f"  R = {R_TARGET:.0f} Ω  (rhigh: W={R_WIDTH} µm, L={R_LENGTH:.2f} µm)")
    print(f"  2R = {R_TARGET*2:.0f} Ω  (L={R2_LENGTH:.2f} µm)")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
