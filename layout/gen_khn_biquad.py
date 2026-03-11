#!/usr/bin/env python3
"""
Generate KHN 2-OTA SC Biquad layout for IHP SG13G2 130nm.

Architecture: KHN state-variable filter with SC resistors + OTA integrators.

  Vin ──→ [SC1: C_in] ──→ sum1 ──→ [OTA1: inv. integrator] ──→ BP
                           ↑         Cint1 (feedback bp→sum1)
  LP ───→ [SC2: C_fb] ──→─┘
                           ↑
  BP ───→ [Q bank] ──────→┘ (C_Q array, q-switched)

  BP ───→ [SC4: C_is] ──→ sum2 ──→ [OTA2: inv. integrator] ──→ LP
                                    Cint2 (feedback lp→sum2)

  Vin ──→ [SC5: C5] ──→ sum3 ──→ [OTA3: HP reconstruction] ──→ HP
  LP ───→ [SC6: C6] ──→ sum3     C_hp (feedback hp→sum3)
                                  HP reset TG (φ1)

  Output mixer: en_lp→TG→LP, en_bp→TG→BP, en_hp→TG→HP → vout

Compact layout: switches nested under MIM integration caps (different metal
layers: switches use M1-M3, MIM caps use M5/TM1).  Q array stacked
vertically beside integration caps.

Components:
  3 × OTA (5T diff pair: 2 integrators + 1 HP reconstruction)
  2 × MIM integration cap (C_int = 0.8 pF, ~23×23 µm)
  6 × MIM switching cap (C_sw = 73.5 fF, ~7×7 µm)
  4 × C_Q array cap (4.9 fF unit, binary-weighted)
  36 × CMOS TG (20 SC + 12 Q-bank + 1 HP reset + 3 mixer, in 2 rows of 18)
  4 × NOL clock inverters (8 transistors)
  7 × complement inverters (4 Q + 3 enable)
  1 × Bias generator (diode-connected PMOS + NMOS)

Macro size: 60 × 58 µm
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from sg13g2_layers import *
from gen_sc_svf import (
    draw_nmos, draw_pmos, draw_gate_contact,
    draw_via1, draw_via2, draw_via3, draw_via4, draw_topvia1,
    draw_via_stack_m2_to_m5, draw_via_stack_m2_to_tm1,
    draw_via_stack_m3_to_m5, draw_via_stack_m3_to_tm1,
    draw_mim_cap, draw_ota, draw_cmos_switch,
    draw_nol_clock, draw_bias_gen,
    OTA_DP_W, OTA_DP_L, OTA_LD_W, OTA_LD_L, OTA_TAIL_W, OTA_TAIL_L,
    C_INT_SIDE, C_SW_SIDE, CQ_UNIT_SIDE,
    SW_N_W, SW_N_L, SW_P_W, SW_P_L,
    NOL_N_W, NOL_N_L, NOL_P_W, NOL_P_L,
    BIAS_N_W, BIAS_N_L, BIAS_P_W, BIAS_P_L,
    MIM_SPACE, MIM_ENC_M5,
)


# ===========================================================================
# Design parameters
# ===========================================================================
MACRO_W = 60.0
MACRO_H = 58.0

# Inverter sizes (for complement generation)
INV_N_W = 1.0
INV_N_L = 0.13
INV_P_W = 2.0
INV_P_L = 0.13


# ===========================================================================
# Additional helpers
# ===========================================================================

def draw_inverter(cell, layout, x, y):
    """
    Draw a CMOS inverter (NMOS + PMOS, drains connected).
    Returns dict with pin centers: in, out, vdd, vss.
    """
    li_m1 = layout.layer(*L_METAL1)
    wire_w = M1_WIDTH

    sd_ext = SD_EXT

    # NMOS
    mn = draw_nmos(cell, layout, x, y, w=INV_N_W, l=INV_N_L)

    # PMOS above
    pmos_y = y + INV_N_W + 1.5
    mp = draw_pmos(cell, layout, x, pmos_y, w=INV_P_W, l=INV_P_L)

    # Gate contacts on outer sides
    mn['gate'] = draw_gate_contact(cell, layout, mn['gate'][0], y - GATPOLY_EXT,
                                    l=INV_N_L, side='below')
    mp['gate'] = draw_gate_contact(cell, layout, mp['gate'][0],
                                    pmos_y + INV_P_W + GATPOLY_EXT,
                                    l=INV_P_L, side='above')

    # Connect gates (M1 vertical)
    cell.shapes(li_m1).insert(rect(mn['gate'][0] - wire_w/2,
                                    mn['gate'][1] - wire_w/2,
                                    mn['gate'][0] + wire_w/2,
                                    mp['gate'][1] + wire_w/2))

    # Connect drains (output, M1 vertical)
    drn_hw = (CONT_SIZE + 2 * CONT_ENC_M1) / 2
    cell.shapes(li_m1).insert(rect(mn['drain'][0] - drn_hw,
                                    mn['drain'][1] - drn_hw,
                                    mn['drain'][0] + drn_hw,
                                    mp['drain'][1] + drn_hw))

    act_len = sd_ext + INV_N_L + sd_ext
    total_h = (pmos_y + INV_P_W) - y

    return {
        'in':      mn['gate'],      # input (connected NMOS+PMOS gates)
        'out':     mn['drain'],     # output (connected drains)
        'vdd':     mp['source'],    # PMOS source → VDD
        'vss':     mn['source'],    # NMOS source → VSS
        'total_w': act_len,
        'total_h': total_h,
    }


# ===========================================================================
# Main: build the compact KHN Biquad
# ===========================================================================
def build_khn_biquad():
    layout = new_layout()
    top = layout.create_cell("khn_biquad")

    li_m1 = layout.layer(*L_METAL1)
    li_m2 = layout.layer(*L_METAL2)
    li_m3 = layout.layer(*L_METAL3)
    li_m4 = layout.layer(*L_METAL4)
    li_nw = layout.layer(*L_NWELL)

    wire_w = M1_WIDTH
    wire_w2 = M2_WIDTH

    # =====================================================================
    # Layout sections (Y offsets) — compact, switches nested under caps:
    #   y=0..2       : VSS rail (Metal3)
    #   y=3..10      : 6 small MIM switching caps (M5/TM1)
    #   y=12..36     : MIM integration caps (M5/TM1, x=2..52)
    #                  Q array (M5/TM1, x=53..59, stacked vertically)
    #   y=14..22     : Switch row 1 (18 TGs, M1-M3, under caps)
    #   y=24..32     : Switch row 2 (18 TGs, M1-M3, under caps)
    #   y=37..44     : NOL clock + bias gen + complement inverters
    #   y=45..54     : OTA row (3 OTAs)
    #   y=56..58     : VDD rail (Metal3)
    # =====================================================================

    # --- VDD rail (top, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, MACRO_H - 2.0, MACRO_W, MACRO_H))

    # --- VSS rail (bottom, Metal3) ---
    top.shapes(li_m3).insert(rect(0.0, 0.0, MACRO_W, 2.0))

    # =====================================================================
    # OTA row: 3 OTAs (integrator 1, integrator 2, HP reconstruction)
    # =====================================================================
    ota_y = 45.0
    ota_gap = 3.0
    dp_act_len = SD_EXT + OTA_DP_L + SD_EXT
    ota_total_w = dp_act_len * 2 + 1.4  # from draw_ota dp_gap=1.4

    ota1_x = 2.2
    ota1 = draw_ota(top, layout, x=ota1_x, y=ota_y)
    ota2_x = ota1_x + ota1['total_w'] + ota_gap
    ota2 = draw_ota(top, layout, x=ota2_x, y=ota_y)
    ota3_x = ota2_x + ota2['total_w'] + ota_gap
    ota3 = draw_ota(top, layout, x=ota3_x, y=ota_y)

    # Connect OTA PMOS sources to VDD rail via M2 bus
    ota_ld_top = ota_y + OTA_TAIL_W + 1.5 + OTA_DP_W + 2.0 + OTA_LD_W
    vdd_bus_y = ota_ld_top + 0.6
    vdd_via_xs = []
    for ota in [ota1, ota2, ota3]:
        for vdd_pin in ['vdd_l', 'vdd_r']:
            px, py = ota[vdd_pin]
            draw_via1(top, layout, px, py)
            top.shapes(li_m2).insert(rect(px - wire_w2/2, py - wire_w2/2,
                                          px + wire_w2/2, vdd_bus_y + wire_w2/2))
            vdd_via_xs.append(px)

    # Via2 + M3 from PMOS sources to M3 VDD rail
    for px in vdd_via_xs:
        draw_via2(top, layout, px, vdd_bus_y)
        top.shapes(li_m3).insert(rect(px - wire_w2/2, vdd_bus_y - wire_w2/2,
                                       px + wire_w2/2, MACRO_H))

    # Connect OTA VSS (tail source) to VSS rail via M3
    for ota in [ota1, ota2, ota3]:
        px, py = ota['vss']
        draw_via1(top, layout, px, py)
        draw_via2(top, layout, px, py)
        top.shapes(li_m3).insert(rect(px - wire_w2/2, 0.0,
                                       px + wire_w2/2, py + wire_w2/2))

    # M2 VDD bus
    vdd_x_min = min(vdd_via_xs)
    vdd_x_max = max(vdd_via_xs)
    top.shapes(li_m2).insert(rect(vdd_x_min - wire_w2/2, vdd_bus_y - wire_w2/2,
                                   vdd_x_max + wire_w2/2, vdd_bus_y + wire_w2/2))
    for vx in [vdd_x_min, vdd_x_max]:
        draw_via2(top, layout, vx, MACRO_H - 1.0)
        top.shapes(li_m2).insert(rect(vx - wire_w2/2, vdd_bus_y - wire_w2/2,
                                       vx + wire_w2/2, MACRO_H - 1.0 + wire_w2/2))

    # =====================================================================
    # Bias generator
    # =====================================================================
    bias_x = 2.40
    bias_y = 37.5
    bias = draw_bias_gen(top, layout, bias_x, bias_y)

    # Bias VSS → VSS rail via M3
    bvx, bvy = bias['vss']
    draw_via1(top, layout, bvx, bvy)
    draw_via2(top, layout, bvx, bvy)
    top.shapes(li_m3).insert(rect(bvx - wire_w2/2, 0.0,
                                   bvx + wire_w2/2, bvy + wire_w2/2))

    # Bias VDD → VDD rail via M3
    bvx, bvy = bias['vdd']
    draw_via1(top, layout, bvx, bvy)
    draw_via2(top, layout, bvx, bvy)
    top.shapes(li_m3).insert(rect(bvx - wire_w2/2, bvy - wire_w2/2,
                                   bvx + wire_w2/2, MACRO_H))

    # Bias output → OTA tail gates via M1 horizontal bus
    bias_out_x, bias_out_y = bias['bias_out']
    bias_bus_y = 43.8
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_out_y - wire_w/2,
                                   bias_out_x + wire_w/2, bias_bus_y + wire_w/2))
    t3x, t3y = ota3['tail']
    top.shapes(li_m1).insert(rect(bias_out_x - wire_w/2, bias_bus_y - wire_w/2,
                                   t3x + wire_w/2, bias_bus_y + wire_w/2))
    for tx, ty in [ota1['tail'], ota2['tail'], ota3['tail']]:
        top.shapes(li_m1).insert(rect(tx - wire_w/2, bias_bus_y - wire_w/2,
                                       tx + wire_w/2, ty + wire_w/2))

    # Connect OTA non-inverting inputs (inp) to bias/VCM via M2
    vcm_bus_y = 44.5
    for ota in [ota1, ota2, ota3]:
        px, py = ota['inp']
        draw_via1(top, layout, px, py)
        top.shapes(li_m2).insert(rect(bias_out_x - wire_w2/2, vcm_bus_y - wire_w2/2,
                                       px + wire_w2/2, vcm_bus_y + wire_w2/2))
        top.shapes(li_m2).insert(rect(px - wire_w2/2, min(vcm_bus_y, py) - wire_w2/2,
                                       px + wire_w2/2, max(vcm_bus_y, py) + wire_w2/2))
    draw_via1(top, layout, bias_out_x, bias_out_y)
    top.shapes(li_m2).insert(rect(bias_out_x - wire_w2/2, bias_out_y - wire_w2/2,
                                   bias_out_x + wire_w2/2, vcm_bus_y + wire_w2/2))

    # =====================================================================
    # NOL clock generator
    # =====================================================================
    nol_x = 14.0
    nol_y = 38.5
    nol = draw_nol_clock(top, layout, nol_x, nol_y)

    nol_gate_cx = nol['clk_in'][0]
    nol_gate_cnt_y = nol['clk_in'][1]

    # NOL NMOS sources to VSS via M3
    for i in range(4):
        sx, sy = nol['nmos'][i]['source']
        draw_via1(top, layout, sx, sy)
        draw_via2(top, layout, sx, sy)
        top.shapes(li_m3).insert(rect(sx - wire_w2/2, 0.0,
                                       sx + wire_w2/2, sy + wire_w2/2))

    # NOL PMOS sources to VDD via M3
    for i in range(4):
        px, py = nol['pmos'][i]['source']
        draw_via1(top, layout, px, py)
        if i == 2:
            # Route PMOS[2] via M2 to PMOS[3] to avoid M3 congestion
            nol_pmos_3_x = nol['pmos'][3]['source'][0]
            top.shapes(li_m2).insert(rect(px - wire_w2/2, py - wire_w2/2,
                                           nol_pmos_3_x + wire_w2/2, py + wire_w2/2))
        else:
            draw_via2(top, layout, px, py)
            top.shapes(li_m3).insert(rect(px - wire_w2/2, py - wire_w2/2,
                                           px + wire_w2/2, MACRO_H))

    # =====================================================================
    # Complement inverters (7 total: q0_b..q3_b, en_lp_b, en_bp_b, en_hp_b)
    # =====================================================================
    inv_x_start = 28.0
    inv_y = 37.5
    inv_pitch = (SD_EXT + INV_N_L + SD_EXT) + 1.2

    inverters = []
    for i in range(7):
        ix = inv_x_start + i * inv_pitch
        inv = draw_inverter(top, layout, ix, inv_y)
        inverters.append(inv)

    inv_q0, inv_q1, inv_q2, inv_q3 = inverters[0], inverters[1], inverters[2], inverters[3]
    inv_en_lp, inv_en_bp, inv_en_hp = inverters[4], inverters[5], inverters[6]

    # Inverter NWells: merge into one strip
    inv_pmos_y = inv_y + INV_N_W + 1.5
    inv_first_x = inv_x_start - NWELL_ENC_ACTIV
    inv_last_x = inv_x_start + 6 * inv_pitch + (SD_EXT + INV_N_L + SD_EXT) + NWELL_ENC_ACTIV
    top.shapes(li_nw).insert(rect(inv_first_x, inv_pmos_y - NWELL_ENC_ACTIV,
                                   inv_last_x, inv_pmos_y + INV_P_W + NWELL_ENC_ACTIV))

    # Inverter power: VSS via M3, VDD via M3
    for inv in inverters:
        vx, vy = inv['vss']
        draw_via1(top, layout, vx, vy)
        draw_via2(top, layout, vx, vy)
        top.shapes(li_m3).insert(rect(vx - wire_w2/2, 0.0,
                                       vx + wire_w2/2, vy + wire_w2/2))
        vx, vy = inv['vdd']
        draw_via1(top, layout, vx, vy)
        draw_via2(top, layout, vx, vy)
        top.shapes(li_m3).insert(rect(vx - wire_w2/2, vy - wire_w2/2,
                                       vx + wire_w2/2, MACRO_H))

    # =====================================================================
    # MIM Integration Caps (C_int1 and C_int2)
    # y=12..36, x=2..52 (M5/TM1)
    # =====================================================================
    cap_y = 12.0
    c1_x = 2.0
    c1_bot, c1_top = draw_mim_cap(top, layout, c1_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    c2_x = c1_x + C_INT_SIDE + MIM_SPACE + 2 * MIM_ENC_M5 + 1.0
    c2_bot, c2_top = draw_mim_cap(top, layout, c2_x, cap_y, C_INT_SIDE, C_INT_SIDE)

    # =====================================================================
    # C_Q Binary-Weighted Cap Array — stacked vertically beside integration
    # caps at x=53.5, y=12..35 (M5/TM1)
    # =====================================================================
    cq_gap = MIM_SPACE + 2 * MIM_ENC_M5  # gap between Q caps (TM1.b)

    # Integration cap 2 M5 right edge: c2_x + C_INT_SIDE + MIM_ENC_M5
    c2_m5_right = c2_x + C_INT_SIDE + MIM_ENC_M5
    # Q array Cmim left: need M5 left = Cmim_x - MIM_ENC_M5 >= c2_m5_right + 0.44 (M5 spacing)
    cq_x = c2_m5_right + 0.44 + MIM_ENC_M5
    cq_x = snap5(cq_x)

    cq_caps = []
    cq_cy = cap_y
    for i in range(4):
        fF = 4.9 * (2 ** i)
        side = math.sqrt(fF / 1.5)
        side = round(side * 200) / 200  # snap to 5nm grid
        b, t = draw_mim_cap(top, layout, cq_x, cq_cy, side, side)
        cq_caps.append({'bot': b, 'top': t, 'x': cq_x, 'w': side, 'h': side, 'y': cq_cy})
        cq_cy += side + cq_gap

    # =====================================================================
    # Small MIM Switching Caps (6 × C_sw)
    # C_in, C_fb, C_is, C5, C6, C_hp — bottom band y=3
    # =====================================================================
    sw_cap_y = 3.0
    csw_gap = MIM_SPACE + 2 * MIM_ENC_M5  # 1.64µm (TM1.b min spacing)

    csw_caps = []
    csw_x = 2.0
    for i in range(6):
        cx = csw_x + i * (C_SW_SIDE + csw_gap)
        bot, top_c = draw_mim_cap(top, layout, cx, sw_cap_y, C_SW_SIDE, C_SW_SIDE)
        csw_caps.append((bot, top_c))

    csw1_bot, csw1_top = csw_caps[0]  # C_in (vin→sum1)
    csw2_bot, csw2_top = csw_caps[1]  # C_fb (lp→sum1)
    csw3_bot, csw3_top = csw_caps[2]  # C_is (bp→sum2)
    csw4_bot, csw4_top = csw_caps[3]  # C5 (vin→sum3)
    csw5_bot, csw5_top = csw_caps[4]  # C6 (lp→sum3)
    csw6_bot, csw6_top = csw_caps[5]  # C_hp (hp feedback)

    # =====================================================================
    # CMOS Switches: 2 rows of 18 (under integration caps, M1-M3)
    # Row 1 (y=14): SC1(4) + SC2(4) + SC4(4) + Q0 enable(1) + Q0 phi(1) + Q0 ref(1) + Q1(3)
    # Row 2 (y=24): SC5(4) + SC6(4) + Q2(3) + Q3(3) + HP_reset(1) + mixer_lp(1) + mixer_bp(1) + mixer_hp(1)
    # =====================================================================
    sd_ext = SD_EXT
    sw_w = sd_ext + SW_N_L + sd_ext
    sw_gap = 1.5
    sw_pitch = sw_w + sw_gap
    sw_start_x = NWELL_SPACE_DN + NWELL_ENC_ACTIV + 0.12

    sw_row1_y = 14.0
    sw_row2_y = 24.0

    switches_r1 = []
    for i in range(18):
        sx = sw_start_x + i * sw_pitch
        sw = draw_cmos_switch(top, layout, sx, sw_row1_y)
        switches_r1.append(sw)

    switches_r2 = []
    for i in range(18):
        sx = sw_start_x + i * sw_pitch
        sw = draw_cmos_switch(top, layout, sx, sw_row2_y)
        switches_r2.append(sw)

    # NWell strips for each switch row
    for row_y in [sw_row1_y, sw_row2_y]:
        sw_pmos_y = row_y + SW_N_W + 1.5
        nw_y1 = sw_pmos_y - NWELL_ENC_ACTIV
        nw_y2 = sw_pmos_y + SW_P_W + NWELL_ENC_ACTIV
        nw_x1 = sw_start_x - NWELL_ENC_ACTIV
        sw_last_x = sw_start_x + 17 * sw_pitch
        nw_x2 = sw_last_x + sw_w + NWELL_ENC_ACTIV
        top.shapes(li_nw).insert(rect(nw_x1, nw_y1, nw_x2, nw_y2))

    # Assign switches to SC elements:
    # Row 1: SC1(4) + SC2(4) + SC4(4) + Q0(3) + Q1(3)
    sw_e1 = switches_r1[0:4]    # C_in switches
    sw_e2 = switches_r1[4:8]    # C_fb switches
    sw_e4 = switches_r1[8:12]   # C_is switches
    sw_q = [switches_r1[12:15], switches_r1[15:18]]  # Q0, Q1

    # Row 2: SC5(4) + SC6(4) + Q2(3) + Q3(3) + HP_reset(1) + mixer(3)
    sw_e5 = switches_r2[0:4]    # C5 switches
    sw_e6 = switches_r2[4:8]    # C6 switches
    sw_q += [switches_r2[8:11], switches_r2[11:14]]  # Q2, Q3
    hp_reset = switches_r2[14]
    mixer_lp = switches_r2[15]
    mixer_bp = switches_r2[16]
    mixer_hp = switches_r2[17]

    # =====================================================================
    # Via stacks for MIM caps
    # =====================================================================
    via_pad_hw = VIA3_ENC_M3 + VIA3_SIZE / 2

    # Integration caps: via stacks for top plates
    draw_via_stack_m3_to_tm1(top, layout, c1_top[0], c1_top[1])
    draw_via_stack_m3_to_tm1(top, layout, c2_top[0], c2_top[1])

    # C_int1 bottom plate → sum1 (OTA1 inverting input)
    sum1_x, sum1_y = ota1['inn']
    c1_bot_via_x = sum1_x - 0.25
    c1_bot_via_y = c1_bot[1] + 0.20
    draw_via_stack_m2_to_m5(top, layout, c1_bot_via_x, c1_bot_via_y)
    top.shapes(li_m3).insert(rect(c1_bot_via_x - wire_w2/2, c1_bot_via_y - wire_w2/2,
                                   c1_bot_via_x + wire_w2/2, sum1_y + wire_w2/2))
    draw_via1(top, layout, sum1_x, sum1_y)
    draw_via2(top, layout, c1_bot_via_x, sum1_y)
    top.shapes(li_m2).insert(rect(c1_bot_via_x - wire_w2/2, sum1_y - wire_w2/2,
                                   sum1_x + wire_w2/2, sum1_y + wire_w2/2))

    # C_int2 bottom plate → sum2 (OTA2 inverting input)
    sum2_x, sum2_y = ota2['inn']
    c2_bot_vy = c2_bot[1] + 0.20
    draw_via_stack_m2_to_m5(top, layout, c2_bot[0], c2_bot_vy)
    draw_via1(top, layout, sum2_x, sum2_y)
    c2_route_x = sum2_x - 0.5
    draw_via3(top, layout, c2_route_x, c2_bot_vy)
    e4 = VIA3_ENC_M4 + VIA3_SIZE / 2
    top.shapes(li_m4).insert(rect(c2_route_x - e4, c2_bot_vy - e4,
                                   c2_bot[0] + e4, c2_bot_vy + e4))
    top.shapes(li_m3).insert(rect(c2_route_x - wire_w2/2, c2_bot_vy - wire_w2/2,
                                   c2_route_x + wire_w2/2, sum2_y + wire_w2/2))
    draw_via2(top, layout, c2_route_x, sum2_y)
    top.shapes(li_m2).insert(rect(c2_route_x - wire_w2/2, sum2_y - wire_w2/2,
                                   sum2_x + wire_w2/2, sum2_y + wire_w2/2))

    # Switching caps and CQ: via stacks
    for csw_bot, csw_top in csw_caps:
        draw_via_stack_m3_to_tm1(top, layout, csw_top[0], csw_top[1])
        draw_via_stack_m2_to_m5(top, layout, csw_bot[0], csw_bot[1])
        top.shapes(li_m3).insert(rect(csw_bot[0] - via_pad_hw, csw_bot[1] - via_pad_hw,
                                       csw_bot[0] + via_pad_hw, csw_bot[1] + via_pad_hw))

    for cap_info in cq_caps:
        draw_via_stack_m3_to_tm1(top, layout, cap_info['top'][0], cap_info['top'][1])
        bot_via_x = cap_info['x'] + cap_info['w'] / 2
        draw_via_stack_m2_to_m5(top, layout, bot_via_x, cap_info['bot'][1])
        top.shapes(li_m3).insert(rect(bot_via_x - via_pad_hw, cap_info['bot'][1] - via_pad_hw,
                                       bot_via_x + via_pad_hw, cap_info['bot'][1] + via_pad_hw))

    # =====================================================================
    # Signal routing
    # =====================================================================

    # --- OTA1 output (BP node) ---
    bp_x1, bp_y1 = ota1['out']
    draw_via1(top, layout, bp_x1, bp_y1)
    bp_route_y = ota_y - 1.2
    draw_via2(top, layout, bp_x1, bp_y1)
    draw_via2(top, layout, bp_x1, bp_route_y)
    top.shapes(li_m3).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   bp_x1 + wire_w2/2, bp_y1 + wire_w2/2))

    # BP → C_int1 top plate (feedback)
    draw_via2(top, layout, c1_top[0], bp_route_y)
    top.shapes(li_m3).insert(rect(c1_top[0] - wire_w2/2, c1_top[1] - wire_w2/2,
                                   c1_top[0] + wire_w2/2, bp_route_y + wire_w2/2))
    top.shapes(li_m2).insert(rect(bp_x1 - wire_w2/2, bp_route_y - wire_w2/2,
                                   c1_top[0] + wire_w2/2, bp_route_y + wire_w2/2))

    # --- OTA2 output (LP node) ---
    lp_x1, lp_y1 = ota2['out']
    draw_via1(top, layout, lp_x1, lp_y1)
    lp_route_y = ota_y - 2.5
    draw_via2(top, layout, lp_x1, lp_y1)
    draw_via2(top, layout, lp_x1, lp_route_y)
    top.shapes(li_m3).insert(rect(lp_x1 - wire_w2/2, lp_route_y - wire_w2/2,
                                   lp_x1 + wire_w2/2, lp_y1 + wire_w2/2))

    # LP → C_int2 top plate via M4
    c2_fb_y = 40.0
    draw_via2(top, layout, lp_x1, c2_fb_y)
    draw_via3(top, layout, lp_x1, c2_fb_y)
    top.shapes(li_m3).insert(rect(c2_top[0] - wire_w2/2, c2_fb_y - wire_w2/2,
                                   c2_top[0] + wire_w2/2, c2_top[1] + wire_w2/2))
    draw_via3(top, layout, c2_top[0], c2_fb_y)
    top.shapes(li_m4).insert(rect(lp_x1 - e4, c2_fb_y - e4,
                                   c2_top[0] + e4, c2_fb_y + e4))

    # --- OTA3 output (HP node) ---
    hp_x1, hp_y1 = ota3['out']
    draw_via1(top, layout, hp_x1, hp_y1)
    hp_route_y = ota_y - 3.8
    draw_via2(top, layout, hp_x1, hp_y1)
    draw_via2(top, layout, hp_x1, hp_route_y)
    top.shapes(li_m3).insert(rect(hp_x1 - wire_w2/2, hp_route_y - wire_w2/2,
                                   hp_x1 + wire_w2/2, hp_y1 + wire_w2/2))

    # --- OTA3 inn (sum3) ---
    sum3_x, sum3_y = ota3['inn']
    draw_via1(top, layout, sum3_x, sum3_y)

    # --- Mixer output bus: connect mixer_lp, mixer_bp, mixer_hp outputs via M2 ---
    for sw in [mixer_lp, mixer_bp, mixer_hp]:
        ox, oy = sw['out']
        draw_via1(top, layout, ox, oy)

    mx_lp_out = mixer_lp['out']
    mx_bp_out = mixer_bp['out']
    mx_hp_out = mixer_hp['out']
    # All mixer outputs are in row 2, connect via M2 vertical bus
    mixer_bus_x = mx_lp_out[0] + 0.5
    for sw in [mixer_lp, mixer_bp, mixer_hp]:
        ox, oy = sw['out']
        top.shapes(li_m2).insert(rect(ox - wire_w2/2, oy - wire_w2/2,
                                       mixer_bus_x + wire_w2/2, oy + wire_w2/2))
    # Vertical M2 bus connecting all three (they're in the same row, so same Y)
    # Actually they're adjacent in row 2, so at same Y but different X
    top.shapes(li_m2).insert(rect(mx_lp_out[0] - wire_w2/2, mx_lp_out[1] - wire_w2/2,
                                   mx_hp_out[0] + wire_w2/2, mx_hp_out[1] + wire_w2/2))

    # =====================================================================
    # Substrate taps
    # =====================================================================

    # ptaps for NMOS (LU.b)
    for xt in [0.5, 26.0, 50.0]:
        draw_ptap(top, layout, xt, ota_y - 1.0)
    for xt in [14.0, 22.0, 36.0]:
        draw_ptap(top, layout, xt, 37.0)
    # ptaps in switch rows (under caps, still needed for substrate contact)
    for xt in [4.0, 12.0, 20.0, 28.0, 36.0, 44.0]:
        draw_ptap(top, layout, xt, sw_row1_y - 1.0)
        draw_ptap(top, layout, xt, sw_row2_y - 1.0)

    # ptaps with VSS via connections
    for ptap_x in [8.0, 25.0, 45.0, 55.0]:
        draw_ptap(top, layout, ptap_x, 1.0)
        ptap_cx = ptap_x + 0.18
        ptap_cy = 1.0 + 0.18
        draw_via1(top, layout, ptap_cx, ptap_cy)
        draw_via2(top, layout, ptap_cx, ptap_cy)

    # ntaps for PMOS NWell body → VDD
    NTAP_OFFSET = 0.60
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
    ntap_bias_x = bias_x
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

    # Switch NWell ntaps (one per row)
    for row_y in [sw_row1_y, sw_row2_y]:
        sw_pmos_row_y = row_y + SW_N_W + 1.5
        for ntap_sx in [7.0, 24.0, 40.0]:
            ntap_sw_y = sw_pmos_row_y + SW_P_W + NTAP_OFFSET
            draw_ntap(top, layout, ntap_sx, ntap_sw_y)
            ntap_sw_cx = ntap_sx + 0.18
            ntap_sw_cy = ntap_sw_y + 0.18
            draw_via1(top, layout, ntap_sw_cx, ntap_sw_cy)
            draw_via2(top, layout, ntap_sw_cx, ntap_sw_cy)
            top.shapes(li_m3).insert(rect(ntap_sw_cx - wire_w2/2, ntap_sw_cy - wire_w2/2,
                                           ntap_sw_cx + wire_w2/2, MACRO_H))

    # Inverter NWell ntaps
    inv_ntap_y = inv_pmos_y + INV_P_W + NTAP_OFFSET
    for inv_ntap_x in [31.0, 40.0]:
        draw_ntap(top, layout, inv_ntap_x, inv_ntap_y)
        ntc_x = inv_ntap_x + 0.18
        ntc_y = inv_ntap_y + 0.18
        draw_via1(top, layout, ntc_x, ntc_y)
        draw_via2(top, layout, ntc_x, ntc_y)
        top.shapes(li_m3).insert(rect(ntc_x - wire_w2/2, ntc_y - wire_w2/2,
                                       ntc_x + wire_w2/2, MACRO_H))

    # =====================================================================
    # Pin routing
    # =====================================================================

    # --- vin pin: left edge, y=25 ---
    vin_pin_y = 25.0
    vin_via_x = 1.0
    top.shapes(li_m2).insert(rect(0.0, vin_pin_y - 2.0,
                                   vin_via_x + wire_w2/2, vin_pin_y + 2.0))

    # --- vout pin: right edge, y=20 ---
    vout_pin_y = 20.0
    # Route mixer bus to right edge via M2
    mx_bus_cx = (mx_lp_out[0] + mx_hp_out[0]) / 2
    top.shapes(li_m2).insert(rect(mx_bus_cx - wire_w2/2,
                                   min(mx_lp_out[1], vout_pin_y) - wire_w2/2,
                                   mx_bus_cx + wire_w2/2,
                                   max(mx_lp_out[1], vout_pin_y) + wire_w2/2))
    top.shapes(li_m2).insert(rect(mx_bus_cx - wire_w2/2, vout_pin_y - wire_w2/2,
                                   MACRO_W, vout_pin_y + wire_w2/2))

    # --- en_lp pin: left edge ---
    en_lp_pin_y = 30.0
    top.shapes(li_m2).insert(rect(0.0, en_lp_pin_y - 0.5,
                                   1.0 + wire_w2/2, en_lp_pin_y + 0.5))

    # --- en_bp pin ---
    en_bp_pin_y = 32.0
    top.shapes(li_m2).insert(rect(0.0, en_bp_pin_y - 0.5,
                                   1.0 + wire_w2/2, en_bp_pin_y + 0.5))

    # --- en_hp pin ---
    en_hp_pin_y = 34.0
    top.shapes(li_m2).insert(rect(0.0, en_hp_pin_y - 0.5,
                                   1.0 + wire_w2/2, en_hp_pin_y + 0.5))

    # --- sc_clk pin: left edge ---
    sc_clk_pin_y = 40.0
    via_clk_x = 12.20
    via_clk_y = nol_gate_cnt_y
    draw_via1(top, layout, via_clk_x, via_clk_y)
    top.shapes(li_m1).insert(rect(via_clk_x - wire_w/2, via_clk_y - wire_w/2,
                                   nol_gate_cx + CONT_SIZE/2 + CONT_ENC_M1,
                                   via_clk_y + wire_w/2))
    top.shapes(li_m2).insert(rect(0.0, sc_clk_pin_y - 1.0,
                                   via_clk_x + wire_w2/2, sc_clk_pin_y + 1.0))
    top.shapes(li_m2).insert(rect(via_clk_x - wire_w2/2,
                                   min(sc_clk_pin_y, via_clk_y) - wire_w2/2,
                                   via_clk_x + wire_w2/2,
                                   max(sc_clk_pin_y, via_clk_y) + wire_w2/2))

    # --- q0..q3 pins: left edge ---
    q_pin_ys = [15.0, 17.0, 19.0, 21.0]
    for qi, qy in enumerate(q_pin_ys):
        top.shapes(li_m2).insert(rect(0.0, qy - 0.3,
                                       1.0 + wire_w2/2, qy + 0.3))

    # =====================================================================
    # Pin labels
    # =====================================================================
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, vin_pin_y - 2.0, 0.5, vin_pin_y + 2.0), "vin", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(MACRO_W - 0.5, vout_pin_y - 2.0, MACRO_W, vout_pin_y + 2.0),
                  "vout", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, en_lp_pin_y - 0.5, 0.5, en_lp_pin_y + 0.5), "en_lp", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, en_bp_pin_y - 0.5, 0.5, en_bp_pin_y + 0.5), "en_bp", layout)
    add_pin_label(top, L_METAL2_PIN, L_METAL2_LBL,
                  rect(0.0, en_hp_pin_y - 0.5, 0.5, en_hp_pin_y + 0.5), "en_hp", layout)
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

    # --- PR Boundary ---
    li_bnd = layout.layer(189, 0)
    top.shapes(li_bnd).insert(rect(0, 0, MACRO_W, MACRO_H))

    return layout, top


if __name__ == "__main__":
    outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "khn_biquad.gds")

    layout, top = build_khn_biquad()
    layout.write(outpath)

    print(f"Wrote {outpath}")
    print(f"  Topology: KHN SC+OTA biquad (compact, switches under caps)")
    print(f"  OTAs: 3 × 5-transistor (diff pair W={OTA_DP_W}µm L={OTA_DP_L}µm)")
    print(f"  Integration caps: 2 × 0.8 pF (MIM {C_INT_SIDE}×{C_INT_SIDE} µm)")
    print(f"  Switching caps: 6 × 73.5 fF (MIM {C_SW_SIDE}×{C_SW_SIDE} µm)")
    print(f"  C_Q array: 4-bit binary-weighted ({CQ_UNIT_SIDE}µm unit, 4.9 fF)")
    print(f"  CMOS switches: 36 in 2×18 rows (under integration caps)")
    print(f"  Complement inverters: 7 (4 Q + 3 enable)")
    print(f"  Bias gen: PMOS+NMOS diode (W={BIAS_P_W}µm L={BIAS_P_L}µm)")
    print(f"  NOL clock: 8 transistors (4 CMOS pairs)")
    print(f"  Macro: {MACRO_W} × {MACRO_H} µm = {MACRO_W*MACRO_H:.0f} µm²")
