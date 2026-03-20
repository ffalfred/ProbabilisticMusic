"""Spectral: Smooth — blur magnitude spectrum across frequency bins (spectral envelope smoothing)."""
import numpy as np

NAME     = "Spectral: Smooth"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_spectral_smooth"

PARAMS = {
    "smooth_bins": {"label": "smooth bins", "type": "int",   "min": 1, "max": 10, "default": 3},
    "dry_wet":     {"label": "dry/wet %",   "type": "float", "min": 0, "max": 100,"default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa
    from scipy.ndimage import uniform_filter1d

    smooth = int(params.get("smooth_bins", 3))
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio  = clip.astype(np.float32)
    n_fft  = 2048
    hop    = 512

    D      = librosa.stft(audio, n_fft=n_fft, hop_length=hop)
    mag    = np.abs(D)
    phase  = np.angle(D)

    # Smooth magnitude along frequency axis (axis=0)
    size   = max(1, smooth * 2 + 1)
    smooth_mag = uniform_filter1d(mag, size=size, axis=0, mode="reflect")

    D_new  = smooth_mag * np.exp(1j * phase)
    y_new  = librosa.istft(D_new, hop_length=hop, length=len(audio))

    return (audio * (1.0 - dw) + y_new * dw).astype(np.float32)
