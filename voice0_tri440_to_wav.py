#!/usr/bin/env python3
"""Convert voice0_tri440.raw to WAV, showing voice output directly."""
import struct
import sys

SAMPLE_RATE = 44092  # 50 MHz / 1134

def write_wav(filename, samples, sample_rate, bits=16):
    """Write samples as a WAV file."""
    num = len(samples)
    bytes_per = bits // 8
    with open(filename, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + num * bytes_per))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<IHHIIHH', 16, 1, 1, sample_rate,
                            sample_rate * bytes_per, bytes_per, bits))
        f.write(b'data')
        f.write(struct.pack('<I', num * bytes_per))
        for s in samples:
            f.write(struct.pack('<h', max(-32768, min(32767, s))))


def main():
    raw_path = 'voice0_tri440.raw'

    mix_samples = []
    voice_samples = []
    acc_values = []

    with open(raw_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 3:
                mix_samples.append(int(parts[0]))
                voice_samples.append(int(parts[1]))
                acc_values.append(int(parts[2]))

    print(f"Read {len(mix_samples)} samples from {raw_path}")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Duration: {len(mix_samples)/SAMPLE_RATE:.3f}s")

    # Mix output: 8-bit (0-63 typical range for single voice with /4 mix)
    mix_min, mix_max = min(mix_samples), max(mix_samples)
    print(f"\nmix_out range: {mix_min} - {mix_max}")

    # Voice output: 12-bit (waveform * envelope)
    vo_min, vo_max = min(voice_samples), max(voice_samples)
    print(f"voice_out range: {vo_min} - {vo_max}")

    # Detect period from accumulator wraparound
    wraps = []
    for i in range(1, len(acc_values)):
        if acc_values[i] < acc_values[i-1]:
            wraps.append(i)
    if len(wraps) >= 2:
        period_samples = wraps[1] - wraps[0]
        freq = SAMPLE_RATE / period_samples
        print(f"\nDetected period: {period_samples} samples")
        print(f"Detected frequency: {freq:.1f} Hz")
        print(f"Periods captured: {len(wraps)}")

    # Write WAV from voice_out (12-bit → 16-bit signed)
    wav_voice = [(v - vo_max // 2) * (32767 // max(vo_max // 2, 1))
                 for v in voice_samples]
    write_wav('wav/voice0_tri440_voice.wav', wav_voice, SAMPLE_RATE)
    print(f"\nWrote wav/voice0_tri440_voice.wav (voice_out, full scale)")

    # Write WAV from mix_out (8-bit → 16-bit signed)
    wav_mix = [(m - 128) * 256 for m in mix_samples]
    write_wav('wav/voice0_tri440_mix.wav', wav_mix, SAMPLE_RATE)
    print(f"Wrote wav/voice0_tri440_mix.wav (mix_out)")


if __name__ == '__main__':
    main()
