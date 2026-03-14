import os
import subprocess
import tempfile
import soundfile as sf
import numpy as np

def _extract_audio(video_path: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "44100", "-ac", "1", tmp.name],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return tmp.name

def build_bank(score: dict) -> tuple[dict, int]:
    path = score['base_track']
    tmp_path = None
    if path.lower().endswith('.mp4'):
        tmp_path = _extract_audio(path)
        path = tmp_path

    base, sr = sf.read(path, dtype='float32')
    if tmp_path:
        os.remove(tmp_path)
    if base.ndim == 2:
        base = base.mean(axis=1)

    bank = {}
    for name, spec in score['samples'].items():
        i0 = int(spec['from'] * sr)
        i1 = int(spec['to']   * sr)
        bank[name] = base[i0:i1].copy()

    return bank, sr, base