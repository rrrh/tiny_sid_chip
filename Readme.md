# Triple SID Voice Synthesizer (TT-IHP)

Three time-multiplexed SID voices with 8-bit ADSR envelopes, sync and ring
modulation, controlled via a flat parallel register interface, with 8-bit PWM
audio output. Designed for a Tiny Tapeout 1x2 tile on the IHP SG13G2 130nm
process at 5 MHz.

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
and output as an 8-bit PWM signal on `uo_out[0]` at ~19.6 kHz, requiring
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
- 9 envelope rate settings from ~205 µs to ~419 ms full traverse
- 8-bit frequency register, 16-bit phase accumulator (~15.3 Hz resolution)
- 15-bit LFSR noise generator, accumulator-clocked from voice 0
- 3-voice mixer with 10-bit accumulator and ÷4 scaling
- 8-bit PWM audio output (~19.6 kHz carrier at 5 MHz)
- Flat parallel write interface (no SPI/I2C overhead)
- Mod-5 pipeline: 1 MHz effective per voice at 5 MHz system clock
- Fits in a Tiny Tapeout 1x2 tile on IHP SG13G2 130nm

### Source Files

| File | Description |
|------|-------------|
| `src/tt_um_sid.v` | All-in-one top-level: register banks, voice pipeline, mixer, pin mapping |
| `src/pwm_audio.v` | 8-bit PWM audio output (255-clock period) |

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
 uio_in ──────┤  │  │ (16-bit)│  │(saw/tri/  │  │(8-bit    │  │ (8×8→8)  │  │  ┌───────┐  ┌─────────┐
              │  │  │  8-bit  │  │ pulse/    │  │ per      │  │          │  ├──│ Mixer │──│pwm_audio│── uo_out[0]
 Register     │  │  │  freq   │  │ noise)    │  │ voice)   │  │          │  │  │ (÷4)  │  │ (8-bit) │
 Banks        │  │  └─────────┘  └──────────┘  └──────────┘  └──────────┘  │  └───────┘  └─────────┘
 (all per-    │  │                                                          │
  voice)      │  │  Mod-5 slots: 1 MHz effective per voice                  │
              │  └─────────────────────────────────────────────────────────────┘
              │
```

</details>

**Signal flow:**

1. The host writes per-voice registers (frequency, pulse width, waveform,
   attack/decay, sustain/release) via the flat parallel interface. All
   registers are per-voice. A rising edge on `ui_in[7]` latches the data.

2. A mod-5 slot counter cycles through 5 slots at 5 MHz. Slots 0-2 compute
   voices 0-2 respectively, slot 3 latches the mixer output and preloads
   voice 0's pipeline registers, and slot 4 is an idle/preload slot. Each
   voice is updated once per 5-clock frame (1 MHz effective per voice).

3. Each voice's 16-bit phase accumulator advances by the 8-bit frequency
   register value (zero-extended to 16 bits) every frame. This provides
   ~15.3 Hz frequency resolution. Hard sync resets the accumulator when the
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

7. `pwm_audio` converts the 8-bit mix sample into a PWM signal at
   ~19.6 kHz. An external RC low-pass filter recovers analog audio.

---

## Pin Mapping

### Input Pins (`ui_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `ui_in[2:0]` | `reg_addr` | Register address (0--6) |
| `ui_in[4:3]` | `voice_sel` | Voice select: 0=voice 0, 1=voice 1, 2=voice 2 |
| `ui_in[6:5]` | -- | Unused |
| `ui_in[7]` | `wr_en` | Write enable (rising-edge triggered) |

### Data Input Pins (`uio_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uio_in[7:0]` | `wr_data` | 8-bit write data. All 8 pins are inputs. |

### Output Pins (`uo_out`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uo_out[0]` | `pwm_out` | PWM audio output. Connect to RC filter. |
| `uo_out[7:1]` | -- | Tied low. |

### Bidirectional Pin Direction

All `uio` pins are configured as inputs (`uio_oe = 0x00`).

---

## Register Reference

Six registers per voice (addresses 1 and 3 are reserved). All registers
are per-voice -- there are no shared registers. The frequency is an 8-bit
value at address 0 (no high byte).

### Register 0: Frequency (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [              frequency[7:0]            ]
```

The 8-bit frequency register is the phase accumulator increment. The
16-bit accumulator advances at an effective rate of 1 MHz (5 MHz / 5 slots).
The oscillator frequency is:

```
f_out = freq_reg × 1,000,000 / 65,536  ≈  freq_reg × 15.26 Hz
```

**Frequency calculation:**

```
freq_reg = round(desired_Hz × 65,536 / 1,000,000)
         ≈ desired_Hz × 0.06554
