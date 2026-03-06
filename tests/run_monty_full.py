#!/usr/bin/env python3
"""Run full-length Monty on the Run through SID capture → simulation → WAV.

Pipeline:
  1. Capture SID register writes from .sid file using py65emu (6502 emulation)
  2. Translate capture CSV to stimulus file (tick addr data format)
  3. Compile monty_full_tb.v with iverilog
  4. Run simulation with vvp → raw PWM-decimated samples
  5. Convert raw samples → 16-bit signed WAV (44.1 kHz mono)
"""

import os
import subprocess
import sys
import wave

import numpy as np

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

SID_FILE     = os.path.join(
    PROJECT_DIR, "..", "chip", "sid-capture", "sid",
    "Hubbard_Rob_Monty_on_the_Run.sid"
)
CAPTURE_CSV  = os.path.join(SCRIPT_DIR, "Hubbard_Rob_Monty_on_the_Run_capture.csv")
STIMULUS_TXT = os.path.join(SCRIPT_DIR, "monty_full_stim.txt")
RAW_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_full_pwm.raw")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_full.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_full_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_full_sim")

SAMPLE_RATE = 44117  # 24 MHz / 544
DURATION_S  = 210    # 3.5 minutes
NUM_FRAMES  = DURATION_S * 50  # 50 Hz frame rate

# PWM decimation window size (must match TB DECIM parameter)
PWM_DECIM = 544

VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/pwm_comp.v",
]


def step1_capture():
    """Capture SID register writes from .sid file."""
    print(f"Step 1: SID Capture ({NUM_FRAMES} frames = {DURATION_S}s)")
    print(f"  SID file: {SID_FILE}")

    # Import and run sid_capture directly
    sys.path.insert(0, SCRIPT_DIR)
    from sid_capture import run_sid_capture, save_csv

    result = run_sid_capture(SID_FILE, num_frames=NUM_FRAMES)
    save_csv(result, CAPTURE_CSV)
    print(f"  Saved: {CAPTURE_CSV} ({len(result['writes'])} writes)")
    return len(result['writes'])


def step2_translate():
    """Translate SID capture CSV to stimulus file."""
    print(f"\nStep 2: Translate CSV → Stimulus")

    sys.path.insert(0, SCRIPT_DIR)
    from sid_to_stimulus import translate

    count = translate(CAPTURE_CSV, STIMULUS_TXT)
    return count


def step3_compile():
    """Compile the testbench with iverilog."""
    print(f"\nStep 3: Compile Testbench")

    srcs = [os.path.join(PROJECT_DIR, s) for s in VERILOG_SRCS]
    srcs.append(TB_FILE)
    cmd = ["iverilog", "-g2005", "-DBEHAVIORAL_SIM", "-o", SIM_BINARY] + srcs

    print(f"  iverilog -g2005 -DBEHAVIORAL_SIM ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("COMPILE ERROR:")
        print(result.stderr)
        sys.exit(1)
    if result.stderr:
        print(f"  Warnings: {result.stderr.strip()}")
    print("  Compilation successful")


def step4_simulate():
    """Run the simulation."""
    print(f"\nStep 4: Simulate ({DURATION_S}s + 1s tail)")
    print(f"  This will take a long time...")

    result = subprocess.run(
        ["vvp", SIM_BINARY],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,
        timeout=86400,  # 24 hour timeout
    )
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    if result.returncode != 0:
        print("SIMULATION ERROR:")
        print(result.stderr)
        sys.exit(1)
    print("  Simulation complete")


def step5_wav():
    """Convert raw PWM-decimated samples to WAV."""
    print(f"\nStep 5: Convert Raw → WAV")

    samples = []
    with open(RAW_OUTPUT) as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(int(line))

    n = len(samples)
    duration = n / SAMPLE_RATE
    print(f"  {n} samples, {duration:.2f} seconds at {SAMPLE_RATE} Hz")
    print(f"  Raw range: {min(samples)}-{max(samples)} (PWM high count per {PWM_DECIM} clocks)")

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
    print("Monty on the Run — Full 3.5 Minute PWM Capture")
    print("=" * 60)
    print()

    step1_capture()
    step2_translate()
    step3_compile()
    step4_simulate()
    wav_path = step5_wav()

    print()
    print("=" * 60)
    print(f"Done! Output: {wav_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
