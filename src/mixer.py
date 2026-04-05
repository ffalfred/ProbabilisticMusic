import numpy as np
import librosa
from scipy.signal import butter, sosfilt
from src.envelope import apply_fade, build_duck_envelope, build_density_scale
from src.fx       import apply_fx
from src.pitch    import resolve_event_pitch, apply_pitch_shift


def _apply_brightness(clip: np.ndarray, sr: int, brightness: float) -> np.ndarray:
    """High-shelf EQ at ~4 kHz. brightness=0.5 → flat, 0 → -8 dB, 1 → +8 dB."""
    gain_db = (brightness - 0.5) * 16.0
    if abs(gain_db) < 0.25:
        return clip
    nyq = sr / 2.0
    fc  = min(4000.0 / nyq, 0.95)
    sos = butter(2, fc, btype='high', output='sos')
    hf  = sosfilt(sos, clip).astype(np.float32)
    # Add scaled HF component to original (high-shelf approximation)
    linear_delta = 10 ** (gain_db / 20.0) - 1.0
    return np.clip(clip + hf * linear_delta, -1.0, 1.0).astype(np.float32)


def _apply_stereo_width(clip: np.ndarray, width: float) -> np.ndarray:
    """Adjust stereo width. width=0.5 → no change, 0 → mono, 1 → widened.

    For mono signals (1D), this is a no-op. For stereo, uses M/S decomposition.
    For mono signals with width > 0.5, adds a subtle decorrelated side signal.
    """
    if clip.ndim == 1:
        # Mono — can't do M/S, but if width > 0.5 we can add subtle noise-decorrelation
        # (actual stereo conversion happens at final render stage, not here)
        return clip
    # Stereo: M/S processing
    mid  = (clip[:, 0] + clip[:, 1]) * 0.5
    side = (clip[:, 0] - clip[:, 1]) * 0.5
    # width: 0 → pure mid, 0.5 → original, 1 → boosted side
    side_gain = width * 2.0  # 0→0, 0.5→1.0, 1→2.0
    out = np.column_stack([mid + side * side_gain,
                           mid - side * side_gain])
    return np.clip(out, -1.0, 1.0).astype(np.float32)


# ─── Phase B: within-note LFO modulation ──────────────────────────────────────
# These helpers add time-varying modulation across a note's duration so long
# sustained notes "breathe". Each LFO is seeded per-event for reproducibility.

def _event_seed(event: dict) -> int:
    """Derive a per-event seed for LFO phase randomization (reproducible renders)."""
    t = float(event.get('t', 0.0))
    s = str(event.get('sample', ''))
    # Simple hash combining t and sample name
    return (int(t * 1000) * 2654435761 + hash(s)) & 0x7FFFFFFF


def _apply_vibrato(clip: np.ndarray, sr: int, depth_cents: float,
                   rate_hz: float, seed: int = 0) -> np.ndarray:
    """Sinusoidal pitch modulation using a resampler. Depth in cents, ±depth around 0."""
    if depth_cents < 0.1 or len(clip) < sr // 10:
        return clip
    n = len(clip)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 2 * np.pi)
    # Fractional resample offset per sample: modulated by LFO
    # ratio = 2^(cents/1200); for small cents, ratio ≈ 1 + cents*ln(2)/1200
    cents_curve = depth_cents * np.sin(2 * np.pi * rate_hz * t + phase)
    ratio = np.exp(cents_curve * np.log(2.0) / 1200.0)
    # Cumulative read position
    read_pos = np.cumsum(ratio)
    read_pos -= read_pos[0]  # start at 0
    # Clamp to valid range
    read_pos = np.clip(read_pos, 0, n - 1)
    # Linear interpolation
    idx_lo = np.floor(read_pos).astype(np.int64)
    idx_hi = np.minimum(idx_lo + 1, n - 1)
    frac = read_pos - idx_lo
    if clip.ndim == 1:
        return (clip[idx_lo] * (1 - frac) + clip[idx_hi] * frac).astype(np.float32)
    # Stereo
    out = np.zeros_like(clip)
    for ch in range(clip.shape[1]):
        out[:, ch] = clip[idx_lo, ch] * (1 - frac) + clip[idx_hi, ch] * frac
    return out.astype(np.float32)