```

Resolution: ~15.3 Hz. Range: 15.3 Hz (reg=1) to 3,891 Hz (reg=255).

| Frequency Register | Output Frequency | Note |
|---------------------|-----------------|------|
| 0x00 | 0 Hz | Silence |
| 0x01 | ~15.3 Hz | Lowest pitch |
| 0x11 (17) | ~259 Hz | ~C4 |
| 0x1D (29) | ~443 Hz | ~A4 |
| 0xFF (255) | ~3,891 Hz | Maximum |

### Register 2: Pulse Width (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [             pulse_width[7:0]           ]
```

Sets the pulse waveform duty cycle by comparison with the accumulator
upper byte (`acc[15:8] >= pulse_width`):

- `pw = 0x00`: Pulse always high (near DC)
- `pw = 0x80`: ~50% duty cycle (square wave)
- `pw = 0xFF`: Pulse almost always low (narrow pulse)

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

### Envelope Rate Table

The ADSR uses a 14-bit free-running prescaler (LSB fixed to 0). Each rate
value selects which prescaler bits must all be 1 for an envelope tick. The
8-bit envelope counter steps by 1 per tick, so a full 0→255 traverse takes
256 ticks. Decay and release use exponential adjustment (the rate slows as
the envelope decreases).

| Rate | Check bits | Period | Full Traverse (256 ticks) |
|------|-----------|--------|--------------------------|
| 0 | &pre[2:1] | 4 clks | ~205 µs |
| 1 | &pre[3:1] | 8 clks | ~410 µs |
| 2 | &pre[4:1] | 16 clks | ~819 µs |
| 3 | &pre[5:1] | 32 clks | ~1.6 ms |
| 4 | &pre[6:1] | 64 clks | ~3.3 ms |
| 5 | &pre[7:1] | 128 clks | ~6.6 ms |
| 6 | &pre[8:1] | 256 clks | ~13.1 ms |
| 7 | &pre[9:1] | 512 clks | ~26.2 ms |
| 8--15 | &pre[13:1] | 8192 clks | ~419 ms |

Formula: `traverse_time = 256 × period / 5,000,000` seconds.

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

1. Set `ui_in[2:0]` = register address (0, 2, 4, 5, or 6)
2. Set `ui_in[4:3]` = voice select (0, 1, or 2)
3. Set `uio_in[7:0]` = data byte
4. Pulse `ui_in[7]` high for at least one clock cycle
5. Return `ui_in[7]` low before the next write

The register latches on the rising edge of `ui_in[7]`. The minimum write
cycle is 3 clock cycles (600 ns at 5 MHz): one to set up address/data,
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
// addr: 0,2,4,5,6  voice: 0-2  data: 0-255
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
| PWM frequency @ 5 MHz | ~19.6 kHz |
| Duty cycle range | 0% (sample=0) to 100% (sample=255) |
| Audio bandwidth | Up to ~10 kHz (Nyquist ~9.8 kHz) |

---

## Audio Recovery Filter

The PWM output on `uo_out[0]` swings between 0 and VDD. A third-order
passive RC low-pass filter is recommended to recover the analog audio
signal with good suppression of the ~19.6 kHz PWM carrier.

### Recommended Circuit

```
uo_out[0] ---[R1]---+---[R2]---+---[R3]---+---[Cac]---> Audio Out
                     |          |          |
                    [C1]       [C2]       [C3]
                     |          |          |
                    GND        GND        GND
```

### Component Values

| R (per stage) | C (per stage) | Per-stage fc | Combined rolloff | @ 19.6 kHz |
|---------------|---------------|-------------|-----------------|-----------|
| 3.3 kΩ | 4.7 nF | ~10.3 kHz | -18 dB/oct (3rd order) | ~-14 dB |

- **Cac** = 1 µF ceramic -- DC blocking capacitor after the filter.
- For driving low-impedance loads (headphones), add a unity-gain op-amp
  buffer after the filter.
- A second-order (two-stage) filter also works but with less carrier
  rejection.

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
                       uo_out[0] --[3.3k]--+--[3.3k]--+--[3.3k]--+--[1uF]--> amp
                                           |          |           |
                                        [4.7nF]    [4.7nF]    [4.7nF]
                                           |          |           |
                                          GND        GND         GND
