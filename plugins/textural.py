"""Penderecki: Textural — a restless, aleatoric cluster (Polymorphia style).

The same band as Cluster (every semitone or quarter tone across
`cluster_width`), but every voice is unstable: each jumps to a new random
detune (up to ±`detune_cents`) about every 250 ms, with a short glide, and
swells and fades on its own (`swell`). In stereo the voices are scattered at
random across the field, as wide as `spread`.
"""
import numpy as np
from plugins import plugin_rng, frames_io
from plugins import _cluster
from src.stretch import steps_to_curve

NAME     = "Penderecki: Textural"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_textural"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "cluster_width": {"label": "band width st", "type": "int",   "min": 1, "max": 12,  "default": 4},
    "step":          {"label": "step", "type": "select", "options": ["semitone", "quarter tone"], "default": "semitone"},
    "detune_cents":  {"label": "detune cents",  "type": "float", "min": 0, "max": 100, "default": 25},
    "swell":         {"label": "swell %",       "type": "float", "min": 0, "max": 100, "default": 50},
    "spread":        {"label": "stereo spread %", "type": "float", "min": 0, "max": 100, "default": 80},
    "dry_wet":       {"label": "dry/wet %",     "type": "float", "min": 0, "max": 100, "default": 80},
}

_JUMP_EVERY  = 0.25   # s between a voice's random detunes
_JUMP_GLIDE  = 0.06   # s glide into each new detune
_SWELL_EVERY = 0.4    # s between a voice's level targets


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    width  = float(params.get("cluster_width", 4))
    step   = str(params.get("step", "semitone"))
    detune = float(params.get("detune_cents", 25)) / 100.0
    swell  = float(params.get("swell", 50)) / 100.0
    spread = float(params.get("spread", 80)) / 100.0
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    n = len(audio)
    if n == 0:
        return back(audio)
    rng = plugin_rng()
    offsets = _cluster.band(width, step)
    nv = len(offsets)

    jump = max(1, int(_JUMP_EVERY * sr))
    n_j = -(-n // jump) + 1
    pitch = [steps_to_curve(rng.uniform(-detune, detune, n_j), jump, n, glide=int(_JUMP_GLIDE * sr))
             if detune > 0 else None for _ in range(nv)]

    sw = max(1, int(_SWELL_EVERY * sr))
    n_s = -(-n // sw) + 1
    gains = [steps_to_curve(rng.uniform(1.0 - swell, 1.0, n_s), sw, n) if swell > 0 else None
             for _ in range(nv)]

    pans = rng.uniform(-spread, spread, nv)        # scattered

    wet = _cluster.render(audio, sr, offsets, pitch, gains, pans)
    return back(audio * (1.0 - dw) + wet * dw)
