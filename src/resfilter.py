"""Resonant low-pass / high-pass filter, fixed or changing over time.

One definition for the Composer's filter effect (static and automated) and
the golems' filter_cutoff / filter_resonance mix dims.

A 2nd-order (RBJ cookbook) biquad. Resonance 0..1 sets Q from 0.707 to 12 on
a log scale: 0 is exactly the Butterworth filter used before (no peak), 0.5
gives Q ≈ 2.9 (+9 dB at the cutoff), 1 gives Q 12 (+22 dB, a whistling peak).
"""
import numpy as np
from scipy.signal import sosfilt

Q_MIN, Q_MAX = 1.0 / np.sqrt(2.0), 12.0


def resonance_to_q(res):
    """Resonance 0..1 → filter Q (0.707..12, log scale)."""
    r = np.clip(np.asarray(res, dtype=np.float64), 0.0, 1.0)
    return Q_MIN * (Q_MAX / Q_MIN) ** r


def _sos(cut, q, sr, btype):
    """Biquad coefficients as sos rows, one per (cut, q) pair."""
    cut = np.clip(np.atleast_1d(np.asarray(cut, dtype=np.float64)), 20.0, 0.49 * sr)
    q = np.atleast_1d(np.asarray(q, dtype=np.float64))
    w0 = 2.0 * np.pi * cut / sr
    cw, alpha = np.cos(w0), np.sin(w0) / (2.0 * q)
    if btype == 'high':
        b0 = (1.0 + cw) / 2.0
        b1 = -(1.0 + cw)
    else:
        b0 = (1.0 - cw) / 2.0
        b1 = 1.0 - cw
    a0 = 1.0 + alpha
    return np.stack([b0 / a0, b1 / a0, b0 / a0,
                     np.ones_like(cw), -2.0 * cw / a0, (1.0 - alpha) / a0], axis=-1)


def resonant_filter(x: np.ndarray, sr: int, cutoff, resonance=0.0,
                    btype: str = 'low', block: int = 64) -> np.ndarray:
    """Filter x (frames × channels, or mono) with a resonant 'low' or 'high'
    pass. cutoff (Hz) and resonance (0..1) are numbers or per-sample arrays;
    a changing filter updates every `block` samples with its state carried
    over, so sweeps are smooth (no segments, no crossfades)."""
    x = np.asarray(x, dtype=np.float32)
    n = len(x)
    if n == 0:
        return x
    cut = np.asarray(cutoff, dtype=np.float64)
    res = np.asarray(resonance, dtype=np.float64)
    if cut.ndim == 0 and res.ndim == 0:
        return sosfilt(_sos(cut, resonance_to_q(res), sr, btype), x, axis=0).astype(np.float32)

    cut = np.broadcast_to(cut, (n,)) if cut.ndim == 0 else cut[:n]
    res = np.broadcast_to(res, (n,)) if res.ndim == 0 else res[:n]
    mids = np.minimum(np.arange(0, n, block) + block // 2, n - 1)
    sos_all = _sos(cut[mids], resonance_to_q(res[mids]), sr, btype)      # (blocks, 6)
    if _biquad_blocks is not None:
        x2 = x.reshape(n, -1).astype(np.float64)
        return _biquad_blocks(x2, sos_all, block).astype(np.float32).reshape(x.shape)
    out = np.empty_like(x)
    zi = np.zeros((1, 2) + x.shape[1:])
    for k, s in enumerate(range(0, n, block)):
        e = min(n, s + block)
        out[s:e], zi = sosfilt(sos_all[k:k + 1], x[s:e], axis=0, zi=zi)
    return out


# Compiled sample loop (numba ships with librosa); ~20× faster than calling
# sosfilt once per block. Same maths: transposed direct form II, state kept
# across coefficient changes.
try:
    from numba import njit

    @njit(cache=True)
    def _biquad_blocks(x, sos_all, block):
        n, ch = x.shape
        y = np.empty_like(x)
        for c in range(ch):
            z1 = 0.0
            z2 = 0.0
            for i in range(n):
                k = i // block
                b0 = sos_all[k, 0]; b1 = sos_all[k, 1]; b2 = sos_all[k, 2]
                a1 = sos_all[k, 4]; a2 = sos_all[k, 5]
                xi = x[i, c]
                yi = b0 * xi + z1
                z1 = b1 * xi - a1 * yi + z2
                z2 = b2 * xi - a2 * yi
                y[i, c] = yi
        return y
except Exception:                                   # no numba: block loop above
    _biquad_blocks = None
