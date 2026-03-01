#!/usr/bin/env python3
"""Generate SVG schematics for the four analog hard macros."""

import schemdraw
import schemdraw.elements as elm
from schemdraw import flow
import os

OUT_DIR = os.path.dirname(__file__)


def draw_r2r_dac():
    """8-bit complementary-switch R-2R DAC."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=11, unit=3)

        # Title
        d += elm.Annotate().at((0, 12.5)).label(
            '8-bit R-2R DAC (Complementary Switch)', fontsize=14).color('black')
        d += elm.Annotate().at((0, 11.8)).label(
            'IHP SG13G2 130nm — R=2kΩ, 2R=4kΩ, VDD=1.2V', fontsize=9).color('gray')

        # Draw the ladder from MSB (top) to LSB (bottom)
        bits = ['b7\n(MSB)', 'b6', 'b5', 'b4', 'b3', 'b2', 'b1', 'b0\n(LSB)']
        y_start = 10.0
        y_step = -1.3

        # Output node
        d += elm.Dot().at((6, y_start)).label('Vout', loc='right')
        vout_y = y_start

        for i, blabel in enumerate(bits):
            y = y_start + (i + 1) * y_step

            # Tap node
            d += elm.Dot().at((6, y))

            # Series R (between taps) — except after MSB which connects to vout
            if i == 0:
                d += elm.Resistor().at((6, vout_y)).down().to((6, y)).label('R', loc='left')
            else:
                y_prev = y_start + i * y_step
                d += elm.Resistor().at((6, y_prev)).down().to((6, y)).label('R', loc='left')

            # 2R shunt leg
            d += elm.Line().at((6, y)).left().length(1.5)
            d += elm.Resistor().left().length(2).label('2R', loc='top')
            sw_x = 6 - 1.5 - 2

            # CMOS switch (simplified as a box)
            d += elm.Switch().left().length(1.5).label(blabel, loc='top')

            # VDD/VSS labels at switch
            bit_x = sw_x - 1.5
            d += elm.Annotate().at((bit_x - 0.3, y + 0.3)).label('VDD/VSS', fontsize=7).color('gray')

        # Termination 2R at bottom
        last_y = y_start + len(bits) * y_step
        term_y = last_y + y_step
        d += elm.Resistor().at((6, last_y)).down().to((6, term_y)).label('2R', loc='left')
        d += elm.Ground().at((6, term_y))

        # MSB 2R shunt
        d += elm.Dot().at((6, y_start))
        d += elm.Line().at((6, y_start)).left().length(1.5)
        d += elm.Resistor().left().length(2).label('2R', loc='top')
        d += elm.Switch().left().length(1.5).label('b7\n(MSB)', loc='top')

        d.save(os.path.join(OUT_DIR, 'sch_r2r_dac.svg'))
    print("  Wrote sch_r2r_dac.svg")


def draw_sc_svf():
    """2nd-order Switched-Capacitor State Variable Filter (Tow-Thomas biquad)."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=10, unit=3.5)

        # Title
        d += elm.Annotate().at((-1, 8)).label(
            'SC State Variable Filter (Tow-Thomas Biquad)', fontsize=14).color('black')
        d += elm.Annotate().at((-1, 7.3)).label(
            'IHP SG13G2 130nm — C_int=1.1pF, C_sw=73.5fF, VDD=1.2V', fontsize=9).color('gray')

        # ---- Integrator 1 (produces BP) ----
        # Input SC resistor
        d += elm.Dot().at((0, 4)).label('Vin', loc='left')
        d += elm.Line().right().length(1)
        d += elm.Capacitor().right().length(2).label('C_sw\n73.5fF', loc='top')
        d += elm.Annotate().at((2, 3.3)).label('SC_R1', fontsize=8).color('blue')

        # Summing node
        d += elm.Dot().at((3, 4)).label('Σ', loc='top')
        sum_x = 3

        # OTA1
        d += elm.Line().right().length(1)
        d += elm.Opamp().right().anchor('in1').label('OTA1', loc='center', ofst=0)
        ota1_out_x = 7.5

        # C_int1 (feedback)
        d += elm.Line().at((sum_x + 0.5, 4)).up().length(1.5)
        d += elm.Capacitor().right().length(3.5).label('C_int1\n1.1pF', loc='top')
        d += elm.Line().down().length(1.5)
        d += elm.Dot().at((ota1_out_x, 4)).label('BP', loc='top')

        # ---- Integrator 2 (produces LP_bar) ----
        d += elm.Line().at((ota1_out_x, 4)).right().length(1)
        d += elm.Capacitor().right().length(2).label('C_sw\n73.5fF', loc='top')
        d += elm.Annotate().at((9.5, 3.3)).label('SC_R2→int', fontsize=8).color('blue')

        sum2_x = 10.5
        d += elm.Dot().at((sum2_x, 4))

        d += elm.Line().right().length(1)
        d += elm.Opamp().right().anchor('in1').label('OTA2', loc='center', ofst=0)
        ota2_out_x = 15

        # C_int2 (feedback)
        d += elm.Line().at((sum2_x + 0.5, 4)).up().length(1.5)
        d += elm.Capacitor().right().length(3).label('C_int2\n1.1pF', loc='top')
        d += elm.Line().down().length(1.5)

        # LP_bar label
        d += elm.Dot().at((ota2_out_x, 4)).label('LP_bar', loc='right')

        # ---- Unity inverter → LP ----
        d += elm.Line().at((ota2_out_x, 4)).right().length(1)
        d += elm.Annotate().at((ota2_out_x + 1, 4.4)).label('−1', fontsize=12).color('blue')
        d += elm.Line().right().length(1.5)
        d += elm.Dot().at((ota2_out_x + 2.5, 4)).label('LP', loc='right')

        # ---- LP feedback to Σ ----
        lp_x = ota2_out_x + 2.5
        d += elm.Line().at((lp_x, 4)).down().length(3)
        d += elm.Line().left().length(lp_x - sum_x)
        d += elm.Capacitor().up().length(2).label('C_sw\n(feedback)', loc='right')
        d += elm.Line().up().length(1).to((sum_x, 4))

        # ---- C_Q damping (BP → Σ) ----
        d += elm.Line().at((ota1_out_x, 4)).down().length(1.5)
        d += elm.Line().left().length(ota1_out_x - sum_x)
        d += elm.Capacitor().up().length(1.5).label('C_Q\n(4-bit)', loc='right')

        # ---- NOL clock annotation ----
        d += elm.Annotate().at((1.5, 2)).label(
            'φ1/φ2: Non-overlapping clocks from sc_clk', fontsize=8).color('gray')

        # ---- Output mux ----
        d += elm.Annotate().at((ota2_out_x - 2, 0.5)).label(
            'Output Mux (sel[1:0]): HP | BP | LP | Bypass', fontsize=9).color('blue')

        d.save(os.path.join(OUT_DIR, 'sch_sc_svf.svg'))
    print("  Wrote sch_sc_svf.svg")


