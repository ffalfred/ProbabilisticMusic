"""Xenakis: Grain Scatter — stochastic granular resynthesis: grains shuffled, re-pitched and re-levelled.

Grains overlap by half under Hann windows, which sum to a constant, so an
unaltered grain stream reconstructs the input exactly (no ripple at the
grain rate). In stereo, each grain lands at a random place in the stereo
field (`spread`; 0 = grains keep the source's own image)."""
import numpy as np
from plugins import plugin_rng, frames_io, pan_gains
from src.stretch import read_at_rate

NAME     = "Xenakis: Grain Scatter"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_grain_scatter"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "grain_ms":      {"label": "grain ms",     "type": "float", "min": 10,  "max": 100, "default": 40},
    "pitch_spread":  {"label": "pitch spread", "type": "float", "min": 0,   "max": 24,  "default": 6},
    "shuffle_pct":   {"label": "shuffle %",    "type": "float", "min": 0,   "max": 100, "default": 30},
    "amplitude_var": {"label": "amp var %",    "type": "float", "min": 0,   "max": 100, "default": 40},
    "spread":        {"label": "stereo spread %", "type": "float", "min": 0, "max": 100, "default": 50},
    "dry_wet":       {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 90},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    grain_ms  = float(params.get("grain_ms", 40))
    p_spread  = float(params.get("pitch_spread", 6))
    shuffle   = float(params.get("shuffle_pct", 30)) / 100.0
    amp_var   = float(params.get("amplitude_var", 40)) / 100.0
    spread    = float(params.get("spread", 50)) / 100.0
    dw        = float(params.get("dry_wet", 90)) / 100.0

    audio, back = frames_io(clip)
    n_ch      = audio.shape[1]
    grain_len = max(64, int(grain_ms * sr / 1000)) // 2 * 2
    hop       = grain_len // 2                        # grains overlap by half
    n_grains  = -(-len(audio) // hop) + 1             # two grains cover every sample
    rng       = plugin_rng()
    # Periodic Hann at 50% overlap sums to exactly 1: no ripple between grains
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(grain_len) / grain_len)).astype(np.float32)

    grain_indices = list(range(n_grains))
    n_shuffle = int(n_grains * shuffle)
    if n_shuffle > 1:
        shuf_idx = rng.choice(n_grains, size=n_shuffle, replace=False)
        permed   = rng.permutation(shuf_idx)
        for a, b in zip(shuf_idx, permed):
            grain_indices[a], grain_indices[b] = grain_indices[b], grain_indices[a]

    # Output grain k sits at (k - 1) * hop, so the first grain's fade-in
    # falls before the clip and every sample is covered by two grains
    grains = []
    for out_gi, src_gi in enumerate(grain_indices):
        if p_spread > 0.05:
            # Granular pitch: read the grain faster or slower (tape-style).
            # Grains are 10-100 ms, too short for a time-stretcher.
            st = float(rng.uniform(-p_spread / 2, p_spread / 2))
            ratio = 2.0 ** (st / 12.0)
        else:
            ratio = 1.0
        gain = float(rng.uniform(1.0 - amp_var, 1.0)) if amp_var > 0 else 1.0
        grains.append((out_gi, (src_gi - 1) * hop, ratio, gain))
    # Stereo positions are drawn last, so a mono render is unchanged
    pans = rng.uniform(-1, 1, len(grains)) * spread if n_ch == 2 else np.zeros(len(grains))

    wet = np.zeros((len(audio) + 2 * grain_len, n_ch), dtype=np.float32)
    for (out_gi, start, ratio, gain), pan in zip(grains, pans):
        grain = np.stack([read_at_rate(audio[:, c], start, grain_len, ratio)
                          for c in range(n_ch)], axis=1)
        o = out_gi * hop                                # buffer is offset by one hop
        wet[o:o + grain_len] += grain * (win * gain)[:, None] * pan_gains(pan, n_ch)[None, :]

    wet = wet[hop:hop + len(audio)]
    return back(audio * (1.0 - dw) + wet * dw)
