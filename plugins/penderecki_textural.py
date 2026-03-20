"""Penderecki: Textural — layered clusters + aleatoric detune (Polymorphia style)."""
import numpy as np

NAME     = "Penderecki: Textural"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_penderecki_textural"

PARAMS = {
    "cluster_width": {"label": "cluster width", "type": "int",   "min": 1,   "max": 12,  "default": 4},
    "n_voices":      {"label": "voices",         "type": "int",   "min": 2,   "max": 8,   "default": 4},
    "detune_cents":  {"label": "detune cents",   "type": "float", "min": 0,   "max": 100, "default": 25},
    "dry_wet":       {"label": "dry/wet %",      "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    width  = int(params.get("cluster_width", 4))
    voices = int(params.get("n_voices", 4))
    detune = float(params.get("detune_cents", 25)) / 100.0
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio = clip.astype(np.float32)
    wet   = np.zeros_like(audio)
    rng   = np.random.default_rng()

    # Cluster layer
    for v in range(voices):
        st = -width / 2 + v * width / max(voices - 1, 1)
        try:
            layer = librosa.effects.pitch_shift(audio, sr=sr, n_steps=float(st))
        except Exception:
            continue
        min_len = min(len(wet), len(layer))
        wet[:min_len] += layer[:min_len] / voices * 0.6

    # Aleatoric layer over ~250ms segments
    seg_len = max(sr // 4, 1024)
    n_segs  = max(1, (len(audio) + seg_len - 1) // seg_len)
    for s in range(n_segs):
        i0  = s * seg_len
        i1  = min(i0 + seg_len, len(audio))
        seg = audio[i0:i1]
        shift = float(rng.uniform(-detune, detune))
        if abs(shift) < 0.02:
            continue
        try:
            shifted = librosa.effects.pitch_shift(seg, sr=sr, n_steps=shift)
        except Exception:
            continue
        min_len = min(i1 - i0, len(shifted))
        wet[i0:i0 + min_len] += shifted[:min_len] * 0.4

    peak = np.max(np.abs(wet))
    if peak > 1.0:
        wet /= peak

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
