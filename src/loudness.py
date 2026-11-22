"""Output loudness: the safety brake and the optional export adjustment.

Renders keep the level the performance produced. Two optional steps finish
the audio:

  adjust  one gain for the whole file, chosen by measured loudness (LUFS,
          ITU-R BS.1770): match the source recording, or reach a target
          such as -14 (streaming), -16 (Apple / podcasts), -23 (broadcast).
          It never changes levels inside the piece.
  brake   a look-ahead limiter that pulls down only the moments that would
          go above the ceiling (-1 dBFS) and leaves everything else as is.

`finish` runs adjust then brake and reports what it did.
"""
import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import sosfilt

from src.dsp import as_frames

CEILING_DB = -1.0
TARGETS = {'streaming': -14.0, 'apple': -16.0, 'broadcast': -23.0}


# ─── Loudness measurement (ITU-R BS.1770-4) ─────────────────────────────────

def _k_weighting(sr: int):
    """The two BS.1770 pre-filters (high shelf + high pass) for any rate."""
    # High shelf: +4 dB above ~1.5 kHz (head acoustics)
    G, Q, fc = 4.0, 1 / np.sqrt(2), 1500.0
    A = 10 ** (G / 40)
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * Q)
    cw, sA = np.cos(w0), np.sqrt(A)
    shelf = (
        [A * ((A + 1) + (A - 1) * cw + 2 * sA * alpha),
         -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - 2 * sA * alpha)],
        [(A + 1) - (A - 1) * cw + 2 * sA * alpha,
         2 * ((A - 1) - (A + 1) * cw),
         (A + 1) - (A - 1) * cw - 2 * sA * alpha],
    )
    # High pass at ~38 Hz (RLB weighting)
    Q, fc = 0.5, 38.0
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * Q)
    cw = np.cos(w0)
    hp = ([(1 + cw) / 2, -(1 + cw), (1 + cw) / 2],
          [1 + alpha, -2 * cw, 1 - alpha])
    return shelf, hp


def measure_lufs(audio, sr: int) -> float:
    """Integrated loudness in LUFS (gated, BS.1770-4). -inf for silence.

    Mono counts as one channel, as the standard says: the same signal
    as dual-mono stereo reads 3 LU louder.
    """
    x = as_frames(audio).astype(np.float64)
    block, step = int(round(0.4 * sr)), int(round(0.1 * sr))
    if len(x) < block:                       # shorter than one block: pad
        x = np.pad(x, ((0, block - len(x)), (0, 0)))
    # Both pre-filters in one pass (second-order sections)
    sos = np.vstack([np.concatenate([np.asarray(b) / a[0], np.asarray(a) / a[0]])
                     for b, a in _k_weighting(sr)])
    x = sosfilt(sos, x, axis=0)
    # Mean square per 400 ms block (75 % overlap), summed over L/R (weight 1)
    csum = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(x * x, axis=0)])
    starts = np.arange(0, len(x) - block + 1, step)
    z = ((csum[starts + block] - csum[starts]) / block).sum(axis=1)
    with np.errstate(divide='ignore'):
        lk = -0.691 + 10 * np.log10(z)
    z = z[lk > -70.0]                                   # absolute gate
    if not len(z):
        return float('-inf')
    rel = -0.691 + 10 * np.log10(z.mean()) - 10.0       # relative gate
    with np.errstate(divide='ignore'):
        z = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(z.mean()))


def peak_db(audio) -> float:
    p = float(np.max(np.abs(audio))) if np.size(audio) else 0.0
    return 20 * np.log10(p) if p > 0 else float('-inf')


# ─── Safety brake ───────────────────────────────────────────────────────────

