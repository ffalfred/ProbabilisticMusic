"""Plugin auto-discovery and dispatch for Morphogenics processors."""
import importlib
import os
import sys

_PLUGIN_DIR = os.path.dirname(__file__)

# Maps type_key -> module
_registry: dict = {}


def load_plugins() -> dict:
    """Discover and return all plugin modules keyed by their type key."""
    global _registry
    if _registry:
        return _registry
    for fname in sorted(os.listdir(_PLUGIN_DIR)):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        mod_name = fname[:-3]
        try:
            mod = importlib.import_module(f"plugins.{mod_name}")
            if hasattr(mod, "NAME") and hasattr(mod, "PARAMS") and hasattr(mod, "process"):
                type_key = getattr(mod, "TYPE_KEY", f"morpho_{mod_name}")
                _registry[type_key] = mod
        except Exception as e:
            print(f"[plugins] skipping {mod_name}: {e}", file=sys.stderr)
    return _registry


def plugin_rng():
    """Random generator for plugins, drawn from the global numpy state so a
    render seeded with seed_everything() is reproducible."""
    import numpy as np
    from src.rand import rng
    return np.random.default_rng(rng().randint(0, 2**31 - 1))


def frames_io(clip):
    """A plugin's input as float32 (frames, channels), plus a function that
    returns a (frames, channels) result in the input's own layout (1-D in,
    1-D out). Lets STEREO plugins also be called directly on mono arrays."""
    import numpy as np
    x = np.asarray(clip, dtype=np.float32)
    if x.ndim == 1:
        return x[:, None], lambda y: np.asarray(y, dtype=np.float32)[:, 0]
    return x, lambda y: np.asarray(y, dtype=np.float32)


def mono(x):
    """Mono sum of a (frames, channels) signal, for analysis (onsets, pitch,
    brightness), so every channel follows the same decisions."""
    return x.mean(axis=1) if x.ndim == 2 else x


def pan_gains(pos: float, n_ch: int):
    """Equal-power balance gains for a position from -1 (left) to +1 (right).
    Centre is (1, 1), hard left (√2, 0): the total power stays the same.
    Mono signals are not panned."""
    import numpy as np
    if n_ch != 2:
        return np.ones(n_ch, dtype=np.float32)
    a = (float(np.clip(pos, -1, 1)) + 1) * np.pi / 4
    return np.array([np.cos(a), np.sin(a)], dtype=np.float32) * np.sqrt(2)


def _band_blend(original, processed, sr: int, low_hz: float, high_hz: float):
    """Keep `processed` inside [low_hz, high_hz] and `original` outside.

    This ensures that frequencies outside the plugin's target band pass through
    at full amplitude — the plugin effect is band-limited.
    """
    import numpy as np
    try:
        from scipy.signal import butter, sosfilt
    except ImportError:
        return processed  # fallback: no band isolation
    nyq = sr / 2.0
    low  = max(1.0, float(low_hz  or 0))
    high = min(nyq * 0.999, float(high_hz or nyq))
    n = min(len(original), len(processed))
    orig_n = original[:n].copy()
    proc_n = processed[:n].copy()
    try:
        if low > 5.0 and high < nyq * 0.95:
            sos_bp = butter(4, [low / nyq, high / nyq], btype='band',     output='sos')
            sos_bs = butter(4, [low / nyq, high / nyq], btype='bandstop', output='sos')
            inside  = sosfilt(sos_bp, proc_n, axis=0)
            outside = sosfilt(sos_bs, orig_n, axis=0)
        elif low > 5.0:  # high-pass only
            sos_hp = butter(4, low / nyq, btype='high', output='sos')
            sos_lp = butter(4, low / nyq, btype='low',  output='sos')
            inside  = sosfilt(sos_hp, proc_n, axis=0)
            outside = sosfilt(sos_lp, orig_n, axis=0)
        else:             # low-pass only
            sos_lp = butter(4, high / nyq, btype='low',  output='sos')
            sos_hp = butter(4, high / nyq, btype='high', output='sos')
            inside  = sosfilt(sos_lp, proc_n, axis=0)
            outside = sosfilt(sos_hp, orig_n, axis=0)
    except Exception:
        return processed
    result = (inside + outside).astype(np.float32)
    # Preserve any extra length the plugin may have added
    if len(original) > n:
        result = np.concatenate([result, original[n:]])
    return result


_warned = set()   # unknown types already reported (once per run)


def apply_plugin(clip, sr: int, fx: dict):
    """Dispatch an FX dict with type starting with 'morpho_' to the matching plugin.

    When the plugin defines ``low_hz`` / ``high_hz`` parameters (frequency band),
    the plugin effect is automatically band-limited: processed audio is kept only
    inside [low_hz, high_hz] and the original passes through at full amplitude
    outside that band.
    """
    plugins = load_plugins()
    t = fx.get("type", "")
    mod = plugins.get(t)
    if mod is None:
        if t not in _warned:
            _warned.add(t)
            print(f"[plugins] unknown effect type '{t}' — left out. "
                  f"Known: {', '.join(sorted(plugins))}", file=sys.stderr)
        return clip
    # Resolve concrete param values from fx dict (use plugin defaults for missing
    # keys). Ranges / distributions are drawn here, since fx outside events are
    # not resolved by the score parser.
    from src.parser import _resolve
    params = {}
    for key, spec in mod.PARAMS.items():
        params[key] = _resolve(fx.get(key, spec.get("default")))

    # STEREO plugins get all channels at once (frames, channels): they analyse
    # the mono sum, shift channels together and can place voices in the
    # stereo field. Others are mono and run per channel; per_channel replays
    # the same random draws, so both sides match.
    from src.dsp import as_frames, per_channel
    original  = as_frames(clip).copy()
    if getattr(mod, "STEREO", False):
        processed = as_frames(mod.process(original.copy(), sr, params))
    else:
        processed = per_channel(lambda c: mod.process(c, sr, params), original)

    # Band-limit the effect when the plugin has frequency-range params
    if "low_hz" in mod.PARAMS or "high_hz" in mod.PARAMS:
        low_hz  = float(params.get("low_hz")  or 0)
        high_hz = float(params.get("high_hz") or sr / 2)
        return _band_blend(original, processed, sr, low_hz, high_hz)

    return processed
