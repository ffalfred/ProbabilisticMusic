import os
import subprocess
import tempfile
import soundfile as sf
import numpy as np
from src.fx import apply_fx


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
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "44100", "-ac", "1", tmp.name],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return tmp.name

def build_bank(score: dict) -> tuple[dict, int, np.ndarray]:
    """
    Returns (bank, sr, combined_base).
    If score has a 'tracks' list, loads each track, applies gain/mute,
    sums them into combined_base. Track 0 = original full-mix file.
    Samples are sliced from their designated track (default track 0).
    Backwards-compatible: if no 'tracks', falls back to base_track.
    """
    tracks_spec = score.get('tracks', [])

    if tracks_spec:
        tracks_audio = []
        sr = None
        for tk in tracks_spec:
            path = tk['path']
            tmp_path = None
            if path.lower().endswith('.mp4'):
                tmp_path = _extract_audio(path)
                path = tmp_path
            audio, file_sr = sf.read(path, dtype='float32')
            if tmp_path:
                os.remove(tmp_path)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            if sr is None:
                sr = file_sr
            # Apply per-track FX before mixing
        fx_list = tk.get('fx', [])
        if fx_list:
            audio = apply_fx(audio, sr, fx_list)
        tracks_audio.append(audio)

        # Place each track at its correct timeline position (from_t offset)
        track_data = []
        max_end = 0
        for tk, audio in zip(tracks_spec, tracks_audio):
            t_from = float(tk.get('from', 0))
            offset_s = int(t_from * sr)
            end_s    = offset_s + len(audio)
            max_end  = max(max_end, end_s)
            track_data.append((tk, audio, offset_s))

        combined = np.zeros(max_end, dtype=np.float32)
        for tk, audio, offset_s in track_data:
            if tk.get('muted', False):
                continue
            # Volume automation envelope (multiplies on top of gain_db)
            auto = tk.get('automation', [])
            if auto:
                env = _build_auto_envelope(len(audio), sr, auto,
                                           t_from=float(tk.get('from', 0)))
                audio = audio * env
            gain = 10 ** (tk.get('gain_db', 0.0) / 20.0)
            combined[offset_s:offset_s + len(audio)] += audio * gain
        base = combined
    else:
        path = score['base_track']
        tmp_path = None
        if path.lower().endswith('.mp4'):
            tmp_path = _extract_audio(path)
            path = tmp_path
        base, sr = sf.read(path, dtype='float32')
        if tmp_path:
            os.remove(tmp_path)
        if base.ndim == 2:
            base = base.mean(axis=1)
        tracks_audio = [base]

    bank = {}
    for name, spec in score['samples'].items():
        track_idx = spec.get('track', 0)
        src = tracks_audio[track_idx] if track_idx < len(tracks_audio) else tracks_audio[0]
        i0 = int(spec['from'] * sr)
        i1 = int(spec['to']   * sr)
        bank[name] = src[i0:i1].copy()

    return bank, sr, base