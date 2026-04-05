"""Saariaho: Microtonal — detune by ±cents driven by spectral brightness of the source."""
import numpy as np

NAME     = "Microtonal"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_microtonal"

PARAMS = {
    "max_cents": {"label": "max cents",  "type": "float", "min": 0,   "max": 50,  "default": 25},
    "dry_wet":   {"label": "dry/wet %", "type": "float", "min": 0,   "max": 100, "default": 100},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    max_cents = float(params.get("max_cents", 25))
    dw        = float(params.get("dry_wet", 100)) / 100.0

    if max_cents < 0.5:
        return clip.astype(np.float32)

    audio = clip.astype(np.float32)

    # Spectral centroid → brightness measure
    centroid      = librosa.feature.spectral_centroid(y=audio, sr=sr)
    mean_centroid = float(np.mean(centroid))

    # Normalize to [-1, 1]: 500 Hz = −1 (dark/flat), 5000 Hz = +1 (bright/sharp)
    normalized = float(np.clip((mean_centroid - 500) / (5000 - 500) * 2 - 1, -1.0, 1.0))

    detune_semitones = normalized * max_cents / 100.0
    if abs(detune_semitones) < 0.001:
        return audio

    wet = librosa.effects.pitch_shift(audio, sr=sr, n_steps=float(detune_semitones))
    if len(wet) > len(audio):
        wet = wet[:len(audio)]
    elif len(wet) < len(audio):
        wet = np.pad(wet, (0, len(audio) - len(wet)))

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
