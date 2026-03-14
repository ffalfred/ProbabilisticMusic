import statistics


OUTPUT_PARAMS = ['gain_db', 'brightness', 'timing_offset_ms', 'attack_shape', 'reverb_wet']


def infer_phrase_boundaries(events: list) -> list:
    """Return list of times where a new phrase begins (gap > 3× median inter-event gap)."""
    if len(events) < 2:
        return []
    times = sorted(e['t'] for e in events)
    gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    threshold = 3 * statistics.median(gaps)
    return [times[i + 1] for i, g in enumerate(gaps) if g > threshold]


def compute_context(events: list, score: dict, t: float, total_duration: float,
                    phrase_boundaries: list) -> dict:
    """
    Compute context vector for a given time t.

    Returns:
        tempo_direction:  -1 (accel) / 0 (stable) / +1 (decel)
        phrase_position:  0.0 (phrase start) to 1.0 (phrase end)
        piece_position:   0.0 to 1.0
        event_density:    events per second in ±5s window
    """
    tempo_direction = _tempo_direction(score.get('tempo', []), t)
    phrase_position = _phrase_position(t, phrase_boundaries, total_duration)
    piece_position  = t / total_duration if total_duration > 0 else 0.0
    event_density   = _event_density(events, t, window=5.0)

    return {
        'tempo_direction': tempo_direction,
        'phrase_position': phrase_position,
        'piece_position':  piece_position,
        'event_density':   event_density,
    }


def _tempo_direction(tempo_ranges: list, t: float) -> int:
    """Return -1 if accelerating, +1 if decelerating, 0 if stable at time t."""
    for rng in tempo_ranges:
        t0, t1 = rng.get('from', 0), rng.get('to', 0)
        if t0 <= t <= t1:
            factor = rng.get('factor', 1.0)
            if factor > 1.05:
                return -1   # factor > 1 compresses time → accelerando
            if factor < 0.95:
                return 1    # factor < 1 expands time → ritardando
    return 0


def _phrase_position(t: float, phrase_boundaries: list, total_duration: float) -> float:
    """Return fraction through the current phrase (0.0 = start, 1.0 = end)."""
    boundaries = sorted([0.0] + phrase_boundaries + [total_duration])
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        if start <= t <= end:
            span = end - start
            return (t - start) / span if span > 0 else 0.0
    return 1.0


def _event_density(events: list, t: float, window: float = 5.0) -> float:
    """Return events per second in a ±window second window around t."""
    count = sum(1 for e in events if abs(e['t'] - t) <= window)
    return count / (2 * window)
