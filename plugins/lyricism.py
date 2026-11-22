"""Desyatnikov: Lyricism — shadow the line with two parallel non-functional intervals.

Two transposed copies of the sound run alongside it, by default a major 7th
(+11 st) and a perfect 11th (+17 st) above, which colour the line without
implying functional harmony. Both intervals and the side (above / below) can
be set; interval 2 = 0 switches the second voice off.
"""
import numpy as np
from plugins import frames_io
from src.stretch import pitch_shift, parallel_map

NAME     = "Desyatnikov: Lyricism"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_lyricism"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "interval_1":   {"label": "interval 1 st",   "type": "int",    "min": 1,   "max": 24, "default": 11},
    "interval_2":   {"label": "interval 2 st (0 = off)", "type": "int", "min": 0, "max": 24, "default": 17},
    "placement":    {"label": "placement", "type": "select", "options": ["above", "below"], "default": "above"},
    "harm_gain_db": {"label": "harmony gain dB", "type": "float",  "min": -24, "max": -6, "default": -18},
    "dry_wet":      {"label": "dry/wet %",        "type": "float",  "min": 0,   "max": 100,"default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    sign         = -1.0 if str(params.get("placement", "above")) == "below" else 1.0
    intervals    = [int(params.get("interval_1", 11)), int(params.get("interval_2", 17))]
    shifts       = [sign * float(i) for i in intervals if i > 0]
    harm_gain_db = float(params.get("harm_gain_db", -18))
    dw           = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    harm_gain = 10 ** (harm_gain_db / 20.0)

    wet = audio.copy()
    for layer in parallel_map(lambda st: pitch_shift(audio, sr, st), shifts):
        wet = wet + layer * harm_gain

    return back(audio * (1.0 - dw) + wet * dw)
