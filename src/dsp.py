"""DSP helpers shared by the engine and plugins.

- Channel layout helpers: the engine's (frames, channels) convention.
- Piecewise processing: butting processed pieces together leaves a waveform
  discontinuity at every seam, which is heard as a click. splice / fade_edges
  join pieces with crossfades / fades instead. They work on 1-D signals and
  on (frames, channels) arrays.
"""
import numpy as np


# ─── Channel layout ──────────────────────────────────────────────────────────
# Inside the engine all audio is 2-D, shape (frames, channels), channels 1 or 2
# — the layout soundfile reads and writes. Envelopes and ramps stay 1-D
# (frames,) and are applied with env_mul, never `x * env`: an (n, 1) array
# times an (n,) array broadcasts to (n, n). Likewise use pad_frames, never
# np.pad(x, (0, k)), which on 2-D audio also pads the channel axis.

def as_frames(x) -> np.ndarray:
    """Return x as float32 (frames, channels); 1-D input becomes one channel.
    May return x itself or a view of it (as can to_channels) — copy before
    modifying in place."""
    x = np.asarray(x, dtype=np.float32)
    return x[:, None] if x.ndim == 1 else x


def to_channels(x: np.ndarray, channels: int) -> np.ndarray:
    """Match a channel count: mono is copied to every channel, more channels
    than wanted keep the first ones (L/R of a surround file), stereo → mono
    averages."""
    x = as_frames(x)
    c = x.shape[1]
    if c == channels:
        return x
    if c == 1:
        return np.repeat(x, channels, axis=1)
    if channels == 1:
        return x[:, :2].mean(axis=1, keepdims=True)
    return x[:, :channels]


def pad_frames(x: np.ndarray, n: int) -> np.ndarray:
    """Zero-pad along time to at least n frames."""
    if len(x) >= n:
        return x
    return np.pad(x, [(0, n - len(x))] + [(0, 0)] * (x.ndim - 1))


def fit_frames(x: np.ndarray, n: int) -> np.ndarray:
    """Trim or zero-pad along time to exactly n frames."""
    return pad_frames(x[:n], n)


def env_mul(x: np.ndarray, env) -> np.ndarray:
    """Multiply audio by a per-frame envelope (1-D, same length as x or a
    scalar) — the safe way to apply gains to (frames, channels) audio."""
    env = np.asarray(env, dtype=np.float32)
    if env.ndim == 1 and x.ndim == 2:
        env = env[:, None]
    return (x * env).astype(np.float32)


def per_channel(fn, x) -> np.ndarray:
    """Apply a mono function fn(1-D) -> mono to every channel of x.

    The numpy random state is restored before each channel, so randomised
    processing (plugins, random fx parameters) makes the same choices on
    both sides and the global random stream advances exactly as for mono —
    stereo and mono renders of one seed stay in step.
    """
    x = as_frames(x)
    if x.shape[1] == 1:
        return as_frames(fn(np.ascontiguousarray(x[:, 0])))
    from src.rand import rng
    r = rng()
    state = r.get_state()
    outs = []
    for c in range(x.shape[1]):
        r.set_state(state)
        # fn may return 1-D or a one-channel (frames, 1) array
        outs.append(as_frames(fn(np.ascontiguousarray(x[:, c])))[:, 0])
    n = max(len(o) for o in outs)
    return np.stack([np.pad(o, (0, n - len(o))) for o in outs], axis=1)


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
    if old.ndim == 2:
        mix = mix[:, None]
    dst[i0:i0 + n] = old * (1.0 - mix) + new * mix


def fade_edges(x: np.ndarray, n_fade: int) -> np.ndarray:
    """Return a copy of x with short linear fades at both ends."""
    x = x.astype(np.float32).copy()
    f = min(int(n_fade), len(x) // 2)
    if f > 1:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        if x.ndim == 2:
            ramp = ramp[:, None]
        x[:f] *= ramp
        x[-f:] *= ramp[::-1]
    return x
