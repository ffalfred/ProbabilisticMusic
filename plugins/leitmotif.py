"""Wagner: Leitmotif — onset-segmented motifs, each transposed and optionally time-stretched + repeated."""
import numpy as np
from plugins import plugin_rng, frames_io, mono
from src.dsp import fade_edges
from src.stretch import transform, parallel_map

NAME     = "Wagner: Leitmotif"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_leitmotif"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "transpose_range": {"label": "transpose range st", "type": "float", "min": 0,  "max": 12, "default": 7},
    "repetitions":     {"label": "repetitions",         "type": "int",   "min": 1,  "max": 3,  "default": 2},
    "dry_wet":         {"label": "dry/wet %",            "type": "float", "min": 0,  "max": 100,"default": 80},
}

_STRETCH_CHOICES = [0.75, 1.0, 1.25]


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    trans_range  = float(params.get("transpose_range", 7))
    repetitions  = int(params.get("repetitions", 2))
    dw           = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    rng     = plugin_rng()
    onsets  = librosa.onset.onset_detect(y=mono(audio), sr=sr, units="samples")

    if len(onsets) < 1:
        return back(audio)

    boundaries = list(onsets) + [len(audio)]
    wet = np.zeros_like(audio)

    # 1. Draw each motif's transposition and stretch (in onset order)
    jobs = []
    for i in range(len(onsets)):
        i0 = int(boundaries[i])
        i1 = int(boundaries[i + 1])
        if i1 - i0 < 32:
            wet[i0:i1] += audio[i0:i1]
            continue
        n_steps = float(rng.uniform(-trans_range, trans_range))
        stretch = float(rng.choice(_STRETCH_CHOICES))
        if abs(stretch - 1.0) <= 0.01:
            stretch = 1.0
        jobs.append((i0, i1, n_steps, stretch))

    # 2. Transform every motif (independent calls, run in parallel). Each is
    #    processed with surrounding context and then cut back out, so the
    #    stretcher's edges don't land inside it.
    def _transform(job):
        i0, i1, n_steps, stretch = job
        c0, c1 = max(0, i0 - 2048), min(len(audio), i1 + 2048)
        out = transform(audio[c0:c1], sr, rate=stretch, semitones=n_steps)
        return out[int((i0 - c0) / stretch):int((i1 - c0) / stretch)]

    # 3. Tile each motif across its segment
    for (i0, i1, _, _), transformed in zip(jobs, parallel_map(_transform, jobs)):
        # Short fades so motif and tile boundaries don't click.
        transformed = fade_edges(transformed, int(0.005 * sr))
        seg_len = i1 - i0
        if repetitions > 1 and len(transformed) > 0:
            tiled = np.tile(transformed, (repetitions, 1))[:seg_len]
        else:
            tiled = transformed[:seg_len]
        if len(tiled) < seg_len:
            tiled = np.pad(tiled, ((0, seg_len - len(tiled)), (0, 0)))
        wet[i0:i1] += fade_edges(tiled, int(0.005 * sr))  # truncation may cut mid-tile

    return back(audio * (1.0 - dw) + wet * dw)
