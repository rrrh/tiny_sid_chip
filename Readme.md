# Triple SID Voice Synthesizer (TT-IHP)

Three time-multiplexed SID voices with 8-bit ADSR envelopes, sync and ring
modulation, controlled via a flat parallel register interface, with 8-bit PWM
audio output. Designed for a Tiny Tapeout 1x2 tile on the IHP SG13G2 130nm
process at 24 MHz.

[View the GDS layout](https://rrrh.github.io/tiny_sid_chip/)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Pin Mapping](#pin-mapping)
4. [Register Reference](#register-reference)
5. [Write Interface Protocol](#write-interface-protocol)
6. [Audio Output and PWM](#audio-output-and-pwm)
7. [Audio Recovery Filter](#audio-recovery-filter)
8. [Usage Guide](#usage-guide)
9. [Design Constraints](#design-constraints)

---

## Overview

This design implements a triple-voice sound synthesizer inspired by the
MOS 6581/8580 SID chip from the Commodore 64. Three independent voices
share a single compute pipeline via time-multiplexing, each providing
four classic waveform types (sawtooth, triangle, pulse, noise), a full
8-bit ADSR amplitude envelope with exponential decay, hard sync, and ring
modulation -- all packed into a Tiny Tapeout 1x2 tile.

A host microcontroller (Arduino, RP2040, ESP32, etc.) writes per-voice
control registers through a simple flat parallel interface using 8-bit
data and a rising-edge write strobe. The three voice outputs are mixed
and output as an 8-bit PWM signal on `uo_out[0]` at ~94.1 kHz, requiring
only a passive RC low-pass filter to produce analog audio.

### Key Features

- Three independent voices, time-multiplexed through one shared pipeline
- Four waveforms per voice: sawtooth, triangle, pulse (variable width), noise
- AND-combining of simultaneous waveforms (SID-compatible)
- Hard sync modulation (circular: V0←V2, V1←V0, V2←V1)
- Ring modulation (XOR sync source MSB into triangle)
- 8-bit ADSR envelope per voice (256 amplitude levels, exponential decay)
- Per-voice ADSR parameters (attack, decay, sustain, release)
- 4-state envelope FSM (IDLE, ATTACK, DECAY, SUSTAIN)
- 9 envelope rate settings from ~128 µs to ~262 ms full traverse
- 16-bit frequency register, 16-bit phase accumulator (~24.4 Hz resolution, full audio range)
- 15-bit LFSR noise generator, accumulator-clocked from voice 0
- 3-voice mixer with 10-bit accumulator and ÷4 scaling
- 9-bit Q8.1 State Variable Filter (SVF) with LP/BP/HP priority mux (HP > BP > LP), shift-add multiply
- 3-bit alpha1 (fc[10:8], 3-term /8) and 2-bit alpha2 ((15-res)>>2, 2-term /4)
- SID-compatible filter interface: 11-bit cutoff, 4-bit resonance, per-voice routing, 4-bit volume
- Fixed 6 dB/octave lowpass (fc ≈ 2000 Hz) before PWM output — single-pole IIR, alpha = 1/128 (single shift)
- Single 8-bit PWM audio output on uo_out[0] (~94.1 kHz carrier at 24 MHz)
- Flat parallel write interface (no SPI/I2C overhead)
- Mod-5 pipeline: 1.6 MHz effective per voice at 8 MHz voice clock (24 MHz ÷3)
- Fits in a Tiny Tapeout 1x2 tile on IHP SG13G2 130nm (~77% utilization, CTS enabled)

### Source Files

| File | Description |
|------|-------------|
| `src/tt_um_sid.v` | Top-level: register banks, voice pipeline, mixer, filter, pin mapping |
| `src/pwm_audio.v` | 8-bit PWM audio output (255-clock period) |
| `src/filter.v` | SID filter wrapper: bypass, mode mixing, volume scaling |
| `src/SVF_8bit.v` | 9-bit Q8.1 State Variable Filter core (shift-add, 3-bit alpha1, 2-bit alpha2) |
| `src/output_lpf.v` | Fixed 6 dB/octave lowpass (fc ≈ 2000 Hz), single-pole IIR before PWM |

---

## Architecture

![Architecture Block Diagram](docs/architecture.svg)

<details><summary>ASCII fallback</summary>

```
                 ┌─────────────────────────────────────────────────────────────┐
 ui_in[2:0] ──┐  │              Mod-5 Voice Pipeline (×3 TDM)                │
 ui_in[4:3] ──┤  │  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
 ui_in[7]   ──┤  │  │ Phase   │  │ Waveform  │  │  ADSR    │  │ Envelope │  │
              ├──┤  │ Acc     │──│ Gen       │──│ Envelope │──│ Scaling  │──┤
 uio_in ──────┤  │  │ (16-bit)│  │(saw/tri/  │  │(8-bit    │  │ (8×8→8)  │  │  ┌───────┐
              │  │  │  8-bit  │  │ pulse/    │  │ per      │  │          │  ├──│ Mixer │
 Register     │  │  │  freq   │  │ noise)    │  │ voice)   │  │          │  │  │ (÷4)  │
 Banks        │  │  └─────────┘  └──────────┘  └──────────┘  └──────────┘  │  └───┬───┘
 (all per-    │  │                                                          │      │
  voice)      │  │  ÷3 clk_en → 8 MHz voice pipeline, 1.6 MHz per voice    │      ▼
              │  └─────────────────────────────────────────────────────────────┘  ┌──────────┐  ┌──────────┐  ┌──────────┐
              │                                                                  │ R-2R DAC │──│  SC SVF  │──│ SAR ADC  │
              │   Analog signal chain:                                           │ (8-bit)  │  │(2nd ord) │  │ (8-bit)  │
              │   R-2R DAC → SC SVF → SAR ADC → volume scaling                  └──────────┘  └──────────┘  └─────┬────┘
              │                                                                                                    │
              │                                                               ┌──────────┐  ┌─────────┐           │
              │                                                               │output_lpf│──│pwm_audio│── uo_out[0]
              │                                                               │(2000 Hz) │  │ (8-bit) │           │
              │                                                               └─────┬────┘  └─────────┘           │
              │                                                                     │        24 MHz               │
              │                                                                     └─────────────────────────────┘
```

</details>

**Signal flow:**

1. The host writes per-voice registers (frequency, pulse width, waveform,
   attack/decay, sustain/release) via the flat parallel interface. All
   registers are per-voice. A rising edge on `ui_in[7]` latches the data.

2. A ÷3 clock divider produces an 8 MHz clock enable from the 24 MHz system
   clock. A mod-5 slot counter (gated by the 8 MHz enable) cycles through
   5 slots. Slots 0-2 compute voices 0-2 respectively, slot 3 latches the
   mixer output and preloads voice 0's pipeline registers, and slot 4 is an
   idle/preload slot. Each voice is updated once per 5-slot frame (1.6 MHz
   effective per voice).

3. Each voice's 16-bit phase accumulator advances by the 16-bit frequency
   register value every frame. This provides ~24.4 Hz frequency resolution
   across the full audio range. Hard sync resets the accumulator when the
   sync source voice's MSB has a rising edge.

4. The waveform generator derives sawtooth, triangle, pulse, and noise
   outputs from the accumulator state and a shared 15-bit LFSR (clocked from
   voice 0's accumulator bit 11). Selected waveforms are AND-combined into
   an 8-bit value. Ring modulation XORs the sync source's accumulator MSB
   into the triangle waveform's fold bit.

5. The 8-bit waveform is multiplied by the 8-bit ADSR envelope to produce
   a 16-bit product; the upper 8 bits are taken as the voice output.

6. The mixer accumulates three 8-bit voice outputs into a 10-bit accumulator
   over 3 slots, then divides by 4 (right-shift by 2) to produce an 8-bit
   mix sample for the PWM module.

7. A fixed single-pole IIR lowpass (`output_lpf`) with fc ≈ 2000 Hz and
   6 dB/octave rolloff smooths the mix before PWM conversion. It uses
   a single arithmetic right shift (alpha = 1/128, no multiplier) with
   a 10-bit unsigned accumulator (8.2 fixed-point).

8. `pwm_audio` converts the filtered sample into a PWM signal at
   ~94.1 kHz (running at full 24 MHz). An external RC low-pass filter
   recovers analog audio.

---

## Pin Mapping

### Input Pins (`ui_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `ui_in[2:0]` | `reg_addr` | Register address (0--6) |
| `ui_in[4:3]` | `voice_sel` | Voice select: 0=voice 0, 1=voice 1, 2=voice 2, 3=filter |
| `ui_in[6:5]` | -- | Unused |
| `ui_in[7]` | `wr_en` | Write enable (rising-edge triggered) |

### Data Input Pins (`uio_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uio_in[7:0]` | `wr_data` | 8-bit write data. All 8 pins are inputs. |

### Output Pins (`uo_out`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uo_out[0]` | `pwm_out` | PWM audio output (filtered or bypass). Connect to RC filter. |
| `uo_out[7:1]` | -- | Tied low. |

### Bidirectional Pin Direction

All `uio` pins are configured as inputs (`uio_oe = 0x00`).

---

## Register Reference

Seven registers per voice (voice_sel 0--2), plus four filter/volume
registers (voice_sel 3).

### Register 0: Frequency Low Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              freq_lo[7:0]              ]
```

### Register 1: Frequency High Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              freq_hi[7:0]              ]
```

The 16-bit frequency register `{freq_hi, freq_lo}` is the phase accumulator
increment. The 16-bit accumulator advances at an effective rate of 1.6 MHz
(24 MHz ÷3 ÷5 slots). The oscillator frequency is:

```
f_out = freq_reg × 1,600,000 / 65,536  ≈  freq_reg × 24.414 Hz
```

**Frequency calculation:**

```
freq_reg = round(desired_Hz × 65,536 / 1,600,000)
         ≈ desired_Hz × 0.04096
```

Resolution: ~24.4 Hz. Range: 24.4 Hz (reg=1) to ~1.6 MHz (reg=65535).
Useful audio range: 24 Hz to ~20 kHz.

| freq_reg | freq_hi | freq_lo | Output Frequency | Note |
|----------|---------|---------|-----------------|------|
| 0 | 0x00 | 0x00 | 0 Hz | Silence |
| 1 | 0x00 | 0x01 | ~24.4 Hz | Lowest pitch |
| 11 | 0x00 | 0x0B | ~269 Hz | ~C4 |
| 18 | 0x00 | 0x12 | ~440 Hz | ~A4 |
| 86 | 0x00 | 0x56 | ~2,100 Hz | ~C7 |
| 172 | 0x00 | 0xAC | ~4,199 Hz | ~C8 |
| 819 | 0x03 | 0x33 | ~19,995 Hz | ~Limit of hearing |

### Register 2: Pulse Width Low Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              pw_lo[7:0]                ]
```

### Register 3: Pulse Width High Nibble

```
Bit:   7    6    5    4    3    2    1    0
     [    (unused)       ][ pw_hi[3:0]        ]
```

The 12-bit pulse width `{pw_hi, pw_lo}` sets the pulse waveform duty cycle
by comparison with the accumulator upper 12 bits (`acc[15:4] >= pw`):

- `pw = 0x000`: Pulse always high (near DC)
- `pw = 0x800`: ~50% duty cycle (square wave)
- `pw = 0xFFF`: Narrow pulse (~0.02% duty)

### Register 4: Attack / Decay Rates (8-bit, per-voice)

```
Bit:   7    6    5    4    3    2    1    0
     [  decay_rate[3:0]  ][ attack_rate[3:0] ]
```

| Field | Bits | Description |
|-------|------|-------------|
| `attack_rate` | `[3:0]` | How fast the envelope rises from 0 to 255 |
| `decay_rate` | `[7:4]` | How fast the envelope falls from 255 to sustain level (with exponential decay) |

### Register 5: Sustain Level / Release Rate (8-bit, per-voice)

```
Bit:   7    6    5    4    3    2    1    0
     [ release_rate[3:0] ][sustain_level[3:0]]
```

| Field | Bits | Description |
|-------|------|-------------|
| `sustain_level` | `[3:0]` | Sustain amplitude (0--15). The 8-bit envelope holds at `{sustain_level, 4'hF}` (i.e. 0x0F, 0x1F, ..., 0xFF). |
| `release_rate` | `[7:4]` | How fast the envelope falls to 0 after gate off (with exponential decay) |

### Register 6: Waveform Control (8-bit, per-voice)

```
Bit:   7      6      5        4        3     2     1     0
     [noise][pulse][sawtooth][triangle][test][ring][sync][gate]
```

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `gate` | Set to 1 to start a note (attack). Clear to 0 to release. |
| 1 | `sync` | Hard sync: resets phase accumulator on sync source voice MSB rising edge. Circular routing: V0←V2, V1←V0, V2←V1. |
| 2 | `ring` | Ring modulation: XORs sync source voice accumulator MSB into triangle waveform fold bit, producing bell-like timbres. |
| 3 | `test` | Forces oscillator accumulator to 0 while held. |
| 4 | `triangle` | Enable triangle waveform. |
| 5 | `sawtooth` | Enable sawtooth waveform. |
| 6 | `pulse` | Enable pulse waveform (duty cycle set by reg 2). |
| 7 | `noise` | Enable noise waveform (shared 15-bit LFSR, accumulator-clocked from voice 0). |

When multiple waveform bits are set, their outputs are bitwise
AND-combined (starting from 0xFF, each enabled waveform ANDs its value).
This matches the real SID's behavior where simultaneous waveforms produce
a bitwise AND of their individual outputs.

### Filter Registers (voice_sel = 3)

Four registers control the on-chip analog filter chain (R-2R DAC → SC SVF
→ SAR ADC → digital volume scaling). These are accessed with `ui_in[4:3]`
= 3 (voice_sel = 3).

#### Register 0 (addr 0x18): Cutoff Low Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              fc_lo[7:0]                ]
```

Only bits `[2:0]` are used in the cutoff frequency calculation.

#### Register 1 (addr 0x19): Cutoff High Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              fc_hi[7:0]                ]
```

The 11-bit cutoff `{fc_hi, fc_lo[2:0]}` maps bits `[10:7]` to a 4-bit
code (`d_fc[3:0]`) that selects the SC switching clock divider from a
16-entry LUT, setting the filter center frequency (~250 Hz to ~16 kHz).

#### Register 2 (addr 0x1A): Resonance / Filter Enable

```
Bit:   7    6    5    4    3    2    1    0
     [  filt_res[3:0]   ][ filt_en[3:0]      ]
```

| Field | Bits | Description |
|-------|------|-------------|
| `filt_en` | `[3:0]` | Per-voice filter routing: bit 0 = voice 0, bit 1 = voice 1, bit 2 = voice 2. Filter is bypassed if `[2:0]` are all zero. |
| `filt_res` | `[7:4]` | Resonance (Q). Drives the 4-bit binary-weighted C_Q capacitor array in the SC SVF. Higher values = lower Q (less resonance). |

#### Register 3 (addr 0x1B): Mode / Volume

```
Bit:   7    6    5    4    3    2    1    0
     [V3OFF][HP ][BP ][LP ][  filt_vol[3:0]   ]
```

| Field | Bits | Description |
|-------|------|-------------|
| `filt_vol` | `[3:0]` | Master volume (0--15). Post-ADC digital shift-add scaling. |
| `LP` | `[4]` | Enable lowpass output from SVF. |
| `BP` | `[5]` | Enable bandpass output from SVF. |
| `HP` | `[6]` | Enable highpass output from SVF. Priority: HP > BP > LP. |
| `V3OFF` | `[7]` | Disconnect voice 3 from mixer output (filter-only routing). |

### Analog Signal Chain

The mixed digital audio passes through an on-chip analog processing chain
before reaching the PWM output:

```
  Mix (8-bit) → R-2R DAC → SC SVF → SAR ADC → Volume Scaling → output_lpf → PWM
                (8-bit)    (2nd ord)  (8-bit)    (digital)       (IIR)
```

1. **R-2R DAC** (`r2r_dac_8bit`, 38×48 µm) — converts the 8-bit digital
   mix to an analog voltage.
2. **SC SVF** (`svf_2nd`, 62×72 µm) — 2nd-order switched-capacitor State
   Variable Filter with LP/BP/HP outputs. Center frequency is set by a
   programmable clock divider (16 steps, ~250 Hz to ~16 kHz). Q is set by
   a 4-bit binary-weighted capacitor array.
3. **SAR ADC** (`sar_adc_8bit`, 42×45 µm) — converts the filtered analog
   signal back to 8-bit digital.
4. **Volume Scaling** — digital shift-add volume control using `filt_vol[3:0]`.
5. **Output LPF** (`output_lpf`) — fixed 2 kHz single-pole IIR smoothing
   before PWM conversion.

When the filter is bypassed (no voices routed or no mode selected), the
digital mix passes directly to the output LPF, skipping the analog chain.

### Envelope Rate Table

The ADSR uses a 14-bit free-running prescaler (LSB fixed to 0). Each rate
value selects which prescaler bits must all be 1 for an envelope tick. The
8-bit envelope counter steps by 1 per tick, so a full 0→255 traverse takes
256 ticks. Decay and release use exponential adjustment (the rate slows as
the envelope decreases).

| Rate | Check bits | Period | Full Traverse (256 ticks) |
|------|-----------|--------|--------------------------|
| 0 | &pre[2:1] | 4 clks | ~128 µs |
| 1 | &pre[3:1] | 8 clks | ~256 µs |
| 2 | &pre[4:1] | 16 clks | ~512 µs |
| 3 | &pre[5:1] | 32 clks | ~1.0 ms |
| 4 | &pre[6:1] | 64 clks | ~2.0 ms |
| 5 | &pre[7:1] | 128 clks | ~4.1 ms |
| 6 | &pre[8:1] | 256 clks | ~8.2 ms |
| 7 | &pre[9:1] | 512 clks | ~16.4 ms |
| 8--15 | &pre[13:1] | 8192 clks | ~262 ms |

Formula: `traverse_time = 256 × period / 8,000,000` seconds (prescaler clocks at 8 MHz).

### ADSR Envelope FSM

The envelope uses a 4-state FSM: IDLE → ATTACK → DECAY → SUSTAIN.

- **IDLE**: Envelope is 0. Waits for gate rising edge to transition to ATTACK.
- **ATTACK**: Envelope increments toward 255 at the attack rate. Transitions to DECAY when envelope reaches 255. Gate off triggers release.
- **DECAY**: Envelope decrements toward sustain level with exponential decay. Transitions to SUSTAIN when envelope reaches `{sustain_level, 4'hF}`. Gate off triggers release.
- **SUSTAIN**: Envelope holds at sustain level. Gate off triggers release.

Release is handled by a separate `releasing` flag that decrements the envelope toward 0 with exponential decay from any state when the gate is cleared.

---

## Write Interface Protocol

The register interface uses a simple parallel bus with rising-edge write
strobe. No SPI or I2C protocol is needed.

### Write Sequence

To write one register:

1. Set `ui_in[2:0]` = register address (0-6)
2. Set `ui_in[4:3]` = voice select (0, 1, or 2)
3. Set `uio_in[7:0]` = data byte
4. Pulse `ui_in[7]` high for at least one clock cycle
5. Return `ui_in[7]` low before the next write

The register latches on the rising edge of `ui_in[7]`. The minimum write
cycle is 3 clock cycles (125 ns at 24 MHz): one to set up address/data,
one with WE high, one with WE low.

### Timing Diagram

```
            ┌───────┐                         ┌───────┐
  ui_in[7]  │       │                         │       │
 ───────────┘       └─────────────────────────┘       └─────
                ^                                 ^
          write latched                     write latched

  ui_in[4:0]  <  voice | addr  >             < voice | addr  >

  uio_in      <    data byte   >             <  data byte    >
```

### Write Function (C / Arduino)

```c
// Write an 8-bit value to a SID register
// addr: 0-6  voice: 0-3 (3=filter)  data: 0-255
void sid_write(uint8_t addr, uint8_t data, uint8_t voice) {
    uint8_t ui = (addr & 0x07) | ((voice & 0x03) << 3);
    set_ui_in(ui);           // address + voice, WE=0
    set_uio_in(data);        // data byte
    set_ui_in(ui | 0x80);    // assert WE (rising edge triggers write)
    set_ui_in(ui);           // deassert WE
}
```

---

## Audio Output and PWM

### How It Works

The `pwm_audio` module converts the 8-bit mixer output into a
pulse-width modulated signal. A free-running 8-bit counter cycles from
0 to 254 (period = 255 clocks). The output is high when the counter is
less than the sample value:

```
pwm_out = (count < sample) ? 1 : 0
```

### Signal Characteristics

| Parameter | Value |
|-----------|-------|
| Input resolution | 8 bits (unsigned, 0--255) |
| Output | 1-bit PWM on `uo_out[0]` |
| PWM period | 255 clocks |
| PWM frequency @ 24 MHz | ~94.1 kHz |
| Duty cycle range | 0% (sample=0) to 100% (sample=255) |
| Audio bandwidth | Up to ~23.5 kHz (Nyquist) |

---

## Audio Recovery Filter

The PWM output on `uo_out[0]` swings between 0 and VDD. A second-order
passive RC low-pass filter recovers the analog audio signal. The ~94.1 kHz
PWM carrier is well above the 20 kHz audio band.

### Recommended Circuit

```
uo_out[0] ---[R1]---+---[R2]---+---[Cac]---> Audio Out
                     |          |
                    [C1]       [C2]
                     |          |
                    GND        GND
```

### Component Values

| R (per stage) | C (per stage) | Per-stage fc | Combined rolloff | @ 94 kHz |
|---------------|---------------|-------------|-----------------|-----------|
| 3.3 kΩ | 2.2 nF | ~22 kHz | -12 dB/oct (2nd order) | ~-25 dB |

- **Cac** = 1 µF ceramic -- DC blocking capacitor after the filter.
- For driving low-impedance loads (headphones), add a unity-gain op-amp
  buffer after the filter.
- A third-order (three-stage, same values) filter can be added for better
  carrier rejection.

---

## Usage Guide

### Minimal Wiring

```
MCU                    TT Chip                   Audio
-----------           ----------------          -------
GPIO (D0)   --------> ui_in[0]  addr[0]
GPIO (D1)   --------> ui_in[1]  addr[1]
GPIO (D2)   --------> ui_in[2]  addr[2]
GPIO (D3)   --------> ui_in[3]  voice[0]
GPIO (D4)   --------> ui_in[4]  voice[1]
GPIO (WE)   --------> ui_in[7]  write enable
GPIO (D5-12)--------> uio_in[7:0]  data bus
                       uo_out[0] --[3.3k]--+--[3.3k]--+--[1uF]--> amp
                                           |          |
                                        [2.2nF]    [2.2nF]
                                           |          |
                                          GND        GND
```

### Playing a Note (Voice 0, Sawtooth ~440 Hz)

```c
// freq_reg = round(440 * 65536 / 1600000) = 18
sid_write(0, 18, 0);    // freq_lo = 0x12
sid_write(1, 0, 0);     // freq_hi = 0x00
sid_write(4, 0x00, 0);  // attack=0 (fastest), decay=0
sid_write(5, 0x0F, 0);  // sustain=15 (max), release=0
sid_write(6, 0x21, 0);  // sawtooth + gate ON

delay(500);              // hold note for 500 ms

sid_write(6, 0x20, 0);  // gate OFF (release begins)
```

### Three-Voice Chord (C Major)

```c
// C4 ≈ 262 Hz → freq_reg = round(262 * 65536 / 1600000) = 11
sid_write(0, 11, 0); sid_write(1, 0, 0);
sid_write(4, 0x00, 0); sid_write(5, 0x0F, 0);
sid_write(6, 0x21, 0);  // Voice 0: sawtooth C4

// E4 ≈ 330 Hz → freq_reg = round(330 * 65536 / 1600000) = 14
sid_write(0, 14, 1); sid_write(1, 0, 1);
sid_write(4, 0x00, 1); sid_write(5, 0x0F, 1);
sid_write(6, 0x11, 1);  // Voice 1: triangle E4

// G4 ≈ 392 Hz → freq_reg = round(392 * 65536 / 1600000) = 16
sid_write(0, 16, 2); sid_write(1, 0, 2);
sid_write(2, 0x00, 2); sid_write(3, 0x08, 2);  // pw = 0x800 (50%)
sid_write(4, 0x00, 2); sid_write(5, 0x0F, 2);
sid_write(6, 0x41, 2);  // Voice 2: pulse G4
```

### Sound Recipes

#### Simple Square Wave (8-bit Game Style)

```c
sid_write(0, freq_reg & 0xFF, v);
sid_write(1, freq_reg >> 8, v);
sid_write(2, 0x00, v); sid_write(3, 0x08, v);  // pw = 0x800, 50% duty
sid_write(4, 0x00, v);    // instant attack/decay
sid_write(5, 0x0F, v);    // max sustain, instant release
sid_write(6, 0x41, v);    // pulse + gate
```

#### Drum Hit (Noise with Fast Decay)

```c
sid_write(0, 0xFF, v);    // high freq noise
sid_write(4, 0xA0, v);    // instant attack, rate-10 decay
sid_write(5, 0xA0, v);    // sustain=0, rate-10 release
sid_write(6, 0x81, v);    // noise + gate
// Naturally decays to silence
```

#### Pad (Triangle with Slow Envelope)

```c
sid_write(0, freq_reg & 0xFF, v);
sid_write(1, freq_reg >> 8, v);
sid_write(4, 0x8A, v);    // attack=10 (~524ms), decay=8 (~524ms)
sid_write(5, 0x8C, v);    // sustain=12, release=8
sid_write(6, 0x11, v);    // triangle + gate
```

#### Bell (Ring Modulation)

```c
// Voice 0: modulator at higher frequency
sid_write(0, 38, 0);     // ~928 Hz modulator
sid_write(6, 0x11, 0);   // triangle + gate (modulator)

// Voice 1: carrier with ring mod enabled
sid_write(0, 11, 1);     // ~269 Hz carrier (C4)
sid_write(4, 0x50, 1);   // instant attack, rate-5 decay
sid_write(5, 0x54, 1);   // sustain=4, rate-5 release
sid_write(6, 0x15, 1);   // triangle + ring + gate
```

### Frequency Table (Equal Temperament, A4=440 Hz)

```
freq_reg = round(Hz × 65,536 / 1,600,000)
```

| Note | Hz | freq_reg | freq_hi | freq_lo |
|------|----|----------|---------|---------|
| C3 | 130.8 | 5 | 0x00 | 0x05 |
| D3 | 146.8 | 6 | 0x00 | 0x06 |
| E3 | 164.8 | 7 | 0x00 | 0x07 |
| G3 | 196.0 | 8 | 0x00 | 0x08 |
| A3 | 220.0 | 9 | 0x00 | 0x09 |
| C4 | 261.6 | 11 | 0x00 | 0x0B |
| E4 | 329.6 | 14 | 0x00 | 0x0E |
| G4 | 392.0 | 16 | 0x00 | 0x10 |
| A4 | 440.0 | 18 | 0x00 | 0x12 |
| C5 | 523.3 | 21 | 0x00 | 0x15 |
| A5 | 880.0 | 36 | 0x00 | 0x24 |
| C6 | 1046.5 | 43 | 0x00 | 0x2B |
| C7 | 2093.0 | 86 | 0x00 | 0x56 |
| C8 | 4186.0 | 172 | 0x00 | 0xAC |

### Reset and Initialization

After power-on or chip reset (`rst_n` asserted low), all registers are
cleared to zero. All voices are silent. No initialization sequence is
required.

To silence the output at any time:
- Clear the gate bit: `sid_write(6, waveform & 0xFE, voice)`
- Set frequency to 0: `sid_write(0, 0, v)`
- Set the test bit: `sid_write(6, 0x08, v)`

---

## Design Constraints

| Parameter | Value |
|-----------|-------|
| Target technology | IHP SG13G2 130nm SiGe BiCMOS |
| Tile size | Tiny Tapeout 1x2 |
| Core supply (VDD) | 1.2V |
| I/O supply (VDDIO) | 3.3V |
| System clock | 24 MHz (41.7 ns period) |
| Voice pipeline clock | 8 MHz (÷3 clock enable) |
| Pipeline | Mod-5 slot counter (1.6 MHz effective per voice) |
| Core utilization | ~77% (with CTS clock tree) |
| Voice count | 3 (time-multiplexed) |
| Frequency resolution | ~24.4 Hz (16-bit freq, 16-bit acc, 1.6 MHz effective) |
| Envelope depth | 8-bit (256 levels, exponential decay) |
| ADSR prescaler | 14-bit (shared, free-running at 8 MHz) |
| Noise generator | 15-bit LFSR, accumulator-clocked from voice 0 |
| Voice output | 8-bit (8×8 waveform×envelope product, upper byte) |
| PWM output frequency | ~94.1 kHz |
| Audio bandwidth | Up to ~47 kHz (Nyquist) |
| Write interface speed | 1 register per 125 ns (3 clocks) |
