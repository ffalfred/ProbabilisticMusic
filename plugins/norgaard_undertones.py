"""Nørgaard: Undertones — add synthetic undertones below the fundamental (Per Nørgaard)."""
import numpy as np

NAME     = "Nørgaard: Undertones"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_norgaard_undertones"

PARAMS = {
    "n_undertones": {"label": "undertones", "type": "int",   "min": 1,   "max": 8,   "default": 3},
    "gain_db":      {"label": "gain dB",    "type": "float", "min": -24, "max": 0,   "default": -12},
    "dry_wet":      {"label": "dry/wet %",  "type": "float", "min": 0,   "max": 100, "default": 80},
}

# Undertone intervals below the fundamental (semitones down)
_UNDERTONE_STEPS = [12, 19, 24, 28, 31, 34, 36]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    n        = int(params.get("n_undertones", 3))
    gain_db  = float(params.get("gain_db", -12))
    dw       = float(params.get("dry_wet", 80)) / 100.0
    gain_lin = 10.0 ** (gain_db / 20.0)
    steps    = _UNDERTONE_STEPS[:n]

    audio = clip.astype(np.float32)
    wet   = audio.copy()

    for i, s in enumerate(steps):
        try:
            under = librosa.effects.pitch_shift(audio, sr=sr, n_steps=-float(s))
        except Exception:
            continue
        h_gain  = gain_lin / (i + 1)
        min_len = min(len(wet), len(under))
        wet[:min_len] += under[:min_len] * h_gain

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
