"""
CACE postprocessing script: extract high-pass filter parameters from AC data.

Input:
    results['vout_re']  — real part of V(vout)
    results['vout_im']  — imaginary part of V(vout)
    results['freq']     — frequency points (Hz)

Output:
    {'hf_gain': [gain_dB], 'f_3db': [freq_Hz]}
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

    # HF gain (last point, highest frequency)
    hf_gain = mag_db[-1]

    # Find -3dB point searching from high freq to low freq
    target = hf_gain - 3.0
    f_3db = freq[0]  # default: beyond sweep range

    for i in range(n - 2, -1, -1):
        if mag_db[i] < target <= mag_db[i + 1]:
            frac = (target - mag_db[i]) / (mag_db[i + 1] - mag_db[i])
            f_3db = freq[i] + frac * (freq[i + 1] - freq[i])
            break

    return {
        'hf_gain': [hf_gain],
        'f_3db': [f_3db],
    }
