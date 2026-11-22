import numpy as np
from src.dsp import as_frames
from src.stretch import pitch_shift


def _is_banded(nr: dict) -> bool:
    return nr.get('freq_from') is not None or nr.get('freq_to') is not None


def apply_noterel_to_mix(mix: np.ndarray, sr: int, note_rels: list) -> np.ndarray:
    """Apply glissando pitch-slides and arpeggio roll effects to the full mix.
    Each note_rel may carry optional freq_from / freq_to (Hz) to restrict
    the effect to a frequency band; the rest of the spectrum passes through.

    A glissando WITHOUT a band only re-pitches events (see resolve_event_pitch),
    so it is skipped here. A banded glissando slides that band of the whole mix
    instead, and resolve_event_pitch leaves events alone so they are not
    shifted twice."""
    from src.fx import _band_split
    fi_n    = max(1, int(0.015 * sr))  # 15 ms fade-in for arpeggio segments
    result  = as_frames(mix).copy()    # (frames, channels)

    for nr in note_rels:
        t0 = float(nr.get('from', 0))
        t1 = float(nr.get('to', t0))
        i0 = int(t0 * sr)
        i1 = min(int(t1 * sr), len(result))
        if i1 <= i0:
            continue
        if nr.get('type') == 'glissando' and not _is_banded(nr):
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
            # One continuous slide: Rubber Band follows a per-sample pitch curve.
            curve = np.linspace(from_p, to_p, len(seg))
            processed = pitch_shift(seg, sr, curve)
            # Crossfade with the original at the boundaries so the shifted band
            # joins the surrounding mix without a click.
            xf = min(max(1, int(0.010 * sr)), len(seg) // 4)
            seg_orig = seg.astype(np.float32).copy()
            if xf > 1:
                ramp = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
                processed[:xf]  = seg_orig[:xf]  * (1 - ramp) + processed[:xf]  * ramp
                processed[-xf:] = seg_orig[-xf:] * ramp[::-1] + processed[-xf:] * (1 - ramp[::-1])
            seg = processed

        elif nr.get('type') == 'arpeggiate':
            total   = len(seg)
            n_steps = min(8, max(1, total // max(1, int(0.05 * sr))))
            seg_n   = total // n_steps
            for s_idx in range(n_steps):
                s0  = s_idx * seg_n
                s1  = min(s0 + seg_n, total)
                fi  = min(fi_n, s1 - s0)
                if fi > 1:
                    seg[s0:s0 + fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]

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
    Band-limited glissandi are applied to the mix instead and are ignored here.
    """
    for nr in note_rels:
        if nr.get('type') == 'glissando' and not _is_banded(nr):
            t0 = float(nr['from'])
            t1 = float(nr.get('to', t0))
            if t0 <= event_t <= t1 and t1 > t0:
                frac   = (event_t - t0) / (t1 - t0)
                from_p = float(nr.get('from_pitch', 0.0))
                to_p   = float(nr.get('to_pitch',   2.0))
                return from_p + frac * (to_p - from_p)
    return base_pitch


def apply_pitch_shift(clip: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """Pitch-shift a (frames, channels) clip by the given number of semitones
    (Rubber Band, channels together; see src/stretch.py).

    No-op for shifts smaller than 0.05 semitones to avoid unnecessary processing.
    """
    if abs(semitones) < 0.05:
        return clip
    return pitch_shift(clip, sr, semitones)
