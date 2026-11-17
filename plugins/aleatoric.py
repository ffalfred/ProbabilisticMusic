"""Penderecki: Aleatoric — controlled random pitch displacement per segment (Devil's Staircase style)."""
import numpy as np
from plugins import plugin_rng
from src.dsp import ola_blocks

NAME     = "Penderecki: Aleatoric"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_aleatoric"

PARAMS = {
    "detune_cents": {"label": "detune cents", "type": "float", "min": 0,   "max": 100, "default": 25},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    detune = float(params.get("detune_cents", 25)) / 100.0  # convert cents → semitones
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    rng     = plugin_rng()
    seg_len = max(sr // 4, 1024)  # a new random detune every ~250 ms

    def _detune(k, seg):
        shift = float(rng.uniform(-detune, detune))
        if abs(shift) < 0.02:
            return seg
        try:
            return librosa.effects.pitch_shift(seg, sr=sr, n_steps=shift)
        except Exception:
            return seg

    # Overlapping windowed segments, so detune changes crossfade instead of clicking.
    wet = ola_blocks(audio, 2 * seg_len, _detune)

    peak = np.max(np.abs(wet))
    if peak > 1.0:
        wet /= peak

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
