import os
import subprocess
import numpy as np
import soundfile as sf
from src.envelope import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.mixer    import mix_events, normalise


def _apply_phrase_tempo(score: dict) -> dict:
    """Merge phrase tempo_factors into score['tempo'] for transparent _warp_time handling."""
    phrase_tempos = [
        {'from': p['from'], 'to': p['to'], 'factor': p['tempo_factor']}
        for p in score.get('phrases', [])
        if abs(p.get('tempo_factor', 1.0) - 1.0) > 1e-4
    ]
    if not phrase_tempos:
        return score
    merged = dict(score)
    merged['tempo'] = score.get('tempo', []) + phrase_tempos
    return merged


def render(score: dict, bank: dict, events: list, sr: int, base: np.ndarray = None,
           wav_path: str = None):
    score = _apply_phrase_tempo(score)
    mix = mix_events(events, bank, sr, score, base)

    dynamics = score.get('dynamics', [])
    if dynamics:
        env  = build_dynamics_envelope(len(mix), sr, dynamics)
        mix *= env

    phrases = score.get('phrases', [])
    if phrases:
        mix *= build_phrase_envelope(len(mix), sr, phrases)

    # duck_key: a specific sample ducks the entire mix
    dk = score.get('duck_key')
    if dk and dk.get('enabled') and dk.get('key') and events:
        mix *= build_duck_envelope(
            len(mix), sr, events,
            trigger_fn=lambda ev: ev.get('sample') == dk['key'],
            amount_db=dk.get('amount_db', -10.0),
            attack=dk.get('attack', 0.01),
            release=dk.get('release', 0.3),
            tempo_ranges=score.get('tempo', []),
        )

    mix = normalise(mix)
    os.makedirs('output', exist_ok=True)

    # When using tracks: list, fall back to the first track path for video detection.
    tracks_spec = score.get('tracks', [])
    base_track = score.get('base_track') or (tracks_spec[0]['path'] if tracks_spec else None)
    is_video   = bool(base_track and base_track.lower().endswith('.mp4'))
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
