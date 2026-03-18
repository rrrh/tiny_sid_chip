#!/usr/bin/env python3
"""Run Monty on the Run V0-only PWM capture and generate analog-filtered WAV.

Pipeline:
  1. Ensure V0 stimulus exists (from run_monty_v0.py)
  2. Compile V0 PWM testbench with iverilog
  3. Run simulation with vvp → monty_v0_pwm.pwl
  4. Filter PWL through 3rd-order RC LPF → monty_v0_pwm.wav
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

STIMULUS_DEC = os.path.join(SCRIPT_DIR, "monty_v0_stim_dec.txt")
PWL_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_v0_pwm.pwl")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_v0_pwm.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_v0_pwm_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_v0_pwm_sim")

VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/pwm_comp.v",
]


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
    print("Running V0-only PWM capture simulation...")
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


def filter_and_wav():
    """Run PWL through analog filter simulation and generate WAV."""
    sys.path.insert(0, SCRIPT_DIR)
    from sim_analog import load_pwl, simulate_filter, write_wav

    print(f"Loading PWL: {PWL_OUTPUT}")
    t_pwl, v_pwl = load_pwl(PWL_OUTPUT)
    print(f"  {len(t_pwl)} points, {t_pwl[-1]:.4f} s")

    print("Running analog filter simulation (Forward Euler, dt=200ns)...")
    dt = 200e-9
    t, v1, v2, v3, v_out = simulate_filter(t_pwl, v_pwl, dt)
    print(f"  {len(t)} simulation steps")

    print(f"Writing WAV: {WAV_OUTPUT}")
    write_wav(t, v_out, WAV_OUTPUT, sample_rate=44100)


def main():
    print("=" * 60)
    print("Monty on the Run — Voice 0 Only, PWM Analog Output")
    print("=" * 60)

    if not os.path.exists(STIMULUS_DEC):
        print(f"ERROR: V0 stimulus not found: {STIMULUS_DEC}")
        print("  Run run_monty_v0.py first to generate it.")
        sys.exit(1)

    compile_sim()
    print()
    run_sim()
    print()

    if not os.path.exists(PWL_OUTPUT):
        print(f"ERROR: PWL file not generated: {PWL_OUTPUT}")
        sys.exit(1)

    filter_and_wav()

    print()
    print("=" * 60)
    print(f"Done! Output: {WAV_OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
