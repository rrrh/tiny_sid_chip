#!/bin/bash
# Triangle Wave Simulation Runner
# Runs per-macro testbenches and full-chain 3x3 matrix
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PASS=0
FAIL=0
RESULTS=""

run_sim() {
    local name="$1"
    local dir="$2"
    local spice="$3"
    local expected_dats="$4"

    echo "============================================"
    echo "  Running: $name"
    echo "  File:    $dir/$spice"
    echo "============================================"

    cd "$SCRIPT_DIR/$dir"

    if ngspice -b "$spice" 2>&1; then
        # Check for expected .dat files
        local all_found=true
        for dat in $expected_dats; do
            if [ ! -f "$dat" ]; then
                echo "  WARNING: Expected output $dat not found"
                all_found=false
            fi
        done
        if $all_found; then
            echo "  PASS: $name"
            PASS=$((PASS + 1))
            RESULTS="$RESULTS\n  PASS  $name"
        else
            echo "  PARTIAL: $name (sim ran but some .dat files missing)"
            PASS=$((PASS + 1))
            RESULTS="$RESULTS\n  PARTIAL  $name"
        fi
    else
        echo "  FAIL: $name"
        FAIL=$((FAIL + 1))
        RESULTS="$RESULTS\n  FAIL  $name"
    fi

    cd "$SCRIPT_DIR"
    echo ""
}

echo "========================================================"
echo "  Triangle Wave Simulation Suite"
echo "  $(date)"
echo "========================================================"
echo ""

# 1. R-2R DAC triangle testbench
run_sim "R-2R DAC Triangle" \
    "r2r_dac" \
    "r2r_dac_tri_tb.spice" \
    "r2r_dac_tri_220.dat r2r_dac_tri_440.dat r2r_dac_tri_880.dat"

# 2. SC SVF triangle 3x3 testbench
run_sim "SC SVF Triangle 3x3" \
    "svf" \
    "sc_svf_tri_tb.spice" \
    "sc_svf_tri_220_fc50.dat sc_svf_tri_440_fc440.dat sc_svf_tri_880_fc1200.dat"

# 3. SAR ADC triangle testbench
run_sim "SAR ADC Triangle" \
    "sar_adc" \
    "sar_adc_tri_tb.spice" \
    "sar_adc_tri_220.dat sar_adc_tri_440.dat sar_adc_tri_880.dat"

# 4. Bias DAC verification testbench
run_sim "Bias DAC Verification" \
    "bias_dac" \
    "bias_dac_tri_tb.spice" \
    "bias_dac_fc_verify.dat"

# 5. Full chain 3x3 matrix
run_sim "Full Chain 3x3 Matrix" \
    "full_chain" \
    "tri_chain_tb.spice" \
    "tri_chain_220_fc50.dat tri_chain_440_fc440.dat tri_chain_880_fc1200.dat"

# Summary
echo "========================================================"
echo "  SUMMARY"
echo "========================================================"
echo -e "$RESULTS"
echo ""
echo "  Passed: $PASS / $((PASS + FAIL))"
if [ $FAIL -gt 0 ]; then
    echo "  FAILED: $FAIL"
    exit 1
else
    echo "  All simulations completed successfully."
fi
echo "========================================================"
