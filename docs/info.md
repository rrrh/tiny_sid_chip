<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This is a triple-voice SID (MOS 6581-inspired) synthesizer implemented in a single Verilog module. A host microcontroller writes per-voice registers through a flat memory-mapped parallel interface and the chip produces an 8-bit PWM audio output on `uo_out[0]`.

**Architecture:**

- **Flat register interface** -- rising-edge-triggered writes via `ui_in[7]` (WE), `ui_in[4:3]` (voice select), `ui_in[2:0]` (register address), `uio_in[7:0]` (data). No SPI or I2C overhead.
- **3-voice pipelined datapath** -- a mod-5 slot counter cycles through voices 0/1/2 at 5 MHz, giving each voice a 1 MHz effective update rate. 16-bit phase accumulators with 8-bit frequency registers provide ~15.3 Hz frequency resolution.
- **Waveform generation** -- four waveform types (sawtooth, triangle, variable-width pulse, noise via shared 15-bit LFSR), AND-combined when multiple waveforms are selected. Sync and ring modulation are fully implemented with circular cross-voice connections (V0←V2, V1←V0, V2←V1).
- **ADSR envelope** -- 8-bit envelope (256 levels) per voice with per-voice ADSR parameters, 14-bit shared prescaler, exponential decay, and a 4-state FSM (IDLE/ATTACK/DECAY/SUSTAIN). 9 distinct rate settings from ~205 µs to ~419 ms per full traverse.
- **3-voice mixer** -- accumulates the three 8-bit voice outputs (8×8 waveform×envelope product, upper byte) into a 10-bit accumulator and divides by 4 to produce an 8-bit mix.
- **PWM audio** (`pwm_audio`) -- 8-bit PWM with a 255-clock period (~19.6 kHz at 5 MHz).

**Register map (all per-voice, selected by `ui_in[4:3]`):**

| Addr | Register | Description |
|------|----------|-------------|
| 0 | freq | Frequency[7:0] (8-bit phase accumulator increment) |
| 1 | -- | Reserved |
| 2 | pw | Pulse width[7:0] (duty cycle threshold) |
| 3 | -- | Reserved |
| 4 | attack | attack_rate[3:0] / decay_rate[7:4] (per voice) |
| 5 | sustain | sustain_level[3:0] / release_rate[7:4] (per voice) |
| 6 | waveform | {noise, pulse, saw, tri, test, ring, sync, gate} |

**Frequency formula:**

```
f_out = freq_reg × 1,000,000 / 65,536  ≈  freq_reg × 15.26 Hz
```

Range: 15.3 Hz (reg=1) to 3,891 Hz (reg=255).

## How to test

Connect a microcontroller to the parallel interface pins and the PWM output to a low-pass filter:

1. Set frequency: write `freq` (reg 0) for the desired voice (8-bit only, no high byte needed)
2. Set pulse width if using pulse waveform: write `pw` (reg 2)
3. Set ADSR: write attack/decay rates (reg 4) and sustain level/release rate (reg 5) for each voice individually
4. Start the note: write waveform register (reg 6) with the desired waveform bit(s) and gate=1
5. Stop the note: write waveform register with gate=0 to trigger release
6. Repeat for voices 1 and 2 (`ui_in[4:3]` = 01, 10) for polyphony

The write sequence for each register: set `ui_in[2:0]` = address, `ui_in[4:3]` = voice, `uio_in` = data, then pulse `ui_in[7]` high for one clock cycle.

**Sync modulation:** Set bit 1 of the waveform register. Hard-syncs the voice's accumulator to the sync source (V0←V2, V1←V0, V2←V1), resetting the phase on the source voice's MSB rising edge.

**Ring modulation:** Set bit 2 of the waveform register. XORs the sync source voice's accumulator MSB into the triangle waveform's MSB, producing bell-like tones.

## External hardware

A third-order (three-stage) RC low-pass filter on `uo_out[0]` is recommended to recover the analog audio:

```
uo_out[0] ---[3.3k]---+---[3.3k]---+---[3.3k]---+---[1uF]---> Audio Out
                       |            |             |
                    [4.7nF]      [4.7nF]       [4.7nF]
                       |            |             |
                      GND          GND           GND
```

The third stage provides steeper rolloff of the ~19.6 kHz PWM carrier, yielding a cleaner audio signal. Connect the output to headphones (via op-amp buffer) or a line-level amplifier input.
