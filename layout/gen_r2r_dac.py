#!/usr/bin/env python3
"""
Generate 8-bit R-2R DAC layout for IHP SG13G2 130nm.

Architecture:
  Vref (VDD) ─── R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬─ R ─┬── Vout
                     │     │     │     │     │     │     │     │
                    2R    2R    2R    2R    2R    2R    2R    2R
                     │     │     │     │     │     │     │     │
                  ┌──┴──┐  ...                              ┌──┴──┐
                  │ CMOS│                                    │ CMOS│
                  │  SW │                                    │  SW │
                  └──┬──┘                                    └──┬──┘
                  VDD/VSS                                    VDD/VSS

Complementary CMOS switches (NMOS to VSS + PMOS to VDD) per bit.
Compact version: NMOS W=3µm, PMOS W=6µm.

Layout rows (bottom to top):
  VSS rail (Metal3)          0.0 –  1.5
  Pin routing (M2/M3)        2.0 –  7.6
  ptap + VSS bus             8.0 –  9.0
  NMOS switches (W=3µm)      9.5 – 12.5
  Gate contact bridge        12.5 – 13.5
  PMOS switches (W=6µm)      14.0 – 20.0
  ntap + VDD bus (M2)        20.5 – 21.0
  2R lower fold              21.5 – 23.5
  2R upper fold              24.0 – 26.0
  Series R chain             26.5 – 28.5
  VDD rail (Metal3)          28.5 – 30.0

Macro size: 36 × 30 µm
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

NMOS_W    = 3.0         # compact switch (Ron ≈ 160Ω << 2kΩ)
NMOS_L    = 0.13
PMOS_W    = 6.0         # 2× NMOS for Ron matching
PMOS_L    = 0.13

NBITS     = 8
MACRO_W   = 36.0
MACRO_H   = 30.0

# Derived
PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY  # ~0.32 µm
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W
SW_SD_EXT = 0.40

# ===========================================================================
# Layout helpers
# ===========================================================================

def draw_resistor_h(cell, layout, x, y, length, width=R_WIDTH):
    """Draw a horizontal rhigh resistor at (x,y)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_psd = layout.layer(*L_PSD)
    li_nsd = layout.layer(*L_NSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_polyres = layout.layer(*L_POLYRES)
    li_extblk  = layout.layer(*L_EXTBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_l = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    cell.shapes(li_gp).insert(rect(x, y, x + total_l, y + width))

    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))
    cell.shapes(li_nsd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))

    sal_x1 = x + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_x2 = x + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                     sal_x2, y + width + SAL_ENC_GATPOLY))
    cell.shapes(li_polyres).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                         sal_x2, y + width + SAL_ENC_GATPOLY))
    cell.shapes(li_extblk).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
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


