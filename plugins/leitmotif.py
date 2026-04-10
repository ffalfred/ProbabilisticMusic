"""Wagner: Leitmotif — onset-segmented motifs, each transposed and optionally time-stretched + repeated."""
import numpy as np

NAME     = "Wagner: Leitmotif"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_leitmotif"

PARAMS = {
    "transpose_range": {"label": "transpose range st", "type": "float", "min": 0,  "max": 12, "default": 7},
    "repetitions":     {"label": "repetitions",         "type": "int",   "min": 1,  "max": 3,  "default": 2},
    "dry_wet":         {"label": "dry/wet %",            "type": "float", "min": 0,  "max": 100,"default": 80},
}

_STRETCH_CHOICES = [0.75, 1.0, 1.25]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    trans_range  = float(params.get("transpose_range", 7))
    repetitions  = int(params.get("repetitions", 2))
    dw           = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    rng     = np.random.default_rng()
    onsets  = librosa.onset.onset_detect(y=audio, sr=sr, units="samples")

    if len(onsets) < 1:
        return audio

    boundaries = list(onsets) + [len(audio)]
    wet = np.zeros_like(audio)

    for i in range(len(onsets)):
        i0 = int(boundaries[i])
        i1 = int(boundaries[i + 1])
        seg = audio[i0:i1]
        if len(seg) < 32:
            wet[i0:i1] += seg
            continue

        # Random transpose and time-stretch
        n_steps = float(rng.uniform(-trans_range, trans_range))
        stretch = float(rng.choice(_STRETCH_CHOICES))

        try:
            transformed = librosa.effects.pitch_shift(seg, sr=sr, n_steps=n_steps)
            if abs(stretch - 1.0) > 0.01:
                transformed = librosa.effects.time_stretch(transformed, rate=stretch)
        except Exception:
            transformed = seg

        # Tile and truncate to segment boundary
        seg_len = i1 - i0
        if repetitions > 1 and len(transformed) > 0:
            tiled = np.tile(transformed, repetitions)[:seg_len]
        else:
            tiled = transformed[:seg_len]

        if len(tiled) < seg_len:
            tiled = np.pad(tiled, (0, seg_len - len(tiled)))

        wet[i0:i1] += tiled

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
