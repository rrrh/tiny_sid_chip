#!/usr/bin/env python3
"""Convert filter sweep PWL files to WAV via analog RC filter simulation."""
import numpy as np
import wave
import glob
import os

R1 = R2 = R3 = 3.3e3
C1 = C2 = C3 = 4.7e-9
CAC = 1e-6
RLOAD = 10e3


def process_pwl(pwl_path, wav_path):
    times, volts = [], []
    with open(pwl_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            times.append(float(parts[0].rstrip("n")) * 1e-9)
            volts.append(float(parts[1]))
    t_pwl, v_pwl = np.array(times), np.array(volts)
    # Skip the initial "0n" anchor — normalize to first real PWM edge
    if len(t_pwl) > 1 and t_pwl[0] == 0 and t_pwl[1] > 0.001:
        t_offset = t_pwl[1]
        t_pwl -= t_offset
        t_pwl[0] = 0  # clamp initial point to 0
    else:
        t_pwl -= t_pwl[0]

    dt = 200e-9
    n_steps = int(t_pwl[-1] / dt) + 1
    t = np.linspace(0, t_pwl[-1], n_steps)
    v_in = np.interp(t, t_pwl, v_pwl)

    dt_C1, dt_C2, dt_C3, dt_CAC = dt / C1, dt / C2, dt / C3, dt / CAC
    inv_R1, inv_R2, inv_R3, inv_RL = 1 / R1, 1 / R2, 1 / R3, 1 / RLOAD
    v1 = v2 = v3 = v_cac = 0.0
    v_out = np.zeros(n_steps)

    for i in range(n_steps):
        vin = v_in[i]
        v_audio = v3 - v_cac
        v_out[i] = v_audio
        i_r1 = (vin - v1) * inv_R1
        i_r2 = (v1 - v2) * inv_R2
        i_r3 = (v2 - v3) * inv_R3
        i_load = v_audio * inv_RL
        v1 += (i_r1 - i_r2) * dt_C1
        v2 += (i_r2 - i_r3) * dt_C2
        v3 += (i_r3 - i_load) * dt_C3
        v_cac += i_load * dt_CAC

    v_max = max(abs(v_out.max()), abs(v_out.min()))

    sr = 44100
    n_samp = int(t_pwl[-1] * sr)
    t_wav = np.linspace(0, t_pwl[-1], n_samp, endpoint=False)
    v_wav = np.interp(t_wav, t, v_out)
    if v_max > 0:
        v_norm = v_wav / v_max * 32000
    else:
        v_norm = v_wav
    samples = np.clip(v_norm, -32767, 32767).astype(np.int16)

    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())

    print(f"  {wav_path}: {n_samp} samples, {t_pwl[-1]:.3f}s, peak {v_max*1e3:.1f} mV")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for pwl in sorted(glob.glob(os.path.join(script_dir, "filt_*.pwl"))):
        base = os.path.splitext(pwl)[0]
        wav = base + "_gl.wav"
        name = os.path.basename(base)
        print(f"{name}:")
        process_pwl(pwl, wav)
    print("Done.")
