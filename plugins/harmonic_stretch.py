"""Spectral: Harmonic Stretch — scale upper partials outward by stretch_ratio via bin remapping."""
import numpy as np

NAME     = "Spectral: Harmonic Stretch"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_harmonic_stretch"

PARAMS = {
    "stretch_ratio": {"label": "stretch ratio", "type": "float", "min": 0.5, "max": 4.0, "default": 1.5},
    "dry_wet":       {"label": "dry/wet %",     "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa
    from scipy.ndimage import map_coordinates

    ratio = float(params.get("stretch_ratio", 1.5))
    dw    = float(params.get("dry_wet", 80)) / 100.0

    audio  = clip.astype(np.float32)
    n_fft  = 2048
    hop    = 512

    D      = librosa.stft(audio, n_fft=n_fft, hop_length=hop)
    mag    = np.abs(D)
    phase  = np.angle(D)
    n_bins, n_frames = D.shape

    # Remap each bin index: bin k → k / ratio (squeeze high freqs toward low)
    # or k * ratio (stretch high freqs outward). We stretch outward.
    src_bins = np.arange(n_bins, dtype=np.float32) / ratio
    src_bins = np.clip(src_bins, 0, n_bins - 1)

    coords = np.tile(src_bins[:, np.newaxis], (1, n_frames))
    frame_idx = np.tile(np.arange(n_frames, dtype=np.float32)[np.newaxis, :], (n_bins, 1))

    new_mag = map_coordinates(mag, [coords, frame_idx], order=1, mode="constant", cval=0.0)

    # Preserve original phase (no phase adjustment for bin remapping)
    D_new  = new_mag * np.exp(1j * phase)
    y_new  = librosa.istft(D_new, hop_length=hop, length=len(audio))

    return (audio * (1.0 - dw) + y_new * dw).astype(np.float32)
