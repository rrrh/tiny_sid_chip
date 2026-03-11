"""
CACE postprocessing script: extract comparator propagation delay.

The OTA+inverter is overall inverting: vinp > vinn -> out LOW.

Input:
    results['time']  — time points (s)
    results['vinp']  — input voltage waveform (step up at ~50ns, step down at ~200ns)
    results['vout']  — output voltage waveform
    conditions['vdd'] — supply voltage

Output:
    {'t_plh': [delay_ns], 't_phl': [delay_ns]}

tPHL: vinp steps UP through Vinn -> output falls (high-to-low)
tPLH: vinp steps DOWN through Vinn -> output rises (low-to-high)
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    time = [float(t) for t in results['time']]
    vinp = [float(v) for v in results['vinp']]
    vout = [float(v) for v in results['vout']]
    n = len(time)

    if n < 100:
        raise Exception(f'Expected transient data, got only {n} points')

    vdd = float(conditions.get('vdd', 1.2))
    vinn = vdd / 2.0
    threshold = vdd / 2.0

    t_plh = None
    t_phl = None

    # --- tPHL: vinp rises through vinn near 50ns -> output FALLS ---
    for i in range(1, n):
        if vinp[i - 1] < vinn <= vinp[i] and time[i] > 40e-9:
            frac = (vinn - vinp[i - 1]) / max(vinp[i] - vinp[i - 1], 1e-15)
            t_cross = time[i - 1] + frac * (time[i] - time[i - 1])
            for j in range(i, n):
                if vout[j - 1] >= threshold > vout[j]:
                    frac2 = (threshold - vout[j - 1]) / min(vout[j] - vout[j - 1], -1e-15)
                    t_out = time[j - 1] + frac2 * (time[j] - time[j - 1])
                    t_phl = t_out - t_cross
                    break
            break

    # --- tPLH: vinp falls through vinn near 200ns -> output RISES ---
    for i in range(1, n):
        if vinp[i - 1] >= vinn > vinp[i] and time[i] > 150e-9:
            frac = (vinn - vinp[i - 1]) / min(vinp[i] - vinp[i - 1], -1e-15)
            t_cross = time[i - 1] + frac * (time[i] - time[i - 1])
            for j in range(i, n):
                if vout[j - 1] < threshold <= vout[j]:
                    frac2 = (threshold - vout[j - 1]) / max(vout[j] - vout[j - 1], 1e-15)
                    t_out = time[j - 1] + frac2 * (time[j] - time[j - 1])
                    t_plh = t_out - t_cross
                    break
            break

    if t_plh is None:
        t_plh = 999e-9
    if t_phl is None:
        t_phl = 999e-9

    return {
        't_plh': [t_plh],
        't_phl': [t_phl],
    }
