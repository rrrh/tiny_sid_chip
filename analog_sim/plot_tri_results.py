#!/usr/bin/env python3
"""Generate wave output plots for all triangle-wave testbenches.

Produces:
  r2r_dac/r2r_dac_tri_waves.png        — DAC triangle output at 220/440/880 Hz
  svf/sc_svf_tri_matrix.png             — SVF 3×3 frequency/cutoff matrix
  sar_adc/sar_adc_tri_waves.png         — ADC quantization fidelity
  bias_dac/bias_dac_fc_sweep.png        — Bias DAC FC channel transfer curve
  full_chain/tri_chain_matrix.png       — Full chain 3×3 matrix
  full_chain/tri_chain_detail.png       — Full chain detail: 440Hz at each fc
"""

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

# Color palette
C_DAC  = '#2166ac'
C_SVF  = '#d6604d'
C_ADC  = '#4daf4a'
C_IN   = '#333333'
C_220  = '#e66101'
C_440  = '#2166ac'
C_880  = '#5e3c99'


def load_wrdata(path, ncols=None):
    """Load ngspice wrdata file. Returns dict with 'time' and 'v1','v2',..."""
    data = np.loadtxt(path)
    if ncols is None:
        ncols = data.shape[1] // 2
    result = {'time': data[:, 0]}
    for i in range(ncols):
        result[f'v{i+1}'] = data[:, 2*i + 1]
    return result


# =====================================================================
# 1. R-2R DAC Triangle Waves
# =====================================================================
print('Generating R-2R DAC triangle plots...')

fig1, axes1 = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

for ax, freq, color in zip(axes1, [220, 440, 880], [C_220, C_440, C_880]):
    d = load_wrdata(f'r2r_dac/r2r_dac_tri_{freq}.dat', 2)
    t_ms = d['time'] * 1e3
    code = d['v1']
    vout = d['v2']

    ax.plot(t_ms, vout, color=color, linewidth=1, label=f'DAC output')
    ax.set_ylabel('Voltage (V)')
    ax.set_title(f'{freq} Hz Triangle')
    ax.set_ylim(-0.05, 1.25)
    ax.legend(loc='upper right', fontsize=9)

    # Add code axis on right
    ax2 = ax.twinx()
    ax2.plot(t_ms, code, color='gray', linewidth=0.5, alpha=0.4, label='Code')
    ax2.set_ylabel('Code', color='gray')
    ax2.set_ylim(-10, 260)
    ax2.tick_params(axis='y', labelcolor='gray')

axes1[-1].set_xlabel('Time (ms)')
axes1[-1].set_xlim(0, 25)
fig1.suptitle('R-2R DAC Triangle Wave Output — IHP SG13G2', fontsize=13, fontweight='bold')
fig1.tight_layout()
fig1.savefig('r2r_dac/r2r_dac_tri_waves.png', dpi=150)
print('  Wrote r2r_dac/r2r_dac_tri_waves.png')


# =====================================================================
# 2. SC SVF Triangle 3×3 Matrix
# =====================================================================
print('Generating SVF 3×3 triangle matrix...')

freqs = [220, 440, 880]
fcs = [50, 440, 1200]
fc_labels = ['fc=50 Hz', 'fc=440 Hz', 'fc=1200 Hz']
freq_colors = [C_220, C_440, C_880]

fig2, axes2 = plt.subplots(3, 3, figsize=(14, 9), sharex=True, sharey=True)

