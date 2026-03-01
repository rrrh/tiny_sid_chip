<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This is a triple-voice SID (MOS 6581-inspired) synthesizer with an on-chip switched-capacitor (SC) State Variable Filter. It runs at 24 MHz with a ÷3 clock enable producing an 8 MHz voice pipeline (1.6 MHz effective per voice). A host microcontroller writes per-voice registers through a flat memory-mapped parallel interface and the chip produces 8-bit PWM audio output on `uo_out[0]`.

**Architecture:**

- **Flat register interface** -- rising-edge-triggered writes via `ui_in[7]` (WE), `ui_in[4:3]` (voice select), `ui_in[2:0]` (register address), `uio_in[7:0]` (data). No SPI or I2C overhead.
- **3-voice pipelined datapath** -- a ÷3 clock divider produces an 8 MHz clock enable from the 24 MHz system clock. A mod-5 slot counter cycles through voices 0/1/2, giving each voice a 1.6 MHz effective update rate. 16-bit phase accumulators with 16-bit frequency registers provide ~24.4 Hz resolution across the full audio range.
- **Waveform generation** -- four waveform types (sawtooth, triangle, variable-width pulse, noise via shared 15-bit LFSR), AND-combined when multiple waveforms are selected. Sync and ring modulation are fully implemented with circular cross-voice connections (V0←V2, V1←V0, V2←V1).
- **ADSR envelope** -- 8-bit envelope (256 levels) per voice with per-voice ADSR parameters, 14-bit shared prescaler (clocked at 8 MHz), exponential decay, and a 4-state FSM (IDLE/ATTACK/DECAY/SUSTAIN). 9 distinct rate settings from ~128 µs to ~262 ms per full traverse.
- **3-voice mixer** -- accumulates the three 8-bit voice outputs (8×8 waveform×envelope product, upper byte) into a 10-bit accumulator and divides by 4 to produce an 8-bit mix.
- **Analog filter chain** -- the mixed digital audio is converted to analog via an 8-bit R-2R DAC (`r2r_dac_8bit`), filtered by a 2nd-order switched-capacitor State Variable Filter (`svf_2nd`, 2 OTAs + 2 MIM caps + SC resistors), and converted back to digital via an 8-bit SAR ADC (`sar_adc_8bit`). A programmable clock divider sets the SC switching frequency (fc tuning), and a 4-bit binary-weighted capacitor array sets Q directly from register values. LP/BP/HP modes via priority mux (HP > BP > LP), with bypass when no voices are routed or no mode is selected. Digital volume scaling (shift-add) is applied post-ADC.
- **2 kHz lowpass** (`output_lpf`) -- fixed single-pole IIR (6 dB/octave) between filter output and PWM input. Alpha = 1/128 (single shift, fc ≈ 1990 Hz), 10-bit unsigned accumulator (8.2 fixed-point), no multiplier.
- **PWM audio** (`pwm_audio`) -- single instance on `uo_out[0]`. 8-bit PWM with a 255-clock period (~94.1 kHz at 24 MHz).
- **Analog hard macros** -- three IHP SG13G2 130nm hard macros placed on-die: `r2r_dac_8bit` (38×48 µm), `svf_2nd` (62×72 µm), `sar_adc_8bit` (42×45 µm). Total macro area ~8,178 µm² (~12.9% of die). FC and Q tuning are digital (clock divider + cap switches), eliminating the need for a bias DAC.

**Clock tree:**

There is a single physical clock (`clk` at 24 MHz). All registers use `posedge clk`. Slower rates are implemented as clock enables gating register updates, not separate clock domains.

