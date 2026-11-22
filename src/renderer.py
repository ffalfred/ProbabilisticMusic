import os
import subprocess
import numpy as np
import soundfile as sf
from src.envelope import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.mixer    import mix_events, _stretch_mix_by_tempo
from src.fx       import apply_section_fx, apply_global_fx
from src.dsp      import env_mul, pad_frames
from src.loudness import finish, options_from
from src.articulations import apply_mix_fermatas


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


# Score lists whose entries can be muted in the editor (events, dynamics and
# articulations are skipped where they are used)
_MUTABLE = ('tempo', 'phrases', 'note_rel', 'fx_ranges', 'fx_sections')


def drop_muted(score: dict) -> dict:
    """The score without its muted tempo ranges, phrases, note relations and
    FX zones, so a saved score renders like the editor plays it."""
    if not any(isinstance(score.get(k), list) and any(isinstance(x, dict) and x.get('muted')
                                                      for x in score[k]) for k in _MUTABLE):
        return score
    out = dict(score)
    for k in _MUTABLE:
        if isinstance(score.get(k), list):
            out[k] = [x for x in score[k] if not (isinstance(x, dict) and x.get('muted'))]
    return out


def _apply_phrase_tempo(score: dict) -> dict:
    """Merge phrase tempo_factors into score['tempo'] so the single stretch pass handles both.
    Muted entries are dropped first (drop_muted): every render path calls this.

    Phrase tempo_factor is a CONSTANT multiplier across the phrase (not a ramp),
    so we explicitly mark it shape='step'.
    """
    score = drop_muted(score)
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


def render_mix(score: dict, bank: dict, events: list, sr: int,
               base: np.ndarray = None) -> tuple:
    """Render events over the base and return (mix, tempo_map).

    Shared by the CLI renderer and the editor server so every route produces
    the same audio. Expects phrase tempos already merged (_apply_phrase_tempo).
    The mix keeps the level the performance produced — it is not normalised;
    src.loudness.finish applies the safety brake / export adjustment.
    """
    score = drop_muted(score)

    # 1. Mix everything in SCORE TIME — no tempo warping anywhere inside mix_events.
    mix = mix_events(events, bank, sr, score, base)

    # 2. Stretch the rendered mix through tempo ranges. Length may grow/shrink.
    #    Returns a score→real tempo map used to remap everything else.
    mix, tempo_map = _stretch_mix_by_tempo(mix, sr, score.get('tempo', []))

    # 2b. Whole-mix fermatas: the piece waits. Inserts the held sound and
    #     makes the tempo map stand still there, so everything below (and the
    #     editor's cursor) follows.
    mix, tempo_map = apply_mix_fermatas(mix, sr, score.get('articulations', []), tempo_map, _score_to_real)

    # 3. FX applied AFTER stretch, in real time, so reverb tails don't get
    #    phase-vocoded and seam discontinuities are avoided.
    mix = apply_section_fx(mix, sr, score.get('fx_sections', []), tempo_map, _score_to_real)
    mix = apply_global_fx(mix, sr, score.get('fx_global', []))

    # 4. Envelopes: positions authored in score time → remap to real time.
    #    With golems active the golem's gain dimension carries the dynamics,
    #    but phrase gain/fades still apply.
    _golem_active = bool(score.get('_state_trace')) and bool(score.get('golems'))
    if not _golem_active:
        dynamics = score.get('dynamics', [])
        if dynamics:
            mix = env_mul(mix, build_dynamics_envelope(len(mix), sr, _remap_dynamics(dynamics, tempo_map)))

    phrases = score.get('phrases', [])
    if phrases:
        mix = env_mul(mix, build_phrase_envelope(len(mix), sr, _remap_phrases(phrases, tempo_map)))

    # duck_key: a specific sample ducks the entire mix
    dk = score.get('duck_key')
    sounding = [e for e in events if not e.get('muted')]
    if dk and dk.get('enabled') and dk.get('key') and sounding:
        mix = env_mul(mix, build_duck_envelope(
            len(mix), sr, _remap_events(sounding, tempo_map),
            trigger_fn=lambda ev: ev.get('sample') == dk['key'],
            amount_db=dk.get('amount_db', -10.0),
            attack=dk.get('attack', 0.01),
            release=dk.get('release', 0.3),
        ))

    # 5. silence_end: seconds of silence after the piece
    tail = int(float(score.get('silence_end') or 0) * sr)
    if tail > 0:
        mix = pad_frames(mix, len(mix) + tail)

    return mix, tempo_map


def render(score: dict, bank: dict, events: list, sr: int, base: np.ndarray = None,
           wav_path: str = None, loudness: dict = None):
    """Render to a file. `loudness` is config.yaml's output block:
    {brake: true, adjust: none|source|target, target_lufs: -14}."""
    score = _apply_phrase_tempo(score)
    mix, tempo_map = render_mix(score, bank, events, sr, base)
    mix, report = finish(mix, sr, source=base, **options_from(loudness))
    score['_tempo_map'] = tempo_map
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
    print(describe_loudness(report))


def describe_loudness(report: dict) -> str:
    """One line for the user: level, adjustment, brake, peak."""
    def f(v):
        return 'silent' if v is None else f"{v:.1f}"
    parts = [f"loudness {f(report.get('lufs'))} LUFS"]
    if report.get('gain_db'):
        parts.append(f"adjusted {report['gain_db']:+.1f} dB")
    if report.get('brake_db'):
        parts.append(f"brake −{report['brake_db']:.1f} dB")
    pk = report.get('peak_db')
    if pk is not None and pk > 0:
        parts.append(f"peaks +{pk:.1f} dB over max (will clip)")
    else:
        parts.append(f"peak {f(pk)} dB")
    return ', '.join(parts)
