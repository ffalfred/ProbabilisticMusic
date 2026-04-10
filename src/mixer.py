import numpy as np
import librosa
from scipy.signal import butter, sosfilt
from src.envelope import apply_fade, build_duck_envelope, build_density_scale
from src.fx       import apply_fx
from src.pitch    import resolve_event_pitch, apply_pitch_shift, apply_noterel_to_mix


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


def _apply_state_to_mix(mix: np.ndarray, sr: int, trace: list) -> np.ndarray:
    """Apply golem gain modulation to the combined mix.

    Called AFTER events are blended. Only gain_db + dynamic_center applied.
    """
    if mix is None or not trace:
        return mix

    n = len(mix)
    gain_db = _interp_dim_envelope(trace, n, sr, 0)
    gain_lin = (10.0 ** (gain_db / 20.0)).astype(np.float32)

    if mix.ndim == 1:
        return (mix * gain_lin).astype(np.float32)
    return (mix * gain_lin[:, None]).astype(np.float32)


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


def _variable_rate_pv(y: np.ndarray, sr: int, rate_at_score,
                      score_t0: float, score_t1: float,
                      n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    """Variable-rate phase vocoder.

    Stretches a mono chunk where the playback rate varies continuously across
    the chunk. Phase is propagated coherently from start to end (one STFT pass)
    so there are no internal seams.

    rate_at_score(s): callable returning the rate at score time `s` (seconds).
                     rate > 1 = faster (output shorter), rate < 1 = slower.
    score_t0:        score-time position of y[0].
    score_t1:        score-time position of y[-1] + 1 sample.
    """
    if len(y) < n_fft * 2:
        # Too short for a meaningful PV pass — fall back to a constant rate
        # equal to the midpoint, via librosa's tested scalar implementation.
        r_mid = float(rate_at_score((score_t0 + score_t1) / 2.0))
        if abs(r_mid - 1.0) < 1e-3:
            return y.astype(np.float32, copy=False)
        return librosa.effects.time_stretch(y.astype(np.float32), rate=r_mid)

    D = librosa.stft(y.astype(np.float32), n_fft=n_fft, hop_length=hop)
    n_freq, n_in = D.shape
    if n_in < 2:
        return y.astype(np.float32, copy=False)

    # Walk input frames at variable rate (Euler integration of dt_in/dk_out = r).
    # k_out advances by 1 each iteration; t_in advances by r(current_score_time).
    sec_per_frame = hop / sr
    time_steps = [0.0]
    while True:
        cur = time_steps[-1]
        s_score = score_t0 + cur * sec_per_frame
        r = float(rate_at_score(s_score))
        r = max(r, 0.01)
        nxt = cur + r
        if nxt >= n_in - 1:
            break
        time_steps.append(nxt)
    time_steps = np.asarray(time_steps, dtype=np.float64)
    n_out = len(time_steps)

    # Expected phase advance per analysis hop, per frequency bin
    omega = 2.0 * np.pi * np.arange(n_freq) * hop / n_fft

    D_out = np.zeros((n_freq, n_out), dtype=np.complex64)
    phase_acc = np.angle(D[:, 0]).astype(np.float64)
    D_out[:, 0] = np.abs(D[:, 0]) * np.exp(1j * phase_acc)

    for i in range(1, n_out):
        t = time_steps[i]

        t_floor = int(np.floor(t))
        if t_floor >= n_in - 1:
            t_floor = n_in - 2
        alpha = t - t_floor

        # Linear interpolation of magnitude between adjacent input frames
        mag = (1.0 - alpha) * np.abs(D[:, t_floor]) + alpha * np.abs(D[:, t_floor + 1])

        # True phase advance per ANALYSIS hop = omega + delta_phi (principal value)
        dphi = np.angle(D[:, t_floor + 1]) - np.angle(D[:, t_floor]) - omega
        dphi -= 2.0 * np.pi * np.round(dphi / (2.0 * np.pi))

        # Per OUTPUT frame, phase advances by exactly one synthesis hop's worth.
        # The rate only changes which input frame we sample magnitude/dphi from.
        # (Multiplying by `advance` over-rotates and causes overlap-add cancellation.)
        phase_acc = phase_acc + (omega + dphi)
        D_out[:, i] = mag * np.exp(1j * phase_acc)

    y_out = librosa.istft(D_out, hop_length=hop, n_fft=n_fft)

    # Energy preservation: phase-vocoder magnitude interpolation + STFT edge
    # windowing introduce a small but consistent RMS drop (~6–10%). Compensate
    # by matching output RMS to input RMS over the same musical content.
    in_rms  = float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))
    out_rms = float(np.sqrt(np.mean(y_out.astype(np.float64) ** 2)))
    if out_rms > 1e-6 and in_rms > 1e-6:
        gain = in_rms / out_rms
        # Cap the gain to avoid amplifying tail noise if the input is near silent
        gain = min(gain, 4.0)
        y_out = y_out * gain

    return y_out.astype(np.float32)


