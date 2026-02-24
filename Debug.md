# Debug & Development Notes

## Test Suite Summary

### Unit Testbench (`tests/tt_um_sid_tb.v`)

15 automated tests covering all major functionality:

| # | Test | What it verifies |
|---|------|-----------------|
| 1 | Reset | PWM output is 0 during reset |
| 2 | Sawtooth | Voice 0 sawtooth produces PDM transitions |
| 3 | Triangle | Voice 0 triangle produces PDM transitions |
| 4 | Pulse | Voice 0 pulse (50% duty) produces PDM transitions |
| 5 | Noise | Voice 0 noise (LFSR) produces PDM transitions |
| 6 | Gate release | PDM activity drops after gate off |
| 7 | Two voices | V0 sawtooth + V1 pulse simultaneous |
| 8 | Three voices | V0 saw + V1 pulse + V2 triangle |
| 9 | Sync modulation | V1 hard-synced to V0 produces output |
| 10 | Per-voice ADSR | V0 high sustain + V1 low sustain differ |
| 11 | Filter bypass | Vol=15, no routing: audio passes through |
| 12 | LP filter | Low-pass changes output vs bypass |
| 13 | Volume = 0 | Vol=0 produces DC midpoint (silence) |
| 14 | HP filter | High-pass mode produces output |
| 15 | BP filter | Band-pass mode produces output |

**Status: All 15 PASS**

### Waveform Generation Testbench (`tests/gen_wav_tb.v`)

Captures 12 raw files at ~44,117 Hz sample rate (12 MHz / 272):
- 9 waveform captures: saw/tri/pulse x 220/440/880 Hz
- 3 filter captures at 440 Hz sawtooth: LP, HP, BP
- Each file: 5,000 samples

## Filter Optimization Journey

### Stage 1: 24-bit SVF (initial implementation)
- Full 24-bit Q16.8 fixed-point arithmetic
- Hardware multipliers for frequency and damping
- **Cell count: ~3,200 cells** -- far over budget for 1x2 tile

### Stage 2: 16-bit SVF
- Reduced to 16-bit Q12.4 internal precision
- Still using hardware multipliers
- **Cell count: ~2,400 cells** -- still too large

### Stage 3: 12-bit Q8.4 SVF with shift-add (final)
- 12-bit signed Q8.4 internal state (8 integer + 4 fractional bits)
- **Shift-add multiplies**: no hardware multiplier needed
  - Frequency: 7-bit `alpha1` via 7-term shift-add (/128)
  - Damping: 4-bit `alpha2` via 4-term shift-add (/8, exact)
- Saturation to prevent overflow
- **Cell count: ~1,567 cells**
- Total design with filter: ~88% utilization of 1x2 tile

### Coefficient Mapping
- `alpha1 = fc[10:4]` -- 7-bit frequency coefficient
- `alpha2 = 15 - res` -- 4-bit damping (inverse of resonance)

## Waveform Simulation Results

All waveforms captured at 220, 440, and 880 Hz using voice 0 with instant attack, max sustain.

### Sawtooth (`tests/waveform_saw.png`)
- Clean ramp-and-reset shape at all frequencies
- Correct frequency doubling between octaves
- Amplitude ~0-63 (single voice through ÷4 mixer)

### Triangle (`tests/waveform_tri.png`)
- Symmetric triangle shape at all frequencies
- Smooth peaks and valleys
- Same amplitude range as sawtooth

### Pulse (`tests/waveform_pulse.png`)
- Clean 50% duty cycle square wave (pw=0x800)
- Sharp transitions between high and low states
- Correct period at all three frequencies

## Filter Response Observations (`tests/filter_comparison.png`)

Input: 440 Hz sawtooth, fc_hi=0x20, res=0, filt_en=V0

### Low-Pass
- Sawtooth edges are smoothed/rounded
- Fundamental frequency preserved, harmonics attenuated
- Waveform appears more sinusoidal than raw sawtooth

### Band-Pass
- Output centered around DC midpoint (~120)
- Small deviations at sawtooth edge transitions
- Passes frequencies near cutoff, attenuates both low and high

### High-Pass
- Output centered near DC midpoint (~120)
- Small high-frequency ripple visible
- Sawtooth fundamental largely removed at this cutoff setting

## Known Limitations

1. **Amplitude scaling**: Single-voice output is ~0-63 due to ÷4 mixer (designed for 3-voice mix to avoid clipping). Three simultaneous voices at max use the full 0-255 range.

2. **Filter precision**: 12-bit Q8.4 arithmetic limits dynamic range vs the real SID's analog filter. Audible for extreme resonance settings.

3. **Filter sample rate**: Filter processes at the mixer output rate (~53 kHz, once per mod-5 frame), not at the 12 MHz clock. This limits the filter's effective Nyquist.

4. **Noise LFSR**: Shared 15-bit LFSR clocked from voice 0's accumulator bit 11. Noise pitch only tracks voice 0's frequency setting.

5. **No voice 3 off**: The V3OFF bit in mode_vol[7] is parsed but not yet implemented (voice 3 doesn't exist in this 3-voice design).
