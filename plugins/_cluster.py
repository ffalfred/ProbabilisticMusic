"""Shared engine for the Penderecki clusters (Cluster, Textural).

A cluster is a band of transposed copies of the sound, one per semitone (or
quarter tone) across the band. Each voice can follow its own pitch curve
(drift or aleatoric jumps), its own level curve (entries, swells) and its own
place in the stereo field.
"""
import numpy as np
from plugins import pan_gains
from src.stretch import pitch_shift, parallel_map

MAX_VOICES = 25
STEPS = {"semitone": 1.0, "quarter tone": 0.5}


def band(width: float, step: str) -> np.ndarray:
    """Voice offsets in semitones, centred on the sound: every step across the
    band (width 4, semitones → -2, -1, 0, +1, +2). Capped at MAX_VOICES,
    spread evenly across the band if there would be more."""
    st = STEPS.get(step, 1.0)
    width = max(0.0, float(width))
    offsets = np.arange(-width / 2, width / 2 + 1e-9, st)
    if len(offsets) > MAX_VOICES:
        offsets = np.linspace(-width / 2, width / 2, MAX_VOICES)
    return offsets if len(offsets) else np.zeros(1)


def render(audio: np.ndarray, sr: int, offsets, pitch_curves, gain_curves, pans) -> np.ndarray:
    """Sum the voices of a cluster. audio is (frames, channels); each voice is
    shifted by offsets[i] (+ pitch_curves[i], per sample, cents-scale wander
    in semitones) with both channels together, scaled by gain_curves[i] (per
    sample, or None) and placed at pans[i] (-1..1). Returns (frames, channels)
    matched to the input's loudness."""
    n, n_ch = audio.shape

    def voice(i):
        st = offsets[i] if pitch_curves[i] is None else offsets[i] + pitch_curves[i]
        return pitch_shift(audio, sr, st)

    out = np.zeros_like(audio)
    for i, layer in enumerate(parallel_map(voice, range(len(offsets)))):
        if gain_curves[i] is not None:
            layer = layer * gain_curves[i][:, None].astype(np.float32)
        out += layer * pan_gains(pans[i], n_ch)[None, :]
    r_in = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    r_out = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    return out * (r_in / r_out) if r_out > 1e-9 else out
