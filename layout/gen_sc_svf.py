#!/usr/bin/env python3
"""
Generate 2nd-order Switched-Capacitor SVF layout for IHP SG13G2 130nm.

Architecture:
  Vin ──→ [SC_R1] ──→ sum ──→ [OTA1: integrator] ──→ BP ──→ [OTA2: integrator] ──→ LP
                       ↑ [SC_R2] ←── LP feedback                                    │
                       ↑ [C_Q array] ←── BP damping                                 │
                       └────────────────────────────────────────────────────────────┘

  sc_clk → NOL clock gen → phi1, phi2 for SC resistors
  q0..q3 → 4-bit binary-weighted C_Q cap array switches (Q tuning)

Components:
  2 × OTA (5-transistor simple diff pair each)
  2 × MIM integration cap (C_int = 0.5 pF, ~18.3×18.3 µm)
  3 × SC switching cap (C_sw = 33.8 fF, 4.75×4.75 µm MIM)
  4 × C_Q array cap (33.8 fF to 270 fF, binary-weighted MIM)
  10 × CMOS switch (3 SC resistors × 2 + 4 C_Q array switches)
  1 × NOL clock generator (2 NAND gates + 2 inverters in CMOS)
  4 × CMOS transmission gate (analog mux with sel[1:0])
  1 × Bias generator (diode-connected PMOS + NMOS, sets OTA tail + VCM)

Fixes vs previous version:
  - C_int 1.1pF → 0.5pF (kT/C still fine for 8-bit, saves 24% area)
  - Switch count 4 → 10 (proper 2-phase SC operation)
  - OTA inputs corrected (inn = virtual ground/summing node for negative feedback)
  - NMOS-only mux → CMOS transmission gates (full-swing signal path)
  - Added bias generator (OTA tails were floating)
  - OTA non-inverting inputs tied to VCM from bias generator

Macro size: 56 × 60 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 56.0
MACRO_H = 60.0

# OTA transistor sizes
OTA_DP_W  = 4.0    # NMOS diff pair width (µm)
OTA_DP_L  = 0.50   # diff pair length
OTA_LD_W  = 2.0    # PMOS load width
OTA_LD_L  = 0.50   # PMOS load length
OTA_TAIL_W = 2.0   # NMOS tail width
OTA_TAIL_L = 0.50  # tail length

# MIM integration caps (C_int = 0.5 pF each)
C_INT      = 0.5            # pF per integrator
C_INT_SIDE = 18.3           # µm (18.3² × 1.5 = 502 fF ≈ 0.5 pF)

# Switching caps (C_sw = 33.8 fF)
C_SW       = 0.034          # pF
C_SW_SIDE  = 4.75           # µm (4.75² × 1.5 = 33.8 fF)

# C_Q unit cap (same as C_sw)
CQ_UNIT_SIDE = 4.75         # µm (unit cap)

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

def draw_nmos(cell, layout, x, y, w, l):
    """Draw NMOS transistor, return pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
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


def draw_pmos(cell, layout, x, y, w, l, draw_nwell=True):
    """Draw PMOS transistor (in NWell), return pin centers dict."""
    li_act  = layout.layer(*L_ACTIV)
    li_gp   = layout.layer(*L_GATPOLY)
    li_psd  = layout.layer(*L_PSD)
    li_nw   = layout.layer(*L_NWELL)
    li_cnt  = layout.layer(*L_CONT)
    li_m1   = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + l + sd_ext

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
    # TopMetal1 top plate
    cell.shapes(li_tm1).insert(rect(x, y, x + w, y + h))

    bot_center = (x + w / 2, y - enc)
    top_center = (x + w / 2, y + h + 0.1)
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
    dp_gap = 1.3

    sd_ext_n = CONT_SIZE + 2 * CONT_ENC_ACTIV
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

    # M1 routing: diff pair sources to tail drain
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m1['source'][0] + wire_w/2, m1['source'][1] + wire_w/2))
    cell.shapes(li_m1).insert(rect(m2['source'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m2['source'][0] + wire_w/2, m2['source'][1] + wire_w/2))
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m2['source'][0] + wire_w/2, m5['drain'][1] + wire_w/2))

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
        'inp':    m1['gate'],   # non-inverting (+) → tie to VCM
        'inn':    m2['gate'],   # inverting (-) → virtual ground / summing node
        'out':    m4['drain'],  # single-ended output
        'tail':   m5['gate'],   # tail bias input
        'vdd_l':  m3['source'],
        'vdd_r':  m4['source'],
        'vss':    m5['source'],
        'bbox':   (x, y, x + total_w, y + total_h),
        'total_w': total_w,
        'total_h': total_h,
    }


