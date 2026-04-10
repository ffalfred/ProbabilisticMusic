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


def _wet_dry_mix(dry: np.ndarray, wet_processed: np.ndarray, wet_amount: float,
                 mode: str = "add") -> np.ndarray:
    """Length-aligned dry/wet mix in two flavours.

    mode='add'  (reverb, delay):
        out = dry + wet_norm * wet_amount
        Dry passes through at unity. Wet is normalised to HALF the dry's RMS
        and layered on top. The wet builds up naturally (reverb tail, delay
        echoes), so at the start of the segment the wet contribution is ~0
        and the output equals the dry — no boundary click, no "silence at
        the start". Steady-state: at wet=1 the region is at most +1 dB louder
        than the dry, which is below the just-noticeable threshold.

    mode='replace'  (overdrive, flanger):
        out = dry * sqrt(1 - wet_amount) + wet_norm * sqrt(wet_amount)
        Equal-power crossfade between dry and the loudness-matched wet. For
        decorrelated signals (which reverb/delay wets are, due to diffusion
        and delay-line phase) the sqrt gains sum to unity RMS at every mix
        position, so the crossfade is level-preserving. Used for FX where
        the wet IS the transformed source — no separate "tail" is added on
        top. wet=1 → pure wet at dry loudness.

    Both modes RMS-normalise the wet (in 'add' mode to half the dry's RMS,
    in 'replace' mode to the full dry's RMS) so the wet is always audibly
    present without raising perceived loudness.

    Pads the shorter signal with zeros so tails extending past the dry are
    preserved. IMPORTANT: RMS is computed on the ORIGINAL (unpadded) signals,
    not the padded buffers — otherwise a long reverb tail dilutes the dry's
    RMS calculation and the wet ends up normalised against a too-low target,
    causing an audible level drop inside the effect region.
    """
    wet_amount = float(np.clip(wet_amount, 0.0, 1.0))
    dry = dry.astype(np.float32)
    wet = wet_processed.astype(np.float32)

    # Compute RMS on the original (unpadded) signals so neither side dilutes
    # the other's energy measurement with zero-padding.
    in_rms  = float(np.sqrt(np.mean(dry.astype(np.float64) ** 2))) if len(dry) > 0 else 0.0
    wet_rms = float(np.sqrt(np.mean(wet.astype(np.float64) ** 2))) if len(wet) > 0 else 0.0

    # Pad to the same length for the final combination step.
    n = max(len(dry), len(wet))
    if len(dry) < n:
        dry = np.pad(dry, (0, n - len(dry)))
    if len(wet) < n:
        wet = np.pad(wet, (0, n - len(wet)))

    if wet_amount < 1e-6:
        return dry

    if mode == "replace":
        if in_rms > 1e-6 and wet_rms > 1e-6:
            wet = wet * (in_rms / wet_rms)
        # Equal-power crossfade: sqrt gains keep perceived loudness constant
        # across the blend (linear crossfade causes -3 dB at the midpoint
        # for decorrelated signals).
        dry_gain = float(np.sqrt(1.0 - wet_amount))
        wet_gain = float(np.sqrt(wet_amount))
        return (dry * dry_gain + wet * wet_gain).astype(np.float32)

    # 'add' mode: layer wet on top of unity dry. Normalise wet to half the
    # dry RMS so adding it at wet=1 raises the region by at most √(1+0.25)
    # ≈ +1 dB — well below the just-noticeable threshold (~3 dB).
    if in_rms > 1e-6 and wet_rms > 1e-6:
        wet = wet * (in_rms * 0.5 / wet_rms)
    return (dry + wet * wet_amount).astype(np.float32)


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
    time     = float(np.clip(_resolve(fx.get('time', fx.get('delay_sec', 0.3)), 0.3), 0.01, 4.0))
    feedback = float(np.clip(_resolve(fx.get('feedback', 0.6), 0.6), 0.0, 0.95))
    wet      = _resolve(fx.get('wet', 0.5), 0.5)

    # Manual multi-tap delay in numpy: pure echoes (no dry mixed in), so the
    # additive blend below doesn't double-count the dry. Up to 8 taps with
    # each tap at feedback**tap — at feedback=0.6 the 8th tap is still ~1.7%,
    # giving a long natural-sounding decay.
    n_taps = 8
    delay_samples = int(round(time * sr))
    if delay_samples < 1 or len(clip) == 0:
        return clip.astype(np.float32, copy=False)

    out_len = len(clip) + delay_samples * n_taps
    wet_only = np.zeros(out_len, dtype=np.float32)
    for tap in range(1, n_taps + 1):
        offset = delay_samples * tap
        amp    = feedback ** tap
        if amp < 1e-4:
            break
        end_in_out = offset + len(clip)
        if end_in_out > out_len:
            end_in_out = out_len
        wet_only[offset:end_in_out] += clip[:end_in_out - offset].astype(np.float32) * amp

    return _wet_dry_mix(clip, wet_only, wet, mode="replace")


