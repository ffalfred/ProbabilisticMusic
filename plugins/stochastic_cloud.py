"""Xenakis: Stochastic Cloud — dense probabilistically generated sine-burst clusters."""
import numpy as np

NAME     = "Xenakis: Stochastic Cloud"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_stochastic_cloud"

PARAMS = {
    "density":  {"label": "notes/sec", "type": "float", "min": 10,  "max": 200, "default": 80},
    "low_hz":   {"label": "low Hz",   "type": "float", "min": 50,  "max": 2000, "default": 200},
    "high_hz":  {"label": "high Hz",  "type": "float", "min": 500, "max": 8000, "default": 3000},
    "grain_ms": {"label": "grain ms", "type": "float", "min": 5,   "max": 30,   "default": 10},
    "dry_wet":  {"label": "dry/wet %","type": "float", "min": 0,   "max": 100,  "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    density  = float(params.get("density", 80))
    low_hz   = float(params.get("low_hz", 200))
    high_hz  = float(params.get("high_hz", 3000))
    grain_ms = float(params.get("grain_ms", 10))
    dw       = float(params.get("dry_wet", 80)) / 100.0

    audio     = clip.astype(np.float32)
    dur       = len(audio) / sr
    n_grains  = max(1, int(density * dur))
    grain_len = max(32, int(grain_ms * sr / 1000))
    rng       = np.random.default_rng()

    # Use log-uniform frequency distribution (equal density per octave)
    log_low  = np.log(max(low_hz, 1.0))
    log_high = np.log(max(high_hz, low_hz + 1.0))

    wet = np.zeros_like(audio)
    for _ in range(n_grains):
        onset = int(rng.uniform(0, max(1, len(audio) - grain_len)))
        freq  = float(np.exp(rng.uniform(log_low, log_high)))
        amp   = float(rng.uniform(0.05, 0.20))
        t     = np.arange(grain_len) / sr
        grain = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        grain *= np.hanning(grain_len).astype(np.float32)
        end   = min(onset + grain_len, len(wet))
        wet[onset:end] += grain[:end - onset]

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