for row, freq in enumerate(freqs):
    for col, fc in enumerate(fcs):
        ax = axes2[row, col]
        d = load_wrdata(f'svf/sc_svf_tri_{freq}_fc{fc}.dat', 2)
        t_ms = d['time'] * 1e3

        ax.plot(t_ms, d['v1'], color=C_IN, linewidth=0.7, alpha=0.4, label='Input')
        ax.plot(t_ms, d['v2'], color=freq_colors[row], linewidth=1.2, label='BP out')

        if row == 0:
            ax.set_title(fc_labels[col], fontsize=11)
        if col == 0:
            ax.set_ylabel(f'{freq} Hz\nVoltage (V)')
        if row == 2:
            ax.set_xlabel('Time (ms)')

        # Show steady-state pk-pk
        mask = d['time'] >= 0.015
        if np.any(mask):
            vout = d['v2'][mask]
            pp = np.max(vout) - np.min(vout)
            ax.text(0.97, 0.03, f'pk-pk={pp:.3f}V', transform=ax.transAxes,
                    fontsize=8, ha='right', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

        ax.legend(fontsize=7, loc='upper right')

axes2[0, 0].set_xlim(0, 25)
axes2[0, 0].set_ylim(0, 1.1)

fig2.suptitle('SC SVF Bandpass (Q=0.5) — Triangle Wave 3×3 Matrix', fontsize=13, fontweight='bold')
fig2.tight_layout()
fig2.savefig('svf/sc_svf_tri_matrix.png', dpi=150)
print('  Wrote svf/sc_svf_tri_matrix.png')


# =====================================================================
# 3. SAR ADC Triangle Waves
# =====================================================================
print('Generating SAR ADC triangle plots...')

fig3, axes3 = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

for ax, freq, color in zip(axes3, [220, 440, 880], [C_220, C_440, C_880]):
    d = load_wrdata(f'sar_adc/sar_adc_tri_{freq}.dat', 3)
    t_ms = d['time'] * 1e3
    v_in = d['v1']
    code = d['v2']
    v_rec = d['v3']

    ax.plot(t_ms, v_in, color=C_IN, linewidth=1, alpha=0.5, label='Analog input')
    ax.plot(t_ms, v_rec, color=color, linewidth=1.2, label='ADC reconstructed')
    ax.set_ylabel('Voltage (V)')
    ax.set_title(f'{freq} Hz Triangle — Quantization Fidelity')
    ax.set_ylim(0, 1.15)
    ax.legend(loc='upper right', fontsize=9)

    # Quantization error inset
    mask = d['time'] >= 0.015
    if np.any(mask):
        err = v_in[mask] - v_rec[mask]
        ax.text(0.97, 0.03, f'max |err|={np.max(np.abs(err))*1e3:.1f} mV',
                transform=ax.transAxes, fontsize=8, ha='right', va='bottom',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

axes3[-1].set_xlabel('Time (ms)')
axes3[-1].set_xlim(0, 25)
fig3.suptitle('SAR ADC Triangle Wave Quantization — Behavioral 8-bit', fontsize=13, fontweight='bold')
fig3.tight_layout()
fig3.savefig('sar_adc/sar_adc_tri_waves.png', dpi=150)
print('  Wrote sar_adc/sar_adc_tri_waves.png')


# =====================================================================
# 4. Bias DAC FC Channel Sweep
# =====================================================================
print('Generating Bias DAC FC sweep plot...')

# The file has mixed format: first 3 lines are spotlight codes (vfc, vq),
# then 16 lines of full sweep (code, vfc)
raw = []
with open('bias_dac/bias_dac_fc_verify.dat') as f:
    for line in f:
        parts = line.strip().split()
        if len(parts) >= 2:
            raw.append([float(x) for x in parts])

# The last 16 entries are the full sweep (code 0-15)
sweep = np.array(raw[-16:])
codes = sweep[:, 0]
vfc = sweep[:, 1]

# Spotlight codes from first 3 entries
spot_codes = [1, 6, 12]
spot_vfc = [raw[0][0], raw[1][0], raw[2][0]]

fig4, ax4 = plt.subplots(figsize=(8, 5))
ax4.plot(codes, vfc, 'o-', color=C_DAC, linewidth=2, markersize=6, label='Vout_fc')
ax4.plot(codes, codes / 15 * 1.2, '--', color='gray', linewidth=1, alpha=0.6, label='Ideal (linear)')

# Highlight target fc codes
for code, v, fc_hz in zip(spot_codes, spot_vfc, [50, 440, 1200]):
    ax4.annotate(f'fc≈{fc_hz} Hz\n(code {code})',
                 xy=(code, v), xytext=(code + 1.2, v + 0.06),
                 fontsize=9, ha='left',
                 arrowprops=dict(arrowstyle='->', color='#d6604d'),
                 color='#d6604d', fontweight='bold')
    ax4.plot(code, v, 'o', color='#d6604d', markersize=10, zorder=5)

ax4.set_xlabel('FC Code (4-bit)')
ax4.set_ylabel('Output Voltage (V)')
ax4.set_title('Bias DAC — FC Channel Transfer Function')
ax4.set_xlim(-0.5, 15.5)
ax4.set_ylim(-0.05, 1.25)
ax4.set_xticks(range(16))
ax4.legend(loc='upper left')
fig4.tight_layout()
fig4.savefig('bias_dac/bias_dac_fc_sweep.png', dpi=150)
print('  Wrote bias_dac/bias_dac_fc_sweep.png')


# =====================================================================
# 5. Full Chain 3×3 Matrix
# =====================================================================
print('Generating full chain 3×3 matrix...')

fig5, axes5 = plt.subplots(3, 3, figsize=(14, 9), sharex=True, sharey=True)

for row, freq in enumerate(freqs):
    for col, fc in enumerate(fcs):
        ax = axes5[row, col]
        d = load_wrdata(f'full_chain/tri_chain_{freq}_fc{fc}.dat', 3)
        t_ms = d['time'] * 1e3

        ax.plot(t_ms, d['v1'], color=C_IN, linewidth=0.6, alpha=0.35, label='DAC')
        ax.plot(t_ms, d['v2'], color=C_SVF, linewidth=1.2, label='SVF BP')
        ax.plot(t_ms, d['v3'], color=C_ADC, linewidth=0.8, alpha=0.7, label='ADC')

        if row == 0:
            ax.set_title(fc_labels[col], fontsize=11)
        if col == 0:
            ax.set_ylabel(f'{freq} Hz\nVoltage (V)')
        if row == 2:
            ax.set_xlabel('Time (ms)')

        # Show SVF pk-pk
        mask = d['time'] >= 0.015
        if np.any(mask):
            svf_pp = np.max(d['v2'][mask]) - np.min(d['v2'][mask])
            adc_pp = np.max(d['v3'][mask]) - np.min(d['v3'][mask])
            ax.text(0.97, 0.03, f'SVF={svf_pp:.3f}V\nADC={adc_pp:.3f}V',
                    transform=ax.transAxes, fontsize=7, ha='right', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

        if row == 0 and col == 2:
            ax.legend(fontsize=7, loc='upper right')

axes5[0, 0].set_xlim(0, 25)
axes5[0, 0].set_ylim(0, 1.2)

fig5.suptitle('Full Chain: DAC → SVF (BP, Q=0.5) → ADC — Triangle Wave 3×3', fontsize=13, fontweight='bold')
fig5.tight_layout()
fig5.savefig('full_chain/tri_chain_matrix.png', dpi=150)
print('  Wrote full_chain/tri_chain_matrix.png')


# =====================================================================
# 6. Full Chain Detail: 440 Hz triangle through all 3 cutoffs
# =====================================================================
print('Generating full chain detail plot...')

fig6, axes6 = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

for ax, fc, fc_label in zip(axes6, fcs, fc_labels):
    d = load_wrdata(f'full_chain/tri_chain_440_fc{fc}.dat', 3)
    t_ms = d['time'] * 1e3

    ax.plot(t_ms, d['v1'], color=C_IN, linewidth=0.8, alpha=0.4, label='DAC input')
    ax.plot(t_ms, d['v2'], color=C_SVF, linewidth=1.5, label='SVF BP out')
    ax.plot(t_ms, d['v3'], color=C_ADC, linewidth=1, linestyle='--', alpha=0.7, label='ADC recon')
    ax.set_ylabel('Voltage (V)')
    ax.set_title(f'440 Hz Triangle → {fc_label} Bandpass')
    ax.set_ylim(0, 1.2)
    ax.legend(loc='upper right', fontsize=9)

    # Annotations
    mask = d['time'] >= 0.015
    if np.any(mask):
        svf_pp = np.max(d['v2'][mask]) - np.min(d['v2'][mask])
        ax.text(0.02, 0.95, f'SVF pk-pk = {svf_pp:.3f} V',
                transform=ax.transAxes, fontsize=9, va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.9))

axes6[-1].set_xlabel('Time (ms)')
axes6[-1].set_xlim(10, 25)
fig6.suptitle('Full Chain Detail: 440 Hz Triangle at Three Cutoff Frequencies',
              fontsize=13, fontweight='bold')
fig6.tight_layout()
fig6.savefig('full_chain/tri_chain_detail.png', dpi=150)
print('  Wrote full_chain/tri_chain_detail.png')

print('\nAll triangle wave plots generated.')
