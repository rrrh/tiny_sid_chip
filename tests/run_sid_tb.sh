#!/bin/bash
# SID top-level testbench — compile & run all 15 tests
# Requires -DBEHAVIORAL_SIM so the SVF filter uses its behavioral model
# instead of the empty blackbox stub.
set -e

PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ_DIR"

echo "============================================"
echo "  SID Top-Level Testbench (tt_um_sid_tb)"
echo "============================================"

echo ""
echo "--- Compile (Icarus Verilog, -DBEHAVIORAL_SIM) ---"
iverilog -o tests/tt_um_sid_tb.vvp -g2005 -DBEHAVIORAL_SIM \
    src/tt_um_sid.v src/SVF_8bit.v src/filter.v src/filter_top.v \
    src/output_lpf.v src/pwm_audio.v \
    macros/nl/r2r_dac_8bit.v macros/nl/svf_2nd.v macros/nl/sar_adc_8bit.v \
    tests/tt_um_sid_tb.v

echo ""
echo "--- Run ---"
vvp tests/tt_um_sid_tb.vvp

echo ""
echo "============================================"
echo "  Done.  Waveform: tt_um_sid_tb.vcd"
echo "============================================"
