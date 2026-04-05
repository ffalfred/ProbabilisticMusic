"""
Piece characters — named expressive personality bundles.

Three golem types are supported:

  type: kalman  (default)
    Parameters: A1, A2 (AR momentum), Q_scale, R_scale, lam (familiarity),
                A1_dims/A2_dims (per-dimension overrides of A1/A2),
                drama_curve ('linear'|'square'|'exp'),
                obs_weight (0–1, how strongly this golem follows dynamics),
                sample_dist ('gaussian'|'laplace'|'cauchy'|'mixture'),
                mixture_p, mixture_scale (for mixture distribution).

  type: random_walk
    Parameters: step_size[D], drift[D], mean_reversion (scalar),
                mr_dims[D] (per-dimension mean reversion override),
                distribution ('gaussian'|'laplace'|'cauchy'|'uniform'|'beta'|'mixture'),
                boundary_mode ('clip'|'reflect'),
                correlation (D×D matrix or None),
                mixture_p, mixture_scale.

  type: discrete
    Fixed state vector — no drift, no AR momentum, no reaction to score markings.
    Parameters: state dict mapping dimension names to explicit values.

Golem-level envelope fields (used by interpreter, not stored in character bundles):
    weight     — blend weight (default 1.0)
    fade_in    — seconds over which the golem fades in from the start of its range
    fade_out   — seconds over which the golem fades out before the end of its range

12D expressive state:
  [gain_db, brightness, timing_offset_ms, attack_shape, release_shape,
   reverb_wet, filter_cutoff, filter_resonance, stereo_width,
   overdrive_drive, pitch_dev_cents, dynamic_center]
"""

import numpy as np

D = 12   # expressive state dimensions

# Dimension names in canonical order
DIM_NAMES = (
    'gain_db', 'brightness', 'timing_offset_ms', 'attack_shape', 'release_shape',
    'reverb_wet', 'filter_cutoff', 'filter_resonance', 'stereo_width',
    'overdrive_drive', 'pitch_dev_cents', 'dynamic_center',
)

# Physical limits per dimension [lo, hi]
DIM_RANGES = [
    [-40.0,   6.0],      # gain_db
    [  0.0,   1.0],      # brightness
    [-50.0,  50.0],      # timing_offset_ms
    [  0.0,   1.0],      # attack_shape
    [  0.0,   1.0],      # release_shape
    [  0.0,   1.0],      # reverb_wet
    [ 20.0, 20000.0],    # filter_cutoff (Hz)
    [  0.0,   1.0],      # filter_resonance
    [  0.0,   1.0],      # stereo_width
    [  0.0,   1.0],      # overdrive_drive
    [-50.0,  50.0],      # pitch_dev_cents
    [-30.0,   0.0],      # dynamic_center (dB)
]

# Default cold-start values per dimension
DIM_DEFAULTS = {
    'gain_db': 0.0, 'brightness': 0.5, 'timing_offset_ms': 0.0,
    'attack_shape': 0.5, 'release_shape': 0.5, 'reverb_wet': 0.3,
    'filter_cutoff': 5000.0, 'filter_resonance': 0.0, 'stereo_width': 0.5,
    'overdrive_drive': 0.0, 'pitch_dev_cents': 0.0, 'dynamic_center': -12.0,
}

# Default inertia per dimension (A1 diagonal values)
DIM_INERTIA = {
    'gain_db': 0.7, 'brightness': 0.7, 'timing_offset_ms': 0.4,
    'attack_shape': 0.7, 'release_shape': 0.7, 'reverb_wet': 0.85,
    'filter_cutoff': 0.7, 'filter_resonance': 0.7, 'stereo_width': 0.85,
    'overdrive_drive': 0.7, 'pitch_dev_cents': 0.4, 'dynamic_center': 0.92,
}

# ── Kalman characters ─────────────────────────────────────────────────────────

