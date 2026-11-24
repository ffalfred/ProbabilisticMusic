import numpy as np
import librosa
from scipy.signal import butter, sosfilt
from src.envelope import apply_fade, build_duck_envelope, build_density_scale, DEFAULT_FADE_CURVE
from src.fx       import apply_fx, apply_zone, _band_split, reverb_wet
from src.pitch    import resolve_event_pitch, apply_pitch_shift, apply_noterel_to_mix
from src.stretch  import time_stretch
from src.articulations import match_events, next_gaps, shape_event, accent_event, apply_mix_marks
from src import render_cache
from src.dsp      import as_frames, to_channels, pad_frames, fit_frames, env_mul, per_channel


# ─── Golem state → mix modulation ─────────────────────────────────────────────
# Interpolate the golem trace over the mix timeline and apply time-varying
# gain, brightness, filter and reverb in a single pass after events are mixed.

def _interp_dim_envelope(trace: list, n: int, sr: int, dim_idx: int) -> np.ndarray:
    """Linear-interp a single state dim across the audio's sample timeline."""
    anchor_x = np.array([float(s['t']) * sr for s in trace], dtype=np.float64)
    x_full   = np.arange(n, dtype=np.float64)
    vals     = np.array([float(s['sample'][dim_idx]) for s in trace], dtype=np.float64)
    return np.interp(x_full, anchor_x, vals).astype(np.float32)


