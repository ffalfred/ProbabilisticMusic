import os
import tempfile
import subprocess
import numpy as np
import soundfile as sf

def apply_fx(clip: np.ndarray, sr: int, fx_list: list) -> np.ndarray:
    for fx in fx_list:
        if fx['type'] == 'delay':
            clip = _delay(clip, sr, fx)
        elif fx['type'] == 'reverb':
            clip = _reverb(clip, sr, fx)
        elif fx['type'] == 'overdrive':
            clip = _overdrive(clip, sr, fx)
        elif fx['type'] == 'flanger':
            clip = _flanger(clip, sr, fx)
        elif fx['type'] == 'pitch':
            clip = _pitch(clip, sr, fx)
        elif fx['type'] == 'compress':
            clip = _compress(clip, sr, fx)
        elif fx['type'] == 'eq':
            clip = _eq(clip, sr, fx)
    return clip

def _delay(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay_sec = fx.get('delay_sec', 0.3)
    feedback  = fx.get('feedback',  0.4)

    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    subprocess.run([
        'sox', tmp_in, tmp_out,
        'echo',
        '0.8', '0.9',
        str(delay_sec * 1000),  str(feedback),
        str(delay_sec * 2000),  str(feedback ** 2),
        str(delay_sec * 3000),  str(feedback ** 3),
    ], check=True)

    return _read_and_clean(tmp_in, tmp_out)

def _reverb(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    reverberance = fx.get('reverberance', 50)  # 0-100
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)

    subprocess.run([
        'sox', tmp_in, tmp_out,
        'reverb', str(reverberance)
    ], check=True)

    return _read_and_clean(tmp_in, tmp_out)

def _overdrive(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    gain   = fx.get('gain',   20)   # 0–100
    colour = fx.get('colour', 20)   # 0–100
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'overdrive', str(gain), str(colour)], check=True)
    return _read_and_clean(tmp_in, tmp_out)

def _flanger(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    delay    = fx.get('delay_ms', 0)    # 0–30 ms
    depth    = fx.get('depth_ms', 2)    # 0–10 ms
    speed    = fx.get('speed_hz', 0.5)  # 0.1–10 Hz
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'flanger',
        str(delay), str(depth), '0', '71', str(speed), 'sine', 'linear'
    ], check=True)
    return _read_and_clean(tmp_in, tmp_out)

def _pitch(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    cents = fx.get('cents', 0)   # 100 = +1 semitone, -1200 = -1 octave
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run(['sox', tmp_in, tmp_out, 'pitch', str(cents)], check=True)
    return _read_and_clean(tmp_in, tmp_out)

def _compress(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    threshold  = fx.get('threshold_db', -20)   # dB, onset of compression
    ratio      = max(1.0, fx.get('ratio', 4))  # compression ratio (e.g. 4 = 4:1)
    attack     = fx.get('attack',  0.01)        # seconds
    release    = fx.get('release', 0.3)         # seconds
    makeup     = fx.get('makeup_db', 0)         # output gain after compression
    above_out  = threshold + (0 - threshold) / ratio
    transfer   = f"6:-80,-80,{threshold},{threshold},0,{above_out:.1f}"
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'compand',
        f"{attack},{release}", transfer, str(makeup)
    ], check=True)
    return _read_and_clean(tmp_in, tmp_out)

def _eq(clip: np.ndarray, sr: int, fx: dict) -> np.ndarray:
    freq    = fx.get('freq_hz',  1000)   # centre frequency in Hz
    gain    = fx.get('gain_db',  0)      # boost (+) or cut (-) in dB
    q       = fx.get('q',        1.0)    # bandwidth (higher = narrower)
    tmp_in, tmp_out = _tmp_paths()
    sf.write(tmp_in, clip, sr)
    subprocess.run([
        'sox', tmp_in, tmp_out, 'equalizer',
        str(freq), f"{q}q", str(gain)
    ], check=True)
    return _read_and_clean(tmp_in, tmp_out)

def _tmp_paths() -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_in = f.name
    tmp_out = tmp_in.replace('.wav', '_out.wav')
    return tmp_in, tmp_out

def _read_and_clean(tmp_in: str, tmp_out: str) -> np.ndarray:
    result, _ = sf.read(tmp_out, dtype='float32')
    if result.ndim == 2:
        result = result.mean(axis=1)
    os.remove(tmp_in)
    os.remove(tmp_out)
    return result