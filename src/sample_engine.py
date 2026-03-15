import os
import subprocess
import tempfile
import soundfile as sf
import numpy as np

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
            tracks_audio.append(audio)

        max_len = max(len(a) for a in tracks_audio)
        combined = np.zeros(max_len, dtype=np.float32)
        for tk, audio in zip(tracks_spec, tracks_audio):
            if tk.get('muted', False):
                continue
            gain = 10 ** (tk.get('gain_db', 0.0) / 20.0)
            combined[:len(audio)] += audio * gain
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