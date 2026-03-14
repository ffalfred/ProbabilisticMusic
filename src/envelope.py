import numpy as np

DYNAMIC_LEVELS = {
    'ppp': 0.10, 'pp': 0.20, 'p': 0.35, 'mp': 0.50,
    'mf':  0.65, 'f':  0.80, 'ff': 0.90, 'fff': 1.00,
}

def build_dynamics_envelope(n_samples: int, sr: int, dynamics: list) -> np.ndarray:
    """
    Build amplitude envelope from dynamics markings.

    Point markings  — { t: 4.0, mark: mf }
      Define the amplitude level at a moment in time; holds until the next point.

    Range markings  — { from: 2.0, to: 5.0, mark: crescendo }
      Linearly interpolate between the surrounding point levels.
      mark: crescendo | decrescendo
    """
    if not dynamics:
        return np.ones(n_samples, dtype=np.float32)

    env = np.ones(n_samples, dtype=np.float32)

    points = sorted(
        [(d['t'], DYNAMIC_LEVELS[d['mark']]) for d in dynamics if 't' in d],
        key=lambda p: p[0]
    )
    ranges = [d for d in dynamics if 'from' in d]

    if not points:
        return env

    # fill step-wise from point markings
    first_t, first_v = points[0]
    env[:int(first_t * sr)] = first_v

    for i, (t, v) in enumerate(points):
        i0 = int(t * sr)
        i1 = int(points[i + 1][0] * sr) if i + 1 < len(points) else n_samples
        env[i0:i1] = v

    # overlay crescendo / decrescendo ranges as linear interpolations
    for rng in ranges:
        i0 = min(int(rng['from'] * sr), n_samples - 1)
        i1 = min(int(rng['to']   * sr), n_samples)
        if i0 >= i1:
            continue
        env[i0:i1] = np.linspace(env[i0], env[min(i1, n_samples - 1)],
                                  i1 - i0, dtype=np.float32)

    return env


def apply_fade(clip: np.ndarray, sr: int, ms: float = 10.0) -> np.ndarray:
    fade = min(int(ms * sr / 1000), len(clip) // 4)
    clip[:fade]  *= np.linspace(0, 1, fade, dtype=np.float32)
    clip[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return clip
