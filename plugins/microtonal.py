"""Saariaho: Microtonal — the pitch bends with the sound's brightness, moment by moment.

The spectral centroid (brightness) is followed over time: brighter moments
are detuned sharp, darker ones flat, up to ±`max_cents` (500 Hz = fully
flat, 5 kHz = fully sharp), smoothed over ~150 ms so the pitch glides rather
than jitters. Timbre steers pitch, as in Saariaho's timbre–harmony thinking.
(It used to apply one fixed detune from the clip's average brightness.)"""
import numpy as np
from plugins import frames_io, mono
from src.stretch import pitch_shift

NAME     = "Saariaho: Microtonal"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_microtonal"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "max_cents": {"label": "max cents",  "type": "float", "min": 0,   "max": 50,  "default": 25},
    "dry_wet":   {"label": "dry/wet %", "type": "float", "min": 0,   "max": 100, "default": 100},
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    import librosa

    max_cents = float(params.get("max_cents", 25))
    dw        = float(params.get("dry_wet", 100)) / 100.0

    audio, back = frames_io(clip)
    if max_cents < 0.5:
        return back(audio)

    # Brightness (spectral centroid) over time, weighted towards the louder
    # frames so silence doesn't swing the pitch
    hop = 512
    m = mono(audio)
    centroid = librosa.feature.spectral_centroid(y=m, sr=sr, hop_length=hop)[0]
    rms = librosa.feature.rms(y=m, hop_length=hop)[0][:len(centroid)]
    loud = rms > rms.max() * 0.05 if rms.size and rms.max() > 0 else np.ones(len(centroid), bool)
    if loud.any():
        centroid = np.where(loud, centroid, np.interp(np.arange(len(centroid)),
                                                      np.flatnonzero(loud), centroid[loud]))

    # 500 Hz → fully flat, 5 kHz → fully sharp; smoothed over ~150 ms
    norm = np.clip((centroid - 500.0) / (5000.0 - 500.0) * 2 - 1, -1.0, 1.0)
    k = max(1, int(0.15 * sr / hop))
    norm = np.convolve(np.pad(norm, (k // 2, k - 1 - k // 2), mode='edge'), np.ones(k) / k, mode='valid')
    detune = norm * max_cents / 100.0                          # semitones per frame
    if np.abs(detune).max() < 0.001:
        return back(audio)
    curve = np.interp(np.arange(len(audio)), np.arange(len(detune)) * hop, detune)

    wet = pitch_shift(audio, sr, curve)
    return back(audio * (1.0 - dw) + wet * dw)
