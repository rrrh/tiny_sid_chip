#!/usr/bin/env python3
"""
Generate 2nd-order Switched-Capacitor SVF layout for IHP SG13G2 130nm.

Architecture (replaces gm-C SVF):
  Vin ──→ [SC_R1] ──→ sum ──→ [OTA1: integrator] ──→ BP ──→ [OTA2: integrator] ──→ LP
                       ↑ [SC_R2] ←── LP feedback                                    │
                       ↑ [C_Q array] ←── BP damping                                 │
                       └────────────────────────────────────────────────────────────┘

  sc_clk → NOL clock gen → phi1, phi2 for SC resistors
  q0..q3 → 4-bit binary-weighted C_Q cap array switches (Q tuning)

Components:
  2 × OTA (5-transistor simple diff pair each)
  2 × MIM integration cap (C_int = 1.1 pF, ~27×27 µm)
  3 × SC switching cap (C_sw = 73.5 fF, 7×7 µm MIM)
  4 × C_Q array cap (73.5 fF to 588 fF, binary-weighted MIM)
  8 × CMOS switch (for SC resistors and C_Q array)
  1 × NOL clock generator (2 NAND gates + 2 inverters in CMOS)
  4 × NMOS pass gate (analog mux with sel[1:0])

Macro size: 62 × 72 µm (compacted from 70 × 85)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 62.0
MACRO_H = 72.0

# OTA transistor sizes (same as gm-C version)
OTA_DP_W  = 4.0    # NMOS diff pair width (µm)
OTA_DP_L  = 0.50   # diff pair length
OTA_LD_W  = 2.0    # PMOS load width
OTA_LD_L  = 0.50   # PMOS load length
OTA_TAIL_W = 2.0   # NMOS tail width
OTA_TAIL_L = 0.50  # tail length

# MIM integration caps (C_int = 1.1 pF each)
C_INT      = 1.1           # pF per integrator
C_INT_SIDE = 27.1          # µm (27.1² ≈ 734 µm² → ~1.1 pF at 1.5 fF/µm²)

# Switching caps (C_sw = 73.5 fF, minimum practical MIM)
C_SW       = 0.0735        # pF
C_SW_SIDE  = 7.0           # µm (7² = 49 µm² → ~73.5 fF at 1.5 fF/µm²)

# C_Q unit cap (same as C_sw = 73.5 fF)
CQ_UNIT_SIDE = 7.0         # µm (unit cap)

# CMOS switch sizes
SW_N_W = 2.0    # NMOS switch width
SW_N_L = 0.13   # min length for on-resistance
SW_P_W = 4.0    # PMOS switch width (2× NMOS for balanced R_on)
SW_P_L = 0.13

# Mux pass gates
MUX_W = 2.0
MUX_L = 0.13

# NOL clock gate sizes
NOL_N_W = 1.0
NOL_N_L = 0.13
NOL_P_W = 2.0
NOL_P_L = 0.13


# ===========================================================================
# Transistor drawing helpers (reused from gen_svf.py)
# ===========================================================================

def draw_nmos(cell, layout, x, y, w, l):
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


def draw_mim_cap(cell, layout, x, y, w, h):
    """Draw a MIM capacitor. Returns (bot_center, top_center)."""
    li_m5   = layout.layer(*L_METAL5)
    li_cmim = layout.layer(*L_CMIM)

    cell.shapes(li_cmim).insert(rect(x, y, x + w, y + h))
    enc = MIM_ENC_M5
    cell.shapes(li_m5).insert(rect(x - enc, y - enc, x + w + enc, y + h + enc))

    bot_center = (x + w / 2, y - enc)
    top_center = (x + w / 2, y + h + 0.1)
    return bot_center, top_center


# ===========================================================================
# New block-level drawing functions for SC SVF
# ===========================================================================

def draw_ota(cell, layout, x, y):
    """
    Draw a 5-transistor OTA (same topology as gm-C version).
    Returns dict with pin centers and bounding box.
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

    # M1 routing
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
        'inp':    m1['gate'],
        'inn':    m2['gate'],
        'out':    m4['drain'],
        'tail':   m5['gate'],
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
    Used for SC resistor switches and C_Q array switches.

    Returns dict with pin centers:
      in, out, ctrl (gate for NMOS, inverted for PMOS)
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
        'in':      mn['source'],      # source side = input
        'out':     mn['drain'],       # drain side = output
        'ctrl_n':  mn['gate'],        # NMOS gate (connect to phi/ctrl)
        'ctrl_p':  mp['gate'],        # PMOS gate (connect to phi_bar/ctrl_bar)
        'total_w': nmos_act_len,
        'total_h': total_h,
    }


