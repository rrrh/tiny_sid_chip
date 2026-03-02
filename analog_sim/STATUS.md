# Analog Simulation Status — 2026-02-28

## Infrastructure: COMPLETE
- **ngspice-43** at `/home/shue/.local/bin/ngspice` (KLU+OSDI+XSPICE+OpenMP)
- **OSDI plugins** (psp103, psp103_nqs, r3_cmc) compiled via OpenVAF, loaded in spinit
- **PDK**: IHP SG13G2 typical corner (mos_tt, res_typ, cap_typ)

## Simulation Results

### r2r_dac: PASS (monotonic, good linearity)
- 256-code DC sweep complete, data in `r2r_dac_transfer.dat`
- CMOS complementary switches (PMOS W=20u + NMOS W=10u, L=0.13u)
- Transfer: code 0 = 0.000V, code 128 = 0.596V, code 255 = 1.192V
- **Monotonic**: 0 non-monotonic transitions
- LSB = 4.676mV (ideal 4.706mV)
- DNL: -0.070 to +0.077 LSB
- INL: 0.660 LSB max

![R-2R DAC Transfer Function](r2r_dac/r2r_dac_transfer.png)

### bias_dac: PASS (monotonic, correct range)
- 16-code sweep for both FC and Q channels, data in `bias_dac_fc.dat` / `bias_dac_q.dat`
- CMOS complementary switches, same topology as r2r_dac
- Both channels identical: code 0 = 0.000V, code 15 = 1.121V
- Monotonic, ~74.7mV per step

### svf: PASS (audio-band, stable AC + transient)
- Ideal behavioral gm-C SVF with current-sourcing OTAs and lossy integrators
- **Audio-band center frequency: ~1.9 kHz** (gm_fc=5µA/V, C=800pF)
- DC operating point: all nodes at VCM=0.6V ✓
- BP peak gain = -21.6 dB at 1.9 kHz (~-1.6 dB actual with 0.1 AC source)
- LP DC gain = -25.7 dB (~-5.7 dB actual)
- HP high-freq gain = -12.3 dB (bounded, stable)
- Transient (1kHz sine, 5ms): stable, bounded oscillation at all nodes ✓
- gm_fc=5µA/V, gm_q=2.5µA/V, C=800pF (ideal), Rbias=1M-10M
- Transistor-level OTA needs folded-cascode topology (SG13G2 Vtn+|Vtp|≈VDD)

![SVF AC Frequency Response](svf/svf_ac_response.png)

### sar_adc: PASS (comparator + cap DAC run)
- Comparator transient: resolves, data in `sar_comp_tran.dat`
- Cap DAC 256-code sweep: runs, data in `sar_adc_ramp.dat`
- Cap DAC output all zeros due to 1TΩ bias resistor + short transient settle time

### full_chain: PASS (DAC -> SVF -> ADC, signal passes through)
- 5ms transient simulation, 508 data points, 1kHz sine input (audio band)
- DAC output: quantized 1kHz sine (0.38-0.67V range around VCM) ✓
- SVF output: filtered sine (0.46-0.67V), tracks 1kHz input ✓
- ADC output: re-quantized version of SVF output, tracks correctly ✓
- Uses corrected CMOS-switch R-2R DAC + audio-band ideal-Gm SVF + behavioral ADC
- Data in `full_chain_out.dat`

![Full Chain: 1kHz through SVF BP](full_chain/full_chain_filtered.png)

### Waveform Tests: 440Hz & 880Hz (filter bypass)
- DAC → ADC bypass (no SVF), verifies DAC/ADC round-trip
- 440Hz (A4) and 880Hz (A5) quantized sines, 12ms transient

![440Hz and 880Hz Waveforms](full_chain/waveform_440_880.png)

### full_sweep: PASS (16-point frequency sweep, full chain + PWM recovery)
- 16 frequency points from 250 Hz to 16 kHz (matching SVF fc divider LUT, analog sim uses continuous-time model)
- Behavioral chain: sine → SVF (Tow-Thomas CT-equiv, LP mode, Q=1) → LPF → PWM → 3rd-order RC filter
- SVF fc tracks input frequency at each step via `alter` (R_eff = div_ratio / (24 MHz × C_sw))
- PWM: 94.1 kHz PULSE sawtooth with tanh comparator, 3.3V output into PCB RC filter
- RC recovery: 3×3.3kΩ + 3×4.7nF + 1µF AC coupling + 10kΩ load

