"""Penderecki: Glissando — linear pitch slides spanning each segment."""
import numpy as np

NAME     = "Penderecki: Glissando"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_penderecki_glissando"

PARAMS = {
    "gliss_range": {"label": "gliss range st", "type": "int",   "min": 1,   "max": 24,  "default": 12},
    "n_steps":     {"label": "steps",          "type": "int",   "min": 3,   "max": 10,  "default": 5},
    "dry_wet":     {"label": "dry/wet %",      "type": "float", "min": 0,   "max": 100, "default": 80},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    gliss_range = int(params.get("gliss_range", 12))
    n_steps     = max(3, int(params.get("n_steps", 5)))
    dw          = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    wet     = np.zeros_like(audio)
    seg_len = max(1024, int(0.2 * sr))  # ~200 ms segments
    n_segs  = max(1, (len(audio) + seg_len - 1) // seg_len)

    # Pitch sweep: linearly from -gliss_range/2 → +gliss_range/2 over n_steps subframes
    shifts = np.linspace(-gliss_range / 2, gliss_range / 2, n_steps)

    for s in range(n_segs):
        i0  = s * seg_len
        i1  = min(i0 + seg_len, len(audio))
        seg = audio[i0:i1]

        sub_len = len(seg) // n_steps
        if sub_len < 32:
            wet[i0:i1] += seg
            continue

        pieces = []
        for si, st in enumerate(shifts):
            s0  = si * sub_len
            s1  = s0 + sub_len if si < n_steps - 1 else len(seg)
            sub = seg[s0:s1]
            if len(sub) < 8:
                pieces.append(sub)
                continue
            try:
                shifted_sub = librosa.effects.pitch_shift(sub, sr=sr, n_steps=float(st))
            except Exception:
                shifted_sub = sub
            shifted_sub = shifted_sub[:len(sub)]
            if len(shifted_sub) < len(sub):
                shifted_sub = np.pad(shifted_sub, (0, len(sub) - len(shifted_sub)))
            pieces.append(shifted_sub)

        result = np.concatenate(pieces)
        result = result[:len(seg)]
        if len(result) < len(seg):
            result = np.pad(result, (0, len(seg) - len(result)))
        wet[i0:i1] += result

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
