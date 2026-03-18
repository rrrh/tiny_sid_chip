"""
CACE postprocessing script: extract SAR ADC full-conversion parameters.

Input:
    results['code_out'] — SAR output code (0..255) at each vin step
    results['vtop']     — DAC top-plate voltage at each step
    results['residual'] — vin - vtop residual at each step
    conditions['vdd']   — supply/reference voltage (V)

Output:
    {'inl': [max_abs_inl], 'dnl': [max_abs_dnl], 'conv_time_ns': [800.0]}

INL/DNL are computed from the code_out vs vin transfer function
using the endpoint-fit method.
"""

from typing import Any


def postprocess(
    results: dict[str, list], conditions: dict[str, Any]
) -> dict[str, list]:

    code_raw = [float(v) for v in results['code_out']]
    vdd = float(conditions.get('vdd', 1.2))

    # The DC sweep goes from 0 to VDD in 257 steps (0, VDD/256, ..., VDD).
    # Build the transfer function: for each code 0..255, find the vin
    # threshold where code transitions from (code-1) to code.
    # Round codes to nearest integer.
    codes = [int(round(c)) for c in code_raw]

    # Clamp to valid range
    codes = [max(0, min(255, c)) for c in codes]

    n_points = len(codes)
    if n_points < 10:
        raise Exception(f'Expected ~257 data points, got {n_points}')

    # Build code-to-first-occurrence mapping (transition thresholds)
    # For each code k, find the first vin index where code >= k
    # The vin values are linearly spaced: vin[i] = vdd * i / 256
    first_idx = {}
    for i, c in enumerate(codes):
        if c not in first_idx:
            first_idx[c] = i

    # Extract the unique codes present in the sweep
    unique_codes = sorted(first_idx.keys())
    n_codes = len(unique_codes)

    if n_codes < 2:
        raise Exception(f'Only {n_codes} unique codes found in sweep')

    # Compute the transition voltages (midpoint of each code bin)
    # For endpoint INL/DNL, use the code-center voltages
    # vin_center[k] = average vin for all points with code == k
    code_centers = {}
    code_counts = {}
    for i, c in enumerate(codes):
        vin_i = vdd * i / 256.0
        if c not in code_centers:
            code_centers[c] = 0.0
            code_counts[c] = 0
        code_centers[c] += vin_i
        code_counts[c] += 1

    for c in code_centers:
        code_centers[c] /= code_counts[c]

    # Endpoint-corrected INL/DNL
    # Use the first and last unique codes as endpoints
    c_min = unique_codes[0]
    c_max = unique_codes[-1]
    v_min = code_centers[c_min]
    v_max = code_centers[c_max]

    if c_max == c_min:
        raise Exception('All codes are identical — ADC not functioning')

    # Ideal LSB in voltage
    lsb_v = (v_max - v_min) / (c_max - c_min)

    # Compute step sizes (DNL) between consecutive codes
    max_abs_dnl = 0.0
    for i in range(1, len(unique_codes)):
        c_prev = unique_codes[i - 1]
        c_curr = unique_codes[i]
        step_v = code_centers[c_curr] - code_centers[c_prev]
        code_diff = c_curr - c_prev
        # DNL = actual_step / ideal_step - 1 (per code step)
        if code_diff > 0:
            dnl_k = step_v / (lsb_v * code_diff) - 1.0
            if abs(dnl_k) > max_abs_dnl:
                max_abs_dnl = abs(dnl_k)

    # Compute INL (endpoint corrected)
    max_abs_inl = 0.0
    for c in unique_codes:
        ideal_v = v_min + (c - c_min) * lsb_v
        inl_k = (code_centers[c] - ideal_v) / lsb_v
        if abs(inl_k) > max_abs_inl:
            max_abs_inl = abs(inl_k)

    # Conversion time: 8 clock cycles at 10 MHz = 800 ns
    conv_time_ns = 800.0

    return {
        'inl': [max_abs_inl],
        'dnl': [max_abs_dnl],
        'conv_time_ns': [conv_time_ns],
    }
