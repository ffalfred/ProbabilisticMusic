import os
import subprocess
import numpy as np
import soundfile as sf
from src.envelope import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.mixer    import mix_events, normalise, _stretch_mix_by_tempo
from src.fx       import apply_section_fx, apply_global_fx


def _neutralise_score(score: dict, events: list):
    """Return (score, events) with ALL expressive timing stripped.

    Used by the "performance-neutral" render mode so the output follows
    the raw score grid without accelerando/ritardando, articulation
    length changes, arpeggio stagger, or per-event timing jitter.

    What's stripped:
      - score['tempo']             → [] (no global tempo ramps)
      - phrase['tempo_factor']     → 1.0 (constant per phrase)
      - score['articulations']     → [] (no staccato/legato/fermata)
      - score['note_rel']          → [] (no arpeggio stagger, no glissando time-warp)
    What's zeroed per event:
      - event['timing_offset_ms']  → 0.0 (no Kalman timing jitter)
      - event['attack_shape']      → 0.5 (neutral fade)
      - event['release_shape']     → 0.5 (neutral fade)

    Does NOT touch pitch, gain, dynamics envelopes, FX, or any Kalman
    dimension other than timing.
    """
    # Shallow copy so we don't mutate the caller's score dict
    score2 = dict(score)
    score2['tempo']         = []
    score2['articulations'] = []
    score2['note_rel']      = []
    if score.get('phrases'):
        score2['phrases'] = [dict(p, tempo_factor=1.0) for p in score['phrases']]
    # Events get timing-related fields neutralised
    events2 = []
    for ev in events:
        e2 = dict(ev)
        e2['timing_offset_ms'] = 0.0
        e2['attack_shape']     = 0.5
        e2['release_shape']    = 0.5
        events2.append(e2)
    return score2, events2


def _apply_phrase_tempo(score: dict) -> dict:
    """Merge phrase tempo_factors into score['tempo'] so the single stretch pass handles both.

    Phrase tempo_factor is a CONSTANT multiplier across the phrase (not a ramp),
    so we explicitly mark it shape='step'.
    """
    phrase_tempos = [
        {'from': p['from'], 'to': p['to'], 'factor': p['tempo_factor'], 'shape': 'step'}
        for p in score.get('phrases', [])
        if abs(p.get('tempo_factor', 1.0) - 1.0) > 1e-4
    ]
    if not phrase_tempos:
        return score
    merged = dict(score)
    merged['tempo'] = score.get('tempo', []) + phrase_tempos
    return merged


def _score_to_real(score_t: float, tempo_map: list) -> float:
    """Linearly interpolate a score-time position to its real-time position."""
    if not tempo_map:
        return score_t
    if score_t <= tempo_map[0][0]:
        return tempo_map[0][1]
    for (s0, r0), (s1, r1) in zip(tempo_map[:-1], tempo_map[1:]):
        if score_t <= s1:
            if s1 == s0:
                return r0
            return r0 + (score_t - s0) * (r1 - r0) / (s1 - s0)
    s_last, r_last = tempo_map[-1]
    return r_last + (score_t - s_last)


def _remap_dynamics(dynamics: list, tempo_map: list) -> list:
    out = []
    for d in dynamics:
        d2 = dict(d)
        if 't'    in d: d2['t']    = _score_to_real(float(d['t']),    tempo_map)
        if 'from' in d: d2['from'] = _score_to_real(float(d['from']), tempo_map)
        if 'to'   in d: d2['to']   = _score_to_real(float(d['to']),   tempo_map)
        out.append(d2)
    return out


def _remap_phrases(phrases: list, tempo_map: list) -> list:
    out = []
    for p in phrases:
        p2 = dict(p)
        p2['from'] = _score_to_real(float(p['from']), tempo_map)
        p2['to']   = _score_to_real(float(p['to']),   tempo_map)
        out.append(p2)
    return out


def _remap_events(events: list, tempo_map: list) -> list:
    out = []
    for ev in events:
        e2 = dict(ev)
        e2['t'] = _score_to_real(float(ev['t']), tempo_map)
        out.append(e2)
    return out


def render(score: dict, bank: dict, events: list, sr: int, base: np.ndarray = None,
           wav_path: str = None):
    score = _apply_phrase_tempo(score)

    # 1. Mix everything in SCORE TIME — no tempo warping anywhere inside mix_events.
    mix = mix_events(events, bank, sr, score, base)

    # 2. Stretch the rendered mix through tempo ranges. Length may grow/shrink.
    #    Returns a score→real tempo map used to remap everything else.
    mix, tempo_map = _stretch_mix_by_tempo(mix, sr, score.get('tempo', []))
    score['_tempo_map'] = tempo_map

    # 3. FX applied AFTER stretch, in real time, so reverb tails don't get
    #    phase-vocoded and seam discontinuities are avoided.
    mix = apply_section_fx(mix, sr, score.get('fx_sections', []))
    mix = apply_global_fx(mix, sr, score.get('fx_global', []))

    # 4. Envelopes: positions authored in score time → remap to real time.
    _golem_active = bool(score.get('_state_trace')) and bool(score.get('golems'))
    if not _golem_active:
        dynamics = score.get('dynamics', [])
        if dynamics:
            env = build_dynamics_envelope(len(mix), sr, _remap_dynamics(dynamics, tempo_map))
            mix *= env

        phrases = score.get('phrases', [])
        if phrases:
            mix *= build_phrase_envelope(len(mix), sr, _remap_phrases(phrases, tempo_map))

    # duck_key: a specific sample ducks the entire mix
    dk = score.get('duck_key')
    if dk and dk.get('enabled') and dk.get('key') and events:
        mix *= build_duck_envelope(
            len(mix), sr, _remap_events(events, tempo_map),
            trigger_fn=lambda ev: ev.get('sample') == dk['key'],
            amount_db=dk.get('amount_db', -10.0),
            attack=dk.get('attack', 0.01),
            release=dk.get('release', 0.3),
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
