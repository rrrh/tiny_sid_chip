#!/usr/bin/env python3
"""
Generate PWM Comparator layout for IHP SG13G2 130nm.

Architecture:
  vinp ──→ [OTA: 5-transistor diff pair] ──→ [CMOS Inverter] ──→ out
  vinn ──↗

Components:
  1 × OTA (5 transistors): NMOS diff pair (W=4u L=0.5u),
     PMOS mirror (W=2u L=0.5u), NMOS tail (W=2u L=0.5u)
  1 × CMOS inverter (2 transistors): NMOS W=0.5u L=0.13u,
     PMOS W=1u L=0.13u — sharpens OTA output to rail-to-rail

Total: 7 transistors
Macro size: 12 × 15 µm
Pins: vinp, vinn, out, vdd, vss
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 12.0
MACRO_H = 15.0

# OTA transistor sizes
OTA_DP_W  = 4.0    # NMOS diff pair width (µm)
OTA_DP_L  = 0.50   # diff pair length
OTA_LD_W  = 2.0    # PMOS load width
OTA_LD_L  = 0.50   # PMOS load length
OTA_TAIL_W = 2.0   # NMOS tail width
OTA_TAIL_L = 0.50  # tail length

# Inverter sizes
INV_N_W = 0.50
INV_N_L = 0.13
INV_P_W = 1.00
INV_P_L = 0.13


# ===========================================================================
# Transistor drawing helpers (same as gen_sc_svf.py)
# ===========================================================================

def draw_nmos(cell, layout, x, y, w, l):
    """Draw NMOS transistor (no nSD, no pSD), return pin centers dict."""
    li_act = layout.layer(*L_ACTIV)
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = SD_EXT
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


def draw_gate_contact(cell, layout, gate_x, gate_y, l, side='above'):
    """Add Contact + M1 pad on GatPoly extension for gate connection.
    Extends poly if needed. Only for L >= 0.32µm gates.
    Returns (m1_cx, m1_cy)."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    margin = 0.14  # Cnt.e: min Cont on GatPoly space to Activ = 0.14µm

    if side == 'above':
        activ_top = gate_y - GATPOLY_EXT
        cnt_bot = activ_top + margin
        cnt_cy = cnt_bot + CONT_SIZE / 2
        poly_top = cnt_bot + CONT_SIZE + CONT_ENC_GATPOLY
        if poly_top > gate_y:
            cell.shapes(li_gp).insert(rect(gate_x - l / 2, gate_y,
                                            gate_x + l / 2, poly_top))
    else:  # below
        activ_bot = gate_y + GATPOLY_EXT
        cnt_top = activ_bot - margin
        cnt_cy = cnt_top - CONT_SIZE / 2
        poly_bot = cnt_top - CONT_SIZE - CONT_ENC_GATPOLY
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


