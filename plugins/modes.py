"""Messiaen: Modes — sliding-window pitch quantization to Messiaen's modes of limited transposition."""
import numpy as np

NAME     = "Modes"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_modes"

# Standard musicologically correct Messiaen modes (semitone intervals within octave)
_MODES = {
    "1": [0, 2, 4, 6, 8, 10],           # whole-tone
    "2": [0, 1, 3, 4, 6, 7, 9, 10],     # octatonic (half-whole)
    "3": [0, 2, 3, 4, 6, 7, 8, 10, 11],
    "4": [0, 1, 2, 5, 6, 7, 8, 11],
    "5": [0, 1, 5, 6, 7, 11],
    "6": [0, 2, 4, 5, 6, 8, 10, 11],
    "7": [0, 1, 2, 3, 5, 6, 7, 8, 9, 11],
}

PARAMS = {
    "mode":       {"label": "mode",      "type": "select", "options": ["1","2","3","4","5","6","7"], "default": "2"},
    "root_hz":    {"label": "root Hz",   "type": "float",  "min": 20,  "max": 2000, "default": 440},
    "window_sec": {"label": "window s",  "type": "float",  "min": 0.1, "max": 2.0,  "default": 0.5},
    "dry_wet":    {"label": "dry/wet %", "type": "float",  "min": 0,   "max": 100,  "default": 100},
}


def _snap_shift(f0: float, root_hz: float, pitch_classes: list) -> float:
    """Return semitones needed to snap f0 to the nearest pitch class in the mode."""
    semitones_from_root = 12 * np.log2(f0 / root_hz)
    pc_raw = semitones_from_root % 12
    nearest_pc = min(pitch_classes,
                     key=lambda pc: min(abs(pc_raw - pc), 12 - abs(pc_raw - pc)))
    shift = nearest_pc - pc_raw
    if shift > 6:
        shift -= 12
    elif shift < -6:
        shift += 12
    return shift


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    mode_key      = str(params.get("mode", "2"))
    root_hz       = float(params.get("root_hz", 440))
    window_sec    = float(params.get("window_sec", 0.5))
    dw            = float(params.get("dry_wet", 100)) / 100.0
    pitch_classes = _MODES.get(mode_key, _MODES["2"])

    audio   = clip.astype(np.float32)
    win_len = max(512, int(window_sec * sr))
    hop_len = win_len // 2

    wet  = np.zeros_like(audio)
    norm = np.zeros_like(audio)

    for i0 in range(0, len(audio), hop_len):
        i1     = min(i0 + win_len, len(audio))
        window = audio[i0:i1]
        if len(window) < 64:
            continue

        # Pitch detection for this window
        fl = min(2048, (len(window) // 2) * 2)
        hl = min(512, len(window) // 4)
        if fl < 64 or hl < 1:
            shift_st = 0.0
        else:
            f0s    = librosa.yin(window, fmin=50, fmax=min(sr // 2, 4000),
                                 sr=sr, frame_length=fl, hop_length=hl)
            voiced = f0s[(f0s >= 50) & (f0s < sr // 2)]
            if len(voiced) == 0:
                shift_st = 0.0
            else:
                shift_st = _snap_shift(float(np.median(voiced)), root_hz, pitch_classes)

        # Apply shift to this window
        if abs(shift_st) >= 0.05:
            try:
                shifted = librosa.effects.pitch_shift(window, sr=sr, n_steps=float(shift_st))
            except Exception:
                shifted = window.copy()
        else:
            shifted = window.copy()

        # Trim/pad to window length
        if len(shifted) > len(window):
            shifted = shifted[:len(window)]
        elif len(shifted) < len(window):
            shifted = np.pad(shifted, (0, len(window) - len(shifted)))

        # Hanning envelope for overlap-add
        env         = np.hanning(len(window)).astype(np.float32)
        wet[i0:i1]  += shifted * env
        norm[i0:i1] += env

    # Normalize by accumulated envelope weights
    safe_norm = np.where(norm > 1e-6, norm, 1.0)
    wet       = wet / safe_norm

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
