"""
CACE postprocessing script: extract band-pass filter parameters from AC data.

Input:
    results['vout_re']  — real part of V(vout) at each frequency
    results['vout_im']  — imaginary part of V(vout)
    results['freq']     — frequency points (Hz)
    conditions['f_clk'] — switching clock frequency (Hz)
    conditions['q_code'] — Q control code

Output:
    {'f0': [center_freq_Hz], 'peak_gain': [gain_dB], 'q_meas': [measured_Q]}
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

    # Find peak (BP center frequency)
    peak_idx = 0
    peak_val = mag_db[0]
    for i in range(1, n):
        if mag_db[i] > peak_val:
            peak_val = mag_db[i]
            peak_idx = i

    f0 = freq[peak_idx]
    peak_gain = peak_val

    # Find -3dB points for Q measurement
    target = peak_val - 3.0

    # Lower -3dB: search from left to peak
    f_lo = freq[0]
    for i in range(1, peak_idx + 1):
        if mag_db[i - 1] < target <= mag_db[i]:
            # Linear interpolation
            frac = (target - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
            f_lo = freq[i - 1] + frac * (freq[i] - freq[i - 1])
            break

    # Upper -3dB: search from peak to right
    f_hi = freq[-1]
    for i in range(peak_idx + 1, n):
        if mag_db[i - 1] >= target > mag_db[i]:
            frac = (target - mag_db[i - 1]) / (mag_db[i] - mag_db[i - 1])
            f_hi = freq[i - 1] + frac * (freq[i] - freq[i - 1])
            break

    bw = f_hi - f_lo
    q_meas = f0 / bw if bw > 0 else 0.0

    return {
        'f0': [f0],
        'peak_gain': [peak_gain],
        'q_meas': [q_meas],
    }