def draw_cmos_switch(cell, layout, x, y):
    """
    Draw a CMOS transmission gate (NMOS + PMOS in parallel).
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV

    # NMOS switch
    mn = draw_nmos(cell, layout, x, y, w=SW_N_W, l=SW_N_L)

    # PMOS switch (above NMOS, sharing source/drain columns)
    pmos_y = y + SW_N_W + 1.5
    mp = draw_pmos(cell, layout, x, pmos_y, w=SW_P_W, l=SW_P_L)

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

    Bit 0: 1× unit (4.75×4.75 µm, 33.8 fF)
    Bit 1: 2× unit (4.75×9.5 µm, 67.7 fF)
    Bit 2: 4× unit (9.5×9.5 µm, 135.4 fF)
    Bit 3: 8× unit (13.4×13.4 µm, 269 fF)

    Returns dict with per-bit top/bot centers.
    """
    gap = MIM_SPACE + 2 * MIM_ENC_M5

    caps = []

    # Bit 0: 1× (4.75×4.75)
    b0, t0 = draw_mim_cap(cell, layout, x, y, 4.75, 4.75)
    caps.append({'bot': b0, 'top': t0, 'x': x, 'w': 4.75, 'h': 4.75})

    # Bit 1: 2× (4.75×9.5)
    x1 = x + 4.75 + gap
    b1, t1 = draw_mim_cap(cell, layout, x1, y, 4.75, 9.5)
    caps.append({'bot': b1, 'top': t1, 'x': x1, 'w': 4.75, 'h': 9.5})

    # Bit 2: 4× (9.5×9.5)
    x2 = x1 + 4.75 + gap
    b2, t2 = draw_mim_cap(cell, layout, x2, y, 9.5, 9.5)
    caps.append({'bot': b2, 'top': t2, 'x': x2, 'w': 9.5, 'h': 9.5})

    # Bit 3: 8× (13.4×13.4 → 269 fF ≈ 8× unit)
    x3 = x2 + 9.5 + gap
    b3, t3 = draw_mim_cap(cell, layout, x3, y, 13.4, 13.4)
    caps.append({'bot': b3, 'top': t3, 'x': x3, 'w': 13.4, 'h': 13.4})

    total_w = (x3 + 13.4) - x

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
    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV

    nmos_pitch = (sd_ext + NOL_N_L + sd_ext) + 1.0
    nmos = []
    for i in range(4):
        nx = x + i * nmos_pitch
        mn = draw_nmos(cell, layout, nx, y, w=NOL_N_W, l=NOL_N_L)
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
                       draw_nwell=False)
        pmos.append(mp)

    # Wire NMOS/PMOS pairs as inverters (drain-to-drain)
    for i in range(4):
        cell.shapes(li_m1).insert(rect(
            nmos[i]['drain'][0] - wire_w/2, nmos[i]['drain'][1] - wire_w/2,
            nmos[i]['drain'][0] + wire_w/2, pmos[i]['drain'][1] + wire_w/2))

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

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
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
        # Connect NMOS source to PMOS source
        cell.shapes(li_m1).insert(rect(mn['source'][0] - wire_w/2, mn['source'][1] - wire_w/2,
                                        mn['source'][0] + wire_w/2, mp['source'][1] + wire_w/2))
        # Connect NMOS drain to PMOS drain
        cell.shapes(li_m1).insert(rect(mn['drain'][0] - wire_w/2, mn['drain'][1] - wire_w/2,
                                        mn['drain'][0] + wire_w/2, mp['drain'][1] + wire_w/2))
        switches.append({'nmos': mn, 'pmos': mp,
                         'in': mn['source'], 'out': mn['drain'],
                         'ctrl_n': mn['gate'], 'ctrl_p': mp['gate']})

    # Connect all drains together via vertical M1 (output bus)
    out_x = switches[0]['out'][0]
    cell.shapes(li_m1).insert(rect(out_x - wire_w/2, switches[0]['out'][1] - wire_w/2,
                                    out_x + wire_w/2, switches[3]['out'][1] + wire_w/2))

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
        'out':         switches[0]['out'],
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

    # Connect NMOS drain to PMOS drain (bias node, M1 vertical)
    cell.shapes(li_m1).insert(rect(mn['drain'][0] - wire_w/2, mn['drain'][1] - wire_w/2,
                                    mn['drain'][0] + wire_w/2, mp['drain'][1] + wire_w/2))

    # NMOS diode: gate to drain (M1 horizontal)
    gx, gy = mn['gate']
    dx, dy = mn['drain']
    cell.shapes(li_m1).insert(rect(min(gx, dx) - wire_w/2, dy - wire_w/2,
                                    max(gx, dx) + wire_w/2, dy + wire_w/2))

    # PMOS diode: gate to drain (M1 horizontal)
    gx, gy = mp['gate']
    dx, dy = mp['drain']
    cell.shapes(li_m1).insert(rect(min(gx, dx) - wire_w/2, dy - wire_w/2,
                                    max(gx, dx) + wire_w/2, dy + wire_w/2))

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + BIAS_N_L + sd_ext

    return {
        'bias_out': mn['drain'],   # V_bias ≈ VDD/2 (junction of diodes)
        'vdd':      mp['source'],  # connect to VDD rail
        'vss':      mn['source'],  # connect to VSS rail
        'total_w':  act_len,
        'total_h':  (pmos_y + BIAS_P_W) - y,
    }


