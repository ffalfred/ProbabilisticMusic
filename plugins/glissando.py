"""Penderecki: Glissando — linear pitch slides spanning each segment."""
import numpy as np
from src.dsp import ola_blocks

NAME     = "Penderecki: Glissando"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_glissando"

PARAMS = {
    "gliss_range": {"label": "gliss range st", "type": "int",   "min": 1,   "max": 24,  "default": 12},
    "n_steps":     {"label": "steps",          "type": "int",   "min": 3,   "max": 10,  "default": 5},
    "dry_wet":     {"label": "dry/wet %",      "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    gliss_range = int(params.get("gliss_range", 12))
    n_steps     = max(3, int(params.get("n_steps", 5)))
    dw          = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    seg_len = max(1024, int(0.2 * sr))  # one sweep every ~200 ms
    sub_len = seg_len // n_steps

    # Pitch sweep: linearly from -gliss_range/2 → +gliss_range/2 over n_steps
    # sub-steps, repeating every segment.
    shifts = np.linspace(-gliss_range / 2, gliss_range / 2, n_steps)

    def _step(k, sub):
        st = float(shifts[k % n_steps])
        try:
            return librosa.effects.pitch_shift(sub, sr=sr, n_steps=st)
        except Exception:
            return sub

    # Overlapping windows crossfade adjacent steps (butted steps crackle).
    wet = ola_blocks(audio, 2 * sub_len, _step)

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
