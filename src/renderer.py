import os
import subprocess
import numpy as np
import soundfile as sf
from src.envelope import build_dynamics_envelope
from src.mixer    import mix_events, normalise

def render(score: dict, bank: dict, events: list, sr: int, base: np.ndarray = None,
           wav_path: str = None):
    mix = mix_events(events, bank, sr, score, base)

    dynamics = score.get('dynamics', [])
    if dynamics:
        env  = build_dynamics_envelope(len(mix), sr, dynamics)
        mix *= env

    mix = normalise(mix)
    os.makedirs('output', exist_ok=True)

    base_track = score['base_track']
    is_video   = base_track.lower().endswith('.mp4')
    wav_path   = wav_path or 'output/output.wav'

    sf.write(wav_path, mix, sr)

    if is_video:
        out_path = wav_path.replace('.wav', '.mp4')
        subprocess.run([
            'ffmpeg', '-y',
            '-i', base_track,
            '-i', wav_path,
            '-c:v', 'copy',
            '-map', '0:v:0',
            '-map', '1:a:0',
            out_path
        ], check=True)
        os.remove(wav_path)
        print(f"rendered → {out_path}  ({len(mix)/sr:.1f}s)")
    else:
        print(f"rendered → {wav_path}  ({len(mix)/sr:.1f}s)")