# svf_2nd

- Description: 2nd-order SC state variable filter (Tow-Thomas biquad)
- PDK: ihp-sg13g2

## Authorship

- Designer: shue
- Created: March 3, 2026
- License: Apache 2.0
- Company: None
- Last modified: None

## Pins

- vin
  + Description: Audio input signal
  + Type: signal
  + Direction: input
  + Vmin: 0
  + Vmax: vdd
- vout
  + Description: Filtered output (LP/BP/HP/bypass via sel mux)
  + Type: signal
  + Direction: output
  + Vmin: 0
  + Vmax: vdd
- sel0
  + Description: Output mux select bit 0
  + Type: digital
  + Direction: input
- sel1
  + Description: Output mux select bit 1
  + Type: digital
  + Direction: input
- sc_clk
  + Description: Switching clock (sets center frequency)
  + Type: digital
  + Direction: input
- q0
  + Description: Q tuning bit 0 (LSB)
  + Type: digital
  + Direction: input
- q1
  + Description: Q tuning bit 1
  + Type: digital
  + Direction: input
- q2
  + Description: Q tuning bit 2
  + Type: digital
  + Direction: input
- q3
  + Description: Q tuning bit 3 (MSB)
  + Type: digital
  + Direction: input
- vdd
  + Description: Positive power supply
  + Type: power
  + Direction: inout
  + Vmin: 1.08
  + Vmax: 1.32
- vss
  + Description: Ground
  + Type: ground
  + Direction: inout

## Default Conditions

- vdd
  + Description: Power supply voltage
  + Display: Vdd
  + Unit: V
  + Typical: 1.2
- f_clk
  + Description: Switching clock frequency
  + Display: f_clk
  + Unit: Hz
  + Typical: 93750
- q_code
  + Description: Q control code (1-15)
  + Display: Q code
  + Typical: 4
- sel0
  + Description: Mux select bit 0 voltage
  + Display: sel0
  + Unit: V
  + Typical: 1.2
- sel1
  + Description: Mux select bit 1 voltage
  + Display: sel1
  + Unit: V
  + Typical: 0

## Symbol

![Symbol of svf_2nd](svf_2nd_symbol.svg)

## Schematic

![Schematic of svf_2nd](svf_2nd_schematic.svg)

## Layout

![Layout of svf_2nd with white background](svf_2nd_w.png)
![Layout of svf_2nd with black background](svf_2nd_b.png)
