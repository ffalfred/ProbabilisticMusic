import numpy as np


def apply_noterel_to_mix(mix: np.ndarray, sr: int, note_rels: list) -> np.ndarray:
    """Apply glissando pitch-slides and arpeggio roll effects to the full mix.
    Each note_rel may carry optional freq_from / freq_to (Hz) to restrict
    the effect to a frequency band; the rest of the spectrum passes through."""
    import librosa
    from src.fx import _band_split
    chunk_n = max(1, int(0.02 * sr))   # 20 ms chunks for glissando
    fi_n    = max(1, int(0.015 * sr))  # 15 ms fade-in for arpeggio segments
    result  = mix.copy()

    for nr in note_rels:
        t0 = float(nr.get('from', 0))
        t1 = float(nr.get('to', t0))
        i0 = int(t0 * sr)
        i1 = min(int(t1 * sr), len(result))
        if i1 <= i0:
            continue

        # Optional frequency targeting
        freq_from = nr.get('freq_from')
        freq_to   = nr.get('freq_to')
        need_split = (freq_from is not None) or (freq_to is not None)

        if need_split:
            seg_full = result[i0:i1].copy()
            seg, band_rest = _band_split(seg_full, sr, freq_from, freq_to)
        else:
            seg = result[i0:i1]  # direct view for in-place writes
            band_rest = None

        if nr.get('type') == 'glissando':
            from_p = float(nr.get('from_pitch', 0.0))
            to_p   = float(nr.get('to_pitch',   2.0))
            if abs(to_p - from_p) < 0.05:
                continue
            total = len(seg)
            seg_out = seg.copy()
            for ci in range(0, total, chunk_n):
                s = ci
                e = min(s + chunk_n, total)
                frac      = ci / max(total - 1, 1)
                semitones = from_p + frac * (to_p - from_p)
                if abs(semitones) < 0.05:
                    continue
                chunk = seg[s:e].astype(np.float32)
                pad   = max(0, 2048 - len(chunk))
                if pad:
                    chunk = np.pad(chunk, (0, pad))
                shifted      = librosa.effects.pitch_shift(chunk, sr=sr, n_steps=semitones)
                seg_out[s:e] = shifted[:e - s]
            seg = seg_out

        elif nr.get('type') == 'arpeggiate':
            total   = len(seg)
            n_steps = min(8, max(1, total // max(1, int(0.05 * sr))))
            seg_n   = total // n_steps
            for s_idx in range(n_steps):
                s0  = s_idx * seg_n
                s1  = min(s0 + seg_n, total)
                fi  = min(fi_n, s1 - s0)
                if fi > 1:
                    seg[s0:s0 + fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)

        # Recombine if band-split was used
        if band_rest is not None:
            n = min(len(band_rest), len(seg), i1 - i0)
            result[i0:i0 + n] = (band_rest[:n] + seg[:n]).astype(np.float32)

    return result


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
