#!/bin/bash
# Full System Frequency Sweep — orchestrates digital TB, analog sim, and plots
set -e

PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ_DIR"

echo "============================================"
echo "  SID Full System Frequency Sweep"
echo "============================================"

# 1. Compile & run Verilog digital sweep (bypass mode, 16 freq points)
echo ""
echo "--- Step 1: Digital frequency sweep (Icarus Verilog) ---"
iverilog -o tests/freq_sweep -g2005 \
    src/tt_um_sid.v src/output_lpf.v src/pwm_audio.v \
    macros/nl/r2r_dac_8bit.v macros/nl/svf_2nd.v macros/nl/sar_adc_8bit.v \
    tests/freq_sweep_tb.v
vvp tests/freq_sweep

echo ""
echo "PWL files generated:"
ls -la tests/sweep_*.pwl 2>/dev/null || echo "  (none found — check for errors above)"

# 2. Process PWL through analog filter → WAV
echo ""
echo "--- Step 2: PWL → analog filter → WAV (sim_analog.py) ---"
python3 tests/sim_analog.py

# 3. Run ngspice analog chain sweep
echo ""
echo "--- Step 3: Full analog chain sweep (ngspice) ---"
cd analog_sim/full_sweep
ngspice -b full_sweep_tb.spice -o full_sweep.log
echo "ngspice log: analog_sim/full_sweep/full_sweep.log"

# 4. Generate plots
echo ""
echo "--- Step 4: Generate plots ---"
python3 plot_sweep.py

cd "$PROJ_DIR"
echo ""
echo "============================================"
echo "  Sweep complete. Output files:"
echo "  PWL:  tests/sweep_*.pwl (16 files)"
echo "  WAV:  tests/sweep_*_analog.wav (16 files)"
echo "  Data: analog_sim/full_sweep/seg_*.dat (16 files)"
echo "  Gain: analog_sim/full_sweep/sweep_gain.dat"
echo "  Plots: analog_sim/full_sweep/*.png (4 files)"
echo "============================================"
