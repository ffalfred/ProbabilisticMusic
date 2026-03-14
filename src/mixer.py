import numpy as np
import librosa
from src.envelope import apply_fade
from src.fx       import apply_fx


def _warp_time(t_score: float, tempo_ranges: list) -> float:
    """
    Map a score time to real time via tempo ranges.
    factor > 1  =  accelerando (time compressed, events happen sooner)
    factor < 1  =  ritardando  (time expanded, events happen later)
    """
    offset = 0.0
    cursor = 0.0
    for rng in sorted(tempo_ranges, key=lambda r: r['from']):
        t0, t1   = rng['from'], rng['to']
        factor   = rng.get('factor', 1.0)
        if t_score < t0:
            return offset + (t_score - cursor)
        offset += t0 - cursor
        cursor  = t0
        if t_score <= t1:
            return offset + (t_score - t0) / factor
        offset += (t1 - t0) / factor
        cursor  = t1
    return offset + (t_score - cursor)


def _apply_speed(clip: np.ndarray, speed: float, sr: int) -> np.ndarray:
    if abs(speed - 1.0) < 1e-3:
        return clip
    return librosa.resample(
        clip, orig_sr=int(sr * speed), target_sr=sr
    ).astype(np.float32)


def mix_events(events: list, bank: dict, sr: int, score: dict = None, base: np.ndarray = None) -> np.ndarray:
    silence_start = (score or {}).get('silence_start', 0.0)
    tempo_ranges  = (score or {}).get('tempo', [])

    mix = base.copy() if base is not None else np.zeros(int((max(e['t'] for e in events) + 30.0) * sr), dtype=np.float32)

    # --- base fx (applied before events are layered) ---
    base_fx = (score or {}).get('base_fx', [])
    if base_fx and base is not None:
        mix = apply_fx(mix, sr, base_fx)

    # --- ranged fx (applied to specific segments of the base) ---
    for fr in sorted((score or {}).get('fx_ranges', []), key=lambda r: r['from']):
        i0 = int(fr['from'] * sr)
        i1 = min(int(fr['to'] * sr), len(mix))
        if i0 >= len(mix) or i0 >= i1:
            continue
        segment  = mix[i0:i1].copy()
        processed = apply_fx(segment, sr, fr['fx'])
        mix[i0:i1] = 0.0
        out_end = i0 + len(processed)
        if out_end > len(mix):
            mix = np.pad(mix, (0, out_end - len(mix)))
        mix[i0:out_end] += processed

    for event in events:
        base_clip = bank[event['sample']].copy()

        # --- speed / layered transpositions ---
        speeds = event.get('speeds')
        if speeds:
            layers  = [_apply_speed(base_clip.copy(), s, sr) for s in speeds]
            max_len = max(len(l) for l in layers)
            clip    = np.zeros(max_len, dtype=np.float32)
            for l in layers:
                clip[:len(l)] += l
        else:
            clip = _apply_speed(base_clip, event.get('speed', 1.0), sr)

        # --- reverse ---
        if event.get('reverse', False):
            clip = clip[::-1].copy()

        # --- loop ---
        loop = event.get('loop', 0)
        if loop > 0:
            clip = np.tile(clip, loop + 1)

        # --- fade edges ---
        clip = apply_fade(clip, sr)

        # --- gain ---
        gain_db = event.get('gain_db', -6.0)
        clip   *= 10 ** (gain_db / 20.0)

        # --- fx ---
        fx_list = event.get('fx', [])
        if fx_list:
            clip = apply_fx(clip, sr, fx_list)

        # --- place on timeline (tempo-warped + silence offset) ---
        t_real = _warp_time(event['t'], tempo_ranges) + silence_start
        i0 = int(t_real * sr)
        i1 = i0 + len(clip)
        if i1 > len(mix):
            mix = np.pad(mix, (0, i1 - len(mix)))
        mix[i0:i1] += clip

    return mix


def normalise(mix: np.ndarray, headroom: float = 0.9) -> np.ndarray:
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * headroom
    return mix
