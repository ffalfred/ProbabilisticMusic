"""Spectral: Inharmonic — shift partials to inharmonic ratios (×1.3, ×2.7, ×4.5)."""
import numpy as np

NAME     = "Spectral: Inharmonic"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_inharmonic"

PARAMS = {
    "inharmonic_factor": {"label": "inharmonic factor", "type": "float", "min": 1.0, "max": 3.0, "default": 1.5},
    "dry_wet":           {"label": "dry/wet %",          "type": "float", "min": 0,   "max": 100, "default": 80},
}

# Fixed inharmonic ratio offsets (fractional multipliers relative to factor)
_RATIOS = [1.0, 1.3, 2.7, 4.5]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa
    from scipy.ndimage import map_coordinates

    factor = float(params.get("inharmonic_factor", 1.5))
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio  = clip.astype(np.float32)
    n_fft  = 2048
    hop    = 512

    D      = librosa.stft(audio, n_fft=n_fft, hop_length=hop)
    mag    = np.abs(D)
    phase  = np.angle(D)
    n_bins, n_frames = D.shape

    wet_mag = np.zeros_like(mag)
    frame_idx = np.tile(np.arange(n_frames, dtype=np.float32)[np.newaxis, :], (n_bins, 1))

    for r in _RATIOS:
        effective = r * factor
        src_bins  = np.arange(n_bins, dtype=np.float32) / effective
        src_bins  = np.clip(src_bins, 0, n_bins - 1)
        coords    = np.tile(src_bins[:, np.newaxis], (1, n_frames))
        layer_mag = map_coordinates(mag, [coords, frame_idx], order=1, mode="constant", cval=0.0)
        wet_mag  += layer_mag / len(_RATIOS)

    D_new = wet_mag * np.exp(1j * phase)
    y_new = librosa.istft(D_new, hop_length=hop, length=len(audio))

    return (audio * (1.0 - dw) + y_new * dw).astype(np.float32)
