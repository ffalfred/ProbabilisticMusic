"""Spectral helpers shared by the engine (articulations) and the Morphogenics.

- stft / istft with instantaneous frequency, so a held spectrum keeps each
  partial at its true frequency instead of the bin centre;
- sustain: hold one moment of a sound (a spectral freeze);
- warp_partials: move every partial to a new frequency f -> fn(f) without
  smearing (peak-based phase-vocoder shifting, Laroche & Dolson 1999), for
  stretched or squeezed harmonics;
- keep_peaks: reduce a spectrum to its N strongest partials;
- hold_moment: sustain the sound just before a given sample;
- legato_bridges: at each boundary, let the sound just before it ring on
  across it (fading) and soften what enters — a legato join.
stft / sustain / warp_partials / keep_peaks work on 1-D signals; hold_moment
and legato_bridges take (frames, channels).
"""
import numpy as np


def stft(x: np.ndarray, n_fft: int, hop: int):
    """Complex STFT (bins, frames) and each bin's instantaneous frequency in
    radians per hop (same shape), from the phase advance between frames."""
    import librosa
    D = librosa.stft(x.astype(np.float32), n_fft=n_fft, hop_length=hop)
    omega = 2 * np.pi * np.arange(D.shape[0]) * hop / n_fft
    ph = np.angle(D)
    dphi = np.diff(ph, axis=1) - omega[:, None]
    dphi -= 2 * np.pi * np.round(dphi / (2 * np.pi))
    inst = np.empty(D.shape, dtype=np.float64)
    inst[:, 1:] = omega[:, None] + dphi
    inst[:, 0] = inst[:, 1] if D.shape[1] > 1 else omega
    return D, inst


def istft(D: np.ndarray, hop: int, n_fft: int, length: int) -> np.ndarray:
    import librosa
    return librosa.istft(D, hop_length=hop, n_fft=n_fft, length=length).astype(np.float32)


def keep_peaks(mag: np.ndarray, n: int, width: int = 2) -> np.ndarray:
    """Zero all but the n strongest spectral peaks of a magnitude vector,
    keeping `width` bins either side of each peak (the window's main lobe)."""
    if n <= 0 or n >= len(mag):
        return mag
    is_peak = np.zeros(len(mag), bool)
    is_peak[1:-1] = (mag[1:-1] > mag[:-2]) & (mag[1:-1] >= mag[2:])
    idx = np.flatnonzero(is_peak)
    if len(idx) > n:
        idx = idx[np.argsort(mag[idx])[-n:]]
    keep = np.zeros(len(mag), bool)
    for d in range(-width, width + 1):
        keep[np.clip(idx + d, 0, len(mag) - 1)] = True
    return np.where(keep, mag, 0.0)


def sustain(mag: np.ndarray, inst: np.ndarray, phase0: np.ndarray, n_samples: int,
            hop: int, n_fft: int) -> np.ndarray:
    """Hold one spectral moment for n_samples: constant magnitudes, each bin's
    phase advancing at its own instantaneous frequency (a spectral freeze)."""
    n_frames = n_samples // hop + 3
    k = np.arange(n_frames)
    D = mag[:, None] * np.exp(1j * (phase0[:, None] + inst[:, None] * k[None, :]))
    return istft(D, hop, n_fft, n_samples)


