"""
CACE postprocessing script: compute INL and DNL for dual-channel bias DAC.

Input:
    results['vout_fc'] — list of 16 FC channel output voltages (code 0..15)
    results['vout_q']  — list of 16 Q channel output voltages (code 0..15)

Output:
    {'inl_fc': [max_abs_inl], 'dnl_fc': [max_abs_dnl],
     'inl_q':  [max_abs_inl], 'dnl_q':  [max_abs_dnl]}   (in LSB units)
"""

from typing import Any


def _compute_inl_dnl(vout):
    """Compute max |INL| and max |DNL| from a list of output voltages."""
    n = len(vout)
    if n < 2:
        raise Exception(f'Expected 16 data points, got {n}')

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

    return max_abs_inl, max_abs_dnl


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vout_fc = [float(v) for v in results['vout_fc']]
    vout_q = [float(v) for v in results['vout_q']]

    inl_fc, dnl_fc = _compute_inl_dnl(vout_fc)
    inl_q, dnl_q = _compute_inl_dnl(vout_q)

    return {
        'inl_fc': [inl_fc],
        'dnl_fc': [dnl_fc],
        'inl_q': [inl_q],
        'dnl_q': [dnl_q],
    }
