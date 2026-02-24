#!/usr/bin/env python3
"""Convert raw PCM text files from gen_wav_tb to WAV files."""
import struct
import glob
import os

SAMPLE_RATE = 44117  # 12 MHz / 272


def raw_to_wav(raw_path, wav_path):
    """Read text file of 8-bit unsigned samples, write 8-bit unsigned PCM WAV."""
    samples = []
    with open(raw_path) as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(int(line) & 0xFF)

    num_samples = len(samples)
    data_size = num_samples  # 8-bit = 1 byte per sample

    with open(wav_path, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))
        f.write(b'WAVE')
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))            # chunk size
        f.write(struct.pack('<H', 1))             # PCM format
        f.write(struct.pack('<H', 1))             # mono
        f.write(struct.pack('<I', SAMPLE_RATE))
        f.write(struct.pack('<I', SAMPLE_RATE))   # byte rate (1 byte/sample)
        f.write(struct.pack('<H', 1))             # block align
        f.write(struct.pack('<H', 8))             # bits per sample
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        f.write(bytes(samples))

    print(f"  {wav_path}: {num_samples} samples, {num_samples/SAMPLE_RATE:.2f}s")


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    raw_files = sorted(glob.glob(os.path.join(script_dir, '*.raw')))
    if not raw_files:
        print("No .raw files found. Run the Verilog simulation first.")
        exit(1)

    for raw_path in raw_files:
        wav_path = raw_path.replace('.raw', '.wav')
        raw_to_wav(raw_path, wav_path)

    print(f"\nConverted {len(raw_files)} files.")
