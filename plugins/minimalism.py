"""Desyatnikov: Minimalism — every Nth onset segment displaced by a sharp quote interval (polystylistic)."""
import numpy as np

NAME     = "Minimalism"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_minimalism"

PARAMS = {
    "nth_onset":      {"label": "every N onsets", "type": "int",   "min": 2,  "max": 8,  "default": 4},
    "quote_interval": {"label": "quote interval", "type": "float", "min": 1,  "max": 12, "default": 6},
    "dry_wet":        {"label": "dry/wet %",       "type": "float", "min": 0,  "max": 100,"default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    nth      = int(params.get("nth_onset", 4))
    interval = float(params.get("quote_interval", 6))
    dw       = float(params.get("dry_wet", 80)) / 100.0

    audio = clip.astype(np.float32)

    onsets = librosa.onset.onset_detect(y=audio, sr=sr, units="samples")
    if len(onsets) < 1:
        return audio

    boundaries = list(onsets) + [len(audio)]
    wet = audio.copy()

    for i in range(len(onsets)):
        if (i % nth) != 0:
            continue
        i0 = int(boundaries[i])
        i1 = int(boundaries[i + 1])
        seg = audio[i0:i1]
        if len(seg) < 32:
            continue
        try:
            shifted = librosa.effects.pitch_shift(seg, sr=sr, n_steps=float(interval))
        except Exception:
            continue
        if len(shifted) > len(seg):
            shifted = shifted[:len(seg)]
        elif len(shifted) < len(seg):
            shifted = np.pad(shifted, (0, len(seg) - len(shifted)))
        wet[i0:i1] = shifted

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
