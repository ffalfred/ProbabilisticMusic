"""Spectral: Harmonic Stretch — stretch or squeeze the spacing of the partials.

Partial n of a sound with fundamental f0 moves from n·f0 to f0·n^β, with
β = log2(octave_ratio): the "octave" between partial 1 and 2 becomes
octave_ratio instead of 2 (2.0 = unchanged), and higher partials are pushed
out (or pulled in) progressively, like a stretched piano tuning or a bell.
The fundamental stays where it is. Partials are moved one by one with their
phases kept continuous, so the result is clean rather than phasey.
"""
import numpy as np
from plugins import frames_io, mono
from src.spectral import warp_partials, median_f0

NAME     = "Spectral: Harmonic Stretch"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_harmonic_stretch"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "octave_ratio": {"label": "octave ratio", "type": "float", "min": 1.5, "max": 3.0,  "default": 2.2},
    "pivot_hz":     {"label": "pivot Hz (0 = auto)", "type": "float", "min": 0, "max": 2000, "default": 0},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100,  "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    ratio = float(params.get("octave_ratio", 2.2))
    pivot = float(params.get("pivot_hz", 0))
    dw    = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    if abs(ratio - 2.0) < 1e-3:
        return back(audio)
    if pivot <= 0:
        pivot = median_f0(mono(audio), sr) or 220.0     # the sound's own fundamental
    beta = np.log2(ratio)
    warp = lambda f: pivot * (np.maximum(f, 1e-3) / pivot) ** beta
    wet = np.stack([warp_partials(audio[:, c], sr, warp) for c in range(audio.shape[1])], axis=1)
    return back(audio * (1.0 - dw) + wet * dw)
