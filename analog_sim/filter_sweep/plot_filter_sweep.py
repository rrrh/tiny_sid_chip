#!/usr/bin/env python3
"""Plot SVF filter characterization: LP, BP, HP from ngspice wrdata segments.

Generates 3 PNG files (filter_lp.png, filter_bp.png, filter_hp.png),
each with a 2x2 grid of subplots (one per cutoff frequency), overlaying 4 Q curves.
Input sine fixed at 500 Hz; filter fc varies (250, 500, 1000, 1500 Hz).

wrdata interleaved format for 3 signals: v(vin), v(lp), v(bp)
  col 0: time
  col 1: v(vin)
  col 2: time (dup)
  col 3: v(lp)
  col 4: time (dup)
  col 5: v(bp)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Segment layout: Q outer, fc inner
Q_VALUES = [0.5, 1.0, 2.0, 5.0]
FC_VALUES = [250, 500, 1000, 1500]  # filter cutoff frequencies
F_IN = 500  # fixed input sine frequency
VCM = 0.6
T_SETTLE = 50e-3   # discard first 50ms
T_TOTAL = 60e-3     # total sim time per segment

COL_TIME = 0
COL_VIN = 1
COL_LP = 3
COL_BP = 5

Q_COLORS = {0.5: "C0", 1.0: "C1", 2.0: "C2", 5.0: "C3"}


def load_segment(seg_idx):
    """Load one segment file, return measurement window only."""
    fname = f"seg_{seg_idx:02d}.dat"
    data = np.loadtxt(fname)
    # Keep only measurement window (last 10ms)
    mask = data[:, COL_TIME] >= T_SETTLE
    return data[mask]


def make_plot(mode, extract_fn, filename, title_prefix):
    """Create a 2x2 figure for one filter mode."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    fig.suptitle(f"{title_prefix} Response — SVF Filter (fin={F_IN} Hz)", fontsize=14)

    # Collect global y limits across all subplots
    all_ymin, all_ymax = [], []

    for fi, fc in enumerate(FC_VALUES):
        ax = axes[fi // 2][fi % 2]
        ax.set_title(f"fc = {fc} Hz")
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Voltage (V)")
        ax.grid(True, alpha=0.3)

        for qi, q in enumerate(Q_VALUES):
            seg_idx = qi * len(FC_VALUES) + fi
            d = load_segment(seg_idx)
            t_ms = (d[:, COL_TIME] - T_SETTLE) * 1e3
            y = extract_fn(d, q)
            ax.plot(t_ms, y, color=Q_COLORS[q], label=f"Q={q}", linewidth=0.8)
            all_ymin.append(np.min(y))
            all_ymax.append(np.max(y))

        ax.legend(fontsize=8, loc="upper right")

    # Uniform y-axis across all subplots
    ylo = min(all_ymin) - 0.02
    yhi = max(all_ymax) + 0.02
    for row in axes:
        for ax in row:
            ax.set_ylim(ylo, yhi)

    fig.tight_layout()
    fig.savefig(filename, dpi=150)
    plt.close(fig)
    print(f"Saved {filename}")


def extract_lp(data, q):
    return data[:, COL_LP]


def extract_bp(data, q):
    return data[:, COL_BP]


def extract_hp(data, q):
    vin = data[:, COL_VIN]
    lp = data[:, COL_LP]
    bp = data[:, COL_BP]
    # HP = VCM + (Vin - VCM) - (LP - VCM) - (BP - VCM)/Q
    hp = VCM + (vin - VCM) - (lp - VCM) - (bp - VCM) / q
    return hp


if __name__ == "__main__":
    make_plot("lp", extract_lp, "filter_lp.png", "Low-Pass")
    make_plot("bp", extract_bp, "filter_bp.png", "Band-Pass")
    make_plot("hp", extract_hp, "filter_hp.png", "High-Pass")
    print("Done.")
