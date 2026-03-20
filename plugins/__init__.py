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


def apply_plugin(clip, sr: int, fx: dict):
    """Dispatch an FX dict with type starting with 'morpho_' to the matching plugin."""
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
    return mod.process(clip, sr, params)
