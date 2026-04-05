"""
V2 Expressive Interpretation Engine.

interpret(score, config) -> list[dict]
  Takes a parsed score dict and config dict.
  Returns an enriched event list ready for V1 rendering.

Two golem types are supported in score['golems']:

  type: kalman (default)
    Maintains a Gaussian belief over the 5D expressive state via an AR(2)
    augmented Kalman filter.  Dynamic markings constrain the posterior.
    Sampling from the posterior can use Gaussian, Laplace, Cauchy, or Mixture.

  type: random_walk
    Expressive state evolves as Brownian motion (optionally Ornstein–Uhlenbeck).
    Supports Gaussian, Laplace, Cauchy, Uniform, Beta, Mixture noise.
    Per-dimension mean reversion, boundary reflection, and dim correlations.

Golem envelope:
    weight    — blend weight (default 1.0); fade_in / fade_out ramp it
"""

import os
import copy
import yaml
import bisect
import numpy as np

from src.kalman      import build_F, build_Q_aug, build_Sigma0, predict, update
from src.drama       import compute_drama, compute_future_pull
from src.observation import build_window_obs, lookup_HR
from src.character   import (character_at, make_AR_matrices,
                              rw_character_at, D, BUILTIN as _KALMAN_BUILTIN,
                              DIM_NAMES, DIM_RANGES as _CHAR_DIM_RANGES,
                              DIM_DEFAULTS as _CHAR_DIM_DEFAULTS)


_TABLE_PATH = os.path.join(os.path.dirname(__file__), 'transition_table.yaml')

OUTPUT_KEYS = DIM_NAMES

_OUTPUT_LIMITS = {k: tuple(v) for k, v in zip(DIM_NAMES, _CHAR_DIM_RANGES)}


# ── Distribution sampling ─────────────────────────────────────────────────────

def _sample_noise(rng, size: int, dist: str, scale,
                  mixture_p: float = 0.05, mixture_scale: float = 4.0,
                  student_df: float = 3.0, bimodal_sep: float = 0.75,
                  cauchy_clip: float = 5.0, beta_a: float = 2.0, beta_b: float = 2.0,
                  skew: float = 0.0, trunc_lo: float = -3.0, trunc_hi: float = 3.0,
                  base_dist: str = 'gaussian') -> np.ndarray:
    """
    Sample a noise vector from the named distribution.

    All variants are normalised so that the scale parameter has the same
    meaning as a Gaussian σ: E[noise²] ≈ scale² per dimension.

    Distributions:
        gaussian / Natural       — standard Gaussian
        laplace  / Edgy          — heavy-tailed symmetric
        cauchy   / Wild          — very heavy tails (clipped)
        uniform  / Even          — flat distribution
        beta     / Curved        — parabolic (via beta_a, beta_b)
        mixture  / Bursting      — Gaussian + rare large spikes
        student_t / Weighted     — t-distribution (df controls tail weight)
        bimodal  / Bipolar       — two expressive poles (sep controlled by bimodal_sep)
        skew_normal              — asymmetric Gaussian (scipy.stats.skewnorm)
        truncated                — rejection-sampled base_dist within [trunc_lo, trunc_hi] σ
    """
    scale = np.array(scale, dtype=float)
    if dist == 'laplace':
        return rng.laplace(0.0, scale / np.sqrt(2.0))
    elif dist == 'cauchy':
        raw = rng.standard_cauchy(size)
        return np.clip(raw, -cauchy_clip, cauchy_clip) * scale * (0.3 / (cauchy_clip / 5.0))
    elif dist == 'uniform':
        a = scale * np.sqrt(3.0)
        return rng.uniform(-a, a)
    elif dist == 'beta':
        return (rng.beta(beta_a, beta_b, size) - beta_a / (beta_a + beta_b)) * 2.0 * scale
    elif dist == 'mixture':
        base   = rng.normal(0.0, scale)
        spikes = rng.normal(0.0, scale * mixture_scale)
        mask   = rng.random(size) < mixture_p
        return np.where(mask, spikes, base)
    elif dist == 'student_t':
        df  = max(float(student_df), 2.01)
        raw = rng.standard_t(df, size)
        # Normalise variance: Var(t_df) = df/(df-2)
        return raw * scale / np.sqrt(df / (df - 2.0))
    elif dist == 'bimodal':
        sign = np.where(rng.random(size) < 0.5, 1.0, -1.0)
        return sign * rng.normal(scale * bimodal_sep, scale * 0.3)
    elif dist == 'skew_normal':
        try:
            from scipy.stats import skewnorm
            return skewnorm.rvs(a=skew, loc=0.0, scale=scale, size=size, random_state=rng.bit_generator)
        except ImportError:
            # Fallback: approximate skew_normal as Gaussian (scipy not available)
            return rng.normal(0.0, scale)
    elif dist == 'truncated':
        # Rejection sampling: draw from base_dist, reject outside [trunc_lo, trunc_hi] σ
        lo_abs = trunc_lo * scale
        hi_abs = trunc_hi * scale
        result = np.empty(size if np.isscalar(scale) else scale.shape)
        filled = np.zeros(result.shape, dtype=bool)
        for _ in range(50):  # max 50 attempts
            remaining = ~filled
            if not np.any(remaining):
                break
            n_rem = int(np.sum(remaining)) if not np.isscalar(remaining) else (1 if remaining else 0)
            sample = _sample_noise(rng, n_rem, base_dist, scale if np.isscalar(scale) else scale[remaining],
                                   mixture_p=mixture_p, mixture_scale=mixture_scale,
                                   student_df=student_df, bimodal_sep=bimodal_sep)
            within = (sample >= lo_abs if np.isscalar(lo_abs) else sample >= lo_abs[remaining]) & \
                     (sample <= hi_abs if np.isscalar(hi_abs) else sample <= hi_abs[remaining])
            result[remaining] = np.where(within, sample, result[remaining])
            filled[remaining] = within
        # Any still unfilled: hard-clip to limits
        result = np.clip(result, lo_abs, hi_abs)
        return result
    else:  # gaussian / Natural
        return rng.normal(0.0, scale)


