#!/usr/bin/env python3
"""Generate comparison plots across Q values for SVF and full chain triangle sims.

Reads Q-tagged .dat files: *_q{Q}.dat
Produces:
  svf/sc_svf_tri_q_sweep.png         — SVF 3×3 matrix overlay for all Q values
  full_chain/tri_chain_q_sweep.png   — Full chain 3×3 overlay
  full_chain/tri_chain_q_detail.png  — 440Hz detail across Q values
"""

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({
    'font.size': 10,
    'axes.titlesize': 11,
    'axes.labelsize': 10,
    'figure.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
})

Q_VALUES = [0.5, 1.5, 3.0, 6.0]
Q_COLORS = {0.5: '#2166ac', 1.5: '#4daf4a', 3.0: '#ff7f00', 6.0: '#d6604d'}
Q_LABELS = {q: f'Q={q}' for q in Q_VALUES}

FREQS = [220, 440, 880]
FCS = [50, 440, 1200]
FC_LABELS = ['fc=50 Hz', 'fc=440 Hz', 'fc=1200 Hz']


def load_wrdata(path, ncols=None):
    data = np.loadtxt(path)
    if ncols is None:
        ncols = data.shape[1] // 2
    result = {'time': data[:, 0]}
    for i in range(ncols):
        result[f'v{i+1}'] = data[:, 2*i + 1]
    return result


def check_files_exist():
    """Check which Q-tagged files exist."""
    available = []
    for q in Q_VALUES:
        path = f'svf/sc_svf_tri_440_fc440_q{q}.dat'
        try:
            np.loadtxt(path)
            available.append(q)
        except (FileNotFoundError, OSError):
            print(f'  Warning: Q={q} data not found, skipping')
    return available


# =====================================================================
# 1. SVF 3×3 Q-sweep overlay
# =====================================================================
print('Generating SVF 3×3 Q-sweep comparison...')

available_q = check_files_exist()
if not available_q:
    print('  ERROR: No Q-tagged data files found. Run sims first.')
    sys.exit(1)

fig1, axes1 = plt.subplots(3, 3, figsize=(15, 10), sharex=True, sharey=True)

for row, freq in enumerate(FREQS):
    for col, fc in enumerate(FCS):
        ax = axes1[row, col]

        # Plot input triangle (from first available Q — they're all the same input)
        q0 = available_q[0]
        d0 = load_wrdata(f'svf/sc_svf_tri_{freq}_fc{fc}_q{q0}.dat', 2)
        t_ms = d0['time'] * 1e3
        ax.plot(t_ms, d0['v1'], color='#cccccc', linewidth=0.5, label='Input')

        # Overlay each Q value
        pp_text = []
        for q in available_q:
            d = load_wrdata(f'svf/sc_svf_tri_{freq}_fc{fc}_q{q}.dat', 2)
            ax.plot(t_ms, d['v2'], color=Q_COLORS[q], linewidth=1.0,
                    alpha=0.85, label=Q_LABELS[q])
            mask = d['time'] >= 0.015
            if np.any(mask):
                pp = np.max(d['v2'][mask]) - np.min(d['v2'][mask])
                pp_text.append(f'Q={q}: {pp:.3f}V')

        if row == 0:
            ax.set_title(FC_LABELS[col], fontsize=11)
        if col == 0:
            ax.set_ylabel(f'{freq} Hz\nVoltage (V)')
        if row == 2:
            ax.set_xlabel('Time (ms)')

        # pk-pk annotation
        ax.text(0.97, 0.03, '\n'.join(pp_text), transform=ax.transAxes,
                fontsize=6.5, ha='right', va='bottom', family='monospace',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85))

        if row == 0 and col == 2:
            ax.legend(fontsize=7, loc='upper right')

axes1[0, 0].set_xlim(0, 25)
axes1[0, 0].set_ylim(-0.2, 1.6)

fig1.suptitle('SC SVF Bandpass — Q Sweep Comparison (0.5, 1.5, 3.0, 6.0)',
              fontsize=13, fontweight='bold')
fig1.tight_layout()
fig1.savefig('svf/sc_svf_tri_q_sweep.png', dpi=150)
print('  Wrote svf/sc_svf_tri_q_sweep.png')


# =====================================================================
# 2. Full Chain 3×3 Q-sweep overlay
# =====================================================================
print('Generating full chain 3×3 Q-sweep comparison...')

fig2, axes2 = plt.subplots(3, 3, figsize=(15, 10), sharex=True, sharey=True)

