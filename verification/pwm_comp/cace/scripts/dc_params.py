"""
CACE postprocessing script: extract comparator DC parameters.

Input:
    results['vout'] — output voltage vs Vinp sweep (0 to VDD, 1mV steps)
    conditions['vdd'] — supply voltage

Output:
    {'vos': [offset_mV], 'trip_point': [trip_V]}
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vout = [float(v) for v in results['vout']]
    n = len(vout)

    if n < 100:
        raise Exception(f'Expected DC sweep data, got only {n} points')

    vdd = float(conditions.get('vdd', 1.2))

    # Vinp sweep from 0 to VDD in 1mV steps
    vinp = [i * vdd / (n - 1) for i in range(n)]

    # Find trip point: where output crosses VDD/2
    # OTA is inverting (vinp > vinn -> out goes LOW for this topology)
    # The inverter then re-inverts, so: vinp > vinn -> out HIGH
    # Trip point is where vout crosses VDD/2
    threshold = vdd / 2.0
    trip_point = vdd / 2.0  # default

    for i in range(1, n):
        # Look for upward crossing (out goes from low to high)
        if vout[i - 1] < threshold <= vout[i]:
            frac = (threshold - vout[i - 1]) / (vout[i] - vout[i - 1])
            trip_point = vinp[i - 1] + frac * (vinp[i] - vinp[i - 1])
            break
        # Look for downward crossing (out goes from high to low)
        if vout[i - 1] >= threshold > vout[i]:
            frac = (threshold - vout[i - 1]) / (vout[i] - vout[i - 1])
            trip_point = vinp[i - 1] + frac * (vinp[i] - vinp[i - 1])
            break

    # Offset = trip_point - ideal (VDD/2), in mV
    vos = (trip_point - vdd / 2.0) * 1000.0

    return {
        'vos': [abs(vos)],
        'trip_point': [trip_point],
    }
