"""
Pre-rendering pass — compute drama, salience, and future_pull for every
dynamic marking in the score.

drama(t)        — how structurally significant is this marking (looks back)?
salience(t)     — same formula, used when t is a *future* event (looks forward)
future_pull(t)  — decaying weighted sum of upcoming marking values

Both use the same formula so that "importance" is consistently defined.
"""

import math
import numpy as np


# Dynamic ladder rank
RANK = {'ppp': 0, 'pp': 1, 'p': 2, 'mp': 3, 'mf': 4, 'f': 5, 'ff': 6, 'fff': 7}
# Structurally emphatic markings (binary contribution)
STRUCTURAL = {'sfz', 'fp', 'subito_p', 'subito_f'}
# Gradual markings — we encode them at their start rank for observation purposes
GRADUAL    = {'cresc', 'crescendo', 'decresc', 'decrescendo'}


def _rank(marking: str) -> float:
    """Return ordinal rank of a dynamic marking; structural → mean rank 3.5."""
    m = marking.lower()
    if m in RANK:
        return float(RANK[m])
    if m in STRUCTURAL:
        return 3.5   # treated as mid-range for contrast/distance
    if m in GRADUAL:
        return 3.5
    return 3.5       # unknown → mid-range


def _is_structural(marking: str) -> float:
    return 1.0 if marking.lower() in STRUCTURAL else 0.0


def _compute_importance(i: int, markings: list, boundaries: set,
                        weights: dict, W: int = 3) -> float:
    """
    Compute importance score for markings[i].
    Used for both drama (backward look) and salience (forward look).

    weights keys: 'distance', 'structural', 'contrast', 'boundary'
    """
    n = len(markings)
    m = markings[i]
    r = _rank(m)

    # Component 1 — dynamic distance from previous marking
    prev_r = _rank(markings[i - 1]) if i > 0 else r
    distance = abs(r - prev_r) / 7.0

    # Component 2 — structural marking
    structural = _is_structural(m)

    # Component 3 — local contrast: |r - local_mean| / 7
    lo = max(0, i - W)
    hi = min(n, i + W + 1)
    local_mean = sum(_rank(markings[j]) for j in range(lo, hi)) / (hi - lo)
    contrast = abs(r - local_mean) / 7.0

    # Component 4 — phrase boundary
    boundary = 1.0 if i in boundaries else 0.0

    w = weights
    return (w['distance']   * distance +
            w['structural'] * structural +
            w['contrast']   * contrast +
            w['boundary']   * boundary)


def compute_drama(markings: list,
                  boundaries: set,
                  weights: dict) -> list:
    """
    Compute drama score for each marking.

    Parameters
    ----------
    markings   : list of marking strings, time-sorted
    boundaries : set of indices that are phrase-boundary events
    weights    : dict with keys 'distance', 'structural', 'contrast', 'boundary'

    Returns
    -------
    list of floats, one per marking
    """
    return [_compute_importance(i, markings, boundaries, weights)
            for i in range(len(markings))]


def compute_future_pull(markings: list,
                        drama_vals: list,
                        lambda_: float,
                        K: int = 10) -> list:
    """
    Compute future_pull for each marking.

    future_pull[i] = Σ_{k=1}^{K}  λᵏ · salience(i+k) · enc(m(i+k))

    salience == drama (same formula, different direction).

    Parameters
    ----------
    markings   : list of marking strings, time-sorted
    drama_vals : precomputed drama/salience for each index
    lambda_    : familiarity decay ∈ (0, 1)
    K          : look-ahead window

    Returns
    -------
    list of floats (scalar pull per marking, in ℝ)
    """
    n = len(markings)
    pulls = []
    for i in range(n):
        pull = 0.0
        for k in range(1, K + 1):
            j = i + k
            if j >= n:
                break
            sal = drama_vals[j]           # salience = drama at j
            enc = _rank(markings[j]) / 7.0  # normalised to [0,1]
            pull += (lambda_ ** k) * sal * enc
        pulls.append(pull)
    return pulls
