import os
import subprocess
import tempfile
import soundfile as sf
import numpy as np
from src.fx import apply_fx, apply_zone
from src.dsp import to_channels, pad_frames, env_mul

# Containers whose audio is extracted with ffmpeg (same list as the editor)
_VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.webm')


def _build_auto_envelope(n_samples: int, sr: int, automation: list,
                         t_from: float = 0.0) -> np.ndarray:
    """Linear-interpolate automation points into a per-sample gain envelope.
    Times in automation are absolute (score time); t_from offsets them to
    the track's local timeline."""
    if not automation:
        return np.ones(n_samples, dtype=np.float32)
    times = np.array([float(a['t']) - t_from for a in automation]) * sr
    dbs   = np.array([float(a['db']) for a in automation], dtype=np.float32)
    x     = np.arange(n_samples, dtype=np.float32)
    db_env = np.interp(x, times, dbs, left=dbs[0], right=dbs[-1])
    return (10.0 ** (db_env / 20.0)).astype(np.float32)

def _extract_audio(video_path: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()
    subprocess.run(  # keeps the video's channels and sample rate
        ["ffmpeg", "-y", "-i", video_path, "-vn", tmp.name],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return tmp.name


_LOADED = {}           # (path, mtime, size) -> (audio, sr), read-only arrays
_LOADED_MAX = 4


def _load_audio(path: str) -> tuple:
    """Read an audio or video file as (frames, channels) float32 and its rate.
    More than two channels keep the first two (L/R). The last few files are
    kept decoded (a video's audio is extracted by ffmpeg only once), until
    the file changes on disk. The returned array is read-only."""
    try:
        st = os.stat(path)
        key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key in _LOADED:
        return _LOADED[key]
    audio, sr = _decode_audio(path)
    audio.flags.writeable = False
    if key is not None:
        while len(_LOADED) >= _LOADED_MAX:
            _LOADED.pop(next(iter(_LOADED)))
        _LOADED[key] = (audio, sr)
    return audio, sr


def _decode_audio(path: str) -> tuple:
    tmp_path = None
    if path.lower().endswith(_VIDEO_EXTS):
        tmp_path = _extract_audio(path)
        path = tmp_path
    try:
        audio, sr = sf.read(path, dtype='float32', always_2d=True)
    finally:
        if tmp_path:
            os.remove(tmp_path)
    return np.ascontiguousarray(audio[:, :2]), sr


def _resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Resample (frames, channels) audio along time (soxr, high quality)."""
    if sr_from == sr_to:
        return audio
    import librosa
    return librosa.resample(audio, orig_sr=sr_from, target_sr=sr_to, axis=0).astype(np.float32)


# What a sample can carry over from its track, in the order a track applies it
SAMPLE_STAGES = ('fx', 'fx_regions', 'automation', 'gain')
DEFAULT_INCLUDE = ('fx',)


def sample_include(spec: dict) -> tuple:
    """The track stages a sample carries: `include` is a list of
    SAMPLE_STAGES, or 'all' / 'none'. Default: the track's FX chain only."""
    inc = spec.get('include', DEFAULT_INCLUDE)
    if isinstance(inc, str):
        inc = SAMPLE_STAGES if inc == 'all' else () if inc == 'none' else (inc,)
    return tuple(st for st in SAMPLE_STAGES if st in inc)


def _apply_fx_regions(audio: np.ndarray, tk: dict, sr: int, channels: int) -> np.ndarray:
    """A track's FX regions (effects on time ranges of the track). Region
    times are on the timeline; the track's own time starts at its `from`."""
    t_from_tk = float(tk.get('from', 0))
    for fr in tk.get('fx_regions', []):
        ri0 = int((float(fr['from']) - t_from_tk) * sr)
        ri1 = int((float(fr['to']) - t_from_tk) * sr)
        audio = apply_zone(audio, sr, ri0, ri1, fr['fx'], fr)
    return audio


def _track_stages(raw: np.ndarray, tk: dict, sr: int, channels: int, include) -> np.ndarray:
    """A track's audio with the chosen stages applied, in the track's order:
    FX chain → FX regions → volume automation → gain."""
    audio = raw
    if 'fx' in include and tk.get('fx'):
        audio = to_channels(apply_fx(audio, sr, tk['fx']), channels)
    if 'fx_regions' in include and tk.get('fx_regions'):
        audio = _apply_fx_regions(audio, tk, sr, channels)
    if 'automation' in include and tk.get('automation'):
        audio = env_mul(audio, _build_auto_envelope(len(audio), sr, tk['automation'],
                                                    t_from=float(tk.get('from', 0))))
    if 'gain' in include:
        g = 10 ** (tk.get('gain_db', 0.0) / 20.0)
        if g != 1.0:
            audio = audio * g
    return audio


def build_bank(score: dict) -> tuple[dict, int, np.ndarray]:
    """
    Returns (bank, sr, combined_base). All audio is (frames, channels): the
    piece is stereo if any track is, and mono tracks then play on both sides.
    The piece's sample rate is track 0's; other tracks are resampled to it.
    If score has a 'tracks' list, loads each track, applies its FX chain,
    FX regions, automation and gain, and sums the unmuted ones, each at its
    `from`, into combined_base. Track 0 = original full-mix file.
    Samples are sliced from their designated track (default track 0), on the
    timeline, carrying the track stages listed in their `include` (default:
    the FX chain only; mute is never carried, so a muted track can still be
    sampled). Backwards-compatible: if no 'tracks', falls back to base_track.
    """
    tracks_spec = score.get('tracks', [])

    if tracks_spec:
        loaded = [_load_audio(tk['path']) for tk in tracks_spec]
        sr = loaded[0][1]
        channels = max(a.shape[1] for a, _ in loaded)
        raw_tracks = [np.array(to_channels(_resample(audio, file_sr, sr), channels), dtype=np.float32)
                      for audio, file_sr in loaded]     # writable copies of the cached files

        # Track audio per set of stages, computed once each
        cache = {}

        def staged(i, include):
            key = (i, include)
            if key not in cache:
                cache[key] = _track_stages(raw_tracks[i], tracks_spec[i], sr, channels, include)
            return cache[key]

        # Place each unmuted track, fully processed, at its timeline position
        placed = []
        for i, tk in enumerate(tracks_spec):
            if tk.get('muted', False):
                continue
            placed.append((int(float(tk.get('from', 0)) * sr), staged(i, SAMPLE_STAGES)))
        max_end = max([o + len(a) for o, a in placed] +
                      [int(float(tk.get('from', 0)) * sr) + len(r) for tk, r in zip(tracks_spec, raw_tracks)])
        combined = np.zeros((max_end, channels), dtype=np.float32)
        for offset_s, audio in placed:
            combined[offset_s:offset_s + len(audio)] += audio
        base = combined
    else:
        base, sr = _load_audio(score['base_track'])
        base = base.copy()
        tracks_spec = []

    bank = {}
    for name, spec in score['samples'].items():
        if tracks_spec:
            track_idx = spec.get('track', 0)
            if track_idx >= len(tracks_spec):
                track_idx = 0
            src = staged(track_idx, sample_include(spec))
            # Sample times are on the timeline (where the range was marked),
            # like fx_regions and automation: a track that starts at `from`
            # holds its own second 0 there.
            t_from = float(tracks_spec[track_idx].get('from', 0))
        else:
            src, t_from = base, 0.0
        bank[name] = _slice_timeline(src, sr, float(spec['from']) - t_from,
                                     float(spec['to']) - t_from)

    return bank, sr, base


def _slice_timeline(src: np.ndarray, sr: int, t0: float, t1: float) -> np.ndarray:
    """src between t0 and t1 seconds of its own time, (frames, channels).
    Parts before its start or after its end are silent, as on the timeline,
    so the sample is always as long as the marked range."""
    i0, i1 = int(np.floor(t0 * sr)), int(np.floor(t1 * sr))   # like int(t * sr) elsewhere
    out = np.zeros((max(0, i1 - i0), src.shape[1]), dtype=np.float32)
    a, b = max(i0, 0), min(i1, len(src))
    if b > a:
        out[a - i0:b - i0] = src[a:b]
    return out