def draw_sar_adc():
    """8-bit SAR ADC with StrongARM comparator and binary-weighted cap DAC."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=10, unit=3.5)

        # Title
        d += elm.Annotate().at((-1, 10)).label(
            '8-bit SAR ADC', fontsize=14).color('black')
        d += elm.Annotate().at((-1, 9.3)).label(
            'IHP SG13G2 130nm — StrongARM comparator + binary-weighted cap DAC', fontsize=9).color('gray')

        # ---- StrongARM Comparator ----
        comp_x, comp_y = 6, 6

        # Draw opamp symbol for comparator
        d += elm.Dot().at((0, 6.5)).label('Vin', loc='left')
        d += elm.Line().right().length(2)

        d += elm.Opamp().right().anchor('in1').label('StrongARM\nComparator', loc='center', ofst=0)

        # Clock input
        d += elm.Annotate().at((2, 4.5)).label('clk →', fontsize=9).color('blue')

        # Comparator output
        comp_out_x = 6
        d += elm.Dot().at((comp_out_x, 6)).label('comp_out', loc='top')

        # ---- SAR Logic ----
        d += elm.Line().at((comp_out_x, 6)).right().length(2)
        # Draw SAR logic as a box
        d += elm.Annotate().at((8.5, 6.5)).label('SAR', fontsize=12).color('black')
        d += elm.Annotate().at((8.5, 5.8)).label('Logic', fontsize=12).color('black')
        d += elm.Annotate().at((8.5, 5.1)).label('(8-bit)', fontsize=9).color('gray')

        # Digital output
        d += elm.Line().at((10.5, 6)).right().length(2)
        d += elm.Dot().at((12.5, 6)).label('dout[7:0]', loc='right')

        # EOC
        d += elm.Line().at((10.5, 5)).right().length(2)
        d += elm.Dot().at((12.5, 5)).label('eoc', loc='right')

        # ---- Binary-Weighted Cap DAC ----
        d += elm.Line().at((8.5, 4.5)).down().length(1)
        d += elm.Annotate().at((5, 3)).label('Binary-Weighted Capacitor DAC', fontsize=10).color('black')

        # Draw cap array
        cap_labels = ['256fF', '128fF', '64fF', '32fF', '16fF', '8fF', '4fF', '2fF', '2fF']
        bit_labels = ['b7', 'b6', 'b5', 'b4', 'b3', 'b2', 'b1', 'b0', 'dum']
        x_start = 0.5
        x_step = 1.4

        # Top plate line
        d += elm.Line().at((x_start, 2.5)).right().length(x_step * 8.5)
        d += elm.Dot().at((x_start, 2.5)).label('vtop →\ncomp+', loc='left', fontsize=8)

        for i, (cl, bl) in enumerate(zip(cap_labels, bit_labels)):
            cx = x_start + i * x_step + 0.5
            d += elm.Capacitor().at((cx, 2.5)).down().length(1.5).label(cl, loc='right', fontsize=7)
            d += elm.Annotate().at((cx - 0.3, 0.5)).label(bl, fontsize=7).color('blue')

            # Switch to Vref or VSS
            if bl != 'dum':
                d += elm.Switch().at((cx, 1)).down().length(0.8)

        # Ground for dummy
        dx = x_start + 8 * x_step + 0.5
        d += elm.Ground().at((dx, 1))

        # Vref/VSS labels
        d += elm.Annotate().at((1, -0.2)).label(
            'Switches connect to VDD (1.2V) or VSS based on SAR decision', fontsize=8).color('gray')

        d.save(os.path.join(OUT_DIR, 'sch_sar_adc.svg'))
    print("  Wrote sch_sar_adc.svg")


def draw_bias_dac():
    """Dual 4-bit Bias DAC for FC and Q control."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=10, unit=3)

        # Title
        d += elm.Annotate().at((0, 10)).label(
            'Dual 4-bit Bias DAC (FC + Q Control)', fontsize=14).color('black')
        d += elm.Annotate().at((0, 9.3)).label(
            'IHP SG13G2 130nm — R-2R ladder, VDD=1.2V', fontsize=9).color('gray')

        # ---- FC Channel (left side) ----
        d += elm.Annotate().at((1, 8.2)).label('FC Channel', fontsize=11).color('blue')

        bits_fc = ['dfc3\n(MSB)', 'dfc2', 'dfc1', 'dfc0\n(LSB)']
        y_start = 7.5
        y_step = -1.3
        x_base = 3

        d += elm.Dot().at((x_base, y_start)).label('Vout_fc', loc='right')

        for i, blabel in enumerate(bits_fc):
            y = y_start + (i + 1) * y_step

            d += elm.Dot().at((x_base, y))

            if i == 0:
                d += elm.Resistor().at((x_base, y_start)).down().to((x_base, y)).label('R', loc='left')
            else:
                y_prev = y_start + i * y_step
                d += elm.Resistor().at((x_base, y_prev)).down().to((x_base, y)).label('R', loc='left')

            d += elm.Line().at((x_base, y)).left().length(1)
            d += elm.Resistor().left().length(1.5).label('2R', loc='top')
            d += elm.Switch().left().length(1).label(blabel, loc='top')

        # Termination
        last_y = y_start + len(bits_fc) * y_step
        term_y = last_y + y_step
        d += elm.Resistor().at((x_base, last_y)).down().to((x_base, term_y)).label('2R', loc='left')
        d += elm.Ground().at((x_base, term_y))

        # ---- Q Channel (right side) ----
        d += elm.Annotate().at((10, 8.2)).label('Q Channel', fontsize=11).color('blue')

        bits_q = ['dq3\n(MSB)', 'dq2', 'dq1', 'dq0\n(LSB)']
        x_base_q = 12

        d += elm.Dot().at((x_base_q, y_start)).label('Vout_q', loc='right')

        for i, blabel in enumerate(bits_q):
            y = y_start + (i + 1) * y_step

            d += elm.Dot().at((x_base_q, y))

            if i == 0:
                d += elm.Resistor().at((x_base_q, y_start)).down().to((x_base_q, y)).label('R', loc='left')
            else:
                y_prev = y_start + i * y_step
                d += elm.Resistor().at((x_base_q, y_prev)).down().to((x_base_q, y)).label('R', loc='left')

            d += elm.Line().at((x_base_q, y)).left().length(1)
            d += elm.Resistor().left().length(1.5).label('2R', loc='top')
            d += elm.Switch().left().length(1).label(blabel, loc='top')

        d += elm.Resistor().at((x_base_q, last_y)).down().to((x_base_q, term_y)).label('2R', loc='left')
        d += elm.Ground().at((x_base_q, term_y))

        d.save(os.path.join(OUT_DIR, 'sch_bias_dac.svg'))
    print("  Wrote sch_bias_dac.svg")


