"""Automation: effect settings that change over time.

Any numeric effect setting can be a curve instead of a number:

    - type: filter
      cutoff: {curve: [[0, 200], [2, 3000], [5, 400]]}   # [seconds, value] points

Times are seconds from the start of the audio the effect processes (the
event's sound, the FX zone, the track, or the whole output). Between points
the value moves in a straight line; before the first and after the last it
holds.

Exact (each sample gets its own value):
- reverb, delay: `dry`, `wet` — delay's wet is a send level: echoes keep
  the level they were sent at;
- every Morphogenics effect: `dry_wet`;
- filter: `cutoff`, `resonance` (coefficients updated every 64 samples);
- tremolo: `rate`, `depth`;
- pitch: `semitones` / `cents` (Rubber Band follows the pitch curve).
Everything else is approximated: the effect is rendered with the settings
it has at a series of moments along the curves (every point, plus extra
moments so they are ≤ 0.25 s apart, at most MAX_RENDERS), and the output
moves smoothly from one render to the next. That costs one render per
moment, and a sweep sounds like a blend of renders rather than one moving
setting.
"""
import numpy as np

from src.dsp import as_frames, pad_frames

MAX_RENDERS = 12
MAX_GAP_S = 0.25
FILTER_BLOCK = 64

NATIVE = {
    'reverb':  {'dry', 'wet'},
    'delay':   {'dry', 'wet'},
    'filter':  {'cutoff', 'resonance'},
    'tremolo': {'rate', 'depth'},
    'pitch':   {'semitones', 'cents'},
}


def is_curve(v) -> bool:
    return isinstance(v, dict) and isinstance(v.get('curve'), (list, tuple)) and len(v['curve']) > 0


def has_curves(fx: dict) -> bool:
    return any(is_curve(v) for k, v in fx.items() if k != 'type')


def points(v) -> np.ndarray:
    """A curve's points as an (n, 2) float array sorted by time."""
    p = np.array([[float(t), float(x)] for t, x in v['curve']], dtype=np.float64)
    return p[np.argsort(p[:, 0], kind='stable')]


def values(v, n: int, sr: int) -> np.ndarray:
    """A setting at every sample of n (curve or plain number)."""
    if not is_curve(v):
        return np.full(n, float(v), dtype=np.float64)
    p = points(v)
    return np.interp(np.arange(n) / sr, p[:, 0], p[:, 1])


def at(v, t: float):
    """A setting's value at time t (curve or plain value)."""
    if not is_curve(v):
        return v
    p = points(v)
    return float(np.interp(t, p[:, 0], p[:, 1]))


def static(fx: dict, t: float = 0.0) -> dict:
    """The effect with every curve replaced by its value at time t."""
    return {k: (at(v, t) if is_curve(v) else v) for k, v in fx.items()}


def apply(clip: np.ndarray, sr: int, fx: dict, apply_one) -> np.ndarray:
    """Apply an effect whose settings may be curves. apply_one(clip, sr, fx)
    applies an effect with fixed settings."""
    clip = as_frames(clip)
    curved = {k for k, v in fx.items() if k != 'type' and is_curve(v)}
    kind = fx.get('type', '')
    native = NATIVE.get(kind) or ({'dry_wet'} if kind.startswith('morpho_') else set())
    if curved and curved <= native:
        return _NATIVE_FN[kind if kind in _NATIVE_FN else 'morpho'](clip, sr, fx, apply_one)
    return _morph(clip, sr, fx, apply_one)


# ─── Exact automation ────────────────────────────────────────────────────────

def _reverb(clip, sr, fx, apply_one):
    from src.fx import reverb_wet
    n = len(clip)
    wet = reverb_wet(clip, sr, static(fx))
    wet_c = np.clip(values(fx.get('wet', 0.5), len(wet), sr), 0, 1)
    dry_c = np.clip(values(fx.get('dry', 1.0), n, sr), 0, 1)
    out = wet * wet_c[:, None].astype(np.float32)
    out[:n] += clip * dry_c[:, None].astype(np.float32)
    return out.astype(np.float32)


def _delay(clip, sr, fx, apply_one):
    from src.fx import _resolve
    time = float(np.clip(_resolve(fx.get('time', fx.get('delay_sec', 0.3)), 0.3), 0.01, 4.0))
    fb = float(np.clip(_resolve(fx.get('feedback', 0.6), 0.6), 0.0, 0.95))
    n = len(clip)
    d = int(round(time * sr))
    dry_c = np.clip(values(fx.get('dry', 1.0), n, sr), 0, 1)
    wet_c = np.clip(values(fx.get('wet', 0.5), n, sr), 0, 1)
    gains, g = [], float(wet_c.max())
    while g >= 1e-3 and len(gains) * time < 30.0:
        gains.append(fb ** len(gains))
        g *= fb
        if fb <= 0:
            break
    out = np.zeros((n + d * len(gains), clip.shape[1]), dtype=np.float32)
    out[:n] = clip * dry_c[:, None]
    send = clip * wet_c[:, None].astype(np.float32)        # echoes keep the level they were sent at
    for k, gk in enumerate(gains, start=1):
        out[k * d:k * d + n] += send * gk
    return out


