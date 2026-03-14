import numpy as np

OUTPUT_PARAMS = ['gain_db', 'brightness', 'timing_offset_ms', 'attack_shape', 'reverb_wet']

# Fallback chain for unknown transition keys
_FALLBACK_ORDER = ['any_to_mf']


def _resolve_key(marking_key: str, transition_table: dict) -> str:
    """
    Resolve a transition key using the fallback chain:
      1. Exact key (e.g. 'p_to_mp')
      2. Wildcard 'any_to_<curr>' (e.g. 'any_to_sfz')
      3. Neutral fallback 'any_to_mf'
    """
    if marking_key in transition_table:
        return marking_key

    # Try wildcard: any_to_<curr_marking>
    parts = marking_key.split('_to_')
    if len(parts) == 2:
        wildcard = f"any_to_{parts[1]}"
        if wildcard in transition_table:
            return wildcard

    # Neutral fallback
    return 'any_to_mf'


def sample_output(marking_key: str, transition_table: dict, context: dict,
                  covariance_mode: str, rng: np.random.Generator) -> dict:
    """
    Sample the output vector o(t) from a multivariate Gaussian.

    Args:
        marking_key:      transition key, e.g. 'p_to_mp' or 'any_to_sfz'
        transition_table: loaded from transition_table.yaml (the 'transitions' sub-dict)
        context:          dict from compute_context()
        covariance_mode:  'diagonal' or 'full'
        rng:              seeded numpy Generator

    Returns:
        dict with keys: gain_db, brightness, timing_offset_ms, attack_shape, reverb_wet
    """
    key = _resolve_key(marking_key, transition_table)
    entry = transition_table[key]

    mu = np.array([entry[p]['mean'] for p in OUTPUT_PARAMS], dtype=float)
    stds = np.array([entry[p]['std'] for p in OUTPUT_PARAMS], dtype=float)

    if covariance_mode == 'full' and 'correlations' in entry:
        sigma = _build_full_cov(stds, entry['correlations'])
    else:
        sigma = np.diag(stds ** 2)

    # Context modulation: scale timing and gain slightly by phrase/piece position
    # This gives the Gaussian a gentle deterministic nudge without hard-coding rules.
    phrase_pos = context.get('phrase_position', 0.5)
    density    = context.get('event_density', 1.0)

    # Denser passages: tighter timing (reduce timing_offset std slightly)
    timing_idx = OUTPUT_PARAMS.index('timing_offset_ms')
    sigma[timing_idx, timing_idx] *= max(0.5, 1.0 - density * 0.05)

    # Phrase endings: slightly more freedom (widen gain std)
    gain_idx = OUTPUT_PARAMS.index('gain_db')
    sigma[gain_idx, gain_idx] *= (1.0 + 0.3 * phrase_pos)

    sample = rng.multivariate_normal(mu, sigma)
    return {p: float(sample[i]) for i, p in enumerate(OUTPUT_PARAMS)}


def sample_gradient(gradient_key: str, transition_table: dict,
                    rng: np.random.Generator) -> dict:
    """
    Sample a per-second rate for cresc/decresc.

    Returns:
        dict with keys: gain_db_per_sec, brightness_per_sec
    """
    key = gradient_key  # 'cresc' or 'decresc'
    if key not in transition_table:
        return {'gain_db_per_sec': 0.0, 'brightness_per_sec': 0.0}

    entry = transition_table[key]
    result = {}
    for param in ('gain_db_per_sec', 'brightness_per_sec'):
        if param in entry:
            mean = entry[param]['mean']
            std  = entry[param]['std']
            result[param] = float(rng.normal(mean, std))
        else:
            result[param] = 0.0
    return result


def _build_full_cov(stds: np.ndarray, correlations: dict) -> np.ndarray:
    """Build a full covariance matrix from stds and correlation pairs."""
    n = len(stds)
    corr_mat = np.eye(n)
    for pair, rho in correlations.items():
        parts = pair.split('_x_')
        if len(parts) == 2 and parts[0] in OUTPUT_PARAMS and parts[1] in OUTPUT_PARAMS:
            i = OUTPUT_PARAMS.index(parts[0])
            j = OUTPUT_PARAMS.index(parts[1])
            corr_mat[i, j] = rho
            corr_mat[j, i] = rho
    sigma = np.outer(stds, stds) * corr_mat
    # Ensure positive semi-definite
    eigenvalues = np.linalg.eigvalsh(sigma)
    if np.any(eigenvalues < 0):
        sigma += np.eye(n) * (-eigenvalues.min() + 1e-6)
    return sigma
