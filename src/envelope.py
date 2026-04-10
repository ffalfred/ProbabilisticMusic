import numpy as np

DYNAMIC_LEVELS = {
    'ppp': 0.05, 'pp': 0.10, 'p': 0.20, 'mp': 0.45,
    'mf':  0.65, 'f':  0.85, 'ff': 1.00, 'fff': 1.20,
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


def _is_crescendo(mark: str) -> bool:
    m = mark.lower().strip().rstrip('.')
    return m in ('crescendo', 'cresc', 'cr')

def _is_decrescendo(mark: str) -> bool:
    m = mark.lower().strip().rstrip('.')
    return m in ('decrescendo', 'decresc', 'diminuendo', 'dim', 'decr')


def build_dynamics_envelope(n_samples: int, sr: int, dynamics: list) -> np.ndarray:
    """
    Build amplitude envelope from dynamics markings.

    Point markings  — { t: 4.0, mark: mf }
      Define the amplitude level at a moment in time.

    Range markings  — { from: 2.0, to: 5.0, mark: crescendo }
      Linearly interpolate across the span.
      After the range ends, the level HOLDS until the next marking.
    """
    if not dynamics:
        return np.ones(n_samples, dtype=np.float32)

    # Filter out muted dynamics
    active = [d for d in dynamics if not d.get('muted')]
    if not active:
        return np.ones(n_samples, dtype=np.float32)

    # Build a single sorted event list from all markings
    events = []  # [(time_samples, type, ...data)]

    # Point markings
    for d in active:
        if 't' not in d:
            continue
        mark = d.get('mark') or d.get('marking') or ''
        level = DYNAMIC_LEVELS.get(mark)
        if level is None:
            continue  # skip invalid/unknown point marks
        events.append((int(d['t'] * sr), 'set', level))

    # Range markings (crescendo / decrescendo)
    # Sort point marks by time for next-point lookups
    sorted_points = sorted(
        [(d['t'], DYNAMIC_LEVELS.get(d.get('mark') or d.get('marking') or '', None))
         for d in active if 't' in d and DYNAMIC_LEVELS.get(d.get('mark') or d.get('marking') or '')],
        key=lambda p: p[0]
    )

    for d in active:
        if 'from' not in d:
            continue
        mark = d.get('mark') or d.get('marking') or ''
        t_from = int(d['from'] * sr)
        t_to   = min(int(d['to'] * sr), n_samples)
        if t_to <= t_from:
            continue

        # Determine the ramp target
        next_pts = [v for t, v in sorted_points if t >= d['to'] and v is not None]

        if _is_crescendo(mark):
            if next_pts:
                target = next_pts[0]
            else:
                target = None  # resolved at render time from current level
            events.append((t_from, 'ramp', t_to, target, 'up'))
        elif _is_decrescendo(mark):
            if next_pts:
                target = next_pts[0]
            else:
                target = None
            events.append((t_from, 'ramp', t_to, target, 'down'))

    # Sort all events by time
    events.sort(key=lambda e: e[0])

    # Build envelope by walking through events chronologically
    env = np.ones(n_samples, dtype=np.float32)
    current_level = 0.65  # default: mf
    cursor = 0  # current sample position

    # If there are point marks, start at the first one's level
    if sorted_points:
        current_level = sorted_points[0][1]

    for ev in events:
        t = ev[0]
        if t < 0:
            t = 0
        if t > n_samples:
            break

        # Fill from cursor to this event with current level
        if t > cursor:
            env[cursor:t] = current_level

        if ev[1] == 'set':
            # Point marking — smooth transition to new level
            new_level = ev[2]
            gap_sec = (t - cursor) / sr if cursor < t else 0.5
            trans = min(_transition_samples(gap_sec, sr), max(1, (n_samples - t) // 2))
            if trans > 1 and t + trans <= n_samples:
                env[t:t + trans] = np.linspace(current_level, new_level, trans, dtype=np.float32)
                cursor = t + trans
            else:
                cursor = t
            current_level = new_level

        elif ev[1] == 'ramp':
            # Range marking (crescendo / decrescendo)
            t_to   = ev[2]
            target = ev[3]
            direction = ev[4]
            start_v = current_level

            if target is not None:
                end_v = target
            elif direction == 'up':
                end_v = min(start_v * 2.5, 1.2)
            else:
                end_v = max(start_v * 0.4, 0.05)

            ramp_len = min(t_to, n_samples) - t
            if ramp_len > 0:
                env[t:t + ramp_len] = np.linspace(start_v, end_v, ramp_len, dtype=np.float32)
            current_level = end_v
            cursor = min(t_to, n_samples)

    # Fill remainder after last event
    if cursor < n_samples:
        env[cursor:] = current_level

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
                        release: float = 0.3) -> np.ndarray:
    duck  = 10 ** (amount_db / 20.0)
    atk_s = max(1, int(attack  * sr))
    rel_s = max(1, int(release * sr))
    env   = np.ones(n_samples, dtype=np.float32)
    for ev in events:
        if not trigger_fn(ev):
            continue
        i0 = int(float(ev['t']) * sr)
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
                        mode: str = "sqrt",
                        silence_start: float = 0.0) -> np.ndarray:
    density = np.ones(n_samples, dtype=np.float32)
    for ev in events:
        spec   = samples_spec.get(ev.get('sample', ''), {})
        t_real = float(ev['t']) + silence_start
        i0     = int(t_real * sr)
        dur    = (spec.get('to', 0) - spec.get('from', 0)) / max(ev.get('speed', 1.0), 0.01)
        i1     = min(i0 + max(1, int(dur * sr)), n_samples)
        if i0 < n_samples:
            density[i0:i1] += 1.0
    if mode == "sqrt":
        return np.where(density > 1, 1.0 / np.sqrt(density), 1.0).astype(np.float32)
    else:
        return (1.0 / density).astype(np.float32)
