# pwm_comp

- Description: PWM comparator — 5T OTA with CMOS inverter output stage
- PDK: ihp-sg13g2

## Authorship

- Designer: shue
- Created: March 6, 2026
- License: Apache 2.0
- Company: None
- Last modified: None

## Pins

- vinp
  + Description: Non-inverting input (from SVF output)
  + Type: signal
  + Direction: input
  + Vmin: 0
  + Vmax: vdd
- vinn
  + Description: Inverting input (from ramp DAC)
  + Type: signal
  + Direction: input
  + Vmin: 0
  + Vmax: vdd
- out
  + Description: Digital PWM output (rail-to-rail)
  + Type: signal
  + Direction: output
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
- temperature
  + Description: Ambient temperature
  + Display: Temp
  + Unit: °C
  + Typical: 27
- corner
  + Description: Process corner (MOS)
  + Display: Corner
  + Typical: mos_tt

## Symbol

![Symbol of pwm_comp](pwm_comp_symbol.svg)

## Schematic

![Schematic of pwm_comp](pwm_comp_schematic.svg)

## Layout

![Layout of pwm_comp with white background](pwm_comp_w.png)
![Layout of pwm_comp with black background](pwm_comp_b.png)
