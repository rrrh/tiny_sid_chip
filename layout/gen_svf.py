#!/usr/bin/env python3
"""
Generate 2nd-order gm-C State Variable Filter layout for IHP SG13G2 130nm.

Architecture:
  Vin ──→ [Summing OTA1] ──→ HP ──→ [Integrator OTA2] ──→ BP ──→ [Integrator OTA3] ──→ LP
                ↑                                                                        │
                ├────────────────────── feedback ────────────────────────────────────────┘
                │
          [Damping OTA4] ←── BP    (Q = gm_int / gm_damp)

  ibias_fc → fc bias mirror → tails for OTA1/2/3 (sets fc = gm/(2πC))
  ibias_q  → q bias mirror  → tail for OTA4      (sets Q)

  4:1 Analog Mux selects LP/BP/HP/bypass → Vout

Components:
  4 × OTA (5-transistor simple diff pair each)
  2 × MIM cap (1 pF each, ~25.8 × 25.8 µm)
  4 × NMOS pass gate (analog mux with sel[1:0])
  2 × Bias circuit (NMOS current mirrors: fc mirror + q mirror)

Macro size: 70 × 85 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 70.0
MACRO_H = 85.0

# OTA transistor sizes
OTA_DP_W  = 4.0    # NMOS diff pair width (µm)
OTA_DP_L  = 0.50   # diff pair length (longer L for matching)
OTA_LD_W  = 2.0    # PMOS load width
OTA_LD_L  = 0.50   # PMOS load length
OTA_TAIL_W = 2.0   # NMOS tail width
OTA_TAIL_L = 0.50  # tail length

# MIM integration caps
C_INT      = 1.0           # pF per integrator
C_INT_AREA = C_INT * 1000 / MIM_CAP_DENSITY  # ~666.7 µm²
C_INT_SIDE = 25.8          # µm (25.8² ≈ 665.6 µm² → ~1.0 pF)

# Mux pass gates
MUX_W = 2.0
MUX_L = 0.13

# Bias mirror
BIAS_W = 2.0
BIAS_L = 1.0   # long L for accuracy


# ===========================================================================
# Transistor drawing helpers (reuse patterns from gen_sar_adc)
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
    li_tm1  = layout.layer(*L_TOPMETAL1)

    cell.shapes(li_cmim).insert(rect(x, y, x + w, y + h))
    enc = MIM_ENC_M5
    cell.shapes(li_m5).insert(rect(x - enc, y - enc, x + w + enc, y + h + enc))
    cell.shapes(li_tm1).insert(rect(x - 0.1, y - 0.1, x + w + 0.1, y + h + 0.1))

    bot_center = (x + w / 2, y - enc)
    top_center = (x + w / 2, y + h + 0.1)
    return bot_center, top_center


# ===========================================================================
# Block-level drawing functions
# ===========================================================================

def draw_ota(cell, layout, x, y):
    """
    Draw a 5-transistor OTA (simple differential pair with current mirror load).

    Topology:
        VDD ─── M3(PMOS) ─┬─ M4(PMOS) ─── VDD
                  drain    │    drain
                    │      │      │
                    ├──────┘      │
                    │             │
                  drain         drain
        Vinp ── M1(NMOS)   M2(NMOS) ── Vinn
                  source      source
                    │           │
                    └─────┬─────┘
                          │
                        drain
                       M5(NMOS) ── tail current
                        source
                          │
                         VSS

    Returns dict with pin centers and bounding box.
    """
    dp_gap = 1.5

    sd_ext_n = CONT_SIZE + 2 * CONT_ENC_ACTIV
    dp_act_len = sd_ext_n + OTA_DP_L + sd_ext_n
    ld_act_len = sd_ext_n + OTA_LD_L + sd_ext_n
    tail_act_len = sd_ext_n + OTA_TAIL_L + sd_ext_n

    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    # --- M5: Tail current source (NMOS) ---
    tail_x = x + (dp_act_len * 2 + dp_gap - tail_act_len) / 2
    m5 = draw_nmos(cell, layout, tail_x, y, w=OTA_TAIL_W, l=OTA_TAIL_L)

    # --- M1, M2: Differential pair (NMOS) ---
    dp_y = y + OTA_TAIL_W + 2.0
    m1 = draw_nmos(cell, layout, x, dp_y, w=OTA_DP_W, l=OTA_DP_L)
    m2 = draw_nmos(cell, layout, x + dp_act_len + dp_gap, dp_y, w=OTA_DP_W, l=OTA_DP_L)

    # --- M3, M4: PMOS current mirror load ---
    ld_y = dp_y + OTA_DP_W + 2.5
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

    # --- M1 routing ---
    # M1 source and M2 source to M5 drain
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


def draw_bias(cell, layout, x, y):
    """
    Draw bias current mirror: 2 NMOS transistors (diode-connected + mirror).
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + BIAS_L + sd_ext

    gap = 1.0
    m_ref = draw_nmos(cell, layout, x, y, w=BIAS_W, l=BIAS_L)
    m_mir = draw_nmos(cell, layout, x + act_len + gap, y, w=BIAS_W, l=BIAS_L)

    # Diode-connect M_ref: gate to drain
    cell.shapes(li_m1).insert(rect(m_ref['gate'][0] - wire_w/2,
                                    min(m_ref['gate'][1], m_ref['drain'][1]) - wire_w/2,
                                    m_ref['gate'][0] + wire_w/2,
                                    max(m_ref['gate'][1], m_ref['drain'][1]) + wire_w/2))
    cell.shapes(li_m1).insert(rect(m_ref['drain'][0] - wire_w/2, m_ref['gate'][1] - wire_w/2,
                                    m_ref['gate'][0] + wire_w/2, m_ref['gate'][1] + wire_w/2))

    # Connect gates
    cell.shapes(li_m1).insert(rect(m_ref['gate'][0] - wire_w/2, m_ref['gate'][1] - wire_w/2,
                                    m_mir['gate'][0] + wire_w/2, m_ref['gate'][1] + wire_w/2))

    total_w = 2 * act_len + gap

    return {
        'ref_drain': m_ref['drain'],
        'mir_drain': m_mir['drain'],
        'ref_gate':  m_ref['gate'],
        'ref_source': m_ref['source'],
        'mir_source': m_mir['source'],
        'total_w': total_w,
    }