# ── Drama curve ───────────────────────────────────────────────────────────────

def _apply_drama_curve(drama: float, curve: str) -> float:
    """Map drama ∈ [0,1] through the chosen non-linearity."""
    if curve == 'square':
        return drama ** 2
    elif curve == 'exp':
        # exp(3x)-1 normalised so that f(1)=1
        return (np.exp(3.0 * drama) - 1.0) / (np.exp(3.0) - 1.0)
    return float(drama)   # linear


# ── Boundary handling ─────────────────────────────────────────────────────────

def _apply_boundary(x: np.ndarray, mode: str,
                    custom_limits=None, clip_method: str = 'hard') -> np.ndarray:
    """
    Apply boundary at each output dimension's physical limits.

    mode        : 'clip' or 'reflect'
    custom_limits: optional D×2 list [[lo,hi],...] indexed by OUTPUT_KEYS order
    clip_method  : 'hard' (np.clip), 'soft'/'tanh' (smooth tanh squashing)
    """
    limits = {}
    for i, key in enumerate(OUTPUT_KEYS):
        if (custom_limits is not None and i < len(custom_limits)
                and custom_limits[i] is not None and len(custom_limits[i]) >= 2):
            limits[key] = (float(custom_limits[i][0]), float(custom_limits[i][1]))
        else:
            limits[key] = _OUTPUT_LIMITS[key]

    out = x.copy()
    for i, key in enumerate(OUTPUT_KEYS):
        lo, hi = limits[key]
        v = out[i]
        if mode == 'reflect':
            for _ in range(4):   # up to 4 reflections for large overshoots
                if v < lo:
                    v = 2.0 * lo - v
                elif v > hi:
                    v = 2.0 * hi - v
                else:
                    break
        # Final clamp / soft squash
        if clip_method in ('soft', 'tanh'):
            mid  = (lo + hi) / 2.0
            half = (hi - lo) / 2.0
            if half > 0:
                out[i] = mid + half * np.tanh((v - mid) / half)
            else:
                out[i] = float(np.clip(v, lo, hi))
        else:  # hard
            out[i] = float(np.clip(v, lo, hi))
    return out


# ── Score helpers ─────────────────────────────────────────────────────────────

def _total_duration(events: list, score: dict) -> float:
    if events:
        last = max(e['t'] + e.get('dur', 1.0) for e in events)
    else:
        last = 0.0
    dyn = [d for d in score.get('dynamics', []) if 't' in d]
    if dyn:
        last = max(last, max(d['t'] for d in dyn) + 1.0)
    return max(last, 1.0)


def _extract_markings(score: dict) -> list:
    raw = score.get('dynamics', [])
    pairs = sorted(
        [(d['t'], d.get('mark') or d.get('marking')) for d in raw
         if ('mark' in d or 'marking' in d) and 't' in d],
        key=lambda p: p[0]
    )
    return pairs


def _find_marking_for_event(ev_or_t, marking_times: list) -> int:
    t     = ev_or_t if isinstance(ev_or_t, (int, float)) else ev_or_t['t']
    times = [p[0] for p in marking_times]
    idx   = bisect.bisect_right(times, t) - 1
    return max(0, idx)


def _phrase_boundary_indices(score: dict, marking_times: list) -> set:
    phrases        = score.get('phrases', [])
    boundary_times = {p['from'] for p in phrases}
    times          = [p[0] for p in marking_times]
    indices        = set()
    for bt in boundary_times:
        idx = bisect.bisect_left(times, bt)
        if idx < len(times) and abs(times[idx] - bt) < 0.5:
            indices.add(idx)
    return indices


def _resolve_character_name(t: float, golems: list) -> str:
    active = [g for g in golems if g.get('from', 0) <= t < g.get('to', float('inf'))]
    if not active:
        return 'default'
    return max(active, key=lambda g: g.get('from', 0))['character']


def _resolve_golem_type(t: float, golems: list) -> str:
    """
    Return the dominant golem type at time t.
    'discrete' if ALL active golems are discrete.
    'random_walk' if ALL active golems are random_walk.
    Otherwise 'kalman' (the default).
    """
    active = [g for g in golems if g.get('from', 0) <= t < g.get('to', float('inf'))]
    if not active:
        return 'kalman'
    types = {g.get('type', 'kalman') for g in active}
    if types == {'discrete'}:
        return 'discrete'
    if types == {'random_walk'}:
        return 'random_walk'
    return 'kalman'


