import os
import random
import tempfile
import subprocess
import numpy as np
import soundfile as sf


def _resolve(val, default=0):
    """Resolve a fixed / range / gaussian parameter to a concrete float."""
    if isinstance(val, list) and len(val) == 2:
        return float(random.uniform(val[0], val[1]))
    if isinstance(val, dict):
        dist = val.get('distribution', '')
        if dist == 'gaussian':
            return float(np.random.normal(val.get('mean', default or 0), abs(val.get('std', 0))))
        return None if default is None else float(default)
    if val is None:
        return None if default is None else float(default)
    return float(val)


# ── Per-event FX dispatch ────────────────────────────────────────────────────

def apply_fx(clip: np.ndarray, sr: int, fx_list: list) -> np.ndarray:
    """Apply a list of FX dicts to a clip sequentially."""
    for fx in fx_list:
        t = fx.get('type', '')
        if t == 'delay':
            clip = _delay(clip, sr, fx)
        elif t == 'reverb':
            clip = _reverb(clip, sr, fx)
        elif t == 'overdrive':
            clip = _overdrive(clip, sr, fx)
        elif t == 'flanger':
            clip = _flanger(clip, sr, fx)
        elif t == 'pitch':
            clip = _pitch(clip, sr, fx)
        elif t == 'compress':
            clip = _compress(clip, sr, fx)
        elif t == 'eq':
            clip = _eq(clip, sr, fx)
        elif t == 'filter':
            clip = _filter(clip, sr, fx)
        elif t == 'chorus':
            clip = _chorus(clip, sr, fx)
        elif t == 'tremolo':
            clip = _tremolo(clip, sr, fx)
        elif t == 'spectral_inversion':
            clip = _spectral_inversion(clip, sr, fx)
        elif t == 'overtones':
            clip = _overtones(clip, sr, fx)
        elif t.startswith('morpho_'):
            from plugins import apply_plugin
            clip = apply_plugin(clip, sr, fx)
    return clip


# ── Section and global FX ────────────────────────────────────────────────────

