# SID Waveform Verification Report

**Date:** 2026-03-04 18:00
**Capture duration:** 75 ms per tone (1,800,000 cycles at 24 MHz)
**Attack settle:** 200,000 cycles (~8.3 ms)
**Filter:** 3rd-order RC LPF (R=3.3k x3, C=4.7nF x3) + Cac=1uF + Rload=10k

---

## Frequency Sweep (Triangle 220 / 440 / 880 Hz)

Verifies that the SID tone generator produces correct frequency output
across one octave below and above A4 (440 Hz).

| # | Frequency | Freq Reg | Waveform Reg | PWL File |
|---|-----------|----------|-------------|----------|
| 1 | 220 Hz | 0x0E6B | 0x11 | `wv_tri_220.pwl` |
| 2 | 440 Hz | 0x1CD6 | 0x11 | `wv_tri_440.pwl` |
| 3 | 880 Hz | 0x39AC | 0x11 | `wv_tri_880.pwl` |

### Triangle 220 Hz
![Triangle 220 Hz](wv_tri_220.png)

### Triangle 440 Hz
![Triangle 440 Hz](wv_tri_440.png)

### Triangle 880 Hz
![Triangle 880 Hz](wv_tri_880.png)

---

## Waveform Comparison (440 Hz)

Demonstrates all four SID waveform types at the same frequency.

| # | Waveform | Waveform Reg | PWL File |
|---|----------|-------------|----------|
| 1 | Triangle | 0x11 | `wv_tri_440.pwl` |
| 2 | Sawtooth | 0x21 | `wv_saw_440.pwl` |
| 3 | Pulse | 0x41 | `wv_pulse_440.pwl` |
| 4 | Noise | 0x81 | `wv_noise_440.pwl` |

### Triangle 440 Hz
![Triangle 440 Hz](wv_tri_440.png)

### Sawtooth 440 Hz
![Sawtooth 440 Hz](wv_saw_440.png)

### Pulse 440 Hz (50%)
![Pulse 440 Hz (50%)](wv_pulse_440.png)

### Noise 440 Hz
![Noise 440 Hz](wv_noise_440.png)

---

## output_lpf.v Dead-Zone Fix

The IIR lowpass filter accumulator was widened from 10-bit (8.2 fixed-point)
to 16-bit (8.8 fixed-point) to eliminate a quantization dead zone.

| Parameter | Before | After |
|-----------|--------|-------|
| Accumulator width | 10-bit (8.2) | 16-bit (8.8) |
| `x_ext` | `{sample_in, 2'b0}` | `{sample_in, 8'b0}` |
| `diff` / `step` | `signed [10:0]` | `signed [16:0]` |
| `sample_out` | `acc[9:2]` | `acc[15:8]` |

**Problem:** With only 2 fractional bits, `step = diff >>> 7` rounded positive
diffs of 1–127 to zero (negative diffs always produced at least −1 due to
arithmetic right-shift). This caused triangle waveforms to plateau on the
rising edge (trapezoidal distortion).

**Fix:** With 8 fractional bits, a 1-LSB input change maps to diff=256,
giving step=2 — always non-zero. Residual dead zone is <0.5 LSB, below the
quantization floor. Filter response (alpha=1/128, fc≈1244 Hz) is unchanged.

**Result:** Triangle waveforms now show smooth, continuous ramps with no
flat plateaus at all three test frequencies (220, 440, 880 Hz).

---

## Summary

- **Tones captured:** 6/6
- **Pass criteria:** All 6 PWL files generated, WAVs audible at correct pitch
- **LPF dead-zone fix:** Verified — triangle ramps are smooth

### Output Files

- `wv_tri_220`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_tri_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_tri_880`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_saw_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_pulse_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_noise_440`: PWL=yes WAV=yes PNG=yes [OK]