# ===========================================================================
# OTA builder (same topology as gen_sc_svf.py)
# ===========================================================================
def draw_ota(cell, layout, x, y):
    """
    Draw a 5-transistor OTA.
    Returns dict with pin centers.
    """
    dp_gap = 1.4  # increased from 1.3 to fix M1.b between dp source wire and tail drain pad
    sd_ext = SD_EXT
    dp_act_len = sd_ext + OTA_DP_L + sd_ext
    ld_act_len = sd_ext + OTA_LD_L + sd_ext
    tail_act_len = sd_ext + OTA_TAIL_L + sd_ext

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
    cell.shapes(li_nw).insert(rect(nw_x1, ld_y - nw_enc,
                                    nw_x2, ld_y + OTA_LD_W + nw_enc))

    m3 = draw_pmos(cell, layout, x, ld_y, w=OTA_LD_W, l=OTA_LD_L, draw_nwell=False)
    m4 = draw_pmos(cell, layout, x + dp_act_len + dp_gap, ld_y,
                   w=OTA_LD_W, l=OTA_LD_L, draw_nwell=False)

    # Gate contacts — place on OUTER sides to avoid M1.b with drain wires
    m5_gate_x = m5['gate'][0]
    m5['gate'] = draw_gate_contact(cell, layout, m5_gate_x, y - GATPOLY_EXT,
                                    l=OTA_TAIL_L, side='below')
    m1_gate_x = m1['gate'][0]
    m1['gate'] = draw_gate_contact(cell, layout, m1_gate_x, dp_y - GATPOLY_EXT,
                                    l=OTA_DP_L, side='below')
    m2_gate_x = m2['gate'][0]
    m2['gate'] = draw_gate_contact(cell, layout, m2_gate_x, dp_y - GATPOLY_EXT,
                                    l=OTA_DP_L, side='below')
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
    tail_route_y = y + OTA_TAIL_W + 0.7  # above tail, clear of drain M1 pad
    # Vertical M1 from each diff pair source down to tail route y
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m1['source'][0] + wire_w/2, m1['source'][1] + wire_w/2))
    cell.shapes(li_m1).insert(rect(m2['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m2['source'][0] + wire_w/2, m2['source'][1] + wire_w/2))
    # Horizontal M1 at tail route y connecting both sources
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, tail_route_y - wire_w/2,
                                    m2['source'][0] + wire_w/2, tail_route_y + wire_w/2))
    # Vertical M1 from tail route y down to tail drain (avoids tail source)
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
        'inp':      m1['gate'],
        'inn':      m2['gate'],
        'out':      m4['drain'],
        'tail':     m5['gate'],
        'tail_drn': m5['drain'],
        'vdd_l':    m3['source'],
        'vdd_r':    m4['source'],
        'vss':      m5['source'],
        'bbox':     (x, y, x + total_w, y + total_h),
        'total_w':  total_w,
        'total_h':  total_h,
    }


