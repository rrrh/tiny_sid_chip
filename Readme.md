# SID Voice Synthesizer (TT-IHP)

Single SID voice with ADSR envelope, controlled via SPI, with a 12-bit PWM
audio output. Designed for a Tiny Tapeout 1x1 tile on the IHP SG13G2 130nm
process at 50 MHz.

[View the GDS layout](https://rrrh.github.io/tiny_sid_chip/)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Pin Mapping](#pin-mapping)
4. [Module Descriptions](#module-descriptions)
5. [Register Reference](#register-reference)
6. [SPI Protocol](#spi-protocol)
7. [Audio Output and PWM](#audio-output-and-pwm)
8. [Audio Recovery Filter](#audio-recovery-filter)
9. [Usage Guide](#usage-guide)
10. [Design Constraints](#design-constraints)
11. [Physical Implementation (LibreLane PnR)](#physical-implementation-librelane-pnr)

---

## Overview

This design implements a single-voice sound synthesizer inspired by the
MOS 6581/8580 SID chip, the legendary audio IC from the Commodore 64. It
provides four classic waveform types (sawtooth, triangle, pulse, noise), a
full ADSR amplitude envelope, and ring modulation / hard sync control bits,
all packed into a Tiny Tapeout 1x1 tile.

A host microcontroller (Arduino, RP2040, ESP32, etc.) writes seven
SID-style control registers over a simple 3-wire SPI bus using compact
16-bit frames. The synthesized audio is output as a 12-bit PWM signal on
`uio[7]` with a ~12.2 kHz PWM frequency that only requires a passive
second-order RC low-pass filter to produce an analog signal suitable for
headphones or a line-level amplifier input.

### Key Features

- Four waveforms: sawtooth, triangle, pulse (variable width), noise (LFSR)
- OR-combining of simultaneous waveforms (matches real SID behavior)
- Ring modulation and hard sync control bits
- Full ADSR envelope with independent attack, decay, sustain, and release
- Linear envelope with power-of-2 rate scaling (16 rate settings per phase)
- 12-bit internal voice resolution, 8-bit envelope depth (20-bit product)
- 12-bit PWM audio output (~12.2 kHz PWM frequency at 50 MHz)
- 3-wire write-only SPI control interface (CPOL=0, CPHA=0, 16-bit frames)
- Single 50 MHz clock domain
- Fits in a Tiny Tapeout 1x1 tile (~14,000 um^2 logic area on IHP SG13G2)

### Source Files

| File | Description |
|------|-------------|
| `src/tt_um_sid.v` | Top-level TT wrapper: pin mapping and module instantiation |
| `src/spi_regs.v` | SPI slave with 2FF synchronizers and write-only register bank |
| `src/sid_voice.v` | SID waveform generator: oscillator, waveform mux, envelope scaling |
| `src/sid_asdr_generator.v` | Simplified linear ADSR envelope state machine |
| `src/pwm_audio.v` | 12-bit PWM audio output (4095-clock period) |

---

## Architecture

![Architecture Block Diagram](docs/architecture.svg)

<details><summary>ASCII fallback</summary>

```
                         +-----------+     +-----------+     +-----------+
  ui_in[0] spi_cs_n --->|           |     |           |     |           |
  ui_in[1] spi_clk  --->| spi_regs  |---->| sid_voice |---->| pwm_audio |---> uio[7] pwm_out
  ui_in[2] spi_mosi --->|           |     |           |     |           |
                         +-----------+     +-----------+     +-----------+
                          7 registers       12-bit voice      12-bit PWM
                          (write-only)      output            (~12.2 kHz)
```

</details>

**Signal flow:**

1. The host sends 16-bit SPI write transactions to `spi_regs`, which
   synchronizes the SPI signals into the 50 MHz clock domain and latches
   the 8-bit data into one of seven byte-addressed control registers.

2. `sid_voice` reads those registers every clock cycle. A 24-bit phase
   accumulator generates the master oscillator, from which the four
   waveform generators derive their outputs. The selected waveform(s) are
   OR-combined into a 12-bit waveform value, then multiplied by the 8-bit
   ADSR envelope to produce a 20-bit product. The top 12 bits become the
   voice output.

3. `pwm_audio` converts the 12-bit voice sample into a PWM signal with a
   4095-clock period (~12.2 kHz at 50 MHz). The output duty cycle is
   proportional to the sample value. Externally, a second-order RC
   low-pass filter recovers the analog audio.

---

## Pin Mapping

### Input Pins (`ui_in`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `ui_in[0]` | `spi_cs_n` | SPI chip select, active low. Pull high when idle. |
| `ui_in[1]` | `spi_clk` | SPI clock (CPOL=0, CPHA=0). Max frequency depends on system clock; must be < clk/4 for reliable synchronization. |
| `ui_in[2]` | `spi_mosi` | SPI data input (master out, slave in). MSB first. |
| `ui_in[7:3]` | -- | Unused. Active low internally. |

### Output Pins (`uo_out`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uo_out[0]` | `spi_miso` | Tied low. SPI is write-only; no read-back. |
| `uo_out[7:1]` | -- | Tied low. |

### Bidirectional Pins (`uio`)

| Pin | Signal | Description |
|-----|--------|-------------|
| `uio[7]` | `pwm_out` | PWM audio output. Connect to reconstruction filter. Output enabled. |
| `uio[6:0]` | -- | Unused. Configured as inputs (no drive). |

---

## Module Descriptions

### `tt_um_sid` (Top Level)

The Tiny Tapeout wrapper. Connects the SPI bus pins to `spi_regs`, wires
the seven register outputs to `sid_voice`, feeds the 12-bit voice output
into `pwm_audio`, and maps `pwm_out` to `uio[7]`. All unused pins are tied
to safe defaults (outputs low, bidirectional pins set as inputs). Only
`uio[7]` is output-enabled (`uio_oe = 0x80`).

### `spi_regs` (SPI Register Bank)

A write-only SPI slave that accepts 16-bit transactions. The frame format
is `{addr[2:0], 5'b0, data[7:0]}`. All three SPI signals (`spi_clk`,
`spi_cs_n`, `spi_mosi`) pass through 2-stage flip-flop synchronizers
before processing, making the interface safe across clock domains. Rising
edges of `spi_clk` are detected in the system clock domain via a 3-stage
pipeline and edge comparator.

16-bit frequency and pulse width values are split into low/high byte
register pairs (addresses 0/1 and 2/3 respectively).

Transaction state resets whenever `spi_cs_n` goes high (inactive), so
partial or corrupted transactions are safely discarded.

### `sid_voice` (Waveform Generator)

Implements the core SID voice:

- **24-bit phase accumulator**: Increments by `frequency` every clock cycle.
  The upper bits drive the waveform generators.
- **Sawtooth**: Top 12 bits of the accumulator (`accumulator[23:12]`).
- **Triangle**: Bits `[22:11]` XORed with a mask derived from `accumulator[23]`
  (or `accumulator_msb_in` when ring modulation is active).
- **Pulse**: Comparator output -- high when `accumulator[23:12] > duration[11:0]`.
  The `duration` register sets the pulse width (duty cycle).
- **Noise**: 23-bit LFSR (taps at bits 17 and 22) clocked by `accumulator[19]`.
  Outputs bits `[22:11]` of the LFSR as a 12-bit pseudo-random value.
- **Waveform mux**: Selected waveforms are OR-combined (matching real SID
  behavior where enabling multiple waveforms simultaneously produces the
  bitwise OR of their outputs).
- **Envelope scaling**: The 12-bit waveform value is multiplied by the 8-bit
  ADSR envelope value, producing a 20-bit result. The top 12 bits
  (`[19:8]`) are output as the voice signal.

The `IS_8580` parameter is provided for future use (currently hardcoded to 0
for 6581 behavior).

### `sid_asdr_generator` (ADSR Envelope)

A simplified linear ADSR envelope generator with four states:

![ADSR State Machine](docs/adsr_fsm.svg)

<details><summary>ASCII fallback</summary>

```
IDLE --[gate rising edge]--> ATTACK --[env=0xFF]--> DECAY --[gate low]--> RELEASE --[env=0]--> IDLE
                                 |                    |                       ^
                                 +--[gate low]--------+                       |
                                                                              |
                                                      +--[gate rising edge]---+
```

</details>

**Timing mechanism:** A free-running 23-bit prescaler increments every
clock cycle. The 4-bit rate value selects which prescaler bits to check:
rate N fires an envelope tick when all of `prescaler[N+8:0]` are 1, i.e.,
every 2^(N+9) clock cycles. This gives a range from ~2.6 ms (rate 0) to
~86 s (rate 15) for a full 256-step envelope traverse at 50 MHz.

- **ATTACK**: Increments `env_counter` from 0 to 255 at the attack rate.
- **DECAY**: Decrements `env_counter` toward the sustain level at the decay rate.
  Holds at the sustain level while gate remains high (sustain phase).
- **RELEASE**: Decrements `env_counter` from current value to 0 at the release rate.

The sustain level is the upper 4 bits of the sustain register value,
zero-extended to 8 bits (`{sustain_value, 4'h0}`), giving 16 sustain
levels in steps of 16 (0, 16, 32, ..., 240).

### `pwm_audio` (PWM Audio Output)

A 12-bit PWM modulator with a 4095-clock period. The entire operation is:

```verilog
pwm <= count < sample;
count <= count + 1;
if (count == 12'hffe) count <= 0;
```

On each clock cycle, the 12-bit counter is compared against the input
sample. The output is high when the counter is less than the sample value,
producing a pulse whose width is proportional to the input amplitude.

| Parameter | Value |
|-----------|-------|
| Input resolution | 12 bits (unsigned, 0--4095) |
| PWM period | 4095 clocks |
| PWM frequency @ 50 MHz | ~12.2 kHz (50 MHz / 4095) |
| Output duty cycle | sample / 4095 (0% to 100%) |

---

## Register Reference

The seven registers are written via SPI using a 3-bit address (0--6).
All registers are 8-bit. The 16-bit frequency and pulse width values are
split into low/high byte pairs.

### Register 0: Frequency Low Byte (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [              frequency[7:0]            ]
```

### Register 1: Frequency High Byte (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [             frequency[15:8]            ]
```

The combined 16-bit frequency is the phase accumulator increment. Added
to the 24-bit accumulator every clock cycle, so the oscillator frequency is:

```
f_out = frequency * f_clk / 2^24
```

At 50 MHz:

| Frequency Register | Output Frequency | Note |
|---------------------|-----------------|------|
| 0x0000 | 0 Hz | Silence |
| 0x0112 | ~16.35 Hz | C0 |
| 0x10C3 | ~261.6 Hz | C4 |
| 0x1CD6 | ~440 Hz | A4 (concert pitch) |
| 0xFFFF | ~3051.76 Hz | Maximum fundamental |

**Frequency calculation:**
```
frequency_reg = round(f_desired * 2^24 / 50000000)
```

To write e.g. 4291 (0x10C3): write 0xC3 to register 0, then 0x10 to register 1.

### Register 2: Pulse Width Low Byte (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [              duration[7:0]             ]
```

### Register 3: Pulse Width High Byte (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [             duration[15:8]             ]
```

Only bits `[11:0]` of the combined 16-bit value are used. Sets the pulse
waveform duty cycle by comparison with `accumulator[23:12]`:

- `duration = 0x000`: Pulse is always low (0% duty cycle, silent)
- `duration = 0x800`: 50% duty cycle (classic square wave)
- `duration = 0xFFF`: Pulse is almost always high (~100% duty, nearly DC)

To write e.g. 2048 (0x0800): write 0x00 to register 2, then 0x08 to register 3.

### Register 4: Attack / Decay Rates (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [  decay_rate[3:0]  ][attack_rate[3:0] ]
```

| Field | Bits | Description |
|-------|------|-------------|
| `attack_rate` | `[3:0]` | Controls how fast the envelope rises from 0 to 255 |
| `decay_rate` | `[7:4]` | Controls how fast the envelope falls from 255 to the sustain level |

Both fields use the same 4-bit rate encoding (see [Envelope Rate Table](#envelope-rate-table)).

### Register 5: Sustain Level / Release Rate (8-bit)

```
Bit:   7    6    5    4    3    2    1    0
     [ release_rate[3:0] ][sustain_value[3:0]]
```

| Field | Bits | Description |
|-------|------|-------------|
| `sustain_value` | `[3:0]` | Sustain amplitude level (0--15). Mapped to 8-bit as `{value, 4'h0}`: 0=0, 1=16, ..., 15=240. |
| `release_rate` | `[7:4]` | Controls how fast the envelope falls from the current level to 0 after gate off. |

The sustain level is the amplitude the envelope holds at after the decay
phase completes, for as long as the gate remains high. Setting sustain to
15 (0xF) means the envelope stays near maximum after attack; setting it to
0 means the sound decays to silence even while the gate is held.

### Register 6: Waveform Control (8-bit)

```
Bit:   7      6      5        4        3     2     1     0
     [noise][pulse][sawtooth][triangle][test][ring][sync][gate]
```

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `gate` | **Gate control.** Set to 1 to start a note (triggers attack phase). Clear to 0 to release (triggers release phase). The attack phase begins on the rising edge of gate. |
| 1 | `sync` | **Hard sync.** When enabled, the oscillator accumulator resets on the falling edge of `accumulator_msb_in` (from another voice). In this single-voice design, `accumulator_msb_in` is tied to 0, so sync has no effect. |
| 2 | `ring` | **Ring modulation.** Modifies the triangle waveform by XORing with `accumulator_msb_in` instead of the local oscillator MSB. In this single-voice design, `accumulator_msb_in` is tied to 0, so ring mod inverts the triangle waveform. |
| 3 | `test` | **Test bit.** Forces the oscillator accumulator and LFSR to reset. While held high, the oscillator is frozen at 0 and noise output is reset. Useful for synchronizing or silencing. |
| 4 | `triangle` | **Enable triangle waveform.** Produces a triangle wave from the phase accumulator. |
| 5 | `sawtooth` | **Enable sawtooth waveform.** Produces a ramp (sawtooth) wave from the accumulator upper bits. |
| 6 | `pulse` | **Enable pulse waveform.** Produces a pulse/square wave; duty cycle set by registers 2/3. |
| 7 | `noise` | **Enable noise waveform.** Produces pseudo-random noise from a 23-bit LFSR. |

**Waveform combining:** When multiple waveform bits are set simultaneously,
their 12-bit outputs are bitwise OR-combined. This matches the real SID
chip behavior and produces distinctive (often harsh) timbres. Common useful
combinations:

- Single waveform (triangle, sawtooth, pulse, or noise) -- clean tones
- Triangle + sawtooth -- produces a characteristic SID "combined" timbre
- Pulse alone with varying width -- the most versatile SID sound

### Envelope Rate Table

All rate fields (attack, decay, release) use this mapping. The time listed
is the duration for a full 256-step traverse of the envelope at 50 MHz.

| Rate Value | Prescaler Period | Envelope Time (256 steps) | Typical Use |
|------------|------------------|---------------------------|-------------|
| 0 | 2^9 = 512 clocks | ~2.6 ms | Instantaneous percussive attack |
| 1 | 2^10 = 1024 | ~5.2 ms | Very fast |
| 2 | 2^11 = 2048 | ~10.5 ms | Fast |
| 3 | 2^12 = 4096 | ~21 ms | Quick pluck |
| 4 | 2^13 = 8192 | ~42 ms | Medium-fast |
| 5 | 2^14 = 16384 | ~84 ms | Medium |
| 6 | 2^15 = 32768 | ~168 ms | Moderate |
| 7 | 2^16 = 65536 | ~336 ms | Slow attack |
| 8 | 2^17 = 131072 | ~671 ms | Slow |
| 9 | 2^18 = 262144 | ~1.3 s | Very slow |
| 10 | 2^19 = 524288 | ~2.7 s | Pad-style |
| 11 | 2^20 = 1048576 | ~5.4 s | Long pad |
| 12 | 2^21 = 2097152 | ~10.7 s | Very long |
| 13 | 2^22 = 4194304 | ~21.5 s | Extreme |
| 14 | 2^23 = 8388608 | ~43 s | Ultra slow |
| 15 | 2^23 = 8388608 | ~43 s | Same as 14 (clamped) |

Formula: `envelope_time = 256 * 2^(rate+9) / 50000000` seconds.

---

## SPI Protocol

### Physical Layer

- **Mode:** CPOL=0, CPHA=0 (SPI Mode 0). Clock idle low; data sampled on rising edge.
- **Bit order:** MSB first.
- **Bus signals:** `spi_clk` (clock), `spi_cs_n` (chip select, active low), `spi_mosi` (data in).
- **MISO:** Permanently tied low. No read-back capability.
- **Clock speed:** The SPI clock must be slower than `clk/4` (< 12.5 MHz at 50 MHz system clock) due to the 2FF synchronizer and edge detection pipeline. Speeds up to 10 MHz are recommended for reliable operation.

### Transaction Format

Each write is a 16-bit (2-byte) transaction with `spi_cs_n` held low for
the entire transfer:

```
         Byte 0                 Byte 1
  CS_n  __|                                   |__
         |                                     |
  MOSI  [A2][A1][A0][x][x][x][x][x] [D7][D6]...[D0]
         ^                                     ^
       bit 15                                bit 0
```

| Byte | Bits | Field | Description |
|------|------|-------|-------------|
| 0 | `[7:5]` | A | Register address (0--6). |
| 0 | `[4:0]` | -- | Reserved (ignored). |
| 1 | `[7:0]` | D | 8-bit register data. |

**Important:** The register write takes effect on the 16th rising edge of
`spi_clk`. After the transaction, deassert `spi_cs_n` (drive high) before
starting the next transaction. The internal state machine resets on
`spi_cs_n` going high.

### Timing Diagram

```
spi_cs_n  ‾‾‾\___________________________/‾‾‾‾
                                           ^
spi_clk   ____/‾\_/‾\_/ ... \_/‾\_/‾\____
              1   2         15  16
                                 ^
                                 register written

spi_mosi  ----<A2><A1><A0><x><x><x><x><x><D7><D6>...<D1><D0>----
```

---

## Audio Output and PWM

### How It Works

The PWM audio module converts the 12-bit voice output into a pulse-width
modulated signal. A free-running 12-bit counter cycles from 0 to 4094
(period = 4095 clocks). On each clock, the output is high when the counter
is less than the input sample value:

```
pwm_out = (count < sample) ? 1 : 0
```

When the sample value is large, the output pulse is wider (higher duty
cycle). When the sample is small, the pulse is narrow. The time-averaged
voltage is proportional to the input amplitude.

### Signal Characteristics

| Parameter | Value |
|-----------|-------|
| Input resolution | 12 bits (unsigned, 0--4095) |
| Output | 1-bit PWM on `uio[7]` |
| PWM period | 4095 clocks |
| PWM frequency @ 50 MHz | ~12.2 kHz |
| Duty cycle range | 0% (sample=0) to 100% (sample=4095) |
| Audio bandwidth | Limited by PWM frequency; max usable ~3 kHz |

### Comparison with Delta-Sigma DAC

The previous design used a first-order delta-sigma DAC running at 50 MHz,
which pushed quantization noise to ultrasonic frequencies and allowed a
simple single-pole RC filter for reconstruction. The PWM approach trades
the higher oversampling ratio for implementation simplicity (no accumulator
overflow logic), but requires a steeper reconstruction filter to adequately
suppress the 12.2 kHz PWM carrier and its harmonics.

---

## Audio Recovery Filter

The PWM output on `uio[7]` is a digital signal swinging between 0 and VDD.
To recover a clean analog audio signal, a second-order (two-stage) passive
RC low-pass filter is recommended. This provides -40 dB/decade rolloff,
which is necessary to adequately suppress the 12.2 kHz PWM carrier while
passing audio frequencies.

### Recommended Circuit

```
uio[7] ---[R1]---+---[R2]---+---> Audio Out
                  |          |
                 [C1]       [C2]
                  |          |
                 GND        GND
```

### Component Values

Each stage has a per-stage cutoff of 1/(2*pi*R*C). However, in a passive
RC ladder the second stage loads the first, pulling the overall -3 dB
point significantly lower than the per-stage value.

| R (per stage) | C (per stage) | Per-stage fc | Actual -3 dB | @ 6.1 kHz | @ 12.2 kHz |
|---------------|---------------|-------------|-------------|-----------|-----------|
| 4.7 kOhm | 10 nF | 3.4 kHz | **1.26 kHz** | -15 dB | -24 dB |
| 3.3 kOhm | 10 nF | 4.8 kHz | ~1.8 kHz | -12 dB | -20 dB |
| 1.5 kOhm | 10 nF | 10.6 kHz | ~4.0 kHz | -5 dB | -12 dB |

The recommended 4.7 kOhm / 10 nF values give a -3 dB point around
1.26 kHz with good suppression of the PWM carrier (-24 dB at 12.2 kHz).

![2nd-order RC filter Bode plot](docs/pwm_rc_filter_bode.png)

A SPICE netlist for the filter is provided at `vivado/rc_filter.spice`.

### Design Notes

- **Why second-order?** A single-pole RC filter only provides -20 dB/decade
  rolloff. Two cascaded stages double the rolloff to -40 dB/decade, giving
  -24 dB at the 12.2 kHz PWM frequency with the recommended values.

- **Stage interaction:** The second RC stage loads the first, shifting the
  overall -3 dB point well below the individual per-stage cutoff. With
  4.7 kOhm / 10 nF (3.4 kHz per stage), the actual -3 dB point is
  ~1.26 kHz. The Bode plot above shows both the actual ladder response
  (solid) and the ideal non-interacting response (dashed) for comparison.

- **AC coupling:** The voice output is unsigned (centered at ~VDD/2), so
  add a DC blocking capacitor (10 uF electrolytic or 1 uF ceramic) in
  series after the filter when connecting to an amplifier input.

- **Output impedance:** The two-stage filter has a combined output
  impedance of R1+R2. For driving low-impedance loads (headphones), follow
  the filter with a unity-gain op-amp buffer, or reduce the resistor values
  (e.g., 1 kOhm each) and increase the capacitors proportionally.

- **Active alternative:** For better performance, replace the passive
  filter with a second-order Sallen-Key active filter using a single
  op-amp. This eliminates stage interaction and provides a buffered
  low-impedance output.

### Simulation Testbench

A Verilog testbench (`vivado/pwm_audio_tb.v`) is provided that generates a
440 Hz sine wave, feeds it through the `pwm_audio` module, simulates
two-stage RC filter recovery using a digital IIR model, and writes the
result as a 16-bit 44.1 kHz mono WAV file (`pwm_440hz.wav`).

![PWM testbench output waveform](docs/pwm_testbench_output.png)

A frequency sweep testbench (`vivado/pwm_audio_sweep_tb.v`) sweeps a sine
wave from 0 to 15 kHz over 3 seconds, producing a Bode plot of the
end-to-end PWM + filter frequency response:

![PWM frequency response (Bode plot)](docs/pwm_bode_plot.png)

The response is flat to ~3 kHz, rolls off toward the PWM Nyquist limit at
~6.1 kHz, and shows aliased energy above that. This confirms the usable
audio bandwidth of the 12-bit PWM output is approximately 0--5 kHz.

```bash
# Icarus Verilog — 440 Hz tone test
iverilog -o pwm_audio_tb vivado/pwm_audio_tb.v src/pwm_audio.v && vvp pwm_audio_tb

# Icarus Verilog — frequency sweep
iverilog -o pwm_audio_sweep_tb vivado/pwm_audio_sweep_tb.v src/pwm_audio.v && vvp pwm_audio_sweep_tb

# Vivado — 440 Hz tone test
xvlog vivado/pwm_audio_tb.v src/pwm_audio.v && xelab pwm_audio_tb && xsim pwm_audio_tb -R
```

---

## Usage Guide

### Minimal Wiring

```
MCU                    TT Chip                   Audio
-----------           ----------------          -------
GPIO (CS)   --------> ui_in[0] spi_cs_n
GPIO (SCK)  --------> ui_in[1] spi_clk
GPIO (MOSI) --------> ui_in[2] spi_mosi
                       uio[7] pwm_out ----[4.7k]---+---[4.7k]---+---> amp / headphones
                                                    |            |
                                                  [10nF]       [10nF]
                                                    |            |
                                                   GND          GND
```

**TT Demo Board RP2040 GPIO mapping:**

| TT Pin | Function | RP2040 GPIO |
|--------|----------|-------------|
| ui_in[0] | spi_cs_n | GPIO17 (SPI0.CS) |
| ui_in[1] | spi_clk | GPIO18 (SPI0.SCK) |
| ui_in[2] | spi_mosi | GPIO19 |
| uio[7] | pwm_out | GPIO28 |

No pull-up or pull-down resistors are needed on the SPI lines. The chip's
internal synchronizers handle signal conditioning.

### SPI Write Function (C / Arduino Example)

```c
// Write an 8-bit value to a SID register (address 0-6)
void sid_write(uint8_t addr, uint8_t data) {
    uint16_t word = ((addr & 0x07) << 13) | data;
    uint8_t byte0 = (word >> 8) & 0xFF;
    uint8_t byte1 = word & 0xFF;

    digitalWrite(CS_PIN, LOW);
    SPI.transfer(byte0);
    SPI.transfer(byte1);
    digitalWrite(CS_PIN, HIGH);
}

// Write a 16-bit frequency as two byte registers
void sid_write_freq(uint16_t freq) {
    sid_write(0, freq & 0xFF);        // freq_lo
    sid_write(1, (freq >> 8) & 0xFF); // freq_hi
}

// Write a 16-bit pulse width as two byte registers
void sid_write_pw(uint16_t pw) {
    sid_write(2, pw & 0xFF);          // pw_lo
    sid_write(3, (pw >> 8) & 0xFF);   // pw_hi
}
```

Ensure SPI is configured for Mode 0, MSB first, at <= 10 MHz.

### Playing a Note

To play a single note, configure the voice registers and then set the gate
bit. To stop the note, clear the gate bit to trigger the release phase.

```c
// Configure a 440 Hz sawtooth note with moderate ADSR
sid_write_freq(0x0241);  // Frequency = 440 Hz
sid_write_pw(0x0800);    // Pulse width = 50% (unused for sawtooth)
sid_write(4, 0x22);      // Attack=2 (~10ms), Decay=2 (~10ms)
sid_write(5, 0x2A);      // Sustain=10 (160/255), Release=2 (~10ms)
sid_write(6, 0x21);      // Sawtooth + gate ON

delay(500);              // Hold note for 500 ms

sid_write(6, 0x20);      // Sawtooth + gate OFF (release begins)
```

### Sound Recipes

Below are some starting-point register settings for common sounds.

#### Simple Square Wave (8-bit Game Style)

```c
sid_write_freq(freq);    // Desired frequency
sid_write_pw(0x0800);    // 50% duty cycle
sid_write(4, 0x00);      // Attack=0 (instant), Decay=0 (instant)
sid_write(5, 0x0F);      // Sustain=15 (max), Release=0 (instant)
sid_write(6, 0x41);      // Pulse waveform + gate ON
```

#### Bass (Pulse with Slow Attack)

```c
sid_write_freq(0x0056);  // ~65 Hz (low C)
sid_write_pw(0x0400);    // 25% duty cycle (nasal/thin bass)
sid_write(4, 0x53);      // Attack=3 (~21ms), Decay=5 (~84ms)
sid_write(5, 0x38);      // Sustain=8 (128/255), Release=3 (~21ms)
sid_write(6, 0x41);      // Pulse + gate ON
```

#### Pad (Triangle with Long Attack/Release)

```c
sid_write_freq(freq);    // Desired frequency
sid_write(4, 0x47);      // Attack=7 (~336ms), Decay=4 (~42ms)
sid_write(5, 0x6C);      // Sustain=12 (192/255), Release=6 (~168ms)
sid_write(6, 0x11);      // Triangle + gate ON
```

#### Drum / Percussion Hit (Noise with Fast Decay)

```c
sid_write_freq(0x4000);  // High frequency for dense noise texture
sid_write(4, 0x30);      // Attack=0 (instant), Decay=3 (~21ms)
sid_write(5, 0x20);      // Sustain=0 (full decay to silence), Release=2
sid_write(6, 0x81);      // Noise + gate ON
// After ~30ms the sound naturally decays to silence
sid_write(6, 0x80);      // Gate OFF
```

#### SID-Style Lead (Pulse with PWM Sweep)

For the classic SID "PWM lead" sound, sweep the pulse width register over
time from your host MCU:

```c
sid_write_freq(freq);
sid_write(4, 0x22);      // Attack=2, Decay=2
sid_write(5, 0x2B);      // Sustain=11, Release=2
sid_write(6, 0x41);      // Pulse + gate ON

// Sweep pulse width in a loop
for (uint16_t pw = 0x200; pw < 0xE00; pw += 0x10) {
    sid_write_pw(pw);
    delay(5);            // ~5ms per step
}
```

### Frequency Table (Equal Temperament at A4=440 Hz)

Register values for standard musical notes at 50 MHz system clock:

| Note | Oct 2 | Oct 3 | Oct 4 | Oct 5 | Oct 6 |
|------|-------|-------|-------|-------|-------|
| C | 0x0056 | 0x00AB | 0x0156 | 0x02AC | 0x0558 |
| C# | 0x005B | 0x00B5 | 0x016A | 0x02D5 | 0x05AA |
| D | 0x0060 | 0x00C0 | 0x0180 | 0x0300 | 0x0601 |
| D# | 0x0066 | 0x00CC | 0x0198 | 0x032F | 0x065E |
| E | 0x006C | 0x00D8 | 0x01B0 | 0x0361 | 0x06C2 |
| F | 0x0073 | 0x00E5 | 0x01CA | 0x0395 | 0x072A |
| F# | 0x0079 | 0x00F3 | 0x01E6 | 0x03CC | 0x0799 |
| G | 0x0080 | 0x0101 | 0x0203 | 0x0406 | 0x080C |
| G# | 0x0088 | 0x0110 | 0x0221 | 0x0443 | 0x0886 |
| A | 0x0090 | 0x0121 | 0x0241 | 0x0483 | 0x0906 |
| A# | 0x0099 | 0x0132 | 0x0264 | 0x04C8 | 0x098F |
| B | 0x00A2 | 0x0144 | 0x0288 | 0x0510 | 0x0A20 |

### Reset and Initialization

After power-on or chip reset (`rst_n` asserted low), all registers are
cleared to zero. The voice is silent (gate=0, frequency=0, all waveforms
disabled). No initialization sequence is required beyond configuring the
desired sound parameters.

To silence the output at any time, either:
- Clear the gate bit: `sid_write(6, waveform & 0xFE)`
- Set frequency to 0: `sid_write_freq(0x0000)`
- Set the test bit to freeze the oscillator: `sid_write(6, 0x08)`

---

## Design Constraints

| Parameter | Value |
|-----------|-------|
| Target technology | IHP SG13G2 130nm SiGe BiCMOS |
| Tile size | Tiny Tapeout 1x1 (~167 x 108 um) |
| Core supply (VDD) | 1.2V |
| I/O supply (VDDIO) | 3.3V |
| System clock | 50 MHz (20 ns period) |
| Logic area | ~13,828 um^2 (Yosys, IHP SG13G2 stdcell) |
| Core utilization | 41.6% |
| Flip-flop count | 203 |
| SPI max clock | < 12.5 MHz (clk/4); 10 MHz recommended |
| PWM output frequency | ~12.2 kHz |
| Audio bandwidth | ~3 kHz (limited by PWM frequency and reconstruction filter) |

---

## Physical Implementation (LibreLane PnR)

Post place-and-route results from LibreLane 3.0.0.dev50, targeting the
TT-IHP 1x1 tile on IHP SG13G2 130nm.

### Die / Floorplan

| Parameter | Value |
|-----------|-------|
| Die area | 196.97 x 207.69 um (40,936 um^2) |
| Core area | 185.84 x 184.96 um (34,373 um^2) |
| Logic area | 13,828 um^2 |
| Core utilization | 41.6% |
| PDK | IHP SG13G2 (sg13g2_stdcell) |
| Routing layers | Metal1 -- Metal5 |

### Cell Count (after fill insertion)

| Cell Type | Count |
|-----------|------:|
| Multi-input combinational | 950 |
| Sequential (flip-flops) | 203 |
| Decap cells | 738 |
| Tap cells | 490 |
| Antenna diodes | 417 |
| Fill cells | 136 |
| **Total instances** | **2,488** |

### Area Breakdown

| Category | Area (um^2) | % of Logic |
|----------|----------:|----------:|
| Combinational | 9,095 | 65.8% |
| Sequential | 4,733 | 34.2% |
| **Total logic** | **13,828** | 100% |

### Timing (Post-PnR, nom_tt_025C_1v80)

| Parameter | Value |
|-----------|-------|
| Clock period | 20.0 ns (50 MHz) |
| Setup violations | 0 |
| Hold violations | 0 |
| Max slew violations | 0 |
| Max cap violations | 0 |

### Routing

| Parameter | Value |
|-----------|-------|
| Total wirelength | 31,764 um |
| Total vias | 10,018 |
| met1 | 16,474 um (51.8%) |
| met2 | 14,658 um (46.1%) |
| met3 | 457 um (1.4%) |
| met4 | 172 um (0.5%) |

### Power (nom_tt_025C_1v80)

| Parameter | Value |
|-----------|-------|
| Total power | 0.80 mW |
| Sequential (registers + clocking) | 0.41 mW (51%) |
| Clock distribution | 0.37 mW (46%) |
| Combinational | 0.02 mW (3%) |
| Leakage | < 0.001 mW |

### IR Drop (nom_tt_025C_1v80)

| Net | Worst Drop |
|-----|-----------|
| VPWR (1.20 V) | 0.25 mV (0.02%) |
| VGND (0.00 V) | 0.24 mV (0.02%) |

### Verification

| Check | Result |
|-------|--------|
| Magic DRC | Passed |
| KLayout DRC | Passed |
| LVS | Passed |
| XOR (GDS match) | Passed |