def draw_strongarm():
    """StrongARM comparator transistor-level schematic."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=10, unit=3)

        # Title
        d += elm.Annotate().at((0, 14)).label(
            'StrongARM Latch Comparator', fontsize=14).color('black')
        d += elm.Annotate().at((0, 13.3)).label(
            'IHP SG13G2 130nm — VDD=1.2V', fontsize=9).color('gray')

        cx = 6  # center x

        # VDD rail
        d += elm.Line().at((cx - 4, 12)).right().length(8)
        d += elm.Annotate().at((cx + 4.2, 12)).label('VDD', fontsize=10)

        # PMOS reset switches (Mp_rst1, Mp_rst2)
        d += elm.Annotate().at((cx - 3, 11.5)).label('Mp_rst1', fontsize=8).color('gray')
        d += elm.Annotate().at((cx + 1.5, 11.5)).label('Mp_rst2', fontsize=8).color('gray')
        d += elm.Annotate().at((cx - 5, 11)).label('clk_b →', fontsize=8).color('blue')

        # dp and dn nodes
        d += elm.Dot().at((cx - 2, 10)).label('dp', loc='left', fontsize=9)
        d += elm.Dot().at((cx + 2, 10)).label('dn', loc='right', fontsize=9)
        d += elm.Line().at((cx - 2, 12)).down().length(2)
        d += elm.Line().at((cx + 2, 12)).down().length(2)

        # PMOS output reset (Mp_rst3, Mp_rst4)
        d += elm.Dot().at((cx - 4, 10)).label('outp', loc='left', fontsize=9)
        d += elm.Dot().at((cx + 4, 10)).label('outn', loc='right', fontsize=9)
        d += elm.Line().at((cx - 4, 12)).down().length(2)
        d += elm.Line().at((cx + 4, 12)).down().length(2)

        # Cross-coupled PMOS latch
        d += elm.Annotate().at((cx - 3.5, 9.2)).label('PMOS latch', fontsize=8).color('blue')
        d += elm.Annotate().at((cx - 4.5, 8.5)).label('Mp_cc1: outn→gate', fontsize=7).color('gray')
        d += elm.Annotate().at((cx + 0.5, 8.5)).label('Mp_cc2: outp→gate', fontsize=7).color('gray')

        d += elm.Line().at((cx - 4, 10)).down().length(2)
        d += elm.Line().at((cx + 4, 10)).down().length(2)

        # Cross-coupled NMOS latch
        d += elm.Annotate().at((cx - 3.5, 7.2)).label('NMOS latch', fontsize=8).color('blue')
        d += elm.Annotate().at((cx - 4.5, 6.5)).label('Mn_cc1: outn→gate', fontsize=7).color('gray')
        d += elm.Annotate().at((cx + 0.5, 6.5)).label('Mn_cc2: outp→gate', fontsize=7).color('gray')

        # Connect latch to dp/dn
        d += elm.Line().at((cx - 4, 8)).right().length(2)  # outp → dp
        d += elm.Line().at((cx + 4, 8)).left().length(2)   # outn → dn

        # Input diff pair
        d += elm.Annotate().at((cx - 2, 5.5)).label('NMOS Diff Pair', fontsize=9).color('blue')
        d += elm.Dot().at((cx - 2, 5)).label('Mn1', loc='left', fontsize=8)
        d += elm.Dot().at((cx + 2, 5)).label('Mn2', loc='right', fontsize=8)
        d += elm.Line().at((cx - 2, 8)).down().length(3)
        d += elm.Line().at((cx + 2, 8)).down().length(3)

        # Input labels
        d += elm.Line().at((cx - 2, 5)).left().length(2)
        d += elm.Annotate().at((cx - 4.5, 5)).label('Vin+', fontsize=10)
        d += elm.Line().at((cx + 2, 5)).right().length(2)
        d += elm.Annotate().at((cx + 4.2, 5)).label('Vin−', fontsize=10)

        # Tail connection
        d += elm.Line().at((cx - 2, 5)).down().length(1)
        d += elm.Line().left().length(0).to((cx, 4))
        d += elm.Line().at((cx + 2, 5)).down().length(1)
        d += elm.Line().right().length(0).to((cx, 4))
        d += elm.Line().at((cx - 2, 4)).right().length(4)

        # Tail NMOS
        d += elm.Dot().at((cx, 4))
        d += elm.Annotate().at((cx - 1, 3.2)).label('Mtail\n(W=4µm)', fontsize=8).color('gray')
        d += elm.Line().at((cx, 4)).down().length(1.5)
        d += elm.Annotate().at((cx - 2, 2.8)).label('clk →', fontsize=9).color('blue')

        # VSS
        d += elm.Ground().at((cx, 2.5))
        d += elm.Annotate().at((cx + 0.5, 2.2)).label('VSS', fontsize=9)

        # Transistor sizes annotation
        d += elm.Annotate().at((0, 1.5)).label(
            'Sizes: Diff pair W=2µm L=0.5µm | Latch W=1µm L=0.13µm | Reset W=2µm L=0.13µm | Tail W=4µm L=0.13µm',
            fontsize=8).color('gray')

        d.save(os.path.join(OUT_DIR, 'sch_strongarm.svg'))
    print("  Wrote sch_strongarm.svg")


def draw_ota():
    """5-transistor OTA used in SC SVF."""
    with schemdraw.Drawing(show=False) as d:
        d.config(fontsize=10, unit=3)

        # Title
        d += elm.Annotate().at((0, 12)).label(
            '5-Transistor OTA (SC SVF Integrator)', fontsize=14).color('black')
        d += elm.Annotate().at((0, 11.3)).label(
            'IHP SG13G2 130nm — VDD=1.2V', fontsize=9).color('gray')

        cx = 6

        # VDD rail
        d += elm.Line().at((cx - 3, 10)).right().length(6)
        d += elm.Annotate().at((cx + 3.2, 10)).label('VDD', fontsize=10)

        # PMOS current mirror (M3, M4)
        d += elm.Annotate().at((cx - 2.5, 9.2)).label('M3 (PMOS)', fontsize=8).color('gray')
        d += elm.Annotate().at((cx + 0.5, 9.2)).label('M4 (PMOS)', fontsize=8).color('gray')
        d += elm.Annotate().at((cx - 1, 9.7)).label('W=2µm L=0.5µm', fontsize=7).color('gray')

        d += elm.Line().at((cx - 2, 10)).down().length(1.5)
        d += elm.Line().at((cx + 2, 10)).down().length(1.5)

        # Diode-connected M3
        d += elm.Annotate().at((cx - 3.5, 8.2)).label('(diode)', fontsize=7).color('blue')

        # Mirror gate connection
        d += elm.Line().at((cx - 2, 8.5)).right().length(4)

        # Diff pair drains connect to mirror
        d += elm.Dot().at((cx - 2, 8.5))
        d += elm.Dot().at((cx + 2, 8.5))

        # NMOS diff pair (M1, M2)
        d += elm.Annotate().at((cx - 2.5, 6.5)).label('M1 (NMOS)', fontsize=8).color('gray')
        d += elm.Annotate().at((cx + 0.5, 6.5)).label('M2 (NMOS)', fontsize=8).color('gray')
        d += elm.Annotate().at((cx - 1, 7.2)).label('W=4µm L=0.5µm', fontsize=7).color('gray')

        d += elm.Line().at((cx - 2, 8.5)).down().length(2)
        d += elm.Line().at((cx + 2, 8.5)).down().length(2)

        # Output from M4 drain (= M2 drain)
        d += elm.Line().at((cx + 2, 8.5)).right().length(2)
        d += elm.Dot().at((cx + 4, 8.5)).label('Vout', loc='right', fontsize=10)

        # Input gates
        d += elm.Line().at((cx - 2, 6.5)).left().length(2)
        d += elm.Annotate().at((cx - 4.5, 6.5)).label('Vin+', fontsize=10)

        d += elm.Line().at((cx + 2, 6.5)).right().length(2)
        d += elm.Annotate().at((cx + 4.2, 6.5)).label('Vin−', fontsize=10)

        # Common source → tail
        d += elm.Line().at((cx - 2, 6.5)).down().length(1)
        d += elm.Line().at((cx + 2, 6.5)).down().length(1)
        d += elm.Line().at((cx - 2, 5.5)).right().length(4)

        # Tail NMOS (M5)
        d += elm.Dot().at((cx, 5.5))
        d += elm.Annotate().at((cx - 1, 4.7)).label('M5 (tail)\nW=2µm L=0.5µm', fontsize=8).color('gray')

        d += elm.Line().at((cx, 5.5)).down().length(2)

        # Bias gate
        d += elm.Line().at((cx, 4.5)).left().length(2)
        d += elm.Annotate().at((cx - 2.5, 4.5)).label('Vbias', loc='left', fontsize=10)

        # VSS
        d += elm.Ground().at((cx, 3.5))

        d.save(os.path.join(OUT_DIR, 'sch_ota.svg'))
    print("  Wrote sch_ota.svg")


if __name__ == '__main__':
    print("Generating analog schematics...")
    draw_r2r_dac()
    draw_sc_svf()
    draw_sar_adc()
    draw_bias_dac()
    draw_strongarm()
    draw_ota()
    print("Done.")
