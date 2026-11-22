"""Spectral: Inharmonic — frequency shift: add the same number of Hz to every partial.

A harmonic sound has partials at f0, 2·f0, 3·f0, ... Shifting all of them by
the same amount (say +100 Hz) breaks those whole-number ratios, so the sound
turns metallic and bell-like, the classic frequency-shifter (Bode) effect.
Small shifts (a few Hz) give slow beating and phasing; negative shifts pull
partials down, and those pushed below 0 Hz fold back up.
Done exactly with the analytic signal (Hilbert transform): no smearing.
"""
import numpy as np
from plugins import frames_io

NAME     = "Spectral: Inharmonic"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_inharmonic"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "shift_hz": {"label": "shift Hz",  "type": "float", "min": -1000, "max": 1000, "default": 100},
    "dry_wet":  {"label": "dry/wet %", "type": "float", "min": 0,     "max": 100,  "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    from scipy.signal import hilbert

    shift = float(params.get("shift_hz", 100))
    dw    = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    if abs(shift) < 1e-3 or len(audio) == 0:
        return back(audio)
    pad = 4096                                   # keeps the FFT's wrap-around off the ends
    analytic = hilbert(np.pad(audio.astype(np.float64), ((pad, pad), (0, 0))), axis=0)[pad:pad + len(audio)]
    t = np.arange(len(audio))[:, None] / sr
    wet = np.real(analytic * np.exp(2j * np.pi * shift * t)).astype(np.float32)
    return back(audio * (1.0 - dw) + wet * dw)