```

### Playing a Note (Voice 0, Sawtooth ~440 Hz)

```c
// freq_reg = round(440 * 65536 / 1000000) = 29
sid_write(0, 29, 0);    // freq = 0x1D
sid_write(4, 0x00, 0);  // attack=0 (fastest), decay=0
sid_write(5, 0x0F, 0);  // sustain=15 (max), release=0
sid_write(6, 0x21, 0);  // sawtooth + gate ON

delay(500);              // hold note for 500 ms

sid_write(6, 0x20, 0);  // gate OFF (release begins)
```

### Three-Voice Chord (C Major)

```c
// C4 ≈ 262 Hz → freq_reg = round(262 * 65536 / 1000000) = 17
sid_write(0, 17, 0);
sid_write(4, 0x00, 0); sid_write(5, 0x0F, 0);
sid_write(6, 0x21, 0);  // Voice 0: sawtooth C4

// E4 ≈ 330 Hz → freq_reg = round(330 * 65536 / 1000000) = 22
sid_write(0, 22, 1);
sid_write(4, 0x00, 1); sid_write(5, 0x0F, 1);
sid_write(6, 0x11, 1);  // Voice 1: triangle E4

// G4 ≈ 392 Hz → freq_reg = round(392 * 65536 / 1000000) = 26
sid_write(0, 26, 2);
sid_write(2, 0x80, 2);  // pulse width = 50%
sid_write(4, 0x00, 2); sid_write(5, 0x0F, 2);
sid_write(6, 0x41, 2);  // Voice 2: pulse G4
```

### Sound Recipes

#### Simple Square Wave (8-bit Game Style)

```c
sid_write(0, freq_reg, v);
sid_write(2, 0x80, v);    // 50% duty cycle
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
sid_write(0, freq_reg, v);
sid_write(4, 0x8A, v);    // attack=10 (~419ms), decay=8 (~419ms)
sid_write(5, 0x8C, v);    // sustain=12, release=8
sid_write(6, 0x11, v);    // triangle + gate
```

#### Bell (Ring Modulation)

```c
// Voice 0: modulator at higher frequency
sid_write(0, 60, 0);     // ~916 Hz modulator
sid_write(6, 0x11, 0);   // triangle + gate (modulator)

// Voice 1: carrier with ring mod enabled
sid_write(0, 17, 1);     // ~259 Hz carrier (C4)
sid_write(4, 0x50, 1);   // instant attack, rate-5 decay
sid_write(5, 0x54, 1);   // sustain=4, rate-5 release
sid_write(6, 0x15, 1);   // triangle + ring + gate
```

### Frequency Table (Equal Temperament, A4=440 Hz)

```
freq_reg = round(Hz × 65,536 / 1,000,000)
```

| Note | Hz | freq_reg | hex |
|------|----|----------|-----|
| C3 | 130.8 | 9 | 0x09 |
| D3 | 146.8 | 10 | 0x0A |
| E3 | 164.8 | 11 | 0x0B |
| G3 | 196.0 | 13 | 0x0D |
| A3 | 220.0 | 14 | 0x0E |
| C4 | 261.6 | 17 | 0x11 |
| E4 | 329.6 | 22 | 0x16 |
| G4 | 392.0 | 26 | 0x1A |
| A4 | 440.0 | 29 | 0x1D |
| C5 | 523.3 | 34 | 0x22 |
| A5 | 880.0 | 58 | 0x3A |
| C6 | 1046.5 | 69 | 0x45 |
| C7 | 2093.0 | 137 | 0x89 |

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
| System clock | 5 MHz (200 ns period) |
| Pipeline | Mod-5 slot counter (1 MHz effective per voice) |
| Core utilization | ~65% |
| Voice count | 3 (time-multiplexed) |
| Frequency resolution | ~15.3 Hz (8-bit freq, 16-bit acc, 1 MHz effective) |
| Envelope depth | 8-bit (256 levels, exponential decay) |
| ADSR prescaler | 14-bit (shared, free-running) |
| Noise generator | 15-bit LFSR, accumulator-clocked from voice 0 |
| Voice output | 8-bit (8×8 waveform×envelope product, upper byte) |
| PWM output frequency | ~19.6 kHz |
| Audio bandwidth | Up to ~10 kHz (Nyquist ~9.8 kHz) |
| Write interface speed | 1 register per 600 ns (3 clocks) |