# ===========================================================================
# Main: build the PWM comparator
# ===========================================================================
def build_pwm_comp():
    layout = new_layout()
    top = layout.create_cell("pwm_comp")

    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)

    wire_w  = M1_WIDTH
    wire_w2 = M2_WIDTH

    # =====================================================================
    # Layout plan (bottom to top):
    #   y=0..2     : VSS rail (Metal3)
    #   y=2..13    : OTA (5 transistors)
    #   y=2..5     : CMOS inverter (2 transistors, right side)
    #   y=13..15   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA (5 transistors)
    # NW.b1: OTA PMOS NWell must be >= 1.8µm from macro left edge
    # =====================================================================
    ota_x = NWELL_SPACE_DN + NWELL_ENC_ACTIV + 0.12  # 2.23µm (extra margin for neighbor NWell)
    ota_y = 2.5
    ota = draw_ota(top, layout, x=ota_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via1+M2+via2 to M3
    for vdd_pin in ['vdd_l', 'vdd_r']:
        px, py = ota[vdd_pin]
        top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                       px + wire_w/2, MACRO_H - 2.5))
        draw_via1(top, layout, px, MACRO_H - 2.5)
        draw_via2(top, layout, px, MACRO_H - 1.0)
        # M2 connecting Via1 to Via2
        top.shapes(li_m2).insert(rect(px - wire_w2/2, MACRO_H - 2.5 - wire_w2/2,
                                       px + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # Connect OTA VSS (tail source) to VSS rail via M3
    px, py = ota['vss']
    draw_via1(top, layout, px, py)
    draw_via2(top, layout, px, py)
    # Extend M3 to merge with VSS rail (avoid gap)
    top.shapes(li_m3).insert(rect(px - wire_w2/2, 0.0,
                                   px + wire_w2/2, py + wire_w2/2))

    # Self-bias: connect tail gate to drain (diode-connected)
    tx, ty = ota['tail']
    dx, dy = ota['tail_drn']
    # Horizontal M1 from gate contact to drain x at gate y
    top.shapes(li_m1).insert(rect(min(tx, dx) - wire_w/2, ty - wire_w/2,
                                   max(tx, dx) + wire_w/2, ty + wire_w/2))
    # Vertical M1 from gate y down to drain y at drain x
    top.shapes(li_m1).insert(rect(dx - wire_w/2, min(ty, dy) - wire_w/2,
                                   dx + wire_w/2, max(ty, dy) + wire_w/2))

    # =====================================================================
    # CMOS Inverter (2 transistors) — sharpens OTA output to rail-to-rail
    # NW.b1: inverter PMOS NWell must be >= 1.8µm from macro right edge
    # NWell right = inv_x + inv_act_len + NWELL_ENC_ACTIV
    # Need: MACRO_W - NWell_right >= NWELL_SPACE_DN
    # inv_x <= MACRO_W - NWELL_SPACE_DN - NWELL_ENC_ACTIV - inv_act_len
    # =====================================================================
    sd_ext = SD_EXT
    inv_act_len = sd_ext + INV_N_L + sd_ext  # 0.89µm

    inv_x = MACRO_W - NWELL_SPACE_DN - NWELL_ENC_ACTIV - inv_act_len - 0.02  # ~8.81
    inv_n_y = 2.5  # NMOS

    # Place PMOS close: GatPoly bridges the gap (no M1 needed for gate connect)
    # Activ gap >= 0.21µm (Act.b) but poly extensions overlap/bridge
    inv_p_y = inv_n_y + INV_N_W + 0.32  # gap must be >= PSD_ENC_GATE(0.30) to avoid pSD overlap

    inv_n = draw_nmos(top, layout, inv_x, inv_n_y, w=INV_N_W, l=INV_N_L)
    inv_p = draw_pmos(top, layout, inv_x, inv_p_y, w=INV_P_W, l=INV_P_L)

    # Connect NMOS drain to PMOS drain (inverter output) via M1 vertical
    top.shapes(li_m1).insert(rect(inv_n['drain'][0] - wire_w/2, inv_n['drain'][1] - wire_w/2,
                                   inv_n['drain'][0] + wire_w/2, inv_p['drain'][1] + wire_w/2))

    # Connect NMOS gate to PMOS gate via GatPoly bridge
    gp_x1 = inv_x + sd_ext  # gate poly left edge
    gp_bridge_bot = inv_n_y + INV_N_W + GATPOLY_EXT
    gp_bridge_top = inv_p_y - GATPOLY_EXT
    if gp_bridge_top > gp_bridge_bot:
        top.shapes(li_gp).insert(rect(gp_x1, gp_bridge_bot,
                                       gp_x1 + INV_N_L, gp_bridge_top))

    # Extend GatPoly below NMOS for gate contact
    # Extra 0.05µm extension to increase M2 via pad gap between gate via1 and drain via1
    gp_ext_below = CONT_ENC_GATPOLY + CONT_SIZE + CONT_ENC_GATPOLY + 0.05  # 0.37µm
    gp_bottom = inv_n_y - gp_ext_below
    top.shapes(li_gp).insert(rect(gp_x1, gp_bottom,
                                   gp_x1 + INV_N_L, inv_n_y - GATPOLY_EXT))

    # Gate contact on the extended poly below NMOS (lowered for M2 pad clearance)
    gate_cnt_x = gp_x1 + INV_N_L / 2 - CONT_SIZE / 2
    gate_cnt_y = inv_n_y - GATPOLY_EXT - CONT_ENC_GATPOLY - CONT_SIZE - 0.05
    top.shapes(li_cnt).insert(rect(gate_cnt_x, gate_cnt_y,
                                    gate_cnt_x + CONT_SIZE, gate_cnt_y + CONT_SIZE))
    # M1 pad for gate contact
    top.shapes(li_m1).insert(rect(gate_cnt_x - CONT_ENC_M1, gate_cnt_y - CONT_ENC_M1,
                                   gate_cnt_x + CONT_SIZE + CONT_ENC_M1,
                                   gate_cnt_y + CONT_SIZE + CONT_ENC_M1))
    gate_m1_cx = gate_cnt_x + CONT_SIZE / 2
    gate_m1_cy = gate_cnt_y + CONT_SIZE / 2

    # NMOS source → VSS: route M1 left to avoid gate contact, then via stack to M3 VSS
    ns_x, ns_y = inv_n['source']
    # Route M1 left from source to a via point well away from gate contact and drain
    vss_via_x = inv_x - 1.5  # well left of inverter, clear of gate contact
    vss_via_y = ns_y  # keep at same y as source for simple horizontal route
    # Horizontal M1 from source to via point
    top.shapes(li_m1).insert(rect(vss_via_x - wire_w/2, ns_y - wire_w/2,
                                   ns_x + wire_w/2, ns_y + wire_w/2))
    draw_via1(top, layout, vss_via_x, vss_via_y)
    draw_via2(top, layout, vss_via_x, vss_via_y)
    top.shapes(li_m3).insert(rect(vss_via_x - wire_w2/2, 0.0,
                                   vss_via_x + wire_w2/2, vss_via_y + wire_w2/2))

    # PMOS source → VDD via M1 vertical + via1+via2 to M3
    # Via1 must be ≥ M2.b (0.21µm) below OTA output M2 route (which is at ota_out_y)
    ps_x, ps_y = inv_p['source']
    inv_via1_y = MACRO_H - 2.8  # lowered from MACRO_H-2.5 to avoid M2 pad conflict with OTA M2 route
    top.shapes(li_m1).insert(rect(ps_x - wire_w/2, ps_y - wire_w/2,
                                   ps_x + wire_w/2, inv_via1_y))
    draw_via1(top, layout, ps_x, inv_via1_y)
    draw_via2(top, layout, ps_x, MACRO_H - 1.0)
    # M2 connecting Via1 to Via2
    top.shapes(li_m2).insert(rect(ps_x - wire_w2/2, inv_via1_y - wire_w2/2,
                                   ps_x + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # =====================================================================
    # Signal routing: OTA output → inverter gate
    # Route on M2 via an offset x to avoid M2.b with vinn via pad
    # M2 vertical runs at x = MACRO_W/2 (= 6.0), safely right of vinn M2 pads
    # =====================================================================
    ota_out_x, ota_out_y = ota['out']
    m2_route_x = 6.5  # offset right to clear OTA output via1 M2 pad notch (right edge 6.155)

    # Via1 at OTA output
    draw_via1(top, layout, ota_out_x, ota_out_y)

    # Via1 at gate contact (below inverter NMOS)
    draw_via1(top, layout, gate_m1_cx, gate_m1_cy)

    # M2: horizontal at ota_out_y from OTA output to m2_route_x
    top.shapes(li_m2).insert(rect(ota_out_x - wire_w2/2, ota_out_y - wire_w2/2,
                                   m2_route_x + wire_w2/2, ota_out_y + wire_w2/2))
    # M2: vertical at m2_route_x from ota_out_y down to gate_m1_cy
    top.shapes(li_m2).insert(rect(m2_route_x - wire_w2/2,
                                   min(gate_m1_cy, ota_out_y) - wire_w2/2,
                                   m2_route_x + wire_w2/2,
                                   max(gate_m1_cy, ota_out_y) + wire_w2/2))
    # M2: horizontal at gate_m1_cy from m2_route_x to gate contact
    top.shapes(li_m2).insert(rect(m2_route_x - wire_w2/2, gate_m1_cy - wire_w2/2,
                                   gate_m1_cx + wire_w2/2, gate_m1_cy + wire_w2/2))

    # =====================================================================
    # Substrate taps
    # =====================================================================
    # ptap near OTA NMOS — connect to VSS M3 rail via via1+via2
    for ptap_x in [2.2, 5.0]:
        draw_ptap(top, layout, ptap_x, 2.0)
        # ptap M1 center
        ptap_cx = ptap_x + 0.18
        ptap_cy = 2.0 + 0.18
        draw_via1(top, layout, ptap_cx, ptap_cy)
        draw_via2(top, layout, ptap_cx, ptap_cy)

    # ntap inside OTA PMOS NWell (same NWell region → no NW.b1)
    ota_ld_y = ota_y + OTA_TAIL_W + 1.5 + OTA_DP_W + 2.0
    # Place ntap between M3 and M4 in the shared PMOS NWell
    ntap_ota_x = ota_x + 1.5
    ntap_ota_y = ota_ld_y + 0.2
    draw_ntap(top, layout, ntap_ota_x, ntap_ota_y)
    # Connect OTA ntap to VDD via via1+M2+via2 to M3 rail
    ntap_ota_cx = ntap_ota_x + 0.18  # ntap M1 center x
    ntap_ota_cy = ntap_ota_y + 0.18  # ntap M1 center y
    draw_via1(top, layout, ntap_ota_cx, ntap_ota_cy)
    draw_via2(top, layout, ntap_ota_cx, MACRO_H - 1.0)
    top.shapes(li_m2).insert(rect(ntap_ota_cx - wire_w2/2, ntap_ota_cy - wire_w2/2,
                                   ntap_ota_cx + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # ntap above inverter PMOS (inside NWell but outside transistor Activ)
    gp_top = inv_p_y + INV_P_W + GATPOLY_EXT
    ntap_inv_y = gp_top + 0.14 + CONT_SIZE/2 + 0.05
    draw_ntap(top, layout, inv_x + 0.2, ntap_inv_y)
    # Connect inverter ntap M1 to inverter PMOS source M1 wire (VDD)
    ntap_inv_cx = inv_x + 0.2 + 0.18  # ntap M1 center x
    ntap_inv_cy = ntap_inv_y + 0.18   # ntap M1 center y
    top.shapes(li_m1).insert(rect(ps_x - wire_w/2, ntap_inv_cy - wire_w/2,
                                   ntap_inv_cx + wire_w/2, ntap_inv_cy + wire_w/2))

    # =====================================================================
    # Pin routing and labels
    # =====================================================================

    # --- vinp pin: left edge, y≈5 ---
    # Route via M3 vertical to avoid crossing vinn M2 horizontal at y=9
    vinp_pin_y = 5.0
    vinp_gate_x, vinp_gate_y = ota['inp']
    draw_via1(top, layout, vinp_gate_x, vinp_gate_y)
    # Via2 at gate to go up to M3
    draw_via2(top, layout, vinp_gate_x, vinp_gate_y)
    # M3 vertical from gate y down to pin y
    top.shapes(li_m3).insert(rect(vinp_gate_x - wire_w2/2,
                                   vinp_pin_y - wire_w2/2,
                                   vinp_gate_x + wire_w2/2,
                                   vinp_gate_y + wire_w2/2))
    # Via2 at pin y to come back to M2
    draw_via2(top, layout, vinp_gate_x, vinp_pin_y)
    # M2 horizontal from via2 to left edge for pin
    top.shapes(li_m2).insert(rect(0.0, vinp_pin_y - wire_w2/2,
                                   vinp_gate_x + wire_w2/2, vinp_pin_y + wire_w2/2))

    # --- vinn pin: left edge, y≈9 ---
    vinn_pin_y = 9.0
    vinn_gate_x, vinn_gate_y = ota['inn']
    draw_via1(top, layout, vinn_gate_x, vinn_gate_y)
    top.shapes(li_m2).insert(rect(0.0, vinn_pin_y - wire_w2/2,
                                   vinn_gate_x + wire_w2/2, vinn_pin_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vinn_gate_x - wire_w2/2,
                                   min(vinn_pin_y, vinn_gate_y) - wire_w2/2,
                                   vinn_gate_x + wire_w2/2,
                                   max(vinn_pin_y, vinn_gate_y) + wire_w2/2))

    # --- out pin: right edge, y≈7 ---
    out_pin_y = 7.0
    inv_out_x, inv_out_y = inv_n['drain']
    draw_via1(top, layout, inv_out_x, inv_out_y)
    top.shapes(li_m2).insert(rect(inv_out_x - wire_w2/2, out_pin_y - wire_w2/2,
                                   MACRO_W, out_pin_y + wire_w2/2))
    if abs(inv_out_y - out_pin_y) > 0.1:
        top.shapes(li_m2).insert(rect(inv_out_x - wire_w2/2,
                                       min(inv_out_y, out_pin_y) - wire_w2/2,
                                       inv_out_x + wire_w2/2,
                                       max(inv_out_y, out_pin_y) + wire_w2/2))

    # =====================================================================
    # Pin labels
    # =====================================================================
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, vinp_pin_y - 0.5, 0.5, vinp_pin_y + 0.5), "vinp", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, vinn_pin_y - 0.5, 0.5, vinn_pin_y + 0.5), "vinn", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, out_pin_y - 0.5, MACRO_W, out_pin_y + 0.5),
                  "out", layout)
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
    outpath = os.path.join(outdir, "pwm_comp.gds")

    layout, top = build_pwm_comp()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  OTA: 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Inverter: NMOS W={INV_N_W}µm L={INV_N_L}µm, PMOS W={INV_P_W}µm L={INV_P_L}µm")
    print(f"  Total: 7 transistors")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