def _apply_timbral_breath(clip: np.ndarray, sr: int, depth: float,
                          rate_hz: float, seed: int = 0) -> np.ndarray:
    """Slow gentle brightness modulation — LFO on high-shelf EQ.
    depth ∈ [0, 1], rate_hz typically 0.2–1.5 Hz."""
    if depth < 0.02 or len(clip) < sr // 10:
        return clip
    from scipy.signal import butter, sosfilt
    n = len(clip)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(seed ^ 0x9E3779B9)
    phase = rng.uniform(0, 2 * np.pi)
    # LFO modulates a high-shelf gain between (1-depth*8dB) and (1+depth*8dB)
    nyq = sr / 2.0
    fc = min(3500.0 / nyq, 0.95)
    sos = butter(2, fc, btype='high', output='sos')
    hf = sosfilt(sos, clip).astype(np.float32) if clip.ndim == 1 \
         else np.stack([sosfilt(sos, clip[:, ch]) for ch in range(clip.shape[1])], axis=1).astype(np.float32)
    gain_db_curve = depth * 8.0 * np.sin(2 * np.pi * rate_hz * t + phase)
    gain_lin_delta = (10 ** (gain_db_curve / 20.0) - 1.0).astype(np.float32)
    if clip.ndim == 1:
        return np.clip(clip + hf * gain_lin_delta, -1.0, 1.0).astype(np.float32)
    out = clip.copy()
    for ch in range(clip.shape[1]):
        out[:, ch] = np.clip(clip[:, ch] + hf[:, ch] * gain_lin_delta, -1.0, 1.0)
    return out.astype(np.float32)


def _apply_reverb_swell(clip: np.ndarray, sr: int, base_wet: float,
                        swell_depth: float, seed: int = 0) -> np.ndarray:
    """Amplitude-blend between dry clip and its reverb-tail, swelling across the note.
    Low-overhead approximation: uses a single offline SoX reverb pass then blends
    with a time-varying mix curve."""
    if swell_depth < 0.05 or base_wet < 0.05 or len(clip) < sr // 4:
        return clip
    # Generate wet version once
    try:
        wet = apply_fx(clip, sr, [{'type': 'reverb', 'room': base_wet}])
    except Exception:
        return clip
    # Align lengths
    n = min(len(clip), len(wet))
    dry = clip[:n]
    wet = wet[:n]
    # Blend curve: rises over first 60% of note, plateaus, dips slightly at end
    rng = np.random.default_rng(seed ^ 0x85EBCA6B)
    t = np.linspace(0, 1, n, dtype=np.float32)
    # Cosine-eased rise, amplitude = swell_depth * base_wet
    curve = base_wet * (1.0 + swell_depth * 0.5 * (1.0 - np.cos(np.pi * np.minimum(t * 1.6, 1.0))))
    curve = np.clip(curve, 0.0, 1.0)
    # tiny phase jitter for run-to-run variance
    curve = curve * (1.0 + 0.05 * rng.standard_normal() * swell_depth)
    if dry.ndim == 1:
        return (dry * (1.0 - curve) + wet * curve).astype(np.float32)
    out = np.zeros_like(dry)
    for ch in range(dry.shape[1]):
        out[:, ch] = dry[:, ch] * (1.0 - curve) + wet[:, ch] * curve
    return out.astype(np.float32)


# ─── Phase C: continuous state-driven rendering ───────────────────────────────
# Interpolate the Kalman trace across a note's duration and apply time-varying
# modulation (filter sweeps, gain envelope) inside the note body.