def _filter(clip, sr, fx, apply_one):
    from scipy.signal import butter, sosfilt
    n = len(clip)
    cut = np.clip(values(fx.get('cutoff', 1000), n, sr), 20, sr / 2 - 1)
    res = np.clip(values(fx.get('resonance', 0), n, sr), 0, 1)
    ftype = str(fx.get('filter_type', fx.get('type_', 'lp'))).lower()
    btype = {'lp': 'low', 'hp': 'high', 'bp': 'band', 'lowpass': 'low',
             'highpass': 'high', 'bandpass': 'band'}.get(ftype, 'low')

    if btype != 'band':
        # resonant low/high pass, smooth sweeps (src/resfilter.py)
        from src.resfilter import resonant_filter
        return resonant_filter(clip, sr, cut, res, btype, block=FILTER_BLOCK)

    def sos_at(i):
        c, q = cut[i], 0.5 + res[i] * 11.5
        bw = c * 0.3 / max(q, 0.5)
        return butter(2, [max(20, c - bw), min(sr / 2 - 1, c + bw)], btype='band', fs=sr, output='sos')

    out = np.empty_like(clip, dtype=np.float32)
    zi = None
    for s in range(0, n, FILTER_BLOCK):
        e = min(n, s + FILTER_BLOCK)
        sos = sos_at((s + e) // 2)
        if zi is None:
            zi = np.zeros((sos.shape[0], 2, clip.shape[1]))
        y, zi = sosfilt(sos, clip[s:e], axis=0, zi=zi)
        out[s:e] = y
    return out


def _tremolo(clip, sr, fx, apply_one):
    n = len(clip)
    rate = np.clip(values(fx.get('rate', 5.0), n, sr), 0.1, 30)
    depth = np.clip(values(fx.get('depth', 0.5), n, sr), 0.0, 1.0)
    phase = 2 * np.pi * np.concatenate([[0.0], np.cumsum(rate[:-1])]) / sr
    mod = 1.0 - depth * 0.5 * (1 + np.sin(phase))
    return (clip * mod[:, None]).astype(np.float32)


def _pitch(clip, sr, fx, apply_one):
    from src.stretch import pitch_shift
    n = len(clip)
    if fx.get('semitones') is not None:
        st = values(fx['semitones'], n, sr)
    else:
        st = values(fx.get('cents', 0), n, sr) / 100.0
    return pitch_shift(clip, sr, np.clip(st, -24, 24))


def _morpho_dry_wet(clip, sr, fx, apply_one):
    wet = as_frames(apply_one(clip, sr, dict(static(fx), dry_wet=100)))
    n = max(len(wet), len(clip))
    dw = np.clip(values(fx['dry_wet'], n, sr), 0, 100)[:, None] / 100.0
    return (pad_frames(clip, n) * (1 - dw) + pad_frames(wet, n) * dw).astype(np.float32)


_NATIVE_FN = {'reverb': _reverb, 'delay': _delay, 'filter': _filter,
              'tremolo': _tremolo, 'pitch': _pitch, 'morpho': _morpho_dry_wet}


# ─── Approximate automation: blend renders taken along the curves ───────────

def _moments(fx: dict, dur: float, n_ch: int, n: int) -> np.ndarray:
    """When to render: every curve point inside the clip, its start and end,
    and extra moments so none are more than MAX_GAP_S apart — at most
    MAX_RENDERS (fewer for very long audio, to bound memory)."""
    limit = int(np.clip(400e6 / max(1, n * n_ch * 4), 2, MAX_RENDERS))
    ts = {0.0, dur}
    for v in fx.values():
        if is_curve(v):
            ts.update(float(t) for t in points(v)[:, 0] if 0.0 < t < dur)
    ts = sorted(ts)
    if len(ts) > limit:
        ts = list(np.linspace(0.0, dur, limit))
    while len(ts) < limit:
        gaps = np.diff(ts)
        i = int(np.argmax(gaps))
        if gaps[i] <= MAX_GAP_S:
            break
        ts.insert(i + 1, (ts[i] + ts[i + 1]) / 2)
    return np.array(ts)


def _morph(clip, sr, fx, apply_one):
    from src.rand import rng
    n = len(clip)
    ts = _moments(fx, n / sr, clip.shape[1], n)
    r = rng()
    state = r.get_state()
    renders = []
    for t in ts:
        r.set_state(state)                 # every render makes the same random choices
        renders.append(as_frames(apply_one(clip, sr, static(fx, t))))
    L = max(len(x) for x in renders)
    renders = [pad_frames(x, L) for x in renders]
    # Weight of each render at every sample: a straight line from one moment
    # to the next; after the last moment, the last render
    tt = np.arange(L) / sr
    out = np.zeros_like(renders[0])
    for k, x in enumerate(renders):
        w = np.interp(tt, ts, np.eye(len(ts))[k])
        if k == len(ts) - 1:
            w[tt >= ts[-1]] = 1.0
        nz = w > 0
        if nz.any():
            out[nz] += x[nz] * w[nz, None].astype(np.float32)
    return out.astype(np.float32)
