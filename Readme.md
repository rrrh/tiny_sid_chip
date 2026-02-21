# Triple SID Voice Synthesizer (TT-IHP)

Three time-multiplexed SID voices with ADSR envelopes, controlled via a
flat parallel register interface, with 8-bit PWM audio output. Designed
for a Tiny Tapeout 1x1 tile on the IHP SG13G2 130nm process at 5 MHz.

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
ADSR amplitude envelope, and waveform OR-combining -- all packed into a
Tiny Tapeout 1x1 tile.

A host microcontroller (Arduino, RP2040, ESP32, etc.) writes per-voice
control registers through a simple flat parallel interface using 8-bit
data and a rising-edge write strobe. The three voice outputs are mixed
and output as an 8-bit PWM signal on `uo_out[0]` at ~19.6 kHz, requiring
only a passive second-order RC low-pass filter to produce analog audio.

### Key Features

- Three independent voices, time-multiplexed through one shared pipeline
- Four waveforms per voice: sawtooth, triangle, pulse (variable width), noise
- OR-combining of simultaneous waveforms (matches real SID behavior)
- 4-bit linear ADSR envelope per voice (16 amplitude levels)
- 13 envelope rate settings from ~205 us to ~839 ms full traverse
- 16-bit phase accumulators (~25.4 Hz resolution, no prescaler)
- 3-voice mixer with automatic level scaling
- 8-bit PWM audio output (~19.6 kHz carrier at 5 MHz)
- Flat parallel write interface (no SPI/I2C overhead)
- Single 5 MHz clock domain, no PLLs or clock enables
- Fits in a Tiny Tapeout 1x1 tile on IHP SG13G2 130nm

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
 ui_in[2:0] ──┐  │              Shared Voice Pipeline (×3 TDM)                │
 ui_in[4:3] ──┤  │  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
 ui_in[7]   ──┤  │  │ Phase   │  │ Waveform  │  │  ADSR    │  │ Envelope │  │
              ├──┤  │ Acc     │──│ Gen       │──│ Envelope │──│ Scaling  │──┤
 uio_in ──────┤  │  │ (16-bit)│  │(saw/tri/  │  │(4-bit    │  │ (8×4=12) │  │  ┌───────┐  ┌─────────┐
              │  │  │ direct  │  │ pulse/    │  │ per      │  │          │  ├──│ Mixer │──│pwm_audio│── uo_out[0]
 Register     │  │  │ advance │  │ noise)    │  │ voice)   │  │          │  │  │ (>>2) │  │ (8-bit) │
 Banks        │  │  └─────────┘  └──────────┘  └──────────┘  └──────────┘  │  └───────┘  └─────────┘
 (per-voice   │  │                                                          │
  freq/PW/    │  │  vidx: 0→1→2→0→… @ 5 MHz                               │
  waveform +  │  └─────────────────────────────────────────────────────────────┘
  shared ADSR)│
              │
```

</details>

**Signal flow:**

1. The host writes per-voice registers (frequency, pulse width, waveform)
   and shared ADSR registers (attack/decay, sustain/release) via the
   flat parallel interface. A rising edge on `ui_in[7]` latches the data.

2. A 2-bit round-robin counter (`vidx`) cycles 0→1→2→0 every clock at
   5 MHz, selecting which voice's state is processed. Each voice is
   updated every 3 clocks (1.667 MHz effective per voice).

3. Each voice's 16-bit phase accumulator advances directly by the 16-bit
   frequency register value every cycle (no prescaler). This provides
   ~25.4 Hz frequency resolution.

4. The waveform generator derives sawtooth, triangle, pulse, and noise
   outputs from the accumulator state and a shared 8-bit LFSR. Selected
   waveforms are OR-combined into an 8-bit value, then multiplied by
   the 4-bit ADSR envelope to produce a 12-bit voice output.

5. The mixer accumulates three voice outputs over 3 clocks, shifts right
   by 2, and outputs an 8-bit mix sample to the PWM module.

6. `pwm_audio` converts the 8-bit mix sample into a PWM signal at
   ~19.6 kHz. An external RC low-pass filter recovers analog audio.

---

## Pin Mapping

### Input Pins (`ui_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `ui_in[2:0]` | `reg_addr` | Register address (0--6) |
| `ui_in[4:3]` | `voice_sel` | Voice select: 0=voice 1, 1=voice 2, 2=voice 3 |
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

