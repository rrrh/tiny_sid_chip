#!/usr/bin/env python3
"""SID Waveform Verification — compile, simulate, filter, plot, report.

Pipeline:
  1. Compile waveform_verify_tb.v with iverilog (-g2005 -DBEHAVIORAL_SIM)
  2. Run vvp simulation -> 6 PWL files (wv_*.pwl)
  3. Filter each PWL through 3rd-order RC LPF -> WAV files
  4. Generate 6 PNG plots (raw + filtered per tone)
  5. Generate waveform_verify_report.md
"""

import os
import subprocess
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

TB_FILE = os.path.join(SCRIPT_DIR, "waveform_verify_tb.v")
SIM_BINARY = os.path.join(SCRIPT_DIR, "waveform_verify_sim")

# Same source list as run_monty_pwm.py
VERILOG_SRCS = [
    "src/tt_um_sid.v",
    "src/output_lpf.v",
    "src/pwm_audio.v",
    "macros/nl/r2r_dac_8bit.v",
    "macros/nl/svf_2nd.v",
    "macros/nl/pwm_comp.v",
]

# Tone definitions: (name, label, freq_hz, waveform)
TONES = [
    ("wv_tri_220",   "Triangle 220 Hz",    220, "Triangle"),
    ("wv_tri_440",   "Triangle 440 Hz",    440, "Triangle"),
    ("wv_tri_880",   "Triangle 880 Hz",    880, "Triangle"),
    ("wv_saw_220",   "Sawtooth 220 Hz",    220, "Sawtooth"),
    ("wv_saw_440",   "Sawtooth 440 Hz",    440, "Sawtooth"),
    ("wv_saw_880",   "Sawtooth 880 Hz",    880, "Sawtooth"),
    ("wv_pulse_220", "Pulse 220 Hz (50%)", 220, "Pulse"),
    ("wv_pulse_440", "Pulse 440 Hz (50%)", 440, "Pulse"),
    ("wv_pulse_880", "Pulse 880 Hz (50%)", 880, "Pulse"),
    ("wv_noise_220", "Noise 220 Hz",       220, "Noise"),
    ("wv_noise_440", "Noise 440 Hz",       440, "Noise"),
    ("wv_noise_880", "Noise 880 Hz",       880, "Noise"),
]

WAVEFORMS = ["Triangle", "Sawtooth", "Pulse", "Noise"]
FREQUENCIES = [220, 440, 880]


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
    print("Running simulation (~24M cycles, expect ~60s)...")
    result = subprocess.run(
        ["vvp", SIM_BINARY],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,
        timeout=600,
    )
    for line in result.stdout.strip().split("\n"):
        print(f"  {line}")
    if result.returncode != 0:
        print("SIMULATION ERROR:")
        print(result.stderr)
        sys.exit(1)
    print("  Simulation complete")


def filter_and_wav():
    """Filter all 6 PWL files through analog sim and generate WAVs.

    Returns dict of {name: (t, v1, v2, v3, v_out)} for plotting.
    """
    sys.path.insert(0, SCRIPT_DIR)
    from sim_analog import load_pwl, simulate_filter, write_wav

    dt = 200e-9
    results = {}

    for name, label, _, _ in TONES:
        pwl_path = os.path.join(SCRIPT_DIR, name + ".pwl")
        wav_path = os.path.join(SCRIPT_DIR, name + "_analog.wav")

        if not os.path.exists(pwl_path):
            print(f"  WARNING: {pwl_path} not found, skipping")
            continue

        print(f"\n  {label}:")
        t_pwl, v_pwl = load_pwl(pwl_path)
        print(f"    PWL: {len(t_pwl)} points, {t_pwl[-1]*1e3:.1f} ms")

        t, v1, v2, v3, v_out = simulate_filter(t_pwl, v_pwl, dt)
        write_wav(t, v_out, wav_path)
        results[name] = (t, v1, v2, v3, v_out)

    return results