_DEFAULT: dict = dict(
    A1=0.7, A2=0.2, Q_scale=1.0, R_scale=1.0, lam=0.7,
    A1_dims=None, A2_dims=None,
    drama_curve='linear',
    obs_weight=1.0,
    sample_dist='gaussian',
    mixture_p=0.05, mixture_scale=4.0,
)

BUILTIN: dict = {
    'dramatic': dict(
        A1=0.8, A2=0.1, Q_scale=2.0, R_scale=2.0, lam=0.7,
        A1_dims=None, A2_dims=None,
        drama_curve='exp',
        obs_weight=1.0,
        sample_dist='mixture', mixture_p=0.08, mixture_scale=3.5,
        cold_start_bias={
            'gain_db': 3.0, 'brightness': 0.25, 'timing_offset_ms': 0.0,
            'attack_shape': 0.35, 'release_shape': 0.3,
            'reverb_wet': 0.65, 'filter_cutoff': 3000.0, 'filter_resonance': 0.2,
            'stereo_width': 0.7, 'overdrive_drive': 0.15,
            'pitch_dev_cents': 0.0, 'dynamic_center': -6.0,
        },
    ),
    'lyrical': dict(
        A1=0.6, A2=0.3, Q_scale=0.5, R_scale=1.0, lam=0.8,
        A1_dims=None, A2_dims=None,
        drama_curve='linear',
        obs_weight=1.0,
        sample_dist='gaussian', mixture_p=0.05, mixture_scale=2.0,
        cold_start_bias={
            'gain_db': 0.0, 'brightness': 0.75, 'timing_offset_ms': 0.0,
            'attack_shape': 0.75, 'release_shape': 0.7,
            'reverb_wet': 0.40, 'filter_cutoff': 8000.0, 'filter_resonance': 0.0,
            'stereo_width': 0.5, 'overdrive_drive': 0.0,
            'pitch_dev_cents': 0.0, 'dynamic_center': -12.0,
        },
    ),
    'sparse': dict(
        A1=0.9, A2=0.0, Q_scale=0.2, R_scale=0.5, lam=0.4,
        A1_dims=None, A2_dims=None,
        drama_curve='square',
        obs_weight=0.6,
        sample_dist='gaussian', mixture_p=0.02, mixture_scale=2.0,
        cold_start_bias={
            'gain_db': -4.0, 'brightness': 0.50, 'timing_offset_ms': 0.0,
            'attack_shape': 0.10, 'release_shape': 0.4,
            'reverb_wet': 0.05, 'filter_cutoff': 5000.0, 'filter_resonance': 0.0,
            'stereo_width': 0.3, 'overdrive_drive': 0.0,
            'pitch_dev_cents': 0.0, 'dynamic_center': -18.0,
        },
    ),
    'turbulent': dict(
        A1=0.5, A2=0.2, Q_scale=3.0, R_scale=2.0, lam=0.3,
        A1_dims=None, A2_dims=None,
        drama_curve='exp',
        obs_weight=1.0,
        sample_dist='cauchy', mixture_p=0.15, mixture_scale=5.0,
        cold_start_bias={
            'gain_db': 4.0, 'brightness': 0.55, 'timing_offset_ms': 0.0,
            'attack_shape': 0.20, 'release_shape': 0.2,
            'reverb_wet': 0.55, 'filter_cutoff': 2000.0, 'filter_resonance': 0.4,
            'stereo_width': 0.8, 'overdrive_drive': 0.3,
            'pitch_dev_cents': 0.0, 'dynamic_center': -4.0,
        },
    ),
}

# Keys that blend by weighted average (scalar)
_SCALAR_KEYS = ('A1', 'A2', 'Q_scale', 'R_scale', 'lam', 'obs_weight', 'mixture_p', 'mixture_scale')
# Keys where the dominant golem's value wins (strings)
_STRING_KEYS = ('drama_curve', 'sample_dist')

