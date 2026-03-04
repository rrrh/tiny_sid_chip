#!/usr/bin/env python3
"""Run Monty on the Run filter-bypass simulation and generate WAV output.

Pipeline:
  1. Preprocess SID stimulus file → decimal format for Verilog $fscanf
  2. Compile testbench with iverilog (BEHAVIORAL_SIM mode)
  3. Run simulation with vvp
  4. Convert raw 8-bit samples → 16-bit signed WAV (44.1 kHz mono)
"""

import os
import subprocess
import sys
import wave

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

STIMULUS_SRC = os.path.join(
    PROJECT_DIR, "..", "chip", "rhesutron_sid_asic_tiny",
    "stimuli", "Hubbard_Rob_Monty_on_the_Run_tt6581_stimulus.txt"
)
STIMULUS_DEC = os.path.join(SCRIPT_DIR, "monty_stim_dec.txt")
RAW_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_bypass.raw")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_bypass.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_bypass_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_bypass_sim")

SAMPLE_RATE = 44117  # 24 MHz / 544

# Verilog source files needed for compilation
VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/sar_adc_8bit.v",
]


def preprocess_stimulus():
    """Convert stimulus file to decimal format (strip comments, 0x prefixes)."""
    print(f"Preprocessing stimulus: {STIMULUS_SRC}")
    count = 0
    with open(STIMULUS_SRC) as fin, open(STIMULUS_DEC, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            tick = int(parts[0])
            addr = int(parts[1], 16)
            data = int(parts[2], 16)
            fout.write(f"{tick} {addr} {data}\n")
            count += 1
    print(f"  {count} events written to {STIMULUS_DEC}")
    return count


def compile_sim():
    """Compile testbench with iverilog."""
    srcs = [os.path.join(PROJECT_DIR, s) for s in VERILOG_SRCS]
    srcs.append(TB_FILE)

    cmd = [
        "iverilog",
        "-g2005",
        "-DBEHAVIORAL_SIM",
        "-o", SIM_BINARY,
    ] + srcs

    print(f"Compiling: iverilog -g2005 -DBEHAVIORAL_SIM ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("COMPILE ERROR:")
        print(result.stderr)
        sys.exit(1)
    if result.stderr:
        print(f"  Warnings: {result.stderr.strip()}")
    print("  Compilation successful")


def run_sim():
    """Run simulation with vvp."""
    print(f"Running simulation (this may take several minutes)...")
    result = subprocess.run(
        ["vvp", SIM_BINARY],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,  # so relative paths in testbench resolve correctly
        timeout=3600,      # 60 min timeout (full sim ~45 min)
    )
    # Print simulation output
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    if result.returncode != 0:
        print("SIMULATION ERROR:")
        print(result.stderr)
        sys.exit(1)
    print("  Simulation complete")


def raw_to_wav():
    """Convert raw 8-bit unsigned samples to normalized 16-bit signed WAV."""
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

    # Remove DC offset and normalize to 16-bit range
    arr = np.array(samples, dtype=np.float64)
    dc = arr.mean()
    ac = arr - dc
    peak = max(abs(ac.min()), abs(ac.max()))

    if peak > 0:
        scale = 30000.0 / peak  # leave headroom
        pcm = np.clip(ac * scale, -32768, 32767).astype(np.int16)
    else:
        pcm = np.zeros(n, dtype=np.int16)

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
    print("Monty on the Run — Filter Bypass Simulation")
    print("=" * 60)

    preprocess_stimulus()
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
