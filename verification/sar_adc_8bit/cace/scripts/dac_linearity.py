"""
CACE postprocessing script: compute cap DAC INL and DNL.

Input:
    results['vtop'] — list of 256 DAC output voltages (code 0..255)

Output:
    {'inl': [max_abs_inl], 'dnl': [max_abs_dnl]}  (in LSB units)

Identical to the R2R DAC INL/DNL script.
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vtop = [float(v) for v in results['vtop']]
    n = len(vtop)

    if n < 2:
        raise Exception(f'Expected 256 data points, got {n}')

    v_min = vtop[0]
    v_max = vtop[-1]
    lsb = (v_max - v_min) / (n - 1)

    if abs(lsb) < 1e-15:
        raise Exception(f'LSB is effectively zero: V(0)={v_min}, V({n-1})={v_max}')

    # INL — endpoint corrected
    max_abs_inl = 0.0
    for k in range(n):
        ideal = v_min + k * lsb
        inl_k = (vtop[k] - ideal) / lsb
        if abs(inl_k) > max_abs_inl:
            max_abs_inl = abs(inl_k)

    # DNL
    max_abs_dnl = 0.0
    for k in range(1, n):
        step = vtop[k] - vtop[k - 1]
        dnl_k = step / lsb - 1.0
        if abs(dnl_k) > max_abs_dnl:
            max_abs_dnl = abs(dnl_k)

    return {'inl': [max_abs_inl], 'dnl': [max_abs_dnl]}
