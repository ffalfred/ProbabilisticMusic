"""Desyatnikov: Lyricism — add non-functional harmonies (maj7 +11 st, dim11 +17 st) under the melodic line."""
import numpy as np

NAME     = "Desyatnikov: Lyricism"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_desyatnikov_lyricism"

PARAMS = {
    "harm_gain_db": {"label": "harmony gain dB", "type": "float", "min": -24, "max": -6, "default": -18},
    "dry_wet":      {"label": "dry/wet %",        "type": "float", "min": 0,   "max": 100,"default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    harm_gain_db = float(params.get("harm_gain_db", -18))
    dw           = float(params.get("dry_wet", 80)) / 100.0

    audio     = clip.astype(np.float32)
    harm_gain = 10 ** (harm_gain_db / 20.0)

    # maj7 = +11 semitones, dim11 = +17 semitones
    wet = audio.copy()
    for n_steps in (11.0, 17.0):
        try:
            layer = librosa.effects.pitch_shift(audio, sr=sr, n_steps=n_steps)
        except Exception:
            continue
        if len(layer) > len(audio):
            layer = layer[:len(audio)]
        elif len(layer) < len(audio):
            layer = np.pad(layer, (0, len(audio) - len(layer)))
        wet = wet + layer * harm_gain

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
