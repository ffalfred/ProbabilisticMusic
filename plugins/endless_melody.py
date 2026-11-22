"""Wagner: Endless Melody — join notes into one unbroken line, with chromatic passing tones.

At every detected note boundary:
1. Bridge: the previous note's last moment is held (a short spectral freeze)
   and rings on across the boundary, fading out over `crossfade_ms`, so the
   line never breaks.
2. The new note's attack comes in softened (from half level), so it grows
   out of the held sound instead of cutting in.
3. Passing tone: a 50 ms burst of the boundary, a semitone up or down
   (random), is added — a chromatic grace note joining the two notes.
"""
import numpy as np
from plugins import plugin_rng, frames_io, mono
from src.spectral import legato_bridges
from src.stretch import pitch_shift, parallel_map

NAME     = "Wagner: Endless Melody"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_endless_melody"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "crossfade_ms": {"label": "crossfade ms", "type": "float", "min": 50,  "max": 300, "default": 200},
    "dry_wet":      {"label": "dry/wet %",    "type": "float", "min": 0,   "max": 100, "default": 80},
}

_PASSING_MS  = 50    # duration of passing-tone burst at each boundary
_ATTACK_FROM = 0.5   # level the new note's attack starts from
_N_FFT, _HOP = 2048, 512


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    cf_ms   = float(params.get("crossfade_ms", 200))
    dw      = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    n_ch    = audio.shape[1]
    cf_len  = max(32, int(cf_ms * sr / 1000))
    pt_len  = max(32, int(_PASSING_MS * sr / 1000))

    onsets = librosa.onset.onset_detect(y=mono(audio), sr=sr, units="samples")
    if len(onsets) < 2 or len(audio) < _N_FFT:
        return back(audio)

    rng = plugin_rng()
    # Passing tones are cut from whole-clip shifts a semitone up and down:
    # two Rubber Band calls instead of one per boundary.
    neighbours = dict(zip((1.0, -1.0), parallel_map(lambda st: pitch_shift(audio, sr, st), (1.0, -1.0))))

    # 1 + 2. Bridges and softened entries at every boundary (all channels at
    #        the same places)
    boundaries = [int(b) for b in onsets[1:]]
    bridge, attack_gain = legato_bridges(audio, boundaries, cf_len, _ATTACK_FROM, _N_FFT, _HOP)

    # 3. Passing tone centred on each boundary
    passing_layer = np.zeros_like(audio)
    for b in boundaries:
        pt_start = max(0, b - pt_len // 2)
        pt_end   = min(len(audio), pt_start + pt_len)
        if pt_end - pt_start < 32:
            continue
        direction = float(rng.choice([-1.0, 1.0]))
        passing = neighbours[direction][pt_start:pt_end]
        env = np.hanning(len(passing)).astype(np.float32)[:, None]
        passing_layer[pt_start:pt_end] += passing * env * 0.4  # additive, subdued

    wet = audio * attack_gain[:, None] + bridge + passing_layer
    return back(audio * (1.0 - dw) + wet * dw)
