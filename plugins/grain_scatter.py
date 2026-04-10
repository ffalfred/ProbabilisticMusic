"""Xenakis: Granular Cloud — stochastic granular synthesis with pitch/time randomization."""
import numpy as np

NAME     = "Xenakis: Grain Scatter"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_grain_scatter"

PARAMS = {
    "grain_ms":      {"label": "grain ms",     "type": "float", "min": 10,  "max": 100, "default": 40},
    "pitch_spread":  {"label": "pitch spread", "type": "float", "min": 0,   "max": 24,  "default": 6},
    "shuffle_pct":   {"label": "shuffle %",    "type": "float", "min": 0,   "max": 100, "default": 30},
    "amplitude_var": {"label": "amp var %",    "type": "float", "min": 0,   "max": 100, "default": 40},
    "dry_wet":       {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 90},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    grain_ms  = float(params.get("grain_ms", 40))
    p_spread  = float(params.get("pitch_spread", 6))
    shuffle   = float(params.get("shuffle_pct", 30)) / 100.0
    amp_var   = float(params.get("amplitude_var", 40)) / 100.0
    dw        = float(params.get("dry_wet", 90)) / 100.0

    audio     = clip.astype(np.float32)
    grain_len = max(64, int(grain_ms * sr / 1000))
    n_grains  = max(1, len(audio) // grain_len)
    rng       = np.random.default_rng()

    grain_indices = list(range(n_grains))
    n_shuffle = int(n_grains * shuffle)
    if n_shuffle > 1:
        shuf_idx = rng.choice(n_grains, size=n_shuffle, replace=False)
        permed   = rng.permutation(shuf_idx)
        for a, b in zip(shuf_idx, permed):
            grain_indices[a], grain_indices[b] = grain_indices[b], grain_indices[a]

    wet = np.zeros_like(audio)
    for out_gi, src_gi in enumerate(grain_indices):
        i0_src = src_gi * grain_len
        i1_src = min(i0_src + grain_len, len(audio))
        grain  = audio[i0_src:i1_src].copy()

        if p_spread > 0.05:
            st = float(rng.uniform(-p_spread / 2, p_spread / 2))
            try:
                grain = librosa.effects.pitch_shift(grain, sr=sr, n_steps=st)
            except Exception:
                pass

        if amp_var > 0:
            grain = grain * float(rng.uniform(1.0 - amp_var, 1.0))

        grain = grain * np.hanning(len(grain)).astype(np.float32)

        i0_out = out_gi * grain_len
        i1_out = i0_out + len(grain)
        if i1_out > len(wet):
            wet = np.pad(wet, (0, i1_out - len(wet)))
        wet[i0_out:i1_out] += grain

    if len(wet) > len(audio):
        wet = wet[:len(audio)]
    elif len(wet) < len(audio):
        wet = np.pad(wet, (0, len(audio) - len(wet)))

    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
