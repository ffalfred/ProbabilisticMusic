"""Nørgaard: Undertones — add synthetic undertones below the fundamental (Per Nørgaard)."""
import numpy as np

NAME     = "Nørgaard: Undertones"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_undertones"

PARAMS = {
    "n_undertones": {"label": "undertones", "type": "int",   "min": 1,   "max": 8,   "default": 3},
    "gain_db":      {"label": "gain dB",    "type": "float", "min": -24, "max": 0,   "default": -12},
    "dry_wet":      {"label": "dry/wet %",  "type": "float", "min": 0,   "max": 100, "default": 80},
}

# Undertone intervals below the fundamental (semitones down)
_UNDERTONE_STEPS = [12, 19, 24, 28, 31, 34, 36]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    n        = int(params.get("n_undertones", 3))
    gain_db  = float(params.get("gain_db", -12))
    dw       = float(params.get("dry_wet", 80)) / 100.0
    gain_lin = 10.0 ** (gain_db / 20.0)
    steps    = _UNDERTONE_STEPS[:n]

    audio = clip.astype(np.float32)
    wet   = audio.copy()

    # Fade window (50ms) to mask phase artifacts at the start/end of each
    # pitch-shifted layer. librosa.pitch_shift produces audible clicks at
    # boundaries especially for large shifts (>24 semitones).
    fade_n = max(1, int(0.05 * sr))

    # Pre-compute a low-pass filter to remove high-frequency artifacts from
    # the pitch shifter. Undertones are below the fundamental, so anything
    # above ~3 kHz is pitch-shift garbage (clicking/grain), not signal.
    from scipy.signal import butter, sosfilt
    nyq = sr / 2.0
    lp_cutoff = min(3000.0 / nyq, 0.95)
    lp_sos = butter(4, lp_cutoff, btype='low', output='sos')

    for i, s in enumerate(steps):
        try:
            # n_fft=4096 gives better frequency resolution for large pitch
            # shifts, reducing phase-vocoder artifacts that sound like crackle.
            under = librosa.effects.pitch_shift(
                audio, sr=sr, n_steps=-float(s), n_fft=4096,
            )
        except Exception:
            continue
        # Low-pass to strip HF pitch-shift artifacts (the click/grain noise).
        under = sosfilt(lp_sos, under).astype(np.float32)
        # Apply fade-in/out to mask onset/offset clicks from the pitch shifter
        if len(under) > fade_n * 2:
            under[:fade_n]  *= np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
            under[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
        h_gain  = gain_lin / (i + 1)
        min_len = min(len(wet), len(under))
        wet[:min_len] += under[:min_len] * h_gain

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