Six registers per voice (address 3 is reserved). The 16-bit frequency
value is split into low/high byte pairs at addresses 0 and 1.
Attack/sustain registers are shared across all voices.

### Register 0: Frequency Low Byte

```
Bit:   7    6    5    4    3    2    1    0
     [              frequency[7:0]            ]
```

### Register 1: Frequency High Byte

```
Bit:   7    6    5    4    3    2    1    0
     [             frequency[15:8]            ]
```

The combined 16-bit frequency is the phase accumulator increment. The
16-bit accumulator advances at an effective rate of 5 MHz / 3 voices
= 1.667 MHz per voice. The oscillator frequency is:

```
f_out = frequency_reg * 1666667 / 65536
```

**Frequency calculation:**

```
frequency_reg = round(desired_Hz * 65536 / 1666667)
              ≈ desired_Hz * 0.03932
```

| Frequency Register | Output Frequency | Note |
|---------------------|-----------------|------|
| 0x0000 | 0 Hz | Silence |
| 0x0003 | ~76.3 Hz | ~C2 |
| 0x000A | ~254.3 Hz | ~C4 |
| 0x0011 | ~432.3 Hz | ~A4 |
| 0xFFFF | ~1.667 MHz | Maximum (ultrasonic) |

### Register 2: Pulse Width (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [             pulse_width[7:0]           ]
```

Sets the pulse waveform duty cycle by comparison with the accumulator
upper byte (`acc[15:8] > pulse_width`):

- `pw = 0x00`: Pulse always low (silent)
- `pw = 0x80`: 50% duty cycle (square wave)
- `pw = 0xFF`: Pulse almost always high (near DC)

### Register 4: Attack / Decay Rates (8-bit, shared)

```
Bit:   7    6    5    4    3    2    1    0
     [  decay_rate[3:0]  ][ attack_rate[3:0] ]
```

| Field | Bits | Description |
|-------|------|-------------|
| `attack_rate` | `[3:0]` | How fast the envelope rises from 0 to 15 |
| `decay_rate` | `[7:4]` | How fast the envelope falls from 15 to sustain level |

This register is shared across all three voices.

### Register 5: Sustain Level / Release Rate (8-bit, shared)

```
Bit:   7    6    5    4    3    2    1    0
     [ release_rate[3:0] ][sustain_level[3:0]]
```

| Field | Bits | Description |
|-------|------|-------------|
| `sustain_level` | `[3:0]` | Sustain amplitude (0--15). The envelope holds at this level during sustain. |
| `release_rate` | `[7:4]` | How fast the envelope falls to 0 after gate off |

This register is shared across all three voices.

### Register 6: Waveform Control (8-bit, per-voice)

```
Bit:   7      6      5        4        3     2     1     0
     [noise][pulse][sawtooth][triangle][test][ring][sync][gate]
