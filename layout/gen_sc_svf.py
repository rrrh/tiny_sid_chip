#!/usr/bin/env python3
"""
Generate 2nd-order SC+OTA SVF layout for IHP SG13G2 130nm.

Architecture: Tow-Thomas biquad with SC resistors + OTA integrators + inverter.

  fc[10:0] → 16-bit NCO → sc_clk → NOL → phi1, phi2
  res[3:0] → q[3:0] = 15-res → C_Q enable switches

  Vin ──→ [SC_R_in] ──→ sum1 ──→ [OTA1: inv. integrator] ──→ BP
                          ↑                                     │
  LP ───→ [SC_R_fb] ──→──┘        Cint1 (feedback bp→sum1)     │
                          ↑                                     │
  BP ───→ [SC_R_damp] ──→┘ (C_Q array, q-switched)             │
                                                                │
  BP ───→ [SC_R_int2] ──→ sum2 ──→ [OTA2: inv. integrator] ──→ lp_neg
                                    Cint2 (feedback lp_neg→sum2)
                                                                │
  lp_neg → [SC_R_inv_a] ─→ sum3 ──→ [OTA3: inverter] ──→ LP   │
  LP ────→ [SC_R_inv_b] ─→ sum3    (gain=-1, no Cint)          │
                                                   └── feedback ┘

  Filter params: fc = Csw×fclk/(2π×Cint),  Q = Csw_in/Csw_q

Components:
  3 × OTA (5T diff pair: 2 integrators + 1 inverter)
  2 × MIM integration cap (C_int = 1.1 pF, ~27×27 µm)
  5 × MIM switching cap (C_sw = 73.5 fF, ~7×7 µm)
  4 × C_Q array cap (4.9 fF unit, binary-weighted: 4.9/9.8/19.6/39.2 fF)
  16 × CMOS switch (6 SC resistors × 2 clock + 4 C_Q enable)
  1 × NOL clock generator (2 NAND + 2 INV, 8 transistors)
  4 × CMOS transmission gate (analog mux: LP/BP/HP/bypass)
  1 × Bias generator (diode-connected PMOS + NMOS)

Macro size: 70 × 72 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 70.0
MACRO_H = 72.0

# OTA transistor sizes
OTA_DP_W  = 4.0    # NMOS diff pair width (µm)
OTA_DP_L  = 0.50   # diff pair length
OTA_LD_W  = 2.0    # PMOS load width
OTA_LD_L  = 0.50   # PMOS load length
OTA_TAIL_W = 2.0   # NMOS tail width
OTA_TAIL_L = 0.50  # tail length

# MIM integration caps (C_int = 1.1 pF each)
C_INT      = 1.1            # pF per integrator
C_INT_SIDE = 27.1           # µm (27.1² × 1.5 = 1101 fF ≈ 1.1 pF)

# Switching caps (C_sw = 73.5 fF)
C_SW       = 0.0735         # pF
C_SW_SIDE  = 7.0            # µm (7.0² × 1.5 = 73.5 fF)

# C_Q unit cap (4.9 fF — gives Q = Csw_in/Csw_q = 73.5/(n×4.9), range 1..15)
CQ_UNIT_SIDE = 1.81         # µm (1.81² × 1.5 = 4.9 fF)

# CMOS switch sizes
SW_N_W = 2.0    # NMOS switch width
SW_N_L = 0.13   # min length for on-resistance
SW_P_W = 4.0    # PMOS switch width (2× NMOS for balanced R_on)
SW_P_L = 0.13

# Mux CMOS transmission gate sizes
MUX_N_W = 2.0
MUX_N_L = 0.13
MUX_P_W = 4.0
MUX_P_L = 0.13

# NOL clock gate sizes
NOL_N_W = 1.0
NOL_N_L = 0.13
NOL_P_W = 2.0
NOL_P_L = 0.13

# Bias generator sizes
BIAS_N_W = 2.0
BIAS_N_L = 0.50
BIAS_P_W = 2.0
BIAS_P_L = 0.50


# ===========================================================================
# Transistor drawing helpers
# ===========================================================================

def draw_nmos(cell, layout, x, y, w, l, sd_ext=None):
    """Draw NMOS transistor, return pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    if sd_ext is None:
        sd_ext = SD_EXT
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    # No nSD drawn — NMOS = Activ + GatPoly without pSD or nSD

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
        'gate':   (gp_x1 + l / 2, y + w + GATPOLY_EXT),
        'source': (x + sd_ext / 2, y + w / 2),
        'drain':  (gp_x1 + l + sd_ext / 2, y + w / 2),
        'width':  act_len,
    }


def draw_pmos(cell, layout, x, y, w, l, draw_nwell=True, sd_ext=None):
    """Draw PMOS transistor (in NWell), return pin centers dict."""
    li_act  = layout.layer(*L_ACTIV)
    li_gp   = layout.layer(*L_GATPOLY)
    li_psd  = layout.layer(*L_PSD)
    li_nw   = layout.layer(*L_NWELL)
    li_cnt  = layout.layer(*L_CONT)
    li_m1   = layout.layer(*L_METAL1)

    if sd_ext is None:
        sd_ext = SD_EXT
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


