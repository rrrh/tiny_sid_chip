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
Both gates driven by d[n]: d=VDD → NMOS on (sw=VSS), d=0 → PMOS on (sw=VDD).
Inverted output: code 0 → Vout ≈ VDD, code 255 → Vout ≈ 0.

Bit ordering: bit 0 (LSB) maps to VDD end of series chain (lowest weight tap),
bit 7 (MSB) maps to output end (highest weight tap).

Resistors: rhigh (high-ohmic poly, ~1300 Ω/sq).
Switches: sg13_lv_nmos W=10µm L=0.13µm + sg13_lv_pmos W=20µm L=0.13µm.

Layout rows (bottom to top):
  VSS rail (Metal3)
  Gate routing (M2/M3 from left-edge pins to gate contacts)
  NMOS switches (PWell, W=10µm)
  PMOS switches (NWell, W=20µm)
  2R lower fold
  2R upper fold
  Series R chain
  VDD rail (Metal3)

Macro size: 36 × 60 µm
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

NMOS_W    = 10.0        # switch width (Ron << R for linearity)
NMOS_L    = 0.13        # gate length (min for 1.2V)
PMOS_W    = 20.0        # PMOS switch width (2× NMOS for Ron matching)
PMOS_L    = 0.13        # PMOS gate length

NBITS     = 8
MACRO_W   = 36.0
MACRO_H   = 60.0

# Derived
PAD_W     = CONT_SIZE + 2 * CONT_ENC_GATPOLY  # ~0.32 µm
R_TOTAL   = PAD_W + SAL_SPACE_CONT + R_LENGTH + SAL_SPACE_CONT + PAD_W

# Source/drain extension for switches
# Must satisfy Cnt.f (gate-to-contact ≥ 0.11µm) AND M1.e (source-drain M1 gap ≥ 0.22µm)
SW_SD_EXT = 0.40  # → Cnt.f = 0.12µm ✓, M1 gap = 0.23µm ✓

# ===========================================================================
# Layout helpers
# ===========================================================================

