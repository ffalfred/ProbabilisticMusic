"""Mix-level processing driven by golem dimensions over time (mixer.py
_apply_state_to_mix): overdrive (overdrive_drive) and a compressor whose
threshold is the golem's dynamic centre (dynamic_center).

Both take per-sample control curves (frames,) and audio (frames, channels).
"""
import numpy as np
from scipy.signal import resample_poly

# Saturation: a signal at this level (≈ −12 dBFS) keeps its level whatever
# the drive, so drive changes the colour and squeezes peaks rather than
# making everything louder or quieter.
_SAT_REF = 0.25
_DRIVE_DB = 24.0                 # drive 1 = 24 dB into the saturator


def saturate(x: np.ndarray, sr: int, drive) -> np.ndarray:
    """Overdrive: tanh saturation, mixed in by `drive` (0..1, per sample).

    drive 0 is exactly the input. At drive d the signal goes into a tanh at
    +24·d dB and is mixed in at d: 0.15 adds a little warmth to peaks, 0.3 is
    clearly driven, 1 is fully saturated (quiet parts come up, peaks flatten).
    Run at twice the sample rate so the new harmonics don't fold back down.
    """
    x = np.asarray(x, dtype=np.float32)
    d = np.clip(np.asarray(drive, dtype=np.float32), 0.0, 1.0)
    if d.ndim == 0:
        d = np.full(len(x), d, dtype=np.float32)
    if len(x) == 0 or float(d.max()) <= 1e-4:
        return x
    mono = x.ndim == 1
    xf = x[:, None] if mono else x
    up = resample_poly(xf, 2, 1, axis=0).astype(np.float32)
    d2 = np.repeat(d, 2)[:len(up)]
    if len(d2) < len(up):
        d2 = np.concatenate([d2, np.full(len(up) - len(d2), d2[-1] if len(d2) else 0.0, np.float32)])
    g = np.power(np.float32(10.0), d2 * np.float32(_DRIVE_DB / 20.0))[:, None]   # float32 throughout
    wet = np.tanh(g * up)
    wet *= np.float32(_SAT_REF) / np.tanh(g * np.float32(_SAT_REF))
    wet -= up
    wet *= d2[:, None]                        # what the drive adds, at 2× rate
    # The dry signal is never resampled: only the added part goes back down,
    # so drive 0 is exactly the input
    add = resample_poly(wet, 1, 2, axis=0)[:len(xf)].astype(np.float32)
    y = xf.copy()
    y[:len(add)] += add
    return y[:, 0] if mono else y


def compress(x: np.ndarray, sr: int, threshold_db, ratio: float = 2.0,
             attack: float = 0.010, release: float = 0.150,
             makeup: float = 0.5, block_ms: float = 1.0) -> np.ndarray:
    """Compressor with a threshold that changes over time.

    Above `threshold_db` (dBFS, per sample) the level rises 1/ratio as fast;
    both channels get the same gain. Peak detection on 1 ms blocks, with
    attack / release smoothing of the gain. `makeup` gives back that share of
    the reduction a full-scale peak would get, so a low threshold squeezes
    the dynamics toward the centre rather than only turning things down.
    """
    x = np.asarray(x, dtype=np.float32)
    n = len(x)
    if n == 0:
        return x
    thr = np.asarray(threshold_db, dtype=np.float64)
    if thr.ndim == 0:
        thr = np.full(n, float(thr))
    blk = max(1, int(sr * block_ms / 1000.0))
    nb = (n + blk - 1) // blk
    a = np.abs(x).reshape(n, -1).max(axis=1)
    peak = np.zeros(nb * blk, dtype=np.float32)
    peak[:n] = a
    lvl_db = 20.0 * np.log10(np.maximum(peak.reshape(nb, blk).max(axis=1), 1e-9))
    thr_b = thr[np.minimum(np.arange(nb) * blk + blk // 2, n - 1)]
    slope = 1.0 - 1.0 / max(ratio, 1.0)
    want = -np.maximum(lvl_db - thr_b, 0.0) * slope          # target gain (dB, ≤ 0)

    ca = np.exp(-blk / (sr * max(attack, 1e-4)))
    cr = np.exp(-blk / (sr * max(release, 1e-4)))
    gr = np.empty(nb)
    g = 0.0
    for i in range(nb):                       # ~1000 steps per second of audio
        w = want[i]
        c = ca if w < g else cr               # falling gain = attack
        g = c * g + (1.0 - c) * w
        gr[i] = g
    gain_db = gr + makeup * slope * np.maximum(-thr_b, 0.0)
    centres = np.arange(nb) * blk + blk / 2.0
    gain = (10.0 ** (np.interp(np.arange(n), centres, gain_db) / 20.0)).astype(np.float32)
    return x * (gain if x.ndim == 1 else gain[:, None])
