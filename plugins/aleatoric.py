"""Penderecki: Aleatoric — controlled random pitch displacement per segment (Devil's Staircase style)."""
import numpy as np
from plugins import plugin_rng, frames_io
from src.stretch import pitch_shift, steps_to_curve

NAME     = "Penderecki: Aleatoric"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_aleatoric"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "detune_cents": {"label": "detune cents", "type": "float", "min": 0,   "max": 100, "default": 25},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    detune = float(params.get("detune_cents", 25)) / 100.0  # convert cents → semitones
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    rng     = plugin_rng()
    seg_len = max(sr // 4, 1024)  # a new random detune every ~250 ms

    # One random detune per segment, joined by glides into one pitch curve
    # that a single Rubber Band pass follows.
    n_seg = -(-len(audio) // seg_len)
    shifts = rng.uniform(-detune, detune, n_seg)
    wet = pitch_shift(audio, sr, steps_to_curve(shifts, seg_len, len(audio)))

    peak = np.max(np.abs(wet))
    if peak > 1.0:
        wet /= peak

    return back(audio * (1.0 - dw) + wet * dw)
