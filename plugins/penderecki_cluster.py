"""Penderecki: Cluster — dense pitch-cluster chords (Threnody style)."""
import numpy as np

NAME     = "Penderecki: Cluster"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_penderecki_cluster"

PARAMS = {
    "cluster_width": {"label": "cluster width", "type": "int",   "min": 1,   "max": 12,  "default": 4},
    "n_voices":      {"label": "voices",         "type": "int",   "min": 2,   "max": 8,   "default": 4},
    "dry_wet":       {"label": "dry/wet %",      "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    width  = int(params.get("cluster_width", 4))
    voices = int(params.get("n_voices", 4))
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio = clip.astype(np.float32)
    wet   = np.zeros_like(audio)

    for v in range(voices):
        st = -width / 2 + v * width / max(voices - 1, 1)
        try:
            layer = librosa.effects.pitch_shift(audio, sr=sr, n_steps=float(st))
        except Exception:
            continue
        min_len = min(len(wet), len(layer))
        wet[:min_len] += layer[:min_len] / voices

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
