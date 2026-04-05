"""Xenakis: GENDY — Weibull-distributed amplitude envelope with abrupt mathematically-derived cuts."""
import numpy as np

NAME     = "GENDY"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_gendy"

PARAMS = {
    "weibull_shape": {"label": "Weibull shape", "type": "float", "min": 0.5, "max": 5.0, "default": 1.5},
    "grain_ms":      {"label": "grain ms",      "type": "float", "min": 5,   "max": 50,  "default": 20},
    "dry_wet":       {"label": "dry/wet %",     "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    shape    = float(params.get("weibull_shape", 1.5))
    grain_ms = float(params.get("grain_ms", 20))
    dw       = float(params.get("dry_wet", 80)) / 100.0

    audio     = clip.astype(np.float32)
    grain_len = max(32, int(grain_ms * sr / 1000))
    n_grains  = max(1, (len(audio) + grain_len - 1) // grain_len)

    rng     = np.random.default_rng()
    weights = rng.weibull(shape, n_grains)
    w_max   = float(np.max(weights)) if np.max(weights) > 0 else 1.0
    weights = (weights / w_max).astype(np.float32)

    # Build sample-level step envelope from per-grain weights
    envelope = np.ones(len(audio), dtype=np.float32)
    for gi in range(n_grains):
        i0 = gi * grain_len
        i1 = min(i0 + grain_len, len(audio))
        envelope[i0:i1] = weights[gi]

    wet = audio * envelope
    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
