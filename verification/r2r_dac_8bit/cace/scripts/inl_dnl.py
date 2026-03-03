"""
CACE postprocessing script: compute INL and DNL from DC sweep results.

Input:
    results['vout'] — list of 256 output voltages (code 0 .. 255)

Output:
    {'inl': [max_abs_inl], 'dnl': [max_abs_dnl]}   (in LSB units)

INL: endpoint-corrected integral non-linearity
    INL(k) = (Vout(k) - Videal(k)) / LSB
    where Videal(k) = Vout(0) + k * (Vout(255) - Vout(0)) / 255

DNL: differential non-linearity
    DNL(k) = (Vout(k) - Vout(k-1)) / LSB - 1
    where LSB = (Vout(255) - Vout(0)) / 255
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vout = [float(v) for v in results['vout']]
    n = len(vout)

    if n < 2:
        raise Exception(f'Expected 256 data points, got {n}')

    v_min = vout[0]
    v_max = vout[-1]
    lsb = (v_max - v_min) / (n - 1)

    if abs(lsb) < 1e-15:
        raise Exception(f'LSB is effectively zero: Vout(0)={v_min}, Vout({n-1})={v_max}')

    # INL — endpoint corrected
    max_abs_inl = 0.0
    for k in range(n):
        ideal = v_min + k * lsb
        inl_k = (vout[k] - ideal) / lsb
        if abs(inl_k) > max_abs_inl:
            max_abs_inl = abs(inl_k)

    # DNL
    max_abs_dnl = 0.0
    for k in range(1, n):
        step = vout[k] - vout[k - 1]
        dnl_k = step / lsb - 1.0
        if abs(dnl_k) > max_abs_dnl:
            max_abs_dnl = abs(dnl_k)

    return {'inl': [max_abs_inl], 'dnl': [max_abs_dnl]}
