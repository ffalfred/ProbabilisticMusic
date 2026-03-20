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
            return float(np.random.normal(val.get('mean', default), abs(val.get('std', 0))))
        return float(default)
    if val is None:
        return float(default)
    return float(val)


def apply_fx(clip: np.ndarray, sr: int, fx_list: list) -> np.ndarray:
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
        elif t == 'spectral_inversion':
            clip = _spectral_inversion(clip, sr, fx)
        elif t == 'overtones':
            clip = _overtones(clip, sr, fx)
        elif t.startswith('morpho_'):
            from plugins import apply_plugin
            clip = apply_plugin(clip, sr, fx)
    return clip


def _delay(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay_sec = np.clip(_resolve(fx.get('delay_sec', 0.3), 0.3), 0.01, 4.0)
    feedback  = np.clip(_resolve(fx.get('feedback',  0.4), 0.4), 0.0, 0.99)

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    subprocess.run([
        'sox', tmp_in, tmp_out,
        'echo',
        '0.8', '0.9',
        str(delay_sec * 1000),  str(round(feedback, 3)),
        str(delay_sec * 2000),  str(round(feedback ** 2, 3)),
        str(delay_sec * 3000),  str(round(feedback ** 3, 3)),
    ], check=True, capture_output=True)

    return _read_and_clean(tmp_in, tmp_out)


def _reverb(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    reverberance = int(np.clip(_resolve(fx.get('reverberance', 50), 50), 0, 100))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    subprocess.run([
        'sox', tmp_in, tmp_out,
        'reverb', str(reverberance)
    ], check=True, capture_output=True)

    return _read_and_clean(tmp_in, tmp_out)


def _overdrive(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    gain   = int(np.clip(_resolve(fx.get('gain',   20), 20), 0, 100))
    colour = int(np.clip(_resolve(fx.get('colour', 20), 20), 0, 100))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'overdrive', str(gain), str(colour)],
                   check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _flanger(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay = np.clip(_resolve(fx.get('delay_ms', 0),   0),   0,   30)
    depth = np.clip(_resolve(fx.get('depth_ms', 2),   2),   0,   10)
    speed = np.clip(_resolve(fx.get('speed_hz', 0.5), 0.5), 0.1, 10)
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'flanger',
        str(round(delay, 2)), str(round(depth, 2)), '0', '71',
        str(round(speed, 2)), 'sine', 'linear'
    ], check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _pitch(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    cents = int(np.clip(_resolve(fx.get('cents', 0), 0), -2400, 2400))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'pitch', str(cents)],
                   check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _compress(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    threshold  = np.clip(_resolve(fx.get('threshold_db', -20), -20), -80, 0)
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
    freq = np.clip(_resolve(fx.get('freq_hz', 1000), 1000), 20, sr / 2 - 1)
    gain = np.clip(_resolve(fx.get('gain_db',    0),    0), -40, 40)
    q    = max(0.1, _resolve(fx.get('q', 1.0), 1.0))
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'equalizer',
        str(round(freq, 1)), f"{round(q, 2)}q", str(round(gain, 1))
    ], check=True, capture_output=True)
    return _read_and_clean(tmp_in, tmp_out)


def _spectral_inversion(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Invert spectral amplitude within a frequency band.

    Parameters
    ----------
    low_hz, high_hz   : frequency band to process (default 20–10 000 Hz)
    threshold_db      : only invert bins louder than this level (default -60 dB)
    amount            : 0–100 % inversion depth (default 100)
    dry_wet           : 0–100 % wet/dry blend (default 100)
    fft_size          : STFT window size — 512, 1024, or 2048 (default 2048)
    """
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
    freq_mask  = (freqs >= low_hz) & (freqs <= high_hz)          # (n_bins,)

    global_max = float(np.max(mag)) if np.max(mag) > 0 else 1.0
    thresh_lin = global_max * (10.0 ** (threshold_db / 20.0))

    # For each bin in the band, invert its magnitude relative to the band max+min
    band_mag = mag[freq_mask, :]
    if band_mag.size > 0:
        b_max = float(np.max(band_mag))
        b_min = float(np.min(band_mag))
        inv_band = (b_max + b_min) - band_mag                 # spectral flip
        inv_band = band_mag + (inv_band - band_mag) * amount  # blend by amount

        # Only apply where above threshold
        above = band_mag > thresh_lin
        band_mag[above] = inv_band[above]
        mag[freq_mask, :] = band_mag

    D_inv = mag * np.exp(1j * phase)
    y_inv = librosa.istft(D_inv, length=len(audio))

    result = audio * (1.0 - dry_wet) + y_inv * dry_wet
    return result.astype(np.float32)


def _overtones(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    """Add synthetic harmonics (overtones) above the fundamental.

    Parameters
    ----------
    n_harmonics  : number of harmonics to add above the fundamental (default 3)
    gain_db      : overall gain of the added harmonics (default -12 dB)
    low_hz       : only add overtones when the fundamental is above this Hz (unused
                   in this simple implementation — kept for forward compatibility)
    """
    try:
        import librosa
    except ImportError:
        return clip

    n_harmonics = max(1, int(fx.get('n_harmonics', 3)))
    gain_db     = np.clip(_resolve(fx.get('gain_db', -12), -12), -60, 12)
    gain_lin    = 10.0 ** (gain_db / 20.0)

    result = clip.astype(np.float32).copy()

    for h in range(2, n_harmonics + 2):
        # Pitch up by log2(h) octaves = h semitones ratio
        n_steps = round(12.0 * np.log2(h))
        try:
            harmonic = librosa.effects.pitch_shift(
                clip.astype(np.float32), sr=sr, n_steps=float(n_steps)
            )
        except Exception:
            continue
        # Each successive harmonic is quieter
        h_gain = gain_lin / (h - 1)
        # Align lengths
        min_len = min(len(result), len(harmonic))
        result[:min_len] += harmonic[:min_len] * h_gain

    return result.astype(np.float32)


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
