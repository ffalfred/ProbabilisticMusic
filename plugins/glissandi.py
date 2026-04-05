"""Desyatnikov: Glissandi — portamento slides at a random subset of onset boundaries."""
import numpy as np

NAME     = "Glissandi"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_glissandi"

PARAMS = {
    "portamento_st": {"label": "portamento st",  "type": "float", "min": 1,  "max": 7,  "default": 3},
    "density_pct":   {"label": "density %",      "type": "float", "min": 1,  "max": 30, "default": 10},
    "dry_wet":       {"label": "dry/wet %",       "type": "float", "min": 0,  "max": 100,"default": 80},
}

_SLIDE_MS = 50  # portamento duration in ms


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    port_st  = float(params.get("portamento_st", 3))
    density  = float(params.get("density_pct", 10)) / 100.0
    dw       = float(params.get("dry_wet", 80)) / 100.0

    audio    = clip.astype(np.float32)
    slide_len = max(32, int(_SLIDE_MS * sr / 1000))

    onsets = librosa.onset.onset_detect(y=audio, sr=sr, units="samples")
    if len(onsets) < 1:
        return audio

    rng        = np.random.default_rng()
    n_selected = max(1, int(len(onsets) * density))
    selected   = rng.choice(onsets, size=min(n_selected, len(onsets)), replace=False)

    wet = audio.copy()

    for onset in selected:
        i0 = int(onset)
        i1 = min(i0 + slide_len, len(audio))
        seg = audio[i0:i1]
        if len(seg) < 32:
            continue

        # Slide from +port_st down to 0 (glide into the note)
        n_sub = 5
        sub_len = len(seg) // n_sub
        if sub_len < 8:
            continue

        slide_out = np.zeros(len(seg), dtype=np.float32)
        for k in range(n_sub):
            t = k / max(n_sub - 1, 1)
            st = port_st * (1.0 - t)  # slide from port_st → 0
            s0 = k * sub_len
            s1 = s0 + sub_len if k < n_sub - 1 else len(seg)
            sub = seg[s0:s1]
            try:
                shifted = librosa.effects.pitch_shift(sub, sr=sr, n_steps=float(st))
            except Exception:
                shifted = sub
            if len(shifted) > len(sub):
                shifted = shifted[:len(sub)]
            elif len(shifted) < len(sub):
                shifted = np.pad(shifted, (0, len(sub) - len(shifted)))
            slide_out[s0:s1] = shifted

        env = np.hanning(len(slide_out)).astype(np.float32)
        wet[i0:i1] += slide_out * env * 0.5  # additive blend

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
