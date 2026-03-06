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

    sd_ext = max(CONT_SIZE + 2 * CONT_ENC_ACTIV, CONT_SIZE + 2 * 0.11)
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

    sd_ext = max(CONT_SIZE + 2 * CONT_ENC_ACTIV, CONT_SIZE + 2 * 0.11)
    act_len = sd_ext + l + sd_ext

    if draw_nwell:
        nw_enc = NWELL_ENC_ACTIV
        cell.shapes(li_nw).insert(rect(x - nw_enc, y - nw_enc,
                                        x + act_len + nw_enc, y + w + nw_enc))

    cell.shapes(li_act).insert(rect(x, y, x + act_len, y + w))
    psd_enc_activ = 0.18
    psd_enc_gate = 0.30
    cell.shapes(li_psd).insert(rect(x - psd_enc_activ, y - psd_enc_gate,
                                     x + act_len + psd_enc_activ, y + w + psd_enc_gate))

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


# ===========================================================================
# OTA builder (same topology as gen_sc_svf.py)
# ===========================================================================
def draw_ota(cell, layout, x, y):
    """
    Draw a 5-transistor OTA.
    Returns dict with pin centers.
    """
    dp_gap = 1.3
    sd_ext = max(CONT_SIZE + 2 * CONT_ENC_ACTIV, CONT_SIZE + 2 * 0.11)
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


