"""Articulations: staccato, accent, legato, fermata.

Each mark has a target:
- `event` (default) — it shapes the events it marks, before they are mixed.
  A point mark (`t`) marks the event starting nearest to t (within 0.5 s);
  a range mark (`from`/`to`) marks every event starting inside the range.
  The source audio and other events are untouched.
- `mix` — it shapes everything sounding at that time (source + events).
  Over a range, staccato / accent / legato act at the attacks detected in
  the mix, or on a regular grid every `every_s` seconds if that is set.

What each mark does:
- staccato: keep `keep_s` from the start (default 0.15 s), then a quick fade
  to silence. On the mix, a point mark cuts everything for `silence_s` after
  `keep_s`; a range chops each attack to `keep_s` until the next one.
- accent: the first 50 ms are louder by `boost_db` (default 6), easing back.
- legato: an event rings on until the next event starts (when its sample
  runs out, its last moment is held), then fades as the next one enters;
  with no next event it just ends on a long fade. On the mix, at each attack
  the sound before it rings on across it while the new sound eases in.
- fermata: an event's last moment is held for `hold_s` (default 2 s), then
  fades; nothing else moves. On the mix, the whole piece waits: the sound at
  `t` is held for `hold_s` and inserted into the timeline, then everything
  resumes. The tempo map gets a flat step there, so the score cursor stops.

Any mark can be limited to a frequency band (`freq_from` / `freq_to`).
"""
import numpy as np

from src.dsp import pad_frames
from src.spectral import hold_moment, legato_bridges

MATCH_WINDOW = 0.5        # s: a point mark finds the nearest event this close
ACCENT_S     = 0.05       # s: length of the accent's boost
STACCATO_FADE = 0.01      # s: the staccato's cut
LEGATO_OVERLAP = 0.1      # s: a legato event fades out this long after the next enters
LEGATO_END_FADE = 0.5     # s: legato with no next event: long fade at the end
MIX_BRIDGE   = 0.2        # s: whole-mix legato bridge length
FERMATA_XF   = 0.05       # s: whole-mix fermata: crossfade back into the music


def target(art: dict) -> str:
    return 'mix' if art.get('target') == 'mix' else 'event'


def _active(art: dict) -> bool:
    return not art.get('muted') and art.get('type') in ('staccato', 'accent', 'legato', 'fermata')


def _is_range(art: dict) -> bool:
    return art.get('from') is not None and art.get('to') is not None


def _band(seg, sr, art):
    """(part to shape, rest) — rest is None when the mark has no band."""
    if art.get('freq_from') is None and art.get('freq_to') is None:
        return seg, None
    from src.fx import _band_split
    return _band_split(seg, sr, art.get('freq_from'), art.get('freq_to'))


def _join(part, rest):
    if rest is None:
        return part
    n = max(len(part), len(rest))
    return (pad_frames(part, n) + pad_frames(rest, n)).astype(np.float32)


def _fade_out(x, n):
    n = min(int(n), len(x))
    if n > 1:
        x[-n:] *= np.cos(np.linspace(0, np.pi / 2, n)).astype(np.float32)[:, None]
    return x


# ─── Event target ────────────────────────────────────────────────────────────

def match_events(articulations: list, events: list) -> dict:
    """{event index: [marks]} for the event-target marks."""
    times = np.array([float(e['t']) for e in events])
    out = {}
    if not len(times):
        return out
    for art in articulations or []:
        if not _active(art) or target(art) != 'event':
            continue
        if _is_range(art):
            lo, hi = float(art['from']), float(art['to'])
            idx = np.flatnonzero((times >= lo) & (times <= hi))
        elif art.get('t') is not None:
            d = np.abs(times - float(art['t']))
            i = int(np.argmin(d))
            idx = [i] if d[i] <= MATCH_WINDOW else []
        else:
            continue
        for i in idx:
            out.setdefault(int(i), []).append(art)
    return out


def next_gaps(events: list) -> list:
    """For each event, seconds until the next event starts later (None if none)."""
    times = np.array([float(e['t']) for e in events])
    order = np.unique(times)
    gaps = []
    for t in times:
        j = np.searchsorted(order, t, side='right')
        gaps.append(float(order[j] - t) if j < len(order) else None)
    return gaps