for row, freq in enumerate(FREQS):
    for col, fc in enumerate(FCS):
        ax = axes2[row, col]

        q0 = available_q[0]
        d0 = load_wrdata(f'full_chain/tri_chain_{freq}_fc{fc}_q{q0}.dat', 3)
        t_ms = d0['time'] * 1e3
        ax.plot(t_ms, d0['v1'], color='#cccccc', linewidth=0.5, label='DAC')

        pp_text = []
        for q in available_q:
            d = load_wrdata(f'full_chain/tri_chain_{freq}_fc{fc}_q{q}.dat', 3)
            ax.plot(t_ms, d['v3'], color=Q_COLORS[q], linewidth=1.0,
                    alpha=0.85, label=f'ADC Q={q}')
            mask = d['time'] >= 0.015
            if np.any(mask):
                pp = np.max(d['v3'][mask]) - np.min(d['v3'][mask])
                pp_text.append(f'Q={q}: {pp:.3f}V')

        if row == 0:
            ax.set_title(FC_LABELS[col], fontsize=11)
        if col == 0:
            ax.set_ylabel(f'{freq} Hz\nVoltage (V)')
        if row == 2:
            ax.set_xlabel('Time (ms)')

        ax.text(0.97, 0.03, '\n'.join(pp_text), transform=ax.transAxes,
                fontsize=6.5, ha='right', va='bottom', family='monospace',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.85))

        if row == 0 and col == 2:
            ax.legend(fontsize=7, loc='upper right')

axes2[0, 0].set_xlim(0, 25)
axes2[0, 0].set_ylim(-0.1, 1.3)

fig2.suptitle('Full Chain ADC Output — Q Sweep Comparison (0.5, 1.5, 3.0, 6.0)',
              fontsize=13, fontweight='bold')
fig2.tight_layout()
fig2.savefig('full_chain/tri_chain_q_sweep.png', dpi=150)
print('  Wrote full_chain/tri_chain_q_sweep.png')


# =====================================================================
# 3. Detail: 440 Hz triangle through fc=440 Hz BP at each Q
# =====================================================================
print('Generating 440 Hz / fc=440 Hz Q-sweep detail...')

fig3, axes3 = plt.subplots(len(available_q), 1, figsize=(10, 2.5 * len(available_q) + 1),
                            sharex=True)
if len(available_q) == 1:
    axes3 = [axes3]

for ax, q in zip(axes3, available_q):
    d_svf = load_wrdata(f'svf/sc_svf_tri_440_fc440_q{q}.dat', 2)
    d_fc = load_wrdata(f'full_chain/tri_chain_440_fc440_q{q}.dat', 3)
    t_ms = d_svf['time'] * 1e3

    ax.plot(t_ms, d_svf['v1'], color='#999999', linewidth=0.6, alpha=0.4, label='Input')
    ax.plot(t_ms, d_svf['v2'], color=Q_COLORS[q], linewidth=1.5, label=f'SVF BP (Q={q})')
    ax.plot(t_ms, d_fc['v3'], color='black', linewidth=0.8, linestyle='--',
            alpha=0.6, label='ADC (clipped to 0-1.2V)')

    mask = d_svf['time'] >= 0.015
    if np.any(mask):
        svf_pp = np.max(d_svf['v2'][mask]) - np.min(d_svf['v2'][mask])
        adc_pp = np.max(d_fc['v3'][mask]) - np.min(d_fc['v3'][mask])
        clipped = ' [CLIPPED]' if svf_pp > 1.2 else ''
        ax.text(0.02, 0.95, f'Q={q}  SVF pk-pk={svf_pp:.3f}V  ADC pk-pk={adc_pp:.3f}V{clipped}',
                transform=ax.transAxes, fontsize=9, va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.9))

    ax.set_ylabel('Voltage (V)')
    ax.set_ylim(-0.5, 2.5)
    ax.axhline(0, color='gray', linewidth=0.3)
    ax.axhline(1.2, color='red', linewidth=0.5, linestyle=':', alpha=0.5)
    ax.legend(fontsize=8, loc='upper right')

axes3[-1].set_xlabel('Time (ms)')
axes3[-1].set_xlim(10, 25)
fig3.suptitle('440 Hz Triangle → fc=440 Hz Bandpass — Q Sweep Detail',
              fontsize=13, fontweight='bold')
fig3.tight_layout()
fig3.savefig('full_chain/tri_chain_q_detail.png', dpi=150)
print('  Wrote full_chain/tri_chain_q_detail.png')

# =====================================================================
# Summary table
# =====================================================================
print('\n=== SVF BP Peak (440 Hz / fc=440 Hz) across Q ===')
print(f'  {"Q":>5}  {"SVF pk-pk":>10}  {"ADC pk-pk":>10}  {"Clipped?":>8}')
for q in available_q:
    d_svf = load_wrdata(f'svf/sc_svf_tri_440_fc440_q{q}.dat', 2)
    d_fc = load_wrdata(f'full_chain/tri_chain_440_fc440_q{q}.dat', 3)
    mask = d_svf['time'] >= 0.015
    svf_pp = np.max(d_svf['v2'][mask]) - np.min(d_svf['v2'][mask])
    adc_pp = np.max(d_fc['v3'][mask]) - np.min(d_fc['v3'][mask])
    clip = 'YES' if svf_pp > 1.2 else 'no'
    print(f'  {q:>5.1f}  {svf_pp:>10.3f}V  {adc_pp:>10.3f}V  {clip:>8}')

print('\nAll Q-sweep plots generated.')
