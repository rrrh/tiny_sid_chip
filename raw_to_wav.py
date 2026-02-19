#!/usr/bin/env python3
"""Convert raw PCM text files from gen_wav_tb to WAV files."""
import struct
import os
import glob

SAMPLE_RATE = 44208  # 50 MHz / 1131

def raw_to_wav(raw_path, wav_path):
    """Read text file of 8-bit unsigned samples, write 16-bit signed WAV."""
    samples = []
    with open(raw_path) as f:
        for line in f:
            line = line.strip()
            if line:
                val = int(line)
                # Convert 8-bit unsigned (0-255) to 16-bit signed
                samples.append((val - 128) * 256)

    num_samples = len(samples)
    data_size = num_samples * 2  # 16-bit = 2 bytes per sample

    with open(wav_path, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))
        f.write(b'WAVE')
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))       # chunk size
        f.write(struct.pack('<H', 1))        # PCM format
        f.write(struct.pack('<H', 1))        # mono
        f.write(struct.pack('<I', SAMPLE_RATE))
        f.write(struct.pack('<I', SAMPLE_RATE * 2))  # byte rate
        f.write(struct.pack('<H', 2))        # block align
        f.write(struct.pack('<H', 16))       # bits per sample
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        for s in samples:
            f.write(struct.pack('<h', max(-32768, min(32767, s))))

    print(f"  {wav_path}: {num_samples} samples, {num_samples/SAMPLE_RATE:.2f}s")


if __name__ == '__main__':
    raw_files = sorted(glob.glob('voice*_*.raw'))
    if not raw_files:
        print("No .raw files found. Run the Verilog simulation first.")
        exit(1)

    os.makedirs('wav', exist_ok=True)
    for raw_path in raw_files:
        wav_path = os.path.join('wav', raw_path.replace('.raw', '.wav'))
        raw_to_wav(raw_path, wav_path)

    print(f"\nGenerated {len(raw_files)} WAV files in wav/")