```
                         24 MHz clk
                            │
            ┌───────────────┼───────────────────────┐
            │               │                       │
            ▼               ▼                       ▼
      ┌──────────┐    ┌──────────┐            ┌──────────┐
      │ clk_div  │    │ wr_en_d  │            │ pwm_audio│
      │ ÷3 ctr   │    │ edge det │            │ 8-bit ctr│
      │ (2-bit)  │    └──────────┘            │ /255     │
      └────┬─────┘     24 MHz                 │ 94.1 kHz │
           │                                  └──────────┘
           ▼                                    24 MHz
      clk_en_8m                               (free-running)
       (8 MHz)
           │
     ┌─────┼──────────────────────┐
     │     │                      │
     ▼     ▼                      ▼
 ┌───────┐ ┌───────────────┐ ┌──────────┐
 │ slot  │ │ pipeline regs │ │ adsr_pre │
 │ mod-5 │ │ (V0/V1/V2     │ │ 14-bit   │
 │(3-bit)│ │  load/compute)│ │ prescaler│
 └───┬───┘ └───────────────┘ └──────────┘
     │
     ▼
 voice_active ──► acc/env/ast state (slots 0-2)
     │
     ▼
 mix_acc ──► mix_out (slot 3 latch)
     │
     ▼
 sample_valid ──► 1 clk pulse after slot 3
     │
     ├──► r2r_dac → svf_2nd → sar_adc  (continuous analog)
     ├──► output_lpf (IIR) @ 1.6 MHz
     └──► pwm_audio        @ 24 MHz (free-running)
```

| Domain | Rate | Drives |
|--------|------|--------|
| 24 MHz (`clk`) | 24 MHz | All flip-flops, PWM counter, write-enable edge detect |
| 8 MHz (`clk_en_8m`) | 8 MHz | Slot counter, pipeline loads, voice state updates, mix, ADSR prescaler |
| 1.6 MHz (`sample_valid`) | 1.6 MHz | output_lpf IIR (1 pulse per mod-5 frame) |
| Continuous | analog | R-2R DAC → SC SVF → SAR ADC (free-running conversion) |
| Noise LFSR | pitch-dependent | Edge-detected from voice 0 accumulator bit 11 |

**Register map** — full address = `{voice_sel[1:0], reg_addr[2:0]}`, selected by `ui_in[4:3]` (voice_sel) and `ui_in[2:0]` (reg_addr):

| Addr | Register | Description |
|------|----------|-------------|
| **Voice 0** (`voice_sel=0`) | | |
| 0x00 | freq_lo[0] | Frequency low byte [7:0] |
| 0x01 | freq_hi[0] | Frequency high byte [15:8] |
| 0x02 | pw_lo[0] | Pulse width low byte [7:0] |
| 0x03 | pw_hi[0] | Pulse width high nibble [11:8] (bits [3:0] only) |
| 0x04 | attack[0] | attack_rate[3:0] / decay_rate[7:4] |
| 0x05 | sustain[0] | sustain_level[3:0] / release_rate[7:4] |
| 0x06 | waveform[0] | {noise, pulse, saw, tri, test, ring, sync, gate} |
| 0x07 | — | unused |
| **Voice 1** (`voice_sel=1`) | | |
| 0x08 | freq_lo[1] | Frequency low byte [7:0] |
| 0x09 | freq_hi[1] | Frequency high byte [15:8] |
| 0x0A | pw_lo[1] | Pulse width low byte [7:0] |
| 0x0B | pw_hi[1] | Pulse width high nibble [11:8] (bits [3:0] only) |
| 0x0C | attack[1] | attack_rate[3:0] / decay_rate[7:4] |
| 0x0D | sustain[1] | sustain_level[3:0] / release_rate[7:4] |
| 0x0E | waveform[1] | {noise, pulse, saw, tri, test, ring, sync, gate} |
| 0x0F | — | unused |
| **Voice 2** (`voice_sel=2`) | | |
| 0x10 | freq_lo[2] | Frequency low byte [7:0] |
| 0x11 | freq_hi[2] | Frequency high byte [15:8] |
| 0x12 | pw_lo[2] | Pulse width low byte [7:0] |
| 0x13 | pw_hi[2] | Pulse width high nibble [11:8] (bits [3:0] only) |
| 0x14 | attack[2] | attack_rate[3:0] / decay_rate[7:4] |
| 0x15 | sustain[2] | sustain_level[3:0] / release_rate[7:4] |
| 0x16 | waveform[2] | {noise, pulse, saw, tri, test, ring, sync, gate} |
| 0x17 | — | unused |
| **Filter** (`voice_sel=3`) | | |
| 0x18 | fc_lo | Cutoff low byte [7:0] (bits [2:0] used in filt_fc) |
| 0x19 | fc_hi | Cutoff high byte [7:0] → filt_fc[10:7] drives d_fc[3:0] bias DAC |
| 0x1A | res_filt | [7:4] resonance → d_q[3:0] bias DAC, [3:0] per-voice filter enable |
| 0x1B | mode_vol | [7] V3OFF, [6:4] mode (HP/BP/LP) → svf_sel, [3:0] master volume |
| 0x1C–0x1F | — | unused |