def draw_gate_contact(cell, layout, gate_x, gate_y, l, side='above'):
    """Add Contact + M1 pad on GatPoly extension for gate connection.
    Extends poly if needed. Works for any L (narrow gates use centered contact).
    Returns (m1_cx, m1_cy)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    margin = 0.14  # Cnt.e: min Cont on GatPoly space to Activ = 0.14µm
    gp_enc = CONT_ENC_GATPOLY  # 0.08

    if side == 'above':
        activ_top = gate_y - GATPOLY_EXT
        cnt_bot = activ_top + margin
        cnt_cy = cnt_bot + CONT_SIZE / 2
        poly_top = cnt_bot + CONT_SIZE + gp_enc
        if poly_top > gate_y:
            cell.shapes(li_gp).insert(rect(gate_x - l / 2, gate_y,
                                            gate_x + l / 2, poly_top))
    else:  # below
        activ_bot = gate_y + GATPOLY_EXT
        cnt_top = activ_bot - margin
        cnt_cy = cnt_top - CONT_SIZE / 2
        poly_bot = cnt_top - CONT_SIZE - gp_enc
        if poly_bot < gate_y:
            cell.shapes(li_gp).insert(rect(gate_x - l / 2, poly_bot,
                                            gate_x + l / 2, gate_y))

    cnt_x = gate_x - CONT_SIZE / 2
    cnt_y = cnt_cy - CONT_SIZE / 2
    cell.shapes(li_cnt).insert(rect(cnt_x, cnt_y,
                                     cnt_x + CONT_SIZE, cnt_y + CONT_SIZE))
    cell.shapes(li_m1).insert(rect(cnt_x - CONT_ENC_M1, cnt_y - CONT_ENC_M1,
                                    cnt_x + CONT_SIZE + CONT_ENC_M1,
                                    cnt_y + CONT_SIZE + CONT_ENC_M1))

    return (gate_x, cnt_cy)


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
    """TopVia1 with M5+TM1 pads."""
    li_tv1 = layout.layer(*L_TOPVIA1)
    li_m5  = layout.layer(*L_METAL5)
    li_tm1 = layout.layer(*L_TOPMETAL1)
    hs = TOPVIA1_SIZE / 2
    cell.shapes(li_tv1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e5 = TOPVIA1_ENC_M5 + hs
    cell.shapes(li_m5).insert(rect(x - e5, y - e5, x + e5, y + e5))
    TM1_MIN_HALF = 1.64 / 2
    et = max(TOPVIA1_ENC_TM1 + hs, TM1_MIN_HALF)
    y_lo = max(y - et, 0)
    cell.shapes(li_tm1).insert(rect(x - et, y_lo, x + et, y + et))


def draw_via_stack_m2_to_m5(cell, layout, x, y):
    """Full via stack M2->M3->M4->M5 at a single point."""
    draw_via2(cell, layout, x, y)
    draw_via3(cell, layout, x, y)
    draw_via4(cell, layout, x, y)


def draw_via_stack_m2_to_tm1(cell, layout, x, y):
    """Full via stack M2->M3->M4->M5->TM1 at a single point."""
    draw_via_stack_m2_to_m5(cell, layout, x, y)
    draw_topvia1(cell, layout, x, y)


def draw_via_stack_m3_to_m5(cell, layout, x, y):
    """Via stack M3->M4->M5 (no M2 involvement)."""
    draw_via3(cell, layout, x, y)
    draw_via4(cell, layout, x, y)


def draw_via_stack_m3_to_tm1(cell, layout, x, y):
    """Via stack M3->M4->M5->TM1 (no M2 involvement)."""
    draw_via_stack_m3_to_m5(cell, layout, x, y)
    draw_topvia1(cell, layout, x, y)


def draw_mim_cap(cell, layout, x, y, w, h):
    """Draw a MIM capacitor with both plates. Returns (bot_center, top_center)."""
    li_m5   = layout.layer(*L_METAL5)
    li_cmim = layout.layer(*L_CMIM)
    li_tm1  = layout.layer(*L_TOPMETAL1)

    # Cmim dielectric
    cell.shapes(li_cmim).insert(rect(x, y, x + w, y + h))
    # Metal5 bottom plate (with enclosure)
    enc = MIM_ENC_M5
    cell.shapes(li_m5).insert(rect(x - enc, y - enc, x + w + enc, y + h + enc))

    # Top plate via center must be OUTSIDE M5 bottom plate footprint.
    # M5 top edge = y + h + enc.  TopVia1 creates M5 pad of half-size 0.31µm.
    # Need ~0.30µm M5 spacing between bottom plate edge and via M5 pad.
    tv_m5_half = TOPVIA1_ENC_M5 + TOPVIA1_SIZE / 2   # 0.31
    top_via_y = y + h + enc + 0.30 + tv_m5_half       # outside M5 plate
    # TopMetal1 top plate — extend to reach TopVia1 TM1 pad
    tm1_pad_half = max(TOPVIA1_ENC_TM1 + TOPVIA1_SIZE / 2, 1.64 / 2)  # 0.82
    cell.shapes(li_tm1).insert(rect(x, y, x + w, top_via_y + tm1_pad_half))

    bot_center = (x + w / 2, y - enc)
    top_center = (x + w / 2, top_via_y)
    return bot_center, top_center


# ===========================================================================
# Block-level drawing functions
# ===========================================================================

def draw_ota(cell, layout, x, y):
    """
    Draw a 5-transistor OTA.
    Returns dict with pin centers and bounding box.
    Note: 'inp' = M1 gate = non-inverting (+)
          'inn' = M2 gate = inverting (-)
    """
    dp_gap = 1.4  # increased from 1.3 to fix M1.b between dp source wire and tail drain pad

    sd_ext_n = SD_EXT
    dp_act_len = sd_ext_n + OTA_DP_L + sd_ext_n
    ld_act_len = sd_ext_n + OTA_LD_L + sd_ext_n
    tail_act_len = sd_ext_n + OTA_TAIL_L + sd_ext_n

    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    # M5: Tail current source (NMOS)
    tail_x = x + (dp_act_len * 2 + dp_gap - tail_act_len) / 2
    m5 = draw_nmos(cell, layout, tail_x, y, w=OTA_TAIL_W, l=OTA_TAIL_L)

    # M1, M2: Differential pair (NMOS)
    dp_y = y + OTA_TAIL_W + 1.5
    m1 = draw_nmos(cell, layout, x, dp_y, w=OTA_DP_W, l=OTA_DP_L)
    m2 = draw_nmos(cell, layout, x + dp_act_len + dp_gap, dp_y, w=OTA_DP_W, l=OTA_DP_L)

    # M3, M4: PMOS current mirror load
    ld_y = dp_y + OTA_DP_W + 2.0
    nw_enc = NWELL_ENC_ACTIV
    li_nw = layout.layer(*L_NWELL)
    nw_x1 = x - nw_enc
    nw_x2 = x + dp_act_len + dp_gap + ld_act_len + nw_enc
    nw_y1 = ld_y - nw_enc
    nw_y2 = ld_y + OTA_LD_W + nw_enc
    cell.shapes(li_nw).insert(rect(nw_x1, nw_y1, nw_x2, nw_y2))

    m3 = draw_pmos(cell, layout, x, ld_y, w=OTA_LD_W, l=OTA_LD_L, draw_nwell=False)
    m4 = draw_pmos(cell, layout, x + dp_act_len + dp_gap, ld_y,
                   w=OTA_LD_W, l=OTA_LD_L, draw_nwell=False)

    # Gate contacts — place on OUTER sides to avoid M1.b with drain wires
    # Tail: gate below (away from diff pair above)
    m5_gate_x = m5['gate'][0]
    m5['gate'] = draw_gate_contact(cell, layout, m5_gate_x, y - GATPOLY_EXT,
                                    l=OTA_TAIL_L, side='below')
    # Diff pair: gates below (away from load above)
    m1_gate_x = m1['gate'][0]
    m1['gate'] = draw_gate_contact(cell, layout, m1_gate_x, dp_y - GATPOLY_EXT,
                                    l=OTA_DP_L, side='below')
    m2_gate_x = m2['gate'][0]
    m2['gate'] = draw_gate_contact(cell, layout, m2_gate_x, dp_y - GATPOLY_EXT,
                                    l=OTA_DP_L, side='below')
    # Load: gates above (away from diff pair below)
    m3_gate_x = m3['gate'][0]
    m3['gate'] = draw_gate_contact(cell, layout, m3_gate_x,
                                    ld_y + OTA_LD_W + GATPOLY_EXT,
                                    l=OTA_LD_L, side='above')
    m4_gate_x = m4['gate'][0]
    m4['gate'] = draw_gate_contact(cell, layout, m4_gate_x,
                                    ld_y + OTA_LD_W + GATPOLY_EXT,
                                    l=OTA_LD_L, side='above')

    # M1 routing: diff pair sources to tail drain
    # Route via y above tail to avoid shorting tail drain to tail source
    tail_route_y = y + OTA_TAIL_W + 0.7
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m1['source'][0] + wire_w/2, m1['source'][1] + wire_w/2))
    cell.shapes(li_m1).insert(rect(m2['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m2['source'][0] + wire_w/2, m2['source'][1] + wire_w/2))
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m2['source'][0] + wire_w/2, tail_route_y + wire_w/2))
    cell.shapes(li_m1).insert(rect(m5['drain'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m5['drain'][0] + wire_w/2, tail_route_y + wire_w/2))

    # M1.drain to M3.drain
    cell.shapes(li_m1).insert(rect(m1['drain'][0] - wire_w/2, m1['drain'][1] - wire_w/2,
                                    m1['drain'][0] + wire_w/2, m3['drain'][1] + wire_w/2))

    # M2.drain to M4.drain (output)
    cell.shapes(li_m1).insert(rect(m2['drain'][0] - wire_w/2, m2['drain'][1] - wire_w/2,
                                    m2['drain'][0] + wire_w/2, m4['drain'][1] + wire_w/2))

    # M3.gate to M4.gate (mirror)
    cell.shapes(li_m1).insert(rect(m3['gate'][0] - wire_w/2, m3['gate'][1] - wire_w/2,
                                    m4['gate'][0] + wire_w/2, m3['gate'][1] + wire_w/2))
    # M3.gate to M3.drain (diode-connected)
    cell.shapes(li_m1).insert(rect(m3['drain'][0] - wire_w/2, m3['gate'][1] - wire_w/2,
                                    m3['drain'][0] + wire_w/2, m3['drain'][1] + wire_w/2))

    total_w = dp_act_len * 2 + dp_gap
    total_h = (ld_y + OTA_LD_W) - y

    return {
        'inp':      m1['gate'],   # non-inverting (+) → tie to VCM
        'inn':      m2['gate'],   # inverting (-) → virtual ground / summing node
        'out':      m4['drain'],  # single-ended output
        'tail':     m5['gate'],   # tail bias input
        'tail_drn': m5['drain'],  # tail drain (for diode connection if needed)
        'vdd_l':    m3['source'],
        'vdd_r':    m4['source'],
        'vss':      m5['source'],
        'bbox':     (x, y, x + total_w, y + total_h),
        'total_w':  total_w,
        'total_h':  total_h,
    }


def draw_cmos_switch(cell, layout, x, y):
    """
    Draw a CMOS transmission gate (NMOS + PMOS in parallel).
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = SD_EXT

    # NMOS switch
    mn = draw_nmos(cell, layout, x, y, w=SW_N_W, l=SW_N_L)

    # PMOS switch (above NMOS, sharing source/drain columns)
    pmos_y = y + SW_N_W + 1.5
    mp = draw_pmos(cell, layout, x, pmos_y, w=SW_P_W, l=SW_P_L)

    # Gate contacts — place on OUTER sides to avoid M1.b with source/drain wires
    nmos_gate_x = mn['gate'][0]
    mn['gate'] = draw_gate_contact(cell, layout, nmos_gate_x, y - GATPOLY_EXT,
                                    l=SW_N_L, side='below')
    pmos_gate_x = mp['gate'][0]
    mp['gate'] = draw_gate_contact(cell, layout, pmos_gate_x,
                                    pmos_y + SW_P_W + GATPOLY_EXT,
                                    l=SW_P_L, side='above')

    # Connect NMOS source to PMOS source (M1 vertical)
    cell.shapes(li_m1).insert(rect(mn['source'][0] - wire_w/2, mn['source'][1] - wire_w/2,
                                    mn['source'][0] + wire_w/2, mp['source'][1] + wire_w/2))

    # Connect NMOS drain to PMOS drain (M1 vertical)
    cell.shapes(li_m1).insert(rect(mn['drain'][0] - wire_w/2, mn['drain'][1] - wire_w/2,
                                    mn['drain'][0] + wire_w/2, mp['drain'][1] + wire_w/2))

    nmos_act_len = sd_ext + SW_N_L + sd_ext
    total_h = (pmos_y + SW_P_W) - y

    return {
        'in':      mn['source'],
        'out':     mn['drain'],
        'ctrl_n':  mn['gate'],      # NMOS gate (connect to phi)
        'ctrl_p':  mp['gate'],      # PMOS gate (connect to phi_bar)
        'total_w': nmos_act_len,
        'total_h': total_h,
    }