# ===========================================================================
# Main: build the PWM comparator
# ===========================================================================
def build_pwm_comp():
    layout = new_layout()
    top = layout.create_cell("pwm_comp")

    li_m1  = layout.layer(*L_METAL1)
    li_m2  = layout.layer(*L_METAL2)
    li_m3  = layout.layer(*L_METAL3)

    wire_w  = M1_WIDTH
    wire_w2 = M2_WIDTH

    # =====================================================================
    # Layout plan (bottom to top):
    #   y=0..1.5   : VSS rail (Metal3)
    #   y=2..12    : OTA (5 transistors)
    #   y=12..14   : CMOS inverter (2 transistors)
    #   y=13.5..15 : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 1.5))

    # =====================================================================
    # OTA (5 transistors)
    # =====================================================================
    ota_x = 0.5
    ota_y = 2.0
    ota = draw_ota(top, layout, x=ota_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M1 vertical + via1+via2 to M3
    for vdd_pin in ['vdd_l', 'vdd_r']:
        px, py = ota[vdd_pin]
        top.shapes(li_m1).insert(rect(px - wire_w/2, py - wire_w/2,
                                       px + wire_w/2, MACRO_H - 2.0))
        draw_via1(top, layout, px, MACRO_H - 2.0)
        draw_via2(top, layout, px, MACRO_H - 0.75)

    # Connect OTA VSS (tail source) to VSS rail via M3
    px, py = ota['vss']
    draw_via1(top, layout, px, py)
    draw_via2(top, layout, px, py)
    top.shapes(li_m3).insert(rect(px - wire_w2/2, 0.0,
                                   px + wire_w2/2, py + wire_w2/2))

    # Self-bias: connect tail gate to drain (simple current mirror bias)
    tx, ty = ota['tail']
    top.shapes(li_m1).insert(rect(min(tx, ota['vss'][0]) - wire_w/2, ty - wire_w/2,
                                   max(tx, ota['vss'][0]) + wire_w/2, ty + wire_w/2))

    # =====================================================================
    # CMOS Inverter (2 transistors) — sharpens OTA output to rail-to-rail
    # Place to the right of OTA output
    # =====================================================================
    sd_ext = max(CONT_SIZE + 2 * CONT_ENC_ACTIV, CONT_SIZE + 2 * 0.11)
    inv_act_len = sd_ext + INV_N_L + sd_ext

    inv_x = 9.0
    inv_n_y = 2.5  # NMOS
    inv_p_y = inv_n_y + INV_N_W + 2.0  # PMOS above

    inv_n = draw_nmos(top, layout, inv_x, inv_n_y, w=INV_N_W, l=INV_N_L)
    inv_p = draw_pmos(top, layout, inv_x, inv_p_y, w=INV_P_W, l=INV_P_L)

    # Connect NMOS drain to PMOS drain (inverter output)
    top.shapes(li_m1).insert(rect(inv_n['drain'][0] - wire_w/2, inv_n['drain'][1] - wire_w/2,
                                   inv_n['drain'][0] + wire_w/2, inv_p['drain'][1] + wire_w/2))

    # Connect NMOS gate to PMOS gate (inverter input)
    # Route via M1 horizontal
    top.shapes(li_m1).insert(rect(inv_n['gate'][0] - wire_w/2, inv_n['gate'][1] - wire_w/2,
                                   inv_n['gate'][0] + wire_w/2, inv_p['gate'][1] + wire_w/2))

    # NMOS source → VSS via M3
    ns_x, ns_y = inv_n['source']
    draw_via1(top, layout, ns_x, ns_y)
    draw_via2(top, layout, ns_x, ns_y)
    top.shapes(li_m3).insert(rect(ns_x - wire_w2/2, 0.0,
                                   ns_x + wire_w2/2, ns_y + wire_w2/2))

    # PMOS source → VDD via M1 vertical + via1+via2 to M3
    ps_x, ps_y = inv_p['source']
    top.shapes(li_m1).insert(rect(ps_x - wire_w/2, ps_y - wire_w/2,
                                   ps_x + wire_w/2, MACRO_H - 2.0))
    draw_via1(top, layout, ps_x, MACRO_H - 2.0)
    draw_via2(top, layout, ps_x, MACRO_H - 0.75)

    # =====================================================================
    # Signal routing: OTA output → inverter input
    # =====================================================================
    ota_out_x, ota_out_y = ota['out']
    inv_in_x = inv_n['gate'][0]
    inv_in_y = (inv_n['gate'][1] + inv_p['gate'][1]) / 2

    # Route on M2: via1 at OTA output, horizontal M2, via1 at inverter gate
    draw_via1(top, layout, ota_out_x, ota_out_y)
    route_y = ota_out_y
    top.shapes(li_m2).insert(rect(ota_out_x - wire_w2/2, route_y - wire_w2/2,
                                   inv_in_x + wire_w2/2, route_y + wire_w2/2))
    draw_via1(top, layout, inv_in_x, route_y)
    # M1 vertical from via1 to inverter gate
    top.shapes(li_m1).insert(rect(inv_in_x - wire_w/2, min(route_y, inv_n['gate'][1]) - wire_w/2,
                                   inv_in_x + wire_w/2, max(route_y, inv_p['gate'][1]) + wire_w/2))

    # =====================================================================
    # Substrate taps
    # =====================================================================
    # ptap near OTA NMOS (y≈2)
    draw_ptap(top, layout, 0.5, 1.5)
    draw_ptap(top, layout, 4.0, 1.5)
    # ptap near inverter NMOS
    draw_ptap(top, layout, 9.0, 1.5)

    # ntap near OTA PMOS (inside NWell)
    # OTA PMOS NWell region: x≈0.2..4.5, y≈9.2..11.8
    draw_ntap(top, layout, 2.0, 10.5)

    # ntap near inverter PMOS
    draw_ntap(top, layout, 10.0, inv_p_y + 0.2)

    # =====================================================================
    # Pin routing and labels
    # =====================================================================

    # --- vinp pin: left edge, y≈5 ---
    vinp_pin_y = 5.0
    vinp_gate_x, vinp_gate_y = ota['inp']
    draw_via1(top, layout, vinp_gate_x, vinp_gate_y)
    top.shapes(li_m2).insert(rect(0.0, vinp_pin_y - wire_w2/2,
                                   vinp_gate_x + wire_w2/2, vinp_pin_y + wire_w2/2))
    # M2 vertical from pin_y to gate_y
    top.shapes(li_m2).insert(rect(vinp_gate_x - wire_w2/2,
                                   min(vinp_pin_y, vinp_gate_y) - wire_w2/2,
                                   vinp_gate_x + wire_w2/2,
                                   max(vinp_pin_y, vinp_gate_y) + wire_w2/2))

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
    # M2 horizontal to right edge
    top.shapes(li_m2).insert(rect(inv_out_x - wire_w2/2, out_pin_y - wire_w2/2,
                                   MACRO_W, out_pin_y + wire_w2/2))
    # M2 vertical jog if needed
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
                  rect(0.0, MACRO_H - 1.5, MACRO_W, MACRO_H), "vdd", layout)
    add_pin_label(top, L_METAL3_PIN, L_METAL3_LBL,
                  rect(0.0, 0.0, MACRO_W, 1.5), "vss", layout)

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