```

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `gate` | Set to 1 to start a note (attack). Clear to 0 to release. |
| 1 | `sync` | Reserved (no effect in current design). |
| 2 | `ring` | Reserved (no effect in current design). |
| 3 | `test` | Forces oscillator accumulator to 0 while held. |
| 4 | `triangle` | Enable triangle waveform. |
| 5 | `sawtooth` | Enable sawtooth waveform. |
| 6 | `pulse` | Enable pulse waveform (duty cycle set by reg 2). |
| 7 | `noise` | Enable noise waveform (shared 8-bit LFSR). |

When multiple waveform bits are set, their outputs are bitwise
OR-combined (matching real SID behavior).

### Envelope Rate Table

The ADSR uses an 18-bit free-running prescaler. Each rate value selects
which prescaler bits must all be 1 for an envelope tick. The 4-bit
envelope counter steps by 1 per tick, so a full 0→15 traverse takes
16 ticks.

| Rate | Prescaler Period | Full Traverse (16 steps) |
|------|------------------|--------------------------|
| 0 | 2^6 = 64 clocks | ~205 us |
| 1 | 2^7 = 128 | ~410 us |
| 2 | 2^8 = 256 | ~820 us |
| 3 | 2^9 = 512 | ~1.6 ms |
| 4 | 2^10 = 1024 | ~3.3 ms |
| 5 | 2^11 = 2048 | ~6.6 ms |
| 6 | 2^12 = 4096 | ~13.1 ms |
| 7 | 2^13 = 8192 | ~26.2 ms |
| 8 | 2^14 = 16384 | ~52.4 ms |
| 9 | 2^15 = 32768 | ~105 ms |
| 10 | 2^16 = 65536 | ~210 ms |
| 11 | 2^17 = 131072 | ~419 ms |
| 12--15 | 2^18 = 262144 | ~839 ms |

Formula: `traverse_time = 16 * 2^(rate+6) / 5000000` seconds.

---

## Write Interface Protocol

The register interface uses a simple parallel bus with rising-edge write
strobe. No SPI or I2C protocol is needed.

### Write Sequence

To write one register:

1. Set `ui_in[2:0]` = register address (0--6)
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
// addr: 0-6, voice: 0-2, data: 0-255
void sid_write(uint8_t addr, uint8_t data, uint8_t voice) {
    uint8_t ui = (addr & 0x07) | ((voice & 0x03) << 3);
    set_ui_in(ui);           // address + voice, WE=0
    set_uio_in(data);        // data byte
    set_ui_in(ui | 0x80);    // assert WE (rising edge triggers write)
    set_ui_in(ui);           // deassert WE
}

// Write a 16-bit frequency
void sid_write_freq(uint16_t freq, uint8_t voice) {
    sid_write(0, freq & 0xFF, voice);
    sid_write(1, (freq >> 8) & 0xFF, voice);
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

The PWM output on `uo_out[0]` swings between 0 and VDD. A second-order
passive RC low-pass filter recovers the analog audio signal.

### Recommended Circuit

```
uo_out[0] ---[R1]---+---[R2]---+---[Cac]---> Audio Out
                     |          |
                    [C1]       [C2]
                     |          |
                    GND        GND
```

### Component Values

| R (per stage) | C (per stage) | Per-stage fc | Actual -3 dB | @ 19.6 kHz |
|---------------|---------------|-------------|-------------|-----------|
| 3.3 kOhm | 4.7 nF | 10.3 kHz | ~8 kHz | -9 dB |

- **Cac** = 1 uF ceramic -- DC blocking capacitor after the filter.
- For driving low-impedance loads (headphones), add a unity-gain op-amp
  buffer after the filter.

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
                       uo_out[0] ----[3.3k]---+---[3.3k]---+---[1uF]---> amp
                                               |            |
                                            [4.7nF]       [4.7nF]
                                               |            |
                                              GND          GND
```

### Playing a Note (Voice 0, Sawtooth 440 Hz)

```c
// freq_reg = 440 * 0.03932 ≈ 17
sid_write(0, 17, 0);    // freq_lo = 0x11
sid_write(1, 0, 0);     // freq_hi = 0x00
sid_write(4, 0x00, 0);   // attack=0 (fastest), decay=0
sid_write(5, 0x0F, 0);   // sustain=15 (max), release=0
sid_write(6, 0x21, 0);   // sawtooth + gate ON

delay(500);              // hold note for 500 ms

sid_write(6, 0x20, 0);   // gate OFF (release begins)
```

### Three-Voice Chord (C Major)

