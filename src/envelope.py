import numpy as np

DYNAMIC_LEVELS = {
    'ppp': 0.10, 'pp': 0.20, 'p': 0.35, 'mp': 0.50,
    'mf':  0.65, 'f':  0.80, 'ff': 0.90, 'fff': 1.00,
}

# Smooth transition time between adjacent dynamic marks, based on gap duration.
# Prevents jarring volume jumps.
def _transition_samples(gap_sec: float, sr: int) -> int:
    if gap_sec < 0.5:
        ms = 12
    elif gap_sec < 2.0:
        ms = 35
    elif gap_sec < 5.0:
        ms = 100
    elif gap_sec < 10.0:
        ms = 200
    else:
        ms = 500
    return int(ms * sr / 1000)


def build_dynamics_envelope(n_samples: int, sr: int, dynamics: list) -> np.ndarray:
    """
    Build amplitude envelope from dynamics markings.

    Point markings  — { t: 4.0, mark: mf }
      Define the amplitude level at a moment in time.
      Transitions between adjacent marks are smoothed to avoid jarring jumps.

    Range markings  — { from: 2.0, to: 5.0, mark: crescendo }
      Linearly interpolate across the span.
      Works even without surrounding point marks.
    """
    if not dynamics:
        return np.ones(n_samples, dtype=np.float32)

    env = np.ones(n_samples, dtype=np.float32)

    points = sorted(
        [(d['t'], DYNAMIC_LEVELS[d['mark']]) for d in dynamics if 't' in d],
        key=lambda p: p[0]
    )
    ranges = [d for d in dynamics if 'from' in d]

    # ── Step-wise fill from point marks (with smooth cross-fades at transitions) ──
    if points:
        first_t, first_v = points[0]
        # Everything before the first mark holds at the first mark's level
        env[:int(first_t * sr)] = first_v

        for i, (t, v) in enumerate(points):
            i0 = int(t * sr)
            i1 = int(points[i + 1][0] * sr) if i + 1 < len(points) else n_samples
            env[i0:i1] = v

            # Smooth transition from previous level into this level
            if i > 0:
                prev_v = points[i - 1][1]
                gap    = t - points[i - 1][0]
                trans  = min(_transition_samples(gap, sr), (i1 - i0) // 2)
                if trans > 1:
                    env[i0:i0 + trans] = np.linspace(prev_v, v, trans, dtype=np.float32)

    # ── Overlay crescendo / decrescendo ranges ─────────────────────────────────
    for rng in ranges:
        i0 = min(int(rng['from'] * sr), n_samples - 1)
        i1 = min(int(rng['to']   * sr), n_samples)
        if i0 >= i1:
            continue

        start_v = float(env[i0])
        end_v   = float(env[min(i1, n_samples - 1)])

        # When there are no surrounding point marks, use sensible defaults
        if not points:
            if rng['mark'] == 'crescendo':
                start_v, end_v = DYNAMIC_LEVELS['p'],  DYNAMIC_LEVELS['f']
            else:
                start_v, end_v = DYNAMIC_LEVELS['f'],  DYNAMIC_LEVELS['p']

        env[i0:i1] = np.linspace(start_v, end_v, i1 - i0, dtype=np.float32)

    return env


def apply_fade(clip: np.ndarray, sr: int,
               fade_in_pct: float = 0.0, fade_out_pct: float = 0.0,
               ms: float = 10.0) -> np.ndarray:
    """Apply fade in/out to a clip.

    If fade_in_pct / fade_out_pct > 0, use them as a fraction of clip length.
    Otherwise fall back to a fixed ms fade.
    """
    n = len(clip)
    fi = int(n * fade_in_pct)  if fade_in_pct  > 0 else int(ms * sr / 1000)
    fo = int(n * fade_out_pct) if fade_out_pct > 0 else int(ms * sr / 1000)
    fi = min(fi, n // 2)
    fo = min(fo, n // 2)
    if fi > 0:
        clip[:fi]  *= np.linspace(0, 1, fi,  dtype=np.float32)
    if fo > 0:
        clip[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    return clip


def build_duck_envelope(n_samples: int, sr: int, events: list, trigger_fn,
                        amount_db: float = -6.0, attack: float = 0.01,
                        release: float = 0.3, tempo_ranges: list = None) -> np.ndarray:
    from src.mixer import _warp_time
    duck  = 10 ** (amount_db / 20.0)
    atk_s = max(1, int(attack  * sr))
    rel_s = max(1, int(release * sr))
    env   = np.ones(n_samples, dtype=np.float32)
    for ev in events:
        if not trigger_fn(ev):
            continue
        i0 = int(_warp_time(ev['t'], tempo_ranges or []) * sr)
        if i0 >= n_samples:
            continue
        a1 = min(i0 + atk_s, n_samples)
        env[i0:a1] = np.minimum(env[i0:a1],
                                np.linspace(1.0, duck, a1 - i0, dtype=np.float32))
        r1 = min(a1 + rel_s, n_samples)
        env[a1:r1] = np.minimum(env[a1:r1],
                                np.linspace(duck, 1.0, r1 - a1, dtype=np.float32))
    return env


def build_phrase_envelope(n_samples: int, sr: int, phrases: list) -> np.ndarray:
    """Multiplicative envelope: per-phrase gain + fade-in/out."""
    env = np.ones(n_samples, dtype=np.float32)
    for ph in phrases:
        gain_db = ph.get('gain_db', 0.0)
        fi_pct  = ph.get('fade_in',  0.0)
        fo_pct  = ph.get('fade_out', 0.0)
        if gain_db == 0.0 and fi_pct == 0.0 and fo_pct == 0.0:
            continue
        i0 = int(ph['from'] * sr)
        i1 = min(int(ph['to'] * sr), n_samples)
        if i0 >= i1:
            continue
        n   = i1 - i0
        seg = np.full(n, 10 ** (gain_db / 20.0), dtype=np.float32)
        fi  = min(int(n * fi_pct), n // 2)
        fo  = min(int(n * fo_pct), n // 2)
        if fi > 0: seg[:fi]  *= np.linspace(0, 1, fi,  dtype=np.float32)
        if fo > 0: seg[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
        env[i0:i1] *= seg
    return env


def build_density_scale(n_samples: int, sr: int, events: list, samples_spec: dict,
                        tempo_ranges: list = None, mode: str = "sqrt",
                        silence_start: float = 0.0) -> np.ndarray:
    from src.mixer import _warp_time
    density = np.ones(n_samples, dtype=np.float32)
    for ev in events:
        spec   = samples_spec.get(ev.get('sample', ''), {})
        t_real = _warp_time(ev['t'], tempo_ranges or []) + silence_start
        i0     = int(t_real * sr)
        dur    = (spec.get('to', 0) - spec.get('from', 0)) / max(ev.get('speed', 1.0), 0.01)
        i1     = min(i0 + max(1, int(dur * sr)), n_samples)
        if i0 < n_samples:
            density[i0:i1] += 1.0
    if mode == "sqrt":
        return np.where(density > 1, 1.0 / np.sqrt(density), 1.0).astype(np.float32)
    else:
        return (1.0 / density).astype(np.float32)
