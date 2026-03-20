"""Wagner: Tristan — overlay Tristan chord (4:5:6:7 just-intonation) on every Nth onset segment."""
import numpy as np

NAME     = "Wagner: Tristan"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_wagner_tristan"

PARAMS = {
    "tristan_interval": {"label": "every N onsets", "type": "int",   "min": 2,  "max": 8,  "default": 3},
    "chord_gain_db":    {"label": "chord gain dB",  "type": "float", "min": -24,"max": -6, "default": -12},
    "dry_wet":          {"label": "dry/wet %",       "type": "float", "min": 0,  "max": 100,"default": 80},
}

# Tristan chord in semitones above detected F0: F–B–D#–G# ~ 0, 6, 10, 14
# Using just-intonation ratios 4:5:6:7 expressed in semitones
_TRISTAN_ST = [0.0, 3.86, 7.02, 9.69]  # just-intonation 4:5:6:7


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    nth        = int(params.get("tristan_interval", 3))
    gain_db    = float(params.get("chord_gain_db", -12))
    dw         = float(params.get("dry_wet", 80)) / 100.0

    audio      = clip.astype(np.float32)
    chord_gain = 10 ** (gain_db / 20.0)

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

        chord_layer = np.zeros(len(seg), dtype=np.float32)
        for st in _TRISTAN_ST:
            try:
                voice = librosa.effects.pitch_shift(seg, sr=sr, n_steps=float(st))
            except Exception:
                voice = seg.copy()
            if len(voice) > len(seg):
                voice = voice[:len(seg)]
            elif len(voice) < len(seg):
                voice = np.pad(voice, (0, len(seg) - len(voice)))
            chord_layer += voice

        chord_layer *= (chord_gain / len(_TRISTAN_ST))
        wet[i0:i1] += chord_layer

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
