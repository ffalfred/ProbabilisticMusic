"""
Observation model — window encoding and H / R lookup.

The observation at step t is the last N score markings concatenated:
  y(t) = [enc(m(t)), enc(m(t-1)), ..., enc(m(t-N+1))]  ∈ ℝ^N

H maps from the AR(2) augmented state ℝ^(2d) to observation space ℝ^N.
R is the N×N diagonal observation noise covariance.

Both are looked up by window-pattern key from transition_table.yaml.
If the exact pattern is absent the 'default' entry is used.
"""

import numpy as np
from src.drama import RANK, STRUCTURAL

from src.character import D   # number of expressive state dimensions


def encode_marking(m: str) -> float:
    """
    Return a scalar in [0, 1] for any dynamic marking.
      - Regular dynamics: ordinal rank / 7
      - Structural markings (sfz, fp, subito_*): 1.0 (emphatic)
      - Gradual (cresc/decresc): 0.5 (neutral direction signal)
      - Unknown: 0.5
    """
    lo = m.lower()
    if lo in RANK:
        return RANK[lo] / 7.0
    if lo in STRUCTURAL:
        return 1.0
    return 0.5


def build_window_obs(markings: list, i: int, N: int) -> np.ndarray:
    """
    Build observation vector y(t) for step i using a window of N markings.

    markings : time-sorted list of marking strings
    i        : current index
    N        : window size

    Returns shape (N,) array — most recent marking first.
    For positions before the start, pad with enc('mf') = 0.5.
    """
    pad = encode_marking('mf')
    y = np.full(N, pad)
    for k in range(N):
        j = i - k
        if j >= 0:
            y[k] = encode_marking(markings[j])
    return y


def window_key(markings: list, i: int, N: int) -> str:
    """
    Build a human-readable key for the current window pattern, e.g. 'f_mp_p'.
    Used to look up H/R in the transition table.
    """
    parts = []
    for k in range(N):
        j = i - k
        parts.append(markings[j].lower() if j >= 0 else 'none')
    return '_'.join(parts)


def _diag_R(r_vec: list, N: int) -> np.ndarray:
    """Build N×N diagonal R from a length-N list."""
    r = np.array(r_vec, dtype=float)
    if len(r) < N:
        r = np.pad(r, (0, N - len(r)), constant_values=r[-1])
    return np.diag(r[:N])


def _build_H(h_row: list, N: int, d: int, augmented_d: int) -> np.ndarray:
    """
    Build H matrix (N × augmented_d) from h_row.

    h_row can be either:
      - A flat list of length N*d
      - A list of N sub-lists each of length d (as parsed from YAML)

    The first d columns of H address x(t); columns d..2d address x(t-1).
    We only use the x(t) slot — H[:, d:] = 0.
    """
    # Flatten list-of-lists to a 1-D array
    arr = np.array(h_row, dtype=float).flatten()
    H = np.zeros((N, augmented_d))
    for obs_dim in range(N):
        start = obs_dim * d
        end   = start + d
        if end <= len(arr):
            H[obs_dim, :d] = arr[start:end]
        else:
            # Fallback: simple scalar projection on gain_db (dim 0)
            H[obs_dim, 0] = 1.0 / 7.0
    return H


def lookup_HR(markings: list, i: int, N: int,
              windows_table: dict, augmented_d: int) -> tuple:
    """
    Lookup H and R for the current window pattern.

    Returns
    -------
    H : np.ndarray, shape (N, augmented_d)
    R : np.ndarray, shape (N, N)
    """
    key = window_key(markings, i, N)
    # Try exact key first, then progressively replace trailing parts with 'any'
    # (e.g. 'sfz_f_mp' → 'sfz_f_any' → 'sfz_any_any'), then 'default'
    entry = None
    parts = key.split('_')
    for suffix_len in range(len(parts) + 1):
        candidate = '_'.join(parts[:len(parts) - suffix_len] + ['any'] * suffix_len)
        if candidate in windows_table:
            entry = windows_table[candidate]
            break
    if entry is None:
        entry = windows_table.get('default', {})

    # --- R ---
    r_vec = entry.get('R', [1.0] * N)
    R = _diag_R(r_vec, N)

    # --- H ---
    h_row = entry.get('H', None)
    if h_row is not None:
        H = _build_H(h_row, N, D, augmented_d)
    else:
        # Default H: each obs dimension projects onto gain_db scaled by its slot weight
        slot_weights = [1.0, 0.5, 0.25]   # most-recent slot has strongest weight
        H = np.zeros((N, augmented_d))
        for obs_dim in range(N):
            w = slot_weights[obs_dim] if obs_dim < len(slot_weights) else 0.1
            H[obs_dim, 0] = w / 7.0   # gain_db only

    return H, R
