#!/usr/bin/env python3
"""Run Monty on the Run PWM capture simulation and generate analog WAV output.

Pipeline:
  1. Preprocess SID stimulus file -> decimal format for Verilog $fscanf
  2. Compile testbench with iverilog (BEHAVIORAL_SIM mode)
  3. Run simulation with vvp -> monty_pwm.pwl
  4. Filter PWL through 3rd-order RC LPF (Python Forward Euler) -> monty_pwm.wav
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

STIMULUS_SRC = os.path.join(
    PROJECT_DIR, "..", "chip", "rhesutron_sid_asic_tiny",
    "stimuli", "Hubbard_Rob_Monty_on_the_Run_stimulus.txt"
)
STIMULUS_DEC = os.path.join(SCRIPT_DIR, "monty_stim_dec.txt")
PWL_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_pwm.pwl")
WAV_OUTPUT   = os.path.join(SCRIPT_DIR, "monty_pwm.wav")
TB_FILE      = os.path.join(SCRIPT_DIR, "monty_pwm_tb.v")
SIM_BINARY   = os.path.join(SCRIPT_DIR, "monty_pwm_sim")

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
    if os.path.exists(STIMULUS_DEC):
        print(f"Stimulus already preprocessed: {STIMULUS_DEC}")
        return

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
    print("Running simulation (this may take a long time)...")
    result = subprocess.run(
        ["vvp", SIM_BINARY],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,  # so relative paths in testbench resolve correctly
        timeout=3600,      # 60 min timeout
    )
    # Print simulation output
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    if result.returncode != 0:
        print("SIMULATION ERROR:")
        print(result.stderr)
        sys.exit(1)
    print("  Simulation complete")


def filter_and_wav():
    """Run PWL through analog filter simulation and generate WAV."""
    # Import sim_analog functions
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
    print("Monty on the Run — PWM Analog Output Simulation")
    print("=" * 60)

    preprocess_stimulus()
    print()
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