def generate_plots(results):
    """Generate 2-panel PNG for each tone: raw PWL (stage 1) + filtered output."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for name, label, freq, waveform in TONES:
        if name not in results:
            continue

        t, v1, _v2, _v3, v_out = results[name]
        png_path = os.path.join(SCRIPT_DIR, name + ".png")

        # Decimate for plotting
        dec = max(1, len(t) // 50000)
        t_ms = t[::dec] * 1e3

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        fig.suptitle(f"SID Waveform Verification — {label}", fontsize=13)

        ax1.plot(t_ms, v1[::dec], color="#FF9800", linewidth=0.4)
        ax1.set_ylabel("Voltage (V)")
        ax1.set_title("Raw PWM (after 1st RC stage)", fontsize=10)
        ax1.grid(True, alpha=0.3)

        ax2.plot(t_ms, v_out[::dec], color="#E91E63", linewidth=0.5)
        ax2.set_ylabel("Voltage (V)")
        ax2.set_xlabel("Time (ms)")
        ax2.set_title("Filtered Audio Output (AC-coupled)", fontsize=10)
        ax2.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Plot: {png_path}")


def generate_report(results):
    """Generate waveform_verify_report.md."""
    report_path = os.path.join(SCRIPT_DIR, "waveform_verify_report.md")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    freq_regs = {220: "0x0E6B", 440: "0x1CD6", 880: "0x39AC"}
    wav_regs = {"Triangle": "0x11", "Sawtooth": "0x21", "Pulse": "0x41", "Noise": "0x81"}

    lines = []
    lines.append("# SID Waveform Verification Report")
    lines.append("")
    lines.append(f"**Date:** {now}")
    lines.append(f"**Capture duration:** 75 ms per tone (1,800,000 cycles at 24 MHz)")
    lines.append(f"**Attack settle:** 200,000 cycles (~8.3 ms)")
    lines.append(f"**Filter:** 3rd-order RC LPF (R=3.3k x3, C=4.7nF x3) + Cac=1uF + Rload=10k")
    lines.append(f"**Waveforms:** 4 types x 3 frequencies = 12 captures")
    lines.append("")
    lines.append("---")
    lines.append("")

    # One section per waveform type
    for wf in WAVEFORMS:
        wf_tones = [t for t in TONES if t[3] == wf]
        lines.append(f"## {wf} (220 / 440 / 880 Hz)")
        lines.append("")
        lines.append(f"| # | Frequency | Freq Reg | Waveform Reg | PWL File |")
        lines.append(f"|---|-----------|----------|-------------|----------|")
        for i, (name, label, freq, _) in enumerate(wf_tones, 1):
            lines.append(f"| {i} | {freq} Hz | {freq_regs[freq]} | {wav_regs[wf]} | `{name}.pwl` |")
        lines.append("")

        for name, label, _, _ in wf_tones:
            if name in results:
                lines.append(f"### {label}")
                lines.append(f"![{label}]({name}.png)")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    n_ok = len(results)
    n_total = len(TONES)
    lines.append(f"- **Tones captured:** {n_ok}/{n_total}")
    lines.append(f"- **Pass criteria:** All {n_total} PWL files generated, WAVs audible at correct pitch")
    lines.append("")
    lines.append("### Output Files")
    lines.append("")
    for name, _, _, _ in TONES:
        exists_pwl = os.path.exists(os.path.join(SCRIPT_DIR, name + ".pwl"))
        exists_wav = os.path.exists(os.path.join(SCRIPT_DIR, name + "_analog.wav"))
        exists_png = os.path.exists(os.path.join(SCRIPT_DIR, name + ".png"))
        status = "OK" if (exists_pwl and exists_wav and exists_png) else "MISSING"
        lines.append(f"- `{name}`: PWL={'yes' if exists_pwl else 'no'} "
                      f"WAV={'yes' if exists_wav else 'no'} "
                      f"PNG={'yes' if exists_png else 'no'} [{status}]")
    lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport: {report_path}")


def main():
    print("=" * 60)
    print("SID Waveform Verification")
    print("=" * 60)
    print()

    compile_sim()
    print()
    run_sim()
    print()

    # Verify PWL files were generated
    missing = []
    for name, _, _, _ in TONES:
        pwl = os.path.join(SCRIPT_DIR, name + ".pwl")
        if not os.path.exists(pwl):
            missing.append(pwl)
    if missing:
        print("ERROR: Missing PWL files:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    print("Filtering PWL -> WAV...")
    results = filter_and_wav()

    print("\nGenerating plots...")
    generate_plots(results)

    print("\nGenerating report...")
    generate_report(results)

    print()
    print("=" * 60)
    print("Done! See tests/waveform_verify_report.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