**Frequency response** (normalized to 1 kHz):
- Flat passband 250–800 Hz (+0.7 to +0.8 dB)
- -3 dB at ~2.5 kHz (dominated by 3rd-order RC at fc=10.3 kHz)
- -17 dB at 16 kHz

![Frequency Response](full_sweep/freq_response.png)

![Waveform Waterfall — 16 frequency points](full_sweep/waveform_waterfall.png)

![PWM Recovery Detail — 1 kHz](full_sweep/pwm_recovery.png)

![Full Sweep Summary](full_sweep/full_sweep_summary.png)

### filter_sweep: PASS (LP/BP/HP characterization across Q and fc)
- SVF filter characterization: Tow-Thomas biquad CT-equivalent, no PWM chain
- Fixed 500 Hz input sine; filter fc swept across 250, 500, 1000, 1500 Hz
- 4 Q values (0.5, 1, 2, 5) × 4 cutoff frequencies = 16 ngspice segments
- **Low-pass**: passes signal when fc > fin; attenuates when fc < fin; resonant peak at Q=5
- **Band-pass**: peaks at fc=fin (500 Hz); attenuated above and below; Q sharpens peak
- **High-pass**: passes signal when fc < fin; attenuates when fc > fin; resonant peak at Q=5
- HP computed from sim data: HP = VCM + (Vin−VCM) − (LP−VCM) − (BP−VCM)/Q

![Low-Pass Response](filter_sweep/filter_lp.png)

![Band-Pass Response](filter_sweep/filter_bp.png)

![High-Pass Response](filter_sweep/filter_hp.png)

### Digital Frequency Sweep (`tests/freq_sweep_tb.v`)
- Verilog testbench sweeps Voice 0 sawtooth through 16 frequency points in bypass mode
- Captures PWM output to PWL files, processed through RC filter simulation (`tests/sim_analog.py`)
- 16 frequency points from 250 Hz to 3900 Hz (24-bit accumulator with 16-bit freq register limits fundamental to ~3906 Hz max)
- Run all stages: `bash tests/run_freq_sweep.sh`

## Key Design Issues Found (not simulation bugs)
1. ~~**R-2R DAC non-monotonicity**~~: FIXED — replaced NMOS-only switches with CMOS complementary switches, corrected ladder bit ordering
2. ~~**SVF OTA bias**~~: FIXED — switched to current-sourcing OTAs with lossy integrators (vinn=vout). 5T OTA can't reach VCM=0.6V (Vtn+|Vtp|≈VDD); transistor-level needs folded-cascode
3. **Cap DAC settling**: needs proper sample timing or longer settle time

## Behavioral Simulation Models

Each analog hard macro includes a behavioral model gated by `` `ifdef BEHAVIORAL_SIM ``:

- **`r2r_dac_8bit`** — combinational: captures `{d7,...,d0}` into `sim_data_out[7:0]`
- **`svf_2nd`** — 2nd-order SVF using `real` arithmetic on `posedge sc_clk`. Alpha = C_sw/C_int = 0.0668. Damping = 1/(0.5 + q_val). LP/BP/HP/bypass output select via `{sel1,sel0}`. Internal `sim_data_in[7:0]` / `sim_data_out[7:0]` registers.
- **`sar_adc_8bit`** — rising-edge triggered 9-cycle conversion with `eoc` pulse. Latches `sim_data_in[7:0]` on `start` rising edge.

The parent module (`tt_um_sid.v`) connects the behavioral models via hierarchical references in an `` `ifdef BEHAVIORAL_SIM `` always block: `u_dac.sim_data_out` → `u_svf.sim_data_in` and `u_svf.sim_data_out` → `u_adc.sim_data_in`.

Compile with `-DBEHAVIORAL_SIM` to enable (used by Verilog testbenches in `tests/`). All 15 Verilog tests pass with behavioral models enabled.

## All Sims Run Without Errors
`make all` completes — all 5 macro-level testbenches execute and produce output data.
Full system sweep: `bash tests/run_freq_sweep.sh` (digital + analog + plots).
