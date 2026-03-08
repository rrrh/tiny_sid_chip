#!/usr/bin/env python3
"""
Generate bias_gen layout: dual R-2R DAC for SVF bias currents.
  - 11-bit R-2R for ibias_fc (filter cutoff frequency)
  - 4-bit R-2R for ibias_q (filter Q/resonance)
  - NMOS-only switches (W=2µm) — no PMOS needed for bias DAC
  - rhigh resistors: W=2µm, L=3.08µm → R=2kΩ

Layout (bottom to top):
  VSS rail (M3)          0.0 – 1.5
  Pin routing (M2/M3)    2.0 – 9.0
  ptap row               9.5
  NMOS switches (W=2)    10.5 – 12.5
  2R lower fold          13.5 – 15.5
  2R upper fold          16.5 – 18.5
  Series R chain         19.5 – 21.5
  VDD rail (M3)          22.5 – 24.0

Macro size: 75 × 24 µm

X layout: [11-bit fc section | gap | 4-bit q section]
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
RHIGH_SHEET_R = 1300.0
R_TARGET  = 2000.0
R_WIDTH   = 2.0
R_LENGTH  = R_TARGET / RHIGH_SHEET_R * R_WIDTH  # ~3.08 µm

NMOS_W    = 2.0   # small switches — bias DAC, not signal
NMOS_L    = 0.13

FC_BITS   = 11
Q_BITS    = 4
TOTAL_BITS = FC_BITS + Q_BITS  # 15

MACRO_W   = 75.0
MACRO_H   = 24.0

# Derived
PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY  # 0.32 µm
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W  # ~4.12 µm
SW_SD_EXT = 0.40

# ===========================================================================
# Layout helpers (reuse from gen_r2r_dac.py patterns)
# ===========================================================================

def draw_resistor_h(cell, layout, x, y, length, width=R_WIDTH):
    """Draw a horizontal rhigh resistor at (x,y). Returns contact centers."""
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
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = SW_SD_EXT
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    # Source contact (single for W=2µm)
    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    s_cy = y + w / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(s_cx, s_cy, s_cx + CONT_SIZE, s_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(s_cx - CONT_ENC_M1, s_cy - CONT_ENC_M1,
                                    s_cx + CONT_SIZE + CONT_ENC_M1,
                                    s_cy + CONT_SIZE + CONT_ENC_M1))

    # Drain contact (single for W=2µm)
    d_cx = gp_x1 + l + (sd_ext - CONT_SIZE) / 2
    d_cy = y + w / 2 - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(d_cx, d_cy, d_cx + CONT_SIZE, d_cy + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(d_cx - CONT_ENC_M1, d_cy - CONT_ENC_M1,
                                    d_cx + CONT_SIZE + CONT_ENC_M1,
                                    d_cy + CONT_SIZE + CONT_ENC_M1))

    return {
        'gate':   (gp_x1 + l / 2, y - GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
        'width':  act_len,
    }


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
# Build one R-2R section (N bits)
# ===========================================================================
def build_r2r_section(top, layout, x_start, nbits, pin_prefix,
                      sw_y, r2_lower_y, r2_upper_y, series_y,
                      vss_bus_y, vdd_rail_y, pin_y_start, pin_y_step):
    """Build an N-bit R-2R DAC section starting at x_start.
    Returns (vref_contact, vout_contact, x_end, pin_info_list).
    """
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)
    wire_w = M1_WIDTH
    hw = M2_WIDTH / 2
    sd_ext = SW_SD_EXT

    gap = 0.18
    x_cursor = x_start
    vref_contact = None
    vout_contact = None
    prev_rc = None
    nmos_sources = []
    pin_info = []

    for i in range(nbits):
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

        # Drain target = 2R lower right contact
        drain_target_x = r2l_rc[0]

        # NMOS switch
        n_sw_x = drain_target_x - (sd_ext + NMOS_L + sd_ext / 2)
        nmos = draw_nmos(top, layout, x=n_sw_x, y=sw_y)

        # Track source for VSS bus
        s_cx = n_sw_x + sd_ext / 2 - CONT_SIZE / 2
        nmos_sources.append((s_cx - CONT_ENC_M1, s_cx + CONT_SIZE + CONT_ENC_M1,
                             n_sw_x + sd_ext / 2))

        # M1: 2R lower right → NMOS drain (vertical)
        drain_w = CONT_SIZE + 2 * CONT_ENC_M1
        top.shapes(li_m1).insert(rect(drain_target_x - drain_w / 2, nmos['drain'][1],
                                        drain_target_x + drain_w / 2, r2l_rc[1]))

        # Gate contact — shifted left to avoid drain M1 overlap
        gate_x = nmos['gate'][0]
        gc_x = gate_x - 0.35  # smaller shift for W=2µm NMOS
        gc_y = sw_y - GATPOLY_EXT - 0.3  # below NMOS

        gc_half_gp = CONT_SIZE / 2 + CONT_ENC_GATPOLY
        # GatPoly extension from gate to contact
        gp_hw = NMOS_L / 2
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gp_hw,
                                        gate_x + gp_hw, gc_y + gp_hw))
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gc_half_gp,
                                        gc_x + gc_half_gp, gc_y + gc_half_gp))
        # Vertical GatPoly from gate down to contact Y
        top.shapes(li_gp).insert(rect(gate_x - gp_hw, gc_y - gp_hw,
                                        gate_x + gp_hw, sw_y - GATPOLY_EXT))

        gc_hs = CONT_SIZE / 2
        top.shapes(li_cnt).insert(rect(gc_x - gc_hs, gc_y - gc_hs,
                                        gc_x + gc_hs, gc_y + gc_hs))
        gc_half_m1 = CONT_SIZE / 2 + CONT_ENC_M1
        top.shapes(li_m1).insert(rect(gc_x - gc_half_m1, gc_y - gc_half_m1,
                                        gc_x + gc_half_m1, gc_y + gc_half_m1))

        # Via1 at gate contact → M2
        draw_via1(top, layout, gc_x, gc_y)

        # Pin routing: M2 pin on left edge → M3 → M2 vertical to gate
        pin_y = pin_y_start + i * pin_y_step
        pin_name = f"{pin_prefix}{i}"

        # M2 pin stub
        top.shapes(li_m2).insert(rect(0.0, pin_y - hw, 1.5, pin_y + hw))

        # Via2 at (1.5, pin_y)
        draw_via2(top, layout, 1.5, pin_y)

        # M3 horizontal to gate contact X
        top.shapes(li_m3).insert(rect(1.5, pin_y - hw, gc_x, pin_y + hw))

        # Via2 at (gc_x, pin_y)
        draw_via2(top, layout, gc_x, pin_y)

        # M2 vertical from pin_y to gc_y
        top.shapes(li_m2).insert(rect(gc_x - hw, min(pin_y, gc_y) - 0.1,
                                        gc_x + hw, max(pin_y, gc_y) + 0.1))

        pin_info.append((pin_name, pin_y))
        x_cursor += R_TOTAL + gap

    # NMOS sources → VSS bus (M1 extensions)
    for x_l, x_r, src_cx in nmos_sources:
        top.shapes(li_m1).insert(rect(x_l, vss_bus_y, x_r, sw_y + 0.5))

    # VSS M1 bus
    bus_x1 = x_start
    bus_x2 = x_cursor - gap
    top.shapes(li_m1).insert(rect(bus_x1, vss_bus_y - wire_w / 2,
                                    bus_x2, vss_bus_y + wire_w / 2))

    # Ptaps near NMOS
    ptap_y = sw_y - 1.0
    ptap_step = max(4.0, (bus_x2 - bus_x1) / max(nbits // 2, 1))
    ptx = bus_x1 + 1.0
    while ptx < bus_x2 - 0.5:
        draw_ptap(top, layout, ptx, ptap_y)
        ptap_cx = ptx + 0.18
        ptap_cy = ptap_y + 0.18
        top.shapes(li_m1).insert(rect(ptap_cx - wire_w / 2, ptap_cy,
                                       ptap_cx + wire_w / 2, vss_bus_y))
        ptx += ptap_step

    x_end = x_cursor - gap + R_TOTAL  # last bit end
    return vref_contact, vout_contact, x_end, pin_info


# ===========================================================================
# Main: build the bias_gen
# ===========================================================================
def build_bias_gen():
    layout = new_layout()
    top = layout.create_cell("bias_gen")

    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)
    wire_w = M1_WIDTH
    hw = M2_WIDTH / 2

    # Y coordinates
    sw_y       = 10.5
    r2_lower_y = 13.5
    r2_upper_y = 16.5
    series_y   = 19.5
    vss_bus_y  = 10.0

    gap = 0.18

    # --- 11-bit FC section ---
    fc_x_start = 2.0
    fc_vref, fc_vout, fc_x_end, fc_pins = build_r2r_section(
        top, layout, fc_x_start, FC_BITS, "fc",
        sw_y, r2_lower_y, r2_upper_y, series_y,
        vss_bus_y, MACRO_H - 0.75,
        pin_y_start=2.0, pin_y_step=0.60)

    # --- 4-bit Q section (after FC, with 2µm gap) ---
    # Q pins use Y positions above FC pins to avoid overlap
    q_x_start = fc_x_end + 2.0
    q_vref, q_vout, q_x_end, q_pins = build_r2r_section(
        top, layout, q_x_start, Q_BITS, "q",
        sw_y, r2_lower_y, r2_upper_y, series_y,
        vss_bus_y, MACRO_H - 0.75,
        pin_y_start=8.5, pin_y_step=0.50)

    # --- Vref connections (series chain left end → VDD rail) ---
    vdd_rail_y = MACRO_H - 0.75
    for vref in [fc_vref, q_vref]:
        vref_x, vref_y = vref
        top.shapes(li_m1).insert(rect(vref_x - wire_w / 2, vref_y,
                                        vref_x + wire_w / 2, vdd_rail_y))
        draw_via1(top, layout, vref_x, vdd_rail_y)
        draw_via2(top, layout, vref_x, vdd_rail_y)

    # --- Analog output pins (right side of each section) ---
    # ibias_fc: from FC vout, route to right edge via M2
    fc_vout_x, fc_vout_y = fc_vout
    ibias_fc_pin_y = 14.0
    draw_via1(top, layout, fc_vout_x, fc_vout_y)
    draw_via2(top, layout, fc_vout_x, fc_vout_y)
    # M3 vertical down to pin Y
    top.shapes(li_m3).insert(rect(fc_vout_x - hw, ibias_fc_pin_y - hw,
                                    fc_vout_x + hw, fc_vout_y))
    # M3 horizontal to right edge of FC section
    fc_pin_x = fc_x_end + 1.0
    top.shapes(li_m3).insert(rect(fc_vout_x - hw, ibias_fc_pin_y - hw,
                                    fc_pin_x, ibias_fc_pin_y + hw))
    draw_via2(top, layout, fc_pin_x, ibias_fc_pin_y)
    top.shapes(li_m2).insert(rect(fc_pin_x - hw, ibias_fc_pin_y - 0.5,
                                    fc_pin_x + 0.5, ibias_fc_pin_y + 0.5))

    # ibias_q: from Q vout, route to right edge via M2
    q_vout_x, q_vout_y = q_vout
    ibias_q_pin_y = 14.0
    draw_via1(top, layout, q_vout_x, q_vout_y)
    draw_via2(top, layout, q_vout_x, q_vout_y)
    top.shapes(li_m3).insert(rect(q_vout_x - hw, ibias_q_pin_y - hw,
                                    q_vout_x + hw, q_vout_y))
    # Route to macro right edge
    q_pin_x = MACRO_W - 0.3
    top.shapes(li_m3).insert(rect(q_vout_x - hw, ibias_q_pin_y - hw,
                                    q_pin_x, ibias_q_pin_y + hw))
    draw_via2(top, layout, q_pin_x, ibias_q_pin_y)
    top.shapes(li_m2).insert(rect(q_pin_x - hw, ibias_q_pin_y - 0.5,
                                    MACRO_W, ibias_q_pin_y + 0.5))

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 1.5))

    # VSS bus → VSS rail connection
    vss_via_x = 2.5
    draw_via1(top, layout, vss_via_x, vss_bus_y)
    draw_via2(top, layout, vss_via_x, vss_bus_y)
    top.shapes(li_m3).insert(rect(0.5 - hw, 0.75, vss_via_x + hw, vss_bus_y + hw))

    # Second VSS connection for Q section
    q_vss_via_x = q_x_start + 1.0
    top.shapes(li_m1).insert(rect(q_vss_via_x - wire_w / 2, vss_bus_y - wire_w / 2,
                                    q_vss_via_x + wire_w / 2, vss_bus_y + wire_w / 2))
    draw_via1(top, layout, q_vss_via_x, vss_bus_y)
    draw_via2(top, layout, q_vss_via_x, vss_bus_y)
    top.shapes(li_m3).insert(rect(q_vss_via_x - hw, 0.75,
                                    q_vss_via_x + hw, vss_bus_y + hw))

    # --- Power via stacks ---
    for px in [x * 2.0 + 1.0 for x in range(int(MACRO_W / 2))]:
        if px < MACRO_W - 0.5:
            draw_power_via_stack(top, layout, px, MACRO_H - 0.75)
            draw_power_via_stack(top, layout, px, 0.75)

    # --- Pin labels ---
    # FC digital inputs
    for pin_name, pin_y in fc_pins:
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, pin_y - 0.25, 0.5, pin_y + 0.25),
                      pin_name, layout)

    # Q digital inputs
    for pin_name, pin_y in q_pins:
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, pin_y - 0.25, 0.5, pin_y + 0.25),
                      pin_name, layout)

    # ibias_fc output
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(fc_pin_x - 0.5, ibias_fc_pin_y - 0.5,
                       fc_pin_x + 0.5, ibias_fc_pin_y + 0.5),
                  "ibias_fc", layout)

    # ibias_q output
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, ibias_q_pin_y - 0.5,
                       MACRO_W, ibias_q_pin_y + 0.5),
                  "ibias_q", layout)

    # Power pins
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H), "vdd", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 1.5), "vss", layout)

    # --- PR Boundary ---
    li_bnd = layout.layer(189, 0)
    top.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout, top


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "bias_gen.gds")

    layout, top = build_bias_gen()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  FC: {FC_BITS}-bit R-2R, Q: {Q_BITS}-bit R-2R")
    print(f"  R = {R_TARGET:.0f} Ω  (rhigh: W={R_WIDTH} µm, L={R_LENGTH:.2f} µm)")
    print(f"  Switches: NMOS-only W={NMOS_W}µm L={NMOS_L}µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
