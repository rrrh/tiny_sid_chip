#!/usr/bin/env python3
"""Generate SC SVF simulation plots from ngspice output data."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

plt.rcParams.update({
    'font.size': 10,
    'axes.titlesize': 11,
    'axes.labelsize': 10,
    'figure.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
})

# ── Load AC data ──
bp = np.loadtxt('svf/sc_svf_bp_ac.dat')
lp = np.loadtxt('svf/sc_svf_lp_ac.dat')
hp = np.loadtxt('svf/sc_svf_hp_ac.dat')

# ── Load transient data (wrdata format: col0=time, col1=vin, col2=time, col3=bp, ...) ──
tran = np.loadtxt('svf/sc_svf_tran.dat')
t_ms    = tran[:, 0] * 1e3
v_in    = tran[:, 1]
v_bp    = tran[:, 3]
v_lp    = tran[:, 5]
v_hp    = tran[:, 7]

# ── Load full chain data ──
fc = np.loadtxt('full_chain/full_chain_out.dat')
fc_t_ms  = fc[:, 0] * 1e3
fc_dac   = fc[:, 1]
fc_svf   = fc[:, 3]
fc_adc   = fc[:, 5]

# =====================================================================
# Figure 1: AC Frequency Responses (BP, LP, HP overlaid)
# =====================================================================
fig1, ax1 = plt.subplots(figsize=(8, 5))
ax1.semilogx(bp[:, 0], bp[:, 1], 'b-', linewidth=2, label='BP (sel=01)')
ax1.semilogx(lp[:, 0], lp[:, 1], 'r-', linewidth=2, label='LP (sel=10)')
ax1.semilogx(hp[:, 0], hp[:, 1], 'g-', linewidth=2, label='HP (sel=00)')
ax1.axhline(-3, color='gray', linestyle='--', alpha=0.5, label='−3 dB')
ax1.axvline(1000, color='gray', linestyle=':', alpha=0.5, label='f₀ = 1 kHz')
ax1.set_xlabel('Frequency (Hz)')
ax1.set_ylabel('Gain (dB)')
ax1.set_title('SC SVF AC Response — Tow-Thomas Biquad (Q = 1, f₀ = 1 kHz)')
ax1.set_xlim(10, 100e3)
ax1.set_ylim(-45, 5)
ax1.legend(loc='lower left')
fig1.tight_layout()
fig1.savefig('svf/sc_svf_ac_response.png', dpi=150)
print('  Wrote svf/sc_svf_ac_response.png')

# =====================================================================
# Figure 2: Transient Response (BP mode, 1 kHz input)
# =====================================================================
fig2, (ax2a, ax2b) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

ax2a.plot(t_ms, v_in, 'k-', linewidth=1.5, label='Vin (1 kHz, 50 mV)')
ax2a.plot(t_ms, v_bp, 'b-', linewidth=1.5, label='BP')
ax2a.set_ylabel('Voltage (V)')
ax2a.set_title('SC SVF Transient — BP Mode (Q = 1, f₀ = 1 kHz)')
ax2a.legend(loc='upper right')
ax2a.set_ylim(0.45, 0.75)

ax2b.plot(t_ms, v_lp, 'r-', linewidth=1.5, label='LP')
ax2b.plot(t_ms, v_hp, 'g-', linewidth=1.5, alpha=0.8, label='HP')
ax2b.set_xlabel('Time (ms)')
ax2b.set_ylabel('Voltage (V)')
ax2b.set_title('LP and HP Outputs')
ax2b.legend(loc='upper right')
ax2b.set_ylim(0.45, 0.75)

fig2.tight_layout()
fig2.savefig('svf/sc_svf_transient.png', dpi=150)
print('  Wrote svf/sc_svf_transient.png')

# =====================================================================
# Figure 3: Full Chain (DAC → SC SVF → ADC)
# =====================================================================
fig3, (ax3a, ax3b, ax3c) = plt.subplots(3, 1, figsize=(8, 7), sharex=True)

ax3a.plot(fc_t_ms, fc_dac, 'k-', linewidth=1)
ax3a.set_ylabel('DAC Out (V)')
ax3a.set_title('Full Signal Chain: DAC → SC SVF (BP, Q=0.25) → ADC')
ax3a.set_ylim(0, 1.2)

ax3b.plot(fc_t_ms, fc_svf, 'b-', linewidth=1)
ax3b.set_ylabel('SVF BP Out (V)')
ax3b.axhline(0.6, color='gray', linestyle=':', alpha=0.5)
ax3b.set_ylim(0.3, 0.9)

ax3c.plot(fc_t_ms, fc_adc, 'r-', linewidth=1)
ax3c.set_ylabel('ADC Recon (V)')
ax3c.set_xlabel('Time (ms)')
ax3c.set_ylim(0.3, 0.9)

fig3.tight_layout()
fig3.savefig('full_chain/full_chain_plot.png', dpi=150)
print('  Wrote full_chain/full_chain_plot.png')

# =====================================================================
# Figure 4: Combined Summary (2×2 grid)
# =====================================================================
fig4 = plt.figure(figsize=(12, 9))
gs = GridSpec(2, 2, figure=fig4, hspace=0.35, wspace=0.3)

# Top-left: AC responses
ax4a = fig4.add_subplot(gs[0, 0])
ax4a.semilogx(bp[:, 0], bp[:, 1], 'b-', linewidth=2, label='BP')
ax4a.semilogx(lp[:, 0], lp[:, 1], 'r-', linewidth=2, label='LP')
ax4a.semilogx(hp[:, 0], hp[:, 1], 'g-', linewidth=2, label='HP')
ax4a.axhline(-3, color='gray', linestyle='--', alpha=0.5)
ax4a.axvline(1000, color='gray', linestyle=':', alpha=0.5)
ax4a.set_xlabel('Frequency (Hz)')
ax4a.set_ylabel('Gain (dB)')
ax4a.set_title('AC Response (Q=1, f₀=1kHz)')
ax4a.set_xlim(10, 100e3)
ax4a.set_ylim(-45, 5)
ax4a.legend(fontsize=9)

# Top-right: Transient BP
ax4b = fig4.add_subplot(gs[0, 1])
ax4b.plot(t_ms, v_in, 'k-', linewidth=1, alpha=0.7, label='Vin')
ax4b.plot(t_ms, v_bp, 'b-', linewidth=1.5, label='BP')
ax4b.set_xlabel('Time (ms)')
ax4b.set_ylabel('Voltage (V)')
ax4b.set_title('Transient BP (1 kHz sine, Q=1)')
ax4b.set_ylim(0.45, 0.75)
ax4b.legend(fontsize=9)

# Bottom-left: Full chain
ax4c = fig4.add_subplot(gs[1, 0])
ax4c.plot(fc_t_ms, fc_dac, 'k-', linewidth=0.8, alpha=0.5, label='DAC')
ax4c.plot(fc_t_ms, fc_svf, 'b-', linewidth=1.5, label='SVF BP')
ax4c.plot(fc_t_ms, fc_adc, 'r--', linewidth=1, alpha=0.7, label='ADC')
ax4c.set_xlabel('Time (ms)')
ax4c.set_ylabel('Voltage (V)')
ax4c.set_title('Full Chain: DAC→SVF(BP,Q=0.25)→ADC')
ax4c.legend(fontsize=9)

# Bottom-right: BP detail (last 3 cycles, steady state)
mask = t_ms >= 7.0
ax4d = fig4.add_subplot(gs[1, 1])
ax4d.plot(t_ms[mask], v_in[mask], 'k-', linewidth=1, alpha=0.7, label='Vin')
ax4d.plot(t_ms[mask], v_bp[mask], 'b-', linewidth=2, label='BP')
ax4d.plot(t_ms[mask], v_lp[mask], 'r-', linewidth=1.5, label='LP')
ax4d.set_xlabel('Time (ms)')
ax4d.set_ylabel('Voltage (V)')
ax4d.set_title('Steady-State Detail (7–10 ms)')
ax4d.legend(fontsize=9)
ax4d.set_ylim(0.45, 0.75)

fig4.suptitle('SC SVF Simulation Results — IHP SG13G2 130nm', fontsize=13, fontweight='bold')
fig4.savefig('sc_svf_summary.png', dpi=150)
print('  Wrote sc_svf_summary.png')

print('\nAll plots generated.')
