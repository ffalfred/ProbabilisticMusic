"""Penderecki: Cluster — a band of every semitone (or quarter tone), each voice alive.

Like the string clusters of Threnody: the sound is copied onto every step
across `cluster_width`, centred on its own pitch. Each voice drifts slowly
and independently by up to ±`drift_cents`, so the band shimmers and beats
instead of sounding like a harmoniser. Voices can enter one by one, in
random order, over `entry_s`. In stereo they are laid out across the field
from low (left) to high (right), as wide as `spread`.
"""
import numpy as np
from plugins import plugin_rng, frames_io
from plugins import _cluster
from src.stretch import steps_to_curve

NAME     = "Penderecki: Cluster"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_cluster"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "cluster_width": {"label": "band width st", "type": "int",   "min": 1, "max": 24,  "default": 4},
    "step":          {"label": "step", "type": "select", "options": ["semitone", "quarter tone"], "default": "semitone"},
    "drift_cents":   {"label": "drift cents",   "type": "float", "min": 0, "max": 50,  "default": 10},
    "entry_s":       {"label": "entries over s (0 = together)", "type": "float", "min": 0, "max": 10, "default": 0},
    "spread":        {"label": "stereo spread %", "type": "float", "min": 0, "max": 100, "default": 60},
    "dry_wet":       {"label": "dry/wet %",     "type": "float", "min": 0, "max": 100, "default": 80},
}

_DRIFT_EVERY = 0.7    # s between a voice's drift targets (it glides between them)
_ENTRY_RAMP  = 0.3    # s for a voice to fade in when it enters


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    width   = float(params.get("cluster_width", 4))
    step    = str(params.get("step", "semitone"))
    drift   = float(params.get("drift_cents", 10)) / 100.0
    entry_s = float(params.get("entry_s", 0))
    spread  = float(params.get("spread", 60)) / 100.0
    dw      = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    n = len(audio)
    if n == 0:
        return back(audio)
    rng = plugin_rng()
    offsets = _cluster.band(width, step)
    nv = len(offsets)

    # Slow independent drift per voice
    hop = max(1, int(_DRIFT_EVERY * sr))
    n_pts = -(-n // hop) + 1
    pitch = [steps_to_curve(rng.uniform(-drift, drift, n_pts), hop, n) if drift > 0 else None
             for _ in range(nv)]

    # Staggered entries, in random order
    gains = [None] * nv
    if entry_s > 0 and nv > 1:
        order = rng.permutation(nv)
        t = np.arange(n) / sr
        for rank, i in enumerate(order):
            start = rank / (nv - 1) * entry_s
            gains[i] = np.clip((t - start) / _ENTRY_RAMP, 0.0, 1.0)

    # Low voices left, high voices right
    pans = np.linspace(-spread, spread, nv) if nv > 1 else np.zeros(1)

    wet = _cluster.render(audio, sr, offsets, pitch, gains, pans)
    return back(audio * (1.0 - dw) + wet * dw)