def _smooth_drama(drama_vals: list, alpha: float) -> list:
    """EMA smoothing of drama values: out[t] = alpha*drama[t] + (1-alpha)*out[t-1]."""
    if alpha >= 1.0 or not drama_vals:
        return drama_vals
    smoothed = [drama_vals[0]]
    for d in drama_vals[1:]:
        smoothed.append(alpha * d + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _dist_kwargs_from_config(dist_cfg: dict) -> dict:
    """Extract distribution-specific keyword arguments from a dist_config dict."""
    return {
        'bimodal_sep':  float(dist_cfg.get('bimodal_sep', dist_cfg.get('sep', 0.75))),
        'cauchy_clip':  float(dist_cfg.get('cauchy_clip', dist_cfg.get('clip_sigma', 5.0))),
        'beta_a':       float(dist_cfg.get('beta_a', dist_cfg.get('a', 2.0))),
        'beta_b':       float(dist_cfg.get('beta_b', dist_cfg.get('b', 2.0))),
        'skew':         float(dist_cfg.get('skew', dist_cfg.get('skew_alpha', 0.0))),
        'trunc_lo':     float(dist_cfg.get('trunc_lo', -3.0)),
        'trunc_hi':     float(dist_cfg.get('trunc_hi', 3.0)),
        'base_dist':    str(dist_cfg.get('base_dist', 'gaussian')),
        'mixture_p':    float(dist_cfg.get('mixture_p', 0.05)),
        'mixture_scale': float(dist_cfg.get('mixture_scale', 4.0)),
        'student_df':   float(dist_cfg.get('df', dist_cfg.get('student_df', 3.0))),
    }


# ── RW step ───────────────────────────────────────────────────────────────────

def _rw_step(x_prev: np.ndarray, char: dict, rng, t: float = 0.0,
             omega: float = None) -> np.ndarray:
    """
    One random walk / OU step in expressive state space.

    x(t) = x(t-1) + drift - mr_dims*(x(t-1)-mr_target) + noise(distribution)

    breath_amp > 0 adds a sinusoidal drift component (period = breath_period).
    omega_step_scale scales step_size by omega_step_scale**omega(t) when omega provided.
    """
    step  = np.array(char['step_size'], dtype=float)
    drift = np.array(char.get('drift', [0.0] * D), dtype=float)
    dist  = char.get('distribution', 'gaussian')
    dist_cfg = char.get('dist_config', {}) or {}

    # Breathing walk: sinusoidal drift
    # Triggered by explicit breath_amp > 0 or by walk_mode == 'breathing'
    breath_amp = float(char.get('breath_amp', 0.6 if char.get('walk_mode') == 'breathing' else 0.0))
    if breath_amp > 0:
        period = float(char.get('breath_period', 8.0))
        drift  = drift + step * breath_amp * np.sin(2.0 * np.pi * t / period)

    # ω-driven step scaling: step_eff = step * omega_step_scale^omega(t)
    omega_step_scale = char.get('omega_step_scale')
    if omega_step_scale is not None and omega is not None:
        step = step * (float(omega_step_scale) ** float(omega))

    # Per-dim mean reversion with optional non-zero target
    mr_dims = char.get('mr_dims')
    if mr_dims is not None:
        mr = np.array(mr_dims, dtype=float)
    else:
        mr = np.full(D, float(char.get('mean_reversion', 0.0)))

    mr_target_raw = char.get('mr_target')
    if mr_target_raw is not None:
        mr_target = np.array(mr_target_raw, dtype=float)
    else:
        mr_target = np.zeros(D)

    # Build dist kwargs
    dkw = _dist_kwargs_from_config(dist_cfg)
    dkw.update({
        'mixture_p':    float(char.get('mixture_p', dkw['mixture_p'])),
        'mixture_scale': float(char.get('mixture_scale', dkw['mixture_scale'])),
        'student_df':   float(char.get('student_df', dkw['student_df'])),
    })

    # Sample noise (possibly correlated)
    corr = char.get('correlation')
    if corr is not None:
        try:
            L     = np.linalg.cholesky(np.array(corr, dtype=float))
            white = _sample_noise(rng, D, dist, np.ones(D), **dkw)
            noise = L @ (white * step)
        except np.linalg.LinAlgError:
            noise = _sample_noise(rng, D, dist, step, **dkw)
    else:
        noise = _sample_noise(rng, D, dist, step, **dkw)

    x_new = x_prev + drift - mr * (x_prev - mr_target) + noise
    return _apply_boundary(x_new, char.get('boundary_mode', 'clip'),
                           custom_limits=char.get('physical_limits'),
                           clip_method=char.get('clip_method', 'hard'))


# ── Kalman posterior sampling ─────────────────────────────────────────────────

def _sample_posterior(rng, mu: np.ndarray, Sig: np.ndarray,
                      dist: str, mixture_p: float, mixture_scale: float,
                      student_df: float = 3.0,
                      inflate: float = 1.0, inflate_dims=None,
                      dist_kwargs: dict = None,
                      dist_dims=None,
                      clip_sigma: float = None,
                      clip_sigma_dims=None) -> np.ndarray:
    """
    Sample from the Kalman posterior using the chosen distribution.
    For non-Gaussian choices, replace multivariate_normal with independent
    marginal samples from the chosen distribution with matching per-dim σ.

    inflate / inflate_dims: scale Sigma before sampling (covariance inflation).
    dist_dims: per-dimension distribution list (overrides dist per dim).
    clip_sigma: tame outliers — clamp each dim to mu ± clip_sigma * σ.
                None = no clamp (wild tails). Float = uniform cap for all dims.
    clip_sigma_dims: optional per-dim cap vector, overrides scalar clip_sigma.
    """
    # Covariance inflation
    Sig_s = Sig.copy()
    if inflate != 1.0 or inflate_dims is not None:
        if inflate_dims is not None:
            inf_diag = np.array(inflate_dims, dtype=float)[:D]
            Sig_s = Sig_s * np.outer(inf_diag, inf_diag)
        else:
            Sig_s = Sig_s * (inflate ** 2)

    dkw = dict(dist_kwargs) if dist_kwargs else {}
    dkw.setdefault('mixture_p', mixture_p)
    dkw.setdefault('mixture_scale', mixture_scale)
    dkw.setdefault('student_df', student_df)

    std = np.sqrt(np.maximum(np.diag(Sig_s), 1e-10))

    if dist_dims is not None:
        # Per-dimension distribution
        noise = np.empty(D)
        for i in range(D):
            d_i = dist_dims[i] if i < len(dist_dims) else dist
            noise[i] = float(_sample_noise(rng, 1, d_i, std[i:i+1], **dkw))
        draw = mu + noise
    elif dist == 'gaussian':
        draw = rng.multivariate_normal(mu, Sig_s)
    else:
        noise = _sample_noise(rng, D, dist, std, **dkw)
        draw = mu + noise

    # Outlier clamp: enforce |draw - mu| <= cap * std per dimension
    if clip_sigma_dims is not None or clip_sigma is not None:
        if clip_sigma_dims is not None:
            caps = np.array([float(clip_sigma_dims[i])
                             if i < len(clip_sigma_dims) else 999.0
                             for i in range(D)], dtype=float)
        else:
            caps = np.full(D, float(clip_sigma))
        max_dev = caps * std
        draw = np.minimum(np.maximum(draw, mu - max_dev), mu + max_dev)
    return draw


# ── State → event ─────────────────────────────────────────────────────────────

def _apply_state(ev: dict, x: np.ndarray) -> dict:
    """Map the 12D Kalman state vector onto event fields."""
    ev = dict(ev)
    ev['gain_db']          = float(ev.get('gain_db', 0.0)) + float(x[0])
    ev['brightness']       = float(np.clip(x[1], 0.0, 1.0))
    ev['timing_offset_ms'] = float(x[2])
    ev['attack_shape']     = float(np.clip(x[3], 0.0, 1.0))
    ev['release_shape']    = float(np.clip(x[4], 0.0, 1.0))
    ev['reverb_wet']       = float(np.clip(x[5], 0.0, 1.0))
    ev['filter_cutoff']    = float(np.clip(x[6], 20.0, 20000.0))
    ev['filter_resonance'] = float(np.clip(x[7], 0.0, 1.0))
    ev['stereo_width']     = float(np.clip(x[8], 0.0, 1.0))
    ev['overdrive_drive']  = float(np.clip(x[9], 0.0, 1.0))
    ev['pitch_dev_cents']  = float(x[10])
    ev['dynamic_center']   = float(np.clip(x[11], -30.0, 0.0))
    return ev


# ── Main entry point ──────────────────────────────────────────────────────────

def interpret(score: dict, config: dict, return_trace: bool = False) -> list:
    """
    Enrich score events with expressive parameters.

    Supports Kalman and Random Walk golems, multiple sampling distributions,
    per-dimension AR coefficients, drama curves, golem fade envelopes, and
    boundary reflection.

    Returns sorted list of enriched event dicts (or (events, trace) if return_trace).
    """
    with open(_TABLE_PATH) as f:
        table_root = yaml.safe_load(f) or {}
    windows_table = table_root.get('windows', {})
    user_chars    = table_root.get('characters', {})
    rw_user_chars = table_root.get('rw_characters', {})
    # Merge both namespaces for character lookup
    all_user_chars = {**user_chars, **rw_user_chars}

    # ── Config ────────────────────────────────────────────────────────────────
    v2cfg = config.get('v2', {})

    Q_base_diag  = v2cfg.get('Q_base', [4.0, 0.01, 25.0, 0.01, 0.01])
    lambda_      = float(v2cfg.get('lambda', 0.7))
    eta          = float(v2cfg.get('eta', 0.3))
    xi           = float(v2cfg.get('xi', 0.05))
    N            = int(v2cfg.get('window_size', 3))
    K_look       = int(v2cfg.get('k_look', 10))
    vol_window   = int(v2cfg.get('vol_window', 10))

    drama_weights = v2cfg.get('drama_weights', {
        'distance': 0.4, 'structural': 0.3, 'contrast': 0.2, 'boundary': 0.1
    })

    cold_outputs = v2cfg.get('cold_start_outputs', {
        'gain_db': 0.0, 'brightness': 0.5,
        'timing_offset_ms': 0.0, 'attack_shape': 0.5, 'reverb_wet': 0.3
    })

    # Seed: v2cfg takes priority over root config
    seed = v2cfg.get('seed', config.get('seed', None))
    # If no seed provided, generate one so callers can reproduce this run.
    if seed is None:
        seed = int(np.random.SeedSequence().entropy & 0x7FFFFFFF)
    v2cfg['_effective_seed'] = int(seed)
    rng  = np.random.default_rng(seed)

    # Global output clipping method and custom physical limits
    clip_method     = str(v2cfg.get('clip_method', 'hard'))
    physical_limits = v2cfg.get('physical_limits', None)  # 5×2 list or None

    # Temporal ω smoothing: alpha=1 means no smoothing
    omega_smooth_alpha = float(v2cfg.get('omega_smooth', 1.0))

    # Salience α/β/γ/δ weights override (from global panel)
    sal_alpha = v2cfg.get('salience_alpha')
    sal_beta  = v2cfg.get('salience_beta')
    sal_gamma = v2cfg.get('salience_gamma')
    sal_delta = v2cfg.get('salience_delta')
    if any(x is not None for x in (sal_alpha, sal_beta, sal_gamma, sal_delta)):
        drama_weights = {
            'distance':   float(sal_alpha) if sal_alpha is not None else drama_weights.get('distance', 0.4),
            'structural': float(sal_beta)  if sal_beta  is not None else drama_weights.get('structural', 0.3),
            'contrast':   float(sal_gamma) if sal_gamma is not None else drama_weights.get('contrast', 0.2),
            'boundary':   float(sal_delta) if sal_delta is not None else drama_weights.get('boundary', 0.1),
        }

    # ── Score data ────────────────────────────────────────────────────────────
    events    = sorted(copy.deepcopy(score.get('events', [])), key=lambda e: e['t'])
    golems    = score.get('golems', [])
    total_dur = _total_duration(events, score)

    if not events:
        return (events, []) if return_trace else events

    # ── Dynamic markings ──────────────────────────────────────────────────────
    marking_pairs = _extract_markings(score)
    _no_markings  = not marking_pairs
    if _no_markings:
        # No dynamics in score — synthesise a neutral 'mp' at the start so the
        # Kalman filter can still run and produce audible golem-character variation.
        marking_pairs = [(0.0, 'mp')]

    markings_list = [p[1] for p in marking_pairs]
    boundaries    = _phrase_boundary_indices(score, marking_pairs)

    # ── Pre-rendering pass ────────────────────────────────────────────────────
    drama_vals_raw = compute_drama(markings_list, boundaries, drama_weights)
    # Without real markings, use a moderate fixed drama so Q_t is non-trivial
    if _no_markings:
        drama_vals_raw = [0.4] * len(drama_vals_raw)
    # Optional salience clamp
    if v2cfg.get('salience_clamp', False):
        drama_vals_raw = [min(d, 1.0) for d in drama_vals_raw]
    # Temporal ω smoothing
    drama_vals   = _smooth_drama(drama_vals_raw, omega_smooth_alpha)
    future_pulls = compute_future_pull(markings_list, drama_vals, lambda_, K=K_look)

    # ── Initialise filter ─────────────────────────────────────────────────────
    # Apply per-character cold-start bias from the first (dominant) golem,
    # then overlay any per-golem cold_start_bias override from the golem dict.
    cold_biased = dict(cold_outputs)
    if golems:
        from src.character import BUILTIN as _CHAR_BUILTIN
        _first_char = golems[0].get('character', '')
        _bias = _CHAR_BUILTIN.get(_first_char, {}).get('cold_start_bias', {})
        cold_biased.update(_bias)
        # Per-golem override wins
        _golem_bias = golems[0].get('cold_start_bias')
        if isinstance(_golem_bias, dict):
            cold_biased.update(_golem_bias)

    mu0     = np.array([cold_biased.get(k, _CHAR_DIM_DEFAULTS.get(k, 0.0))
                        for k in OUTPUT_KEYS], dtype=float)
    X_mu    = np.concatenate([mu0, mu0])
    X_Sigma = build_Sigma0(np.array(Q_base_diag, dtype=float))

    Q_base             = np.diag(np.array(Q_base_diag, dtype=float))
    innovation_history: list = []

    enriched = []
    trace    = [] if return_trace else None

    # Build a unified timeline: Kalman steps fire at EVERY marking time,
    # tempo change, phrase boundary, AND at regular intervals (0.5s) so the
    # filter responds continuously and visualizations animate smoothly.
    _event_by_t = {ev['t']: ev for ev in events}
    _marking_ts = set(p[0] for p in marking_pairs)
    _extra_ts   = set()
    # Harvest times from every score element that carries temporal info:
    # dynamics, tempo, phrases, golems, fx_ranges, note_rel, articulations
    for _key in ('dynamics', 'tempo', 'phrases', 'golems',
                 'fx_ranges', 'note_rel', 'articulations'):
        for item in score.get(_key, []):
            for _tk in ('t', 'from', 'to'):
                if _tk in item:
                    _extra_ts.add(float(item[_tk]))
    # Regular interval steps for smooth trace animation (0 = disabled)
    _step_interval = float(v2cfg.get('trace_step', 0.5))
    if _step_interval > 0:
        _t_cursor = 0.0
        while _t_cursor <= total_dur:
            _extra_ts.add(round(_t_cursor, 3))
            _t_cursor += _step_interval
    _all_ts     = sorted(_marking_ts | _extra_ts | set(ev['t'] for ev in events))

    _last_filter_t = None  # track when filter last stepped (to avoid double-stepping)

    for t in _all_ts:
        is_marking = t in _marking_ts
        ev         = _event_by_t.get(t)

        golem_type = _resolve_golem_type(t, golems)

        if golem_type == 'random_walk':
            # ── Random Walk branch ────────────────────────────────────────────
            rw_char   = rw_character_at(t, golems, total_dur, all_user_chars)
            # Golem-level overrides
            _rw_active = [g for g in golems if g.get('type') == 'random_walk'
                          and g.get('from', 0) <= t < g.get('to', total_dur)]
            if _rw_active:
                _dom = max(_rw_active, key=lambda g: float(g.get('weight', 1.0)))
                for _k in ('distribution', 'walk_mode', 'student_df', 'breath_period',
                           'breath_amp', 'step_size', 'drift', 'mr_dims', 'boundary_mode',
                           'mr_target', 'omega_step_scale', 'correlation',
                           'physical_limits', 'clip_method', 'dist_config'):
                    if _k in _dom:
                        rw_char[_k] = _dom[_k]

            # Provide drama value for omega_step_scale
            m_idx_rw  = _find_marking_for_event(t, marking_pairs)
            drama_rw  = drama_vals[m_idx_rw]

            x_new     = _rw_step(X_mu[:D], rw_char, rng, t=t, omega=drama_rw)
            X_mu[:D]  = x_new

            if return_trace:
                trace.append({
                    't':          float(t),
                    'mu':         x_new.tolist(),
                    'sigma_diag': np.array(rw_char['step_size']).tolist(),
                    'drama':      float(drama_rw),
                    'volatility': 0.0,
                    'golem_type': 'random_walk',
                    'character':  _resolve_character_name(t, golems),
                    'marking':    marking_pairs[m_idx_rw][1] if marking_pairs else '',
                    'sample':     x_new.tolist(),
                    'distribution': rw_char.get('distribution', 'gaussian'),
                })

            x_clipped = x_new  # boundary already applied in _rw_step

        elif golem_type == 'discrete':
            # ── Discrete branch — fixed state, no filter ─────────────────────
            _disc_active = [g for g in golems if g.get('type') == 'discrete'
                           and g.get('from', 0) <= t < g.get('to', total_dur)]
            _disc_state = np.array([_CHAR_DIM_DEFAULTS.get(k, 0.0)
                                    for k in OUTPUT_KEYS], dtype=float)
            if _disc_active:
                _dom = max(_disc_active, key=lambda g: float(g.get('weight', 1.0)))
                _st = _dom.get('state', {})
                for i, k in enumerate(OUTPUT_KEYS):
                    if k in _st:
                        _disc_state[i] = float(_st[k])
            # Update the filter state so transitions to/from discrete are smooth
            X_mu[:D] = _disc_state
            x_clipped = _disc_state

            if return_trace:
                trace.append({
                    't':          float(t),
                    'mu':         _disc_state.tolist(),
                    'sigma_diag': [0.0] * D,
                    'drama':      0.0,
                    'volatility': 0.0,
                    'golem_type': 'discrete',
                    'character':  _resolve_character_name(t, golems),
                    'marking':    '',
                    'sample':     _disc_state.tolist(),
                    'distribution': 'discrete',
                })

        else:
            # ── Kalman branch ─────────────────────────────────────────────────
            char   = character_at(t, golems, total_dur, all_user_chars)
            # Golem-level distribution / student_df override
            _k_active = [g for g in golems if g.get('type', 'kalman') not in ('random_walk', 'discrete')
                         and g.get('from', 0) <= t < g.get('to', total_dur)]

            # Per-golem extra params (initialise to defaults)
            _innov_decay  = 0.7
            _xi_eff       = xi
            _fp_mask      = None
            _fp_scale_vec = None
            _obs_w_dims   = None
            _gamma_w      = 1.0
            _golem_Q_base = None
            _inflate      = 1.0
            _inflate_dims = None
            _dist_cfg     = {}
            _sal_cond     = None
            _clip_sigma   = None
            _clip_sigma_dims = None

            if _k_active:
                _dom = max(_k_active, key=lambda g: float(g.get('weight', 1.0)))
                # Merge inline Kalman params from dominant golem
                for _ui_k, _char_k in (
                    ('A1', 'A1'), ('A2', 'A2'), ('Q_scale', 'Q_scale'), ('R_scale', 'R_scale'),
                    ('lam', 'lam'), ('obs_weight', 'obs_weight'), ('drama_curve', 'drama_curve'),
                    ('sample_dist', 'sample_dist'), ('rw_scatter', 'rw_scatter'),
                    ('distribution', 'sample_dist'), ('student_df', 'student_df'),
                ):
                    if _ui_k in _dom:
                        char[_char_k] = _dom[_ui_k]

                # New per-golem params
                if 'innov_decay' in _dom:
                    _innov_decay = float(_dom['innov_decay'])
                if 'xi_regime' in _dom and _dom['xi_regime'] is not None:
                    _xi_eff = float(_dom['xi_regime'])
                if 'fp_mask' in _dom and _dom['fp_mask'] is not None:
                    _fp_mask = [float(x) for x in _dom['fp_mask']]
                if 'fp_scale' in _dom and _dom['fp_scale'] is not None:
                    _fp_scale_vec = [float(x) for x in _dom['fp_scale']]
                if 'obs_weight_dims' in _dom and _dom['obs_weight_dims'] is not None:
                    _obs_w_dims = np.array(_dom['obs_weight_dims'], dtype=float)
                if 'gamma_w' in _dom and _dom['gamma_w'] is not None:
                    _gamma_w = float(_dom['gamma_w'])
                if 'Q_base' in _dom and _dom['Q_base'] is not None:
                    _golem_Q_base = np.diag(np.array(_dom['Q_base'], dtype=float))
                if 'inflate' in _dom and _dom['inflate'] is not None:
                    _inflate = float(_dom['inflate'])
                if 'inflate_dims' in _dom and _dom['inflate_dims'] is not None:
                    _inflate_dims = [float(x) for x in _dom['inflate_dims']]
                if 'clip_sigma' in _dom and _dom['clip_sigma'] is not None:
                    _clip_sigma = float(_dom['clip_sigma'])
                if 'clip_sigma_dims' in _dom and _dom['clip_sigma_dims'] is not None:
                    _clip_sigma_dims = [float(x) for x in _dom['clip_sigma_dims']]
                if 'dist_config' in _dom and _dom['dist_config']:
                    _dist_cfg = _dom['dist_config'] if isinstance(_dom['dist_config'], dict) else {}

                # dist_config may override sample_dist
                if _dist_cfg.get('dist'):
                    char['sample_dist'] = str(_dist_cfg['dist'])

                # Salience-conditioned distribution
                _sal_cond = _dist_cfg.get('salience_conditioned')

                # A1_dims / A2_dims from golem
                if 'A1_dims' in _dom and _dom['A1_dims'] is not None:
                    char['A1_dims'] = _dom['A1_dims']
                if 'A2_dims' in _dom and _dom['A2_dims'] is not None:
                    char['A2_dims'] = _dom['A2_dims']

            # Per-dim or scalar A1/A2
            A1_val = char.get('A1_dims') or char['A1']
            A2_val = char.get('A2_dims') or char['A2']
            Q_scl  = char['Q_scale']
            R_scl  = char['R_scale']
            lam    = char.get('lam', lambda_)
            obs_w  = float(char.get('obs_weight', 1.0))
            drama_curve   = char.get('drama_curve', 'linear')
            sample_dist   = char.get('sample_dist', 'gaussian')
            mixture_p     = float(char.get('mixture_p', 0.05))
            mixture_scale = float(char.get('mixture_scale', 4.0))

            # Use golem-level Q_base if provided, else global
            Q_base_eff = _golem_Q_base if _golem_Q_base is not None else Q_base

            A1_mat, A2_mat = make_AR_matrices(A1_val, A2_val, D)
            F     = build_F(A1_mat, A2_mat)

            m_idx   = _find_marking_for_event(t, marking_pairs)
            drama_t = drama_vals[m_idx]

            # Drama curve non-linearity
            drama_curved = _apply_drama_curve(drama_t, drama_curve)

            # Salience-conditioned distribution selection
            if _sal_cond:
                threshold = float(_sal_cond.get('threshold', 0.5))
                if drama_curved < threshold * 0.5:
                    sample_dist = _sal_cond.get('dist_low', sample_dist)
                elif drama_curved < threshold:
                    sample_dist = _sal_cond.get('dist_mid', sample_dist)
                else:
                    sample_dist = _sal_cond.get('dist_high', sample_dist)

            # Volatility: exponentially weighted mean of recent squared innovations
            vol_w = min(len(innovation_history), vol_window)
            if vol_w > 0:
                recent = innovation_history[-vol_w:]
                vol = sum((_innov_decay ** (vol_w - 1 - k)) * float(np.dot(recent[k], recent[k]))
                          for k in range(vol_w)) / vol_w
            else:
                vol = 0.0

            Q_t = Q_base_eff * Q_scl * max(drama_curved, 0.15) * (1.0 + eta * vol)
            Q_t = np.maximum(Q_t, np.diag(np.array(Q_base_diag, dtype=float)) * 1e-4)
            Q_aug_t = build_Q_aug(Q_t)

            # Future pull vector — honours fp_mask and fp_scale if set
            fp_scalar = future_pulls[m_idx]
            fp_vec    = np.zeros(D)
            if _fp_mask is not None and _fp_scale_vec is not None:
                for i in range(D):
                    mask_i  = _fp_mask[i] if i < len(_fp_mask) else 0.0
                    scale_i = _fp_scale_vec[i] if i < len(_fp_scale_vec) else 1.0
                    fp_vec[i] = fp_scalar * mask_i * scale_i
            elif _fp_scale_vec is not None:
                for i in range(D):
                    scale_i = _fp_scale_vec[i] if i < len(_fp_scale_vec) else 1.0
                    fp_vec[i] = fp_scalar * scale_i
            else:
                # Default: gain_db only
                fp_vec[0] = fp_scalar * 7.0

            X_mu_bar, X_Sigma_bar = predict(X_mu, X_Sigma, F, Q_aug_t,
                                            future_pull=fp_vec, xi=_xi_eff)

            # Character equilibrium: keep the AR(2) process anchored to the
            # golem character's target values rather than decaying to 0.
            # For stable AR(2): x_steady = (1-A1-A2)*target + A1*x[t-1] + A2*x[t-2]
            # The equilibrium correction is (1-A1-A2) * target added per step.
            if _k_active:
                _dom_char_name = max(_k_active,
                                     key=lambda g: float(g.get('weight', 1.0))).get('character', '')
                _char_eq_dict  = _KALMAN_BUILTIN.get(_dom_char_name, {}).get('cold_start_bias', {})
                if _char_eq_dict:
                    _mu_eq  = np.array([_char_eq_dict.get(k, 0.0) for k in OUTPUT_KEYS], dtype=float)
                    _remain = np.maximum(1.0 - np.diag(A1_mat) - np.diag(A2_mat), 0.0)
                    X_mu_bar[:D] += _remain * _mu_eq

            y    = build_window_obs(markings_list, m_idx, N)
            H, R = lookup_HR(markings_list, m_idx, N, windows_table, augmented_d=2*D)

            # Apply gamma_w window decay (older slots get higher R → less trusted)
            if _gamma_w < 1.0:
                for k in range(N):
                    R[k, k] *= (1.0 / max(_gamma_w ** k, 1e-6))

            # obs_weight scales how much the filter trusts the dynamics markings
            R = R * R_scl / max(obs_w, 0.01)

            # Per-dim observation weighting (scales H columns)
            if _obs_w_dims is not None:
                for i in range(D):
                    w_i = float(_obs_w_dims[i]) if i < len(_obs_w_dims) else 1.0
                    H[:, i] *= w_i

            X_mu, X_Sigma, nu, K_mat = update(X_mu_bar, X_Sigma_bar, y, H, R)
            innovation_history.append(nu)

            mu_cur  = X_mu[:D]
            Sig_cur = X_Sigma[:D, :D]
            Sig_cur = 0.5 * (Sig_cur + Sig_cur.T)
            eigvals = np.linalg.eigvalsh(Sig_cur)
            if eigvals.min() < 1e-8:
                Sig_cur += (1e-8 - eigvals.min()) * np.eye(D)

            # Build dist kwargs from dist_config
            dkw = _dist_kwargs_from_config(_dist_cfg)
            dkw['mixture_p']    = float(char.get('mixture_p', dkw['mixture_p']))
            dkw['mixture_scale'] = float(char.get('mixture_scale', dkw['mixture_scale']))
            dkw['student_df']   = float(char.get('student_df', dkw['student_df']))

            # Per-dimension distribution override
            _dist_dims = _dist_cfg.get('dist_dims')

            x_sample  = _sample_posterior(rng, mu_cur, Sig_cur,
                                          sample_dist, mixture_p, mixture_scale,
                                          student_df=float(char.get('student_df', 3.0)),
                                          inflate=_inflate, inflate_dims=_inflate_dims,
                                          dist_kwargs=dkw, dist_dims=_dist_dims,
                                          clip_sigma=_clip_sigma,
                                          clip_sigma_dims=_clip_sigma_dims)
            # Optional RW scatter: inject additional noise into the posterior sample
            rw_scatter = float(char.get('rw_scatter', 0.0))
            if rw_scatter > 0:
                std = np.sqrt(np.maximum(np.diag(Sig_cur), 1e-10))
                x_sample = x_sample + rng.normal(0, std * rw_scatter, D)

            x_clipped = _apply_boundary(x_sample, 'clip',
                                        custom_limits=physical_limits,
                                        clip_method=clip_method)

            if return_trace:
                trace.append({
                    't':          float(t),
                    'mu':         mu_cur.tolist(),
                    'mu_bar':     X_mu_bar[:D].tolist(),
                    'sigma_diag': np.sqrt(np.maximum(np.diag(Sig_cur), 0)).tolist(),
                    'Sigma':      Sig_cur.tolist(),
                    'K':          K_mat[:D, :D].tolist(),
                    'nu':         nu[:D].tolist(),
                    'Q_diag':     np.diag(Q_t).tolist(),
                    'phi':        fp_vec.tolist(),
                    'drama':      float(drama_t),
                    'volatility': float(vol),
                    'golem_type': 'kalman',
                    'character':  _resolve_character_name(t, golems),
                    'marking':    marking_pairs[m_idx][1] if marking_pairs else '',
                    'sample':     x_clipped.tolist(),
                    'distribution': sample_dist,
                })

        if ev is not None:
            enriched.append(_apply_state(ev, x_clipped))

    if return_trace:
        return enriched, trace
    return enriched
