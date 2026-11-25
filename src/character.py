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

13D expressive state:
  [gain_db, brightness, timing_offset_ms, attack_shape, release_shape,
   reverb_wet, filter_cutoff, filter_resonance, stereo_width,
   overdrive_drive, pitch_dev_cents, dynamic_center, tempo]

tempo is rubato: % faster (+) or slower (−) than written. Older 12-D
vectors (Q base, A1 per dim, random-walk steps…) are padded with defaults.
"""

import numpy as np

D = 13   # expressive state dimensions

# Dimension names in canonical order
DIM_NAMES = (
    'gain_db', 'brightness', 'timing_offset_ms', 'attack_shape', 'release_shape',
    'reverb_wet', 'filter_cutoff', 'filter_resonance', 'stereo_width',
    'overdrive_drive', 'pitch_dev_cents', 'dynamic_center', 'tempo',
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
    [-30.0,  30.0],      # tempo (% faster / slower than written)
]

# Default cold-start values per dimension
DIM_DEFAULTS = {
    'gain_db': 0.0, 'brightness': 0.5, 'timing_offset_ms': 0.0,
    'attack_shape': 0.5, 'release_shape': 0.5, 'reverb_wet': 0.3,
    'filter_cutoff': 5000.0, 'filter_resonance': 0.0, 'stereo_width': 0.5,
    'overdrive_drive': 0.0, 'pitch_dev_cents': 0.0, 'dynamic_center': -12.0,
    'tempo': 0.0,
}

# Default inertia per dimension (A1 diagonal values)
DIM_INERTIA = {
    'gain_db': 0.7, 'brightness': 0.7, 'timing_offset_ms': 0.4,
    'attack_shape': 0.7, 'release_shape': 0.7, 'reverb_wet': 0.85,
    'filter_cutoff': 0.7, 'filter_resonance': 0.7, 'stereo_width': 0.85,
    'overdrive_drive': 0.7, 'pitch_dev_cents': 0.4, 'dynamic_center': 0.92,
    'tempo': 0.9,
}

# ── Kalman characters ─────────────────────────────────────────────────────────
# timing_scale multiplies the timing noise (Q of timing_offset_ms): how loose
# the character's note placement is. Spread of the note timing with the
# default Q_base (std of the per-note offset, measured): disciplined 9 ms,
# sparse 10, memorised 11, impressionist 14, lyrical 15, volatile 18,
# impulsive / turbulent / sight_reading / dramatic ~20 (the last two with
# heavy tails that reach the ±50 ms limit now and then).

# rubato scales how much the tempo presses into crescendos and broadens at
# phrase ends (tempo dimension; 0 = strict, 1 ≈ +6 % pressing / −15 % at a
# phrase end, before the state's lag and noise).

# Global Q base (process noise per dimension) when config.yaml gives none
Q_BASE_DEFAULT = [0.5, 0.04, 250.0, 0.04, 0.04, 0.04, 4000.0, 0.05, 0.04, 0.05, 8.0, 1.0, 0.5]

_DEFAULT: dict = dict(
    A1=0.7, A2=0.2, Q_scale=1.0, R_scale=1.0, lam=0.7,
    A1_dims=None, A2_dims=None,
    drama_curve='linear',
    obs_weight=1.0,
    sample_dist='gaussian',
    mixture_p=0.05, mixture_scale=4.0,
    timing_scale=1.0, rubato=1.0,
)

# Each character's "home": where each dimension rests when nothing pulls it
# (the AR(2) process relaxes toward it). gain_db is an OFFSET from the current
# dynamic marking (sparse plays 4 dB under the marking, turbulent 4 dB over);
# every other value is absolute. Missing dims fall back to DIM_DEFAULTS.
def _home(**kw) -> dict:
    out = dict(DIM_DEFAULTS)
    out.update(kw)
    return out


# The presets — ONE definition, shared by the engine, scores and the editor
# (served to it by /golem_presets). Values match what the editor has always
# sent for its presets.
BUILTIN: dict = {
    'dramatic': dict(
        A1=0.80, A2=0.10, Q_scale=2.0, R_scale=1.5, lam=0.70, obs_weight=1.2, timing_scale=1.0, rubato=1.3,
        drama_curve='exp', sample_dist='laplace',
        cold_start_bias=_home(gain_db=3.0, brightness=0.25, attack_shape=0.35, release_shape=0.3,
                              reverb_wet=0.65, filter_cutoff=3000.0, filter_resonance=0.2,
                              stereo_width=0.7, overdrive_drive=0.15, dynamic_center=-6.0),
    ),
    'lyrical': dict(
        A1=0.65, A2=0.30, Q_scale=0.5, R_scale=0.8, lam=0.85, obs_weight=1.0, timing_scale=0.7, rubato=1.4,
        drama_curve='linear', sample_dist='gaussian',
        cold_start_bias=_home(gain_db=0.0, brightness=0.75, attack_shape=0.75, release_shape=0.7,
                              reverb_wet=0.40, filter_cutoff=8000.0, stereo_width=0.5,
                              dynamic_center=-12.0),
    ),
    'sparse': dict(
        A1=0.90, A2=0.00, Q_scale=0.2, R_scale=0.5, lam=0.40, obs_weight=1.5, timing_scale=0.9, rubato=0.5,
        drama_curve='linear', sample_dist='gaussian',
        cold_start_bias=_home(gain_db=-4.0, brightness=0.50, attack_shape=0.10, release_shape=0.4,
                              reverb_wet=0.05, filter_cutoff=5000.0, stereo_width=0.3,
                              dynamic_center=-18.0),
    ),
    'turbulent': dict(
        A1=0.50, A2=0.20, Q_scale=3.0, R_scale=2.0, lam=0.30, obs_weight=0.6, timing_scale=2.2, rubato=1.0,
        drama_curve='square', sample_dist='student_t', student_df=3.0,
        cold_start_bias=_home(gain_db=4.0, brightness=0.55, attack_shape=0.20, release_shape=0.2,
                              reverb_wet=0.55, filter_cutoff=2000.0, filter_resonance=0.4,
                              stereo_width=0.8, overdrive_drive=0.3, dynamic_center=-4.0),
    ),
    'disciplined': dict(
        A1=0.85, A2=0.10, Q_scale=0.3, R_scale=0.3, lam=0.80, obs_weight=2.0, timing_scale=0.15, rubato=0.3,
        drama_curve='linear', sample_dist='gaussian',
        cold_start_bias=_home(gain_db=0.0, brightness=0.5, attack_shape=0.5, release_shape=0.5,
                              reverb_wet=0.2, filter_cutoff=8000.0, stereo_width=0.5,
                              dynamic_center=-10.0),
    ),
    'impressionist': dict(
        A1=0.60, A2=0.25, Q_scale=1.0, R_scale=2.5, lam=0.90, obs_weight=0.4, timing_scale=3.7, rubato=1.6,
        drama_curve='linear', sample_dist='beta',
        cold_start_bias=_home(gain_db=-1.0, brightness=0.6, attack_shape=0.8, release_shape=0.85,
                              reverb_wet=0.6, filter_cutoff=6000.0, stereo_width=0.75,
                              dynamic_center=-14.0),
    ),
    'impulsive': dict(
        A1=0.40, A2=0.10, Q_scale=2.5, R_scale=0.8, lam=0.50, obs_weight=1.0, timing_scale=4.5, rubato=0.8,
        drama_curve='exp', sample_dist='cauchy',
        cold_start_bias=_home(gain_db=2.0, brightness=0.6, attack_shape=0.1, release_shape=0.3,
                              reverb_wet=0.15, filter_cutoff=9000.0, stereo_width=0.6,
                              overdrive_drive=0.2, dynamic_center=-5.0),
    ),
    'volatile': dict(
        A1=0.70, A2=0.15, Q_scale=1.5, R_scale=1.2, lam=0.60, obs_weight=0.8, timing_scale=1.9, rubato=1.2,
        drama_curve='square', sample_dist='bimodal', dist_config={'bimodal_sep': 0.75},
        cold_start_bias=_home(gain_db=1.0, brightness=0.55, attack_shape=0.3, release_shape=0.4,
                              reverb_wet=0.35, filter_cutoff=7000.0, stereo_width=0.7,
                              overdrive_drive=0.15, dynamic_center=-6.0),
    ),
    'sight_reading': dict(
        A1=0.75, A2=0.15, Q_scale=1.0, R_scale=1.0, lam=0.20, obs_weight=1.0, timing_scale=1.15, rubato=0.5,
        drama_curve='linear', sample_dist='gaussian',
        cold_start_bias=_home(gain_db=-1.0, brightness=0.5, attack_shape=0.5, release_shape=0.5,
                              reverb_wet=0.25, filter_cutoff=6000.0, stereo_width=0.5,
                              dynamic_center=-10.0),
    ),
    'memorised': dict(
        A1=0.70, A2=0.20, Q_scale=1.0, R_scale=1.0, lam=0.95, obs_weight=1.0, timing_scale=0.3, rubato=1.0,
        drama_curve='linear', sample_dist='gaussian',
        cold_start_bias=_home(gain_db=0.0, brightness=0.55, attack_shape=0.6, release_shape=0.6,
                              reverb_wet=0.3, filter_cutoff=8000.0, stereo_width=0.55,
                              dynamic_center=-10.0),
    ),
}


def home_values(name: str, user_chars: dict | None = None, golem: dict | None = None) -> dict:
    """A character's home values: defaults, then the preset's, then a user
    character's, then the golem's own `cold_start_bias` (each overriding)."""
    out = dict(DIM_DEFAULTS)
    out.update(BUILTIN.get(name, {}).get('cold_start_bias', {}))
    if user_chars and isinstance(user_chars.get(name), dict):
        out.update(user_chars[name].get('cold_start_bias', {}) or {})
    if golem and isinstance(golem.get('cold_start_bias'), dict):
        out.update(golem['cold_start_bias'])
    return out

# Keys that blend by weighted average (scalar)
_SCALAR_KEYS = ('A1', 'A2', 'Q_scale', 'R_scale', 'lam', 'obs_weight', 'mixture_p', 'mixture_scale',
                'timing_scale', 'rubato')
# Keys where the dominant golem's value wins (strings)
_STRING_KEYS = ('drama_curve', 'sample_dist')

# ── Random Walk characters ────────────────────────────────────────────────────

# step_size order: gain_db, brightness, timing_ms, attack, release, reverb,
#                  filter_cutoff, filter_res, stereo_w, overdrive, pitch_cents, dyn_center, tempo
_RW_DEFAULT: dict = dict(
    step_size=[1.5, 0.05, 20.0, 0.05, 0.05, 0.05, 200.0, 0.05, 0.05, 0.05, 5.0, 1.0, 0.6],
    drift=[0.0] * D,
    mean_reversion=0.0,
    mr_dims=None,
    distribution='gaussian',
    boundary_mode='clip',
    correlation=None,
    mixture_p=0.05, mixture_scale=4.0,
)

def _rw(step, drift=None, mr=0.0, boundary='reflect', dist='gaussian', **extra):
    step = list(step)
    if len(step) < D:                 # tempo step in proportion to the gain step
        step += [0.6 * step[0] / 1.5] * (D - len(step))
    drift = (list(drift) + [0.0] * (D - len(drift))) if drift else [0.0] * D
    d = dict(step_size=step, drift=drift,
             mean_reversion=0.0, mr_dims=[float(mr)] * D if mr else None,
             distribution=dist, boundary_mode=boundary, correlation=None,
             mixture_p=0.05, mixture_scale=4.0)
    d.update(extra)
    return d


# Random-walk presets — one definition, shared with the editor (/golem_presets).
# Mean reversion pulls toward the home values (DIM_DEFAULTS unless mr_target
# is given), not toward zero.
RW_BUILTIN: dict = {
    'rw_free':      _rw([1.5, 0.05, 20, 0.05, 0.05, 0.05, 200, 0.05, 0.05, 0.05, 5, 1]),
    'rw_drift_up':  _rw([1.2, 0.04, 15, 0.04, 0.04, 0.04, 150, 0.04, 0.04, 0.04, 4, 0.8],
                        drift=[0.3, 0.01, 2, 0.01, 0.01, 0.01, 50, 0.01, 0.01, 0.01, 1, 0.2], boundary='clip'),
    'rw_reverting': _rw([1.5, 0.05, 20, 0.05, 0.05, 0.05, 200, 0.05, 0.05, 0.05, 5, 1], mr=0.12),
    'drift_down':   _rw([1.0, 0.03, 12, 0.03, 0.03, 0.03, 100, 0.03, 0.03, 0.03, 3, 0.5],
                        drift=[-0.2, -0.01, -1.5, -0.01, -0.01, -0.01, -30, -0.01, -0.01, -0.01, -0.5, -0.1],
                        boundary='clip'),
    'breathing':    _rw([0.5, 0.02, 8, 0.02, 0.02, 0.02, 80, 0.02, 0.02, 0.02, 2, 0.4], mr=0.05,
                        breath_period=8.0, breath_amp=0.6),
    'free_improv':  _rw([2.5, 0.08, 30, 0.08, 0.08, 0.08, 300, 0.08, 0.08, 0.08, 8, 1.5], dist='laplace'),
    'anchored':     _rw([1.0, 0.03, 12, 0.03, 0.03, 0.03, 100, 0.03, 0.03, 0.03, 3, 0.5], mr=0.3),
    'dream':        _rw([0.3, 0.01, 5, 0.01, 0.01, 0.01, 50, 0.01, 0.01, 0.01, 1, 0.2], mr=0.02, dist='beta'),
    'erratic':      _rw([3.0, 0.10, 40, 0.10, 0.10, 0.10, 400, 0.10, 0.10, 0.10, 10, 2],
                        boundary='clip', dist='cauchy'),
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
    for k in ('A1', 'A2'):
        scalar = float(char.get(k, _DEFAULT[k]))
        v = char.get(k + '_dims')
        v = [] if v is None else [float(x) for x in v][:D]
        char[k + '_dims'] = v + [scalar] * (D - len(v))      # older 12-D vectors padded
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
                      'A1_dims','A2_dims','student_df','dist_blend','dist_config',
                      'timing_scale', 'rubato')
    chars = []
    for g in active:
        c = _get_char(g.get('character', 'default'), user_chars)
        for k in _INLINE_KALMAN:
            if k in g and g[k] is not None:
                c[k] = g[k]
        if g.get('distribution'):                  # the editor's name for sample_dist
            c['sample_dist'] = g['distribution']
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

    # Each golem's own settings (sent inline by the editor) override its preset
    # before blending, so a crossfade blends what each golem really is
    _INLINE_RW = ('step_size', 'drift', 'mean_reversion', 'mr_dims', 'distribution',
                  'boundary_mode', 'mixture_p', 'mixture_scale')
    chars = []
    for g in active:
        c = _get_rw_char(g.get('character', 'rw_free'), user_chars)
        for k in _INLINE_RW:
            if k in g and g[k] is not None:
                c[k] = g[k]
        chars.append(c)

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
    def _dim(vec, i, default):
        return float(vec[i]) if vec is not None and i < len(vec) else default

    for w, c in zip(weights, chars):
        for i in range(D):
            blended['step_size'][i] += w * _dim(c.get('step_size'), i, _RW_DEFAULT['step_size'][i])
            blended['drift'][i]     += w * _dim(c.get('drift'), i, 0.0)
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