def _reverb(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both old 'reverberance' param and new 'room' alias
    room = _resolve(fx.get('room', None), None)
    if room is not None:
        reverberance = int(np.clip(room * 100, 0, 100))
    else:
        reverberance = int(np.clip(_resolve(fx.get('reverberance', 100), 100), 0, 100))

    damping     = int(np.clip(_resolve(fx.get('damping', 50), 50), 0, 100))
    room_scale  = int(np.clip(_resolve(fx.get('room_scale', 100), 100), 0, 100))
    pre_delay   = int(np.clip(_resolve(fx.get('pre_delay', 0), 0), 0, 500))
    wet         = _resolve(fx.get('wet', 0.5), 0.5)

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    # sox reverb syntax (positional, all required if you want pre_delay):
    #   reverb [-w] reverberance damping room_scale stereo_depth pre_delay wet_gain
    # `-w` makes sox output ONLY the wet signal (no dry mixed in). Stereo
    # depth is hardcoded to 100 (full); wet_gain is 0 dB (we apply our own
    # blend via _wet_dry_mix).
    args = ['sox', tmp_in, tmp_out, 'reverb', '-w',
            str(reverberance), str(damping), str(room_scale), '100',
            str(pre_delay), '0']
    subprocess.run(args, check=True, capture_output=True)

    wet_only = _read_and_clean(tmp_in, tmp_out)
    return _wet_dry_mix(clip, wet_only, wet, mode="replace")


def _overdrive(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    # Support both old 'gain' param and new 'drive' param
    drive = fx.get('drive', None)
    if drive is not None:
        gain = int(np.clip(_resolve(drive, 0.6) * 100, 0, 100))
    else:
        gain = int(np.clip(_resolve(fx.get('gain', 60), 60), 0, 100))
    tone = int(np.clip(_resolve(fx.get('tone', fx.get('colour', 20)), 20), 0, 100))
    wet  = _resolve(fx.get('wet', 1.0), 1.0)

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'overdrive', str(gain), str(tone)],
                   check=True, capture_output=True)
    distorted = _read_and_clean(tmp_in, tmp_out)
    # 'replace' mode: at wet=1 the signal IS the distorted version (loudness
    # matched to dry, so no volume jump). At wet=0 it's pure dry. Drop wet
    # for parallel distortion blends.
    return _wet_dry_mix(clip, distorted, wet, mode="replace")


def _flanger(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay = np.clip(_resolve(fx.get('delay_ms', 0),   0),   0,   30)
    depth = np.clip(_resolve(fx.get('depth', fx.get('depth_ms', 6)), 6), 0, 10)
    speed = np.clip(_resolve(fx.get('rate', fx.get('speed_hz', 2.0)), 2.0), 0.1, 10)
    feedback = np.clip(_resolve(fx.get('feedback', 80), 80), -95, 95)
    wet      = _resolve(fx.get('wet', 0.7), 0.7)

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    # sox flanger args: delay depth regen width speed shape phase interp
    # regen (-95..95) = feedback %, width 71 = sox default, phase 25 = sox default
    subprocess.run([
        'sox', tmp_in, tmp_out, 'flanger',
        str(round(delay, 2)),
        str(round(depth, 2)),
        str(round(feedback, 0)),
        '71',
        str(round(speed, 2)),
        'sine', '25', 'linear'
    ], check=True, capture_output=True)
    flanged = _read_and_clean(tmp_in, tmp_out)
    # 'replace' mode: at wet=1 you hear pure flanged signal at dry loudness
    # (source replaced by the modulated version).
    return _wet_dry_mix(clip, flanged, wet, mode="replace")


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

    return _wet_dry_mix(clip, result, wet, mode="replace")


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

    # RMS-match y_inv to the input so spectral peaks don't cause the whole
    # track to be normalised down after render.
    in_rms  = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    out_rms = float(np.sqrt(np.mean(y_inv.astype(np.float64) ** 2)))
    if in_rms > 1e-6 and out_rms > 1e-6:
        y_inv = y_inv * (in_rms / out_rms)

    result = audio * (1.0 - dry_wet) + y_inv * dry_wet
    return result.astype(np.float32)


def _overtones(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Add synthetic harmonics (overtones) above the fundamental."""
    try:
        import librosa
    except ImportError:
        return clip

    n_harmonics = max(1, int(fx.get('n_harmonics', 3)))
    gain_db     = np.clip(_resolve(fx.get('gain_db', -6), -6), -60, 12)
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
        # Gentler falloff: 1/sqrt(h-1) so higher harmonics stay audible
        h_gain = gain_lin / float(np.sqrt(h - 1))
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
