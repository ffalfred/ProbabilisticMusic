"""Desyatnikov: Minimalism — every Nth onset segment displaced by a sharp quote interval (polystylistic)."""
import numpy as np
from src.dsp import splice
from plugins import frames_io, mono
from src.stretch import pitch_shift

NAME     = "Desyatnikov: Minimalism"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_minimalism"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

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

    audio, back = frames_io(clip)

    onsets = librosa.onset.onset_detect(y=mono(audio), sr=sr, units="samples")
    if len(onsets) < 1:
        return back(audio)

    boundaries = list(onsets) + [len(audio)]
    wet = audio.copy()
    # Shift the whole clip once and cut the quotes out of it: one Rubber Band
    # call instead of one per segment, and every quote has full context.
    shifted_all = pitch_shift(audio, sr, interval)

    for i in range(len(onsets)):
        if (i % nth) != 0:
            continue
        i0 = int(boundaries[i])
        i1 = int(boundaries[i + 1])
        if i1 - i0 < 32:
            continue
        # Crossfade the quote in and out
        splice(wet, i0, shifted_all[i0:i1], int(0.01 * sr))

    return back(audio * (1.0 - dw) + wet * dw)
