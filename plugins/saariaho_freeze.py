"""Saariaho: Spectral Freeze — sustain top-N partials via STFT with slow phase evolution."""
import numpy as np

NAME     = "Saariaho: Spectral Freeze"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_saariaho_freeze"

PARAMS = {
    "n_partials":  {"label": "partials",    "type": "int",   "min": 5,    "max": 50,  "default": 20},
    "freeze_rate": {"label": "freeze rate", "type": "float", "min": 0.01, "max": 1.0, "default": 0.1},
    "dry_wet":     {"label": "dry/wet %",   "type": "float", "min": 0,    "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    n_partials  = int(params.get("n_partials", 20))
    freeze_rate = float(params.get("freeze_rate", 0.1))
    dw          = float(params.get("dry_wet", 80)) / 100.0

    audio  = clip.astype(np.float32)
    n_fft  = 2048
    hop    = 512

    D      = librosa.stft(audio, n_fft=n_fft, hop_length=hop)
    mag    = np.abs(D)
    phase  = np.angle(D)
    n_bins, n_frames = D.shape

    # Keep only top-N partials per frame
    frozen_mag = np.zeros_like(mag)
    for f in range(n_frames):
        frame_mag = mag[:, f]
        top_idx   = np.argpartition(frame_mag, -n_partials)[-n_partials:]
        frozen_mag[top_idx, f] = frame_mag[top_idx]

    # Advance phase slowly (freeze_rate 1.0 = natural, 0.0 = frozen)
    phase_increment = 2 * np.pi * np.arange(n_bins).reshape(-1, 1) / n_fft
    new_phase = phase.copy()
    for f in range(1, n_frames):
        new_phase[:, f] = new_phase[:, f - 1] + phase_increment * freeze_rate

    D_frozen = frozen_mag * np.exp(1j * new_phase)
    y_frozen = librosa.istft(D_frozen, hop_length=hop, length=len(audio))

    return (audio * (1.0 - dw) + y_frozen * dw).astype(np.float32)