def _apply_seg_filter(base: np.ndarray, sr: int, cutoff_env: np.ndarray,
                      res_env: np.ndarray = None, n_segments: int = 16) -> np.ndarray:
    """Apply a time-varying lowpass filter to the base via chunked crossfades.
    cutoff_env: per-sample Hz values (will be sampled at segment midpoints).
    res_env:    optional per-sample resonance 0..1 (mapped to Q 0.5..10).
    """
    from scipy.signal import butter, sosfilt
    n = len(base)
    if n < sr // 10:
        return base
    seg_len = max(1, n // n_segments)
    xfade = min(int(0.03 * sr), seg_len // 4)
    if base.ndim == 1:
        out = np.zeros_like(base)
    else:
        out = np.zeros_like(base)

    def _process(clip, cut, q):
        cut = max(20.0, min(cut, sr / 2 - 1))
        # Simple 2nd-order LP; resonance adjusts Q via a series resonant shelf (approx)
        sos = butter(2, cut, btype='low', fs=sr, output='sos')
        y = sosfilt(sos, clip).astype(np.float32) if clip.ndim == 1 \
            else np.stack([sosfilt(sos, clip[:, ch]) for ch in range(clip.shape[1])], axis=1).astype(np.float32)
        if q is not None and q > 0.05:
            # Add a mild resonant peak at the cutoff by EQ boost
            try:
                from scipy.signal import iirpeak
                b, a = iirpeak(cut / (sr / 2.0), 1.0 + q * 8.0)
                from scipy.signal import tf2sos, sosfilt as _sf
                sos_p = tf2sos(b, a)
                if clip.ndim == 1:
                    y = (y + 0.3 * q * _sf(sos_p, clip).astype(np.float32)).astype(np.float32)
                else:
                    peak = np.stack([_sf(sos_p, clip[:, ch]) for ch in range(clip.shape[1])], axis=1).astype(np.float32)
                    y = (y + 0.3 * q * peak).astype(np.float32)
            except Exception:
                pass
        return y

    for i in range(n_segments):
        s = i * seg_len
        e = n if i == n_segments - 1 else s + seg_len
        if s >= n:
            break
        mid = (s + e) // 2
        cut = float(cutoff_env[min(mid, n - 1)])
        q   = float(res_env[min(mid, n - 1)]) if res_env is not None else None
        seg = _process(base, cut, q)
        if i == 0:
            out[s:e] = seg[s:e]
        else:
            xf_end = min(s + xfade, e)
            ramp = np.linspace(0, 1, xf_end - s, dtype=np.float32)
            if base.ndim == 1:
                out[s:xf_end] = out[s:xf_end] * (1 - ramp) + seg[s:xf_end] * ramp
                out[xf_end:e] = seg[xf_end:e]
            else:
                out[s:xf_end] = out[s:xf_end] * (1 - ramp)[:, None] + seg[s:xf_end] * ramp[:, None]
                out[xf_end:e] = seg[xf_end:e]
    return out


def _apply_seg_shelf(base: np.ndarray, sr: int, bright_env: np.ndarray,
                     n_segments: int = 16) -> np.ndarray:
    """Apply a time-varying high-shelf gain driven by brightness (0..1).
    0.5 = flat, 0 = dark (-8 dB HF), 1 = bright (+8 dB HF)."""
    from scipy.signal import butter, sosfilt
    n = len(base)
    if n < sr // 10:
        return base
    nyq = sr / 2.0
    fc = min(4000.0 / nyq, 0.95)
    sos_hp = butter(2, fc, btype='high', output='sos')
    if base.ndim == 1:
        hf = sosfilt(sos_hp, base).astype(np.float32)
    else:
        hf = np.stack([sosfilt(sos_hp, base[:, ch]) for ch in range(base.shape[1])], axis=1).astype(np.float32)

    # Per-sample HF gain multiplier derived from brightness env (0..1)
    db_env = (bright_env - 0.5) * 16.0  # ±8 dB
    lin_delta = (10.0 ** (db_env / 20.0) - 1.0).astype(np.float32)

    # No clipping here: the mix is float; the safety brake handles overs at the end.
    if base.ndim == 1:
        return (base + hf * lin_delta).astype(np.float32)
    return (base + hf * lin_delta[:, None]).astype(np.float32)


def _apply_state_to_mix(mix: np.ndarray, sr: int, trace: list,
                        mix_dims: list = None) -> np.ndarray:
    """Apply golem state modulation to the combined mix.

    Called AFTER events are blended. Each dimension is gated by mix_dims —
    a list of dimension names the user has enabled. Default: ['gain_db'] only
    (backwards compatible).

    Wired dimensions:
      dim 0  gain_db         — amplitude envelope
      dim 1  brightness      — time-varying high-shelf EQ via _apply_seg_shelf
      dim 5  reverb_wet      — reverb added on top of the mix, at this level
                               (1 = as loud as the original); its tail rings on
      dim 6  filter_cutoff   — time-varying lowpass via _apply_seg_filter
      dim 7  filter_resonance— paired with filter_cutoff
      dim 8  stereo_width    — mid/side width: 0 mono, 0.5 as recorded, 1 twice
                               as wide (stereo pieces only)

    Per-event dimensions (applied in event loop, not here):
      dim 2  timing_offset_ms
      dim 3  attack_shape
      dim 4  release_shape

    Not yet wired (future):
      dim 9  overdrive_drive, dim 10 pitch_dev_cents, dim 11 dynamic_center
    """
    if mix is None or not trace:
        return mix
    if mix_dims is None:
        mix_dims = ['gain_db']

    n = len(mix)

    # dim 0: gain_db — amplitude envelope (existing behavior)
    if 'gain_db' in mix_dims:
        gain_db = _interp_dim_envelope(trace, n, sr, 0)
        gain_lin = (10.0 ** (gain_db / 20.0)).astype(np.float32)
        mix = env_mul(mix, gain_lin)

    # dim 1: brightness — time-varying high-shelf EQ
    if 'brightness' in mix_dims:
        bright_env = _interp_dim_envelope(trace, n, sr, 1)
        mix = _apply_seg_shelf(mix, sr, bright_env)

    # dims 6+7: filter_cutoff (Hz) + filter_resonance — time-varying lowpass
    if 'filter_cutoff' in mix_dims:
        cutoff_env = np.clip(_interp_dim_envelope(trace, n, sr, 6),
                             20.0, 0.45 * sr).astype(np.float32)
        res_env    = _interp_dim_envelope(trace, n, sr, 7)
        mix = _apply_seg_filter(mix, sr, cutoff_env, res_env)

    # dim 5: reverb_wet — reverb added on top of the mix (the original stays
    # at full level, like the Composer's reverb); the tail rings past the end
    if 'reverb_wet' in mix_dims:
        wet_env = np.clip(_interp_dim_envelope(trace, n, sr, 5), 0.0, 1.0).astype(np.float32)
        try:
            wet_full = reverb_wet(mix, sr, {'room': 0.7})      # the reverb alone, as loud as the mix
            w = np.concatenate([wet_env, np.full(max(0, len(wet_full) - n), wet_env[-1] if n else 0.0,
                                                 dtype=np.float32)])[:len(wet_full)]
            out = pad_frames(mix, len(wet_full))
            mix = out + env_mul(wet_full, w)
        except Exception:
            pass  # reverb failed; leave mix unchanged

    # dim 8: stereo_width — mid/side width (stereo pieces only)
    if 'stereo_width' in mix_dims and mix.ndim == 2 and mix.shape[1] == 2:
        width = np.clip(_interp_dim_envelope(trace, len(mix), sr, 8), 0.0, 1.0)
        side_gain = (2.0 * width).astype(np.float32)          # 0.5 → 1: as recorded
        mid  = (mix[:, 0] + mix[:, 1]) * 0.5
        side = (mix[:, 0] - mix[:, 1]) * 0.5 * side_gain
        mix = np.stack([mid + side, mid - side], axis=1).astype(np.float32)

    return mix


def _resolve_tempo_factor(f) -> float:
    """Resolve a probabilistic factor (list/dict from UI) to a plain float."""
    if isinstance(f, (list, tuple)) and len(f) == 2:
        f = (f[0] + f[1]) / 2.0
    elif isinstance(f, dict):
        f = f.get('mean', f.get('default', 1.0))
    return max(float(f or 1.0), 0.01)


def _concat_with_xfade(chunks: list, xf: int) -> np.ndarray:
    """Concatenate chunks with a short linear crossfade at every seam."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    out = chunks[0]
    for nxt in chunks[1:]:
        if len(out) < xf * 2 or len(nxt) < xf * 2:
            out = np.concatenate([out, nxt], axis=0)
            continue
        fade_out = np.linspace(1.0, 0.0, xf, dtype=np.float32)
        fade_in  = np.linspace(0.0, 1.0, xf, dtype=np.float32)
        tail = out[-xf:].copy()
        head = nxt[:xf].copy()
        if tail.ndim == 2:
            seam = tail * fade_out[:, None] + head * fade_in[:, None]
        else:
            seam = tail * fade_out + head * fade_in
        out = np.concatenate([out[:-xf], seam, nxt[xf:]], axis=0)
    return out


def _stretch_mix_by_tempo(mix: np.ndarray, sr: int, tempo_ranges: list):
    """
    Stretch sections of the mix by tempo factor. Length may change.

    Each range accepts a 'shape' field:
      - 'ramp' (default): rate ramps linearly from 1.0 at `from` to `factor` at `to`.
        This is the musically correct accelerando/ritardando — gradual.
        One Rubber Band pass over the whole ramp window with a per-sample rate
        curve (src/stretch.py), so there are no seams inside the ramp.
      - 'step': constant `factor` across the whole window.

    Returns (stretched_mix, tempo_map) where tempo_map is
    [(score_t, real_t), ...] monotonically increasing, used by the editor to
    translate between score time (musical position) and real time (wall clock).
    """
    if mix is None or len(mix) == 0:
        return mix, [(0.0, 0.0)]

    duration = len(mix) / sr

    # 1. Resolve ranges
    resolved = []
    for rng in tempo_ranges or []:
        t0 = max(0.0, float(rng.get('from', 0.0)))
        t1 = min(duration, float(rng.get('to', 0.0)))
        if t1 > t0:
            resolved.append({
                't0':     t0,
                't1':     t1,
                'factor': _resolve_tempo_factor(rng.get('factor', 1.0)),
                'shape':  rng.get('shape', 'ramp'),
            })

    if not resolved:
        return (mix.astype(np.float32, copy=False),
                [(0.0, 0.0), (float(duration), float(duration))])

    # 2. Effective rate at any score time = product of all overlapping ranges.
    #    Step contributes a constant; ramp contributes 1.0 + s*(factor-1.0).
    def rate_at(s):
        r = 1.0
        for rng in resolved:
            if rng['t0'] <= s < rng['t1']:
                if rng['shape'] == 'ramp':
                    pos = (s - rng['t0']) / (rng['t1'] - rng['t0'])
                    local = 1.0 + pos * (rng['factor'] - 1.0)
                else:
                    local = rng['factor']
                r *= max(float(local), 0.01)
        return max(r, 0.01)

    # 3. Boundaries: range edges only. NO sub-division of ramps — each ramp
    #    window is processed as a single segment with a rate curve.
    boundary_set = {0.0, float(duration)}
    for r in resolved:
        boundary_set.add(r['t0'])
        boundary_set.add(r['t1'])
    boundaries = sorted(boundary_set)

    segments = []  # [(t0, t1, has_ramp, const_rate)]
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        if b - a < 1e-6:
            continue
        # has_ramp: any ramp range covers this segment
        has_ramp = any(rng['shape'] == 'ramp' and rng['t0'] <= a and rng['t1'] >= b
                       for rng in resolved)
        # Mid-point rate (used for the constant-rate segment path)
        mid = (a + b) / 2.0
        const_rate = rate_at(mid)
        segments.append((a, b, has_ramp, const_rate))

    # 4. Stretch each segment, build the tempo map, concat with short crossfades.
    #    Seams only fall at range edges, not inside ramps; a short crossfade
    #    hides the change of rate there.
    XFADE_MS = 10
    xf = max(1, int(XFADE_MS * sr / 1000))

    out_chunks = []
    tempo_map = [(0.0, 0.0)]
    out_len = 0          # length of the joined output so far (seams overlap by xf)

    for score_t0, score_t1, has_ramp, const_rate in segments:
        i0 = int(score_t0 * sr)
        i1 = int(score_t1 * sr)
        chunk = mix[i0:i1]
        if len(chunk) == 0:
            continue

        if (not has_ramp and abs(const_rate - 1.0) < 1e-3) or len(chunk) < 2048:
            stretched = chunk.astype(np.float32, copy=False)
        elif has_ramp:
            # One pass across the whole ramp window with a per-sample rate
            # curve (sampled every 64 samples; the rate changes slowly).
            grid = np.arange(0, len(chunk) + 64, 64)
            grid_rate = [rate_at(score_t0 + g / sr) for g in grid]
            curve = np.interp(np.arange(len(chunk)), grid, grid_rate)
            stretched = time_stretch(chunk, sr, curve)
        else:
            # Constant-rate segment (step range or no range)
            stretched = time_stretch(chunk, sr, float(const_rate))

        # Mirror _concat_with_xfade: a crossfaded seam overlaps xf samples
        if out_chunks and out_len >= 2 * xf and len(stretched) >= 2 * xf:
            out_len += len(stretched) - xf
        else:
            out_len += len(stretched)
        out_chunks.append(stretched)
        tempo_map.append((float(score_t1), out_len / sr))

    return _concat_with_xfade(out_chunks, xf), tempo_map


def _apply_speed(clip: np.ndarray, speed: float, sr: int, pitch_lock: bool = False) -> np.ndarray:
    """Varispeed (or time-stretch with pitch_lock) a (frames, channels) clip."""
    if abs(speed - 1.0) < 1e-3:
        return clip
    if pitch_lock:
        # Time-stretch: rate > 1 → shorter, rate < 1 → longer. Pitch unchanged.
        return time_stretch(clip, sr, float(speed))
    return per_channel(lambda ch: librosa.resample(ch, orig_sr=int(sr * speed), target_sr=sr), clip)


def mix_events(events: list, bank: dict, sr: int, score: dict = None, base: np.ndarray = None) -> np.ndarray:
    silence_start  = (score or {}).get('silence_start', 0.0)
    samples_spec   = (score or {}).get('samples', {})
    articulations  = (score or {}).get('articulations', [])
    note_rels      = (score or {}).get('note_rel', [])
    _state_trace   = (score or {}).get('_state_trace', None)
    # Muted events neither sound nor trigger ducking / density scaling.
    events = [e for e in events if not e.get('muted')]

    # All audio is (frames, channels); the piece's channel count comes from
    # the base (or, without one, from the samples).
    if base is not None:
        mix = as_frames(base).copy()
    else:
        n_ch = max((as_frames(c).shape[1] for c in bank.values()), default=1)
        mix = np.zeros((int((max((e['t'] for e in events), default=0.0) + 30.0) * sr), n_ch),
                       dtype=np.float32)
    channels = mix.shape[1]

    # --- the source: base FX, then FX zones on the source (fx_ranges). Cached:
    #     the same settings on the same audio are reused between renders. ---
    base_fx   = (score or {}).get('base_fx', []) if base is not None else []
    fx_ranges = sorted((fr for fr in (score or {}).get('fx_ranges', []) if not fr.get('muted')),
                       key=lambda r: r['from'])
    if base_fx or fx_ranges:
        source = mix

        def _process_source():
            m = apply_fx(source, sr, base_fx) if base_fx else source
            for fr in fx_ranges:
                m = apply_zone(m, sr, int(fr['from'] * sr), int(fr['to'] * sr), fr['fx'], fr)
            return m

        seed = int(np.random.randint(0, 2**31 - 1))
        k = render_cache.key('source', render_cache.array_digest(source), base_fx, fx_ranges, sr)
        mix = render_cache.run(k, seed, _process_source).copy()

    # --- duck_base: duck the base track before events are added ---
    db = (score or {}).get('duck_base')
    if db and db.get('enabled') and events:
        duck_env = build_duck_envelope(
            len(mix), sr, events, trigger_fn=lambda ev: True,
            amount_db=db.get('amount_db', -6.0),
            attack=db.get('attack', 0.01),
            release=db.get('release', 0.3),
        )
        mix[:len(duck_env)] = env_mul(mix[:len(duck_env)], duck_env)

    # Event-target articulations: which marks shape which event, and how long
    # until the next event (for legato)
    event_marks = match_events(articulations, events)
    gaps = next_gaps(events)

    # --- every event's clip: processed in parallel, each with its own random
    #     stream (seeded in order, so a seed renders the same every time) and
    #     cached — an event whose sound didn't change is reused, even when it
    #     moved in time. ---
    clips = _event_clips(events, bank, sr, channels, samples_spec, event_marks, gaps, note_rels)

    for idx, event in enumerate(events):
        clip = clips[idx]

        # --- place on timeline (score time; global stretch happens post-mix) ---
        t_real = float(event['t']) + silence_start
        timing_off = event.get('timing_offset_ms')
        if timing_off:
            t_real = max(0.0, t_real + timing_off / 1000.0)

        # --- arpeggio stagger: offset events in an arpeggiate range by 30ms × rank ---
        for nr in note_rels:
            if nr.get('type') == 'arpeggiate':
                t0_nr = float(nr['from'])
                t1_nr = float(nr.get('to', t0_nr))
                if t0_nr <= float(event['t']) <= t1_nr:
                    rank = sum(1 for e in events if t0_nr <= float(e['t']) < float(event['t']))
                    t_real += rank * 0.03
                    break

        i0 = int(t_real * sr)
        i1 = i0 + len(clip)
        mix = pad_frames(mix, i1)

        # --- mix mode ---
        ev_mix_mode = event.get('mix_mode', 'layer')
        if ev_mix_mode == 'sidechain':
            # Energy-preserving blend: base*(1-blend) + clip*blend
            n_clip = len(clip)
            xf = min(int(0.03 * sr), n_clip // 4)
            blend_level = float(event.get('blend', 0.5))
            blend = np.full(n_clip, blend_level, dtype=np.float32)
            if xf > 0:
                blend[:xf]  = np.linspace(0.0, blend_level, xf, dtype=np.float32)
                blend[-xf:] = np.linspace(blend_level, 0.0, xf, dtype=np.float32)
            mix[i0:i1] = env_mul(mix[i0:i1], 1 - blend) + env_mul(clip, blend)
        else:  # 'layer'
            mix[i0:i1] += clip

    # --- single-pass golem state modulation on the combined mix ---
    # Only apply when golems are explicitly present. Without golems, the audio
    # should play clean with dynamics envelope (the traditional path).
    _has_golems = bool((score or {}).get('golems'))
    if _state_trace and _has_golems:
        mix_dims = (score or {}).get('mix_dims', ['gain_db'])
        mix = _apply_state_to_mix(mix, sr, _state_trace, mix_dims)

    # --- note relationships on the full mix (glissando pitch-slide, arpeggio roll) ---
    if note_rels:
        mix = apply_noterel_to_mix(mix, sr, note_rels)

    # --- whole-mix articulations (target: mix): staccato / accent / legato.
    #     Whole-mix fermatas insert time, so they come after the tempo
    #     stretch (src/renderer.render_mix). ---
    mix = apply_mix_marks(mix, sr, articulations)

    # --- auto_mix: scale down overlapping events ---
    am = (score or {}).get('auto_mix')
    if am and am.get('enabled') and events:
        scale = build_density_scale(
            len(mix), sr, events, samples_spec,
            mode=am.get('mode', 'sqrt'),
            silence_start=silence_start,
        )
        mix = env_mul(mix, scale)

    return mix


# Event fields that only say where an event goes, not how it sounds: an event
# that changed only these reuses its processed clip.
_PLACEMENT_KEYS = ('t', 'timing_offset_ms', 'mix_mode', 'blend', 'muted', 'label')
_EVENT_POOL = None


def _event_pool():
    global _EVENT_POOL
    if _EVENT_POOL is None:
        import os
        from concurrent.futures import ThreadPoolExecutor
        _EVENT_POOL = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2),
                                         thread_name_prefix='event')
    return _EVENT_POOL


def _event_clips(events, bank, sr, channels, samples_spec, event_marks, gaps, note_rels) -> list:
    """Processed clip of every event (see _event_clip), in event order."""
    if not events:
        return []
    from plugins import load_plugins
    load_plugins()                                   # once, before the threads
    seeds = [int(np.random.randint(0, 2**31 - 1)) for _ in events]
    digests = {name: render_cache.array_digest(bank[name])
               for name in {e['sample'] for e in events}}

    def job(idx):
        event = events[idx]
        marks = event_marks.get(idx, [])
        semitones = resolve_event_pitch(event['t'], float(event.get('pitch', 0.0)), note_rels)
        gap = gaps[idx] if any(m.get('type') == 'legato' for m in marks) else None
        sample_spec = samples_spec.get(event['sample'], {})
        sound = {k: v for k, v in event.items() if k not in _PLACEMENT_KEYS}
        k = render_cache.key('event', sound, digests[event['sample']], sample_spec,
                             marks, gap, semitones, channels, sr)
        return render_cache.run(k, seeds[idx], lambda: _event_clip(
            event, bank[event['sample']], sr, channels, marks, gap, sample_spec, semitones))

    if len(events) == 1:
        return [job(0)]
    return list(_event_pool().map(job, range(len(events))))


def _event_clip(event, sample, sr, channels, marks, gap, sample_spec, semitones) -> np.ndarray:
    """One event's sound, before placement: speed, reverse, loop,
    articulations, fades, accent, gain, effects, pitch."""
    # copy: fades and gain below work in place and must not touch the bank
    base_clip = to_channels(sample, channels).copy()

    # --- speed / layered transpositions ---
    pitch_lock = bool(event.get('pitch_lock', False))
    speeds = event.get('speeds')
    if speeds:
        layers  = [_apply_speed(base_clip.copy(), s, sr, pitch_lock) for s in speeds]
        max_len = max(len(l) for l in layers)
        clip    = sum(pad_frames(l, max_len) for l in layers)
    else:
        clip = _apply_speed(base_clip, event.get('speed', 1.0), sr, pitch_lock)

    # --- reverse ---
    if event.get('reverse', False):
        clip = clip[::-1].copy()

    # --- loop ---
    loop = event.get('loop', 0)
    if loop > 0:
        clip = np.concatenate([clip] * (loop + 1), axis=0)

    # --- articulations on this event: staccato / legato / fermata change
    #     its length, before its fades and effects (accent comes after) ---
    if marks:
        clip = shape_event(clip, sr, marks, gap)

    # --- fade edges shaped by golem's attack/release ---
    fade_in_pct  = event.get('fade_in',  sample_spec.get('fade_in',  0.05))
    fade_out_pct = event.get('fade_out', sample_spec.get('fade_out', 0.05))
    attack_shape = event.get('attack_shape')
    if attack_shape is not None:
        fade_in_pct = min(0.8, fade_in_pct * (attack_shape * 2.0))
    release_shape = event.get('release_shape')
    if release_shape is not None:
        fade_out_pct = min(0.9, fade_out_pct * (release_shape * 2.0))
    clip = apply_fade(clip, sr, fade_in_pct=fade_in_pct, fade_out_pct=fade_out_pct,
                      curve=event.get('fade_curve', sample_spec.get('fade_curve', DEFAULT_FADE_CURVE)))
    if marks:
        clip = accent_event(clip, sr, marks)

    # --- score-level gain (NOT golem state — just the score's own gain_db) ---
    gain_db = event.get('gain_db', -6.0)
    clip = clip * (10 ** (gain_db / 20.0))

    # --- composer-authored per-event FX chain (score instructions, not golem) ---
    fx_list = event.get('fx', [])
    if fx_list:
        clip = to_channels(apply_fx(clip, sr, fx_list), channels)

    # --- pitch (score-level: static or glissando — NOT golem pitch_dev) ---
    if semitones:
        clip = apply_pitch_shift(clip, sr, semitones)
    return clip.astype(np.float32, copy=False)
