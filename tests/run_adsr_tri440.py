#!/usr/bin/env python3
"""ADSR envelope test: 440 Hz triangle, slow attack, medium decay, long release.

Pipeline:
  1. Compile adsr_tri440_tb.v with iverilog
  2. Run simulation with vvp → adsr_tri440.raw
  3. Convert raw 8-bit samples → 16-bit signed WAV (44.1 kHz mono)
"""

import os
import subprocess
import sys
import wave

import numpy as np

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

TB_FILE    = os.path.join(SCRIPT_DIR, "adsr_tri440_tb.v")
SIM_BINARY = os.path.join(SCRIPT_DIR, "adsr_tri440_sim")
RAW_OUTPUT = os.path.join(SCRIPT_DIR, "adsr_tri440.raw")
WAV_OUTPUT = os.path.join(SCRIPT_DIR, "adsr_tri440.wav")

SAMPLE_RATE = 44117  # 24 MHz / 544

VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/pwm_comp.v",
]


def compile_sim():
    srcs = [os.path.join(PROJECT_DIR, s) for s in VERILOG_SRCS]
    srcs.append(TB_FILE)

    cmd = ["iverilog", "-g2005", "-DBEHAVIORAL_SIM", "-o", SIM_BINARY] + srcs

    print("Compiling: iverilog -g2005 -DBEHAVIORAL_SIM ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("COMPILE ERROR:")
        print(result.stderr)
        sys.exit(1)
    if result.stderr:
        print(f"  Warnings: {result.stderr.strip()}")
    print("  Compilation successful")


def run_sim():
    print("Running ADSR simulation (~4s audio, expect ~30-40 min)...")
    result = subprocess.run(
        ["vvp", SIM_BINARY],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,
        timeout=3600,
    )
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    if result.returncode != 0:
        print("SIMULATION ERROR:")
        print(result.stderr)
        sys.exit(1)
    print("  Simulation complete")


def raw_to_wav():
    print(f"Converting {RAW_OUTPUT} → {WAV_OUTPUT}")

    samples = []
    with open(RAW_OUTPUT) as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(int(line))

    n = len(samples)
    duration = n / SAMPLE_RATE
    print(f"  {n} samples, {duration:.2f} seconds at {SAMPLE_RATE} Hz")
    print(f"  Raw range: {min(samples)}-{max(samples)}")

    arr = np.array(samples, dtype=np.float64)
    dc = arr.mean()
    ac = arr - dc
    peak = max(abs(ac.min()), abs(ac.max()))

    if peak > 0:
        scale = 30000.0 / peak
        pcm = np.clip(ac * scale, -32768, 32767).astype(np.int16)
    else:
        pcm = np.zeros(n, dtype=np.int16)
        scale = 0

    print(f"  DC offset: {dc:.1f}, peak: {peak:.1f}, scale: {scale:.1f}")

    with wave.open(WAV_OUTPUT, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    print(f"  WAV written: {WAV_OUTPUT}")
    return WAV_OUTPUT


def main():
    print("=" * 60)
    print("ADSR Envelope Test — 440 Hz Triangle")
    print("  Attack: 500ms  Decay: 240ms  Sustain: 0x8 (50%)")
    print("  Gate hold: ~940ms  Release: 2.4s")
    print("=" * 60)
    print()

    compile_sim()
    print()
    run_sim()
    print()
    wav_path = raw_to_wav()

    print()
    print("=" * 60)
    print(f"Done! Output: {wav_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
