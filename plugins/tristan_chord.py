"""Wagner: Tristan — overlay the Tristan chord on every Nth onset segment.

The chord is built on the sound itself as its lowest note, in Wagner's
voicing F–B–D♯–G♯: 0, +6, +10, +15 semitones (a half-diminished seventh,
spread). `voicing: harmonic 7th` gives the previous version's chord instead,
a just-intonation 4:5:6:7 stack (0, +3.86, +7.02, +9.69 st).
"""
import numpy as np
from plugins import frames_io, mono
from src.stretch import pitch_shift, parallel_map

NAME     = "Wagner: Tristan Chord"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_tristan_chord"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "voicing":          {"label": "voicing", "type": "select", "options": ["tristan", "harmonic 7th"], "default": "tristan"},
    "tristan_interval": {"label": "every N onsets", "type": "int",   "min": 2,  "max": 8,  "default": 3},
    "chord_gain_db":    {"label": "chord gain dB",  "type": "float", "min": -24,"max": -6, "default": -12},
    "dry_wet":          {"label": "dry/wet %",       "type": "float", "min": 0,  "max": 100,"default": 80},
}

# Semitones above the sound (its own pitch is the chord's lowest note)
_VOICINGS = {
    "tristan":      [0.0, 6.0, 10.0, 15.0],    # F–B–D♯–G♯
    "harmonic 7th": [0.0, 3.86, 7.02, 9.69],   # just 4:5:6:7 (the old chord)
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    chord      = _VOICINGS.get(str(params.get("voicing", "tristan")), _VOICINGS["tristan"])
    nth        = int(params.get("tristan_interval", 3))
    gain_db    = float(params.get("chord_gain_db", -12))
    dw         = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    chord_gain = 10 ** (gain_db / 20.0)

    onsets = librosa.onset.onset_detect(y=mono(audio), sr=sr, units="samples")
    if len(onsets) < 1:
        return back(audio)

    boundaries = list(onsets) + [len(audio)]
    wet = audio.copy()
    # One whole-clip shift per chord voice; the chords are cut out of these.
    voices = parallel_map(lambda st: pitch_shift(audio, sr, float(st)), chord)

    for i in range(len(onsets)):
        if (i % nth) != 0:
            continue
        i0 = int(boundaries[i])
        i1 = int(boundaries[i + 1])
        seg = audio[i0:i1]
        if len(seg) < 32:
            continue

        chord_layer = np.zeros(seg.shape, dtype=np.float32)
        for voice in voices:
            chord_layer += voice[i0:i1]

        chord_layer *= (chord_gain / len(chord))
        wet[i0:i1] += chord_layer

    return back(audio * (1.0 - dw) + wet * dw)
