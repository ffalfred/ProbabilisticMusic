"""Penderecki: Glissando Sweeps — the pitch sweeps up through each ~200 ms segment, again and again.

(Displayed as "Glissando" before; the type key morpho_glissando is unchanged.)"""
import numpy as np
from plugins import frames_io
from src.stretch import pitch_shift, steps_to_curve

NAME     = "Penderecki: Glissando Sweeps"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_glissando"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "gliss_range": {"label": "gliss range st", "type": "int",   "min": 1,   "max": 24,  "default": 12},
    "n_steps":     {"label": "steps",          "type": "int",   "min": 3,   "max": 10,  "default": 5},
    "dry_wet":     {"label": "dry/wet %",      "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    gliss_range = int(params.get("gliss_range", 12))
    n_steps     = max(3, int(params.get("n_steps", 5)))
    dw          = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    seg_len = max(1024, int(0.2 * sr))  # one sweep every ~200 ms
    sub_len = seg_len // n_steps

    # Pitch sweep: linearly from -gliss_range/2 → +gliss_range/2 over n_steps
    # sub-steps, repeating every segment.
    shifts = np.linspace(-gliss_range / 2, gliss_range / 2, n_steps)

    # The repeating sweep as one pitch curve, gliding between steps, followed
    # by a single Rubber Band pass.
    n_sub = -(-len(audio) // sub_len)
    values = shifts[np.arange(n_sub) % n_steps]
    wet = pitch_shift(audio, sr, steps_to_curve(values, sub_len, len(audio)))

    return back(audio * (1.0 - dw) + wet * dw)
