"""
CACE postprocessing: extract step response parameters from transient data.

Input:
    results['time']  — time points (s)
    results['vout']  — output voltage (V)
    conditions['f_clk'] — clock frequency (Hz)

Output:
    {'v_final': [V], 'settling_cycles': [cycles], 'overshoot': [%]}
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    time = [float(t) for t in results['time']]
    vout = [float(v) for v in results['vout']]

    n = len(time)
    if n < 100:
        raise Exception(f'Expected transient data, got only {n} points')

    f_clk = float(conditions['f_clk'])
    t_clk = 1.0 / f_clk
    t_step = 100 * t_clk  # step occurs at 100 clock cycles

    # Find the step index
    step_idx = 0
    for i in range(n):
        if time[i] >= t_step:
            step_idx = i
            break

    # Pre-step value (average over last 10 points before step)
    pre_start = max(0, step_idx - 10)
    v_pre = sum(vout[pre_start:step_idx]) / max(1, step_idx - pre_start)

    # Final value (average over last 10% of simulation)
    tail_start = int(0.9 * n)
    v_final = sum(vout[tail_start:]) / (n - tail_start)

    step_size = v_final - v_pre
    if abs(step_size) < 1e-6:
        # No measurable step — return defaults
        return {
            'v_final': [v_final],
            'settling_cycles': [0],
            'overshoot': [0.0],
        }

    # Peak value after step (for overshoot)
    post_vout = vout[step_idx:]
    if step_size > 0:
        v_peak = max(post_vout)
    else:
        v_peak = min(post_vout)

    overshoot_pct = abs((v_peak - v_final) / step_size) * 100.0

    # Settling time: find last time output is outside 5% band
    band = abs(step_size) * 0.05
    settling_idx = step_idx
    for i in range(n - 1, step_idx, -1):
        if abs(vout[i] - v_final) > band:
            settling_idx = i
            break

    settling_time = time[settling_idx] - t_step
    settling_cycles = settling_time / t_clk

    return {
        'v_final': [v_final],
        'settling_cycles': [settling_cycles],
        'overshoot': [overshoot_pct],
    }
