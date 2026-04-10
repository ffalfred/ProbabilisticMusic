"""Wagner: Endless Melody — smooth crossfades + chromatic passing tones at motif boundaries."""
import numpy as np

NAME     = "Wagner: Endless Melody"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_endless_melody"

PARAMS = {
    "crossfade_ms": {"label": "crossfade ms", "type": "float", "min": 50,  "max": 300, "default": 200},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 80},
}

_PASSING_MS = 50  # duration of passing-tone burst at each boundary


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    cf_ms   = float(params.get("crossfade_ms", 200))
    dw      = float(params.get("dry_wet", 80)) / 100.0

    audio   = clip.astype(np.float32)
    cf_len  = max(32, int(cf_ms * sr / 1000))
    pt_len  = max(32, int(_PASSING_MS * sr / 1000))

    onsets = librosa.onset.onset_detect(y=audio, sr=sr, units="samples")
    if len(onsets) < 2:
        return audio

    wet = audio.copy()
    rng = np.random.default_rng()

    for i in range(1, len(onsets)):
        b = int(onsets[i])  # boundary sample

        # --- Crossfade: last cf_len samples before boundary fade out,
        #     first cf_len samples after boundary fade in ---
        out_start = max(0, b - cf_len)
        out_end   = b
        n_out     = out_end - out_start
        if n_out > 0:
            fade_out = np.linspace(1.0, 0.0, n_out, dtype=np.float32)
            wet[out_start:out_end] = wet[out_start:out_end] * fade_out

        in_start = b
        in_end   = min(len(wet), b + cf_len)
        n_in     = in_end - in_start
        if n_in > 0:
            fade_in = np.linspace(0.0, 1.0, n_in, dtype=np.float32)
            wet[in_start:in_end] = wet[in_start:in_end] * fade_in

        # --- Passing tone: ±1 semitone burst centered at boundary ---
        pt_start = max(0, b - pt_len // 2)
        pt_end   = min(len(audio), pt_start + pt_len)
        pt_seg   = audio[pt_start:pt_end]
        if len(pt_seg) < 32:
            continue

        direction = float(rng.choice([-1.0, 1.0]))
        try:
            passing = librosa.effects.pitch_shift(pt_seg, sr=sr, n_steps=direction)
        except Exception:
            continue

        if len(passing) > len(pt_seg):
            passing = passing[:len(pt_seg)]
        elif len(passing) < len(pt_seg):
            passing = np.pad(passing, (0, len(pt_seg) - len(passing)))

        env = np.hanning(len(passing)).astype(np.float32)
        wet[pt_start:pt_end] += passing * env * 0.4  # additive, subdued

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
