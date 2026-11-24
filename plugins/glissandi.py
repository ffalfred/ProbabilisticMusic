"""Desyatnikov: Portamento — a short slide into a random subset of the notes.

(Displayed as "Glissandi" before; the type key morpho_glissandi is unchanged.)"""
import numpy as np
from plugins import plugin_rng, frames_io, mono
from src.stretch import read_at_rate

NAME     = "Desyatnikov: Portamento"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_glissandi"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

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

    audio, back = frames_io(clip)
    slide_len = max(32, int(_SLIDE_MS * sr / 1000))

    onsets = librosa.onset.onset_detect(y=mono(audio), sr=sr, units="samples")
    if len(onsets) < 1:
        return back(audio)

    rng        = plugin_rng()
    n_selected = max(1, int(len(onsets) * density))
    selected   = rng.choice(onsets, size=min(n_selected, len(onsets)), replace=False)

    wet = audio.copy()

    for onset in selected:
        i0 = int(onset)
        i1 = min(i0 + slide_len, len(audio))
        seg = audio[i0:i1]
        if len(seg) < 32:
            continue

        # Slide from +port_st down to 0 (glide into the note), tape-style:
        # 50 ms is far too short for a time-stretcher, and a real portamento
        # changes pitch and speed together anyway.
        st = np.linspace(port_st, 0.0, len(seg))
        ratio = 2.0 ** (st / 12.0)
        slide_out = np.stack([read_at_rate(audio[:, c], i0, len(seg), ratio)
                              for c in range(audio.shape[1])], axis=1)

        env = np.hanning(len(slide_out)).astype(np.float32)[:, None]
        wet[i0:i1] += slide_out * env * 0.5  # additive blend

    return back(audio * (1.0 - dw) + wet * dw)
