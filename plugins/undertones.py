"""Nørgaard: Undertones — add synthetic undertones below the fundamental (Per Nørgaard)."""
import numpy as np
from plugins import frames_io
from src.stretch import pitch_shift, parallel_map

NAME     = "Nørgaard: Undertones"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_undertones"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "n_undertones": {"label": "undertones", "type": "int",   "min": 1,   "max": 8,   "default": 3},
    "gain_db":      {"label": "gain dB",    "type": "float", "min": -24, "max": 0,   "default": -12},
    "dry_wet":      {"label": "dry/wet %",  "type": "float", "min": 0,   "max": 100, "default": 80},
}

# The undertone series: f/2, f/3, … f/8, as exact intervals below the sound
# (12·log2 n semitones: 12, 19.02, 24, 27.86, 31.02, 33.69, 36). They used to
# be rounded to semitones, which put 1/5, 1/6 and 1/7 up to 31 cents off.
_UNDERTONE_STEPS = [float(12 * np.log2(n)) for n in range(2, 9)]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:

    n        = int(params.get("n_undertones", 3))
    gain_db  = float(params.get("gain_db", -12))
    dw       = float(params.get("dry_wet", 80)) / 100.0
    gain_lin = 10.0 ** (gain_db / 20.0)
    steps    = _UNDERTONE_STEPS[:n]

    audio, back = frames_io(clip)
    wet   = audio.copy()

    # 50 ms fades soften the start and end of each pitch-shifted layer.
    fade_n = max(1, int(0.05 * sr))

    # Low-pass the layers at ~3 kHz: undertones sit below the fundamental, so
    # this keeps them dark and out of the way of the original's top end.
    from scipy.signal import butter, sosfilt
    nyq = sr / 2.0
    lp_cutoff = min(3000.0 / nyq, 0.95)
    lp_sos = butter(4, lp_cutoff, btype='low', output='sos')

    layers = parallel_map(lambda s: pitch_shift(audio, sr, -float(s)), steps)
    for i, under in enumerate(layers):
        under = sosfilt(lp_sos, under, axis=0).astype(np.float32)
        if len(under) > fade_n * 2:
            ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)[:, None]
            under[:fade_n]  *= ramp
            under[-fade_n:] *= ramp[::-1]
        h_gain  = gain_lin / (i + 1)
        min_len = min(len(wet), len(under))
        wet[:min_len] += under[:min_len] * h_gain

    return back(audio * (1.0 - dw) + wet * dw)