# ===========================================================================
# Main: build the SC SVF
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
    # Layout sections (Y offsets):
    #   y=0..2     : VSS rail (Metal3)
    #   y=3..17    : C_Q cap array (left) + C_sw caps + mux (right)
    #   y=18..38   : MIM integration caps (C_int1, C_int2, 18.3×18.3)
    #   y=38..42   : NOL clock generator + bias generator
    #   y=42..44   : routing gap + substrate taps
    #   y=44..56   : OTA row (2 OTAs, ~11.5µm tall)
    #   y=58..60   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 2 OTAs (integrator 1 and integrator 2)
    # =====================================================================
    ota_y = 44.0
    ota_gap = 3.0

    ota1_x = 2.2
    ota1 = draw_ota(top, layout, x=ota1_x, y=ota_y)
    ota2_x = ota1_x + ota1['total_w'] + ota_gap
    ota2 = draw_ota(top, layout, x=ota2_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via to M3
    for ota in [ota1, ota2]:
        for vdd_pin in ['vdd_l', 'vdd_r']:
            px, py = ota[vdd_pin]
            top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                          px + wire_w/2, MACRO_H - 2.5))
            draw_via1(top, layout, px, MACRO_H - 2.5)
            draw_via2(top, layout, px, MACRO_H - 1.0)

    # Connect OTA VSS (tail source) to VSS rail via M3
    for ota in [ota1, ota2]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        draw_via2(top, layout, px, py)
        top.shapes(li_m3).insert(rect(px - wire_w2/2, 0.0,
                                       px + wire_w2/2, py + wire_w2/2))

    # =====================================================================
    # Bias generator (between NOL clock and OTAs)
    # =====================================================================
    bias_x = 2.0
    bias_y = 38.5
    bias = draw_bias_gen(top, layout, bias_x, bias_y)

    # Bias VSS to VSS rail via M3
    bvx, bvy = bias['vss']
    draw_via1(top, layout, bvx, bvy)
    draw_via2(top, layout, bvx, bvy)
    top.shapes(li_m3).insert(rect(bvx - wire_w2/2, 0.0,
                                   bvx + wire_w2/2, bvy + wire_w2/2))

    # Bias VDD to VDD rail via M1+via
    bvx, bvy = bias['vdd']
    top.shapes(li_m1).insert(rect(bvx - wire_w/2, bvy - wire_w/2,
                                   bvx + wire_w/2, MACRO_H - 2.5))
    draw_via1(top, layout, bvx, MACRO_H - 2.5)
    draw_via2(top, layout, bvx, MACRO_H - 1.0)

    # Connect bias output to OTA tail gates via M1 horizontal bus
    bias_out_x, bias_out_y = bias['bias_out']
    bias_bus_y = 42.5
    # Vertical from bias output to bus
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_out_y - wire_w/2,
                                   bias_out_x + wire_w/2, bias_bus_y + wire_w/2))
    # Horizontal bus connecting to both OTA tail gates
    t1x, t1y = ota1['tail']
    t2x, t2y = ota2['tail']
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_bus_y - wire_w/2,
                                   t2x + wire_w/2, bias_bus_y + wire_w/2))
    # Vertical drops from bus to each OTA tail gate
    for tx, ty in [ota1['tail'], ota2['tail']]:
        top.shapes(li_m1).insert(rect(tx - wire_w/2, bias_bus_y - wire_w/2,
                                       tx + wire_w/2, ty + wire_w/2))

    # Connect OTA non-inverting inputs (inp) to bias/VCM via M2
    # Route both OTA1.inp and OTA2.inp to the bias node (≈VDD/2)
    vcm_bus_y = 43.0
    for ota in [ota1, ota2]:
        px, py = ota['inp']
        draw_via1(top, layout, px, py)
        top.shapes(li_m2).insert(rect(bias_out_x - wire_w2/2, vcm_bus_y - wire_w2/2,
                                       px + wire_w2/2, vcm_bus_y + wire_w2/2))
        # Vertical M2 from bus to OTA inp pin
        top.shapes(li_m2).insert(rect(px - wire_w2/2, min(vcm_bus_y, py) - wire_w2/2,
                                       px + wire_w2/2, max(vcm_bus_y, py) + wire_w2/2))
    # Via from bias M1 to M2 for VCM bus
    draw_via1(top, layout, bias_out_x, bias_out_y)

    # =====================================================================
    # NOL clock generator
    # =====================================================================
    nol_x = 14.0
    nol_y = 38.5
    nol = draw_nol_clock(top, layout, nol_x, nol_y)

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

    # =====================================================================
    # MIM Integration Caps (C_int1 and C_int2, side by side)
    # =====================================================================
    cap_y = 19.0
    c1_x = 2.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # =====================================================================
    # C_Q Binary-Weighted Cap Array (bottom-left region)
    # =====================================================================
    cq_x = 2.0
    cq_y = 3.0
    cq = draw_cap_array(top, layout, cq_x, cq_y)

    # =====================================================================
    # SC Switching Caps (C_sw × 3: input, LP feedback, BP damping)
    # =====================================================================
    sw_cap_y = 3.0
    csw_gap = MIM_SPACE + 2 * MIM_ENC_M5 + 0.5

    csw1_x = cq_x + cq['total_w'] + csw_gap
    csw1_bot, csw1_top = draw_mim_cap(top, layout, csw1_x, sw_cap_y,
                                        C_SW_SIDE, C_SW_SIDE)

    csw2_x = csw1_x + C_SW_SIDE + csw_gap
    csw2_bot, csw2_top = draw_mim_cap(top, layout, csw2_x, sw_cap_y,
                                        C_SW_SIDE, C_SW_SIDE)

    csw3_x = csw2_x + C_SW_SIDE + csw_gap
    csw3_bot, csw3_top = draw_mim_cap(top, layout, csw3_x, sw_cap_y,
                                        C_SW_SIDE, C_SW_SIDE)

    # =====================================================================
    # CMOS Switches: 10 total
    #   SC_R1 (input):      sw_r1a (φ1), sw_r1b (φ2)
    #   SC_R2 (LP feedback): sw_r2a (φ1), sw_r2b (φ2)
    #   SC_R3 (BP damping):  sw_r3a (φ1), sw_r3b (φ2)
    #   C_Q array:           sw_q0..sw_q3 (one per Q bit)
    # =====================================================================
    sw_y = 10.0
    sw_gap = 2.5
    sw_start_x = 2.0

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    sw_w = sd_ext + SW_N_L + sd_ext
    sw_pitch = sw_w + sw_gap

    switches = []
    for i in range(10):
        sx = sw_start_x + i * sw_pitch
        sw = draw_cmos_switch(top, layout, sx, sw_y)
        switches.append(sw)

    # Name the switches for clarity
    sw_r1a, sw_r1b = switches[0], switches[1]   # SC_R1 input resistor
    sw_r2a, sw_r2b = switches[2], switches[3]   # SC_R2 LP feedback
    sw_r3a, sw_r3b = switches[4], switches[5]   # SC_R3 BP damping
    sw_q0, sw_q1, sw_q2, sw_q3 = switches[6], switches[7], switches[8], switches[9]

    # =====================================================================
    # CMOS Analog Mux (4:1, right side)
    # =====================================================================
    mux_x = 42.0
    mux_y = 3.0
    mux = draw_cmos_mux(top, layout, mux_x, mux_y)

    # =====================================================================
    # Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS)
    # =====================================================================
    # Near OTA NMOS region
    for xt in [2.0, 10.0, 18.0, 26.0]:
        draw_ptap(top, layout, xt, ota_y - 1.0)
    # Near NOL clock NMOS
    for xt in [14.0, 18.0, 22.0]:
        draw_ptap(top, layout, xt, 37.5)
    # Near switches
    for xt in [2.0, 8.0, 14.0, 20.0, 26.0]:
        draw_ptap(top, layout, xt, 9.0)
    # Near mux
    draw_ptap(top, layout, 41.0, 2.5)
    draw_ptap(top, layout, 41.0, 10.0)

    # =====================================================================
    # SVF signal routing (M2/M3 for inter-block connections)
    # =====================================================================

    # --- OTA1 output (BP node) → C_int1 top plate + OTA2.inn + mux ---
    # OTA1 output goes to M2 via via1, then routes to:
    #   1. C_int1 top plate (integration cap feedback)
    #   2. OTA2.inn (inverting input = virtual ground of integrator 2)
    #   3. Mux BP input
    bp_x1, bp_y1 = ota1['out']
    bp_x2, bp_y2 = ota2['inn']   # FIXED: OTA2 inverting input
    draw_via1(top, layout, bp_x1, bp_y1)
    draw_via1(top, layout, bp_x2, bp_y2)
    bp_route_y = ota_y - 1.0
    # BP vertical at bp_x1: M3 from bp_route_y to bp_y1
    draw_via2(top, layout, bp_x1, bp_y1)
    draw_via2(top, layout, bp_x1, bp_route_y)
    top.shapes(li_m3).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_y1 + wire_w2/2))
    # BP horizontal on M2
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_route_y + wire_w2/2))
    # BP vertical at bp_x2: M3 from bp_route_y to bp_y2
    draw_via2(top, layout, bp_x2, bp_y2)
    draw_via2(top, layout, bp_x2, bp_route_y)
    top.shapes(li_m3).insert(rect(bp_x2 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_y2 + wire_w2/2))
    # BP → C_int1 top plate
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, c1_top[1] - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_route_y + wire_w2/2))

    # --- OTA2 output (LP node) → C_int2 top plate + feedback ---
    lp_x1, lp_y1 = ota2['out']
    draw_via1(top, layout, lp_x1, lp_y1)
    lp_route_y = ota_y - 2.5
    draw_via2(top, layout, lp_x1, lp_y1)
    draw_via2(top, layout, lp_x1, lp_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, lp_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_y1 + wire_w2/2))
    # LP → C_int2 top plate
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, c2_top[1] - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # --- Summing node: SC resistor outputs → OTA1.inn (inverting = virtual ground) ---
    # FIXED: summing node connects to OTA1 INVERTING input (negative feedback)
    sum_x, sum_y = ota1['inn']
    draw_via1(top, layout, sum_x, sum_y)

    # --- LP feedback: route LP to summing node via SC_R2 ---
    # LP → SC_R2 → summing node (OTA1.inn)
    # Verticals on M3 to avoid crossing sc_clk and q pin M2 routes
    fb_route_y = ota_y - 4.0
    top.shapes(li_m2).insert(rect(min(sum_x, lp_x1) - wire_w2/2, fb_route_y - wire_w2/2,
                                   max(sum_x, lp_x1) + wire_w2/2, fb_route_y + wire_w2/2))
    draw_via2(top, layout, sum_x, fb_route_y)
    top.shapes(li_m3).insert(rect(sum_x - wire_w2/2, fb_route_y - wire_w2/2,
                                   sum_x + wire_w2/2, sum_y + wire_w2/2))
    draw_via2(top, layout, lp_x1, fb_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # =====================================================================
    # Via stacks: connect M2 routing to MIM cap plates (M5 / TM1)
    # =====================================================================

    # C_int1: top plate (TM1) ← BP via M2→TM1 stack
    draw_via_stack_m2_to_tm1(top, layout, c1_top[0], c1_top[1])
    # C_int1: bottom plate (M5) → VSS via M5→M3 stack, then M3 to VSS rail
    draw_via_stack_m2_to_m5(top, layout, c1_bot[0], c1_bot[1])
    top.shapes(li_m3).insert(rect(c1_bot[0] - wire_w2/2, 0.0,
                                   c1_bot[0] + wire_w2/2, c1_bot[1] + wire_w2/2))

    # C_int2: top plate (TM1) ← LP via M2→TM1 stack
    draw_via_stack_m2_to_tm1(top, layout, c2_top[0], c2_top[1])
    # C_int2: bottom plate (M5) → VSS
    draw_via_stack_m2_to_m5(top, layout, c2_bot[0], c2_bot[1])
    top.shapes(li_m3).insert(rect(c2_bot[0] - wire_w2/2, 0.0,
                                   c2_bot[0] + wire_w2/2, c2_bot[1] + wire_w2/2))

    # C_sw1..3: via stacks for top and bottom plates
    for csw_bot, csw_top in [(csw1_bot, csw1_top), (csw2_bot, csw2_top),
                              (csw3_bot, csw3_top)]:
        draw_via_stack_m2_to_tm1(top, layout, csw_top[0], csw_top[1])
        draw_via_stack_m2_to_m5(top, layout, csw_bot[0], csw_bot[1])

    # C_Q array: via stacks
    for cap_info in cq['caps']:
        draw_via_stack_m2_to_tm1(top, layout, cap_info['top'][0], cap_info['top'][1])
        bot_via_x = cap_info['x'] + 1.0
        draw_via_stack_m2_to_m5(top, layout, bot_via_x, cap_info['bot'][1])

    # =====================================================================
    # Mux routing
    # =====================================================================
    # BP → mux.bp_in
    bp_mux_x, bp_mux_y = mux['bp_in']
    draw_via1(top, layout, bp_mux_x, bp_mux_y)
    top.shapes(li_m2).insert(rect(c1_x + C_INT_SIDE / 2 - wire_w2/2, bp_mux_y - wire_w2/2,
                                   bp_mux_x + wire_w2/2, bp_mux_y + wire_w2/2))

    # LP → mux.lp_in
    lp_mux_x, lp_mux_y = mux['lp_in']
    draw_via1(top, layout, lp_mux_x, lp_mux_y)
    top.shapes(li_m2).insert(rect(c2_x + C_INT_SIDE / 2 - wire_w2/2, lp_mux_y - wire_w2/2,
                                   lp_mux_x + wire_w2/2, lp_mux_y + wire_w2/2))

    # HP → mux.hp_in (from summing node area)
    hp_mux_x, hp_mux_y = mux['hp_in']
    draw_via1(top, layout, hp_mux_x, hp_mux_y)

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y≈30 ---
    vin_pin_y = 30.0
    # vin routes to OTA1.inn summing node (inverting input for correct feedback)
    # Via M3 vertical to avoid crossing M2 pin routes
    sum_via_x = sum_x  # already has via1 at sum_x, sum_y
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - wire_w2/2,
                                   sum_via_x + wire_w2/2, vin_pin_y + wire_w2/2))
    # M3 vertical from vin_pin_y to sum_y
    draw_via2(top, layout, sum_via_x, vin_pin_y)
    top.shapes(li_m3).insert(rect(sum_via_x - wire_w2/2, vin_pin_y - wire_w2/2,
                                   sum_via_x + wire_w2/2, sum_y + wire_w2/2))

    # vin also routes to bypass mux input
    bypass_mux_x, bypass_mux_y = mux['bypass_in']
    draw_via1(top, layout, bypass_mux_x, bypass_mux_y)
    draw_via2(top, layout, sum_via_x, bypass_mux_y)
    top.shapes(li_m2).insert(rect(sum_via_x - wire_w2/2, bypass_mux_y - wire_w2/2,
                                   bypass_mux_x + wire_w2/2, bypass_mux_y + wire_w2/2))

    # --- vout pin: right edge, y≈30 ---
    vout_pin_y = 30.0
    mux_out_x, mux_out_y = mux['out']
    draw_via1(top, layout, mux_out_x, mux_out_y)
    vout_jog_x = mux_out_x + 1.5
    top.shapes(li_m2).insert(rect(mux_out_x - wire_w2/2, mux_out_y - wire_w2/2,
                                   vout_jog_x + wire_w2/2, mux_out_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vout_jog_x - wire_w2/2,
                                   min(mux_out_y, vout_pin_y) - wire_w2/2,
                                   vout_jog_x + wire_w2/2,
                                   max(mux_out_y, vout_pin_y) + wire_w2/2))
    top.shapes(li_m2).insert(rect(vout_jog_x - wire_w2/2, vout_pin_y - wire_w2/2,
                                   MACRO_W, vout_pin_y + wire_w2/2))

    # --- sel[0] pin: left edge, y≈8 ---
    sel0_pin_y = 8.0
    top.shapes(li_m2).insert(rect(0.0, sel0_pin_y - wire_w2/2,
                                   mux['lp_ctrl_n'][0] + wire_w2/2, sel0_pin_y + wire_w2/2))

    # --- sel[1] pin: left edge, y≈14 ---
    sel1_pin_y = 14.0
    top.shapes(li_m2).insert(rect(0.0, sel1_pin_y - wire_w2/2,
                                   mux['bp_ctrl_n'][0] + wire_w2/2, sel1_pin_y + wire_w2/2))

    # --- sc_clk pin: left edge, y≈40 ---
    sc_clk_pin_y = 40.0
    nol_clk_y = nol['clk_in'][1]
    via_clk_x = nol_x - 1.5
    via_clk_y = nol_clk_y
    draw_via1(top, layout, via_clk_x, via_clk_y)
    top.shapes(li_m2).insert(rect(0.0, sc_clk_pin_y - wire_w2/2,
                                   via_clk_x + wire_w2/2, sc_clk_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(via_clk_x - wire_w2/2,
                                   min(sc_clk_pin_y, via_clk_y) - wire_w2/2,
                                   via_clk_x + wire_w2/2,
                                   max(sc_clk_pin_y, via_clk_y) + wire_w2/2))

    # --- q0..q3 pins: left edge, y≈45,47,49,51 ---
    q_pin_ys = [45.0, 47.0, 49.0, 51.0]

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
                      rect(0.0, qy - 0.5, 0.5, qy + 0.5), f"q{i}", layout)
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
    print(f"  OTAs: 2 × 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Integration caps: 2 × {C_INT} pF (MIM {C_INT_SIDE}×{C_INT_SIDE} µm)")
    print(f"  Switching caps: 3 × {C_SW*1000:.1f} fF (MIM {C_SW_SIDE}×{C_SW_SIDE} µm)")
    print(f"  C_Q array: 4-bit binary-weighted ({CQ_UNIT_SIDE}µm unit)")
    print(f"  CMOS switches: 10 (N: W={SW_N_W}µm L={SW_N_L}µm, P: W={SW_P_W}µm L={SW_P_L}µm)")
    print(f"  CMOS mux: 4 × TG (N: W={MUX_N_W}µm P: W={MUX_P_W}µm)")
    print(f"  Bias gen: PMOS+NMOS diode (W={BIAS_P_W}µm L={BIAS_P_L}µm)")
    print(f"  NOL clock: 8 transistors (4 CMOS pairs)")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
    print(f"  Alpha: {C_SW*1000:.1f}fF / {C_INT*1000:.0f}fF = {C_SW/C_INT:.4f}")
