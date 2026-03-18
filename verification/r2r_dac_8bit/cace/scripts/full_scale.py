"""
CACE postprocessing script: extract full-scale range from DC sweep results.

Input:
    results['vout'] — list of 256 output voltages (code 0 .. 255)

Output:
    {'vout_min': [min(Vout)], 'vout_max': [max(Vout)]}

Note: NMOS shunt-switch R-2R has inverted output — code 0 gives max,
code 255 gives min. We report actual min/max regardless of code order.
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vout = [float(v) for v in results['vout']]

    if len(vout) < 2:
        raise Exception(f'Expected 256 data points, got {len(vout)}')

    return {
        'vout_min': [min(vout)],
        'vout_max': [max(vout)],
    }
