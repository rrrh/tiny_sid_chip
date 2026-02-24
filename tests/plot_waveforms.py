#!/usr/bin/env python3
"""Generate waveform and filter plots from simulation .raw files."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SAMPLE_RATE = 44117
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_raw(name):
    """Load a .raw file from the tests/ directory."""
    path = os.path.join(SCRIPT_DIR, name)
    with open(path) as f:
        return [int(line.strip()) for line in f if line.strip()]


def time_axis(samples):
    """Return time axis in milliseconds."""
    return [i * 1000.0 / SAMPLE_RATE for i in range(len(samples))]


def plot_waveform_type(waveform_name, display_name):
    """Plot 220/440/880 Hz overlaid for one waveform type."""
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=False)
    fig.suptitle(f'{display_name} Waveform', fontsize=14)

    for ax, freq in zip(axes, [220, 440, 880]):
        fname = f'{waveform_name}_{freq}.raw'
        data = load_raw(fname)
        # Show ~4 cycles: 4/freq seconds
        show_ms = 4000.0 / freq
        show_n = min(int(show_ms * SAMPLE_RATE / 1000), len(data))
        t = time_axis(data[:show_n])
        ax.plot(t, data[:show_n], linewidth=0.8)
        ax.set_title(f'{freq} Hz')
        ax.set_ylabel('Amplitude')
        ax.set_ylim(-5, 260)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel('Time (ms)')
    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, f'waveform_{waveform_name}.png')
    plt.savefig(out, dpi=150)
    plt.close()
    print(f'  {out}')


def plot_filters():
    """Plot LP/HP/BP filter outputs on 440 Hz sawtooth."""
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    fig.suptitle('Filter Comparison (440 Hz Sawtooth Input)', fontsize=14)

    labels = [('filter_lp.raw', 'Low-Pass'), ('filter_bp.raw', 'Band-Pass'), ('filter_hp.raw', 'High-Pass')]
    for ax, (fname, label) in zip(axes, labels):
        data = load_raw(fname)
        # Show ~4 cycles at 440 Hz
        show_n = min(int(4000.0 / 440 * SAMPLE_RATE / 1000), len(data))
        t = time_axis(data[:show_n])
        ax.plot(t, data[:show_n], linewidth=0.8)
        ax.set_title(label)
        ax.set_ylabel('Amplitude')
        ax.set_ylim(-5, 260)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel('Time (ms)')
    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, 'filter_comparison.png')
    plt.savefig(out, dpi=150)
    plt.close()
    print(f'  {out}')


if __name__ == '__main__':
    print('Generating waveform plots...')
    plot_waveform_type('saw', 'Sawtooth')
    plot_waveform_type('tri', 'Triangle')
    plot_waveform_type('pulse', 'Pulse')

    print('Generating filter plot...')
    plot_filters()

    print('Done.')