def shape_event(clip: np.ndarray, sr: int, marks: list, gap_s) -> np.ndarray:
    """Staccato / legato / fermata on one event's clip (frames, channels),
    before its fades and effects (so a reverb still rings after a staccato)."""
    for art in marks:
        kind = art.get('type')
        if kind == 'accent':
            continue                                 # after the fades: see accent_event
        part, rest = _band(clip, sr, art)
        part = part.astype(np.float32).copy()
        if kind == 'staccato':
            keep = int(float(art.get('keep_s', 0.15)) * sr)
            if 0 < keep < len(part):
                part = _fade_out(part[:keep].copy(), STACCATO_FADE * sr)
        elif kind == 'legato':
            if gap_s is None:
                part = _fade_out(part, min(LEGATO_END_FADE * sr, len(part) // 2))
            else:
                overlap = int(LEGATO_OVERLAP * sr)
                want = int(gap_s * sr) + overlap
                if len(part) < want:
                    part = np.concatenate([part, hold_moment(part, len(part), want - len(part))])
                part = _fade_out(part, overlap)
        elif kind == 'fermata':
            hold = int(float(art.get('hold_s', 2.0)) * sr)
            if hold > 0 and len(part):
                held = _fade_out(hold_moment(part, len(part), hold), hold * 0.3)
                part = np.concatenate([part, held])
        clip = _join(part, rest)
    return clip


def accent_event(clip: np.ndarray, sr: int, marks: list) -> np.ndarray:
    """Accents on one event's clip, after its fades."""
    for art in marks:
        if art.get('type') != 'accent':
            continue
        part, rest = _band(clip, sr, art)
        part = part.astype(np.float32).copy()
        _boost(part, 0, sr, float(art.get('boost_db', 6.0)))
        clip = _join(part, rest)
    return clip


def _boost(x, at, sr, boost_db):
    n = min(int(ACCENT_S * sr), len(x) - at)
    if n > 1:
        g = 10 ** (boost_db / 20.0)
        x[at:at + n] *= np.linspace(g, 1.0, n, dtype=np.float32)[:, None]


# ─── Mix target ──────────────────────────────────────────────────────────────

def _attacks(seg, sr, art, include_start):
    """Sample positions within seg where a range mark acts."""
    every = float(art.get('every_s') or 0)
    if every > 0:
        return list(range(0, len(seg), max(1, int(every * sr))))
    import librosa
    mono = seg.mean(axis=1) if seg.ndim == 2 else seg
    on = librosa.onset.onset_detect(y=mono.astype(np.float32), sr=sr, units='samples') if len(mono) > 2048 else []
    pos = sorted({int(p) for p in on if 0 <= p < len(seg)} | ({0} if include_start else set()))
    return pos


def apply_mix_marks(mix: np.ndarray, sr: int, articulations: list) -> np.ndarray:
    """Whole-mix staccato, accent and legato, in score time (fermatas are
    applied after the tempo stretch: see apply_mix_fermatas)."""
    for art in articulations or []:
        if not _active(art) or target(art) != 'mix' or art.get('type') == 'fermata':
            continue
        kind = art['type']
        keep = int(float(art.get('keep_s', 0.15)) * sr)
        if _is_range(art):
            i0, i1 = int(float(art['from']) * sr), int(float(art['to']) * sr)
        elif art.get('t') is not None:
            i0 = int(float(art['t']) * sr)
            i1 = i0 + (keep + int(float(art.get('silence_s', 0.07)) * sr) if kind == 'staccato'
                       else int(max(ACCENT_S, MIX_BRIDGE) * sr))
        else:
            continue
        i1 = min(i1, len(mix))
        if i0 >= i1:
            continue
        seg_full = mix[i0:i1]
        part, rest = _band(seg_full, sr, art)
        part = part.astype(np.float32).copy()

        if kind == 'staccato':
            hits = _attacks(part, sr, art, include_start=True) if _is_range(art) else [0]
            ends = hits[1:] + [len(part)]
            fade = int(STACCATO_FADE * sr)
            for a, b in zip(hits, ends):
                k = min(a + keep, b)
                f = min(fade, k - a)
                if f > 1:
                    part[k - f:k] *= np.cos(np.linspace(0, np.pi / 2, f)).astype(np.float32)[:, None]
                part[k:b] = 0.0
        elif kind == 'accent':
            hits = _attacks(part, sr, art, include_start=False) if _is_range(art) else [0]
            for a in hits:
                _boost(part, a, sr, float(art.get('boost_db', 6.0)))
        elif kind == 'legato':
            # Bridges need the sound before each attack, so work on the whole
            # mix (band-limited if asked) around the range
            hits = _attacks(part, sr, art, include_start=False) if _is_range(art) else [0]
            src, src_rest = _band(mix, sr, art)
            bridge, gain = legato_bridges(src, [i0 + a for a in hits if i0 + a > 0], int(MIX_BRIDGE * sr))
            shaped = src * gain[:, None] + bridge
            mix = _join(shaped, src_rest)[:len(mix)]
            continue

        mix[i0:i1] = _join(part, rest)[:i1 - i0]
    return mix


def apply_mix_fermatas(mix: np.ndarray, sr: int, articulations: list, tempo_map: list,
                       score_to_real) -> tuple:
    """Whole-mix fermatas, after the tempo stretch: the piece waits.

    At each mark's time (a range holds its end), the sound just before it is
    held for hold_s and inserted; the music then resumes with a short
    crossfade. Returns (mix, tempo_map) with the map holding score time still
    during each hold.
    """
    marks = [a for a in articulations or []
             if _active(a) and target(a) == 'mix' and a['type'] == 'fermata']
    pts = []
    for a in marks:
        t = a.get('to') if _is_range(a) else a.get('t')
        if t is not None:
            pts.append((float(t), a))
    tmap = [tuple(p) for p in (tempo_map or [(0.0, 0.0)])]
    for t, art in sorted(pts, key=lambda p: p[0]):
        r = score_to_real(t, tmap)
        T = int(round(r * sr))
        hold = int(float(art.get('hold_s', 2.0)) * sr)
        if hold <= 0 or T <= 0 or T > len(mix):
            continue
        xf = min(int(FERMATA_XF * sr), hold)
        src, _ = _band(mix[:T], sr, art)
        held = hold_moment(src, T, hold + xf)
        held[hold:] *= np.cos(np.linspace(0, np.pi / 2, xf)).astype(np.float32)[:, None]
        after = mix[T:].copy()
        k = min(xf, len(after))
        if k > 1:
            after[:k] *= np.sin(np.linspace(0, np.pi / 2, k)).astype(np.float32)[:, None]
        out = np.zeros((len(mix) + hold, mix.shape[1]), dtype=np.float32)
        out[:T] = mix[:T]
        out[T + hold:] = after
        end = min(len(out), T + hold + xf)
        out[T:end] += held[:end - T]
        mix = out
        # Tempo map: score time stands still at t for the hold
        h = hold / sr
        r = T / sr
        tmap = ([p for p in tmap if p[1] < r] + [(t, r), (t, r + h)] +
                [(s, rr + h) for s, rr in tmap if rr > r])
    return mix, tmap
