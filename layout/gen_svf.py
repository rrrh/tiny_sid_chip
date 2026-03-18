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

Macro size: 62 × 80 µm
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *

# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 62.0
MACRO_H = 80.0

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
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)

    sd_ext = CONT_SIZE + 2 * CONT_ENC_ACTIV
    act_len = sd_ext + l + sd_ext

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))

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

    # Offset gate contact 0.10µm beyond GatPoly extension for Cnt.e clearance
    # (contact on GatPoly must be >= 0.14µm from Activ; 0.18+0.10-0.08 = 0.20 > 0.14)
    gc_offset = 0.10
    return {
        'gate':   (gp_x1 + l / 2, y + w + GATPOLY_EXT + gc_offset),
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

    # Offset gate contact 0.10µm beyond GatPoly extension for Cnt.e clearance
    gc_offset = 0.10
    return {
        'gate':   (gp_x1 + l / 2, y - GATPOLY_EXT - gc_offset),
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


def draw_gate_contact(cell, layout, x, y):
    """Place contact + M1 pad on GatPoly at (x,y) for gate connection."""
    li_gp  = layout.layer(*L_GATPOLY)
    li_cnt = layout.layer(*L_CONT)
    li_m1  = layout.layer(*L_METAL1)
    hs = CONT_SIZE / 2
    gp_enc = CONT_ENC_GATPOLY
    cell.shapes(li_gp).insert(rect(x - hs - gp_enc, y - hs - gp_enc,
                                     x + hs + gp_enc, y + hs + gp_enc))
    cell.shapes(li_cnt).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e = CONT_ENC_M1
    cell.shapes(li_m1).insert(rect(x - hs - e, y - hs - e, x + hs + e, y + hs + e))


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
    """TopVia1 with M5+TM1 pads. TM1 pad enforces min width 1.64µm."""
    li_tv1 = layout.layer(*L_TOPVIA1)
    li_m5  = layout.layer(*L_METAL5)
    li_tm1 = layout.layer(*L_TOPMETAL1)
    hs = TOPVIA1_SIZE / 2
    cell.shapes(li_tv1).insert(rect(x - hs, y - hs, x + hs, y + hs))
    e5 = TOPVIA1_ENC_M5 + hs
    cell.shapes(li_m5).insert(rect(x - e5, y - e5, x + e5, y + e5))
    # TM1 min width = 1.64µm; ensure pad is at least that
    TM1_MIN_HALF = 1.64 / 2
    et = max(TOPVIA1_ENC_TM1 + hs, TM1_MIN_HALF)
    cell.shapes(li_tm1).insert(rect(x - et, y - et, x + et, y + et))


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
    dp_gap = 2.5   # was 1.5; increased for M1.b clearance between diff pair halves

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
    ld_y = dp_y + OTA_DP_W + 3.0  # DP-to-load gap (bias now on M2, so 3.0 is ample for M1.b)
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
    # Connect diff pair sources to M5 drain, AVOIDING M5 source (= VSS).
    # M5 source (left) and drain (right) contacts are at same y, so a straight
    # horizontal bar would short diff pair common source to VSS.
    # Route left diff pair source via a jog BELOW M5 source contact.
    jog_y = m5['drain'][1] - 0.5  # 0.5µm below contact center (clears pad + M1.b)
    # Left diff pair source vertical: down to jog_y
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, jog_y - wire_w/2,
                                    m1['source'][0] + wire_w/2, m1['source'][1] + wire_w/2))
    # Horizontal jog below M5 source: left diff pair to M5 drain x
    cell.shapes(li_m1).insert(rect(m1['source'][0] - wire_w/2, jog_y - wire_w/2,
                                    m5['drain'][0] + wire_w/2, jog_y + wire_w/2))
    # Vertical from jog up to M5 drain
    cell.shapes(li_m1).insert(rect(m5['drain'][0] - wire_w/2, jog_y - wire_w/2,
                                    m5['drain'][0] + wire_w/2, m5['drain'][1] + wire_w/2))
    # Right half: M5 drain to right diff pair source (no M5 source in this range)
    cell.shapes(li_m1).insert(rect(m5['drain'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m2['source'][0] + wire_w/2, m5['drain'][1] + wire_w/2))
    # Right diff pair source vertical
    cell.shapes(li_m1).insert(rect(m2['source'][0] - wire_w/2, m5['drain'][1] - wire_w/2,
                                    m2['source'][0] + wire_w/2, m2['source'][1] + wire_w/2))

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

    # Gate contacts (Bug 1 fix)
    for m in [m1, m2, m5]:      # NMOS gates (top of GatPoly ext)
        draw_gate_contact(cell, layout, m['gate'][0], m['gate'][1])
    for m in [m3, m4]:           # PMOS gates (bottom of GatPoly ext)
        draw_gate_contact(cell, layout, m['gate'][0], m['gate'][1])

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
    # Vertical from gate_x at drain_y up to gate_y
    cell.shapes(li_m1).insert(rect(m_ref['gate'][0] - wire_w/2,
                                    min(m_ref['gate'][1], m_ref['drain'][1]) - wire_w/2,
                                    m_ref['gate'][0] + wire_w/2,
                                    max(m_ref['gate'][1], m_ref['drain'][1]) + wire_w/2))
    # Horizontal from gate_x to drain_x at drain_y (NOT gate_y — must reach drain pad!)
    cell.shapes(li_m1).insert(rect(min(m_ref['drain'][0], m_ref['gate'][0]) - wire_w/2,
                                    m_ref['drain'][1] - wire_w/2,
                                    max(m_ref['drain'][0], m_ref['gate'][0]) + wire_w/2,
                                    m_ref['drain'][1] + wire_w/2))

    # Connect gates
    cell.shapes(li_m1).insert(rect(m_ref['gate'][0] - wire_w/2, m_ref['gate'][1] - wire_w/2,
                                    m_mir['gate'][0] + wire_w/2, m_ref['gate'][1] + wire_w/2))

    # Gate contacts (Bug 1 fix)
    draw_gate_contact(cell, layout, m_ref['gate'][0], m_ref['gate'][1])
    draw_gate_contact(cell, layout, m_mir['gate'][0], m_mir['gate'][1])

    total_w = 2 * act_len + gap

    return {
        'ref_drain': m_ref['drain'],
        'mir_drain': m_mir['drain'],
        'ref_gate':  m_ref['gate'],
        'mir_gate':  m_mir['gate'],
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

    # Gate contacts offset to left of mux to avoid M1 spacing with drain bus
    gc_x = x - 1.5  # well left of active area
    li_gp = layout.layer(*L_GATPOLY)
    gp_x1 = x + sd_ext  # gate poly left edge

    gate_contacts = []
    for i in range(4):
        sy = y + i * sw_pitch
        sw = draw_nmos(cell, layout, x, sy, w=MUX_W, l=MUX_L)
        # GatPoly bridge from offset contact to gate
        gc_y = sw['gate'][1]
        hs_gp = CONT_SIZE / 2 + CONT_ENC_GATPOLY
        cell.shapes(li_gp).insert(rect(gc_x - hs_gp, gc_y - hs_gp,
                                         gp_x1 + MUX_L, gc_y + hs_gp))
        draw_gate_contact(cell, layout, gc_x, gc_y)
        gate_contacts.append((gc_x, gc_y))
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
        'lp_gate':   gate_contacts[0],
        'bp_gate':   gate_contacts[1],
        'hp_gate':   gate_contacts[2],
        'bypass_gate': gate_contacts[3],
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
    hw2 = wire_w2 / 2

    # =====================================================================
    # Layout plan (bottom to top):
    #   y=0..2     : VSS rail (Metal3)
    #   y=6..28    : Analog mux + output routing
    #   y=30..56   : MIM caps (C1 at y=30, C2 at y=30 shifted right)
    #   y=57..61   : Dual bias circuits (fc mirror left, q mirror right)
    #   y=64..77   : OTA row (4 OTAs side by side, ~13µm tall)
    #   y=78..80   : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 4 OTAs side by side (summing, int1, int2, damping)
    # =====================================================================
    ota_y = 64.0    # OTA base y (bias at 57, routes at 58.5-63)
    ota_gap = 3.0   # gap between adjacent OTAs (bias on M2 eliminates M1 conflicts)

    ota_sum = draw_ota(top, layout, x=2.0, y=ota_y)
    ota1_x = 2.0 + ota_sum['total_w'] + ota_gap
    ota_int1 = draw_ota(top, layout, x=ota1_x, y=ota_y)
    ota2_x = ota1_x + ota_int1['total_w'] + ota_gap
    ota_int2 = draw_ota(top, layout, x=ota2_x, y=ota_y)
    ota_damp_x = ota2_x + ota_int2['total_w'] + ota_gap
    ota_damp = draw_ota(top, layout, x=ota_damp_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via2 to M3
    # Stagger via1/via2 y-positions (left=MACRO_H-2.0, right=MACRO_H-1.4) for M2.b clearance
    for ota in [ota_sum, ota_int1, ota_int2, ota_damp]:
        for idx, vdd_pin in enumerate(['vdd_l', 'vdd_r']):
            px, py = ota[vdd_pin]
            via1_y = MACRO_H - 2.0 if idx == 0 else MACRO_H - 1.4
            via2_y = via1_y + 0.5
            top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                          px + wire_w/2, via1_y))
            draw_via1(top, layout, px, via1_y)
            top.shapes(li_m2).insert(rect(px - wire_w2/2, via1_y,
                                          px + wire_w2/2, via2_y))
            draw_via2(top, layout, px, via2_y)

    # Connect OTA VSS (tail source) to VSS rail via M3 vertical
    # (was M2 vertical, but crossed every horizontal M2 signal route)
    li_m4 = layout.layer(*L_METAL4)
    # Signal M3 routes that VSS M3 columns must bridge over:
    #   HP @y=63.0, BP @y=62.5, LP @y=62.0, damp_out @y=61.5 (all from signal routing)
    #   BP_mux @y=55.9, LP_mux @y=57.0 (from mux routing below)
    #   q_bias_bus @y=58.0 (handled separately in q_bias code)
    # Multiple crossings per column are close together, so use a single M4 bridge
    # spanning from below the lowest crossing to above the highest.
    # Each entry: (lowest_cross_y, highest_cross_y) — None if no crossings
    vss_bridge_spans = {
        'ota_sum':  None,                    # x=3.98: no signal M3 routes cross here
        'ota_int1': (61.5, 63.0),            # x=11.76: damp_out(61.5), LP(62.0), HP(63.0)
        'ota_int2': (55.9, 63.0),            # x=19.54: BP_mux(55.9)...HP(63.0)
        'ota_damp': (55.9, 63.0),            # x=27.32: BP_mux(55.9)...HP(63.0)
    }
    v3_offset = 0.52  # via3 placed this far from outermost crossing
    for ota, key in [(ota_sum, 'ota_sum'), (ota_int1, 'ota_int1'),
                     (ota_int2, 'ota_int2'), (ota_damp, 'ota_damp')]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        draw_via2(top, layout, px, py)
        span = vss_bridge_spans[key]
        if span is None:
            # No crossings — continuous M3 from VSS rail to OTA source
            top.shapes(li_m3).insert(rect(px - hw2, 0.0, px + hw2, py + hw2))
        else:
            lo, hi = span
            y_bot_v3 = lo - v3_offset  # via3 below lowest crossing
            y_top_v3 = hi + v3_offset  # via3 above highest crossing
            # M3 segment: OTA source down to top via3
            top.shapes(li_m3).insert(rect(px - hw2, y_top_v3, px + hw2, py + hw2))
            # M3 segment: bottom via3 down to VSS rail
            top.shapes(li_m3).insert(rect(px - hw2, 0.0, px + hw2, y_bot_v3))
            # Via3 pair + M4 bridge
            draw_via3(top, layout, px, y_top_v3)
            draw_via3(top, layout, px, y_bot_v3)
            top.shapes(li_m4).insert(rect(px - hw2, y_bot_v3 - 0.195,
                                           px + hw2, y_top_v3 + 0.195))

    # =====================================================================
    # Dual bias circuits (fc mirror left, q mirror right)
    # =====================================================================
    bias_y = 57.0

    # fc bias mirror (left) — drives OTA1/2/3 tails
    bias_fc_x = 2.0
    bias_fc = draw_bias(top, layout, bias_fc_x, bias_y)

    # q bias mirror (right) — drives OTA4 (damping) tail
    # Gap 2.5 (was 2.0) so q mir_drain via1 clears OTA_sum tail via1 (V1.b, M1.b)
    bias_q_x = bias_fc_x + bias_fc['total_w'] + 2.5
    bias_q = draw_bias(top, layout, bias_q_x, bias_y)

    # Connect fc bias GATE to OTA1/2/3 tail gates via M3 horizontal bus
    # The gate bar (M1) connects ref_gate to mir_gate. Via diode, ref_gate = ref_drain.
    # Tap the gate bar at ota_sum tail x (via1 connects gate bar M1 to tail M2 stub).
    rightmost_fc_tail_x = ota_int2['tail'][0] # 19.95
    fc_bus_m3_y = 59.0  # M3 bus y-level
    fc_gate_bar_y = bias_fc['ref_gate'][1]    # gate bar y (59.28)
    # M3 horizontal bus at y=59 from leftmost to rightmost tail
    # M3 crossings: ota_int1 VSS column (x=11.76), BP→C1 vertical (x=bp_x1=14.40)
    leftmost_fc_tail_x = ota_sum['tail'][0]   # 4.39
    fc_m3_crossings = [ota_int1['vss'][0], ota_int1['out'][0]]  # 11.76, 14.40 (BP vert)
    fc_gap = 0.52
    fc_segs = [leftmost_fc_tail_x - hw2]
    for cross_x in sorted(fc_m3_crossings):
        seg_end = cross_x - fc_gap
        seg_start_after = cross_x + fc_gap
        top.shapes(li_m3).insert(rect(fc_segs[-1], fc_bus_m3_y - hw2,
                                       seg_end, fc_bus_m3_y + hw2))
        draw_via3(top, layout, seg_end, fc_bus_m3_y)
        draw_via3(top, layout, seg_start_after, fc_bus_m3_y)
        top.shapes(li_m4).insert(rect(seg_end - 0.195, fc_bus_m3_y - hw2,
                                       seg_start_after + 0.195, fc_bus_m3_y + hw2))
        fc_segs.append(seg_start_after)
    # Final segment to rightmost tail
    top.shapes(li_m3).insert(rect(fc_segs[-1], fc_bus_m3_y - hw2,
                                   rightmost_fc_tail_x + hw2, fc_bus_m3_y + hw2))
    # Connect each OTA tail gate to fc_bus M3:
    # tail gate (M1) → via1 at gate → M2 stub down to fc_bus_m3_y → via2 → M3 bus
    # (Can't use M1 from y=58 to gate — would cross OTA source bar at y=65)
    for ota in [ota_sum, ota_int1, ota_int2]:
        tx, ty = ota['tail']
        draw_via1(top, layout, tx, ty)  # via1 at tail gate position
        top.shapes(li_m2).insert(rect(tx - wire_w2/2, fc_bus_m3_y - wire_w2/2,
                                       tx + wire_w2/2, ty + wire_w2/2))
        draw_via2(top, layout, tx, fc_bus_m3_y)
    # Tap fc bias gate bar: via1 at ota_sum tail x connects gate bar M1 to tail M2 stub
    draw_via1(top, layout, ota_sum['tail'][0], fc_gate_bar_y)

    # Connect q bias GATE to OTA4 (damping) tail gate via M3
    # Can't tap gate bar at mir_gate x=12.24 — its M2 stub would overlap ota_int1 tail
    # M2 stub (x=12.17, only 0.07µm away, M2 width=0.20µm).
    # Tap at x=11.0 instead (between ref_source x=8.94 and mir_source x=11.58).
    q_gate_bar_y = bias_q['ref_gate'][1]  # 59.28 (gate bar M1 y)
    q_bus_y = 58.0  # M3 bus y-level
    q_tap_x = 11.0  # tap position on gate bar M1
    damp_tail_x = ota_damp['tail'][0] # 27.73
    # Tap q bias gate bar: via1 at tap_x connects gate bar M1 to M2
    draw_via1(top, layout, q_tap_x, q_gate_bar_y)
    # M2 stub from gate bar down to q_bus_y
    top.shapes(li_m2).insert(rect(q_tap_x - wire_w2/2, q_bus_y - wire_w2/2,
                                   q_tap_x + wire_w2/2, q_gate_bar_y + wire_w2/2))
    draw_via2(top, layout, q_tap_x, q_bus_y)
    # M3 horizontal from q_tap_x to damp_tail_x at y=58, with M4 bridges over crossings
    # Crossings: VSS columns + signal M3 verticals (BP→C1 at bp_x1, LP→C2 at lp_x1)
    # Only bridge M3 verticals that are present at y=58:
    # ota_int1 VSS (x=11.76): bridge span (61.5,63.0) → M3 present at y=58 ✓
    # ota_int2 VSS (x=19.54): bridge span (55.9,63.0) → M3 absent at y=58 (gap) — SKIP
    # ota_damp VSS (x=27.32): bridge span (55.9,63.0) → M3 absent at y=58 (gap) — SKIP
    # BP→C1 (x=14.40): M3 from y≈55.9 to 62.5 → present at y=58 ✓
    # LP→C2 (x=22.18): M3 from y≈55.9 to 62.0 → present at y=58 ✓
    q_bus_m3_crossings = [ota_int1['vss'][0], ota_int1['out'][0],  # 11.76, 14.40
                          ota_int2['out'][0]]                      # 22.18
    q_bus_segs = [q_tap_x - hw2]  # start of first segment
    for vss_x in sorted(q_bus_m3_crossings):
        seg_end = vss_x - 0.52  # gap before VSS column
        seg_start_after = vss_x + 0.52  # gap after VSS column
        top.shapes(li_m3).insert(rect(q_bus_segs[-1], q_bus_y - hw2,
                                       seg_end, q_bus_y + hw2))
        draw_via3(top, layout, seg_end, q_bus_y)
        draw_via3(top, layout, seg_start_after, q_bus_y)
        top.shapes(li_m4).insert(rect(seg_end - 0.195, q_bus_y - hw2,
                                       seg_start_after + 0.195, q_bus_y + hw2))
        q_bus_segs.append(seg_start_after)
    # Final M3 segment to damp_tail_x
    top.shapes(li_m3).insert(rect(q_bus_segs[-1], q_bus_y - hw2,
                                   damp_tail_x + hw2, q_bus_y + hw2))
    # Connect M3 bus to OTA4 tail gate via M2 stub (NOT M1 — M1 would cross source bar)
    tx, ty = ota_damp['tail']
    draw_via1(top, layout, tx, ty)       # via1 at tail gate position
    top.shapes(li_m2).insert(rect(tx - wire_w2/2, q_bus_y - wire_w2/2,
                                   tx + wire_w2/2, ty + wire_w2/2))  # M2 stub down to bus
    draw_via2(top, layout, tx, q_bus_y)  # via2 to connect M2 stub to M3 bus

    # Bias sources to VSS via M3 vertical (was M2 vertical, crossed signal routes)
    for bias in [bias_fc, bias_q]:
        for i, src in enumerate([bias['ref_source'], bias['mir_source']]):
            sx, sy = src
            draw_via1(top, layout, sx, sy)
            # Place via2 0.5µm below source to avoid M2 clearance with damp_out M2 at y=58.5
            via2_y = sy - 0.5
            top.shapes(li_m2).insert(rect(sx - wire_w2/2, via2_y,
                                           sx + wire_w2/2, sy))
            draw_via2(top, layout, sx, via2_y)
            # M3 vertical from via2 down to VSS M3 rail
            top.shapes(li_m3).insert(rect(sx - hw2, 0.0, sx + hw2, via2_y + hw2))

    # =====================================================================
    # Substrate taps (LU.b: pSD-PWell tie within 20µm of NMOS)
    # =====================================================================
    # Along OTA NMOS region — place 2µm below OTA base for Cnt.b clearance
    # (tails at y=ota_y, diff pairs at y=ota_y+4; ptaps must be >0.5µm from contacts)
    ptap_ota_y = ota_y - 2.0
    for xt in [2.0, 10.0, 18.0, 26.0, 34.0, 42.0, 50.0]:
        draw_ptap(top, layout, xt, ptap_ota_y)
    # Along bias mirror region — place 1µm below bias_y for clearance
    ptap_bias_y = bias_y - 1.5
    for xt in [2.0, 8.0, 14.0, 20.0]:
        draw_ptap(top, layout, xt, ptap_bias_y)
    # Near mux NMOS switches (x=42, y=6-20)
    draw_ptap(top, layout, 41.0, 4.5)
    draw_ptap(top, layout, 41.0, 12.2)   # was 12.0; moved +0.2 for Gat.d clearance from mux GatPoly
    draw_ptap(top, layout, 41.0, 19.2)   # was 19.0; moved +0.2 for Gat.d clearance from mux GatPoly

    # =====================================================================
    # MIM Integration Caps (C1 and C2, side by side)
    # =====================================================================
    cap_y = 30.0
    c1_x = 3.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # --- MIM cap via stacks (Bug 4 fix) ---
    # C1 top plate: via stack at BP M2 route intersection (bp_x1 set later,
    # use ota_int1 output x which equals bp_x1)
    c1_top_via_x = ota_int1['out'][0]  # bp_x1
    draw_via_stack_m2_to_tm1(top, layout, c1_top_via_x, c1_top[1])

    # C1 bottom plate → VSS via M3
    draw_via_stack_m2_to_m5(top, layout, c1_bot[0], c1_bot[1])
    top.shapes(li_m3).insert(rect(c1_bot[0] - hw2, 0.0,
                                   c1_bot[0] + hw2, c1_bot[1] + hw2))

    # C2 top plate: via stack just inside c2 TM1
    c2_top_via_x = c2_x + 1.0
    draw_via_stack_m2_to_tm1(top, layout, c2_top_via_x, c2_top[1])

    # C2 bottom plate → VSS via M3
    draw_via_stack_m2_to_m5(top, layout, c2_bot[0], c2_bot[1])
    top.shapes(li_m3).insert(rect(c2_bot[0] - hw2, 0.0,
                                   c2_bot[0] + hw2, c2_bot[1] + hw2))

    # =====================================================================
    # SVF signal routing
    # Architecture: M3 horizontal buses at distinct y-levels between OTAs.
    # M2 vertical stubs connect OTA pins (via1) to M3 buses (via2).
    # This prevents same-layer crossings in the congested y=57-63 zone.
    # =====================================================================

    # Pin coordinates
    hp_x1, hp_y1 = ota_sum['out']       # (6.62, 76.0)
    hp_x2, hp_y2 = ota_int1['inp']      # (10.35, 72.28)
    bp_x1, bp_y1 = ota_int1['out']      # (14.40, 76.0)
    bp_x2, bp_y2 = ota_int2['inp']      # (18.13, 72.28)
    lp_x1, lp_y1 = ota_int2['out']      # (22.18, 76.0)
    fb_x, fb_y = ota_sum['inn']          # (6.21, 72.28)
    damp_inp_x, damp_inp_y = ota_damp['inp']  # (25.91, 72.28)
    damp_inn_x, damp_inn_y = ota_damp['inn']  # (29.55, 72.28)
    damp_out_x, damp_out_y = ota_damp['out']  # (29.96, 76.0)

    # via1 at all OTA pins (M1→M2)
    for px, py in [(hp_x1, hp_y1), (hp_x2, hp_y2), (bp_x1, bp_y1), (bp_x2, bp_y2),
                   (lp_x1, lp_y1), (fb_x, fb_y), (damp_inp_x, damp_inp_y),
                   (damp_inn_x, damp_inn_y), (damp_out_x, damp_out_y)]:
        draw_via1(top, layout, px, py)

    # M3 horizontal bus y-levels (each signal at a distinct y, ≥0.21µm apart for M3.b)
    hp_route_y = 63.0    # HP bus
    bp_route_y = 62.5    # BP bus (was 61.5, moved up so all buses fit above bias zone)
    lp_route_y = 62.0    # LP bus (was 60.0)
    damp_out_route_y = 61.5  # damp_out bus (was 58.5)
    # All buses between y=61.5 and y=63.0, safely above bias M2 @y=58 and ibias @y=60/62

    # === HP bus: M3 at y=63, from hp_x1(6.62) to damp_inn_x(29.55) ===
    # M2 stubs: each OTA pin drops from via1 on M1 to via2 transition at y=63
    for px, py in [(hp_x1, hp_y1), (hp_x2, hp_y2), (damp_inn_x, damp_inn_y)]:
        top.shapes(li_m2).insert(rect(px - wire_w2/2, hp_route_y - wire_w2/2,
                                       px + wire_w2/2, py + wire_w2/2))
        draw_via2(top, layout, px, hp_route_y)
    top.shapes(li_m3).insert(rect(hp_x1 - hw2, hp_route_y - hw2,
                                   damp_inn_x + hw2, hp_route_y + hw2))

    # === BP bus: M3 at y=62.5, from bp_x1(14.40) to damp_inp_x(25.91) ===
    for px, py in [(bp_x1, bp_y1), (bp_x2, bp_y2), (damp_inp_x, damp_inp_y)]:
        top.shapes(li_m2).insert(rect(px - wire_w2/2, bp_route_y - wire_w2/2,
                                       px + wire_w2/2, py + wire_w2/2))
        draw_via2(top, layout, px, bp_route_y)
    top.shapes(li_m3).insert(rect(bp_x1 - hw2, bp_route_y - hw2,
                                   damp_inp_x + hw2, bp_route_y + hw2))
    # BP → C1: M3 vertical from bp_route_y down to C1 top plate
    top.shapes(li_m3).insert(rect(bp_x1 - hw2, c1_top[1] - hw2,
                                   bp_x1 + hw2, bp_route_y + hw2))
    draw_via2(top, layout, bp_x1, c1_top[1])

    # === LP bus: M3 at y=62.0, from fb_x(6.21) to lp_x1(22.18) ===
    for px, py in [(fb_x, fb_y), (lp_x1, lp_y1)]:
        top.shapes(li_m2).insert(rect(px - wire_w2/2, lp_route_y - wire_w2/2,
                                       px + wire_w2/2, py + wire_w2/2))
        draw_via2(top, layout, px, lp_route_y)
    top.shapes(li_m3).insert(rect(fb_x - hw2, lp_route_y - hw2,
                                   lp_x1 + hw2, lp_route_y + hw2))
    # LP → C2: M3 vertical from lp_route_y down to C2 top plate
    top.shapes(li_m3).insert(rect(lp_x1 - hw2, c2_top[1] - hw2,
                                   lp_x1 + hw2, lp_route_y + hw2))
    draw_via2(top, layout, lp_x1, c2_top[1])
    # M2 horizontal from lp_x1 via2 to c2 via stack at C2 top plate
    top.shapes(li_m2).insert(rect(min(lp_x1, c2_top_via_x) - wire_w2/2,
                                   c2_top[1] - wire_w2/2,
                                   max(lp_x1, c2_top_via_x) + wire_w2/2,
                                   c2_top[1] + wire_w2/2))

    # === Damp_out bus: M3 at y=61.5, from hp_x1(6.62) to damp_out_x(29.96) ===
    # OTA4.out connects back to HP node (summing junction)
    for px, py in [(damp_out_x, damp_out_y)]:
        top.shapes(li_m2).insert(rect(px - wire_w2/2, damp_out_route_y - wire_w2/2,
                                       px + wire_w2/2, py + wire_w2/2))
        draw_via2(top, layout, px, damp_out_route_y)
    # hp_x1 end: via2 to connect damp_out M3 bus to HP M3 bus above
    draw_via2(top, layout, hp_x1, damp_out_route_y)
    top.shapes(li_m2).insert(rect(hp_x1 - wire_w2/2, damp_out_route_y - wire_w2/2,
                                   hp_x1 + wire_w2/2, hp_route_y + wire_w2/2))
    top.shapes(li_m3).insert(rect(hp_x1 - hw2, damp_out_route_y - hw2,
                                   damp_out_x + hw2, damp_out_route_y + hw2))

    # =====================================================================
    # Analog Mux (bottom region)
    # =====================================================================
    mux_x = 42.0
    mux_y = 6.0
    mux = draw_analog_mux(top, layout, mux_x, mux_y)

    # Route mux inputs via separate M3 vertical columns at different x offsets
    # (was M2 verticals all at x=42.16, causing LP/BP/HP M2 overlap + LP/BP M3 merge)
    # Each mux source → M2 jog → via2 → M3 vertical → signal M3 route

    # LP M3 at y=57.0 (offset from BP M3 at y=55.9 to avoid merge)
    lp_m3_y = 57.0
    lp_jog_x = 43.5   # M3 vertical x for LP mux input
    lp_mux_x, lp_mux_y = mux['lp_in']
    draw_via1(top, layout, lp_mux_x, lp_mux_y)
    # M2 jog from mux source to offset x
    top.shapes(li_m2).insert(rect(lp_mux_x - wire_w2/2, lp_mux_y - wire_w2/2,
                                   lp_jog_x + wire_w2/2, lp_mux_y + wire_w2/2))
    draw_via2(top, layout, lp_jog_x, lp_mux_y)
    # M3 vertical from mux source y up to LP M3 route y
    top.shapes(li_m3).insert(rect(lp_jog_x - hw2, lp_mux_y, lp_jog_x + hw2, lp_m3_y + hw2))
    # LP signal via2 at LP M3 y (connects LP M2 to LP M3 route)
    lp_sig_x = lp_x1  # OTA_int2 output x
    draw_via2(top, layout, lp_sig_x, lp_m3_y)
    # M2 from LP M2 at c2_top y up to LP M3 via2 at y=57.0
    top.shapes(li_m2).insert(rect(lp_sig_x - wire_w2/2, c2_top[1] - wire_w2/2,
                                   lp_sig_x + wire_w2/2, lp_m3_y + wire_w2/2))
    # LP M3 horizontal connecting signal via2 to mux M3 vertical
    top.shapes(li_m3).insert(rect(min(lp_sig_x, lp_jog_x) - hw2, lp_m3_y - hw2,
                                   max(lp_sig_x, lp_jog_x) + hw2, lp_m3_y + hw2))

    # BP M3 at y=55.9 (same as c1_top[1])
    bp_jog_x = 45.5   # M3 vertical x for BP mux input
    bp_mux_x, bp_mux_y = mux['bp_in']
    draw_via1(top, layout, bp_mux_x, bp_mux_y)
    top.shapes(li_m2).insert(rect(bp_mux_x - wire_w2/2, bp_mux_y - wire_w2/2,
                                   bp_jog_x + wire_w2/2, bp_mux_y + wire_w2/2))
    draw_via2(top, layout, bp_jog_x, bp_mux_y)
    bp_sig_y = c1_top[1]
    top.shapes(li_m3).insert(rect(bp_jog_x - hw2, bp_mux_y, bp_jog_x + hw2, bp_sig_y + hw2))
    bp_sig_x = bp_x1  # OTA_int1 output x
    # Note: via2 at (bp_sig_x, bp_sig_y) already placed by C1 top plate via stack
    top.shapes(li_m3).insert(rect(min(bp_sig_x, bp_jog_x) - hw2, bp_sig_y - hw2,
                                   max(bp_sig_x, bp_jog_x) + hw2, bp_sig_y + hw2))

    # HP M3 at y=63.0 (hp_route_y)
    hp_jog_x = 47.5   # M3 vertical x for HP mux input
    hp_mux_x, hp_mux_y = mux['hp_in']
    draw_via1(top, layout, hp_mux_x, hp_mux_y)
    top.shapes(li_m2).insert(rect(hp_mux_x - wire_w2/2, hp_mux_y - wire_w2/2,
                                   hp_jog_x + wire_w2/2, hp_mux_y + wire_w2/2))
    draw_via2(top, layout, hp_jog_x, hp_mux_y)
    hp_sig_y = hp_route_y
    top.shapes(li_m3).insert(rect(hp_jog_x - hw2, hp_mux_y, hp_jog_x + hw2, hp_sig_y + hw2))
    hp_sig_x = hp_x1  # OTA_sum output x
    draw_via2(top, layout, hp_sig_x, hp_sig_y)
    top.shapes(li_m3).insert(rect(min(hp_sig_x, hp_jog_x) - hw2, hp_sig_y - hw2,
                                   max(hp_sig_x, hp_jog_x) + hw2, hp_sig_y + hw2))

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y≈42 ---
    # vin vertical crosses ibias_fc @y=60 and ibias_q @y=62 on M2.
    # Fix: M2 from pin/bypass up to y=57, then via2→M3 up to OTA gate at y=72.28.
    vin_pin_y = 42.0
    vin_ota_x, vin_ota_y = ota_sum['inp']
    draw_via1(top, layout, vin_ota_x, vin_ota_y)
    vin_transition_y = 56.5  # M2→M3 transition below ibias_fc @y=60
    # M2 horizontal from left edge to vin_ota_x
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))
    # M2 vertical from pin up to transition y (stays below ibias zone)
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, vin_pin_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_transition_y + wire_w2/2))
    # via2 at transition point
    draw_via2(top, layout, vin_ota_x, vin_transition_y)
    # M3 vertical from transition up to OTA gate, with M4 bridge over ibias_q M3 @y=61
    vin_ibq_cross_y = 61.0  # ibias_q M3 horizontal y-level
    vin_v3_bot = vin_ibq_cross_y - 0.52
    vin_v3_top = vin_ibq_cross_y + 0.52
    # M3 segment: transition → bottom via3
    top.shapes(li_m3).insert(rect(vin_ota_x - hw2, vin_transition_y - hw2,
                                   vin_ota_x + hw2, vin_v3_bot))
    # M4 bridge over ibias_q M3
    draw_via3(top, layout, vin_ota_x, vin_v3_bot)
    draw_via3(top, layout, vin_ota_x, vin_v3_top)
    top.shapes(li_m4).insert(rect(vin_ota_x - hw2, vin_v3_bot - 0.195,
                                   vin_ota_x + hw2, vin_v3_top + 0.195))
    # M3 segment: top via3 → OTA gate
    top.shapes(li_m3).insert(rect(vin_ota_x - hw2, vin_v3_top,
                                   vin_ota_x + hw2, vin_ota_y + hw2))
    # via2 at OTA gate to drop back to M2 for via1 connection
    draw_via2(top, layout, vin_ota_x, vin_ota_y)

    # Also route vin to bypass mux input
    bypass_mux_x, bypass_mux_y = mux['bypass_in']
    draw_via1(top, layout, bypass_mux_x, bypass_mux_y)
    bypass_tap_y = mux['bypass_in'][1]
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_tap_y - wire_w2/2,
                                   bypass_mux_x + wire_w2/2, bypass_tap_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(vin_ota_x - wire_w2/2, bypass_tap_y - wire_w2/2,
                                   vin_ota_x + wire_w2/2, vin_pin_y + wire_w2/2))

    # --- vout pin: right edge, y≈42 ---
    # Mux drain M1 bus at (42.61, 7→17.5). LP mux M2 jog occupies y=7, x=42-43.6.
    # Can't via1 at mux drain — M2 pad would overlap LP jog.
    # Fix: extend M1 drain bus down to y=4.0, via1 there, then M2 to pin.
    vout_pin_y = 42.0
    mux_out_x, mux_out_y = mux['out']  # (42.61, 7.0)
    vout_low_y = 4.0   # below mux and LP jog
    # Extend M1 from mux drain bus down to vout_low_y
    top.shapes(li_m1).insert(rect(mux_out_x - wire_w/2, vout_low_y - wire_w/2,
                                   mux_out_x + wire_w/2, mux_out_y + wire_w/2))
    # via1 at bottom of M1 extension (safely below LP mux M2 jog)
    draw_via1(top, layout, mux_out_x, vout_low_y)
    vout_jog_x = 49.0  # well right of all mux M3 verticals and jogs
    # M2 horizontal at vout_low_y to vout_jog_x
    top.shapes(li_m2).insert(rect(mux_out_x - wire_w2/2, vout_low_y - wire_w2/2,
                                   vout_jog_x + wire_w2/2, vout_low_y + wire_w2/2))
    # M2 vertical from vout_low_y up to vout_pin_y
    top.shapes(li_m2).insert(rect(vout_jog_x - wire_w2/2, vout_low_y - wire_w2/2,
                                   vout_jog_x + wire_w2/2, vout_pin_y + wire_w2/2))
    # M2 horizontal from vout_jog_x to right edge
    top.shapes(li_m2).insert(rect(vout_jog_x - wire_w2/2, vout_pin_y - wire_w2/2,
                                   MACRO_W, vout_pin_y + wire_w2/2))

    # --- sel[0] pin: left edge, y≈10 ---
    sel0_pin_y = 10.0
    sel0_gc_x, sel0_gc_y = mux['lp_gate']
    top.shapes(li_m2).insert(rect(0.0, sel0_pin_y - wire_w2/2,
                                   sel0_gc_x + wire_w2/2, sel0_pin_y + wire_w2/2))
    draw_via1(top, layout, sel0_gc_x, sel0_pin_y)
    # M1 vertical from via1 to gate contact
    top.shapes(li_m1).insert(rect(sel0_gc_x - wire_w/2, sel0_gc_y - wire_w/2,
                                   sel0_gc_x + wire_w/2, sel0_pin_y + wire_w/2))

    # --- sel[1] pin: left edge, y≈16 ---
    sel1_pin_y = 16.0
    sel1_gc_x, sel1_gc_y = mux['bp_gate']
    top.shapes(li_m2).insert(rect(0.0, sel1_pin_y - wire_w2/2,
                                   sel1_gc_x + wire_w2/2, sel1_pin_y + wire_w2/2))
    draw_via1(top, layout, sel1_gc_x, sel1_pin_y)
    # M1 vertical from via1 to gate contact
    top.shapes(li_m1).insert(rect(sel1_gc_x - wire_w/2, sel1_gc_y - wire_w/2,
                                   sel1_gc_x + wire_w/2, sel1_pin_y + wire_w/2))

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

    # --- ibias_q pin: left edge, y≈62 ---
    # Route on M3 to avoid M2 crossings. M3 horizontal at y=61.0 (avoids LP M3 @y=62).
    # M3 vertical from ref_drain(10.26, 58) up to y=61, then M3 horizontal to x=0.
    # ota_sum VSS M3 column at x=3.98 is continuous here → M4 bridge needed.
    ibias_q_pin_y = 62.0
    ibias_q_m3_y = 61.0   # M3 horizontal y-level
    q_ref_x, q_ref_y = bias_q['ref_drain']
    draw_via1(top, layout, q_ref_x, q_ref_y)
    draw_via2(top, layout, q_ref_x, q_ref_y)
    # M3 vertical from ref drain (y=58) up to M3 horizontal (y=61)
    # Must bridge over fc_bus M3 @y=59 (x=6.02→19.95) since x=10.26 is within range
    fc_cross_y = fc_bus_m3_y  # 59.0
    ibq_v3_bot = fc_cross_y - 0.52  # 58.48
    ibq_v3_top = fc_cross_y + 0.52  # 59.52
    # M3 segment from ref_drain to bottom via3
    top.shapes(li_m3).insert(rect(q_ref_x - hw2, q_ref_y - hw2,
                                   q_ref_x + hw2, ibq_v3_bot))
    # M4 bridge over fc_bus M3
    draw_via3(top, layout, q_ref_x, ibq_v3_bot)
    draw_via3(top, layout, q_ref_x, ibq_v3_top)
    top.shapes(li_m4).insert(rect(q_ref_x - hw2, ibq_v3_bot - 0.195,
                                   q_ref_x + hw2, ibq_v3_top + 0.195))
    # M3 segment from top via3 to M3 horizontal
    top.shapes(li_m3).insert(rect(q_ref_x - hw2, ibq_v3_top,
                                   q_ref_x + hw2, ibias_q_m3_y + hw2))
    # M3 horizontal at y=61 from x=0 to x=q_ref_x, with M4 bridge over VSS @x=3.98
    vss_col_x = ota_sum['vss'][0]  # 3.98
    ibq_gap = 0.52
    # Right segment: from q_ref_x to right of VSS column
    top.shapes(li_m3).insert(rect(vss_col_x + ibq_gap, ibias_q_m3_y - hw2,
                                   q_ref_x + hw2, ibias_q_m3_y + hw2))
    # M4 bridge over VSS M3 column
    draw_via3(top, layout, vss_col_x + ibq_gap, ibias_q_m3_y)
    draw_via3(top, layout, vss_col_x - ibq_gap, ibias_q_m3_y)
    top.shapes(li_m4).insert(rect(vss_col_x - ibq_gap - 0.195, ibias_q_m3_y - hw2,
                                   vss_col_x + ibq_gap + 0.195, ibias_q_m3_y + hw2))
    # Left segment: from left edge to left of VSS column
    top.shapes(li_m3).insert(rect(0.0, ibias_q_m3_y - hw2,
                                   vss_col_x - ibq_gap, ibias_q_m3_y + hw2))

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
                  rect(0.0, ibias_fc_pin_y - 0.5, 0.5, ibias_fc_pin_y + 0.5),
                  "ibias_fc", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, ibias_q_m3_y - 0.5, 0.5, ibias_q_m3_y + 0.5),
                  "ibias_q", layout)
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

    layout, top = build_svf()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  OTAs: 4 × 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Integration caps: 2 × {C_INT} pF (MIM {C_INT_SIDE}×{C_INT_SIDE} µm)")
    print(f"  Mux: 4 × NMOS W={MUX_W}µm L={MUX_L}µm")
    print(f"  Bias: 2 × NMOS mirror (fc + q) W={BIAS_W}µm L={BIAS_L}µm")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
