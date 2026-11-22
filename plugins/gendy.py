"""Xenakis: GENDY — dynamic stochastic synthesis (GENDYN) and two effects built on it.

Xenakis's GENDYN draws a waveform through breakpoints whose heights and
spacings take second-order random walks (a random walk whose step size is
itself a random walk), each held between reflecting barriers. `randomness`
scales the walks.

Modes:
- input (default): the walks act on the input itself. At breakpoints every
  ~`grain_ms`, the read position drifts ahead or behind and the level dips,
  joined by straight lines, so the original is squeezed, stretched and
  re-levelled continuously: it turns grainy and unstable, without clicks.
- synth: a real GENDYN oscillator with `breakpoints` points per period,
  around `pitch_hz` (0 = the input's own pitch), following the input's
  loudness. It adds a new sound; balance it with dry/wet.
- envelope: only the level walks (smoothly, between breakpoints): a
  stochastic tremolo, the gentlest mode.
"""
import numpy as np
from plugins import plugin_rng, frames_io, mono

NAME     = "Xenakis: GENDY"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_gendy"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "mode":        {"label": "mode", "type": "select", "options": ["input", "synth", "envelope"], "default": "input"},
    "randomness":  {"label": "randomness %", "type": "float", "min": 0,  "max": 100,  "default": 30},
    "grain_ms":    {"label": "breakpoint ms (input/envelope)", "type": "float", "min": 2, "max": 50, "default": 20},
    "breakpoints": {"label": "breakpoints / period (synth)",   "type": "int",   "min": 4, "max": 32, "default": 12},
    "pitch_hz":    {"label": "pitch Hz (synth, 0 = auto)",     "type": "float", "min": 0, "max": 2000, "default": 0},
    "spread":      {"label": "stereo spread %", "type": "float", "min": 0, "max": 100, "default": 50},
    "dry_wet":     {"label": "dry/wet %", "type": "float", "min": 0, "max": 100, "default": 80},
}


def _mirror(x, lo, hi):
    """Reflect x back into [lo, hi] (Xenakis's elastic barriers)."""
    w = hi - lo
    if w <= 0:
        return np.full_like(np.asarray(x, dtype=np.float64), lo)
    y = np.mod(np.asarray(x, dtype=np.float64) - lo, 2 * w)
    return lo + np.where(y > w, 2 * w - y, y)


def _step(rng, scale, size=None):
    """Cauchy steps (heavy-tailed, as in GENDYN), clipped to ±3·scale."""
    return np.clip(rng.standard_cauchy(size) * scale, -3 * scale, 3 * scale)


def _walk2(rng, n, lo, hi, x0, step):
    """n values of a second-order random walk between barriers lo..hi."""
    vmax = (hi - lo) / 4
    v, x = 0.0, x0
    out = np.empty(n)
    for i in range(n):
        v = float(_mirror(v + _step(rng, step), -vmax, vmax))
        x = float(_mirror(x + v, lo, hi))
        out[i] = x
    return out


def _breakpoint_times(rng, n_samples, spacing, r):
    """Breakpoint positions whose spacing itself random-walks around `spacing`."""
    n = int(n_samples / spacing * 1.6) + 4
    d = _walk2(rng, n, spacing / (1 + r), spacing * (1 + r), spacing, spacing * r * 0.2)
    t = np.concatenate([[0.0], np.cumsum(d)])
    return t[:np.searchsorted(t, n_samples) + 1]


def _input_curves(rng, n, sr, r, grain_ms):
    """Per-sample read-position offset and level for the input mode."""
    spacing = max(2.0, grain_ms * sr / 1000)
    t = _breakpoint_times(rng, n, spacing, r)
    max_off = r * spacing                     # read head up to ±1 breakpoint away
    off = _walk2(rng, len(t), -max_off, max_off, 0.0, max_off * 0.3)
    off[0] = 0.0
    amp = _walk2(rng, len(t), 1.0 - r, 1.0, 1.0, r * 0.15)
    k = np.arange(n)
    return np.interp(k, t, off), np.interp(k, t, amp)


def _envelope_curve(rng, n, sr, r, grain_ms):
    spacing = max(2.0, grain_ms * sr / 1000)
    t = _breakpoint_times(rng, n, spacing, r)
    amp = _walk2(rng, len(t), 1.0 - r, 1.0, 1.0, r * 0.2)
    return np.interp(np.arange(n), t, amp)