def draw_cap_array(cell, layout, x, y):
    """
    Draw 4-bit binary-weighted C_Q capacitor array using MIM caps.
    Placed side by side horizontally in bottom region of macro.

    Bit 0: 1× unit (7×7 µm, 73.5 fF)
    Bit 1: 2× unit (7×14 µm, 147 fF)
    Bit 2: 4× unit (14×14 µm, 294 fF)
    Bit 3: 8× unit (20×20 µm, 600 fF ≈ 8.2× unit)

    Returns dict with per-bit top/bot centers.
    """
    gap = MIM_SPACE + 2 * MIM_ENC_M5  # spacing between caps (compacted)

    caps = []

    # Bit 0: 1× (7×7)
    b0, t0 = draw_mim_cap(cell, layout, x, y, 7.0, 7.0)
    caps.append({'bot': b0, 'top': t0, 'x': x, 'w': 7.0, 'h': 7.0})

    # Bit 1: 2× (7×14)
    x1 = x + 7.0 + gap
    b1, t1 = draw_mim_cap(cell, layout, x1, y, 7.0, 14.0)
    caps.append({'bot': b1, 'top': t1, 'x': x1, 'w': 7.0, 'h': 14.0})

    # Bit 2: 4× (14×14)
    x2 = x1 + 7.0 + gap
    b2, t2 = draw_mim_cap(cell, layout, x2, y, 14.0, 14.0)
    caps.append({'bot': b2, 'top': t2, 'x': x2, 'w': 14.0, 'h': 14.0})

    # Bit 3: 8× (20×20 → 400 µm² × 1.5 = 600 fF ≈ 8.16× unit)
    x3 = x2 + 14.0 + gap
    b3, t3 = draw_mim_cap(cell, layout, x3, y, 20.0, 20.0)
    caps.append({'bot': b3, 'top': t3, 'x': x3, 'w': 20.0, 'h': 20.0})

    total_w = (x3 + 20.0) - x

    return {
        'caps': caps,
        'total_w': total_w,
    }


