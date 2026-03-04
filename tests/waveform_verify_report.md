# SID Waveform Verification Report

**Date:** 2026-03-04 20:04
**Capture duration:** 75 ms per tone (1,800,000 cycles at 24 MHz)
**Attack settle:** 200,000 cycles (~8.3 ms)
**Filter:** 3rd-order RC LPF (R=3.3k x3, C=4.7nF x3) + Cac=1uF + Rload=10k
**Waveforms:** 4 types x 3 frequencies = 12 captures

---

## Triangle (220 / 440 / 880 Hz)

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

## Sawtooth (220 / 440 / 880 Hz)

| # | Frequency | Freq Reg | Waveform Reg | PWL File |
|---|-----------|----------|-------------|----------|
| 1 | 220 Hz | 0x0E6B | 0x21 | `wv_saw_220.pwl` |
| 2 | 440 Hz | 0x1CD6 | 0x21 | `wv_saw_440.pwl` |
| 3 | 880 Hz | 0x39AC | 0x21 | `wv_saw_880.pwl` |

### Sawtooth 220 Hz
![Sawtooth 220 Hz](wv_saw_220.png)

### Sawtooth 440 Hz
![Sawtooth 440 Hz](wv_saw_440.png)

### Sawtooth 880 Hz
![Sawtooth 880 Hz](wv_saw_880.png)

---

## Pulse (220 / 440 / 880 Hz)

| # | Frequency | Freq Reg | Waveform Reg | PWL File |
|---|-----------|----------|-------------|----------|
| 1 | 220 Hz | 0x0E6B | 0x41 | `wv_pulse_220.pwl` |
| 2 | 440 Hz | 0x1CD6 | 0x41 | `wv_pulse_440.pwl` |
| 3 | 880 Hz | 0x39AC | 0x41 | `wv_pulse_880.pwl` |

### Pulse 220 Hz (50%)
![Pulse 220 Hz (50%)](wv_pulse_220.png)

### Pulse 440 Hz (50%)
![Pulse 440 Hz (50%)](wv_pulse_440.png)

### Pulse 880 Hz (50%)
![Pulse 880 Hz (50%)](wv_pulse_880.png)

---

## Noise (220 / 440 / 880 Hz)

| # | Frequency | Freq Reg | Waveform Reg | PWL File |
|---|-----------|----------|-------------|----------|
| 1 | 220 Hz | 0x0E6B | 0x81 | `wv_noise_220.pwl` |
| 2 | 440 Hz | 0x1CD6 | 0x81 | `wv_noise_440.pwl` |
| 3 | 880 Hz | 0x39AC | 0x81 | `wv_noise_880.pwl` |

### Noise 220 Hz
![Noise 220 Hz](wv_noise_220.png)

### Noise 440 Hz
![Noise 440 Hz](wv_noise_440.png)

### Noise 880 Hz
![Noise 880 Hz](wv_noise_880.png)

---

## Summary

- **Tones captured:** 12/12
- **Pass criteria:** All 12 PWL files generated, WAVs audible at correct pitch

### Output Files

- `wv_tri_220`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_tri_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_tri_880`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_saw_220`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_saw_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_saw_880`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_pulse_220`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_pulse_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_pulse_880`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_noise_220`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_noise_440`: PWL=yes WAV=yes PNG=yes [OK]
- `wv_noise_880`: PWL=yes WAV=yes PNG=yes [OK]
