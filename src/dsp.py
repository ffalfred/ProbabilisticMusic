"""DSP helpers for processing audio piecewise (used by pitch.py and plugins).

Pitch-shifting blocks independently and butting them together leaves a
waveform discontinuity at every seam, which is heard as crackle. These
helpers join pieces with windows / crossfades instead.
"""
import numpy as np


def ola_blocks(audio: np.ndarray, win_len: int, fn, context: int = 2048) -> np.ndarray:
    """Process `audio` in Hann-windowed blocks with 50% overlap.

    fn(k, block) returns the processed block k (any length; it is trimmed or
    zero-padded). Each block is handed to fn with up to `context` samples of
    surrounding audio on both sides, and only the middle is kept: STFT-based
    processors (pitch_shift) produce edge artefacts on short inputs.
    Blocks are overlap-added and normalised by the summed window, so
    unprocessed blocks reconstruct the input exactly.
    """
    n = len(audio)
    win_len = max(16, min(int(win_len), n))
    hop = max(1, win_len // 2)
    out = np.zeros(n, dtype=np.float32)
    weight = np.zeros(n, dtype=np.float32)
    for k, s in enumerate(range(0, n, hop)):
        e = min(s + win_len, n)
        c0 = max(0, s - context)
        c1 = min(n, e + context)
        y = np.asarray(fn(k, audio[c0:c1]), dtype=np.float32)[s - c0:e - c0]
        if len(y) < e - s:
            y = np.pad(y, (0, e - s - len(y)))
        win = np.hanning(win_len + 2)[1:-1][:e - s].astype(np.float32)
        out[s:e] += y * win
        weight[s:e] += win
        if e == n:
            break
    return out / np.maximum(weight, 1e-6)


def splice(dst: np.ndarray, i0: int, new: np.ndarray, xf: int) -> None:
    """Write `new` into dst[i0:i0+len(new)] in place, crossfading with the
    existing content over `xf` samples at both ends."""
    n = min(len(new), len(dst) - i0)
    if n <= 0:
        return
    new = new[:n].astype(np.float32)
    old = dst[i0:i0 + n].copy()
    xf = min(int(xf), n // 2)
    mix = np.ones(n, dtype=np.float32)
    if xf > 1:
        ramp = np.linspace(0.0, 1.0, xf, dtype=np.float32)
        mix[:xf] = ramp
        mix[-xf:] = ramp[::-1]
    dst[i0:i0 + n] = old * (1.0 - mix) + new * mix


def fade_edges(x: np.ndarray, n_fade: int) -> np.ndarray:
    """Return a copy of x with short linear fades at both ends."""
    x = x.astype(np.float32).copy()
    f = min(int(n_fade), len(x) // 2)
    if f > 1:
        x[:f] *= np.linspace(0.0, 1.0, f, dtype=np.float32)
        x[-f:] *= np.linspace(1.0, 0.0, f, dtype=np.float32)
    return x
