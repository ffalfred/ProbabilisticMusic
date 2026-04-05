"""Penderecki: Aleatoric — controlled random pitch displacement per segment (Devil's Staircase style)."""
import numpy as np

NAME     = "Aleatoric"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_aleatoric"

PARAMS = {
    "detune_cents": {"label": "detune cents", "type": "float", "min": 0,   "max": 100, "default": 25},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    detune = float(params.get("detune_cents", 25)) / 100.0  # convert cents → semitones
    dw     = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    wet     = np.zeros_like(audio)
    rng     = np.random.default_rng()
    seg_len = max(sr // 4, 1024)  # ~250 ms segments
    n_segs  = max(1, (len(audio) + seg_len - 1) // seg_len)

    for s in range(n_segs):
        i0  = s * seg_len
        i1  = min(i0 + seg_len, len(audio))
        seg = audio[i0:i1]
        shift = float(rng.uniform(-detune, detune))
        if abs(shift) < 0.02:
            wet[i0:i1] += seg
            continue
        try:
            shifted = librosa.effects.pitch_shift(seg, sr=sr, n_steps=shift)
        except Exception:
            wet[i0:i1] += seg
            continue
        min_len = min(i1 - i0, len(shifted))
        wet[i0:i0 + min_len] += shifted[:min_len]

    peak = np.max(np.abs(wet))
    if peak > 1.0:
        wet /= peak

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