def warp_partials(x: np.ndarray, sr: int, fn, n_fft: int = 4096, hop: int = 1024) -> np.ndarray:
    """Move every partial from frequency f to fn(f) (Hz → Hz, vectorised).

    Each frame's spectral peaks are found; the bins around a peak (its region,
    up to half-way to the next peak) are moved together by the
    peak's shift, and their phase is rotated so the partial lands exactly on
    its new frequency and stays continuous from frame to frame. This keeps
    partials clean, unlike moving every bin independently.
    """
    D, inst = stft(x, n_fft, hop)
    n_bins, n_frames = D.shape
    bin_hz = sr / n_fft
    mag = np.abs(D)
    out = np.zeros_like(D)
    prev_peaks = np.zeros(0, int)
    prev_theta = np.zeros(0)
    floor = mag.max() * 1e-5 if mag.size else 0.0
    bins = np.arange(n_bins)
    for t in range(n_frames):
        m = mag[:, t]
        pk = np.flatnonzero((m[1:-1] > m[:-2]) & (m[1:-1] >= m[2:]) & (m[1:-1] > floor)) + 1
        if len(pk) == 0:
            prev_peaks, prev_theta = pk, np.zeros(0)
            continue
        f_peak = inst[pk, t] * sr / (2 * np.pi * hop)
        f_new = np.asarray(fn(np.maximum(f_peak, 0.0)), dtype=np.float64)
        dk = np.round((f_new - f_peak) / bin_hz).astype(int)
        # Phase rotation per peak, continued from the matching peak of the
        # previous frame so the partial's phase stays continuous
        theta = np.zeros(len(pk))
        if len(prev_peaks):
            j = np.searchsorted(prev_peaks, pk).clip(1, len(prev_peaks)) - 1
            j2 = (j + 1).clip(0, len(prev_peaks) - 1)
            near = np.where(np.abs(prev_peaks[j2] - pk) < np.abs(prev_peaks[j] - pk), j2, j)
            ok = np.abs(prev_peaks[near] - pk) <= 3
            theta[ok] = prev_theta[near[ok]]
        theta += 2 * np.pi * (f_new - f_peak) * hop / sr
        rot = np.exp(1j * theta)
        # Each bin belongs to its nearest peak (regions split half-way
        # between peaks) and moves with it
        region = np.searchsorted((pk[:-1] + pk[1:]) // 2, bins, side='right')
        dest = bins + dk[region]
        ok = (dest >= 0) & (dest < n_bins)
        np.add.at(out[:, t], dest[ok], D[ok, t] * rot[region[ok]])
        prev_peaks, prev_theta = pk, theta
    return istft(out, hop, n_fft, len(x))


def median_f0(x: np.ndarray, sr: int, fmin: float = 40.0, fmax: float = 2000.0) -> float:
    """Median fundamental over the louder frames (YIN); 0 if none found."""
    import librosa
    fl = 4096 if sr > 32000 else 2048
    if len(x) < fl:
        return 0.0
    f0 = librosa.yin(x.astype(np.float32), fmin=fmin, fmax=min(fmax, sr / 4), sr=sr, frame_length=fl)
    rms = librosa.feature.rms(y=x, frame_length=fl, hop_length=fl // 4)[0][:len(f0)]
    loud = rms > rms.max() * 0.1 if rms.size else np.zeros(0, bool)
    return float(np.median(f0[:len(loud)][loud])) if loud.any() else 0.0


def hold_moment(x: np.ndarray, end: int, n_out: int, n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    """Sustain the sound just before sample `end` for n_out samples.

    x is (frames, channels). The moment is the analysis window that ends at
    `end`; each partial is held at its own frequency (from the phase advance
    over one hop) and its phase continues from `end`, so the hold joins the
    sound without a jump. Returns (n_out, channels).
    """
    n, n_ch = x.shape
    out = np.zeros((max(n_out, 0), n_ch), dtype=np.float32)
    if n_out <= 0 or end <= 0:
        return out
    win = np.hanning(n_fft + 1)[:-1]
    omega = 2 * np.pi * np.arange(n_fft // 2 + 1) * hop / n_fft

    def frame(stop, c):
        seg = x[max(0, stop - n_fft):stop, c].astype(np.float64)
        seg = np.pad(seg, (n_fft - len(seg), 0))
        return np.fft.rfft(seg * win)

    for c in range(n_ch):
        F1, F2 = frame(end - hop, c), frame(end, c)
        dphi = np.angle(F2) - np.angle(F1) - omega
        dphi -= 2 * np.pi * np.round(dphi / (2 * np.pi))
        inst = omega + dphi
        # Frame k of the hold is centred k hops after `end`; the captured
        # frame is centred half a window before it
        phase0 = np.angle(F2) + inst * (n_fft / 2 / hop)
        out[:, c] = sustain(np.abs(F2), inst, phase0, n_out, hop, n_fft)
    return out


def legato_bridges(x: np.ndarray, boundaries, length: int, attack_from: float = 0.5,
                   n_fft: int = 2048, hop: int = 512):
    """Legato joins at the given sample positions of x (frames, channels).

    At each boundary the sound just before it is held and rings on across it,
    fading out over `length` samples (equal-power), and what enters is
    softened: its level rises from `attack_from` to 1 over the same time.
    Returns (bridge (frames, channels) to add, gain (frames,) to multiply
    the original by). Close boundaries take the lower gain, not the product.
    """
    n, n_ch = x.shape
    bridge = np.zeros_like(x, dtype=np.float32)
    gain = np.ones(n, dtype=np.float32)
    for b in boundaries:
        b = int(b)
        m = min(int(length), n - b)
        if b <= 0 or m <= 0:
            continue
        held = hold_moment(x, b, m, n_fft, hop)
        bridge[b:b + m] += held * np.cos(np.linspace(0, np.pi / 2, m)).astype(np.float32)[:, None]
        ramp = attack_from + (1 - attack_from) * np.sin(np.linspace(0, np.pi / 2, m))
        gain[b:b + m] = np.minimum(gain[b:b + m], ramp)
    return bridge, gain
