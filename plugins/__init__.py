"""Plugin auto-discovery and dispatch for Morphogenics processors."""
import importlib
import os

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
        except Exception:
            pass
    return _registry


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
        return clip
    # Resolve concrete param values from fx dict (use plugin defaults for missing keys)
    params = {}
    for key, spec in mod.PARAMS.items():
        raw = fx.get(key, spec.get("default"))
        params[key] = raw

    import numpy as np
    original  = clip.copy() if hasattr(clip, 'copy') else clip
    processed = mod.process(clip, sr, params)

    # Band-limit the effect when the plugin has frequency-range params
    if "low_hz" in mod.PARAMS or "high_hz" in mod.PARAMS:
        low_hz  = float(params.get("low_hz")  or 0)
        high_hz = float(params.get("high_hz") or sr / 2)
        return _band_blend(original, processed, sr, low_hz, high_hz)

    return processed
