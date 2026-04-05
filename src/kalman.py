"""
Kalman filter — core predict/update steps.

State space:
  x(t) ∈ ℝ^d  — expressive state (d=12 for the 12 output params)

AR(2) augmented state:
  X(t) = [x(t), x(t-1)]ᵀ ∈ ℝ^(2d)

Transition:
  X(t) = F · X(t-1) + w(t),   w(t) ~ N(0, Q_aug)

where
  F = [[A1, A2],   Q_aug = [[Q, 0],
       [I,  0 ]]            [0, 0]]

Observation:
  y(t) = H · x(t) + v(t),   v(t) ~ N(0, R)
"""

import numpy as np


def build_Sigma0(Q_base_diag: np.ndarray, scale: float = 4.0) -> np.ndarray:
    """
    Build the initial covariance Σ₀ for the augmented AR(2) state (2d×2d).

    Seeds cross-dimension correlations from the plan:
      gain_db ↔ brightness:      0.4
      gain_db ↔ pitch_dev_cents: 0.3
      gain_db ↔ overdrive_drive: 0.4
      gain_db ↔ dynamic_center:  0.6
      filter_cutoff ↔ brightness: 0.5
      reverb_wet ↔ stereo_width:  0.4
      timing_offset_ms ↔ pitch_dev_cents: 0.2
    """
    d = len(Q_base_diag)
    std = np.sqrt(Q_base_diag * scale)
    Sig = np.diag(Q_base_diag * scale)

    # Seed correlations (only if dimensions exist)
    _CORRS = [
        (0, 1, 0.4),    # gain_db ↔ brightness
        (0, 10, 0.3),   # gain_db ↔ pitch_dev_cents
        (0, 9, 0.4),    # gain_db ↔ overdrive_drive
        (0, 11, 0.6),   # gain_db ↔ dynamic_center
        (6, 1, 0.5),    # filter_cutoff ↔ brightness
        (5, 8, 0.4),    # reverb_wet ↔ stereo_width
        (2, 10, 0.2),   # timing_offset_ms ↔ pitch_dev_cents
    ]
    for i, j, rho in _CORRS:
        if i < d and j < d:
            cov = rho * std[i] * std[j]
            Sig[i, j] = cov
            Sig[j, i] = cov

    # Build augmented 2d×2d: [[Sig, 0], [0, Sig]]
    Z = np.zeros((d, d))
    return np.block([[Sig, Z], [Z, Sig]])


def build_F(A1: np.ndarray, A2: np.ndarray) -> np.ndarray:
    """Build 2d×2d AR(2) transition matrix from d×d coefficient matrices."""
    d = A1.shape[0]
    I = np.eye(d)
    Z = np.zeros((d, d))
    return np.block([[A1, A2],
                     [I,  Z]])


def build_Q_aug(Q: np.ndarray) -> np.ndarray:
    """Build 2d×2d augmented process noise — noise only on current state slot."""
    d = Q.shape[0]
    Z = np.zeros((d, d))
    return np.block([[Q, Z],
                     [Z, Z]])


def predict(mu: np.ndarray,
            Sigma: np.ndarray,
            F: np.ndarray,
            Q_aug: np.ndarray,
            future_pull: np.ndarray = None,
            xi: float = 0.0) -> tuple:
    """
    Kalman predict step.

    Parameters
    ----------
    mu      : mean of current belief, shape (2d,)
    Sigma   : covariance of current belief, shape (2d, 2d)
    F       : AR(2) transition matrix, shape (2d, 2d)
    Q_aug   : augmented process noise covariance, shape (2d, 2d)
    future_pull : optional bias vector (d,) — pulled into first d dims
    xi      : scaling for future_pull

    Returns
    -------
    mu_bar, Sigma_bar  — predicted belief
    """
    mu_bar = F @ mu
    if future_pull is not None and xi > 0:
        d = future_pull.shape[0]
        bias = np.zeros_like(mu_bar)
        bias[:d] = xi * future_pull
        mu_bar = mu_bar + bias
    Sigma_bar = F @ Sigma @ F.T + Q_aug
    return mu_bar, Sigma_bar


def update(mu_bar: np.ndarray,
           Sigma_bar: np.ndarray,
           y: np.ndarray,
           H: np.ndarray,
           R: np.ndarray) -> tuple:
    """
    Kalman update step.

    Parameters
    ----------
    mu_bar    : predicted mean, shape (2d,)
    Sigma_bar : predicted covariance, shape (2d, 2d)
    y         : observation vector, shape (m,)
    H         : observation matrix, shape (m, 2d)
    R         : observation noise covariance, shape (m, m)

    Returns
    -------
    mu, Sigma, nu  — updated belief + innovation
    """
    nu = y - H @ mu_bar                                        # innovation
    S  = H @ Sigma_bar @ H.T + R                               # innovation covariance
    K  = np.linalg.solve(S.T, (Sigma_bar @ H.T).T).T          # Kalman gain
    mu    = mu_bar + K @ nu
    Sigma = (np.eye(len(mu_bar)) - K @ H) @ Sigma_bar
    # Symmetrise to avoid drift from floating-point asymmetry
    Sigma = 0.5 * (Sigma + Sigma.T)
    return mu, Sigma, nu, K
