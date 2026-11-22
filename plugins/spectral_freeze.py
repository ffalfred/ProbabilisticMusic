"""Saariaho: Spectral Freeze — hold moments of the sound and sustain them.

Two modes:
- attacks (default): at every detected attack, the sound of that instant is
  captured and sustained until the next attack, crossfading into it. The
  music becomes a chain of held chords / halos.
- follow: the frozen sound follows the original slowly. `freeze_rate` sets
  how fast: 1 follows almost at once (~50 ms), 0.1 takes ~0.5 s, 0.01 ~5 s,
  and 0 holds the very first moment for the whole clip.

A held moment keeps every partial at its true frequency (measured from the
phase), so it sustains as a steady chord rather than a buzz. `n_partials`
keeps only the strongest partials of the held sound (0 = keep everything),
which purifies it towards a few sustained tones.
"""
import numpy as np
from plugins import frames_io, mono
from src.spectral import stft, istft, sustain, keep_peaks

NAME     = "Saariaho: Spectral Freeze"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_spectral_freeze"
STEREO   = True   # gets (frames, channels); see plugins.apply_plugin

PARAMS = {
    "mode":        {"label": "mode",        "type": "select", "options": ["attacks", "follow"], "default": "attacks"},
    "n_partials":  {"label": "partials (0 = all)", "type": "int", "min": 0, "max": 100, "default": 20},
    "freeze_rate": {"label": "follow rate", "type": "float", "min": 0.0, "max": 1.0, "default": 0.1},
    "dry_wet":     {"label": "dry/wet %",   "type": "float", "min": 0,   "max": 100, "default": 80},
}

_N_FFT = 2048
_HOP   = 512
_XFADE = 0.05      # s, crossfade between held moments (attacks mode)
_LATE  = 2         # frames after an attack to capture (the body, not the click)


def _match_rms(wet, ref):
    r_w = float(np.sqrt(np.mean(wet.astype(np.float64) ** 2)))
    r_r = float(np.sqrt(np.mean(ref.astype(np.float64) ** 2)))
    return wet * (r_r / r_w) if r_w > 1e-9 else wet


def _attacks(audio, sr, n_partials, onsets):
    D, inst = stft(audio, _N_FFT, _HOP)
    n_frames = D.shape[1]
    starts = sorted({0, *[int(o) for o in onsets if 0 < o < n_frames]})
    xf = max(1, int(_XFADE * sr))
    wet = np.zeros(len(audio), dtype=np.float32)
    for i, f0 in enumerate(starts):
        s0 = f0 * _HOP
        s1 = starts[i + 1] * _HOP if i + 1 < len(starts) else len(audio)
        e1 = min(len(audio), s1 + xf)                 # ring into the next moment
        cap = min(f0 + _LATE, n_frames - 1)
        mag = keep_peaks(np.abs(D[:, cap]), n_partials)
        held = sustain(mag, inst[:, cap], np.angle(D[:, cap]), e1 - s0, _HOP, _N_FFT)
        # Equal-power crossfade in from the previous moment and out to the next
        n = len(held)
        env = np.ones(n, dtype=np.float32)
        if i > 0:
            k = min(xf, n)
            env[:k] = np.sin(np.linspace(0, np.pi / 2, k))
        if e1 > s1:
            k = e1 - s1
            env[-k:] *= np.cos(np.linspace(0, np.pi / 2, k))
        wet[s0:e1] += held * env
    return wet


def _follow(audio, sr, n_partials, rate):
    D, inst = stft(audio, _N_FFT, _HOP)
    mag = np.abs(D)
    n_bins, n_frames = D.shape
    # One-pole smoothing with time constant 0.05 s / rate
    a = 0.0 if rate <= 0 else 1.0 - np.exp(-(_HOP / sr) * rate / 0.05)
    # Start from the body of the first moment (frame 0 is half padding)
    c = min(_LATE, n_frames - 1)
    m_frz = mag[:, c].copy()
    f_frz = inst[:, c].copy()
    phase = np.angle(D[:, c]).copy()
    out = np.empty_like(D)
    for t in range(n_frames):
        if t:
            # The held frequency follows the live one, weighted by how much
            # each contributes to the held magnitude
            w_new = a * mag[:, t]
            w_old = (1 - a) * m_frz
            f_frz = (w_old * f_frz + w_new * inst[:, t]) / np.maximum(w_old + w_new, 1e-12)
            m_frz = w_old + w_new
            phase = phase + f_frz
        out[:, t] = keep_peaks(m_frz, n_partials) * np.exp(1j * phase)
    return istft(out, _HOP, _N_FFT, len(audio))


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    mode       = str(params.get("mode", "attacks"))
    n_partials = int(params.get("n_partials", 20))
    rate       = float(params.get("freeze_rate", 0.1))
    dw         = float(params.get("dry_wet", 80)) / 100.0

    audio, back = frames_io(clip)
    if len(audio) < _N_FFT:
        return back(audio)
    if mode == "follow":
        wet = np.stack([_follow(audio[:, c], sr, n_partials, rate)
                        for c in range(audio.shape[1])], axis=1)
    else:
        import librosa
        # Attacks from the mono sum, so every channel holds the same moments
        onsets = librosa.onset.onset_detect(y=mono(audio), sr=sr, hop_length=_HOP, units="frames")
        wet = np.stack([_attacks(audio[:, c], sr, n_partials, onsets)
                        for c in range(audio.shape[1])], axis=1)
    wet = _match_rms(wet, audio)
    return back(audio * (1.0 - dw) + wet * dw)