def draw_nmos(cell, layout, x, y, w=NMOS_W, l=NMOS_L):
    """Draw NMOS transistor. Returns pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)

    sd_ext = SW_SD_EXT
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))

    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    _draw_contact_column(cell, layout, s_cx, y, w)

    d_cx = gp_x1 + l + (sd_ext - CONT_SIZE) / 2
    _draw_contact_column(cell, layout, d_cx, y, w)

    return {
        'gate':   (gp_x1 + l / 2, y - GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
        'width':  act_len,
    }


def draw_pmos(cell, layout, x, y, w=PMOS_W, l=PMOS_L, draw_nwell=True):
    """Draw PMOS transistor (in NWell). Returns pin centers dict."""
    li_act  = layout.layer(*L_ACTIV)
    li_gp   = layout.layer(*L_GATPOLY)
    li_psd  = layout.layer(*L_PSD)
    li_nw   = layout.layer(*L_NWELL)

    sd_ext = SW_SD_EXT
    act_len = sd_ext + l + sd_ext

    if draw_nwell:
        nw_enc = NWELL_ENC_ACTIV
        cell.shapes(li_nw).insert(rect(x - nw_enc, y - nw_enc,
                                        x + act_len + nw_enc, y + w + nw_enc))

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    cell.shapes(li_psd).insert(rect(x - PSD_ENC_ACTIV, y - PSD_ENC_GATE,
                                     x + act_len + PSD_ENC_ACTIV, y + w + PSD_ENC_GATE))

    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    _draw_contact_column(cell, layout, s_cx, y, w)

    d_cx = gp_x1 + l + (sd_ext - CONT_SIZE) / 2
    _draw_contact_column(cell, layout, d_cx, y, w)

    return {
        'gate':   (gp_x1 + l / 2, y + w + GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
        'width':  act_len,
    }


def _draw_contact_column(cell, layout, cx, y_base, w_total):
    """Draw a column of contacts with one M1 strip along the transistor width."""
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pitch = CONT_SIZE + CONT_SPACE  # 0.34µm
    margin = CONT_ENC_ACTIV  # 0.08µm from active edge
    available = w_total - 2 * margin
    n_contacts = max(1, int(available / pitch))
    array_h = (n_contacts - 1) * pitch + CONT_SIZE
    y_start = y_base + (w_total - array_h) / 2

    for i in range(n_contacts):
        cy = y_start + i * pitch
        cell.shapes(li_cnt).insert(rect(cx, cy, cx + CONT_SIZE, cy + CONT_SIZE))

    y_bot = y_start - CONT_ENC_M1
    y_top = y_start + array_h + CONT_ENC_M1
    cell.shapes(li_m1).insert(rect(cx - CONT_ENC_M1, y_bot,
                                    cx + CONT_SIZE + CONT_ENC_M1, y_top))


def draw_via1(cell, layout, x, y):
    li_v1 = layout.layer(*L_VIA1)
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    hs = VIA1_SIZE / 2
    cell.shapes(li_v1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e1 = max(VIA1_ENC_M1 + hs, 0.15)
    cell.shapes(li_m1).insert(rect(x - e1, y - e1, x + e1, y + e1))
    e2 = VIA1_ENC_M2 + hs
    cell.shapes(li_m2).insert(rect(x - e2, y - e2, x + e2, y + e2))


def draw_via2(cell, layout, x, y):
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
    li_v4 = layout.layer(*L_VIA4)
    li_m4 = layout.layer(*L_METAL4)
    li_m5 = layout.layer(*L_METAL5)
    hs = VIA4_SIZE / 2
    cell.shapes(li_v4).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e4 = VIA4_ENC_M4 + hs
    cell.shapes(li_m4).insert(rect(x - e4, y - e4, x + e4, y + e4))
    e5 = VIA4_ENC_M5 + hs
    cell.shapes(li_m5).insert(rect(x - e5, y - e5, x + e5, y + e5))


def draw_power_via_stack(cell, layout, x, y):
    draw_via3(cell, layout, x, y)
    draw_via4(cell, layout, x, y)


# ===========================================================================
# Main: build the R-2R DAC
# ===========================================================================
def build_r2r_dac():
    layout = new_layout()
    top = layout.create_cell("r2r_dac_8bit")

    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)
    li_nw  = layout.layer(*L_NWELL)
    wire_w = M1_WIDTH

    # --- Y coordinates (compact layout) ---
    sw_y       = 9.5    # NMOS row bottom
    pm_y       = 14.0   # PMOS row bottom
    r2_lower_y = 21.5   # 2R lower fold
    r2_upper_y = 24.0   # 2R upper fold
    series_y   = 26.5   # Series R chain

    # Gate contact Y: in the NMOS-PMOS bridge gap
    gc_y = (sw_y + NMOS_W + GATPOLY_EXT + pm_y - GATPOLY_EXT) / 2  # ~13.0

    # --- X layout ---
    gap = 0.18
    chain_width = NBITS * R_TOTAL + (NBITS - 1) * gap
    x_start = (MACRO_W - chain_width) / 2

    vss_bus_y = sw_y - 0.5   # 9.0
    vdd_bus_y = pm_y + PMOS_W + 0.5  # 20.5

    x_cursor = x_start
    vref_contact = None
    vout_contact = None
    prev_rc = None
    nmos_source_strips = []
    pmos_source_strips = []
    pmos_devices = []

    sd_ext = SW_SD_EXT

    for i, bit in enumerate(range(NBITS)):
        # Series R
        r_lc, r_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=series_y,
                                          length=R_LENGTH)
        if i == 0:
            vref_contact = r_lc
        vout_contact = r_rc

        if prev_rc is not None:
            bridge_y = series_y + R_WIDTH / 2
            top.shapes(li_m1).insert(rect(prev_rc[0] - wire_w / 2, bridge_y - wire_w / 2,
                                            r_lc[0] + wire_w / 2, bridge_y + wire_w / 2))
        prev_rc = r_rc

        jx, jy = r_rc

        # Folded 2R
        r2u_lc, r2u_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_upper_y,
                                               length=R_LENGTH)
        r2l_lc, r2l_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_lower_y,
                                               length=R_LENGTH)

        # Junction → 2R upper right
        top.shapes(li_m1).insert(rect(jx - wire_w / 2, r2u_rc[1],
                                        jx + wire_w / 2, jy))

        # Hairpin: upper left → lower left
        hp_x = r2u_lc[0]
        top.shapes(li_m1).insert(rect(hp_x - wire_w / 2, r2l_lc[1],
                                        hp_x + wire_w / 2, r2u_lc[1]))

        drain_target_x = r2l_rc[0]

        # NMOS switch
        n_sw_x = drain_target_x - (sd_ext + NMOS_L + sd_ext / 2)
        nmos = draw_nmos(top, layout, x=n_sw_x, y=sw_y)

        s_cx_n = n_sw_x + sd_ext / 2 - CONT_SIZE / 2
        nmos_source_strips.append((s_cx_n - CONT_ENC_M1,
                                    s_cx_n + CONT_SIZE + CONT_ENC_M1))

        # PMOS switch
        p_sw_x = drain_target_x - (sd_ext + PMOS_L + sd_ext / 2)
        pmos = draw_pmos(top, layout, x=p_sw_x, y=pm_y, draw_nwell=False)
        pmos_devices.append((p_sw_x, pm_y))

        s_cx_p = p_sw_x + sd_ext / 2 - CONT_SIZE / 2
        pmos_source_strips.append((s_cx_p - CONT_ENC_M1,
                                    s_cx_p + CONT_SIZE + CONT_ENC_M1))

        # M1: 2R lower right → PMOS drain → NMOS drain
        drain_w = CONT_SIZE + 2 * CONT_ENC_M1
        top.shapes(li_m1).insert(rect(drain_target_x - drain_w / 2, nmos['drain'][1],
                                        drain_target_x + drain_w / 2, r2l_rc[1]))

        # Gate connection: GatPoly bridge between NMOS and PMOS
        gate_x = nmos['gate'][0]
        nmos_poly_top = sw_y + NMOS_W + GATPOLY_EXT
        pmos_poly_bot = pm_y - GATPOLY_EXT
        gp_hw = PMOS_L / 2
        top.shapes(li_gp).insert(rect(gate_x - gp_hw, nmos_poly_top,
                                        gate_x + gp_hw, pmos_poly_bot))

        # Gate contact shifted LEFT to avoid drain M1 overlap
        gc_x = gate_x - 0.40

        gc_half_gp = CONT_SIZE / 2 + CONT_ENC_GATPOLY
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gp_hw,
                                        gate_x + gp_hw, gc_y + gp_hw))
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gc_half_gp,
                                        gc_x + gc_half_gp, gc_y + gc_half_gp))

        gc_hs = CONT_SIZE / 2
        top.shapes(li_cnt).insert(rect(gc_x - gc_hs, gc_y - gc_hs,
                                        gc_x + gc_hs, gc_y + gc_hs))
        gc_half_m1 = CONT_SIZE / 2 + CONT_ENC_M1
        top.shapes(li_m1).insert(rect(gc_x - gc_half_m1, gc_y - gc_half_m1,
                                        gc_x + gc_half_m1, gc_y + gc_half_m1))

        draw_via1(top, layout, gc_x, gc_y)

        # Pin routing: left edge M2 → M3 → M2 vertical to gate
        pin_y = 2.0 + bit * 0.8
        hw = M2_WIDTH / 2

        top.shapes(li_m2).insert(rect(0.0, pin_y - hw, 1.5, pin_y + hw))
        draw_via2(top, layout, 1.5, pin_y)
        top.shapes(li_m3).insert(rect(1.5, pin_y - hw, gc_x, pin_y + hw))
        draw_via2(top, layout, gc_x, pin_y)
        top.shapes(li_m2).insert(rect(gc_x - hw, min(pin_y, gc_y) - 0.1,
                                        gc_x + hw, max(pin_y, gc_y) + 0.1))

        x_cursor += R_TOTAL + gap

    # NWell strip for all PMOS
    nw_enc = NWELL_ENC_ACTIV
    if pmos_devices:
        nw_x1 = pmos_devices[0][0] - nw_enc
        nw_x2 = pmos_devices[-1][0] + (sd_ext + PMOS_L + sd_ext) + nw_enc
        nw_y1 = pm_y - nw_enc
        nw_y2 = pm_y + PMOS_W + nw_enc
        top.shapes(li_nw).insert(rect(nw_x1, nw_y1, nw_x2, nw_y2))

    # NMOS sources → VSS bus
    top.shapes(li_m1).insert(rect(1.0, vss_bus_y - wire_w / 2,
                                    35.0, vss_bus_y + wire_w / 2))
    for x_l, x_r in nmos_source_strips:
        top.shapes(li_m1).insert(rect(x_l, vss_bus_y, x_r, sw_y + 0.5))

    # VSS bus → VSS rail
    vss_via_x = 2.5
    top.shapes(li_m1).insert(rect(1.0, vss_bus_y - wire_w / 2,
                                    vss_via_x + wire_w / 2, vss_bus_y + wire_w / 2))
    draw_via1(top, layout, vss_via_x, vss_bus_y)
    draw_via2(top, layout, vss_via_x, vss_bus_y)
    top.shapes(li_m3).insert(rect(0.5 - hw, vss_bus_y - hw,
                                    vss_via_x + hw, vss_bus_y + hw))
    top.shapes(li_m3).insert(rect(0.5 - hw, 0.75, 0.5 + hw, vss_bus_y))

    # Substrate taps (ptap for PWell near NMOS)
    ptap_y = sw_y - 1.0
    for xt in [3.0, 9.0, 15.0, 21.0, 27.0, 33.0]:
        draw_ptap(top, layout, xt, ptap_y)
        ptap_cx = xt + 0.18
        ptap_cy = ptap_y + 0.18
        top.shapes(li_m1).insert(rect(ptap_cx - wire_w / 2, ptap_cy,
                                       ptap_cx + wire_w / 2, vss_bus_y))

    # PMOS sources → VDD via M2 bus
    vdd_bus_m2_y = vdd_bus_y
    for x_l, x_r in pmos_source_strips:
        src_cx = (x_l + x_r) / 2
        top.shapes(li_m1).insert(rect(x_l, pm_y + PMOS_W - 0.5, x_r, vdd_bus_m2_y))
        draw_via1(top, layout, src_cx, vdd_bus_m2_y)

    m2_hw = M2_WIDTH / 2
    top.shapes(li_m2).insert(rect(2.0, vdd_bus_m2_y - m2_hw,
                                    35.0, vdd_bus_m2_y + m2_hw))

    vdd_via2_x = 2.5
    draw_via2(top, layout, vdd_via2_x, vdd_bus_m2_y)
    top.shapes(li_m3).insert(rect(vdd_via2_x - hw, vdd_bus_m2_y,
                                    vdd_via2_x + hw, MACRO_H - 0.75))

    # NWell taps
    if pmos_devices:
        ntap_y = pm_y + PMOS_W + 0.3
        for ntx in [7.0, 15.5, 24.0, 32.0]:
            draw_ntap(top, layout, ntx, ntap_y, w=0.36, h=0.36)
            ntap_cx = ntx + 0.18
            ntap_cy = ntap_y + 0.18
            top.shapes(li_m1).insert(rect(ntap_cx - wire_w / 2, ntap_cy,
                                           ntap_cx + wire_w / 2, vdd_bus_m2_y))
            draw_via1(top, layout, ntap_cx, vdd_bus_m2_y)

    # Vout pin (right edge)
    vout_via_x = vout_contact[0]
    vout_via_y = vout_contact[1]
    vout_pin_y = 15.0
    hw = M2_WIDTH / 2

    draw_via1(top, layout, vout_via_x, vout_via_y)
    draw_via2(top, layout, vout_via_x, vout_via_y)

    top.shapes(li_m3).insert(rect(vout_via_x - hw, vout_pin_y - hw,
                                    vout_via_x + hw, vout_via_y))

    vout_via2_x = MACRO_W - 0.3
    top.shapes(li_m3).insert(rect(vout_via_x - hw, vout_pin_y - hw,
                                    vout_via2_x, vout_pin_y + hw))

    draw_via2(top, layout, vout_via2_x, vout_pin_y)
    top.shapes(li_m2).insert(rect(vout_via2_x - hw, vout_pin_y - 0.5,
                                    MACRO_W, vout_pin_y + 0.5))

    # VDD rail (top, Metal3)
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H))

    # VSS rail (bottom, Metal3)
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 1.5))

    # Vref → VDD rail
    vref_x = vref_contact[0]
    vref_y = vref_contact[1]
    vdd_tap_y = MACRO_H - 0.75
    top.shapes(li_m1).insert(rect(vref_x - wire_w / 2, vref_y,
                                    vref_x + wire_w / 2, vdd_tap_y))
    draw_via1(top, layout, vref_x, vdd_tap_y)
    draw_via2(top, layout, vref_x, vdd_tap_y)

    # Power via stacks
    vdd_rail_y = MACRO_H - 0.75
    vss_rail_y = 0.75
    for px in [x * 2.0 + 1.0 for x in range(int(MACRO_W / 2))]:
        if px < MACRO_W - 0.5:
            draw_power_via_stack(top, layout, px, vdd_rail_y)
            draw_power_via_stack(top, layout, px, vss_rail_y)

    # Pin labels
    for bit in range(NBITS):
        pin_y = 2.0 + bit * 0.8
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, pin_y - 0.35, 0.5, pin_y + 0.35),
                      f"d{bit}", layout)

    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 0.5, MACRO_W, vout_pin_y + 0.5),
                  "vout", layout)

    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H), "vdd", layout)

    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 1.5), "vss", layout)

    # PR Boundary
    li_bnd = layout.layer(189, 0)
    top.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout, top


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "r2r_dac_8bit.gds")

    layout, top = build_r2r_dac()
    layout.write(outpath)

    chain_w = NBITS * R_TOTAL + (NBITS - 1) * 0.18
    print(f"Wrote {outpath}")
    print(f"  R = {R_TARGET:.0f} Ω  (rhigh: W={R_WIDTH} µm, L={R_LENGTH:.2f} µm)")
    print(f"  2R = {R_TARGET*2:.0f} Ω  (folded: 2× R={R_LENGTH:.2f} µm in series)")
    print(f"  Switches: NMOS W={NMOS_W}µm + PMOS W={PMOS_W}µm, L={NMOS_L}µm")
    print(f"  Series R unit length: {R_TOTAL:.2f} µm, chain: {chain_w:.1f} µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
