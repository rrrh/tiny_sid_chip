<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

This is a single-voice SID (MOS 6581) synthesizer implemented in Verilog. It receives register writes over SPI and produces a 12-bit PWM audio output on `uio[7]`.

**Architecture:**

- **SPI slave** (`spi_regs`) — CPOL=0/CPHA=0, 16-bit write-only transactions. Drives a 7-register byte-addressed bank controlling frequency, pulse width, ADSR rates, and waveform selection.
- **SID voice** (`sid_voice`) — 24-bit phase accumulator with four waveform generators (sawtooth, triangle, pulse, noise via 23-bit LFSR). Waveforms are OR-combined and shaped by an 8-bit ADSR envelope.
- **ADSR envelope** (`sid_asdr_generator`) — Linear attack/decay/sustain/release with power-of-2 rate prescalers, matching the original SID timing.
- **PWM audio** (`pwm_audio`) — 12-bit PWM with a 4095-clock period (~12.2 kHz at 50 MHz). Output duty cycle is proportional to the 12-bit voice sample.

**SPI frame format (16-bit, MSB first):**

```
[15:13] = addr[2:0]   (register address 0-6)
[12:8]  = reserved    (ignored)
[7:0]   = data[7:0]   (8-bit register data)
```

**Register map:**

| Addr | Register | Description |
|------|----------|-------------|
| 0 | freq_lo | Frequency low byte — sid_frequency[7:0] |
| 1 | freq_hi | Frequency high byte — sid_frequency[15:8] |
| 2 | pw_lo | Pulse width low byte — sid_duration[7:0] |
| 3 | pw_hi | Pulse width high byte — sid_duration[15:8] |
| 4 | attack | attack[3:0] / decay[7:4] rate indices |
| 5 | sustain | sustain[3:0] / release[7:4] levels/rates |
| 6 | waveform | {noise, pulse, saw, tri, test, ring, sync, gate} |

## How to test

Connect an SPI master (e.g. microcontroller or Raspberry Pi) to `ui_in[0:2]` (CS_n on bit 0, CLK on bit 1, MOSI on bit 2):

1. Write frequency: register 0 = low byte, register 1 = high byte (e.g. 4291 = 0x10C3 → write 0xC3 to addr 0, 0x10 to addr 1 for ~C4 at 50 MHz)
2. Write attack/decay to register 4 (e.g. 0x09 for fast attack, medium decay)
3. Write sustain/release to register 5 (e.g. 0x0F for full sustain, fast release)
4. Write waveform to register 6 with gate bit set (e.g. 0x21 for sawtooth + gate)
5. Listen to the PWM output on `uio[7]` through a second-order RC reconstruction filter

## External hardware

A second-order (two-stage) RC low-pass reconstruction filter is needed on the PWM output (`uio[7]`) to recover the analog audio signal:

```
uio[7] ---[R1]---+---[R2]---+---> Audio Out
                  |          |
                 [C1]       [C2]
                  |          |
                 GND        GND
```

- **R1, R2** = 4.7 kOhm (series)
- **C1, C2** = 10 nF (shunt to ground) — gives fc ~ 3.4 kHz, ~-22 dB at 12.2 kHz PWM frequency
- **C_ac** = 1 uF (optional AC-coupling cap for amplifier input)

Connect the filter output to headphones (via op-amp buffer) or an audio amplifier.