# ── Random Walk characters ────────────────────────────────────────────────────

# step_size order: gain_db, brightness, timing_ms, attack, release, reverb,
#                  filter_cutoff, filter_res, stereo_w, overdrive, pitch_cents, dyn_center
_RW_DEFAULT: dict = dict(
    step_size=[1.5, 0.05, 20.0, 0.05, 0.05, 0.05, 200.0, 0.05, 0.05, 0.05, 5.0, 1.0],
    drift=[0.0] * D,
    mean_reversion=0.0,
    mr_dims=None,
    distribution='gaussian',
    boundary_mode='clip',
    correlation=None,
    mixture_p=0.05, mixture_scale=4.0,
)

RW_BUILTIN: dict = {
    'rw_free': dict(
        step_size=[1.5, 0.05, 20.0, 0.05, 0.05, 0.05, 200.0, 0.05, 0.05, 0.05, 5.0, 1.0],
        drift=[0.0] * D,
        mean_reversion=0.0, mr_dims=None,
        distribution='gaussian',
        boundary_mode='clip',
        correlation=None,
        mixture_p=0.05, mixture_scale=4.0,
    ),
    'rw_drift_up': dict(
        step_size=[1.0, 0.03, 10.0, 0.03, 0.03, 0.03, 100.0, 0.03, 0.03, 0.03, 3.0, 0.5],
        drift=[0.3, 0.01, 5.0, 0.01, 0.01, 0.01, 50.0, 0.01, 0.01, 0.01, 1.0, 0.2],
        mean_reversion=0.0, mr_dims=None,
        distribution='gaussian',
        boundary_mode='reflect',
        correlation=None,
        mixture_p=0.05, mixture_scale=4.0,
    ),
    'rw_reverting': dict(
        step_size=[1.2, 0.04, 15.0, 0.04, 0.04, 0.04, 150.0, 0.04, 0.04, 0.04, 4.0, 0.8],
        drift=[0.0] * D,
        mean_reversion=0.15, mr_dims=None,
        distribution='gaussian',
        boundary_mode='clip',
        correlation=None,
        mixture_p=0.05, mixture_scale=4.0,
    ),
}

_RW_SCALAR_KEYS = ('mean_reversion', 'mixture_p', 'mixture_scale')
_RW_STRING_KEYS = ('distribution', 'boundary_mode')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fade_curve(x: float, curve: str) -> float:
    """
    Map a linear ramp position x ∈ [0, 1] through the chosen curve.
    x=0 is the start of the fade, x=1 is full weight.
    """
    if curve == 'exp':
        return (np.exp(3.0 * x) - 1.0) / (np.exp(3.0) - 1.0)
    elif curve == 'sigmoid':
        # logistic centred at 0.5
        return 1.0 / (1.0 + np.exp(-12.0 * (x - 0.5)))
    elif curve == 'cosine':
        return 0.5 * (1.0 - np.cos(np.pi * x))
    return float(x)  # linear


def _golem_fade_weight(g: dict, t: float, total_dur: float) -> float:
    """Compute the effective weight of a golem at time t, including fade envelope."""
    w        = float(g.get('weight', 1.0))
    g_from   = float(g.get('from', 0))
    g_to     = float(g.get('to', total_dur))
    fade_in  = float(g.get('fade_in', 0.0))
    fade_out = float(g.get('fade_out', 0.0))
    curve    = str(g.get('fade_curve', 'linear'))
    if fade_in > 0 and (t - g_from) < fade_in:
        w *= _fade_curve((t - g_from) / fade_in, curve)
    if fade_out > 0 and (g_to - t) < fade_out:
        w *= _fade_curve((g_to - t) / fade_out, curve)
    return max(w, 0.0)


def _merge_defaults(base: dict, extra: dict | None) -> dict:
    """Merge user-supplied extra fields on top of base, returning a copy."""
    out = dict(base)
    if extra:
        out.update(extra)
    return out


