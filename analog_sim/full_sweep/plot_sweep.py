#!/usr/bin/env python3
"""Plot results from full system frequency sweep simulation.

Reads ngspice output data (segmented wrdata files) and generates 4 PNG plots:
  1. freq_response.png     — Frequency response (semilog x)
  2. waveform_waterfall.png — 4×4 grid of audio waveforms at each freq
  3. pwm_recovery.png       — PWM recovery detail at 1 kHz
  4. full_sweep_summary.png — Combined 2×2 summary
"""

import os
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Frequency points
FREQS = [250, 330, 400, 500, 660, 800, 1000, 1300,
         2000, 2700, 4000, 5300, 8000, 10600, 12700, 16000]
REF_IDX = 6  # 1 kHz reference index

# ngspice wrdata column mapping (interleaved: time val time val ...)
# wrdata seg.dat v(vin) v(lp) v(pwm_out) v(audio_out) v(mid1) v(mid3)
COL_TIME = 0
COL_VIN = 1
COL_LP = 3
COL_PWM = 5
COL_AUDIO = 7
COL_MID1 = 9
COL_MID3 = 11


def load_wrdata(path):
    """Load ngspice wrdata output (space-separated, first column = time).
    Skips comment lines starting with * or #."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("#"):
                continue
            parts = line.split()
            try:
                row = [float(x) for x in parts]
                data.append(row)
            except ValueError:
                continue
    return np.array(data) if data else np.zeros((0, 7))


def load_segments(script_dir):
    """Load per-segment wrdata files: seg_00.dat through seg_15.dat."""
    segments = []
    for i in range(16):
        seg_path = os.path.join(script_dir, f"seg_{i:02d}.dat")
        if os.path.exists(seg_path):
            data = load_wrdata(seg_path)
            segments.append(data)
        else:
            segments.append(np.zeros((0, 7)))
    return segments


def load_gain_data(path):
    """Load sweep_gain.dat (freq pkpk pairs)."""
    freqs, gains = [], []
    with open(path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    freqs.append(float(parts[0]))
                    gains.append(float(parts[1]))
                except ValueError:
                    continue
    return np.array(freqs), np.array(gains)


def plot_freq_response(freqs, gains, outpath):
    """Plot 1: Frequency response, semilog x, normalized to 0 dB at 1 kHz."""
    ref_gain = gains[REF_IDX] if gains[REF_IDX] > 0 else 1e-6
    gain_db = 20 * np.log10(np.maximum(gains, 1e-9) / ref_gain)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.semilogx(freqs, gain_db, "o-", color="#1976D2", linewidth=2, markersize=8)
    ax.axhline(-3, color="#E53935", linestyle="--", linewidth=1, alpha=0.7, label="-3 dB")
    ax.axhline(0, color="gray", linestyle=":", linewidth=0.5)
    ax.set_xlabel("Frequency (Hz)", fontsize=12)
    ax.set_ylabel("Gain (dB, ref 1 kHz)", fontsize=12)
    ax.set_title("SID Full Chain \u2014 Frequency Response\n"
                 "SVF (LP, fc=fin, Q=1) \u2192 LPF \u2192 PWM \u2192 3rd-order RC",
                 fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, which="both", alpha=0.3)
    ax.set_xlim(200, 20000)
    ax.set_ylim(-20, 6)

    for f, g in zip(freqs, gain_db):
        ax.annotate(f"{g:.1f}", (f, g), textcoords="offset points",
                    xytext=(0, 10), fontsize=7, ha="center", color="#555")

    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {outpath}")


def plot_waveform_grid(segments, outpath):
    """Plot 2: 4x4 grid of audio_out waveforms, last 5ms of each segment."""
    fig, axes = plt.subplots(4, 4, figsize=(16, 12))
    fig.suptitle("SID Full Chain \u2014 Audio Output Waveforms (16 Frequency Points)",
                 fontsize=14, y=0.98)

    # Compute global y-range across all 16 segments for uniform scaling
    # Plot last 10ms of each segment (after 50ms AC coupling cap settling)
    y_min, y_max = 0.0, 0.0
    for i in range(len(FREQS)):
        if i < len(segments) and len(segments[i]) > 0:
            data = segments[i]
            t = data[:, COL_TIME]
            t_max = t[-1]
            mask = t >= (t_max - 10e-3)
            if np.any(mask):
                audio_out = data[mask, COL_AUDIO]
                y_min = min(y_min, audio_out.min())
                y_max = max(y_max, audio_out.max())
    y_margin = (y_max - y_min) * 0.05 if y_max > y_min else 0.1
    y_min -= y_margin
    y_max += y_margin

    for i, freq in enumerate(FREQS):
        row, col = divmod(i, 4)
        ax = axes[row][col]

        if i < len(segments) and len(segments[i]) > 0:
            data = segments[i]
            t = data[:, COL_TIME]
            audio_out = data[:, COL_AUDIO]
            t_max = t[-1]

            # Last 10ms (settled region)
            mask = t >= (t_max - 10e-3)
            if np.any(mask):
                t_ms = (t[mask] - t[mask][0]) * 1e3
                ax.plot(t_ms, audio_out[mask], color="#E91E63", linewidth=0.5)

        ax.set_title(f"{freq} Hz", fontsize=10, fontweight="bold")
        ax.set_xlabel("ms", fontsize=7)
        ax.set_ylabel("V", fontsize=7)
        ax.set_ylim(y_min, y_max)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {outpath}")


def plot_pwm_recovery(segments, outpath):
    """Plot 3: PWM recovery detail at 1 kHz (segment 6)."""
    if len(segments) <= 6 or len(segments[6]) == 0:
        print("  WARNING: No data for 1kHz segment")
        return

    data = segments[6]
    t = data[:, COL_TIME]
    pwm = data[:, COL_PWM]
    mid1 = data[:, COL_MID1]
    audio_out = data[:, COL_AUDIO]

    # 2ms window in settled region (last 2ms of segment)
    t_max = t[-1]
    mask = (t >= (t_max - 2e-3)) & (t <= t_max)
    if not np.any(mask):
        mask = (t >= (t_max - 4e-3)) & (t <= (t_max - 2e-3))

    if not np.any(mask):
        print("  WARNING: No data in 1kHz window for PWM recovery plot")
        return

    t_us = (t[mask] - t[mask][0]) * 1e6

    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("SID PWM Recovery Detail \u2014 1 kHz Signal\n"
                 "94.1 kHz PWM \u2192 3rd-order RC LPF (3\u00d73.3k\u03a9 + 3\u00d74.7nF)",
                 fontsize=13)

    ax = axes[0]
    ax.plot(t_us, pwm[mask], color="#2196F3", linewidth=0.3)
    ax.set_ylabel("Voltage (V)")
    ax.set_title("PWM Output (94.1 kHz carrier)", fontsize=10)
    ax.set_ylim(-0.3, 3.6)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(t_us, mid1[mask], color="#FF9800", linewidth=0.5)
    ax.set_ylabel("Voltage (V)")
    ax.set_title("After 1st RC Stage (mid1)", fontsize=10)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    ax.plot(t_us, audio_out[mask], color="#E91E63", linewidth=0.8)
    ax.set_ylabel("Voltage (V)")
    ax.set_xlabel("Time (\u00b5s)")
    ax.set_title("Audio Output (after 3rd RC + AC coupling)", fontsize=10)
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {outpath}")


def plot_summary(segments, freqs, gains, outpath):
    """Plot 4: Combined 2x2 summary."""
    ref_gain = gains[REF_IDX] if gains[REF_IDX] > 0 else 1e-6
    gain_db = 20 * np.log10(np.maximum(gains, 1e-9) / ref_gain)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("SID Full System Frequency Sweep \u2014 Summary", fontsize=14, y=0.98)

    # (0,0) Frequency response
    ax = axes[0][0]
    ax.semilogx(freqs, gain_db, "o-", color="#1976D2", linewidth=2, markersize=6)
    ax.axhline(-3, color="#E53935", linestyle="--", linewidth=1, alpha=0.7)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Gain (dB)")
    ax.set_title("Frequency Response")
    ax.grid(True, which="both", alpha=0.3)
    ax.set_xlim(200, 20000)
    ax.set_ylim(-20, 6)

    # (0,1) 1kHz chain detail (vin, SVF LP, audio_out)
    ax = axes[0][1]
    if len(segments) > 6 and len(segments[6]) > 0:
        data = segments[6]
        t = data[:, COL_TIME]
        t_max = t[-1]
        mask = (t >= (t_max - 5e-3)) & (t <= t_max)
        if np.any(mask):
            t_ms = (t[mask] - t[mask][0]) * 1e3
            ax.plot(t_ms, data[mask, COL_VIN],
                    label="SVF Input", linewidth=0.8, alpha=0.7)
            ax.plot(t_ms, data[mask, COL_LP],
                    label="SVF LP", linewidth=0.8, alpha=0.7)
            ao = data[mask, COL_AUDIO]
            ao_max = max(abs(ao.max()), abs(ao.min()), 1e-9)
            ao_scaled = ao / ao_max * 0.3 + 0.6
            ax.plot(t_ms, ao_scaled, label="Audio (scaled)",
                    linewidth=0.8, color="#E91E63")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("1 kHz Signal Chain Detail")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (1,0) 250 Hz waveform (last 10ms, settled)
    ax = axes[1][0]
    if len(segments) > 0 and len(segments[0]) > 0:
        data = segments[0]
        t = data[:, COL_TIME]
        t_max = t[-1]
        mask = t >= (t_max - 10e-3)
        if np.any(mask):
            t_ms = (t[mask] - t[mask][0]) * 1e3
            ax.plot(t_ms, data[mask, COL_AUDIO], color="#4CAF50", linewidth=0.6)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Audio Output \u2014 250 Hz")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.grid(True, alpha=0.3)

    # (1,1) 16000 Hz waveform (last 10ms, settled)
    ax = axes[1][1]
    if len(segments) > 15 and len(segments[15]) > 0:
        data = segments[15]
        t = data[:, COL_TIME]
        t_max = t[-1]
        mask = t >= (t_max - 10e-3)
        if np.any(mask):
            t_ms = (t[mask] - t[mask][0]) * 1e3
            ax.plot(t_ms, data[mask, COL_AUDIO], color="#9C27B0", linewidth=0.6)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Audio Output \u2014 16 kHz")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {outpath}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load sweep gain data
    gain_path = os.path.join(script_dir, "sweep_gain.dat")
    if not os.path.exists(gain_path):
        print(f"ERROR: {gain_path} not found \u2014 run ngspice simulation first")
        sys.exit(1)

    freqs, gains = load_gain_data(gain_path)
    print(f"Loaded {len(freqs)} gain measurements")

    # Load segmented transient data
    print("Loading transient data...")
    segments = load_segments(script_dir)
    print(f"Loaded {len(segments)} segments")

    for i, seg in enumerate(segments):
        if len(seg) > 0:
            print(f"  Segment {i}: {len(seg)} points, t=[{seg[0,0]*1e3:.2f}, {seg[-1,0]*1e3:.2f}] ms")

    # Generate all plots
    print("\nGenerating plots...")
    plot_freq_response(freqs, gains,
                       os.path.join(script_dir, "freq_response.png"))
    plot_waveform_grid(segments,
                       os.path.join(script_dir, "waveform_waterfall.png"))
    plot_pwm_recovery(segments,
                      os.path.join(script_dir, "pwm_recovery.png"))
    plot_summary(segments, freqs, gains,
                 os.path.join(script_dir, "full_sweep_summary.png"))

    print("\nAll plots generated successfully.")


if __name__ == "__main__":
    main()
