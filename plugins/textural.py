"""Penderecki: Textural — layered clusters + aleatoric detune (Polymorphia style)."""
import numpy as np
from plugins import plugin_rng
from src.dsp import ola_blocks

NAME     = "Penderecki: Textural"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_textural"

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
    rng   = plugin_rng()

    # Cluster layer
    for v in range(voices):
        st = -width / 2 + v * width / max(voices - 1, 1)
        try:
            layer = librosa.effects.pitch_shift(audio, sr=sr, n_steps=float(st))
        except Exception:
            continue
        min_len = min(len(wet), len(layer))
        wet[:min_len] += layer[:min_len] / voices * 0.6

    # Aleatoric layer: a new random detune every ~250 ms, crossfaded via
    # overlapping windows so segment changes don't click.
    seg_len = max(sr // 4, 1024)

    def _detune(k, seg):
        shift = float(rng.uniform(-detune, detune))
        if abs(shift) < 0.02:
            return np.zeros_like(seg)
        try:
            return librosa.effects.pitch_shift(seg, sr=sr, n_steps=shift)
        except Exception:
            return np.zeros_like(seg)

    wet += ola_blocks(audio, 2 * seg_len, _detune) * 0.4

    peak = np.max(np.abs(wet))
    if peak > 1.0:
        wet /= peak

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