def _get_char(name: str, user_chars: dict | None) -> dict:
    """Resolve a Kalman character name → fully-specified parameter bundle."""
    base = dict(BUILTIN.get(name, _DEFAULT))
    # Fill in any missing keys from _DEFAULT
    for k, v in _DEFAULT.items():
        base.setdefault(k, v)
    if user_chars and name in user_chars:
        base.update(user_chars[name])
    return base


def _get_rw_char(name: str, user_chars: dict | None) -> dict:
    """Resolve a random-walk character name → fully-specified parameter bundle."""
    base = dict(RW_BUILTIN.get(name, _RW_DEFAULT))
    for k, v in _RW_DEFAULT.items():
        base.setdefault(k, v)
    if user_chars and name in user_chars:
        base.update(user_chars[name])
    return base


def _expand_dims(char: dict) -> dict:
    """Ensure A1_dims and A2_dims are always D-element float lists."""
    if char.get('A1_dims') is None:
        char['A1_dims'] = [float(char.get('A1', _DEFAULT['A1']))] * D
    else:
        char['A1_dims'] = [float(x) for x in char['A1_dims'][:D]]
    if char.get('A2_dims') is None:
        char['A2_dims'] = [float(char.get('A2', _DEFAULT['A2']))] * D
    else:
        char['A2_dims'] = [float(x) for x in char['A2_dims'][:D]]
    return char


# ── Public API ────────────────────────────────────────────────────────────────

def character_at(t: float,
                 golems: list,
                 total_dur: float,
                 user_chars: dict | None = None) -> dict:
    """
    Compute the blended Kalman character bundle at time t.

    Blend weights honour per-golem 'weight', 'fade_in', 'fade_out' fields.
    Scalar parameters are averaged; string parameters use the dominant golem.
    Per-dim A1/A2 arrays are always returned (never None).
    """
    if not golems:
        return _expand_dims(dict(_DEFAULT))

    active = [g for g in golems
              if g.get('type', 'kalman') != 'random_walk'
              and g.get('from', 0) <= t < g.get('to', total_dur)]

    if not active:
        return _expand_dims(dict(_DEFAULT))

    weights = [_golem_fade_weight(g, t, total_dur) for g in active]
    total_w = sum(weights)
    if total_w == 0:
        return _expand_dims(dict(_DEFAULT))
    weights = [w / total_w for w in weights]

    # Build character bundle per golem: named lookup + inline param overrides
    _INLINE_KALMAN = ('A1','A2','Q_scale','R_scale','lam','obs_weight',
                      'drama_curve','sample_dist','mixture_p','mixture_scale',
                      'A1_dims','A2_dims','student_df')
    chars = []
    for g in active:
        c = _get_char(g.get('character', 'default'), user_chars)
        for k in _INLINE_KALMAN:
            if k in g:
                c[k] = g[k]
        chars.append(c)

    if len(active) == 1:
        return _expand_dims(chars[0])

    # Blend scalar keys
    blended: dict = {}
    for k in _SCALAR_KEYS:
        blended[k] = sum(w * c.get(k, _DEFAULT.get(k, 0.0))
                         for w, c in zip(weights, chars))

    # String keys: dominant golem
    dom_idx = int(np.argmax(weights))
    for k in _STRING_KEYS:
        blended[k] = chars[dom_idx].get(k, _DEFAULT.get(k, ''))

    # dist_blend: when 'mixture', increase mixture_p proportional to non-dominant weight
    # This blends two regime distributions as a Gaussian + spike rather than snapping.
    dist_blend = chars[dom_idx].get('dist_blend', 'dominant')
    if dist_blend == 'mixture' and len(active) > 1:
        non_dom_w = 1.0 - weights[dom_idx]
        blended['mixture_p'] = float(np.clip(
            blended.get('mixture_p', 0.05) + non_dom_w * 0.3, 0.0, 0.5))

    # Per-dim A1/A2: blend element-wise (expand scalars first)
    def _expand_scalar(c, scalar_key, dims_key):
        v = c.get(dims_key)
        if v is None:
            return [float(c.get(scalar_key, _DEFAULT.get(scalar_key, 0.7)))] * D
        return [float(x) for x in v[:D]]

    a1_expanded = [_expand_scalar(c, 'A1', 'A1_dims') for c in chars]
    a2_expanded = [_expand_scalar(c, 'A2', 'A2_dims') for c in chars]
    blended['A1_dims'] = [sum(weights[i] * a1_expanded[i][d] for i in range(len(chars)))
                          for d in range(D)]
    blended['A2_dims'] = [sum(weights[i] * a2_expanded[i][d] for i in range(len(chars)))
                          for d in range(D)]
    # Keep scalar A1/A2 as weighted mean for backward compat
    blended.setdefault('A1', sum(w * c.get('A1', 0.7) for w, c in zip(weights, chars)))
    blended.setdefault('A2', sum(w * c.get('A2', 0.2) for w, c in zip(weights, chars)))

    return blended


