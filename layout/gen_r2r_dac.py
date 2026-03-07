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
  2R = 4 kΩ → folded as 2× R in series (two horizontal segments)

Switches: sg13_lv_nmos, L=0.13µm, W=2µm

Layout (all resistors horizontal):
  Top:        VDD rail (Metal3)
  Row 1:      Series R chain (horizontal)
  Row 2:      2R upper fold (horizontal R segments)
  Row 3:      2R lower fold (horizontal R segments, hairpin-connected)
  Row 4:      NMOS switches
  Bottom:     VSS rail (Metal3)
  Left edge:  d[7:0] input pins (Metal2, 1.5µm pitch)
  Right edge: vout pin (Metal2)

Macro size: 36 × 18 µm
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

NMOS_W    = 2.0         # switch width
NMOS_L    = 0.13        # gate length (min for 1.2V)

NBITS     = 8
MACRO_W   = 36.0
MACRO_H   = 18.0

# Derived: resistor total length (body + contact pads + SalBlock clearance)
PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY  # ~0.32 µm
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W

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
    li_nsd = layout.layer(*L_NSD)
    li_sal = layout.layer(*L_SALBLOCK)
    li_polyres = layout.layer(*L_POLYRES)
    li_extblk  = layout.layer(*L_EXTBLOCK)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    pad = PAD_W
    total_l = pad + SAL_SPACE_CONT + length + SAL_SPACE_CONT + pad

    # GatPoly body
    cell.shapes(li_gp).insert(rect(x, y, x + total_l, y + width))

    # pSD implant
    enc = 0.1
    cell.shapes(li_psd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))

    # nSD over resistor body (required for rhigh extraction)
    cell.shapes(li_nsd).insert(rect(x - enc, y - enc, x + total_l + enc, y + width + enc))

    # SalBlock over resistor body
    sal_x1 = x + pad + SAL_SPACE_CONT - SAL_ENC_GATPOLY
    sal_x2 = x + pad + SAL_SPACE_CONT + length + SAL_ENC_GATPOLY
    cell.shapes(li_sal).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                     sal_x2, y + width + SAL_ENC_GATPOLY))

    # polyres_drw marker (required for rhigh recognition)
    cell.shapes(li_polyres).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                         sal_x2, y + width + SAL_ENC_GATPOLY))

    # extblock_drw marker (required for rhigh extraction)
    cell.shapes(li_extblk).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
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