def draw_cap_array(cell, layout, x, y):
    """
    Draw 4-bit binary-weighted C_Q capacitor array using MIM caps.
    C_q_unit = 4.9 fF (1.81×1.81 µm plate).
    Q = C_sw_in / C_sw_q = 73.5 / (n × 4.9), range 1.0..15.0

    Bit 0: 1× (1.81×1.81 µm, 4.9 fF)
    Bit 1: 2× (2.56×2.56 µm, 9.8 fF)
    Bit 2: 4× (3.62×3.62 µm, 19.6 fF)
    Bit 3: 8× (5.11×5.11 µm, 39.2 fF)

    Returns dict with per-bit top/bot centers.
    """
    import math
    gap = MIM_SPACE + 2 * MIM_ENC_M5  # TM1.b: need ≥ 1.64µm between TM1 plates

    caps = []
    cx = x
    for i in range(4):
        fF = 4.9 * (2 ** i)
        side = math.sqrt(fF / 1.5)  # MIM density 1.5 fF/µm²
        side = round(side * 200) / 200  # snap to 5nm grid
        b, t = draw_mim_cap(cell, layout, cx, y, side, side)
        caps.append({'bot': b, 'top': t, 'x': cx, 'w': side, 'h': side})
        cx += side + gap

    total_w = cx - gap - x  # last gap not counted

    return {
        'caps': caps,
        'total_w': total_w,
    }


def draw_nol_clock(cell, layout, x, y):
    """
    Draw non-overlapping clock generator (2 NAND + 2 INV, 8 transistors).
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH
    # Use wider sd_ext for NOL to give M1.b clearance between gate M1 pad
    # and source/drain M1 wires (need sd_ext/2 >= 0.165 + M1_SPACE)
    nol_sd_ext = 0.70  # gives gap = 0.70/2 - 0.165 = 0.185 > M1_SPACE

    nmos_pitch = (nol_sd_ext + NOL_N_L + nol_sd_ext) + 1.0
    nmos = []
    for i in range(4):
        nx = x + i * nmos_pitch
        mn = draw_nmos(cell, layout, nx, y, w=NOL_N_W, l=NOL_N_L, sd_ext=nol_sd_ext)
        nmos.append(mn)

    pmos_y = y + NOL_N_W + 2.0
    nw_enc = NWELL_ENC_ACTIV
    li_nw = layout.layer(*L_NWELL)
    nw_x1 = x - nw_enc
    nw_x2 = x + 4 * nmos_pitch + nw_enc
    cell.shapes(li_nw).insert(rect(nw_x1, pmos_y - nw_enc,
                                    nw_x2, pmos_y + NOL_P_W + nw_enc))

    pmos = []
    for i in range(4):
        px = x + i * nmos_pitch
        mp = draw_pmos(cell, layout, px, pmos_y, w=NOL_P_W, l=NOL_P_L,
                       draw_nwell=False, sd_ext=nol_sd_ext)
        pmos.append(mp)

    # Gate contacts between NMOS and PMOS (original positions)
    for i in range(4):
        nmos[i]['gate'] = draw_gate_contact(cell, layout, *nmos[i]['gate'],
                                             l=NOL_N_L, side='above')
        pmos[i]['gate'] = draw_gate_contact(cell, layout, *pmos[i]['gate'],
                                             l=NOL_P_L, side='below')

    # Wire NMOS/PMOS pairs as inverters (drain-to-drain)
    for i in range(4):
        cell.shapes(li_m1).insert(rect(
            nmos[i]['drain'][0] - wire_w/2, nmos[i]['drain'][1] - wire_w/2,
            nmos[i]['drain'][0] + wire_w/2, pmos[i]['drain'][1] + wire_w/2))

    # NOL interstage wiring:
    # Gate 0: INV (clk_in → phi1_bar): gate[0] connected externally
    # Gate 1: INV (phi1_bar → phi1): gate[1] = drain[0] output
    # Gate 2: NAND input: gate[2] = phi1 output = drain[1]
    # Gate 3: INV (nand_out → phi2): gate[3] = drain[2] output
    # NAND feedback: gate[0] also gets phi2 (drain[3]) — cross-coupled
    # Simplified NOL: clk→inv0→inv1(phi1)→inv2→inv3(phi2), with NAND feedback

    # Gate 1 = drain 0 (inv0 output → inv1 input)
    g1x, g1y = nmos[1]['gate']
    d0x, d0y = nmos[0]['drain']
    cell.shapes(li_m1).insert(rect(min(g1x, d0x) - wire_w/2, g1y - wire_w/2,
                                    max(g1x, d0x) + wire_w/2, g1y + wire_w/2))
    cell.shapes(li_m1).insert(rect(d0x - wire_w/2, min(g1y, d0y) - wire_w/2,
                                    d0x + wire_w/2, max(g1y, d0y) + wire_w/2))
    # PMOS[1] gate = same signal (M1 vertical from nmos[1].gate down to pmos[1].gate)
    p1gx, p1gy = pmos[1]['gate']
    cell.shapes(li_m1).insert(rect(g1x - wire_w/2, min(g1y, p1gy) - wire_w/2,
                                    g1x + wire_w/2, max(g1y, p1gy) + wire_w/2))

    # Gate 2 = drain 1 (phi1 → inv2 input)
    g2x, g2y = nmos[2]['gate']
    d1x, d1y = nmos[1]['drain']
    cell.shapes(li_m1).insert(rect(min(g2x, d1x) - wire_w/2, g2y - wire_w/2,
                                    max(g2x, d1x) + wire_w/2, g2y + wire_w/2))
    cell.shapes(li_m1).insert(rect(d1x - wire_w/2, min(g2y, d1y) - wire_w/2,
                                    d1x + wire_w/2, max(g2y, d1y) + wire_w/2))
    p2gx, p2gy = pmos[2]['gate']
    cell.shapes(li_m1).insert(rect(g2x - wire_w/2, min(g2y, p2gy) - wire_w/2,
                                    g2x + wire_w/2, max(g2y, p2gy) + wire_w/2))

    # Gate 3 = drain 2 (inv2 output → inv3 input)
    g3x, g3y = nmos[3]['gate']
    d2x, d2y = nmos[2]['drain']
    cell.shapes(li_m1).insert(rect(min(g3x, d2x) - wire_w/2, g3y - wire_w/2,
                                    max(g3x, d2x) + wire_w/2, g3y + wire_w/2))
    cell.shapes(li_m1).insert(rect(d2x - wire_w/2, min(g3y, d2y) - wire_w/2,
                                    d2x + wire_w/2, max(g3y, d2y) + wire_w/2))
    p3gx, p3gy = pmos[3]['gate']
    cell.shapes(li_m1).insert(rect(g3x - wire_w/2, min(g3y, p3gy) - wire_w/2,
                                    g3x + wire_w/2, max(g3y, p3gy) + wire_w/2))

    # NMOS[0]/PMOS[0] gate pair: connect PMOS[0] gate to NMOS[0] gate
    g0x, g0y = nmos[0]['gate']
    p0gx, p0gy = pmos[0]['gate']
    cell.shapes(li_m1).insert(rect(g0x - wire_w/2, min(g0y, p0gy) - wire_w/2,
                                    g0x + wire_w/2, max(g0y, p0gy) + wire_w/2))

    total_w = 4 * nmos_pitch
    total_h = (pmos_y + NOL_P_W) - y

    return {
        'clk_in':   nmos[0]['gate'],
        'phi1_out': nmos[1]['drain'],
        'phi2_out': nmos[3]['drain'],
        'nmos':     nmos,
        'pmos':     pmos,
        'total_w':  total_w,
        'total_h':  total_h,
    }


def draw_cmos_mux(cell, layout, x, y):
    """
    Draw 4:1 analog mux using 4 CMOS transmission gates.
    sel[1:0] decode: 00=LP, 01=BP, 10=HP, 11=bypass
    Full-swing signal path (unlike NMOS-only version).
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = SD_EXT
    act_len = sd_ext + MUX_N_L + sd_ext

    sw_pitch = MUX_N_W + MUX_P_W + 3.0  # NMOS + gap + PMOS + gap between mux channels

    switches = []
    for i in range(4):
        sy = y + i * sw_pitch
        # NMOS pass gate
        mn = draw_nmos(cell, layout, x, sy, w=MUX_N_W, l=MUX_N_L)
        # PMOS pass gate (above NMOS, parallel)
        pmos_y = sy + MUX_N_W + 1.0
        mp = draw_pmos(cell, layout, x, pmos_y, w=MUX_P_W, l=MUX_P_L)
        # Gate contacts — place on OUTER sides to avoid M1.b with source/drain wires
        nmos_gate_x = mn['gate'][0]
        mn['gate'] = draw_gate_contact(cell, layout, nmos_gate_x, sy - GATPOLY_EXT,
                                        l=MUX_N_L, side='below')
        pmos_gate_x = mp['gate'][0]
        mp['gate'] = draw_gate_contact(cell, layout, pmos_gate_x,
                                        pmos_y + MUX_P_W + GATPOLY_EXT,
                                        l=MUX_P_L, side='above')
        # Connect NMOS source to PMOS source
        cell.shapes(li_m1).insert(rect(mn['source'][0] - wire_w/2, mn['source'][1] - wire_w/2,
                                        mn['source'][0] + wire_w/2, mp['source'][1] + wire_w/2))
        # Connect NMOS drain to PMOS drain
        cell.shapes(li_m1).insert(rect(mn['drain'][0] - wire_w/2, mn['drain'][1] - wire_w/2,
                                        mn['drain'][0] + wire_w/2, mp['drain'][1] + wire_w/2))
        switches.append({'nmos': mn, 'pmos': mp,
                         'in': mn['source'], 'out': mn['drain'],
                         'ctrl_n': mn['gate'], 'ctrl_p': mp['gate']})

    # Connect all drains together via M1 vertical bus, offset right to clear gate M1 pads
    # Gate M1 right edge = gate_x + CONT_SIZE/2 + CONT_ENC_M1 = x + sd_ext + MUX_N_L/2 + 0.15
    # Bus must be > gate_right + M1_SPACE (0.18) from all gate contacts
    bus_x = x + act_len + 0.50  # well right of gate M1 pads
    for sw in switches:
        dx, dy = sw['out']
        # M1 horizontal stub from drain pad to bus
        cell.shapes(li_m1).insert(rect(dx - wire_w/2, dy - wire_w/2,
                                        bus_x + wire_w/2, dy + wire_w/2))
    cell.shapes(li_m1).insert(rect(bus_x - wire_w/2, switches[0]['out'][1] - wire_w/2,
                                    bus_x + wire_w/2, switches[3]['out'][1] + wire_w/2))

    total_h = 4 * sw_pitch

    return {
        'lp_in':       switches[0]['in'],
        'bp_in':       switches[1]['in'],
        'hp_in':       switches[2]['in'],
        'bypass_in':   switches[3]['in'],
        'lp_ctrl_n':   switches[0]['ctrl_n'],
        'lp_ctrl_p':   switches[0]['ctrl_p'],
        'bp_ctrl_n':   switches[1]['ctrl_n'],
        'bp_ctrl_p':   switches[1]['ctrl_p'],
        'hp_ctrl_n':   switches[2]['ctrl_n'],
        'hp_ctrl_p':   switches[2]['ctrl_p'],
        'bypass_ctrl_n': switches[3]['ctrl_n'],
        'bypass_ctrl_p': switches[3]['ctrl_p'],
        'out':         (bus_x, switches[0]['out'][1]),
        'total_h':     total_h,
        'act_len':     act_len,
    }