def draw_analog_mux(cell, layout, x, y):
    """
    Draw 4:1 analog mux using 4 NMOS pass gates.
    sel[1:0] decode: 00=LP, 01=BP, 10=HP, 11=bypass
    Returns dict with pin centers.
    """
    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    wire_w = M1_WIDTH

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + MUX_L + sd_ext

    sw_pitch = MUX_W + 1.5

    switches = []
    names = ['lp', 'bp', 'hp', 'bypass']
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
        'lp_in':     switches[0]['source'],
        'bp_in':     switches[1]['source'],
        'hp_in':     switches[2]['source'],
        'bypass_in': switches[3]['source'],
        'lp_gate':   switches[0]['gate'],
        'bp_gate':   switches[1]['gate'],
        'hp_gate':   switches[2]['gate'],
        'bypass_gate': switches[3]['gate'],
        'out':       switches[0]['drain'],
        'total_h':   total_h,
        'act_len':   act_len,
    }


# ===========================================================================
# Main: build the SVF
# ===========================================================================
def build_svf():
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
    #   y=6..28    : Analog mux + output routing
    #   y=30..56   : MIM caps (C1 at y=30, C2 at y=30 shifted right)
    #   y=57..63   : Dual bias circuits (fc mirror left, q mirror right)
    #   y=63..83   : OTA row (4 OTAs side by side, ~18µm tall)
    #   y=83..85   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 4 OTAs side by side (summing, int1, int2, damping)
    # =====================================================================
    ota_y = 63.0
    ota_gap = 2.5

    ota_sum = draw_ota(top, layout, x=2.0, y=ota_y)
    ota1_x = 2.0 + ota_sum['total_w'] + ota_gap
    ota_int1 = draw_ota(top, layout, x=ota1_x, y=ota_y)
    ota2_x = ota1_x + ota_int1['total_w'] + ota_gap
    ota_int2 = draw_ota(top, layout, x=ota2_x, y=ota_y)
    ota_damp_x = ota2_x + ota_int2['total_w'] + ota_gap
    ota_damp = draw_ota(top, layout, x=ota_damp_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via2 to M3
    for ota in [ota_sum, ota_int1, ota_int2, ota_damp]:
        for vdd_pin in ['vdd_l', 'vdd_r']:
            px, py = ota[vdd_pin]
            top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                          px + wire_w/2, MACRO_H - 2.5))
            draw_via1(top, layout, px, MACRO_H - 2.5)
            draw_via2(top, layout, px, MACRO_H - 1.0)

    # Connect OTA VSS (tail source) to VSS rail
    for ota in [ota_sum, ota_int1, ota_int2, ota_damp]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        top.shapes(li_m2).insert(rect(px - wire_w2/2, 2.5,
                                       px + wire_w2/2, py))
        draw_via2(top, layout, px, 1.0)

    # =====================================================================
    # Dual bias circuits (fc mirror left, q mirror right)
    # =====================================================================
    bias_y = 57.0

    # fc bias mirror (left) — drives OTA1/2/3 tails
    bias_fc_x = 2.0
    bias_fc = draw_bias(top, layout, bias_fc_x, bias_y)

    # q bias mirror (right) — drives OTA4 (damping) tail
    bias_q_x = bias_fc_x + bias_fc['total_w'] + 2.0
    bias_q = draw_bias(top, layout, bias_q_x, bias_y)

    # Connect fc bias mirror drain to OTA1/2/3 tail gates via M1 horizontal bus
    fc_bus_y = bias_fc['mir_drain'][1]
    bx_fc = bias_fc['mir_drain'][0]
    rightmost_fc_tail_x = ota_int2['tail'][0]
    top.shapes(li_m1).insert(rect(bx_fc - wire_w/2, fc_bus_y - wire_w/2,
                                   rightmost_fc_tail_x + wire_w/2, fc_bus_y + wire_w/2))
    for ota in [ota_sum, ota_int1, ota_int2]:
        tx, ty = ota['tail']
        top.shapes(li_m1).insert(rect(tx - wire_w/2, fc_bus_y - wire_w/2,
                                       tx + wire_w/2, ty + wire_w/2))

    # Connect q bias mirror drain to OTA4 (damping) tail gate
    q_bus_y = bias_q['mir_drain'][1]
    bx_q = bias_q['mir_drain'][0]
    damp_tail_x = ota_damp['tail'][0]
    top.shapes(li_m1).insert(rect(bx_q - wire_w/2, q_bus_y - wire_w/2,
                                   damp_tail_x + wire_w/2, q_bus_y + wire_w/2))
    # Vertical tap to OTA4 tail gate
    tx, ty = ota_damp['tail']
    top.shapes(li_m1).insert(rect(tx - wire_w/2, q_bus_y - wire_w/2,
                                   tx + wire_w/2, ty + wire_w/2))

    # Bias sources to VSS
    for bias in [bias_fc, bias_q]:
        for src in [bias['ref_source'], bias['mir_source']]:
            sx, sy = src
            draw_via1(top, layout, sx, sy)
            top.shapes(li_m2).insert(rect(sx - wire_w2/2, 2.5,
                                           sx + wire_w2/2, sy))
            draw_via2(top, layout, sx, 1.0)

    # =====================================================================
    # MIM Integration Caps (C1 and C2, side by side)
    # =====================================================================
    cap_y = 30.0
    c1_x = 3.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # =====================================================================
    # SVF signal routing (M2 layer for inter-block connections)
    # =====================================================================

    # HP node: OTA_sum output → OTA_int1 input
    hp_x1, hp_y1 = ota_sum['out']
    hp_x2, hp_y2 = ota_int1['inp']
    draw_via1(top, layout, hp_x1, hp_y1)
    draw_via1(top, layout, hp_x2, hp_y2)
    hp_route_y = ota_y - 1.0
    top.shapes(li_m2).insert(rect(hp_x1 - wire_w2/2, hp_route_y - wire_w2/2,
                                   hp_x1 + wire_w2/2, hp_y1 + wire_w2/2))
    top.shapes(li_m2).insert(rect(hp_x1 - wire_w2/2, hp_route_y - wire_w2/2,
                                   hp_x2 + wire_w2/2, hp_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(hp_x2 - wire_w2/2, hp_route_y - wire_w2/2,
                                   hp_x2 + wire_w2/2, hp_y2 + wire_w2/2))

    # BP node: OTA_int1 output → C1 top plate + OTA_int2 input
    bp_x1, bp_y1 = ota_int1['out']
    bp_x2, bp_y2 = ota_int2['inp']
    draw_via1(top, layout, bp_x1, bp_y1)
    draw_via1(top, layout, bp_x2, bp_y2)
    bp_route_y = ota_y - 2.5
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_y1 + wire_w2/2))
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(bp_x2 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x2 + wire_w2/2, bp_y2 + wire_w2/2))
    # BP → C1
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, c1_top[1] - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_route_y + wire_w2/2))

    # LP node: OTA_int2 output → C2 top plate + feedback to OTA_sum.inn
    lp_x1, lp_y1 = ota_int2['out']
    fb_x, fb_y = ota_sum['inn']
    draw_via1(top, layout, lp_x1, lp_y1)
    draw_via1(top, layout, fb_x, fb_y)
    lp_route_y = ota_y - 4.0
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, lp_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_y1 + wire_w2/2))
    top.shapes(li_m2).insert(rect(min(fb_x, lp_x1) - wire_w2/2, lp_route_y - wire_w2/2,
                                   max(fb_x, lp_x1) + wire_w2/2, lp_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(fb_x - wire_w2/2, lp_route_y - wire_w2/2,
                                   fb_x + wire_w2/2, fb_y + wire_w2/2))
    # LP → C2
    top.shapes(li_m2).insert(rect(lp_x1 - wire_w2/2, c2_top[1] - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_route_y + wire_w2/2))

    # Damping OTA4: inp=BP, inn=HP, out feeds back to summing node
    # Route BP → OTA4.inp
    damp_inp_x, damp_inp_y = ota_damp['inp']
    draw_via1(top, layout, damp_inp_x, damp_inp_y)
    damp_bp_route_y = ota_y - 2.5  # same level as BP route
    top.shapes(li_m2).insert(rect(damp_inp_x - wire_w2/2, damp_bp_route_y - wire_w2/2,
                                   damp_inp_x + wire_w2/2, damp_inp_y + wire_w2/2))
    # Extend BP route to OTA4.inp
    top.shapes(li_m2).insert(rect(bp_x2 - wire_w2/2, damp_bp_route_y - wire_w2/2,
                                   damp_inp_x + wire_w2/2, damp_bp_route_y + wire_w2/2))

    # Route HP → OTA4.inn (negative feedback reference)
    damp_inn_x, damp_inn_y = ota_damp['inn']
    draw_via1(top, layout, damp_inn_x, damp_inn_y)
    damp_hp_route_y = ota_y - 1.0  # same level as HP route
    top.shapes(li_m2).insert(rect(damp_inn_x - wire_w2/2, damp_hp_route_y - wire_w2/2,
                                   damp_inn_x + wire_w2/2, damp_inn_y + wire_w2/2))
    # Extend HP route to OTA4.inn
    top.shapes(li_m2).insert(rect(hp_x2 - wire_w2/2, damp_hp_route_y - wire_w2/2,
                                   damp_inn_x + wire_w2/2, damp_hp_route_y + wire_w2/2))

    # Route OTA4 output → summing node (OTA_sum output / HP node)
    damp_out_x, damp_out_y = ota_damp['out']
    draw_via1(top, layout, damp_out_x, damp_out_y)
    damp_out_route_y = ota_y - 5.5
    top.shapes(li_m2).insert(rect(damp_out_x - wire_w2/2, damp_out_route_y - wire_w2/2,
                                   damp_out_x + wire_w2/2, damp_out_y + wire_w2/2))
    # Route horizontally to HP node x position
    top.shapes(li_m2).insert(rect(min(hp_x1, damp_out_x) - wire_w2/2,
                                   damp_out_route_y - wire_w2/2,
                                   max(hp_x1, damp_out_x) + wire_w2/2,
                                   damp_out_route_y + wire_w2/2))
    # Connect down to HP route
    top.shapes(li_m2).insert(rect(hp_x1 - wire_w2/2, damp_out_route_y - wire_w2/2,
                                   hp_x1 + wire_w2/2, hp_route_y + wire_w2/2))

    # =====================================================================
    # Analog Mux (bottom region)
    # =====================================================================
    mux_x = 42.0
    mux_y = 6.0
    mux = draw_analog_mux(top, layout, mux_x, mux_y)

    # Route mux inputs from filter nodes (using M2)
    # LP → mux.lp_in
    lp_mux_x, lp_mux_y = mux['lp_in']
    draw_via1(top, layout, lp_mux_x, lp_mux_y)
    lp_tap_y = mux['lp_in'][1]
    top.shapes(li_m2).insert(rect(c2_x + C_INT_SIDE / 2 - wire_w2/2, lp_tap_y - wire_w2/2,
                                   lp_mux_x + wire_w2/2, lp_tap_y + wire_w2/2))

    # BP → mux.bp_in
    bp_mux_x, bp_mux_y = mux['bp_in']
    draw_via1(top, layout, bp_mux_x, bp_mux_y)
    bp_tap_y = mux['bp_in'][1]
    top.shapes(li_m2).insert(rect(c1_x + C_INT_SIDE / 2 - wire_w2/2, bp_tap_y - wire_w2/2,
                                   bp_mux_x + wire_w2/2, bp_tap_y + wire_w2/2))

    # HP → mux.hp_in
    hp_mux_x, hp_mux_y = mux['hp_in']
    draw_via1(top, layout, hp_mux_x, hp_mux_y)
    hp_tap_y = mux['hp_in'][1]
    hp_src_x = ota_sum['out'][0]
    top.shapes(li_m2).insert(rect(min(hp_src_x, hp_mux_x) - wire_w2/2, hp_tap_y - wire_w2/2,
                                   max(hp_src_x, hp_mux_x) + wire_w2/2, hp_tap_y + wire_w2/2))

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y≈42 ---
    vin_pin_y = 42.0
    vin_ota_x, vin_ota_y = ota_sum['inp']
    draw_via1(top, layout, vin_ota_x, vin_ota_y)
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_ota_y + wire_w2/2))

    # Also route vin to bypass mux input
    bypass_mux_x, bypass_mux_y = mux['bypass_in']
    draw_via1(top, layout, bypass_mux_x, bypass_mux_y)
    bypass_tap_y = mux['bypass_in'][1]
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_tap_y - wire_w2/2,
                                   bypass_mux_x + wire_w2/2, bypass_tap_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_tap_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))

    # --- vout pin: right edge, y≈42 ---
    vout_pin_y = 42.0
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
                                   mux['lp_gate'][0] + wire_w2/2, sel0_pin_y + wire_w2/2))

    # --- sel[1] pin: left edge, y≈16 ---
    sel1_pin_y = 16.0
    top.shapes(li_m2).insert(rect(0.0, sel1_pin_y - wire_w2/2,
                                   mux['bp_gate'][0] + wire_w2/2, sel1_pin_y + wire_w2/2))

    # --- ibias_fc pin: left edge, y≈60 ---
    ibias_fc_pin_y = 60.0
    # Route from pin to fc bias ref drain via M2
    fc_ref_x, fc_ref_y = bias_fc['ref_drain']
    draw_via1(top, layout, fc_ref_x, fc_ref_y)
    top.shapes(li_m2).insert(rect(0.0, ibias_fc_pin_y - wire_w2/2,
                                   fc_ref_x + wire_w2/2, ibias_fc_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(fc_ref_x - wire_w2/2,
                                   min(ibias_fc_pin_y, fc_ref_y) - wire_w2/2,
                                   fc_ref_x + wire_w2/2,
                                   max(ibias_fc_pin_y, fc_ref_y) + wire_w2/2))

    # --- ibias_q pin: left edge, y≈66 ---
    ibias_q_pin_y = 66.0
    q_ref_x, q_ref_y = bias_q['ref_drain']
    draw_via1(top, layout, q_ref_x, q_ref_y)
    top.shapes(li_m2).insert(rect(0.0, ibias_q_pin_y - wire_w2/2,
                                   q_ref_x + wire_w2/2, ibias_q_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(q_ref_x - wire_w2/2,
                                   min(ibias_q_pin_y, q_ref_y) - wire_w2/2,
                                   q_ref_x + wire_w2/2,
                                   max(ibias_q_pin_y, q_ref_y) + wire_w2/2))

    # =====================================================================
    # Pin labels
    # =====================================================================
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, vin_pin_y - 2.0, 0.5, vin_pin_y + 2.0), "vin", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 2.0, MACRO_W, vout_pin_y + 2.0),
                  "vout", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, sel0_pin_y - 1.0, 0.5, sel0_pin_y + 1.0), "sel[0]", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, sel1_pin_y - 1.0, 0.5, sel1_pin_y + 1.0), "sel[1]", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, ibias_fc_pin_y - 1.0, 0.5, ibias_fc_pin_y + 1.0),
                  "ibias_fc", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, ibias_q_pin_y - 1.0, 0.5, ibias_q_pin_y + 1.0),
                  "ibias_q", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H), "vdd", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 2.0), "vss", layout)

    # =====================================================================
    # Boundary
    # =====================================================================
    li_bnd = layout.layer(0, 0)
    top.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout, top


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "svf_2nd.gds")

    layout, top = build_svf()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  OTAs: 4 × 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Integration caps: 2 × {C_INT} pF (MIM {C_INT_SIDE}×{C_INT_SIDE} µm)")
    print(f"  Mux: 4 × NMOS W={MUX_W}µm L={MUX_L}µm")
    print(f"  Bias: 2 × NMOS mirror (fc + q) W={BIAS_W}µm L={BIAS_L}µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
