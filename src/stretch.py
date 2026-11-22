"""Pitch shifting and time stretching.

Everything in the engine that changes pitch without changing speed, or speed
without changing pitch, goes through this module: event pitch, pitch-locked
speed, tempo steps and ramps, banded glissandi, the overtones effect and the
Morphogenics effects.

The back end is Rubber Band (R3 "finer" engine) through Spotify's pedalboard.
Compared with librosa's phase vocoder, which this replaced, it keeps attacks
sharp instead of smearing them, and it handles stereo channels together, so
the stereo image survives. It is deterministic: the same input always gives
the same output.

Licence note: Rubber Band and pedalboard are GPLv3, while this project is
Apache-2.0. That doesn't matter for using the tool, but distributing it means
GPL terms. If that ever becomes a problem, this module is the only place to
change: Signalsmith Stretch (MIT, `python-stretch` on PyPI) was the runner-up
in the 2026-11 comparison. See CHANGELOG ("Changed — pitch and time").

Shapes: every function takes and returns either a 1-D signal (n,) or a
(frames, channels) array, and gives back the same layout.

Cost: Rubber Band is ~3-5x slower than the phase vocoder it replaced, and
each call has a fixed set-up cost (~45 ms). Callers that shift many pieces
should, in order of preference: pass one pitch curve for the whole signal
(pitch_shift accepts per-sample arrays); shift the whole clip once and cut
the pieces out; or run independent calls through parallel_map (Rubber Band
releases the GIL, so threads scale; results are identical to serial). Grains
too short for any time-stretcher use read_at_rate.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import pedalboard as _pb

_POOL = None


def parallel_map(fn, items) -> list:
    """list(map(fn, items)) on a shared thread pool, in order.

    For independent Rubber Band calls (chord voices, per-note transforms).
    `fn` must not itself call parallel_map: the pool is shared, and nested
    waits could fill it.
    """
    global _POOL
    items = list(items)
    if len(items) < 2:
        return [fn(i) for i in items]
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2),
                                   thread_name_prefix='stretch')
    return list(_POOL.map(fn, items))


def _to_ch_first(x: np.ndarray):
    """(n,) or (frames, ch) → contiguous float32 (ch, frames), plus a restorer."""
    if x.ndim == 1:
        return np.ascontiguousarray(x[None, :], dtype=np.float32), lambda y: y[0]
    return np.ascontiguousarray(x.T, dtype=np.float32), lambda y: np.ascontiguousarray(y.T)


def _fit(y: np.ndarray, n: int) -> np.ndarray:
    """Trim or zero-pad (ch, frames) to exactly n frames."""
    if y.shape[1] > n:
        return y[:, :n]
    if y.shape[1] < n:
        return np.pad(y, ((0, 0), (0, n - y.shape[1])))
    return y


def _rubberband(x: np.ndarray, sr: int, rate, semitones, n_out: int) -> np.ndarray:
    if len(x) == 0 or n_out <= 0:
        return np.zeros((max(n_out, 0),) + x.shape[1:], dtype=np.float32)
    y, back = _to_ch_first(x)
    out = _pb.time_stretch(
        y, float(sr),
        stretch_factor=rate,
        pitch_shift_in_semitones=semitones,
        high_quality=True,          # R3 engine; the fast mode smears as much as librosa
        transient_mode='crisp',
        preserve_formants=False,    # shift the whole spectrum, like tape or a sampler
    )
    # Rubber Band already compensates its latency; with time-varying curves it
    # adds some silence at the end. Fit to the exact expected length.
    return back(_fit(out, n_out)).astype(np.float32, copy=False)


def _curve(v, n: int):
    """A scalar stays a float; a per-sample curve becomes float64 of length n."""
    if np.ndim(v) == 0:
        return float(v)
    v = np.asarray(v, dtype=np.float64)
    if len(v) != n:
        raise ValueError(f'curve has {len(v)} values for {n} samples')
    return v


def pitch_shift(x: np.ndarray, sr: int, semitones) -> np.ndarray:
    """Shift pitch by `semitones` without changing length.

    `semitones` is a number, or an array with one value per input sample for a
    pitch that moves over time (glides, vibrato, stepped detune). Rubber Band
    reads a moving curve about every 1024 samples, and the timing of the
    output can wander by up to ~20 ms over long, wide glides.
    """
    n = len(x)
    st = _curve(semitones, n)
    if np.ndim(st) == 0 and abs(st) < 1e-4:
        return x.astype(np.float32, copy=True)
    return _rubberband(x, sr, 1.0, st, n)


def time_stretch(x: np.ndarray, sr: int, rate) -> np.ndarray:
    """Change speed without changing pitch. rate > 1 = faster/shorter.

    `rate` is a number, or an array with one value per input sample (a tempo
    ramp). The output length is exactly sum(1 / rate) samples, so a tempo map
    built from it is exact at the ends; inside a ramp the timing can be off
    by up to ~20 ms (Rubber Band updates the rate every ~1024 samples).
    """
    n = len(x)
    r = _curve(rate, n)
    if np.ndim(r) == 0:
        r = max(r, 0.01)
        if abs(r - 1.0) < 1e-4:
            return x.astype(np.float32, copy=True)
        n_out = int(round(n / r))
    else:
        r = np.maximum(r, 0.01)
        n_out = int(round(np.sum(1.0 / r)))
    return _rubberband(x, sr, r, 0.0, n_out)


def transform(x: np.ndarray, sr: int, rate: float = 1.0, semitones: float = 0.0) -> np.ndarray:
    """Change speed and pitch independently in one pass (constant values).
    Output length is round(len(x) / rate)."""
    rate = max(float(rate), 0.01)
    if abs(rate - 1.0) < 1e-4 and abs(semitones) < 1e-4:
        return x.astype(np.float32, copy=True)
    return _rubberband(x, sr, rate, float(semitones), int(round(len(x) / rate)))


def read_at_rate(x: np.ndarray, start: float, n_out: int, ratio) -> np.ndarray:
    """Tape-style read of a 1-D signal: n_out samples from position `start`,
    advancing `ratio` input samples per output sample (2 = an octave up).

    `ratio` is a number or an array of n_out values (a glide). Pitch and speed
    change together, which is what grains and short portamento slides want:
    they are too short for a time-stretcher. Reads past the end are silent.
    """
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    step = np.broadcast_to(np.asarray(ratio, dtype=np.float64), (n_out,))
    pos = start + np.concatenate([[0.0], np.cumsum(step[:-1])])
    return np.interp(pos, np.arange(len(x)), x, left=0.0, right=0.0).astype(np.float32)


def steps_to_curve(values, hop: int, n: int, glide: int = None) -> np.ndarray:
    """Per-sample curve from one value per `hop` samples, with linear glides of
    `glide` samples (default: a whole hop) between neighbouring values.

    Turns "a new random detune every 250 ms" into one smooth pitch curve, so a
    single Rubber Band call replaces many overlapping short shifts.
    """
    values = np.asarray(values, dtype=np.float64)
    if len(values) == 0:
        return np.zeros(n)
    glide = hop if glide is None else max(1, min(int(glide), hop))
    # Each value holds around the centre of its hop; neighbours are joined by
    # a ramp of `glide` samples centred on the boundary (like a crossfade).
    half_hold = (hop - glide) / 2.0
    pts_t, pts_v = [], []
    for k, v in enumerate(values):
        c = k * hop + hop / 2.0
        for t in ((c - half_hold, c + half_hold) if half_hold > 0 else (c,)):
            pts_t.append(t)
            pts_v.append(v)
    return np.interp(np.arange(n), pts_t, pts_v)
