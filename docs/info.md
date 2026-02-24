<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This is a triple-voice SID (MOS 6581-inspired) synthesizer with a 12-bit Q8.4 State Variable Filter (SVF). It runs at 12 MHz with a ÷3 clock enable producing a 4 MHz voice pipeline (800 kHz effective per voice). A host microcontroller writes per-voice registers through a flat memory-mapped parallel interface and the chip produces 8-bit PWM audio outputs on `uo_out[0]` (unfiltered) and `uo_out[1]` (filtered).

**Architecture:**

- **Flat register interface** -- rising-edge-triggered writes via `ui_in[7]` (WE), `ui_in[4:3]` (voice select), `ui_in[2:0]` (register address), `uio_in[7:0]` (data). No SPI or I2C overhead.
- **3-voice pipelined datapath** -- a ÷3 clock divider produces a 4 MHz clock enable from the 12 MHz system clock. A mod-5 slot counter cycles through voices 0/1/2, giving each voice an 800 kHz effective update rate. 16-bit phase accumulators with 16-bit frequency registers provide ~12.2 Hz resolution across the full audio range.
- **Waveform generation** -- four waveform types (sawtooth, triangle, variable-width pulse, noise via shared 15-bit LFSR), AND-combined when multiple waveforms are selected. Sync and ring modulation are fully implemented with circular cross-voice connections (V0←V2, V1←V0, V2←V1).
- **ADSR envelope** -- 8-bit envelope (256 levels) per voice with per-voice ADSR parameters, 14-bit shared prescaler (clocked at 4 MHz), exponential decay, and a 4-state FSM (IDLE/ATTACK/DECAY/SUSTAIN). 9 distinct rate settings from ~256 µs to ~524 ms per full traverse.
- **3-voice mixer** -- accumulates the three 8-bit voice outputs (8×8 waveform×envelope product, upper byte) into a 10-bit accumulator and divides by 4 to produce an 8-bit mix.
- **State Variable Filter** (`filter` + `SVF_8bit`) -- 12-bit Q8.4 Chamberlin SVF with LP/BP/HP modes. Shift-add multiplies (no hardware multiplier). SID-compatible interface: 11-bit cutoff frequency, 4-bit resonance, per-voice filter routing, mode selection, and 4-bit master volume. ~1,567 cells.
- **PWM audio** (`pwm_audio`) -- two instances: unfiltered mix on `uo_out[0]`, filtered output on `uo_out[1]`. 8-bit PWM with a 255-clock period (~47.1 kHz at 12 MHz).

**Register map (voice_sel 0-2: per-voice, voice_sel 3: filter, selected by `ui_in[4:3]`):**

| Addr | Register | Description |
|------|----------|-------------|
| 0 | freq_lo | Frequency low byte [7:0] |
| 1 | freq_hi | Frequency high byte [15:8] |
| 2 | pw_lo | Pulse width low byte [7:0] |
| 3 | pw_hi | Pulse width high nibble [11:8] (bits [3:0] only) |
| 4 | attack | attack_rate[3:0] / decay_rate[7:4] (per voice) |
| 5 | sustain | sustain_level[3:0] / release_rate[7:4] (per voice) |
| 6 | waveform | {noise, pulse, saw, tri, test, ring, sync, gate} |

**Filter registers (voice_sel = 3):**

| Addr | Register | Description |
|------|----------|-------------|
| 0 | fc_lo | Filter cutoff low byte (bits [2:0] used) |
| 1 | fc_hi | Filter cutoff high byte [7:0] |
| 2 | res_filt | [7:4] resonance, [3:0] filter voice enable |
| 3 | mode_vol | [7:4] mode (V3OFF/HP/BP/LP), [3:0] master volume |

**Frequency formula:**

The 16-bit frequency register `{freq_hi, freq_lo}` sets the oscillator pitch:

```
f_out = freq_reg × 800,000 / 65,536  ≈  freq_reg × 12.207 Hz
```

Resolution: ~12.2 Hz. Range: 12.2 Hz (reg=1) to ~800 kHz (reg=65535). Useful audio range: 12 Hz to ~20 kHz.

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

A second-order (two-stage) RC low-pass filter on `uo_out[0]` recovers analog audio from the ~47.1 kHz PWM carrier:

```
uo_out[0] ---[3.3k]---+---[3.3k]---+---[1uF]---> Audio Out
                       |            |
                    [2.2nF]      [2.2nF]
                       |            |
                      GND          GND
```

Each stage has fc ≈ 22 kHz, passing the full 20 kHz audio band. A third stage (same values) can be added for better carrier rejection. Connect the output to headphones (via op-amp buffer) or a line-level amplifier input.
