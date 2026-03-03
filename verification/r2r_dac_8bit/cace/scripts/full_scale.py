"""
CACE postprocessing script: extract full-scale range from DC sweep results.

Input:
    results['vout'] — list of 256 output voltages (code 0 .. 255)

Output:
    {'vout_min': [V(code=0)], 'vout_max': [V(code=255)]}
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    vout = [float(v) for v in results['vout']]

    if len(vout) < 2:
        raise Exception(f'Expected 256 data points, got {len(vout)}')

    return {
        'vout_min': [vout[0]],
        'vout_max': [vout[-1]],
    }