def draw_resistor_h(cell, layout, x, y, length, width=R_WIDTH):
    """Draw a horizontal rhigh resistor at (x,y).
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

    # polyres_drw marker
    cell.shapes(li_polyres).insert(rect(sal_x1, y - SAL_ENC_GATPOLY,
                                         sal_x2, y + width + SAL_ENC_GATPOLY))

    # extblock_drw marker
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

    sd_ext = SW_SD_EXT
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))

    gp_x1 = x + sd_ext
    cell.shapes(li_gp).insert(rect(gp_x1, y - GATPOLY_EXT,
                                    gp_x1 + l, y + w + GATPOLY_EXT))

    # Source contacts (multiple along width for low resistance)
    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    _draw_contact_column(cell, layout, s_cx, y, w)

    # Drain contacts (multiple along width)
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
    li_cnt  = layout.layer(*L_CONT)
    li_m1   = layout.layer(*L_METAL1)

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

    # Source contacts (multiple along width)
    s_cx = x + sd_ext / 2 - CONT_SIZE / 2
    _draw_contact_column(cell, layout, s_cx, y, w)

    # Drain contacts (multiple along width)
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
    # Center the contact array
    array_h = (n_contacts - 1) * pitch + CONT_SIZE
    y_start = y_base + (w_total - array_h) / 2

    for i in range(n_contacts):
        cy = y_start + i * pitch
        cell.shapes(li_cnt).insert(rect(cx, cy, cx + CONT_SIZE, cy + CONT_SIZE))

    # Single M1 strip covering all contacts
    y_bot = y_start - CONT_ENC_M1
    y_top = y_start + array_h + CONT_ENC_M1
    cell.shapes(li_m1).insert(rect(cx - CONT_ENC_M1, y_bot,
                                    cx + CONT_SIZE + CONT_ENC_M1, y_top))


def draw_via1(cell, layout, x, y):
    """Via1 with M1+M2 pads. M1 pad sized to meet M1.d min area (0.09µm²)."""
    li_v1 = layout.layer(*L_VIA1)
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    hs = VIA1_SIZE / 2
    cell.shapes(li_v1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    # M1 pad: max(enclosure rule, min-area requirement)
    e1 = max(VIA1_ENC_M1 + hs, 0.15)  # 0.30µm pad → area = 0.09µm²
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

    # --- Y coordinates for each row (bottom to top) ---
    #   VSS rail:        0.0 –  1.5
    #   Pin routing:     d0@2.0, d1@3.5 ... d7@12.5
    #   ptap + VSS bus:  14.0 – 16.0
    #   NMOS (W=10):     16.5 – 26.5
    #   Gate contact:    ~27.25 (in NMOS-PMOS bridge)
    #   PMOS (W=20):     28.0 – 48.0
    #   ntap + VDD bus:  48.5 – 49.0
    #   2R lower fold:   49.5 – 51.5
    #   2R upper fold:   52.5 – 54.5
    #   Series R:        55.5 – 57.5
    #   VDD rail:        58.5 – 60.0
    sw_y       = 16.5   # NMOS row bottom
    pm_y       = 28.0   # PMOS row bottom
    r2_lower_y = 49.5   # 2R lower fold
    r2_upper_y = 52.5   # 2R upper fold
    series_y   = 55.5   # Series R chain

    # Gate contact Y: in the NMOS-PMOS bridge gap
    gc_y = (sw_y + NMOS_W + GATPOLY_EXT + pm_y - GATPOLY_EXT) / 2  # ~27.25

    # --- X layout: series chain centered ---
    gap = 0.18
    chain_width = NBITS * R_TOTAL + (NBITS - 1) * gap
    x_start = (MACRO_W - chain_width) / 2

    # --- NMOS source VSS bus ---
    # M1 horizontal bus just below NMOS, connected to ptaps and VSS rail
    vss_bus_y = sw_y - 0.5  # 16.0

    # --- PMOS source VDD bus ---
    # M1 horizontal bus just above PMOS, connected to ntaps and VDD rail
    vdd_bus_y = pm_y + PMOS_W + 0.5  # 48.5

    # --- Draw everything ---
    x_cursor = x_start
    vref_contact = None
    vout_contact = None
    prev_rc = None
    nmos_source_strips = []  # (x_left, x_right) of each source M1 strip
    pmos_source_strips = []
    pmos_devices = []  # track PMOS positions for NWell

    sd_ext = SW_SD_EXT

    for i, bit in enumerate(range(NBITS)):
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
        r2u_lc, r2u_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_upper_y,
                                               length=R_LENGTH)
        r2l_lc, r2l_rc, _ = draw_resistor_h(top, layout, x=x_cursor, y=r2_lower_y,
                                               length=R_LENGTH)

        # M1 wire: junction → 2R upper fold right contact
        top.shapes(li_m1).insert(rect(jx - wire_w / 2, r2u_rc[1],
                                        jx + wire_w / 2, jy))

        # M1 hairpin: upper fold left → lower fold left
        hp_x = r2u_lc[0]
        top.shapes(li_m1).insert(rect(hp_x - wire_w / 2, r2l_lc[1],
                                        hp_x + wire_w / 2, r2u_lc[1]))

        # ---- Drain target: 2R lower fold right contact ----
        drain_target_x = r2l_rc[0]

        # ---- NMOS switch ----
        n_sw_x = drain_target_x - (sd_ext + NMOS_L + sd_ext / 2)
        nmos = draw_nmos(top, layout, x=n_sw_x, y=sw_y)

        # Track source M1 strip extent for bus connection
        s_cx_n = n_sw_x + sd_ext / 2 - CONT_SIZE / 2
        nmos_source_strips.append((s_cx_n - CONT_ENC_M1,
                                    s_cx_n + CONT_SIZE + CONT_ENC_M1))

        # ---- PMOS switch (same drain X alignment) ----
        p_sw_x = drain_target_x - (sd_ext + PMOS_L + sd_ext / 2)
        pmos = draw_pmos(top, layout, x=p_sw_x, y=pm_y, draw_nwell=False)
        pmos_devices.append((p_sw_x, pm_y))

        s_cx_p = p_sw_x + sd_ext / 2 - CONT_SIZE / 2
        pmos_source_strips.append((s_cx_p - CONT_ENC_M1,
                                    s_cx_p + CONT_SIZE + CONT_ENC_M1))

        # ---- M1: 2R lower fold right contact → PMOS drain → NMOS drain ----
        drain_w = CONT_SIZE + 2 * CONT_ENC_M1  # match contact strip width
        top.shapes(li_m1).insert(rect(drain_target_x - drain_w / 2, nmos['drain'][1],
                                        drain_target_x + drain_w / 2, r2l_rc[1]))

        # ---- Gate connection: GatPoly bridge between NMOS and PMOS ----
        gate_x = nmos['gate'][0]
        nmos_poly_top = sw_y + NMOS_W + GATPOLY_EXT
        pmos_poly_bot = pm_y - GATPOLY_EXT
        gp_hw = PMOS_L / 2
        top.shapes(li_gp).insert(rect(gate_x - gp_hw, nmos_poly_top,
                                        gate_x + gp_hw, pmos_poly_bot))

        # ---- Gate contact shifted LEFT to avoid drain M1 overlap ----
        # Gate-to-drain X distance is only 0.265µm; M1 pads would overlap.
        # Shift gate contact 0.5µm toward source side.
        gc_x = gate_x - 0.50

        # GatPoly finger from gate bridge to shifted contact pad
        gc_half_gp = CONT_SIZE / 2 + CONT_ENC_GATPOLY
        # Horizontal GatPoly extension (bridge → contact pad)
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gp_hw,
                                        gate_x + gp_hw, gc_y + gp_hw))
        # GatPoly pad for contact
        top.shapes(li_gp).insert(rect(gc_x - gc_half_gp, gc_y - gc_half_gp,
                                        gc_x + gc_half_gp, gc_y + gc_half_gp))

        # Gate contact
        gc_hs = CONT_SIZE / 2
        top.shapes(li_cnt).insert(rect(gc_x - gc_hs, gc_y - gc_hs,
                                        gc_x + gc_hs, gc_y + gc_hs))
        gc_half_m1 = CONT_SIZE / 2 + CONT_ENC_M1
        top.shapes(li_m1).insert(rect(gc_x - gc_half_m1, gc_y - gc_half_m1,
                                        gc_x + gc_half_m1, gc_y + gc_half_m1))

        # Via1 at gate contact → M2
        draw_via1(top, layout, gc_x, gc_y)

        # ---- Pin routing: left edge M2 → M3 → gate via M2 ----
        pin_y = 2.0 + bit * 1.5
        hw = M2_WIDTH / 2

        # M2 pin stub on left edge
        top.shapes(li_m2).insert(rect(0.0, pin_y - hw, 1.5, pin_y + hw))

        # Via2 at (1.5, pin_y) — M2 to M3
        draw_via2(top, layout, 1.5, pin_y)

        # M3 horizontal from left to shifted gate contact X
        top.shapes(li_m3).insert(rect(1.5, pin_y - hw, gc_x, pin_y + hw))

        # Via2 at (gc_x, pin_y) — M3 back to M2
        draw_via2(top, layout, gc_x, pin_y)

        # M2 vertical jog from pin_y to gc_y
        top.shapes(li_m2).insert(rect(gc_x - hw, min(pin_y, gc_y) - 0.1,
                                        gc_x + hw, max(pin_y, gc_y) + 0.1))

        x_cursor += R_TOTAL + gap

    # --- NWell strip for all PMOS devices ---
    nw_enc = NWELL_ENC_ACTIV
    if pmos_devices:
        nw_x1 = pmos_devices[0][0] - nw_enc
        nw_x2 = pmos_devices[-1][0] + (sd_ext + PMOS_L + sd_ext) + nw_enc
        nw_y1 = pm_y - nw_enc
        nw_y2 = pm_y + PMOS_W + nw_enc
        top.shapes(li_nw).insert(rect(nw_x1, nw_y1, nw_x2, nw_y2))

    # --- NMOS sources → VSS bus (M1 extension down to bus) ---
    # VSS bus: horizontal M1 at vss_bus_y
    top.shapes(li_m1).insert(rect(1.0, vss_bus_y - wire_w / 2,
                                    35.0, vss_bus_y + wire_w / 2))
    for x_l, x_r in nmos_source_strips:
        # Extend source M1 strip down to VSS bus
        top.shapes(li_m1).insert(rect(x_l, vss_bus_y, x_r, sw_y + 0.5))

    # VSS bus → VSS rail via L-shaped M3 path:
    # Via stack at (2.5, vss_bus_y) → M3 horizontal to x=0.5 at y=vss_bus_y
    # → M3 vertical from (0.5, vss_bus_y) down to VSS rail at y=0.75.
    # This avoids crossing gate M3 routes (at y=2.0-12.5, x=1.5+).
    vss_via_x = 2.5
    top.shapes(li_m1).insert(rect(1.0, vss_bus_y - wire_w / 2,
                                    vss_via_x + wire_w / 2, vss_bus_y + wire_w / 2))
    draw_via1(top, layout, vss_via_x, vss_bus_y)
    draw_via2(top, layout, vss_via_x, vss_bus_y)
    # M3 horizontal from via2 to left edge
    top.shapes(li_m3).insert(rect(0.5 - hw, vss_bus_y - hw,
                                    vss_via_x + hw, vss_bus_y + hw))
    # M3 vertical from left edge down to VSS rail
    top.shapes(li_m3).insert(rect(0.5 - hw, 0.75, 0.5 + hw, vss_bus_y))

    # --- Substrate taps (ptap for PWell near NMOS) ---
    ptap_y = sw_y - 1.5
    for xt in [3.0, 9.0, 15.0, 21.0, 27.0, 33.0]:
        draw_ptap(top, layout, xt, ptap_y)
        ptap_cx = xt + 0.18
        ptap_cy = ptap_y + 0.18
        # Connect ptap to VSS bus
        top.shapes(li_m1).insert(rect(ptap_cx - wire_w / 2, ptap_cy,
                                       ptap_cx + wire_w / 2, vss_bus_y))

    # --- PMOS sources → VDD via M2 bus ---
    # VDD bus on M2 (not M1!) so drain M1 wires can pass through.
    # Each PMOS source M1 strip → via1 → M2 bus → via2 → M3 → VDD rail.
    vdd_bus_m2_y = vdd_bus_y  # M2 bus at same Y
    for x_l, x_r in pmos_source_strips:
        src_cx = (x_l + x_r) / 2
        # Extend source M1 strip up from contact column
        top.shapes(li_m1).insert(rect(x_l, pm_y + PMOS_W - 0.5, x_r, vdd_bus_m2_y))
        # Via1 at top of source strip → M2
        draw_via1(top, layout, src_cx, vdd_bus_m2_y)

    # M2 horizontal VDD bus connecting all source via1 pads
    m2_hw = M2_WIDTH / 2
    top.shapes(li_m2).insert(rect(2.0, vdd_bus_m2_y - m2_hw,
                                    35.0, vdd_bus_m2_y + m2_hw))

    # VDD bus M2 → M3 → VDD rail (at left side, clear of gate M3 routing)
    vdd_via2_x = 2.5
    draw_via2(top, layout, vdd_via2_x, vdd_bus_m2_y)
    top.shapes(li_m3).insert(rect(vdd_via2_x - hw, vdd_bus_m2_y,
                                    vdd_via2_x + hw, MACRO_H - 0.75))

    # --- NWell taps (ntap for PMOS NWell, LU.a) ---
    # Place between drain wires to avoid M1.b conflicts
    if pmos_devices:
        ntap_y = pm_y + PMOS_W + 0.4  # above PMOS active, inside NWell
        # Place at midpoints between drain wire positions (every ~4.3µm)
        for ntx in [7.0, 15.5, 24.0, 32.0]:
            draw_ntap(top, layout, ntx, ntap_y, w=0.36, h=0.36)
            ntap_cx = ntx + 0.18
            ntap_cy = ntap_y + 0.18
            # Connect ntap M1 → via1 → M2 VDD bus
            top.shapes(li_m1).insert(rect(ntap_cx - wire_w / 2, ntap_cy,
                                           ntap_cx + wire_w / 2, vdd_bus_m2_y))
            draw_via1(top, layout, ntap_cx, vdd_bus_m2_y)

    # --- Vout pin (right edge) ---
    vout_via_x = vout_contact[0]
    vout_via_y = vout_contact[1]
    vout_pin_y = 30.0
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
    print(f"  Switches: NMOS W={NMOS_W}µm + PMOS W={PMOS_W}µm, L={NMOS_L}µm")
    print(f"  Series R unit length: {R_TOTAL:.2f} µm, chain: {chain_w:.1f} µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