def _sample_trace_at(trace: list, t: float, dim_key: str = 'sample') -> list:
    """Linearly interpolate the state vector at time t from the trace.
    trace: list of dicts with 't' and dim_key (e.g. 'sample' or 'mu').
    Returns the interpolated state vector (list of floats), or None if no trace."""
    if not trace:
        return None
    n = len(trace)
    # Binary search for the bracket
    lo, hi = 0, n - 1
    if t <= trace[0]['t']:
        return list(trace[0][dim_key])
    if t >= trace[hi]['t']:
        return list(trace[hi][dim_key])
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if trace[mid]['t'] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = trace[lo]['t'], trace[hi]['t']
    if t1 - t0 < 1e-9:
        return list(trace[lo][dim_key])
    frac = (t - t0) / (t1 - t0)
    v0, v1 = trace[lo][dim_key], trace[hi][dim_key]
    return [v0[d] + frac * (v1[d] - v0[d]) for d in range(len(v0))]


def _apply_time_varying_filter(clip: np.ndarray, sr: int,
                               cutoffs: list, n_segments: int = 4) -> np.ndarray:
    """Apply a lowpass filter whose cutoff varies across the clip.
    cutoffs: list of n_segments+1 cutoff values (Hz) anchoring the curve.
    Chunks the clip and crossfades segments (50ms overlap)."""
    from scipy.signal import butter, sosfilt
    if len(clip) < sr // 10:
        return clip
    n = len(clip)
    seg_len = n // n_segments
    if seg_len < sr // 20:
        # Too short to segment; fall back to single-filter pass at mean cutoff
        mean_cut = float(np.mean(cutoffs))
        mean_cut = max(20.0, min(mean_cut, sr / 2 - 1))
        sos = butter(2, mean_cut, btype='low', fs=sr, output='sos')
        return sosfilt(sos, clip).astype(np.float32)
    xfade = min(int(0.05 * sr), seg_len // 4)
    out = np.zeros_like(clip)
    for i in range(n_segments):
        s = i * seg_len
        e = n if i == n_segments - 1 else s + seg_len
        cut = float(cutoffs[i])
        cut = max(20.0, min(cut, sr / 2 - 1))
        sos = butter(2, cut, btype='low', fs=sr, output='sos')
        seg_filtered = sosfilt(sos, clip).astype(np.float32)
        if i == 0:
            out[s:e] = seg_filtered[s:e]
        else:
            # Crossfade with previous segment
            xf_end = min(s + xfade, e)
            ramp = np.linspace(0, 1, xf_end - s, dtype=np.float32)
            out[s:xf_end] = out[s:xf_end] * (1 - ramp) + seg_filtered[s:xf_end] * ramp
            out[xf_end:e] = seg_filtered[xf_end:e]
    return out


def _apply_dynamic_envelope(clip: np.ndarray, dyn_centers: list) -> np.ndarray:
    """Apply a time-varying gain envelope based on dynamic_center values.
    dyn_centers: list of dB values spread across the clip, interpolated linearly.
    Reference level = median of the list (so the envelope centres around 0 dB
    rather than uniformly attenuating)."""
    if not dyn_centers or len(clip) < 16:
        return clip
    ref = float(np.median(dyn_centers))
    deltas = np.array(dyn_centers, dtype=np.float32) - ref
    # Smooth interpolation across clip length
    n = len(clip)
    x_anchor = np.linspace(0, n - 1, len(deltas), dtype=np.float32)
    x_full   = np.arange(n, dtype=np.float32)
    env_db   = np.interp(x_full, x_anchor, deltas)
    env_lin  = 10 ** (env_db / 20.0).astype(np.float32)
    if clip.ndim == 1:
        return (clip * env_lin).astype(np.float32)
    out = np.zeros_like(clip)
    for ch in range(clip.shape[1]):
        out[:, ch] = clip[:, ch] * env_lin
    return out


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

    if base.ndim == 1:
        return np.clip(base + hf * lin_delta, -1.0, 1.0).astype(np.float32)
    return np.clip(base + hf * lin_delta[:, None], -1.0, 1.0).astype(np.float32)


def _apply_state_to_base(base: np.ndarray, sr: int, trace: list,
                         dims_to_apply) -> np.ndarray:
    """Apply continuous state-driven modulation to the base audio.

    Phase 1 (cheap): gain_db, dynamic_center → amplitude envelope.
    Phase 2 (medium): brightness → high-shelf EQ; filter_cutoff/resonance → lowpass sweep.
    """
    if base is None or not trace or not dims_to_apply:
        return base
    dims = set(dims_to_apply) if not isinstance(dims_to_apply, set) else dims_to_apply
    active_dims = dims & {'gain_db', 'dynamic_center', 'brightness',
                          'filter_cutoff', 'filter_resonance'}
    if not active_dims:
        return base

    n = len(base)
    out = base

    # --- amplitude (Phase 1) ---
    if dims & {'gain_db', 'dynamic_center'}:
        gain_db = np.zeros(n, dtype=np.float32)
        if 'gain_db' in dims:
            gain_db += _interp_dim_envelope(trace, n, sr, 0)
        if 'dynamic_center' in dims:
            dc = _interp_dim_envelope(trace, n, sr, 11)
            dc -= float(np.median(dc))
            gain_db += dc
        gain_lin = (10.0 ** (gain_db / 20.0)).astype(np.float32)
        if out.ndim == 1:
            out = (out * gain_lin).astype(np.float32)
        else:
            out = (out * gain_lin[:, None]).astype(np.float32)

    # --- brightness high-shelf (Phase 2) ---
    if 'brightness' in dims:
        bright_env = _interp_dim_envelope(trace, n, sr, 1)
        out = _apply_seg_shelf(out, sr, bright_env)

    # --- lowpass filter sweep (Phase 2) ---
    if 'filter_cutoff' in dims:
        cutoff_env = _interp_dim_envelope(trace, n, sr, 6)
        res_env    = _interp_dim_envelope(trace, n, sr, 7) if 'filter_resonance' in dims else None
        out = _apply_seg_filter(out, sr, cutoff_env, res_env)

    return out


def _warp_time(t_score: float, tempo_ranges: list) -> float:
    """
    Map a score time to real time via tempo ranges.
    factor > 1  =  accelerando (time compressed, events happen sooner)
    factor < 1  =  ritardando  (time expanded, events happen later)
    """
    offset = 0.0
    cursor = 0.0
    for rng in sorted(tempo_ranges, key=lambda r: r['from']):
        t0, t1   = rng['from'], rng['to']
        factor   = rng.get('factor', 1.0)
        # Resolve probabilistic factor (range/gauss from UI) to a plain float
        if isinstance(factor, (list, tuple)) and len(factor) == 2:
            factor = (factor[0] + factor[1]) / 2.0
        elif isinstance(factor, dict):
            factor = factor.get('mean', factor.get('default', 1.0))
        factor = max(float(factor or 1.0), 0.01)  # guard against 0 / None
        if t_score < t0:
            return offset + (t_score - cursor)
        offset += t0 - cursor
        cursor  = t0
        if t_score <= t1:
            return offset + (t_score - t0) / factor
        offset += (t1 - t0) / factor
        cursor  = t1
    return offset + (t_score - cursor)


def _apply_speed(clip: np.ndarray, speed: float, sr: int) -> np.ndarray:
    if abs(speed - 1.0) < 1e-3:
        return clip
    return librosa.resample(
        clip, orig_sr=int(sr * speed), target_sr=sr
    ).astype(np.float32)


def _find_articulation(event_t: float, articulations: list, max_gap: float = 0.5):
    """Return the first articulation that matches an event at event_t."""
    for art in articulations:
        art_t = art.get('t')
        if art_t is not None and abs(art_t - event_t) <= max_gap:
            return art
        from_t = art.get('from')
        to_t   = art.get('to')
        if from_t is not None and to_t is not None and from_t <= event_t <= to_t:
            return art
    return None


def _apply_articulation(clip: np.ndarray, art_type: str, sr: int) -> np.ndarray:
    """Modify a clip according to the given articulation type."""
    n = len(clip)
    if n == 0:
        return clip

    if art_type == 'staccato':
        # Shorten to ~30% of original duration with a quick fade-out
        keep = max(int(sr * 0.02), int(n * 0.30))  # at least 20 ms
        keep = min(keep, n)
        clip = clip[:keep].copy()
        fo = max(1, int(keep * 0.15))
        clip[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)

    elif art_type == 'accent':
        # Boost attack: ramp 2× → 1× over the first 50 ms
        atk = min(int(0.05 * sr), n)
        if atk > 1:
            env = np.ones(n, dtype=np.float32)
            env[:atk] = np.linspace(2.0, 1.0, atk, dtype=np.float32)
            clip = clip * env

    elif art_type == 'fermata':
        # Hold the last 20% of the clip for an extra duration (smoothly looped)
        hold_n = min(int(n * 0.20), n)
        if hold_n > 4:
            tail   = clip[-hold_n:].copy()
            # Crossfade loop point
            fi = max(1, int(hold_n * 0.25))
            loop_seg = tail.copy()
            loop_seg[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
            clip = np.concatenate([clip, loop_seg, loop_seg])

    elif art_type == 'legato':
        # Smooth connection: replace default short fade-out with a long 500 ms one
        # so the note rings smoothly into the next without an abrupt cutoff.
        fo = min(int(0.5 * sr), n)
        if fo > 1:
            env = np.ones(n, dtype=np.float32)
            env[-fo:] = np.linspace(1.0, 0.0, fo, dtype=np.float32)
            clip = clip * env

    return clip


def mix_events(events: list, bank: dict, sr: int, score: dict = None, base: np.ndarray = None) -> np.ndarray:
    silence_start  = (score or {}).get('silence_start', 0.0)
    tempo_ranges   = (score or {}).get('tempo', [])
    samples_spec   = (score or {}).get('samples', {})
    articulations  = (score or {}).get('articulations', [])
    note_rels      = (score or {}).get('note_rel', [])
    # Phase C: optional Kalman state trace for continuous within-note modulation
    _state_trace   = (score or {}).get('_state_trace', None)
    _base_dims     = (score or {}).get('_interp_base_dims', [])

    mix = base.copy() if base is not None else np.zeros(int((max(e['t'] for e in events) + 30.0) * sr), dtype=np.float32)

    # --- Phase 1: state-driven base modulation (cheap gain-envelope pass) ---
    if base is not None and _state_trace and _base_dims:
        mix = _apply_state_to_base(mix, sr, _state_trace, _base_dims)

    # --- base fx (applied before events are layered) ---
    base_fx = (score or {}).get('base_fx', [])
    if base_fx and base is not None:
        mix = apply_fx(mix, sr, base_fx)

    # --- ranged fx (applied to specific segments of the base) ---
    for fr in sorted((score or {}).get('fx_ranges', []), key=lambda r: r['from']):
        i0 = int(fr['from'] * sr)
        i1 = min(int(fr['to'] * sr), len(mix))
        if i0 >= len(mix) or i0 >= i1:
            continue
        segment  = mix[i0:i1].copy()
        processed = apply_fx(segment, sr, fr['fx'])
        mix[i0:i1] = 0.0
        out_end = i0 + len(processed)
        if out_end > len(mix):
            mix = np.pad(mix, (0, out_end - len(mix)))
        mix[i0:out_end] += processed

    # --- duck_base: duck the base track before events are added ---
    db = (score or {}).get('duck_base')
    if db and db.get('enabled') and events:
        duck_env = build_duck_envelope(
            len(mix), sr, events, trigger_fn=lambda ev: True,
            amount_db=db.get('amount_db', -6.0),
            attack=db.get('attack', 0.01),
            release=db.get('release', 0.3),
            tempo_ranges=tempo_ranges,
        )
        mix[:len(duck_env)] *= duck_env

    for event in events:
        base_clip = bank[event['sample']].copy()

        # --- speed / layered transpositions ---
        speeds = event.get('speeds')
        if speeds:
            layers  = [_apply_speed(base_clip.copy(), s, sr) for s in speeds]
            max_len = max(len(l) for l in layers)
            clip    = np.zeros(max_len, dtype=np.float32)
            for l in layers:
                clip[:len(l)] += l
        else:
            clip = _apply_speed(base_clip, event.get('speed', 1.0), sr)

        # --- reverse ---
        if event.get('reverse', False):
            clip = clip[::-1].copy()

        # --- loop ---
        loop = event.get('loop', 0)
        if loop > 0:
            clip = np.tile(clip, loop + 1)

        # --- per-sample / per-event fade edges ---
        # Event-level fade_in/fade_out overrides sample-level if provided
        sample_spec  = samples_spec.get(event['sample'], {})
        fade_in_pct  = event.get('fade_in',  sample_spec.get('fade_in',  0.05))
        fade_out_pct = event.get('fade_out', sample_spec.get('fade_out', 0.05))

        # --- attack_shape (dim 3): 0=punchy (short attack), 0.5=neutral, 1=soft ---
        attack_shape = event.get('attack_shape')
        if attack_shape is not None:
            fade_in_pct = min(0.8, fade_in_pct * (attack_shape * 2.0))

        # --- release_shape (dim 4): 0=abrupt cutoff, 0.5=neutral, 1=long tail ---
        release_shape = event.get('release_shape')
        if release_shape is not None:
            fade_out_pct = min(0.9, fade_out_pct * (release_shape * 2.0))

        clip = apply_fade(clip, sr, fade_in_pct=fade_in_pct, fade_out_pct=fade_out_pct)

        # --- gain ---
        gain_db = event.get('gain_db', -6.0)
        clip   *= 10 ** (gain_db / 20.0)

        # --- Phase C: dynamic_center slow gain envelope across the note ---
        if _state_trace:
            N_DC = 5
            dur_sec = len(clip) / sr
            dcs = []
            for i in range(N_DC):
                t_q = event['t'] + (i / (N_DC - 1)) * dur_sec
                st = _sample_trace_at(_state_trace, t_q, 'sample')
                if st:
                    dcs.append(st[11])
            if dcs:
                clip = _apply_dynamic_envelope(clip, dcs)

        # --- brightness (Kalman dim 1): high-shelf EQ ---
        brightness = event.get('brightness')
        if brightness is not None:
            clip = _apply_brightness(clip, sr, brightness)

        # --- Phase B: timbral breath (LFO on brightness across the note) ---
        if brightness is not None:
            breath_depth = 0.35 * min(max(brightness, 0.0), 1.0)
            clip = _apply_timbral_breath(clip, sr, depth=breath_depth,
                                         rate_hz=0.7, seed=_event_seed(event))

        # --- fx ---
        fx_list = event.get('fx', [])
        if fx_list:
            clip = apply_fx(clip, sr, fx_list)

        # --- reverb_wet (dim 5): add reverb if not already in fx chain ---
        reverb_wet = event.get('reverb_wet')
        if reverb_wet is not None and reverb_wet > 0.05:
            has_reverb = any(f.get('type') == 'reverb' for f in fx_list)
            if not has_reverb:
                # Phase B: swell across note instead of flat reverb level
                clip = _apply_reverb_swell(clip, sr, base_wet=reverb_wet,
                                           swell_depth=0.6, seed=_event_seed(event))

        # --- filter_cutoff / filter_resonance (dims 6, 7): state-driven filter ---
        filter_cutoff = event.get('filter_cutoff')
        if filter_cutoff is not None and filter_cutoff < 19000:
            has_filter = any(f.get('type') == 'filter' for f in fx_list)
            if not has_filter:
                # Phase C: if trace available, sweep cutoff across the note
                if _state_trace:
                    N_SEG = 4
                    dur = len(clip) / sr
                    cutoffs = []
                    for i in range(N_SEG + 1):
                        t_q = event['t'] + (i / N_SEG) * dur
                        st = _sample_trace_at(_state_trace, t_q, 'sample')
                        cutoffs.append(st[6] if st else filter_cutoff)
                    clip = _apply_time_varying_filter(clip, sr, cutoffs, n_segments=N_SEG)
                else:
                    filter_res = event.get('filter_resonance', 0.0)
                    clip = apply_fx(clip, sr, [{'type': 'filter',
                                                'cutoff': filter_cutoff,
                                                'resonance': filter_res,
                                                'filter_type': 'lp'}])

        # --- overdrive_drive (dim 9): state-driven saturation ---
        od_drive = event.get('overdrive_drive')
        if od_drive is not None and od_drive > 0.05:
            has_od = any(f.get('type') == 'overdrive' for f in fx_list)
            if not has_od:
                clip = apply_fx(clip, sr, [{'type': 'overdrive', 'drive': od_drive}])

        # --- stereo_width (dim 8): M/S width control ---
        stereo_width = event.get('stereo_width')
        if stereo_width is not None and abs(stereo_width - 0.5) > 0.05:
            clip = _apply_stereo_width(clip, stereo_width)

        # --- articulations ---
        if articulations:
            art = _find_articulation(event['t'], articulations)
            if art:
                clip = _apply_articulation(clip, art['type'], sr)

        # --- pitch (per-event static, or interpolated by glissando) ---
        semitones = resolve_event_pitch(event['t'], float(event.get('pitch', 0.0)), note_rels)
        # Add state-driven pitch deviation (dim 10)
        pitch_dev = event.get('pitch_dev_cents', 0.0)
        if pitch_dev:
            semitones = (semitones or 0.0) + pitch_dev / 100.0
        if semitones:
            clip = apply_pitch_shift(clip, sr, semitones)

        # --- Phase B: vibrato (LFO on pitch across the note) ---
        # Depth scales with |pitch_dev_cents| — more expressive events = more vibrato.
        # Base depth ~2.5 cents, scales up to ~6 cents for strongly detuned events.
        vib_depth = 2.5 + 0.08 * abs(pitch_dev)
        # Random rate per event ∈ [4, 7] Hz via event seed
        _evs = _event_seed(event)
        vib_rate = 4.0 + (((_evs >> 3) & 0x7FF) / 0x7FF) * 3.0
        clip = _apply_vibrato(clip, sr, depth_cents=vib_depth,
                              rate_hz=vib_rate, seed=_evs)

        # --- place on timeline (tempo-warped + silence offset + timing_offset_ms) ---
        t_real = _warp_time(event['t'], tempo_ranges) + silence_start
        timing_off = event.get('timing_offset_ms')
        if timing_off:
            t_real = max(0.0, t_real + timing_off / 1000.0)
        i0 = int(t_real * sr)
        i1 = i0 + len(clip)
        if i1 > len(mix):
            mix = np.pad(mix, (0, i1 - len(mix)))
        mix[i0:i1] += clip

    # --- auto_mix: scale down overlapping events ---
    am = (score or {}).get('auto_mix')
    if am and am.get('enabled') and events:
        scale = build_density_scale(
            len(mix), sr, events, samples_spec,
            tempo_ranges=tempo_ranges,
            mode=am.get('mode', 'sqrt'),
            silence_start=silence_start,
        )
        mix *= scale

    return mix


def normalise(mix: np.ndarray, headroom: float = 0.9) -> np.ndarray:
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * headroom
    return mix