def rw_character_at(t: float,
                    golems: list,
                    total_dur: float,
                    user_chars: dict | None = None) -> dict:
    """
    Return the blended random-walk character bundle active at time t.
    Only considers golems with type == 'random_walk'.
    """
    active = [g for g in golems
              if g.get('type') == 'random_walk'
              and g.get('from', 0) <= t < g.get('to', total_dur)]

    if not active:
        return dict(_RW_DEFAULT)

    weights = [_golem_fade_weight(g, t, total_dur) for g in active]
    total_w = sum(weights)
    if total_w == 0:
        return dict(_RW_DEFAULT)
    weights = [w / total_w for w in weights]

    chars = [_get_rw_char(g['character'], user_chars) for g in active]

    if len(active) == 1:
        return chars[0]

    # Blend element-wise vectors
    blended: dict = {
        'step_size':      [0.0] * D,
        'drift':          [0.0] * D,
        'mean_reversion': 0.0,
        'mixture_p':      0.0,
        'mixture_scale':  0.0,
    }
    for w, c in zip(weights, chars):
        for i in range(D):
            blended['step_size'][i] += w * c['step_size'][i]
            blended['drift'][i]     += w * c['drift'][i]
        for k in _RW_SCALAR_KEYS:
            blended[k] += w * c.get(k, _RW_DEFAULT.get(k, 0.0))

    # String keys: dominant golem
    dom_idx = int(np.argmax(weights))
    for k in _RW_STRING_KEYS:
        blended[k] = chars[dom_idx].get(k, _RW_DEFAULT.get(k, ''))

    # Per-dim mean reversion: blend element-wise
    def _expand_mr(c):
        v = c.get('mr_dims')
        if v is None:
            return [float(c.get('mean_reversion', 0.0))] * D
        return [float(x) for x in v[:D]]

    mr_expanded = [_expand_mr(c) for c in chars]
    blended['mr_dims'] = [sum(weights[i] * mr_expanded[i][d] for i in range(len(chars)))
                          for d in range(D)]

    # Correlation: dominant golem's matrix (blending matrices is non-trivial)
    blended['correlation'] = chars[dom_idx].get('correlation')

    return blended


def make_AR_matrices(A1, A2, d: int) -> tuple:
    """
    Build d×d diagonal AR(2) coefficient matrices.
    A1 and A2 may be scalars or length-d lists/arrays.

    Returns (A1_mat, A2_mat) — both shape (d, d).
    """
    def _to_diag(v, d):
        if np.isscalar(v):
            return np.eye(d) * float(v)
        arr = np.array(v, dtype=float)
        if arr.ndim == 0:
            return np.eye(d) * float(arr)
        return np.diag(arr[:d])

    return _to_diag(A1, d), _to_diag(A2, d)
