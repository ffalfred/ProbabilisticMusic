import numpy as np


def resolve_event_pitch(event_t: float, base_pitch: float, note_rels: list) -> float:
    """Return the effective pitch in semitones for an event at event_t.

    Checks glissando ranges first — if the event falls inside one, the pitch is
    linearly interpolated between from_pitch and to_pitch across the range.
    Falls back to the event's own `pitch` field (base_pitch) otherwise.
    """
    for nr in note_rels:
        if nr.get('type') == 'glissando':
            t0 = float(nr['from'])
            t1 = float(nr.get('to', t0))
            if t0 <= event_t <= t1 and t1 > t0:
                frac   = (event_t - t0) / (t1 - t0)
                from_p = float(nr.get('from_pitch', 0.0))
                to_p   = float(nr.get('to_pitch',   2.0))
                return from_p + frac * (to_p - from_p)
    return base_pitch


def apply_pitch_shift(clip: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """Pitch-shift a clip by the given number of semitones using librosa.

    No-op for shifts smaller than 0.05 semitones to avoid unnecessary processing.
    """
    if abs(semitones) < 0.05:
        return clip
    import librosa
    return librosa.effects.pitch_shift(clip.astype(np.float32), sr=sr, n_steps=semitones)