def draw_nol_clock(cell, layout, x, y):
    """
    Draw non-overlapping clock generator using CMOS logic gates.
    2 cross-coupled NAND gates + 2 inverters.

    Input: clk
    Outputs: phi1, phi2 (non-overlapping)

    Implementation: 4 CMOS inverter/NAND pairs using 8 transistors total.
    For layout, we place 4 NMOS + 4 PMOS in a standard-cell style row.

    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH
    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV

    # Place 4 NMOS side by side at bottom
    # Pitch must leave M1_SPACE (0.18µm) between gate via1 pads and drain wires
    nmos_pitch = (sd_ext + NOL_N_L + sd_ext) + 1.0
    nmos = []
    for i in range(4):
        nx = x + i * nmos_pitch
        mn = draw_nmos(cell, layout, nx, y, w=NOL_N_W, l=NOL_N_L)
        nmos.append(mn)

    # Place 4 PMOS above (shared NWell)
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

    # Wire NMOS/PMOS pairs as inverters (gate-to-gate, drain-to-drain)
    for i in range(4):
        # Drain-to-drain (output)
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


def draw_analog_mux(cell, layout, x, y):
    """
    Draw 4:1 analog mux using 4 NMOS pass gates (same as gm-C version).
    sel[1:0] decode: 00=HP, 01=BP, 10=LP, 11=bypass
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + MUX_L + sd_ext

    sw_pitch = MUX_W + 1.5

    switches = []
    for i in range(4):
        sy = y + i * sw_pitch
        sw = draw_nmos(cell, layout, x, sy, w=MUX_W, l=MUX_L)
        switches.append(sw)

    # Connect all drains together via vertical M1
    out_x = switches[0]['drain'][0]
    cell.shapes(li_m1).insert(rect(out_x - wire_w/2, switches[0]['drain'][1] - wire_w/2,
                                    out_x + wire_w/2, switches[3]['drain'][1] + wire_w/2))

    total_h = 4 * sw_pitch

    return {
        'hp_in':       switches[0]['source'],
        'bp_in':       switches[1]['source'],
        'lp_in':       switches[2]['source'],
        'bypass_in':   switches[3]['source'],
        'hp_gate':     switches[0]['gate'],
        'bp_gate':     switches[1]['gate'],
        'lp_gate':     switches[2]['gate'],
        'bypass_gate': switches[3]['gate'],
        'out':         switches[0]['drain'],
        'total_h':     total_h,
        'act_len':     act_len,
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
    # Layout plan (bottom to top):
    #   y=0..2     : VSS rail (Metal3)
    #   y=3..23    : C_Q cap array (left) + mux + switches (right)
    #   y=3..12    : SC switching caps (C_sw, between C_Q and mux)
    #   y=23..50   : MIM integration caps (C_int1, C_int2)
    #   y=50..54   : NOL clock generator + routing
    #   y=56..70   : OTA row (2 OTAs)
    #   y=70..72   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 2 OTAs (integrator 1 and integrator 2)
    # =====================================================================
    ota_y = 56.0
    ota_gap = 3.0

    ota1 = draw_ota(top, layout, x=2.0, y=ota_y)
    ota2_x = 2.0 + ota1['total_w'] + ota_gap
    ota2 = draw_ota(top, layout, x=ota2_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via2 to M3
    for ota in [ota1, ota2]:
        for vdd_pin in ['vdd_l', 'vdd_r']:
            px, py = ota[vdd_pin]
            top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                          px + wire_w/2, MACRO_H - 2.5))
            draw_via1(top, layout, px, MACRO_H - 2.5)
            draw_via2(top, layout, px, MACRO_H - 1.0)

    # Connect OTA VSS (tail source) to VSS rail
    for ota in [ota1, ota2]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        top.shapes(li_m2).insert(rect(px - wire_w2/2, 2.5,
                                       px + wire_w2/2, py))
        draw_via2(top, layout, px, 1.0)

    # OTA tails: connect to VCM (self-biased for behavioral sim)
    # In SC SVF, OTAs are voltage-mode integrators — tail is biased by
    # a simple current source. For layout, we tie tail gates to a bias bus.
    # Use a fixed bias point via M1 horizontal bus
    bias_bus_y = 54.0
    for ota in [ota1, ota2]:
        tx, ty = ota['tail']
        top.shapes(li_m1).insert(rect(tx - wire_w/2, bias_bus_y - wire_w/2,
                                       tx + wire_w/2, ty + wire_w/2))
    # Connect bias bus horizontally between the two OTA tails
    t1x = ota1['tail'][0]
    t2x = ota2['tail'][0]
    top.shapes(li_m1).insert(rect(t1x - wire_w/2, bias_bus_y - wire_w/2,
                                   t2x + wire_w/2, bias_bus_y + wire_w/2))

    # =====================================================================
    # NOL clock generator (between caps and switches)
    # =====================================================================
    nol_x = 42.0
    nol_y = 50.0
    nol = draw_nol_clock(top, layout, nol_x, nol_y)

    # NOL NMOS sources to VSS, PMOS sources to VDD
    for i in range(4):
        sx, sy = nol['nmos'][i]['source']
        draw_via1(top, layout, sx, sy)
        top.shapes(li_m2).insert(rect(sx - wire_w2/2, 2.5,
                                       sx + wire_w2/2, sy))
        draw_via2(top, layout, sx, 1.0)

        px, py = nol['pmos'][i]['source']
        top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                       px + wire_w/2, MACRO_H - 2.5))
        draw_via1(top, layout, px, MACRO_H - 2.5)
        draw_via2(top, layout, px, MACRO_H - 1.0)

    # =====================================================================
    # MIM Integration Caps (C_int1 and C_int2, side by side)
    # =====================================================================
    cap_y = 23.0
    c1_x = 2.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # =====================================================================
    # C_Q Binary-Weighted Cap Array (bottom-left region, y=3..25)
    # =====================================================================
    cq_x = 2.0
    cq_y = 3.0
    cq = draw_cap_array(top, layout, cq_x, cq_y)

    # =====================================================================
    # SC Switching Caps (C_sw × 2, small MIM caps for SC resistors)
    # Placed in bottom region between C_Q array and mux
    # =====================================================================
    sw_cap_y = 3.0
    csw1_x = cq_x + cq['total_w'] + MIM_SPACE + 2 * MIM_ENC_M5 + 0.5
    csw1_bot, csw1_top = draw_mim_cap(top, layout, csw1_x, sw_cap_y,
                                        C_SW_SIDE, C_SW_SIDE)

    csw2_x = csw1_x
    csw2_y = sw_cap_y + C_SW_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 0.3
    csw2_bot, csw2_top = draw_mim_cap(top, layout, csw2_x, csw2_y,
                                        C_SW_SIDE, C_SW_SIDE)

    # =====================================================================
    # CMOS Switches (for SC resistors: 2 per SC_R, 4 total)
    # Placed in single horizontal row above mux
    # =====================================================================
    sw_y = 18.0
    sw_gap = 2.5  # NW.b1: min 1.8µm PWell between NWells (different net)
    sw_start_x = 46.0

    sw1 = draw_cmos_switch(top, layout, sw_start_x, sw_y)
    sw2 = draw_cmos_switch(top, layout, sw_start_x + sw1['total_w'] + sw_gap, sw_y)
    sw3 = draw_cmos_switch(top, layout, sw_start_x + 2*(sw1['total_w'] + sw_gap), sw_y)
    sw4 = draw_cmos_switch(top, layout, sw_start_x + 3*(sw1['total_w'] + sw_gap), sw_y)

    # =====================================================================
    # Analog Mux (right side, bottom region)
    # =====================================================================
    mux_x = 46.0
    mux_y = 3.0
    mux = draw_analog_mux(top, layout, mux_x, mux_y)

    # =====================================================================
    # Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS)
    # =====================================================================
    # Near OTA NMOS region (y≈56)
    for xt in [2.0, 10.0, 18.0, 26.0]:
        draw_ptap(top, layout, xt, 55.0)
    # Near NOL clock NMOS (y≈50)
    for xt in [42.0, 46.0, 50.0]:
        draw_ptap(top, layout, xt, 49.0)
    # Near CMOS switches (y≈16 and below)
    for xt in [46.0, 50.0, 54.0]:
        draw_ptap(top, layout, xt, 15.0)
    # Near mux switches (y≈3)
    draw_ptap(top, layout, 45.0, 2.5)
    draw_ptap(top, layout, 45.0, 8.0)

    # =====================================================================
    # SVF signal routing (M2 layer for inter-block connections)
    # =====================================================================

    # BP node: OTA1 output → C_int1 top + OTA2 input + C_Q array + mux
    bp_x1, bp_y1 = ota1['out']
    bp_x2, bp_y2 = ota2['inp']
    draw_via1(top, layout, bp_x1, bp_y1)
    draw_via1(top, layout, bp_x2, bp_y2)
    bp_route_y = ota_y - 1.0
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_y1 + wire_w2/2))
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(bp_x2 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_y2 + wire_w2/2))
    # BP → C_int1
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, c1_top[1] - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_route_y + wire_w2/2))

    # LP node: OTA2 output → C_int2 top + feedback SC_R2
    lp_x1, lp_y1 = ota2['out']
    draw_via1(top, layout, lp_x1, lp_y1)
    lp_route_y = ota_y - 2.5
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, lp_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_y1 + wire_w2/2))
    # LP → C_int2
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, c2_top[1] - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # Summing node: SC_R1 output + SC_R2 output → OTA1 input
    sum_x, sum_y = ota1['inp']
    draw_via1(top, layout, sum_x, sum_y)

    # LP feedback: route LP to OTA1 negative input via M2
    fb_x, fb_y = ota1['inn']
    draw_via1(top, layout, fb_x, fb_y)
    fb_route_y = ota_y - 4.0
    top.shapes(li_m2).insert(rect(min(fb_x, lp_x1) - wire_w2/2, fb_route_y - wire_w2/2,
                                   max(fb_x, lp_x1) + wire_w2/2, fb_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(fb_x - wire_w2/2, fb_route_y - wire_w2/2,
                                   fb_x + wire_w2/2, fb_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, fb_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # =====================================================================
    # Analog Mux routing
    # =====================================================================
    # Route mux inputs from filter nodes (using M2)
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

    # HP → mux.hp_in (HP derived from vin - LP - Q*BP, route from vin area)
    hp_mux_x, hp_mux_y = mux['hp_in']
    draw_via1(top, layout, hp_mux_x, hp_mux_y)

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y≈36 ---
    vin_pin_y = 36.0
    vin_ota_x, vin_ota_y = ota1['inp']
    draw_via1(top, layout, vin_ota_x, vin_ota_y)
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_ota_y + wire_w2/2))

    # Route vin to bypass mux input
    bypass_mux_x, bypass_mux_y = mux['bypass_in']
    draw_via1(top, layout, bypass_mux_x, bypass_mux_y)
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_mux_y - wire_w2/2,
                                   bypass_mux_x + wire_w2/2, bypass_mux_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_mux_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))

    # --- vout pin: right edge, y≈36 ---
    vout_pin_y = 36.0
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

    # --- sel[0] pin: left edge, y≈10 ---
    sel0_pin_y = 10.0
    top.shapes(li_m2).insert(rect(0.0, sel0_pin_y - wire_w2/2,
                                   mux['hp_gate'][0] + wire_w2/2, sel0_pin_y + wire_w2/2))

    # --- sel[1] pin: left edge, y≈16 ---
    sel1_pin_y = 16.0
    top.shapes(li_m2).insert(rect(0.0, sel1_pin_y - wire_w2/2,
                                   mux['bp_gate'][0] + wire_w2/2, sel1_pin_y + wire_w2/2))

    # --- sc_clk pin: left edge, y≈52 ---
    # Route via1 to left of NOL generator (clear of internal M1 drain wires)
    sc_clk_pin_y = 52.0
    nol_clk_y = nol['clk_in'][1]
    via_clk_x = nol_x - 1.5  # offset left to clear drain M1
    via_clk_y = nol_clk_y
    draw_via1(top, layout, via_clk_x, via_clk_y)
    # M2 from pin to via1
    top.shapes(li_m2).insert(rect(0.0, sc_clk_pin_y - wire_w2/2,
                                   via_clk_x + wire_w2/2, sc_clk_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(via_clk_x - wire_w2/2,
                                   min(sc_clk_pin_y, via_clk_y) - wire_w2/2,
                                   via_clk_x + wire_w2/2,
                                   max(sc_clk_pin_y, via_clk_y) + wire_w2/2))

    # --- q0..q3 pins: left edge, y≈56,58,60,62 ---
    q_pin_ys = [56.0, 58.0, 60.0, 62.0]
    q_names = ['q0', 'q1', 'q2', 'q3']
    for i, (qpy, qname) in enumerate(zip(q_pin_ys, q_names)):
        top.shapes(li_m2).insert(rect(0.0, qpy - wire_w2/2,
                                       6.0, qpy + wire_w2/2))

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
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, q_pin_ys[0] - 1.0, 0.5, q_pin_ys[0] + 1.0), "q0", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, q_pin_ys[1] - 1.0, 0.5, q_pin_ys[1] + 1.0), "q1", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, q_pin_ys[2] - 1.0, 0.5, q_pin_ys[2] + 1.0), "q2", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, q_pin_ys[3] - 1.0, 0.5, q_pin_ys[3] + 1.0), "q3", layout)
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
    print(f"  Switching caps: 2 × {C_SW*1000:.1f} fF (MIM {C_SW_SIDE}×{C_SW_SIDE} µm)")
    print(f"  C_Q array: 4-bit binary-weighted ({CQ_UNIT_SIDE}µm unit)")
    print(f"  CMOS switches: 4 (N: W={SW_N_W}µm L={SW_N_L}µm, P: W={SW_P_W}µm L={SW_P_L}µm)")
    print(f"  NOL clock: 8 transistors (4 CMOS pairs)")
    print(f"  Mux: 4 × NMOS W={MUX_W}µm L={MUX_L}µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