def brake(audio, sr: int, ceiling_db: float = CEILING_DB,
          lookahead: float = 0.005, release: float = 0.15):
    """Look-ahead peak limiter. Returns (audio, max gain reduction in dB).

    Below the ceiling the audio passes through bit-identical. Above it, the
    gain dips smoothly over `lookahead` seconds ahead of each peak (so no
    sample exceeds the ceiling) and recovers over `release` seconds. Both
    channels get the same gain, so the stereo image does not shift.
    """
    x = as_frames(audio)
    ceiling = 10 ** (ceiling_db / 20)
    level = np.abs(x[:, 0]).astype(np.float64)
    for c in range(1, x.shape[1]):
        np.maximum(level, np.abs(x[:, c]), out=level)
    if not len(level) or level.max() <= ceiling:
        return audio, 0.0

    need = np.minimum(1.0, ceiling / np.maximum(level, 1e-12))   # gain each frame needs
    L = max(1, int(lookahead * sr))
    # Hold the lowest gain for L frames on each side, then smooth with an
    # L-frame average: every average that touches a peak is built only from
    # values at or below that peak's gain, so the peak is always covered.
    g = minimum_filter1d(need, size=2 * L + 1, mode='nearest')
    g = uniform_filter1d(g, size=L + 1, mode='nearest')
    g = np.minimum(g, need)                                       # rounding safety

    # Release: reduction (dB) decays exponentially after each peak,
    # r_out[n] = max_k r[k]·a^(n-k), computed in log space as a running max.
    # The tail is ended once it is inaudible (0.001 dB), so the audio after a
    # peak returns to bit-identical. Only the spans where the brake acts — a
    # peak and its tail — are computed; the rest is passed through.
    a = np.exp(-1.0 / max(1.0, release * sr))
    act = np.flatnonzero(g < 1.0)
    out = x.astype(np.float32, copy=True)
    max_red = 0.0
    if len(act):
        r_max = float(-20 * np.log10(g[act].min()))
        tail = int(np.ceil(np.log(max(r_max, 2e-3) / 1e-3) / -np.log(a))) + 2
        gaps = np.flatnonzero(np.diff(act) > tail)
        starts = np.concatenate([[act[0]], act[gaps + 1]])
        ends = np.minimum(np.concatenate([act[gaps], [act[-1]]]) + tail + 1, len(g))
        for s0, e0 in zip(starts, ends):
            r = -20 * np.log10(g[s0:e0])
            n = np.arange(e0 - s0)
            with np.errstate(divide='ignore'):
                logr = np.where(r > 1e-9, np.log(np.maximum(r, 1e-300)), -np.inf)
            held = np.maximum.accumulate(logr - n * np.log(a)) + n * np.log(a)
            r_out = np.maximum(r, np.exp(held))
            r_out[r_out < 1e-3] = 0.0
            max_red = max(max_red, float(r_out.max()))
            out[s0:e0] = (x[s0:e0] * (10 ** (-r_out / 20))[:, None]).astype(np.float32)

    np.clip(out, -ceiling, ceiling, out=out)                      # float rounding only
    if np.ndim(audio) == 1:
        out = out[:, 0]
    return out, max_red


# ─── Finishing ──────────────────────────────────────────────────────────────

def finish(audio, sr: int, adjust: str = 'none', target_lufs: float = None,
           source=None, use_brake: bool = True):
    """Apply the export adjustment, then the brake. Returns (audio, report).

    adjust: 'none'   — keep the level as performed
            'source' — same loudness as `source` (the loaded recording)
            'target' — reach `target_lufs`
    The report says what happened, for the user: measured loudness before
    and after, the gain applied, how hard the brake worked, and the peak.
    """
    report = {'adjust': adjust, 'gain_db': 0.0, 'brake_db': 0.0}
    before = measure_lufs(audio, sr) if np.size(audio) else float('-inf')
    report['lufs_before'] = before

    goal = None
    if adjust == 'source' and source is not None and np.size(source):
        goal = measure_lufs(source, sr)
        report['source_lufs'] = goal
    elif adjust == 'target' and target_lufs is not None:
        goal = float(target_lufs)
    if goal is not None and np.isfinite(goal) and np.isfinite(before):
        report['gain_db'] = goal - before
        audio = (audio * 10 ** (report['gain_db'] / 20)).astype(np.float32)

    if use_brake:
        audio, report['brake_db'] = brake(audio, sr)

    report['lufs'] = before + report['gain_db'] if np.isfinite(before) else before
    if report['brake_db'] > 0:                  # the brake lowers it slightly
        report['lufs'] = measure_lufs(audio, sr)
    report['peak_db'] = peak_db(audio)
    # JSON has no -inf: report silence as None
    return audio, {k: (None if isinstance(v, float) and not np.isfinite(v) else v)
                   for k, v in report.items()}


def options_from(data: dict, default_brake: bool = True) -> dict:
    """Read loudness options from a request / config dict."""
    data = data or {}
    adjust = data.get('adjust', 'none')
    if adjust not in ('none', 'source', 'target'):
        adjust = 'none'
    target = data.get('target_lufs')
    if isinstance(target, str):
        target = TARGETS.get(target, target)
    try:
        target = float(target) if target is not None else None
    except (TypeError, ValueError):
        target = None
    if adjust == 'target' and target is None:
        target = TARGETS['streaming']
    return {'adjust': adjust, 'target_lufs': target,
            'use_brake': bool(data.get('brake', default_brake))}
