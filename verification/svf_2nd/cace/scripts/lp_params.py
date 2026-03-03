"""
CACE postprocessing script: extract low-pass filter parameters from AC data.

Input:
    results['vout_re']  — real part of V(vout)
    results['vout_im']  — imaginary part of V(vout)
    results['freq']     — frequency points (Hz)

Output:
    {'dc_gain': [gain_dB], 'f_3db': [freq_Hz]}
"""

import math
from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    freq = [float(f) for f in results['freq']]
    vout_re = [float(r) for r in results['vout_re']]
    vout_im = [float(i) for i in results['vout_im']]

    n = len(freq)
    if n < 10:
        raise Exception(f'Expected AC sweep data, got only {n} points')

    # Compute magnitude in dB
    mag_db = []
    for i in range(n):
        mag = math.sqrt(vout_re[i] ** 2 + vout_im[i] ** 2)
        if mag > 0:
            mag_db.append(20.0 * math.log10(mag))
        else:
            mag_db.append(-200.0)

    # DC gain (first point, lowest frequency)
    dc_gain = mag_db[0]

    # Find -3dB point (where gain drops 3dB below DC)
    target = dc_gain - 3.0
    f_3db = freq[-1]  # default: beyond sweep range

    for i in range(1, n):
        if mag_db[i - 1] >= target > mag_db[i]:
            # Linear interpolation
            frac = (target - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
            f_3db = freq[i - 1] + frac * (freq[i] - freq[i - 1])
            break

    return {
        'dc_gain': [dc_gain],
        'f_3db': [f_3db],
    }