def draw_nmos(cell, layout, x, y, w=NMOS_W, l=NMOS_L):
    """Draw NMOS transistor. Returns pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))

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


def draw_power_via_stack(cell, layout, x, y):
    """Via stack from M3 to M5 for power rail connection."""
    draw_via3(cell, layout, x, y)
    draw_via4(cell, layout, x, y)


# ===========================================================================
# Main: build the R-2R DAC (compact horizontal layout)
# ===========================================================================
def build_r2r_dac():
    layout = new_layout()
    top = layout.create_cell("r2r_dac_8bit")

    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)
    wire_w = M1_WIDTH

    # --- Y coordinates for each row ---
    #   VDD rail:      16.5 – 18.0
    #   Series R:      14.0 – 16.0  (R_WIDTH = 2.0)
    #   2R upper fold: 11.0 – 13.0
    #   2R lower fold:  8.5 – 10.5
    #   NMOS switches:  5.5 –  7.5  (NMOS_W = 2.0)
    #   Gate contacts:  ~4.5
    #   Pin routing:    2.0 – 4.0
    #   VSS rail:       0.0 –  1.5
    series_y  = 14.0
    r2_upper_y = 11.0
    r2_lower_y =  8.5
    sw_y       =  5.5

    # --- X layout: series chain centered ---
    gap = 0.18
    chain_width = NBITS * R_TOTAL + (NBITS - 1) * gap
    x_start = (MACRO_W - chain_width) / 2

    # --- Draw everything ---
    x_cursor = x_start
    vref_contact = None
    vout_contact = None
    prev_rc = None
    switch_sources = []

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV  # 0.32 µm

    for i, bit in enumerate(range(NBITS - 1, -1, -1)):
        # ---- Series R (horizontal, top row) ----
        r_lc, r_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=series_y,
                                          length=R_LENGTH)
        if i == 0:
            vref_contact = r_lc
        vout_contact = r_rc

        # Bridge gap between consecutive series resistors
        if prev_rc is not None:
            bridge_y = series_y + R_WIDTH / 2
            top.shapes(li_m1).insert(rect(prev_rc[0] - wire_w / 2, bridge_y - wire_w / 2,
                                            r_lc[0] + wire_w / 2, bridge_y + wire_w / 2))
        prev_rc = r_rc

        jx, jy = r_rc  # junction point

        # ---- Folded 2R: two horizontal R segments in series ----
        # Upper fold: right contact connects to junction above
        # Lower fold: right contact connects to NMOS drain below
        # Left contacts of both folds connected by M1 hairpin

        r2u_lc, r2u_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_upper_y,
                                               length=R_LENGTH)
        r2l_lc, r2l_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_lower_y,
                                               length=R_LENGTH)

        # M1 wire: junction → 2R upper fold right contact
        top.shapes(li_m1).insert(rect(jx - wire_w / 2, r2u_rc[1],
                                        jx + wire_w / 2, jy))

        # M1 hairpin: upper fold left contact → lower fold left contact
        hp_x = r2u_lc[0]
        top.shapes(li_m1).insert(rect(hp_x - wire_w / 2, r2l_lc[1],
                                        hp_x + wire_w / 2, r2u_lc[1]))

        # ---- NMOS switch ----
        # Align drain center X with junction X (= right contact X of fold)
        drain_target_x = r2l_rc[0]
        sw_x = drain_target_x - (sd_ext + NMOS_L + sd_ext / 2)
        sw = draw_nmos(top, layout, x=sw_x, y=sw_y)
        switch_sources.append(sw['source'])

        # M1 wire: 2R lower fold right contact → switch drain
        top.shapes(li_m1).insert(rect(drain_target_x - wire_w / 2, sw['drain'][1],
                                        drain_target_x + wire_w / 2, r2l_rc[1]))

        # ---- Gate contact + Via1 → M2 for d[bit] input ----
        gate_x, gate_y = sw['gate']
        gc_y = gate_y - 0.5

        # Extend GatPoly down to contact pad
        gc_half_gp = CONT_SIZE / 2 + CONT_ENC_GATPOLY
        top.shapes(li_gp).insert(rect(gate_x - gc_half_gp, gc_y - gc_half_gp,
                                        gate_x + gc_half_gp, gate_y))

        # Gate contact (Cont + M1 pad)
        gc_hs = CONT_SIZE / 2
        top.shapes(li_cnt).insert(rect(gate_x - gc_hs, gc_y - gc_hs,
                                        gate_x + gc_hs, gc_y + gc_hs))
        gc_half_m1 = CONT_SIZE / 2 + CONT_ENC_M1
        top.shapes(li_m1).insert(rect(gate_x - gc_half_m1, gc_y - gc_half_m1,
                                        gate_x + gc_half_m1, gc_y + gc_half_m1))

        # Via1 at gate contact
        draw_via1(top, layout, gate_x, gc_y)

        # Metal2/3 route: left edge pin → gate via
        pin_y = 2.0 + bit * 1.5
        hw = M2_WIDTH / 2

        # M2 pin stub on left edge
        top.shapes(li_m2).insert(rect(0.0, pin_y - hw, 1.5, pin_y + hw))

        # Via2 at (1.5, pin_y) — M2 to M3
        draw_via2(top, layout, 1.5, pin_y)

        # M3 horizontal from left to gate_x
        top.shapes(li_m3).insert(rect(1.5, pin_y - hw, gate_x, pin_y + hw))

        # Via2 at (gate_x, pin_y) — M3 back to M2
        draw_via2(top, layout, gate_x, pin_y)

        # M2 vertical jog from pin_y to gc_y
        top.shapes(li_m2).insert(rect(gate_x - hw, min(pin_y, gc_y) - 0.1,
                                        gate_x + hw, max(pin_y, gc_y) + 0.1))

        x_cursor += R_TOTAL + gap

    # --- Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS) ---
    # Connect ptap M1 to switch source VSS bus via M1 vertical
    # (cannot use M3 — would short gate M3 routes for d0/d1)
    bus_y = switch_sources[0][1] - 0.8 if switch_sources else sw_y
    for xt in [3.0, 9.0, 15.0, 21.0, 27.0, 33.0]:
        draw_ptap(top, layout, xt, sw_y - 1.5)
        ptap_cx = xt + 0.18
        ptap_cy = sw_y - 1.5 + 0.18
        # M1 vertical from ptap up to VSS bus
        top.shapes(li_m1).insert(rect(ptap_cx - wire_w / 2, ptap_cy - wire_w / 2,
                                       ptap_cx + wire_w / 2, bus_y + wire_w / 2))

    # --- Vout pin (right edge) ---
    vout_via_x = vout_contact[0]
    vout_via_y = vout_contact[1]
    vout_pin_y = 9.0
    hw = M2_WIDTH / 2

    draw_via1(top, layout, vout_via_x, vout_via_y)
    draw_via2(top, layout, vout_via_x, vout_via_y)

    # M3 vertical from junction down to vout_pin_y
    top.shapes(li_m3).insert(rect(vout_via_x - hw, vout_pin_y - hw,
                                    vout_via_x + hw, vout_via_y))

    # M3 horizontal to right edge
    vout_via2_x = MACRO_W - 0.3
    top.shapes(li_m3).insert(rect(vout_via_x - hw, vout_pin_y - hw,
                                    vout_via2_x, vout_pin_y + hw))

    # Via2 near right edge → M2 pin
    draw_via2(top, layout, vout_via2_x, vout_pin_y)
    top.shapes(li_m2).insert(rect(vout_via2_x - hw, vout_pin_y - 0.5,
                                    MACRO_W, vout_pin_y + 0.5))

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 1.5))

    # --- Vref → VDD rail ---
    vref_x = vref_contact[0]
    vref_y = vref_contact[1]
    vdd_tap_y = MACRO_H - 0.75
    top.shapes(li_m1).insert(rect(vref_x - wire_w / 2, vref_y,
                                    vref_x + wire_w / 2, vdd_tap_y))
    draw_via1(top, layout, vref_x, vdd_tap_y)
    draw_via2(top, layout, vref_x, vdd_tap_y)

    # --- Switch sources → VSS rail ---
    if switch_sources:
        bus_y = switch_sources[0][1] - 0.8
        stub_offset = 0.15
        for sx, sy in switch_sources:
            stub_x = sx - stub_offset
            top.shapes(li_m1).insert(rect(stub_x - wire_w / 2, sy - wire_w / 2,
                                            sx + wire_w / 2, sy + wire_w / 2))
            top.shapes(li_m1).insert(rect(stub_x - wire_w / 2, bus_y - wire_w / 2,
                                            stub_x + wire_w / 2, sy))
        right_x = switch_sources[-1][0] - stub_offset
        vss_via_x = 1.0
        top.shapes(li_m1).insert(rect(vss_via_x - wire_w / 2, bus_y - wire_w / 2,
                                        right_x + wire_w / 2, bus_y + wire_w / 2))
        vss_tap_y = 0.75
        draw_via1(top, layout, vss_via_x, bus_y)
        draw_via2(top, layout, vss_via_x, bus_y)
        top.shapes(li_m3).insert(rect(vss_via_x - M2_WIDTH / 2, vss_tap_y,
                                        vss_via_x + M2_WIDTH / 2, bus_y))
        draw_via2(top, layout, vss_via_x, vss_tap_y)

    # --- Power via stacks along VDD/VSS rails ---
    vdd_rail_y = MACRO_H - 0.75
    vss_rail_y = 0.75
    for px in [x * 2.0 + 1.0 for x in range(int(MACRO_W / 2))]:
        if px < MACRO_W - 0.5:
            draw_power_via_stack(top, layout, px, vdd_rail_y)
            draw_power_via_stack(top, layout, px, vss_rail_y)

    # --- Pin labels ---
    for bit in range(NBITS):
        pin_y = 2.0 + bit * 1.5
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, pin_y - 0.5, 0.5, pin_y + 0.5),
                      f"d{bit}", layout)

    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 0.5, MACRO_W, vout_pin_y + 0.5),
                  "vout", layout)

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
    outpath = os.path.join(outdir, "r2r_dac_8bit.gds")

    layout, top = build_r2r_dac()
    layout.write(outpath)

    chain_w = NBITS * R_TOTAL + (NBITS - 1) * 0.18
    print(f"Wrote {outpath}")
    print(f"  R = {R_TARGET:.0f} Ω  (rhigh: W={R_WIDTH} µm, L={R_LENGTH:.2f} µm)")
    print(f"  2R = {R_TARGET*2:.0f} Ω  (folded: 2× R={R_LENGTH:.2f} µm in series)")
    print(f"  Series R unit length: {R_TOTAL:.2f} µm, chain: {chain_w:.1f} µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
