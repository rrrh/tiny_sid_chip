"""
CACE postprocessing script: extract comparator parameters from transient data.

Input:
    results['time']  — time points (s)
    results['outp']  — positive output voltage
    results['outn']  — negative output voltage
    results['clk']   — clock signal
    conditions['vdiff'] — applied differential input (mV)
    conditions['vdd']   — supply voltage (V)

Output:
    {'t_resolve': [resolve_time_ns], 'decision': [correct_decision]}

Resolve time: from clk rising edge to |outp - outn| > VDD/2
Decision: 1.0 if correct (outp > outn for vdiff > 0), 0.0 if wrong
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    time = [float(t) for t in results['time']]
    outp = [float(v) for v in results['outp']]
    outn = [float(v) for v in results['outn']]
    clk = [float(v) for v in results['clk']]

    vdd = float(conditions.get('vdd', 1.2))
    vdiff = float(conditions.get('vdiff', 10))
    threshold = vdd / 2.0

    n = len(time)
    if n < 100:
        raise Exception(f'Expected transient data, got only {n} points')

    # Find first clock rising edge (clk crosses VDD/2 going up)
    clk_rise_idx = None
    for i in range(1, n):
        if clk[i - 1] < threshold <= clk[i]:
            clk_rise_idx = i
            break

    if clk_rise_idx is None:
        raise Exception('No clock rising edge found in transient data')

    clk_rise_time = time[clk_rise_idx]

    # Find when |outp - outn| exceeds VDD/2 after clock rise
    resolve_time_ns = -1.0
    final_outp = outp[-1]
    final_outn = outn[-1]

    for i in range(clk_rise_idx, n):
        diff = abs(outp[i] - outn[i])
        if diff > threshold:
            resolve_time_ns = (time[i] - clk_rise_time) * 1e9
            break

    if resolve_time_ns < 0:
        resolve_time_ns = 10.0  # Did not resolve within window

    # Check if decision is correct
    # In this StrongARM topology: vinp > vinn → more current through Mn1
    # → dn drops faster → outp drops (via cross-coupled latch) → outp < outn
    if vdiff > 0:
        correct = 1.0 if final_outp < final_outn else 0.0
    elif vdiff < 0:
        correct = 1.0 if final_outp > final_outn else 0.0
    else:
        correct = 0.5  # Metastable for zero input

    return {
        't_resolve': [resolve_time_ns],
        'decision': [correct],
    }
