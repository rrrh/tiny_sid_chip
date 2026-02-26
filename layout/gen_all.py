#!/usr/bin/env python3
"""Generate all four analog hard macro GDS files."""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("Generating R-2R DAC...")
print("=" * 60)
from gen_r2r_dac import build_r2r_dac
layout, top = build_r2r_dac()
outdir = os.path.join(os.path.dirname(__file__), "..", "macros", "gds")
os.makedirs(outdir, exist_ok=True)
layout.write(os.path.join(outdir, "r2r_dac_8bit.gds"))
print(f"  → macros/gds/r2r_dac_8bit.gds")

print()
print("=" * 60)
print("Generating dual-channel bias DAC...")
print("=" * 60)
from gen_bias_dac import build_bias_dac
layout, top = build_bias_dac()
layout.write(os.path.join(outdir, "bias_dac_2ch.gds"))
print(f"  → macros/gds/bias_dac_2ch.gds")

print()
print("=" * 60)
print("Generating gm-C SVF...")
print("=" * 60)
from gen_svf import build_svf
layout, top = build_svf()
layout.write(os.path.join(outdir, "svf_2nd.gds"))
print(f"  → macros/gds/svf_2nd.gds")

print()
print("=" * 60)
print("Generating SAR ADC...")
print("=" * 60)
from gen_sar_adc import build_sar_adc
layout, top = build_sar_adc()
layout.write(os.path.join(outdir, "sar_adc_8bit.gds"))
print(f"  → macros/gds/sar_adc_8bit.gds")

print()
print("=" * 60)
print("All macros generated successfully.")
print("=" * 60)