**Filter register detail — analog macro mapping:**

| Register | Bits | Maps to | Destination |
|----------|------|---------|-------------|
| fc_lo + fc_hi | `{fc_hi, fc_lo[2:0]}` → `filt_fc[10:7]` | `d_fc[3:0]` | Clock divider LUT → `sc_clk` → SVF cutoff frequency |
| res_filt | `[7:4]` = `filt_res[3:0]` | `q[3:0]` | Direct to SC SVF binary-weighted C_Q capacitor array → Q / resonance |
| res_filt | `[3:0]` = `filt_en` | bypass control | bypass if `[2:0] == 0` (no voices routed to filter) |
| mode_vol | `[6:4]` = `filt_mode[2:0]` | `svf_sel[1:0]` | HP(10) > BP(01) > LP(00), bypass → 11 |
| mode_vol | `[3:0]` = `filt_vol` | volume scaling | post-ADC digital shift-add (÷16 per bit) |

**Frequency formula:**

The 16-bit frequency register `{freq_hi, freq_lo}` sets the oscillator pitch:

```
f_out = freq_reg × 1,600,000 / 65,536  ≈  freq_reg × 24.414 Hz
```

Resolution: ~24.4 Hz. Range: 24.4 Hz (reg=1) to ~1.6 MHz (reg=65535). Useful audio range: 24 Hz to ~20 kHz.

**Pulse width:**

The 12-bit pulse width `{pw_hi[3:0], pw_lo[7:0]}` is compared against `acc[15:4]`. A value of `0x800` gives a 50% duty cycle.

## How to test

Connect a microcontroller to the parallel interface pins and the PWM output to a low-pass filter:

1. Set frequency: write `freq_lo` (reg 0) and `freq_hi` (reg 1) for the desired voice
2. Set pulse width if using pulse waveform: write `pw_lo` (reg 2) and optionally `pw_hi` (reg 3)
3. Set ADSR: write attack/decay rates (reg 4) and sustain level/release rate (reg 5) for each voice individually
4. Start the note: write waveform register (reg 6) with the desired waveform bit(s) and gate=1
5. Stop the note: write waveform register with gate=0 to trigger release
6. Repeat for voices 1 and 2 (`ui_in[4:3]` = 01, 10) for polyphony

The write sequence for each register: set `ui_in[2:0]` = address, `ui_in[4:3]` = voice, `uio_in` = data, then pulse `ui_in[7]` high for one clock cycle.

**Sync modulation:** Set bit 1 of the waveform register. Hard-syncs the voice's accumulator to the sync source (V0←V2, V1←V0, V2←V1), resetting the phase on the source voice's MSB rising edge.

**Ring modulation:** Set bit 2 of the waveform register. XORs the sync source voice's accumulator MSB into the triangle waveform's MSB, producing bell-like tones.

## External hardware

A second-order (two-stage) RC low-pass filter on `uo_out[0]` recovers analog audio from the ~94.1 kHz PWM carrier. The single PWM output carries the mixed and filtered audio (filter bypass passes unfiltered mix when filter routing is disabled):

```
uo_out[0] ---[3.3k]---+---[3.3k]---+---[1uF]---> Audio Out
                       |            |
                    [2.2nF]      [2.2nF]
                       |            |
                      GND          GND
```

Each stage has fc ≈ 22 kHz, passing the full 20 kHz audio band. A third stage (same values) can be added for better carrier rejection. Connect the output to headphones (via op-amp buffer) or a line-level amplifier input.