```c
// C4 ≈ 262 Hz → freq_reg ≈ 10
sid_write(0, 10, 0);  sid_write(1, 0, 0);
sid_write(4, 0x00, 0); sid_write(5, 0x0F, 0);
sid_write(6, 0x21, 0);  // Voice 0: sawtooth C4

// E4 ≈ 330 Hz → freq_reg ≈ 13
sid_write(0, 13, 1);  sid_write(1, 0, 1);
sid_write(6, 0x11, 1);  // Voice 1: triangle E4

// G4 ≈ 392 Hz → freq_reg ≈ 15
sid_write(0, 15, 2);  sid_write(1, 0, 2);
sid_write(2, 0x80, 2);  // pulse width = 50%
sid_write(6, 0x41, 2);  // Voice 2: pulse G4
```

### Sound Recipes

#### Simple Square Wave (8-bit Game Style)

```c
sid_write(0, freq_lo, v); sid_write(1, freq_hi, v);
sid_write(2, 0x80, v);    // 50% duty cycle
sid_write(4, 0x00, v);    // instant attack/decay
sid_write(5, 0x0F, v);    // max sustain, instant release
sid_write(6, 0x41, v);    // pulse + gate
```

#### Drum Hit (Noise with Fast Decay)

```c
sid_write(0, 0xFF, v); sid_write(1, 0xFF, v);  // high freq noise
sid_write(4, 0xA0, v);    // instant attack, rate-10 decay
sid_write(5, 0xA0, v);    // sustain=0, rate-10 release
sid_write(6, 0x81, v);    // noise + gate
// Naturally decays to silence
```

#### Pad (Triangle with Slow Envelope)

```c
sid_write(0, freq_lo, v); sid_write(1, freq_hi, v);
sid_write(4, 0x8A, v);    // attack=10 (~210ms), decay=8 (~52ms)
sid_write(5, 0x8C, v);    // sustain=12, release=8
sid_write(6, 0x11, v);    // triangle + gate
```

### Frequency Table (Equal Temperament, A4=440 Hz)

```
freq_reg = round(Hz * 65536 / 1666667)
```

| Note | Hz | freq_reg | hex |
|------|----|----------|-----|
| C2 | 65.4 | 3 | 0x0003 |
| C3 | 130.8 | 5 | 0x0005 |
| C4 | 261.6 | 10 | 0x000A |
| E4 | 329.6 | 13 | 0x000D |
| G4 | 392.0 | 15 | 0x000F |
| A4 | 440.0 | 17 | 0x0011 |
| C5 | 523.3 | 21 | 0x0015 |
| C6 | 1046.5 | 41 | 0x0029 |
| C7 | 2093.0 | 82 | 0x0052 |
| C8 | 4186.0 | 165 | 0x00A5 |

### Reset and Initialization

After power-on or chip reset (`rst_n` asserted low), all registers are
cleared to zero. All voices are silent. No initialization sequence is
required.

To silence the output at any time:
- Clear the gate bit: `sid_write(6, waveform & 0xFE, voice)`
- Set frequency to 0: `sid_write(0, 0, v); sid_write(1, 0, v)`
- Set the test bit: `sid_write(6, 0x08, v)`

---

## Design Constraints

| Parameter | Value |
|-----------|-------|
| Target technology | IHP SG13G2 130nm SiGe BiCMOS |
| Tile size | Tiny Tapeout 1x1 |
| Core supply (VDD) | 1.2V |
| I/O supply (VDDIO) | 3.3V |
| System clock | 5 MHz (200 ns period) |
| Core utilization | ~85% |
| Voice count | 3 (time-multiplexed) |
| Frequency resolution | ~25.4 Hz (16-bit acc, no prescaler) |
| Envelope depth | 4-bit (16 levels) |
| PWM output frequency | ~19.6 kHz |
| Audio bandwidth | Up to ~10 kHz (Nyquist ~9.8 kHz) |
| Write interface speed | 1 register per 600 ns (3 clocks) |