def apply_section_fx(audio: np.ndarray, sr: int, fx_sections: list) -> np.ndarray:
    """Apply FX to time ranges within the full mix.

    fx_sections: list of dicts with 'from', 'to', 'type', and FX params.
    Each section's FX is applied only to the specified time range with
    crossfade at boundaries to avoid clicks.
    """
    if not fx_sections:
        return audio
    result = audio.copy()
    crossfade_samples = min(256, len(audio) // 4)
    for sec in fx_sections:
        t_from = float(sec.get('from', 0))
        t_to   = float(sec.get('to', len(audio) / sr))
        s_from = max(0, int(t_from * sr))
        s_to   = min(len(audio), int(t_to * sr))
        if s_to <= s_from:
            continue
        segment = audio[s_from:s_to].copy()
        processed = apply_fx(segment, sr, [sec])
        # Match length
        if len(processed) > len(segment):
            processed = processed[:len(segment)]
        elif len(processed) < len(segment):
            processed = np.pad(processed, (0, len(segment) - len(processed)))
        # Crossfade in
        cf = min(crossfade_samples, len(processed) // 2)
        if cf > 0:
            ramp = np.linspace(0, 1, cf)
            processed[:cf] = result[s_from:s_from + cf] * (1 - ramp) + processed[:cf] * ramp
            processed[-cf:] = processed[-cf:] * (1 - ramp[::-1]) + result[s_to - cf:s_to] * ramp[::-1]
        result[s_from:s_to] = processed
    return result


def apply_global_fx(audio: np.ndarray, sr: int, fx_global: list) -> np.ndarray:
    """Apply FX to the entire track output."""
    if not fx_global:
        return audio
    return apply_fx(audio, sr, fx_global)


# ── Classic FX implementations ───────────────────────────────────────────────

def _delay(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    time     = np.clip(_resolve(fx.get('time', fx.get('delay_sec', 0.3)), 0.3), 0.01, 4.0)
    feedback = np.clip(_resolve(fx.get('feedback', 0.4), 0.4), 0.0, 0.99)
    wet      = np.clip(_resolve(fx.get('wet', 1.0), 1.0), 0.0, 1.0)
    ping_pong = bool(fx.get('ping_pong', False))

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    subprocess.run([
        'sox', tmp_in, tmp_out,
        'echo',
        '0.8', str(round(wet, 3)),
        str(time * 1000),  str(round(feedback, 3)),
        str(time * 2000),  str(round(feedback ** 2, 3)),
        str(time * 3000),  str(round(feedback ** 3, 3)),
    ], check=True, capture_output=True)

    return _read_and_clean(tmp_in, tmp_out)


def _reverb(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both old 'reverberance' param and new 'room'/'wet' params
    room = _resolve(fx.get('room', None), None)
    wet  = _resolve(fx.get('wet', None), None)
    if room is not None:
        reverberance = int(np.clip(room * 100, 0, 100))
    else:
        reverberance = int(np.clip(_resolve(fx.get('reverberance', 50), 50), 0, 100))

    pre_delay = int(np.clip(_resolve(fx.get('pre_delay', 0), 0), 0, 500))
    damping   = int(np.clip(_resolve(fx.get('damping', 50), 50), 0, 100))

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    args = ['sox', tmp_in, tmp_out, 'reverb',
            str(reverberance), str(damping), '100']
    if pre_delay > 0:
        args.extend([str(pre_delay)])
    subprocess.run(args, check=True, capture_output=True)

    result = _read_and_clean(tmp_in, tmp_out)
    # Apply wet/dry mix
    if wet is not None and wet < 1.0:
        min_len = min(len(clip), len(result))
        result = clip[:min_len] * (1.0 - wet) + result[:min_len] * wet
    return result


def _overdrive(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both old 'gain' param and new 'drive' param
    drive = fx.get('drive', None)
    if drive is not None:
        gain = int(np.clip(_resolve(drive, 0.2) * 100, 0, 100))
    else:
        gain = int(np.clip(_resolve(fx.get('gain', 20), 20), 0, 100))
    tone   = int(np.clip(_resolve(fx.get('tone', fx.get('colour', 20)), 20), 0, 100))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'overdrive', str(gain), str(tone)],
                   check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _flanger(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay = np.clip(_resolve(fx.get('delay_ms', 0),   0),   0,   30)
    depth = np.clip(_resolve(fx.get('depth', fx.get('depth_ms', 2)), 2), 0, 10)
    speed = np.clip(_resolve(fx.get('rate', fx.get('speed_hz', 0.5)), 0.5), 0.1, 10)
    feedback = np.clip(_resolve(fx.get('feedback', 0), 0), -95, 95)
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'flanger',
        str(round(delay, 2)), str(round(depth, 2)), '0',
        str(round(feedback + 71, 0)),
        str(round(speed, 2)), 'sine', 'linear'
    ], check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _pitch(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    semitones = fx.get('semitones', None)
    if semitones is not None:
        cents = int(np.clip(_resolve(semitones, 0) * 100, -2400, 2400))
    else:
        cents = int(np.clip(_resolve(fx.get('cents', 0), 0), -2400, 2400))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'pitch', str(cents)],
                   check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _compress(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    threshold  = np.clip(_resolve(fx.get('threshold', fx.get('threshold_db', -20)), -20), -80, 0)
    ratio      = max(1.0, np.clip(_resolve(fx.get('ratio', 4), 4), 1, 50))
    attack     = np.clip(_resolve(fx.get('attack',  0.01), 0.01), 0.001, 2.0)
    release    = np.clip(_resolve(fx.get('release', 0.3),  0.3),  0.01,  5.0)
    makeup     = np.clip(_resolve(fx.get('makeup_db', 0),  0),    -20,   40)
    above_out  = threshold + (0 - threshold) / ratio
    transfer   = f"6:-80,-80,{threshold},{threshold},0,{above_out:.1f}"
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'compand',
        f"{attack:.4f},{release:.4f}", transfer, str(round(makeup, 1))
    ], check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _eq(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both single-band and multi-band ('bands' list)
    bands = fx.get('bands')
    if bands and isinstance(bands, list):
        result = clip
        for band in bands:
            freq = np.clip(_resolve(band.get('freq', 1000), 1000), 20, sr / 2 - 1)
            gain = np.clip(_resolve(band.get('gain', 0), 0), -40, 40)
            q    = max(0.1, _resolve(band.get('q', 1.0), 1.0))
            tmp_in, tmp_out = _tmp_paths()
            sf.write(tmp_in, result, sr)
            subprocess.run([
                'sox', tmp_in, tmp_out, 'equalizer',
                str(round(freq, 1)), f"{round(q, 2)}q", str(round(gain, 1))
            ], check=True, capture_output=True)
            result = _read_and_clean(tmp_in, tmp_out)
        return result

    freq = np.clip(_resolve(fx.get('freq_hz', fx.get('freq', 1000)), 1000), 20, sr / 2 - 1)
    gain = np.clip(_resolve(fx.get('gain_db', fx.get('gain', 0)), 0), -40, 40)
    q    = max(0.1, _resolve(fx.get('q', 1.0), 1.0))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'equalizer',
        str(round(freq, 1)), f"{round(q, 2)}q", str(round(gain, 1))
    ], check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


# ── New FX ───────────────────────────────────────────────────────────────────

def _filter(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Lowpass / highpass / bandpass filter using scipy."""
    from scipy.signal import butter, sosfilt

    cutoff    = np.clip(_resolve(fx.get('cutoff', 1000), 1000), 20, sr / 2 - 1)
    resonance = np.clip(_resolve(fx.get('resonance', 0), 0), 0, 1)
    ftype     = fx.get('filter_type', fx.get('type_', 'lp')).lower()

    # Map resonance 0–1 to Q 0.5–12
    q = 0.5 + resonance * 11.5

    btype_map = {'lp': 'low', 'hp': 'high', 'bp': 'band',
                 'lowpass': 'low', 'highpass': 'high', 'bandpass': 'band'}
    btype = btype_map.get(ftype, 'low')

    try:
        if btype == 'band':
            # Bandpass needs [low, high] — use cutoff ± bandwidth
            bw = cutoff * 0.3 / max(q, 0.5)
            low  = max(20, cutoff - bw)
            high = min(sr / 2 - 1, cutoff + bw)
            sos = butter(2, [low, high], btype='band', fs=sr, output='sos')
        else:
            sos = butter(2, cutoff, btype=btype, fs=sr, output='sos')
        return sosfilt(sos, clip).astype(np.float32)
    except Exception:
        return clip


def _chorus(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Chorus effect — modulated delay mixed with dry signal."""
    rate  = np.clip(_resolve(fx.get('rate', 1.5), 1.5), 0.1, 10)
    depth = np.clip(_resolve(fx.get('depth', 0.5), 0.5), 0.0, 1.0)
    wet   = np.clip(_resolve(fx.get('wet', 0.5), 0.5), 0.0, 1.0)

    # Modulated delay in samples
    max_delay_ms = 25.0 * depth
    max_delay_samples = int(max_delay_ms * sr / 1000)
    if max_delay_samples < 1:
        return clip

    n = len(clip)
    t = np.arange(n, dtype=np.float32)
    mod = max_delay_samples * 0.5 * (1 + np.sin(2 * np.pi * rate * t / sr))
    mod = mod.astype(np.float32)

    result = np.zeros_like(clip)
    for i in range(n):
        delay_idx = i - mod[i]
        if delay_idx < 0:
            result[i] = clip[i]
        else:
            idx_lo = int(delay_idx)
            frac = delay_idx - idx_lo
            if idx_lo + 1 < n:
                result[i] = clip[idx_lo] * (1 - frac) + clip[idx_lo + 1] * frac
            elif idx_lo < n:
                result[i] = clip[idx_lo]
            else:
                result[i] = clip[i]

    return (clip * (1 - wet) + result * wet).astype(np.float32)


def _tremolo(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Tremolo — amplitude modulation at a given rate."""
    rate  = np.clip(_resolve(fx.get('rate', 5.0), 5.0), 0.1, 30)
    depth = np.clip(_resolve(fx.get('depth', 0.5), 0.5), 0.0, 1.0)

    n = len(clip)
    t = np.arange(n, dtype=np.float32) / sr
    mod = 1.0 - depth * 0.5 * (1 + np.sin(2 * np.pi * rate * t))
    return (clip * mod).astype(np.float32)


# ── Spectral FX ──────────────────────────────────────────────────────────────

def _spectral_inversion(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Invert spectral amplitude within a frequency band."""
    try:
        import librosa
    except ImportError:
        return clip

    low_hz       = max(0, _resolve(fx.get('low_hz', 20), 20))
    high_hz      = min(sr / 2 - 1, _resolve(fx.get('high_hz', 10000), 10000))
    amount       = np.clip(_resolve(fx.get('amount', 100), 100), 0, 100) / 100.0
    dry_wet      = np.clip(_resolve(fx.get('dry_wet', 100), 100), 0, 100) / 100.0
    threshold_db = _resolve(fx.get('threshold_db', -60), -60)
    n_fft        = int(fx.get('fft_size', 2048))

    audio = clip.astype(np.float32)
    D     = librosa.stft(audio, n_fft=n_fft)
    mag, phase = np.abs(D), np.angle(D)

    freqs      = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    freq_mask  = (freqs >= low_hz) & (freqs <= high_hz)

    global_max = float(np.max(mag)) if np.max(mag) > 0 else 1.0
    thresh_lin = global_max * (10.0 ** (threshold_db / 20.0))

    band_mag = mag[freq_mask, :]
    if band_mag.size > 0:
        b_max = float(np.max(band_mag))
        b_min = float(np.min(band_mag))
        inv_band = (b_max + b_min) - band_mag
        inv_band = band_mag + (inv_band - band_mag) * amount

        above = band_mag > thresh_lin
        band_mag[above] = inv_band[above]
        mag[freq_mask, :] = band_mag

    D_inv = mag * np.exp(1j * phase)
    y_inv = librosa.istft(D_inv, length=len(audio))

    result = audio * (1.0 - dry_wet) + y_inv * dry_wet
    return result.astype(np.float32)


def _overtones(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Add synthetic harmonics (overtones) above the fundamental."""
    try:
        import librosa
    except ImportError:
        return clip

    n_harmonics = max(1, int(fx.get('n_harmonics', 3)))
    gain_db     = np.clip(_resolve(fx.get('gain_db', -12), -12), -60, 12)
    gain_lin    = 10.0 ** (gain_db / 20.0)

    result = clip.astype(np.float32).copy()

    for h in range(2, n_harmonics + 2):
        n_steps = round(12.0 * np.log2(h))
        try:
            harmonic = librosa.effects.pitch_shift(
                clip.astype(np.float32), sr=sr, n_steps=float(n_steps)
            )
        except Exception:
            continue
        h_gain = gain_lin / (h - 1)
        min_len = min(len(result), len(harmonic))
        result[:min_len] += harmonic[:min_len] * h_gain

    return result.astype(np.float32)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tmp_paths() -> tuple:
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_in = f.name
    tmp_out = tmp_in.replace('.wav', '_out.wav')
    return tmp_in, tmp_out


def _read_and_clean(tmp_in: str, tmp_out: str) -> np.ndarray:
    result, _ = sf.read(tmp_out, dtype='float32')
    if result.ndim == 2:
        result = result.mean(axis=1)
    try:
        os.remove(tmp_in)
        os.remove(tmp_out)
    except OSError:
        pass
    return result
