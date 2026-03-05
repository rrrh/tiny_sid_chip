#!/usr/bin/env python3
"""Extract Voice 0 from Monty on the Run stimulus, simulate, and generate WAV.

Pipeline:
  1. Filter stimulus for V0 registers (SID addr 0x00–0x06) only
  2. Prescale 12 MHz ticks → 50 MHz-equivalent for testbench
  3. Compile testbench with iverilog
  4. Run simulation with vvp
  5. Convert raw 8-bit samples → 16-bit signed WAV (44.1 kHz mono)
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
    "stimuli", "Hubbard_Rob_Monty_on_the_Run_stimulus.txt"
)
STIMULUS_DEC = os.path.join(SCRIPT_DIR, "monty_v0_stim_dec.txt")
RAW_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_v0_bypass.raw")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_v0_bypass.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_v0_bypass_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_v0_bypass_sim")

SAMPLE_RATE = 44117  # 24 MHz / 544

VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/sar_adc_8bit.v",
]


def extract_v0_stimulus():
    """Extract V0 events (SID addr 0x00-0x06) and prescale ticks."""
    print(f"Extracting V0 from: {STIMULUS_SRC}")
    total = 0
    v0_count = 0
    with open(STIMULUS_SRC) as fin, open(STIMULUS_DEC, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            total += 1
            tick = int(parts[0])
            addr = int(parts[1], 16)
            data = int(parts[2], 16)

            # V0 registers: SID addr 0x00–0x06
            if addr > 6:
                continue

            # Prescale: 12 MHz ticks → 50 MHz-equivalent (tick * 83.333 / 20)
            tick_prescaled = round(tick * 83.333 / 20.0)
            fout.write(f"{tick_prescaled} {addr} {data}\n")
            v0_count += 1

    print(f"  {v0_count}/{total} events are V0 (addr 0x00–0x06)")
    print(f"  Written to {STIMULUS_DEC}")
    return v0_count


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
    """Run simulation with vvp."""
    print("Running V0-only simulation...")
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
    print("Monty on the Run — Voice 0 Only Simulation")
    print("=" * 60)

    extract_v0_stimulus()
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
