#!/usr/bin/env python3
"""Run Monty on the Run through bypass capture → WAV.

Pipeline:
  1. Preprocess stimulus: hex→decimal, 12 MHz tick prescaling, time limit
  2. Compile monty_bypass_tb.v with iverilog
  3. Run simulation with vvp → raw samples
  4. Convert raw 8-bit samples → 16-bit signed WAV (44.1 kHz mono)
"""

import os
import subprocess
import sys
import wave

import numpy as np

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

STIMULUS_SRC = os.path.join(
    PROJECT_DIR, "..", "chip", "rhesutron_sid_asic_tiny",
    "stimuli", "Hubbard_Rob_Monty_on_the_Run_stimulus.txt"
)
STIMULUS_DEC = os.path.join(SCRIPT_DIR, "monty_stim_dec.txt")
RAW_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_bypass.raw")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_10s.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_bypass_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_10s_sim")

SAMPLE_RATE = 44117  # 24 MHz / 544

MAX_TICK_12MHZ = 120_000_000  # 10 seconds at 12 MHz

VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/pwm_comp.v",
]


def preprocess_stimulus():
    """Convert stimulus: hex→decimal, prescale ticks, halve freq regs, limit to 10s.

    The stimulus was generated for a design at 12 MHz (0.5 MHz voice update),
    but this design runs at 24 MHz (1 MHz voice update). Frequency register
    values must be halved to produce correct pitch.

    Frequency register addresses (flat SID layout):
      V0: 0x00 (freq_lo), 0x01 (freq_hi)
      V1: 0x07 (freq_lo), 0x08 (freq_hi)
      V2: 0x0E (freq_lo), 0x0F (freq_hi)
    """
    print(f"Preprocessing stimulus (first 10s): {STIMULUS_SRC}")

    # SID frequency register addresses (flat layout)
    FREQ_LO_ADDRS = {0x00, 0x07, 0x0E}
    FREQ_HI_ADDRS = {0x01, 0x08, 0x0F}

    # Track current 16-bit freq per voice to halve correctly
    freq_lo = {0x00: 0, 0x07: 0, 0x0E: 0}
    freq_hi = {0x01: 0, 0x08: 0, 0x0F: 0}
    # Map hi addr → lo addr
    hi_to_lo = {0x01: 0x00, 0x08: 0x07, 0x0F: 0x0E}
    lo_to_hi = {0x00: 0x01, 0x07: 0x08, 0x0E: 0x0F}

    count = 0
    skipped = 0
    freq_adjusted = 0

    with open(STIMULUS_SRC) as fin, open(STIMULUS_DEC, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            tick = int(parts[0])
            if tick > MAX_TICK_12MHZ:
                skipped += 1
                continue
            addr = int(parts[1], 16)
            data = int(parts[2], 16)

            # Halve frequency registers for 1 MHz voice update rate
            # When freq_hi is written, also re-emit corrected freq_lo
            if addr in FREQ_LO_ADDRS:
                freq_lo[addr] = data
                hi_addr = lo_to_hi[addr]
                full = (freq_hi[hi_addr] << 8) | data
                halved = full >> 1
                data = halved & 0xFF
                freq_adjusted += 1
            elif addr in FREQ_HI_ADDRS:
                freq_hi[addr] = data
                lo_addr = hi_to_lo[addr]
                full = (data << 8) | freq_lo[lo_addr]
                halved = full >> 1
                # Emit corrected freq_lo first (now that we know both bytes)
                tick_prescaled = round(tick * 83.333 / 20.0)
                fout.write(f"{tick_prescaled} {lo_addr} {halved & 0xFF}\n")
                count += 1
                data = (halved >> 8) & 0xFF
                freq_adjusted += 1

            # Prescale: 12 MHz ticks → TB timing (tick * 83.333ns / 20ns)
            tick_prescaled = round(tick * 83.333 / 20.0)
            fout.write(f"{tick_prescaled} {addr} {data}\n")
            count += 1

    print(f"  {count} events (skipped {skipped} beyond 10s)")
    print(f"  {freq_adjusted} frequency register writes halved (12 MHz → 24 MHz)")
    print(f"  Written to {STIMULUS_DEC}")
    return count


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
    print("Running Monty bypass simulation (10s + 0.5s tail)...")
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
    print("Monty on the Run — 10-Second Bypass Capture")
    print("=" * 60)
    print()

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