def _stretch_mix_by_tempo(mix: np.ndarray, sr: int, tempo_ranges: list):
    """
    Stretch sections of the mix by tempo factor. Length may change.

    Each range accepts a 'shape' field:
      - 'ramp' (default): rate ramps linearly from 1.0 at `from` to `factor` at `to`.
        This is the musically correct accelerando/ritardando — gradual.
        Implemented as a single variable-rate phase-vocoder pass over the whole
        ramp window so phase is continuous (no granular seams).
      - 'step': constant `factor` across the whole window. Uses librosa's
        scalar `time_stretch`.

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
    #    window is processed as a single segment by the variable-rate PV.
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
    #    Seams are now rare (only at range edges, not inside ramps), so a slightly
    #    longer crossfade hides phase discontinuities at rate transitions.
    XFADE_MS = 10
    xf = max(1, int(XFADE_MS * sr / 1000))
    stereo = (mix.ndim == 2)

    out_chunks = []
    tempo_map = [(0.0, 0.0)]
    real_cursor = 0.0

    for score_t0, score_t1, has_ramp, const_rate in segments:
        i0 = int(score_t0 * sr)
        i1 = int(score_t1 * sr)
        chunk = mix[i0:i1]
        if len(chunk) == 0:
            continue

        if (not has_ramp and abs(const_rate - 1.0) < 1e-3) or len(chunk) < 2048:
            stretched = chunk.astype(np.float32, copy=False)
        elif has_ramp:
            # Variable-rate PV: one continuous phase-coherent pass across the
            # entire ramp window. No internal seams → no granular artifacts.
            if stereo:
                stretched = np.stack([
                    _variable_rate_pv(chunk[:, c], sr, rate_at, score_t0, score_t1)
                    for c in range(chunk.shape[1])
                ], axis=1)
            else:
                stretched = _variable_rate_pv(chunk, sr, rate_at, score_t0, score_t1)
            stretched = stretched.astype(np.float32)
        else:
            # Constant-rate segment (step range or no range): scalar PV.
            if stereo:
                stretched = np.stack([
                    librosa.effects.time_stretch(chunk[:, c].astype(np.float32), rate=float(const_rate))
                    for c in range(chunk.shape[1])
                ], axis=1)
            else:
                stretched = librosa.effects.time_stretch(chunk.astype(np.float32), rate=float(const_rate))
            stretched = stretched.astype(np.float32)

        out_chunks.append(stretched)
        real_cursor += len(stretched) / sr
        tempo_map.append((float(score_t1), float(real_cursor)))

    return _concat_with_xfade(out_chunks, xf), tempo_map


def _apply_speed(clip: np.ndarray, speed: float, sr: int, pitch_lock: bool = False) -> np.ndarray:
    if abs(speed - 1.0) < 1e-3:
        return clip
    if pitch_lock:
        # Phase-vocoder stretch: rate > 1 → shorter, rate < 1 → longer. Pitch unchanged.
        return librosa.effects.time_stretch(clip.astype(np.float32), rate=float(speed))
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
    samples_spec   = (score or {}).get('samples', {})
    articulations  = (score or {}).get('articulations', [])
    note_rels      = (score or {}).get('note_rel', [])
    _state_trace   = (score or {}).get('_state_trace', None)

    mix = base.copy() if base is not None else np.zeros(int((max(e['t'] for e in events) + 30.0) * sr), dtype=np.float32)

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
        )
        mix[:len(duck_env)] *= duck_env

    for event in events:
        if event.get('muted'):
            continue
        base_clip = bank[event['sample']].copy()

        # --- speed / layered transpositions ---
        pitch_lock = bool(event.get('pitch_lock', False))
        speeds = event.get('speeds')
        if speeds:
            layers  = [_apply_speed(base_clip.copy(), s, sr, pitch_lock) for s in speeds]
            max_len = max(len(l) for l in layers)
            clip    = np.zeros(max_len, dtype=np.float32)
            for l in layers:
                clip[:len(l)] += l
        else:
            clip = _apply_speed(base_clip, event.get('speed', 1.0), sr, pitch_lock)

        # --- reverse ---
        if event.get('reverse', False):
            clip = clip[::-1].copy()

        # --- loop ---
        loop = event.get('loop', 0)
        if loop > 0:
            clip = np.tile(clip, loop + 1)

        # --- fade edges shaped by golem's attack/release ---
        sample_spec  = samples_spec.get(event['sample'], {})
        fade_in_pct  = event.get('fade_in',  sample_spec.get('fade_in',  0.05))
        fade_out_pct = event.get('fade_out', sample_spec.get('fade_out', 0.05))
        attack_shape = event.get('attack_shape')
        if attack_shape is not None:
            fade_in_pct = min(0.8, fade_in_pct * (attack_shape * 2.0))
        release_shape = event.get('release_shape')
        if release_shape is not None:
            fade_out_pct = min(0.9, fade_out_pct * (release_shape * 2.0))
        clip = apply_fade(clip, sr, fade_in_pct=fade_in_pct, fade_out_pct=fade_out_pct)

        # --- score-level gain (NOT golem state — just the score's own gain_db) ---
        gain_db = event.get('gain_db', -6.0)
        clip   *= 10 ** (gain_db / 20.0)

        # --- composer-authored per-event FX chain (score instructions, not golem) ---
        fx_list = event.get('fx', [])
        if fx_list:
            clip = apply_fx(clip, sr, fx_list)

        # --- articulations ---
        if articulations:
            art = _find_articulation(event['t'], articulations)
            if art:
                clip = _apply_articulation(clip, art['type'], sr)

        # --- pitch (score-level: static or glissando — NOT golem pitch_dev) ---
        semitones = resolve_event_pitch(event['t'], float(event.get('pitch', 0.0)), note_rels)
        if semitones:
            clip = apply_pitch_shift(clip, sr, semitones)

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
        if i1 > len(mix):
            mix = np.pad(mix, (0, i1 - len(mix)))

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
            if mix.ndim == 1:
                mix[i0:i1] = mix[i0:i1] * (1 - blend) + clip * blend
            else:
                mix[i0:i1] = mix[i0:i1] * (1 - blend[:, None]) + clip * blend[:, None]
        else:  # 'layer'
            mix[i0:i1] += clip

    # --- single-pass golem state modulation on the combined mix ---
    # Only apply when golems are explicitly present. Without golems, the audio
    # should play clean with dynamics envelope (the traditional path).
    _has_golems = bool((score or {}).get('golems'))
    if _state_trace and _has_golems:
        mix = _apply_state_to_mix(mix, sr, _state_trace)

    # --- note relationships on the full mix (glissando pitch-slide, arpeggio roll) ---
    if note_rels:
        mix = apply_noterel_to_mix(mix, sr, note_rels)

    # --- articulations on the full mix (base track + events) ---
    _SILENCE_DUR_DEFAULT = 0.07  # seconds silenced after a staccato point mark
    for art in articulations:
        art_type = art.get('type', '')
        from_t = art.get('from')
        to_t   = art.get('to')
        if from_t is None or to_t is None:
            pt = art.get('t')
            if pt is None:
                continue
            silence_s = float(art.get('silence_s', _SILENCE_DUR_DEFAULT))
            from_t = float(pt)
            to_t   = from_t + silence_s
        i0 = int(float(from_t) * sr)
        i1 = min(int(float(to_t) * sr), len(mix))
        if i0 >= len(mix) or i0 >= i1:
            continue

        if art_type == 'staccato':
            # Punchy: keep 20 ms at full attack, then sharp 5 ms cut, then silence.
            keep  = min(int(0.02 * sr), i1 - i0)
            cut_n = min(int(0.005 * sr), i1 - i0 - keep)
            if cut_n > 1:
                mix[i0 + keep:i0 + keep + cut_n] *= np.linspace(1.0, 0.0, cut_n, dtype=np.float32)
            mix[i0 + keep + cut_n:i1] = 0.0

        elif art_type == 'accent':
            atk = min(int(0.05 * sr), i1 - i0)
            if atk > 1:
                mix[i0:i0 + atk] *= np.linspace(2.0, 1.0, atk, dtype=np.float32)

        elif art_type == 'legato':
            # Smooth 50 ms fade-in at start; long 500 ms fade-out at end.
            fi = min(int(0.05 * sr), (i1 - i0) // 2)
            fo = min(int(0.50 * sr), (i1 - i0) // 2)
            if fi > 1:
                mix[i0:i0 + fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
            if fo > 1:
                mix[i1 - fo:i1] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)

        elif art_type == 'fermata':
            # Grab hold_s of audio ending at i1. Extend the mix buffer and loop
            # it 6 times with a slow fade, creating a dramatic, extended hold.
            hold_s = float(art.get('hold_s', 2.0))
            hold_n = min(int(hold_s * sr), i1)
            src_s  = max(0, i1 - hold_n)
            hold_n = i1 - src_s
            if hold_n > int(0.05 * sr):
                tail = mix[src_s:i1].copy()
                fi   = max(1, hold_n // 8)
                tail[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
                n_reps = 6
                needed = i1 + n_reps * hold_n
                if needed > len(mix):
                    mix = np.pad(mix, (0, needed - len(mix)))
                for rep in range(n_reps):
                    gain = 1.0 - rep / (n_reps * 1.5)  # slow fade — stays loud longer
                    s    = i1 + rep * hold_n
                    mix[s:s + hold_n] += tail * gain

    # --- auto_mix: scale down overlapping events ---
    am = (score or {}).get('auto_mix')
    if am and am.get('enabled') and events:
        scale = build_density_scale(
            len(mix), sr, events, samples_spec,
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