def _gendyn_wave(rng, n_samples, sr, r, n_bp, pitch_hz):
    """A GENDYN waveform, DC removed, at unit RMS."""
    from scipy.signal import butter, sosfilt
    d0 = sr / (pitch_hz * n_bp)                         # nominal breakpoint spacing
    d_lo, d_hi = d0 * 2 ** (-r), d0 * 2 ** r            # pitch range ±r octaves
    dur = np.full(n_bp, d0)
    amp = rng.uniform(-1, 1, n_bp) * 0.5
    v_dur = np.zeros(n_bp)
    v_amp = np.zeros(n_bp)
    out = []
    total = 0
    while total < n_samples:
        # Second-order walks for every breakpoint, once per period
        v_dur = _mirror(v_dur + _step(rng, 0.05 * d0 * r + 1e-9, n_bp), -(d_hi - d_lo) / 4, (d_hi - d_lo) / 4)
        dur = _mirror(dur + v_dur, max(d_lo, 1.0), max(d_hi, 1.0))
        v_amp = _mirror(v_amp + _step(rng, 0.05 * r + 1e-9, n_bp), -0.5, 0.5)
        amp = _mirror(amp + v_amp, -1.0, 1.0)
        t = np.concatenate([[0.0], np.cumsum(dur)])
        n = max(1, int(t[-1]))
        out.append(np.interp(np.arange(n), t, np.append(amp, amp[0])))
        total += n
    y = np.concatenate(out)[:n_samples]
    y = sosfilt(butter(2, 20, btype='high', fs=sr, output='sos'), y)     # remove DC
    return y / (float(np.sqrt(np.mean(y ** 2))) or 1.0)


def _loudness(x, sr):
    """50 ms RMS envelope of a 1-D signal."""
    w = max(1, int(0.05 * sr))
    return np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(w) / w, mode='same'))


def _blend(common, own, s):
    """Each channel's walk: the shared one, moved towards its own by `s`."""
    return [common if o is None else (1 - s) * common + s * o for o in own]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    mode     = str(params.get("mode", "input"))
    r        = float(np.clip(float(params.get("randomness", 30)) / 100.0, 0.0, 1.0))
    grain_ms = float(params.get("grain_ms", 20))
    n_bp     = max(4, int(params.get("breakpoints", 12)))
    pitch_hz = float(params.get("pitch_hz", 0))
    spread   = float(params.get("spread", 50)) / 100.0
    dw       = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    n, n_ch = audio.shape
    if n == 0:
        return back(audio)
    rng = plugin_rng()
    # Stereo: each side also gets its own walks (drawn after the shared ones,
    # so a mono render is unchanged), blended in by `spread`
    stereo = n_ch == 2 and spread > 0
    wet = np.empty_like(audio)
    k = np.arange(n)

    if mode == "synth":
        if pitch_hz <= 0:
            from src.spectral import median_f0
            pitch_hz = median_f0(mono(audio), sr) or 110.0
        common = _gendyn_wave(rng, n, sr, r, n_bp, pitch_hz)
        own = [_gendyn_wave(rng, n, sr, r, n_bp, pitch_hz) for _ in range(n_ch)] if stereo else [None] * n_ch
        for c, y in enumerate(_blend(common, own, spread)):
            y = y / (float(np.sqrt(np.mean(y ** 2))) or 1.0)
            wet[:, c] = y * _loudness(audio[:, c], sr)       # follow the input's loudness
    elif mode == "envelope":
        common = _envelope_curve(rng, n, sr, r, grain_ms)
        own = [_envelope_curve(rng, n, sr, r, grain_ms) for _ in range(n_ch)] if stereo else [None] * n_ch
        for c, amp in enumerate(_blend(common, own, spread)):
            wet[:, c] = audio[:, c] * amp
    else:
        off, amp = _input_curves(rng, n, sr, r, grain_ms)
        own = [_input_curves(rng, n, sr, r, grain_ms) for _ in range(n_ch)] if stereo else [None] * n_ch
        offs = _blend(off, [o[0] for o in own] if stereo else own, spread)
        amps = _blend(amp, [o[1] for o in own] if stereo else own, spread)
        for c in range(n_ch):
            wet[:, c] = np.interp(k + offs[c], k, audio[:, c], left=0.0, right=0.0) * amps[c]
    return back(audio * (1.0 - dw) + wet * dw)