def draw_bias_gen(cell, layout, x, y):
    """
    Draw bias generator: diode-connected PMOS (from VDD) + diode-connected
    NMOS (to VSS). Junction provides V_bias ≈ VDD/2 for OTA tails and VCM.

    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    # NMOS diode (gate=drain), source to VSS
    mn = draw_nmos(cell, layout, x, y, w=BIAS_N_W, l=BIAS_N_L)

    # PMOS diode (gate=drain), source to VDD
    pmos_y = y + BIAS_N_W + 1.5
    mp = draw_pmos(cell, layout, x, pmos_y, w=BIAS_P_W, l=BIAS_P_L)

    # Gate contacts — place on OUTER sides to avoid M1.b with drain wire
    nmos_gate_x = mn['gate'][0]
    mn['gate'] = draw_gate_contact(cell, layout, nmos_gate_x, y - GATPOLY_EXT,
                                    l=BIAS_N_L, side='below')
    pmos_gate_x = mp['gate'][0]
    mp['gate'] = draw_gate_contact(cell, layout, pmos_gate_x,
                                    pmos_y + BIAS_P_W + GATPOLY_EXT,
                                    l=BIAS_P_L, side='above')

    # Connect NMOS drain to PMOS drain (bias node, M1 vertical)
    cell.shapes(li_m1).insert(rect(mn['drain'][0] - wire_w/2, mn['drain'][1] - wire_w/2,
                                    mn['drain'][0] + wire_w/2, mp['drain'][1] + wire_w/2))

    # NMOS diode: gate to drain (M1 horizontal + vertical)
    gx, gy = mn['gate']
    dx, dy = mn['drain']
    cell.shapes(li_m1).insert(rect(min(gx, dx) - wire_w/2, gy - wire_w/2,
                                    max(gx, dx) + wire_w/2, gy + wire_w/2))
    cell.shapes(li_m1).insert(rect(dx - wire_w/2, min(gy, dy) - wire_w/2,
                                    dx + wire_w/2, max(gy, dy) + wire_w/2))

    # PMOS diode: gate to drain (M1 horizontal + vertical)
    gx, gy = mp['gate']
    dx, dy = mp['drain']
    cell.shapes(li_m1).insert(rect(min(gx, dx) - wire_w/2, gy - wire_w/2,
                                    max(gx, dx) + wire_w/2, gy + wire_w/2))
    cell.shapes(li_m1).insert(rect(dx - wire_w/2, min(gy, dy) - wire_w/2,
                                    dx + wire_w/2, max(gy, dy) + wire_w/2))

    sd_ext = SD_EXT
    act_len = sd_ext + BIAS_N_L + sd_ext

    return {
        'bias_out': mn['drain'],   # V_bias ≈ VDD/2 (junction of diodes)
        'vdd':      mp['source'],  # connect to VDD rail
        'vss':      mn['source'],  # connect to VSS rail
        'total_w':  act_len,
        'total_h':  (pmos_y + BIAS_P_W) - y,
    }


# ===========================================================================
# Main: build the SC SVF (Tow-Thomas topology)
# ===========================================================================
def build_sc_svf():
    layout = new_layout()
    top = layout.create_cell("svf_2nd")

    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    li_m3 = layout.layer(*L_METAL3)

    wire_w = M1_WIDTH
    wire_w2 = M2_WIDTH

    # =====================================================================
    # Layout sections (Y offsets) — Tow-Thomas SC+OTA SVF:
    #   y=0..2     : VSS rail (Metal3)
    #   y=3..9     : C_Q array (left) + small C_sw caps + mux (right)
    #   y=11..20   : CMOS switches (16 total, in a row)
    #   y=22..50   : MIM integration caps (C_int1, C_int2, 27×27)
    #   y=50..56   : NOL clock generator + bias generator
    #   y=57..69   : OTA row (3 OTAs: int1, int2, inverter)
    #   y=70..72   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 3 OTAs (integrator 1, integrator 2, inverter)
    # =====================================================================
    ota_y = 57.0
    ota_gap = 3.0

    ota1_x = 2.2
    ota1 = draw_ota(top, layout, x=ota1_x, y=ota_y)
    ota2_x = ota1_x + ota1['total_w'] + ota_gap
    ota2 = draw_ota(top, layout, x=ota2_x, y=ota_y)
    ota3_x = ota2_x + ota2['total_w'] + ota_gap
    ota3 = draw_ota(top, layout, x=ota3_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via to M3
    for ota in [ota1, ota2, ota3]:
        for vdd_pin in ['vdd_l', 'vdd_r']:
            px, py = ota[vdd_pin]
            top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                          px + wire_w/2, MACRO_H - 2.5))
            draw_via1(top, layout, px, MACRO_H - 2.5)
            draw_via2(top, layout, px, MACRO_H - 1.0)
            # M2 bridge between via1 and via2
            top.shapes(li_m2).insert(rect(px - wire_w2/2, MACRO_H - 2.5 - wire_w2/2,
                                          px + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # Connect OTA VSS (tail source) to VSS rail via M3
    for ota in [ota1, ota2, ota3]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        draw_via2(top, layout, px, py)
        top.shapes(li_m3).insert(rect(px - wire_w2/2, 0.0,
                                       px + wire_w2/2, py + wire_w2/2))

    # =====================================================================
    # Bias generator (between NOL clock and OTAs)
    # =====================================================================
    bias_x = 2.64
    bias_y = 50.0  # well below OTA row at y=57
    bias = draw_bias_gen(top, layout, bias_x, bias_y)

    # Bias VSS to VSS rail via M3
    bvx, bvy = bias['vss']
    draw_via1(top, layout, bvx, bvy)
    draw_via2(top, layout, bvx, bvy)
    top.shapes(li_m3).insert(rect(bvx - wire_w2/2, 0.0,
                                   bvx + wire_w2/2, bvy + wire_w2/2))

    # Bias VDD to VDD rail via M3 (NOT long M1 — that would cross OTA1 routing)
    bvx, bvy = bias['vdd']
    draw_via1(top, layout, bvx, bvy)
    draw_via2(top, layout, bvx, bvy)
    top.shapes(li_m3).insert(rect(bvx - wire_w2/2, bvy - wire_w2/2,
                                   bvx + wire_w2/2, MACRO_H))

    # Connect bias output to OTA tail gates via M1 horizontal bus
    bias_out_x, bias_out_y = bias['bias_out']
    bias_bus_y = 55.5
    # Vertical from bias output to bus
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_out_y - wire_w/2,
                                   bias_out_x + wire_w/2, bias_bus_y + wire_w/2))
    # Horizontal bus connecting to all 3 OTA tail gates
    t1x, t1y = ota1['tail']
    t3x, t3y = ota3['tail']
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_bus_y - wire_w/2,
                                   t3x + wire_w/2, bias_bus_y + wire_w/2))
    # Vertical drops from bus to each OTA tail gate
    for tx, ty in [ota1['tail'], ota2['tail'], ota3['tail']]:
        top.shapes(li_m1).insert(rect(tx - wire_w/2, bias_bus_y - wire_w/2,
                                       tx + wire_w/2, ty + wire_w/2))

    # Connect OTA non-inverting inputs (inp) to bias/VCM via M2
    vcm_bus_y = 56.5
    for ota in [ota1, ota2, ota3]:
        px, py = ota['inp']
        draw_via1(top, layout, px, py)
        top.shapes(li_m2).insert(rect(bias_out_x - wire_w2/2, vcm_bus_y - wire_w2/2,
                                       px + wire_w2/2, vcm_bus_y + wire_w2/2))
        # Vertical M2 from bus to OTA inp pin
        top.shapes(li_m2).insert(rect(px - wire_w2/2, min(vcm_bus_y, py) - wire_w2/2,
                                       px + wire_w2/2, max(vcm_bus_y, py) + wire_w2/2))
    # Via from bias M1 to M2 for VCM bus
    draw_via1(top, layout, bias_out_x, bias_out_y)
    # M2 vertical from bias via1 pad up to VCM bus
    top.shapes(li_m2).insert(rect(bias_out_x - wire_w2/2, bias_out_y - wire_w2/2,
                                   bias_out_x + wire_w2/2, vcm_bus_y + wire_w2/2))

    # =====================================================================
    # NOL clock generator
    # =====================================================================
    nol_x = 14.0
    nol_y = 51.0
    nol = draw_nol_clock(top, layout, nol_x, nol_y)

    # Gate contacts now placed inside draw_nol_clock; use nol['clk_in'] directly
    nol_gate_cx = nol['clk_in'][0]
    nol_gate_cnt_y = nol['clk_in'][1]

    # NOL NMOS sources to VSS via M3
    for i in range(4):
        sx, sy = nol['nmos'][i]['source']
        draw_via1(top, layout, sx, sy)
        draw_via2(top, layout, sx, sy)
        top.shapes(li_m3).insert(rect(sx - wire_w2/2, 0.0,
                                       sx + wire_w2/2, sy + wire_w2/2))
    # NOL PMOS sources to VDD
    for i in range(4):
        px, py = nol['pmos'][i]['source']
        top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                       px + wire_w/2, MACRO_H - 2.5))
        draw_via1(top, layout, px, MACRO_H - 2.5)
        draw_via2(top, layout, px, MACRO_H - 1.0)
        # M2 bridge between via1 and via2
        top.shapes(li_m2).insert(rect(px - wire_w2/2, MACRO_H - 2.5 - wire_w2/2,
                                       px + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # =====================================================================
    # MIM Integration Caps (C_int1 and C_int2, side by side)
    # =====================================================================
    cap_y = 22.0
    c1_x = 2.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # =====================================================================
    # C_Q Binary-Weighted Cap Array (bottom-left region)
    # =====================================================================
    # Raise caps above VSS rail to keep via stack M3/M4 pads away from rail
    # Via pad half-extent = 0.195µm, need M3.b gap >= 0.21µm from rail at y=2.0
    # So cap bottom = cap_y - MIM_ENC_M5 = cap_y - 0.60; via center at cap_bottom
    # Via M3 pad bottom = cap_y - 0.60 - 0.195 = cap_y - 0.795
    # Need cap_y - 0.795 >= 2.0 + 0.21 → cap_y >= 3.005
    cq_x = NWELL_SPACE_DN + NWELL_ENC_ACTIV + 0.12  # keep NWell clear (extra margin)
    cq_y = 3.5
    cq = draw_cap_array(top, layout, cq_x, cq_y)

    # =====================================================================
    # SC Switching Caps (C_sw × 5: R_in, R_fb, R_int2, R_inv_a, R_inv_b)
    # =====================================================================
    sw_cap_y = 3.5
    csw_gap = 1.64  # TM1.b min TopMetal1 spacing between cap top plates

    csw_caps = []
    csw_x = cq_x + cq['total_w'] + csw_gap
    for i in range(5):
        cx = csw_x + i * (C_SW_SIDE + csw_gap)
        bot, top_c = draw_mim_cap(top, layout, cx, sw_cap_y, C_SW_SIDE, C_SW_SIDE)
        csw_caps.append((bot, top_c))

    csw1_bot, csw1_top = csw_caps[0]  # R_in (vin→sum1)
    csw2_bot, csw2_top = csw_caps[1]  # R_fb (lp→sum1)
    csw3_bot, csw3_top = csw_caps[2]  # R_int2 (bp→sum2)
    csw4_bot, csw4_top = csw_caps[3]  # R_inv_a (lp_neg→sum3)
    csw5_bot, csw5_top = csw_caps[4]  # R_inv_b (lp→sum3)

    # =====================================================================
    # CMOS Switches: 16 total (Tow-Thomas topology)
    #   SC_R_in (input):      sw0 (φ1), sw1 (φ2)
    #   SC_R_fb (LP feedback): sw2 (φ1), sw3 (φ2)
    #   SC_R_damp (BP damp):   sw4 (φ1), sw5 (φ2) — clock for CQ array
    #   SC_R_int2 (bp→sum2):   sw6 (φ1), sw7 (φ2)
    #   SC_R_inv_a (lp_neg→sum3): sw8 (φ1), sw9 (φ2)
    #   SC_R_inv_b (lp→sum3):  sw10 (φ1), sw11 (φ2)
    #   C_Q array enable:      sw_q0..sw_q3
    # =====================================================================
    sw_y = 12.0
    sw_gap = 2.0
    sw_start_x = NWELL_SPACE_DN + NWELL_ENC_ACTIV + 0.12

    sd_ext = SD_EXT
    sw_w = sd_ext + SW_N_L + sd_ext
    sw_pitch = sw_w + sw_gap

    switches = []
    for i in range(16):
        sx = sw_start_x + i * sw_pitch
        sw = draw_cmos_switch(top, layout, sx, sw_y)
        switches.append(sw)

    # Name the switches for clarity
    sw_r1a, sw_r1b = switches[0], switches[1]     # SC_R_in
    sw_r2a, sw_r2b = switches[2], switches[3]     # SC_R_fb
    sw_r3a, sw_r3b = switches[4], switches[5]     # SC_R_damp (clock for CQ)
    sw_r4a, sw_r4b = switches[6], switches[7]     # SC_R_int2
    sw_r5a, sw_r5b = switches[8], switches[9]     # SC_R_inv_a
    sw_r6a, sw_r6b = switches[10], switches[11]   # SC_R_inv_b
    sw_q0, sw_q1, sw_q2, sw_q3 = switches[12], switches[13], switches[14], switches[15]

    # =====================================================================
    # CMOS Analog Mux (4:1, right side)
    # =====================================================================
    mux_x = 55.0
    mux_y = 3.5
    mux = draw_cmos_mux(top, layout, mux_x, mux_y)

    # =====================================================================
    # Substrate taps (LU.b/LU.a) + body connections for LVS
    # =====================================================================
    li_nw = layout.layer(*L_NWELL)

    # --- ptaps for DRC LU.b (within 20µm of NMOS) ---
    for xt in [2.0, 10.0, 18.4, 26.0]:
        draw_ptap(top, layout, xt, ota_y - 1.0)
    for xt in [14.0, 18.0, 22.0]:
        draw_ptap(top, layout, xt, 50.0)
    for xt in [2.5, 8.5, 14.5, 20.5, 26.5, 32.5, 38.5, 44.5]:
        draw_ptap(top, layout, xt, 11.0)
    draw_ptap(top, layout, 54.0, 3.0)
    draw_ptap(top, layout, 54.0, 12.0)

    # --- ptaps with VSS via connections (for LVS pwell→VSS) ---
    for ptap_x in [8.0, 20.0, 40.0, 55.0]:
        draw_ptap(top, layout, ptap_x, 1.0)
        ptap_cx = ptap_x + 0.18
        ptap_cy = 1.0 + 0.18
        draw_via1(top, layout, ptap_cx, ptap_cy)
        draw_via2(top, layout, ptap_cx, ptap_cy)

    # --- ntaps for PMOS NWell body → VDD ---
    NTAP_OFFSET = 0.60

    # OTA PMOS ntaps
    ota_ld_y = ota_y + OTA_TAIL_W + 1.5 + OTA_DP_W + 2.0
    for ota, ota_ox in [(ota1, ota1_x), (ota2, ota2_x), (ota3, ota3_x)]:
        ntap_x = ota_ox + 0.5
        ntap_y = ota_ld_y + OTA_LD_W + NTAP_OFFSET
        draw_ntap(top, layout, ntap_x, ntap_y)
        ntap_cx = ntap_x + 0.18
        ntap_cy = ntap_y + 0.18
        src_x = ota_ox + SD_EXT / 2
        top.shapes(li_m1).insert(rect(min(ntap_cx, src_x) - wire_w/2,
                                       ntap_cy - wire_w/2,
                                       max(ntap_cx, src_x) + wire_w/2,
                                       ntap_cy + wire_w/2))

    # NOL PMOS ntap
    ntap_nol_x = nol_x
    ntap_nol_y = nol_y + NOL_N_W + 2.0 + NOL_P_W + NTAP_OFFSET
    draw_ntap(top, layout, ntap_nol_x, ntap_nol_y)

    # Bias PMOS ntap
    bias_pmos_y = bias_y + BIAS_N_W + 1.5
    ntap_bias_x = bias_x + 0.5
    ntap_bias_y = bias_pmos_y + BIAS_P_W + NTAP_OFFSET
    draw_ntap(top, layout, ntap_bias_x, ntap_bias_y)
    ntap_bias_cx = ntap_bias_x + 0.18
    ntap_bias_cy = ntap_bias_y + 0.18
    bias_src_x = bias_x + SD_EXT / 2
    top.shapes(li_m1).insert(rect(min(ntap_bias_cx, bias_src_x) - wire_w/2,
                                   ntap_bias_cy - wire_w/2,
                                   max(ntap_bias_cx, bias_src_x) + wire_w/2,
                                   ntap_bias_cy + wire_w/2))
    bvdd_y = bias['vdd'][1]
    top.shapes(li_m1).insert(rect(bias_src_x - wire_w/2, bvdd_y - wire_w/2,
                                   bias_src_x + wire_w/2, ntap_bias_cy + wire_w/2))

    # Switch PMOS ntaps: merge all 16 NWells with NWell bar + ntaps
    sw_pmos_y = sw_y + SW_N_W + 1.5
    sw_nw_y1 = sw_pmos_y - NWELL_ENC_ACTIV
    sw_nw_y2 = sw_pmos_y + SW_P_W + NWELL_ENC_ACTIV
    sw_nw_x1 = sw_start_x - NWELL_ENC_ACTIV
    sw_last_x = sw_start_x + 15 * sw_pitch
    sw_nw_x2 = sw_last_x + sw_w + NWELL_ENC_ACTIV
    top.shapes(li_nw).insert(rect(sw_nw_x1, sw_nw_y1, sw_nw_x2, sw_nw_y2))
    # ntaps along switch row
    for ntap_sx in [7.0, 25.0, 43.0]:
        ntap_sw_y = sw_pmos_y + SW_P_W + NTAP_OFFSET
        draw_ntap(top, layout, ntap_sx, ntap_sw_y)
        ntap_sw_cx = ntap_sx + 0.18
        ntap_sw_cy = ntap_sw_y + 0.18
        draw_via1(top, layout, ntap_sw_cx, ntap_sw_cy)
        draw_via2(top, layout, ntap_sw_cx, ntap_sw_cy)
        top.shapes(li_m3).insert(rect(ntap_sw_cx - wire_w2/2, ntap_sw_cy - wire_w2/2,
                                       ntap_sw_cx + wire_w2/2, MACRO_H))

    # Mux PMOS ntaps
    mux_act_len = SD_EXT + MUX_N_L + SD_EXT
    mux_nw_x2 = mux_x + mux_act_len + NWELL_ENC_ACTIV
    mux_sw_pitch = MUX_N_W + MUX_P_W + 3.0
    mux_first_pmos_y = mux_y + MUX_N_W + 1.0
    mux_last_pmos_y = mux_y + 3 * mux_sw_pitch + MUX_N_W + 1.0
    mux_nw_strip_y1 = mux_first_pmos_y - NWELL_ENC_ACTIV
    mux_nw_strip_y2 = mux_last_pmos_y + MUX_P_W + NWELL_ENC_ACTIV
    top.shapes(li_nw).insert(rect(mux_nw_x2, mux_nw_strip_y1,
                                   mux_nw_x2 + 0.62, mux_nw_strip_y2))
    ntap_mux_x = mux_nw_x2 + 0.13
    ntap_mux_y = (mux_nw_strip_y1 + mux_nw_strip_y2) / 2 - 0.18
    draw_ntap(top, layout, ntap_mux_x, ntap_mux_y)
    ntap_mux_cx = ntap_mux_x + 0.18
    ntap_mux_cy = ntap_mux_y + 0.18
    draw_via1(top, layout, ntap_mux_cx, ntap_mux_cy)
    draw_via2(top, layout, ntap_mux_cx, ntap_mux_cy)
    top.shapes(li_m3).insert(rect(ntap_mux_cx - wire_w2/2, ntap_mux_cy - wire_w2/2,
                                   ntap_mux_cx + wire_w2/2, MACRO_H))

    # =====================================================================
    # SVF signal routing — Tow-Thomas topology
    # OTA1: inv. integrator (sum1→BP), Cint1 feedback bp→sum1
    # OTA2: inv. integrator (sum2→lp_neg), Cint2 feedback lp_neg→sum2
    # OTA3: inverter (sum3→LP), gain=-1 (SC resistors, no Cint)
    # =====================================================================

    # --- OTA1 output (BP node) ---
    bp_x1, bp_y1 = ota1['out']
    draw_via1(top, layout, bp_x1, bp_y1)
    bp_route_y = ota_y - 1.2
    draw_via2(top, layout, bp_x1, bp_y1)
    draw_via2(top, layout, bp_x1, bp_route_y)
    top.shapes(li_m3).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_y1 + wire_w2/2))

    # BP → C_int1 top plate (integration cap feedback: bp → sum1)
    draw_via2(top, layout, c1_top[0], bp_route_y)
    top.shapes(li_m3).insert(rect(c1_top[0] - wire_w2/2, c1_top[1] - wire_w2/2,
                                   c1_top[0] + wire_w2/2, bp_route_y + wire_w2/2))

    # BP → OTA2.inn (via SC_R_int2 path, routed through switches)
    # BP also routes to damping switches and int2 switches via M2

    # --- OTA2 output (lp_neg node) ---
    lp_neg_x, lp_neg_y = ota2['out']
    draw_via1(top, layout, lp_neg_x, lp_neg_y)
    lp_neg_route_y = ota_y - 2.5
    draw_via2(top, layout, lp_neg_x, lp_neg_y)
    draw_via2(top, layout, lp_neg_x, lp_neg_route_y)
    top.shapes(li_m3).insert(rect(lp_neg_x - wire_w2/2, lp_neg_route_y - wire_w2/2,
                                   lp_neg_x + wire_w2/2, lp_neg_y + wire_w2/2))

    # lp_neg → C_int2 top plate (integration cap feedback: lp_neg → sum2)
    top.shapes(li_m2).insert(rect(lp_neg_x - wire_w2/2, c2_top[1] - wire_w2/2,
                                   lp_neg_x + wire_w2/2, lp_neg_route_y + wire_w2/2))

    # --- OTA3 output (LP node) ---
    lp_x1, lp_y1 = ota3['out']
    draw_via1(top, layout, lp_x1, lp_y1)
    lp_route_y = ota_y - 3.8
    draw_via2(top, layout, lp_x1, lp_y1)
    draw_via2(top, layout, lp_x1, lp_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, lp_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_y1 + wire_w2/2))

    # --- Summing nodes ---
    # sum1 = OTA1.inn (input + LP feedback + BP damping)
    sum1_x, sum1_y = ota1['inn']
    draw_via1(top, layout, sum1_x, sum1_y)

    # sum2 = OTA2.inn (BP → int2)
    sum2_x, sum2_y = ota2['inn']
    draw_via1(top, layout, sum2_x, sum2_y)

    # sum3 = OTA3.inn (lp_neg + LP feedback for inverter)
    sum3_x, sum3_y = ota3['inn']
    draw_via1(top, layout, sum3_x, sum3_y)

    # --- LP feedback to sum1 via M2/M3 ---
    fb_route_y = ota_y - 5.0
    sum1_fb_x = sum1_x - 0.25
    top.shapes(li_m2).insert(rect(sum1_fb_x - wire_w2/2, fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, fb_route_y + wire_w2/2))
    draw_via2(top, layout, sum1_fb_x, fb_route_y)
    top.shapes(li_m3).insert(rect(sum1_fb_x - wire_w2/2, fb_route_y - wire_w2/2,
                                   sum1_fb_x + wire_w2/2, sum1_y + wire_w2/2))
    draw_via2(top, layout, sum1_fb_x, sum1_y)
    top.shapes(li_m2).insert(rect(sum1_fb_x - wire_w2/2, sum1_y - wire_w2/2,
                                   sum1_x + wire_w2/2, sum1_y + wire_w2/2))
    draw_via2(top, layout, lp_x1, fb_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # --- lp_neg → OTA3.inn (inverter input) via M2 ---
    inv_route_y = ota_y - 6.5
    draw_via2(top, layout, lp_neg_x, inv_route_y)
    top.shapes(li_m3).insert(rect(lp_neg_x - wire_w2/2, inv_route_y - wire_w2/2,
                                   lp_neg_x + wire_w2/2, lp_neg_route_y + wire_w2/2))
    draw_via2(top, layout, sum3_x, inv_route_y)
    top.shapes(li_m2).insert(rect(lp_neg_x - wire_w2/2, inv_route_y - wire_w2/2,
                                   sum3_x + wire_w2/2, inv_route_y + wire_w2/2))
    top.shapes(li_m3).insert(rect(sum3_x - wire_w2/2, inv_route_y - wire_w2/2,
                                   sum3_x + wire_w2/2, sum3_y + wire_w2/2))

    # --- LP → OTA3.inn (inverter feedback) via separate path ---
    inv_fb_route_y = ota_y - 8.0
    draw_via2(top, layout, lp_x1, inv_fb_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, inv_fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, fb_route_y + wire_w2/2))
    sum3_fb_x = sum3_x + 0.25  # offset right to avoid sum3 M3 vertical
    draw_via2(top, layout, sum3_fb_x, inv_fb_route_y)
    top.shapes(li_m2).insert(rect(sum3_fb_x - wire_w2/2, inv_fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, inv_fb_route_y + wire_w2/2))
    top.shapes(li_m3).insert(rect(sum3_fb_x - wire_w2/2, inv_fb_route_y - wire_w2/2,
                                   sum3_fb_x + wire_w2/2, sum3_y + wire_w2/2))

    # =====================================================================
    # Via stacks: connect routing to MIM cap plates (M5 / TM1)
    # =====================================================================

    # C_int1: top plate (TM1) ← BP
    draw_via_stack_m3_to_tm1(top, layout, c1_top[0], c1_top[1])
    # C_int1: bottom plate (M5) → sum1 (connect to OTA1.inn)
    draw_via_stack_m2_to_m5(top, layout, c1_bot[0], c1_bot[1])
    # Route Cint1 bottom to sum1 via M3
    top.shapes(li_m3).insert(rect(c1_bot[0] - wire_w2/2, c1_bot[1] - wire_w2/2,
                                   c1_bot[0] + wire_w2/2, sum1_y + wire_w2/2))

    # C_int2: top plate (TM1) ← lp_neg
    draw_via_stack_m3_to_tm1(top, layout, c2_top[0], c2_top[1])
    # C_int2: bottom plate (M5) → sum2 (connect to OTA2.inn)
    draw_via_stack_m2_to_m5(top, layout, c2_bot[0], c2_bot[1])
    top.shapes(li_m3).insert(rect(c2_bot[0] - wire_w2/2, c2_bot[1] - wire_w2/2,
                                   c2_bot[0] + wire_w2/2, sum2_y + wire_w2/2))

    # C_sw caps: via stacks
    for csw_bot, csw_top in csw_caps:
        draw_via_stack_m3_to_tm1(top, layout, csw_top[0], csw_top[1])
        draw_via_stack_m2_to_m5(top, layout, csw_bot[0], csw_bot[1])
        top.shapes(li_m3).insert(rect(csw_bot[0] - wire_w2/2, 0.0,
                                       csw_bot[0] + wire_w2/2, csw_bot[1] + wire_w2/2))

    # C_Q array: via stacks
    for cap_info in cq['caps']:
        draw_via_stack_m3_to_tm1(top, layout, cap_info['top'][0], cap_info['top'][1])
        bot_via_x = cap_info['x'] + cap_info['w'] / 2
        draw_via_stack_m2_to_m5(top, layout, bot_via_x, cap_info['bot'][1])
        top.shapes(li_m3).insert(rect(bot_via_x - wire_w2/2, 0.0,
                                       bot_via_x + wire_w2/2, cap_info['bot'][1] + wire_w2/2))

    # =====================================================================
    # Mux routing
    # =====================================================================
    # BP → mux.bp_in
    bp_mux_x, bp_mux_y = mux['bp_in']
    draw_via1(top, layout, bp_mux_x, bp_mux_y)
    top.shapes(li_m2).insert(rect(30.0, bp_mux_y - wire_w2/2,
                                   bp_mux_x + wire_w2/2, bp_mux_y + wire_w2/2))

    # LP → mux.lp_in
    lp_mux_x, lp_mux_y = mux['lp_in']
    draw_via1(top, layout, lp_mux_x, lp_mux_y)
    top.shapes(li_m2).insert(rect(c2_x + C_INT_SIDE / 2 - wire_w2/2, lp_mux_y - wire_w2/2,
                                   lp_mux_x + wire_w2/2, lp_mux_y + wire_w2/2))

    # HP → mux.hp_in
    hp_mux_x, hp_mux_y = mux['hp_in']
    draw_via1(top, layout, hp_mux_x, hp_mux_y)

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y≈35 ---
    vin_pin_y = 35.0
    sum1_via_x = sum1_x - 0.25
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - wire_w2/2,
                                   sum1_via_x + wire_w2/2, vin_pin_y + wire_w2/2))
    draw_via2(top, layout, sum1_via_x, vin_pin_y)
    top.shapes(li_m3).insert(rect(sum1_via_x - wire_w2/2, vin_pin_y - wire_w2/2,
                                   sum1_via_x + wire_w2/2, sum1_y + wire_w2/2))

    # vin → bypass mux input
    bypass_mux_x, bypass_mux_y = mux['bypass_in']
    draw_via1(top, layout, bypass_mux_x, bypass_mux_y)
    draw_via2(top, layout, sum1_via_x, bypass_mux_y)
    top.shapes(li_m2).insert(rect(sum1_via_x - wire_w2/2, bypass_mux_y - wire_w2/2,
                                   bypass_mux_x + wire_w2/2, bypass_mux_y + wire_w2/2))

    # --- vout pin: right edge, y≈35 ---
    vout_pin_y = 35.0
    mux_out_x, mux_out_y = mux['out']
    draw_via1(top, layout, mux_out_x, mux_out_y)
    top.shapes(li_m2).insert(rect(mux_out_x - wire_w2/2,
                                   min(mux_out_y, vout_pin_y) - wire_w2/2,
                                   mux_out_x + wire_w2/2,
                                   max(mux_out_y, vout_pin_y) + wire_w2/2))
    top.shapes(li_m2).insert(rect(mux_out_x - wire_w2/2, vout_pin_y - wire_w2/2,
                                   MACRO_W, vout_pin_y + wire_w2/2))

    # --- sel[0] pin: left edge ---
    sel0_pin_y = 7.5
    sel0_gate_x, sel0_gate_y = mux['lp_ctrl_n']
    draw_via1(top, layout, sel0_gate_x, sel0_gate_y)
    top.shapes(li_m2).insert(rect(0.0, sel0_pin_y - wire_w2/2,
                                   sel0_gate_x + wire_w2/2, sel0_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(sel0_gate_x - wire_w2/2,
                                   min(sel0_pin_y, sel0_gate_y) - wire_w2/2,
                                   sel0_gate_x + wire_w2/2,
                                   max(sel0_pin_y, sel0_gate_y) + wire_w2/2))

    # --- sel[1] pin ---
    sel1_pin_y = 17.5
    sel1_gate_x, sel1_gate_y = mux['bp_ctrl_n']
    draw_via1(top, layout, sel1_gate_x, sel1_gate_y)
    top.shapes(li_m2).insert(rect(0.0, sel1_pin_y - wire_w2/2,
                                   sel1_gate_x + wire_w2/2, sel1_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(sel1_gate_x - wire_w2/2,
                                   min(sel1_pin_y, sel1_gate_y) - wire_w2/2,
                                   sel1_gate_x + wire_w2/2,
                                   max(sel1_pin_y, sel1_gate_y) + wire_w2/2))

    # --- sc_clk pin: left edge, y≈48 ---
    sc_clk_pin_y = 48.0
    via_clk_x = 13.5
    via_clk_y = nol_gate_cnt_y
    draw_via1(top, layout, via_clk_x, via_clk_y)
    top.shapes(li_m1).insert(rect(via_clk_x - wire_w/2, via_clk_y - wire_w/2,
                                   nol_gate_cx + CONT_SIZE/2 + CONT_ENC_M1,
                                   via_clk_y + wire_w/2))
    top.shapes(li_m2).insert(rect(0.0, sc_clk_pin_y - wire_w2/2,
                                   via_clk_x + wire_w2/2, sc_clk_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(via_clk_x - wire_w2/2,
                                   min(sc_clk_pin_y, via_clk_y) - wire_w2/2,
                                   via_clk_x + wire_w2/2,
                                   max(sc_clk_pin_y, via_clk_y) + wire_w2/2))

    # --- q0..q3 pins: left edge ---
    q_pin_ys = [25.0, 26.5, 28.0, 29.5]
    q_switches = [sw_q0, sw_q1, sw_q2, sw_q3]
    for qi, (qy, qsw) in enumerate(zip(q_pin_ys, q_switches)):
        q_route_x = 7.7 + qi * 0.70
        gate_x, gate_y = qsw['ctrl_n']
        q_sw_route_y = gate_y + qi * 0.70
        top.shapes(li_m2).insert(rect(0.0, qy - wire_w2/2,
                                       q_route_x + wire_w2/2, qy + wire_w2/2))
        draw_via2(top, layout, q_route_x, qy)
        draw_via2(top, layout, q_route_x, q_sw_route_y)
        top.shapes(li_m3).insert(rect(q_route_x - wire_w2/2,
                                       min(qy, q_sw_route_y) - wire_w2/2,
                                       q_route_x + wire_w2/2,
                                       max(qy, q_sw_route_y) + wire_w2/2))
        top.shapes(li_m2).insert(rect(min(q_route_x, gate_x) - wire_w2/2,
                                       q_sw_route_y - wire_w2/2,
                                       max(q_route_x, gate_x) + wire_w2/2,
                                       q_sw_route_y + wire_w2/2))
        draw_via1(top, layout, gate_x, gate_y)
        top.shapes(li_m2).insert(rect(gate_x - wire_w2/2,
                                       min(q_sw_route_y, gate_y) - wire_w2/2,
                                       gate_x + wire_w2/2,
                                       max(q_sw_route_y, gate_y) + wire_w2/2))

    # =====================================================================
    # Pin labels
    # =====================================================================
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, vin_pin_y - 2.0, 0.5, vin_pin_y + 2.0), "vin", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 2.0, MACRO_W, vout_pin_y + 2.0),
                  "vout", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, sel0_pin_y - 1.0, 0.5, sel0_pin_y + 1.0), "sel0", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, sel1_pin_y - 1.0, 0.5, sel1_pin_y + 1.0), "sel1", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, sc_clk_pin_y - 1.0, 0.5, sc_clk_pin_y + 1.0),
                  "sc_clk", layout)
    for i, qy in enumerate(q_pin_ys):
        add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                      rect(0.0, qy - 0.3, 0.5, qy + 0.3), f"q{i}", layout)
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
    outpath = os.path.join(outdir, "svf_2nd.gds")

    layout, top = build_sc_svf()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  Topology: Tow-Thomas SC+OTA biquad")
    print(f"  OTAs: 3 × 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Integration caps: 2 × {C_INT} pF (MIM {C_INT_SIDE}×{C_INT_SIDE} µm)")
    print(f"  Switching caps: 5 × {C_SW*1000:.1f} fF (MIM {C_SW_SIDE}×{C_SW_SIDE} µm)")
    print(f"  C_Q array: 4-bit binary-weighted ({CQ_UNIT_SIDE}µm unit, 4.9 fF)")
    print(f"  Q range: 1.0..15.0 (Csw_in/Csw_q), q[3:0] = 15 - res[3:0]")
    print(f"  CMOS switches: 16 (N: W={SW_N_W}µm L={SW_N_L}µm, P: W={SW_P_W}µm L={SW_P_L}µm)")
    print(f"  CMOS mux: 4 × TG (N: W={MUX_N_W}µm P: W={MUX_P_W}µm)")
    print(f"  Bias gen: PMOS+NMOS diode (W={BIAS_P_W}µm L={BIAS_P_L}µm)")
    print(f"  NOL clock: 8 transistors (4 CMOS pairs)")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
    print(f"  Alpha: {C_SW*1000:.1f}fF / {C_INT*1000:.0f}fF = {C_SW/C_INT:.4f}")
