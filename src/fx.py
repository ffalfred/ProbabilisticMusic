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