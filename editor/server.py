import os
import sys
import base64
import tempfile
import subprocess
import json
import threading
import time as _time

import numpy as np
import soundfile as sf
import yaml
from flask import Flask, request, jsonify, send_from_directory

# Allow importing src.* from the parent directory
_BETA_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_BETA_DIR))
from src.sample_engine import build_bank
from src.scheduler     import get_events
from src.parser        import resolve_score, seed_everything
from src.loudness       import finish, options_from
from src.renderer      import _apply_phrase_tempo, _neutralise_score, render_mix
from src.character     import DIM_NAMES

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def _load_server_config(override: dict = None) -> dict:
    """Load config.yaml defaults, then apply any per-request override.
    Dicts (e.g. the 'v2' sub-config) are merged rather than replaced."""
    cfg = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
    if override:
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    return cfg

PREVIEW_TMP = os.path.join(tempfile.gettempdir(), "opacity_toke_preview.wav")
# Last interpreter trace from /preview — saved so the concerto download
# can fetch it via /get_last_trace to ensure viz panels match the audio.
_last_preview_trace = None

# Audio export quality settings
_AUDIO_FORMATS = {
    'wav16':   {'ext': '.wav',  'subtype': 'PCM_16',  'label': '16-bit WAV'},
    'wav24':   {'ext': '.wav',  'subtype': 'PCM_24',  'label': '24-bit WAV (studio)'},
    'wav32f':  {'ext': '.wav',  'subtype': 'FLOAT',   'label': '32-bit float WAV'},
    'flac':    {'ext': '.flac', 'subtype': 'PCM_24',  'label': 'FLAC (lossless)'},
}

def _write_audio(path: str, mix, sr: int, fmt: str = 'wav24'):
    """Write audio in the requested format, adjusting file extension if needed."""
    spec = _AUDIO_FORMATS.get(fmt, _AUDIO_FORMATS['wav24'])
    # Replace extension to match format
    base, _ = os.path.splitext(path)
    path = base + spec['ext']
    sf.write(path, mix, sr, subtype=spec['subtype'])
    return path

app = Flask(__name__, static_folder="static", static_url_path="")


# ─── Local-only access ───────────────────────────────────────────────────────
# Routes here read and write arbitrary paths on purpose (the editor opens
# audio from anywhere), so the server must only answer the editor's own page:
#  - Host must be local: blocks DNS-rebinding, where a website points its own
#    domain at 127.0.0.1 to reach this server.
#  - No cross-origin requests: browsers label them via Sec-Fetch-Site / Origin,
#    so another website — or another app on a different localhost port —
#    can't load files (e.g. <img src=…/image?path=…>) or call the API.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


@app.before_request
def _local_only():
    host = (request.host or "").rsplit(":", 1)[0].lower()
    if host not in _LOCAL_HOSTS:
        return jsonify({"error": "forbidden: non-local Host"}), 403
    if request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return jsonify({"error": "forbidden: cross-origin request"}), 403
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.host}":
        return jsonify({"error": "forbidden: cross-origin request"}), 403


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR = os.path.join(BASE_DIR, "..", "scores")
INTERPS_DIR = os.path.join(BASE_DIR, "..", "interpretations")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


def _load_single(path: str) -> dict:
    """Load audio from path and return {waveform, duration, frame} or {error}."""
    if not os.path.exists(path):
        return {"error": f"File not found: {path}", "status": 404}

    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_wav.close()
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-vn", "-ar", "44100", "-ac", "1", tmp_wav.name],
                    capture_output=True, check=True
                )
                audio_data, samplerate = sf.read(tmp_wav.name, always_2d=True)
            finally:
                os.unlink(tmp_wav.name)
        else:
            audio_data, samplerate = sf.read(path, always_2d=True)
        mono = audio_data.mean(axis=1)
        duration = len(mono) / samplerate

        n_peaks = 2000
        chunk_size = max(1, len(mono) // n_peaks)
        peaks = []
        for i in range(n_peaks):
            start = i * chunk_size
            end = min(start + chunk_size, len(mono))
            if start >= len(mono):
                peaks.append(0.0)
            else:
                chunk = mono[start:end]
                peaks.append(float(np.max(np.abs(chunk))))
    except Exception as e:
        return {"error": f"Could not read audio: {e}", "status": 500}

    frame = None
    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-vframes", "1", "-q:v", "2", tmp_path],
                    capture_output=True, check=True
                )
                with open(tmp_path, "rb") as f:
                    frame_bytes = f.read()
                frame = "data:image/png;base64," + base64.b64encode(frame_bytes).decode()
            finally:
                os.unlink(tmp_path)
        except Exception:
            frame = None

    return {"waveform": peaks, "duration": duration, "frame": frame,
            "channels": int(min(2, audio_data.shape[1]))}


@app.route("/load", methods=["POST"])
def load():
    data = request.get_json()
    tracks_spec = data.get("tracks")
    if tracks_spec:
        results = []
        for tk in tracks_spec:
            results.append(_load_single(tk["path"]))
        return jsonify({"tracks": results})
    path = data.get("path", "")
    result = _load_single(path)
    if "error" in result:
        return jsonify(result), result.get("status", 500)
    return jsonify(result)


@app.route("/frame")
def get_frame():
    path = request.args.get("path", "")
    t = request.args.get("t", "0")

    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    ext = os.path.splitext(path)[1].lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return jsonify({"frame": None})

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", str(t), "-i", path,
                    "-vframes", "1", "-q:v", "2",
                    tmp_path
                ],
                capture_output=True, check=True
            )
            with open(tmp_path, "rb") as f:
                frame_bytes = f.read()
            frame = "data:image/png;base64," + base64.b64encode(frame_bytes).decode()
        finally:
            os.unlink(tmp_path)
        return jsonify({"frame": frame})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/video")
def serve_video():
    path = request.args.get("path", "")
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    ext = os.path.splitext(path)[1].lower()
    mime_map = {
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".avi": "video/x-msvideo", ".mkv": "video/x-matroska", ".webm": "video/webm",
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
        ".ogg": "audio/ogg", ".aac": "audio/aac",
    }
    directory = os.path.dirname(os.path.abspath(path))
    filename  = os.path.basename(path)
    return send_from_directory(directory, filename,
                               mimetype=mime_map.get(ext, "video/mp4"),
                               conditional=True)


@app.route("/preview", methods=["POST"])
def preview():
    data   = request.get_json()
    path   = data.get("path", "")
    score  = data.get("score", {})

    # Interpreter workflow: load score from file path + merge interpretation config
    score_path = data.get("score_path")
    if score_path and not score:
        if not os.path.exists(score_path):
            return jsonify({"error": f"Score not found: {score_path}"}), 404
        with open(score_path) as f:
            score = yaml.safe_load(f) or {}
        # Auto-derive audio path from score if not given
        if not path:
            path = score.get("base_track", "")

    # Merge interpretation block (golems + v2config + mix_dims). An explicit
    # golems list — even an empty one — replaces the golems saved in the score.
    interp = data.get("interp", {})
    if "golems" in interp:
        score["golems"] = interp["golems"]
    mix_dims = data.get("score", {}).get("mix_dims") or interp.get("mix_dims")
    if mix_dims:
        score["mix_dims"] = mix_dims

    config = _load_server_config(data.get("_config") or interp.get("v2config"))
    # Allow request to override engine (e.g. 'v1' for composer mode)
    if data.get("engine"):
        config["engine"] = data["engine"]

    if not path:
        return jsonify({"error": "Audio file path required"}), 400
    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        seed = seed_everything(config)
        resolve_score(score)
        score["base_track"] = path
        score = _apply_phrase_tempo(score)
        bank, sr, base = build_bank(score)

        global _last_preview_trace
        if config.get("engine") == "v2":
            from src.interpreter import interpret
            events, _state_trace = interpret(score, config, return_trace=True)
            score['_state_trace'] = _state_trace
            _last_preview_trace = _state_trace  # save for /get_last_trace
        else:
            events = get_events(score)
            _last_preview_trace = None  # no trace in composer mode

        # Performance-neutral mode: strip all expressive timing from the
        # score + events so the output follows the raw score grid. Must
        # happen AFTER the interpreter runs (so the Kalman state_trace is
        # preserved for visualisation) but BEFORE mixing (so timing
        # offsets don't get applied).
        if bool(data.get("performance_neutral", False)):
            score, events = _neutralise_score(score, events)

        mix, tempo_map = render_mix(score, bank, events, sr, base)
        # Level as performed, then the safety brake (the editor's switch) and,
        # for a Concerto download, the export adjustment. Measured on the
        # whole render, so a later range trim keeps the same level.
        mix, loudness = finish(mix, sr, source=base, **options_from(data.get("loudness")))
        # 32-bit float: the exact render. Browsers decode it, and the files
        # made from it (Concerto audio, the video's soundtrack) are converted
        # once, to the format the user chose, instead of from 16-bit.
        sf.write(PREVIEW_TMP, mix, sr, subtype="FLOAT")
        return jsonify({
            "url": f"/preview_audio?v={int(_time.time())}",
            "tempo_map": tempo_map,
            "duration_real": float(len(mix) / sr),
            "seed": seed,
            "loudness": loudness,
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


# ─── Concerto Download (4K video rendering) ─────────────────────────────────
# Segment-based encoding: long videos are split into N short segments, each
# encoded by its own short-lived ffmpeg subprocess. After all segments finish,
# they're concatenated losslessly with `ffmpeg -c copy` and audio is muxed in.
# This bounds browser memory + ffmpeg pipe back-pressure per segment, which
# otherwise compounds and fails long (~8 min) downloads with NetworkError.
_concerto_ffmpeg    = None  # active ffmpeg subprocess for the CURRENT segment
_concerto_out       = None  # final output path
_concerto_video_tmp = None  # temp video-only file (concat output, pre-mux)
_concerto_preset    = None  # preset dict for pass 2 audio mux
_concerto_time_from = 0     # time range start (seconds)
_concerto_time_to   = 0     # time range end (0 = full)
_concerto_no_audio  = False # if True, skip audio mux in pass 2
_concerto_lead_in   = 0     # seconds of silence before audio
_concerto_lead_out  = 0     # seconds of silence after audio
_concerto_next      = 0     # next expected frame index WITHIN CURRENT SEGMENT
_concerto_buf       = {}    # out-of-order frame buffer {index: raw_bytes}
_concerto_segments  = []    # list of per-segment .mkv paths (for concat)
_concerto_w         = 0     # render width  (remembered across segment starts)
_concerto_h         = 0     # render height
_concerto_fps       = 60    # render fps
# Wire format the browser sends us per frame. 'png' is lossless and safe for
# any content but very large (~15 MB/frame at 4K for fine mesh, which causes
# browser GC pressure and rising-ETA slowdown). 'webp' and 'jpeg' are much
# smaller. Accepted values: 'png', 'webp', 'jpeg'. Default 'png' keeps the
# previous behaviour for callers that don't specify.
_concerto_wire_format = 'png'
# Max threads ffmpeg may use when decoding incoming frames. PNG decode at 4K
# is CPU-heavy; without a cap, ffmpeg will grab every core and starve the
# browser's encode step. Default = max(2, cpu_count // 4) — on an 18-core
# box that's 4, leaving plenty for Chrome. Browser can override per-render
# via the `decode_threads` field on /concerto_start.
_concerto_decode_threads = max(2, (os.cpu_count() or 4) // 4)
# Lock around _concerto_buf / _concerto_next and the ffmpeg process handle —
# held only briefly. Never held during a blocking stdin.write.
_concerto_lock      = threading.Lock()
# Serialises "take the next in-order frames + write them to ffmpeg" across
# request threads. The browser keeps several batch uploads in flight; without
# this, two handlers could each take a run of frames and interleave writes.
_concerto_write_lock = threading.Lock()
_concerto_seg_path  = None  # segment file the current ffmpeg is writing

# Presets from Toke's ffmpeg research, for BrightSign gallery playback.
# Audio: "1" presets AAC in .mp4; "2" presets AC-3 640k in .ts — MPEG-TS can't
# carry plain PCM (ffmpeg writes it as an unnamed data stream, so players are
# silent), and BrightSign documents MPEG audio, AAC and AC-3 for .ts; "3"
# presets lossless 24-bit PCM in .mov (BrightSign support to be tested).
_CONCERTO_PRESETS = {
    # A1: Top Quality HEVC 10-bit + near-lossless AAC 320k (MP4) — SLOW
    'a1': {
        'ext': '.mp4',
        'args': [
            '-c:v', 'libx265', '-preset', 'veryslow', '-crf', '14',
            '-x265-params', 'profile=main10:ref=6:bframes=8:rc-lookahead=60',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'aac', '-b:a', '320k',
            '-movflags', '+faststart',
        ],
    },
    # A2: Top Quality HEVC 10-bit + AC-3 640k (TS) — SLOW
    'a2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'veryslow', '-crf', '14',
            '-x265-params', 'profile=main10:ref=6:bframes=8:rc-lookahead=60',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'ac3', '-b:a', '640k', '-ar', '48000',
            '-f', 'mpegts',
        ],
    },
    # B1: High Quality 4K HEVC 10-bit + AAC 320k (MP4) — 5-10× faster than A1
    'b1': {
        'ext': '.mp4',
        'args': [
            '-c:v', 'libx265', '-preset', 'medium', '-crf', '16',
            '-x265-params', 'profile=main10:ref=4:bframes=4',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'aac', '-b:a', '320k',
            '-movflags', '+faststart',
        ],
    },
    # B2: High Quality 4K HEVC 10-bit + AC-3 640k (TS) — 5-10× faster than A2
    'b2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'medium', '-crf', '16',
            '-x265-params', 'profile=main10:ref=4:bframes=4',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'ac3', '-b:a', '640k', '-ar', '48000',
            '-f', 'mpegts',
        ],
    },
    # T1: Test HEVC 8-bit + AAC 256k (MP4)
    't1': {
        'ext': '.mp4',
        'args': [
            '-c:v', 'libx265', '-preset', 'fast', '-crf', '22',
            '-x265-params', 'profile=main',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '256k',
            '-movflags', '+faststart',
        ],
    },
    # T2: Test HEVC 8-bit + AC-3 640k (TS)
    't2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'fast', '-crf', '22',
            '-x265-params', 'profile=main',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'ac3', '-b:a', '640k', '-ar', '48000',
            '-f', 'mpegts',
        ],
    },
    # H1: Hardware HEVC 10-bit (Intel VAAPI / iHD) QP 22 + AAC 320k (MP4)
    'h1': {
        'ext':  '.mp4',
        'hw':   'vaapi',
        'args': [
            '-c:v', 'hevc_vaapi', '-qp', '22',
            '-profile:v', 'main10',
            '-c:a', 'aac', '-b:a', '320k',
            '-movflags', '+faststart',
        ],
    },
    # H2: Hardware HEVC 10-bit (Intel VAAPI / iHD) QP 22 + AC-3 640k (TS)
    'h2': {
        'ext':  '.ts',
        'hw':   'vaapi',
        'args': [
            '-c:v', 'hevc_vaapi', '-qp', '22',
            '-profile:v', 'main10',
            '-c:a', 'ac3', '-b:a', '640k', '-ar', '48000',
            '-f', 'mpegts',
        ],
    },
    # H1Q: Hardware HEVC 10-bit QP 16 (higher quality) + AAC 320k (MP4)
    'h1q': {
        'ext':  '.mp4',
        'hw':   'vaapi',
        'args': [
            '-c:v', 'hevc_vaapi', '-qp', '16',
            '-profile:v', 'main10',
            '-c:a', 'aac', '-b:a', '320k',
            '-movflags', '+faststart',
        ],
    },
    # H2Q: Hardware HEVC 10-bit QP 16 (higher quality) + AC-3 640k (TS)
    'h2q': {
        'ext':  '.ts',
        'hw':   'vaapi',
        'args': [
            '-c:v', 'hevc_vaapi', '-qp', '16',
            '-profile:v', 'main10',
            '-c:a', 'ac3', '-b:a', '640k', '-ar', '48000',
            '-f', 'mpegts',
        ],
    },
}

# "3" presets: the "2" presets' video with lossless 24-bit PCM in a QuickTime .mov
for _k2, _k3 in (('a2', 'a3'), ('b2', 'b3'), ('t2', 't3'), ('h2', 'h3'), ('h2q', 'h3q')):
    _p = _CONCERTO_PRESETS[_k2]
    _video = _p['args'][:_p['args'].index('-c:a')]
    _CONCERTO_PRESETS[_k3] = {
        **{k: v for k, v in _p.items() if k != 'args'},
        'ext': '.mov',
        'args': _video + ['-c:a', 'pcm_s24le', '-f', 'mov', '-movflags', '+faststart'],
    }


def _preset_audio_args(args: list) -> list:
    """The audio options of a preset (codec, bitrate, sample rate)."""
    out, i = [], 0
    while i < len(args):
        if args[i] in _AUDIO_OPTS:
            out.extend([args[i], args[i + 1]])
            i += 2
        else:
            i += 1
    return out


_AUDIO_OPTS = ('-c:a', '-b:a', '-ar')


def _concerto_mux_cmd(preset: dict, video_path: str, audio_path: str, out_path: str,
                      audio_trim: list = (), audio_filter: list = ()) -> list:
    """ffmpeg command that joins a rendered video with its sound, encoding the
    sound as the preset says."""
    args = preset['args']
    audio_args = _preset_audio_args(args) or ['-c:a', 'copy']
    if audio_filter and audio_args == ['-c:a', 'copy']:
        audio_args = ['-c:a', 'aac', '-b:a', '320k']    # filters need re-encoding
    fmt_args = ['-f', args[args.index('-f') + 1]] if '-f' in args else []
    # HEVC in .mov / .mp4 needs the hvc1 tag for Apple players (QuickTime, Safari)
    hevc = any(a in args for a in ('libx265', 'hevc_vaapi'))
    tag = ['-tag:v', 'hvc1'] if hevc and preset.get('ext') in ('.mov', '.mp4') else []
    return ['ffmpeg', '-y', '-i', video_path, *audio_trim, '-i', audio_path,
            '-c:v', 'copy', *tag, *audio_args, *audio_filter,
            *(['-movflags', '+faststart'] if '-movflags' in args else []),
            *fmt_args, '-shortest', out_path]

def _discard_current_segment():
    """Delete the segment file the killed/failed ffmpeg was writing, so a
    later resume doesn't treat a truncated segment as complete."""
    global _concerto_seg_path
    if _concerto_seg_path and os.path.exists(_concerto_seg_path):
        try: os.remove(_concerto_seg_path)
        except OSError: pass
    if _concerto_seg_path in _concerto_segments:
        _concerto_segments.remove(_concerto_seg_path)
    _concerto_seg_path = None


def _kill_concerto_ffmpeg():
    """Kill any active ffmpeg subprocess, discard its partial segment, and
    clear the global. Safe to call when nothing is running.

    Caller must hold _concerto_lock.
    """
    global _concerto_ffmpeg
    if _concerto_ffmpeg is None:
        return
    proc = _concerto_ffmpeg
    _concerto_ffmpeg = None
    try: proc.stdin.close()
    except Exception: pass
    try: proc.kill()
    except Exception: pass
    try: proc.wait(timeout=5)
    except Exception: pass
    _discard_current_segment()


@app.route("/concerto_start", methods=["POST"])
def concerto_start():
    """Start (or resume) a concerto encode.

    `segment_index == 0` performs full initialisation: stores the output path,
    preset, time range, etc., clears the segment list, AND kills any leftover
    ffmpeg from a prior aborted run. Subsequent calls just spawn a fresh
    ffmpeg subprocess for the next segment, reusing the saved state. Each
    segment's frames are numbered from 0; the browser resets its `start_index`
    per segment.
    """
    global _concerto_ffmpeg, _concerto_out, _concerto_video_tmp, _concerto_preset
    global _concerto_next, _concerto_buf, _concerto_time_from, _concerto_time_to
    global _concerto_no_audio, _concerto_segments, _concerto_w, _concerto_h, _concerto_fps
    global _concerto_wire_format, _concerto_decode_threads
    global _concerto_lead_in, _concerto_lead_out

    data       = request.get_json()
    seg_index  = int(data.get('segment_index', 0))
    is_resume  = bool(data.get('resume', False))  # skip setup, just spawn ffmpeg

    # Defensive unblock: if a previous run's ffmpeg is still alive AND a
    # /concerto_frames thread is stuck on `stdin.write()` (because the OS
    # pipe is full and ffmpeg is slow), SIGKILLing the process closes the
    # pipe, which unblocks the stuck write with BrokenPipeError. Safe to do
    # without the lock — kill is idempotent and we'll re-check / clean up
    # properly inside.
    if seg_index == 0 and _concerto_ffmpeg is not None:
        try: _concerto_ffmpeg.kill()
        except Exception: pass

    # Take the lock for the whole start sequence so we cannot race with a
    # late finish_segment.wait() from a previous run nulling out our fresh
    # _concerto_ffmpeg, or with concurrent /concerto_frames writes touching
    # _concerto_buf / _concerto_next while we're resetting them.
    with _concerto_lock:
        # Per-segment state always resets
        _concerto_next = 0
        _concerto_buf  = {}

        if seg_index == 0 and not is_resume:
            # New encode: defensively kill any leftover ffmpeg from a prior
            # aborted run (browser cancelled, error mid-render, page reloaded,
            # etc.) so we never inherit a dangling subprocess.
            _kill_concerto_ffmpeg()

            _concerto_w   = int(data.get('width',  3840))
            _concerto_h   = int(data.get('height', 2160))
            _concerto_fps = int(data.get('fps',    60))
            quality       = data.get('quality', 'top')
            out_path      = (data.get('out_path') or '').strip()
            _concerto_time_from = float(data.get('time_from', 0) or 0)
            _concerto_time_to   = float(data.get('time_to', 0) or 0)
            _concerto_no_audio  = bool(data.get('no_audio', False))
            _concerto_lead_in   = float(data.get('lead_in', 0) or 0)
            _concerto_lead_out  = float(data.get('lead_out', 0) or 0)

            # Wire format the browser will use to send frames. Only png
            # (lossless) and jpeg (fast) are supported now.
            wf = (data.get('wire_format') or 'raw').lower()
            if wf not in ('raw', 'png', 'jpeg'):
                return jsonify({"error": f"invalid wire_format: {wf}"}), 400
            _concerto_wire_format = wf

            # Optional ffmpeg decode-thread cap. Only meaningful for PNG at
            # the moment (other formats are cheap to decode). Clamp to a
            # sensible range; fall back to computed default.
            dt = data.get('decode_threads')
            if dt is not None:
                try:
                    dt = max(1, min(64, int(dt)))
                except Exception:
                    dt = None
            if dt is not None:
                _concerto_decode_threads = dt

            if not out_path:
                return jsonify({"error": "No save path provided"}), 400

            preset = _CONCERTO_PRESETS.get(quality, _CONCERTO_PRESETS['a1'])
            ext    = preset['ext']

            # Ensure directory exists and fix extension to match preset
            out_path = os.path.abspath(out_path)
            base, _  = os.path.splitext(out_path)
            out_path = base + ext
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            _concerto_out       = out_path
            _concerto_video_tmp = _concerto_out + '.video_tmp.mkv'
            _concerto_preset    = preset
            # Check for segment files from a previous failed render.
            # Build a set of existing segment indices (may have gaps).
            _concerto_segments  = []
            _existing_set = set()
            for _i in range(0, 9999):
                seg_candidate = _concerto_out + f'.seg_{_i:04d}.mkv'
                if os.path.exists(seg_candidate) and os.path.getsize(seg_candidate) > 0:
                    _concerto_segments.append(seg_candidate)
                    _existing_set.add(_i)
                elif _existing_set and _i > max(_existing_set) + 10:
                    break  # stop scanning well past the last found segment
            if _existing_set:
                print(f"[concerto] found {len(_existing_set)} existing segments: {sorted(_existing_set)}")
                # Return early — setup is done, no ffmpeg spawned yet.
                # Browser will call /concerto_start for each missing segment.
                return jsonify({"ok": True, "existing_segments": sorted(_existing_set)})
        else:
            # Spawn ffmpeg for this specific segment — require prior init
            if not _concerto_preset or not _concerto_out:
                return jsonify({"error": "segment_index > 0 without prior init"}), 400
            # Previous segment must have been closed via /concerto_finish_segment
            if _concerto_ffmpeg is not None:
                return jsonify({"error": "previous segment still open — call /concerto_finish_segment first"}), 400

        # Strip audio args AND container-specific flags — video-only segment to MKV
        filtered = []
        skip_next = False
        for a in _concerto_preset['args']:
            if skip_next:
                skip_next = False
                continue
            if a in ('-c:a', '-b:a', '-ar', '-f'):
                skip_next = True
                continue
            if a in ('-movflags', '+faststart'):
                continue
            filtered.append(a)

        seg_path = _concerto_out + f'.seg_{seg_index:04d}.mkv'
        if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
            return jsonify({"error": f"segment {seg_index} already exists — refusing to overwrite"}), 400

        # Input is a stream of concatenated frames in whichever format the
        # browser chose (png / webp / jpeg). The demuxer flags differ per
        # format: PNG + JPEG go through `image2pipe` with `-c:v`, WebP uses
        # its own `webp_pipe` demuxer (no -c:v required).
        if _concerto_wire_format == 'raw':
            # Raw RGBA: no browser-side compression. ffmpeg reads raw pixels.
            input_flags = ['-f', 'rawvideo', '-pix_fmt', 'rgba',
                           '-s', f'{_concerto_w}x{_concerto_h}',
                           '-r', str(_concerto_fps)]
        elif _concerto_wire_format == 'jpeg':
            input_flags = ['-f', 'image2pipe', '-c:v', 'mjpeg',
                           '-framerate', str(_concerto_fps)]
        else:  # png
            # -threads caps CPU usage for PNG decode so ffmpeg doesn't starve
            # the browser's encode step. Only applied for PNG — JPEG decode
            # is cheap enough not to matter.
            input_flags = ['-threads', str(_concerto_decode_threads),
                           '-f', 'image2pipe', '-c:v', 'png',
                           '-framerate', str(_concerto_fps)]

        hw_mode = _concerto_preset.get('hw')

        if hw_mode == 'vaapi':
            # Hardware HEVC via VA-API (Intel iGPU). Requires a hardware
            # device init + format/upload filter before the encoder. The
            # LIBVA_DRIVER_NAME=iHD env var is set on the Popen below so
            # Meteor Lake picks the right driver.
            cmd = [
                'ffmpeg', '-y',
                '-vaapi_device', '/dev/dri/renderD128',
                *input_flags,
                '-i', 'pipe:0',
                '-vf', 'format=p010,hwupload',
                '-an',
                *filtered,
                seg_path,
            ]
        else:
            cmd = [
                'ffmpeg', '-y',
                *input_flags,
                '-i', 'pipe:0',
                '-an',                          # no audio in segment encode
                *filtered,
                seg_path,
            ]
        # For VA-API on Meteor Lake, force the iHD driver — the legacy i965
        # one doesn't support HEVC 10-bit Main10. Inherit other env vars.
        proc_env = None
        if hw_mode == 'vaapi':
            proc_env = os.environ.copy()
            proc_env['LIBVA_DRIVER_NAME'] = 'iHD'

        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.PIPE,
                                          env=proc_env)
        except Exception as e:
            _concerto_ffmpeg = None
            return jsonify({"error": f"ffmpeg spawn failed: {e}"}), 500

        # Catch immediate ffmpeg-startup failures (bad codec, missing binary,
        # etc.) — Popen returns even if ffmpeg exits in the next millisecond.
        # VA-API init takes longer (~100-200 ms) than software startup, so
        # use a slightly larger grace period for hardware presets.
        _time.sleep(0.25 if hw_mode == 'vaapi' else 0.05)
        rc = proc.poll()
        if rc is not None:
            err = b''
            try: err = proc.stderr.read()
            except Exception: pass
            _concerto_ffmpeg = None
            tail = err.decode('utf-8', errors='replace')[-500:] if err else ''
            return jsonify({"error": f"ffmpeg exited immediately (rc={rc}): {tail}"}), 500

        _concerto_ffmpeg = proc
        global _concerto_seg_path
        _concerto_seg_path = seg_path

        # Enlarge the pipe buffer so ffmpeg has breathing room before
        # stdin.write blocks. Default is 64KB (< 1 raw 4K frame).
        # On Linux, F_SETPIPE_SZ can raise it up to pipe-max-size (1MB).
        # On macOS this call doesn't exist — silently skip.
        try:
            import fcntl
            F_SETPIPE_SZ = 1031  # Linux-specific
            pipe_max = 1048576   # 1MB — safe default
            try:
                with open('/proc/sys/fs/pipe-max-size') as f:
                    pipe_max = int(f.read().strip())
            except Exception:
                pass
            fcntl.fcntl(proc.stdin.fileno(), F_SETPIPE_SZ, pipe_max)
        except Exception:
            pass  # not Linux, or permission denied — carry on with default

        # Track segment for later concat (avoid duplicates if the browser retries)
        if seg_path not in _concerto_segments:
            _concerto_segments.append(seg_path)
        return jsonify({"ok": True, "segment_index": seg_index})


@app.route("/concerto_finish_segment", methods=["POST"])
def concerto_finish_segment():
    """Close the current segment's ffmpeg subprocess and wait for it to flush.

    Keeps overall encode state (output path, preset, segments list) intact
    so the next /concerto_start call can spawn the next segment.
    """
    global _concerto_ffmpeg, _concerto_seg_path
    # Wait for any in-flight frame write before closing ffmpeg's stdin.
    with _concerto_write_lock, _concerto_lock:
        proc = _concerto_ffmpeg
        if proc is None:
            seg_count = len(_concerto_segments)
            has_state = bool(_concerto_preset and _concerto_out)
            return jsonify({
                "error": "No active concerto segment",
                "segments_done": seg_count,
                "init_state_present": has_state,
            }), 400
        _concerto_ffmpeg = None
        try: proc.stdin.close()
        except Exception: pass

    try:
        seg_stderr = proc.stderr.read() if proc.stderr else b''
        proc.wait(timeout=300)
        tail = seg_stderr.decode('utf-8', errors='replace')[-300:] if seg_stderr else ''
        if proc.returncode != 0:
            with _concerto_lock:
                _discard_current_segment()
            return jsonify({"error": f"ffmpeg failed on segment (rc={proc.returncode}): {tail}"}), 500
        if tail:
            print(f"[concerto seg {len(_concerto_segments) - 1} stderr]", tail)
        _concerto_seg_path = None  # complete — keep it for resume
        return jsonify({"ok": True, "segments_done": len(_concerto_segments)})
    except Exception as e:
        try: proc.kill()
        except Exception: pass
        with _concerto_lock:
            _discard_current_segment()
        return jsonify({"error": str(e)}), 500


@app.route("/concerto_cancel", methods=["POST"])
def concerto_cancel():
    """Abort an in-progress concerto encode.

    Called by the browser on Cancel and on any error. Kills the current
    ffmpeg subprocess, deletes the segment it was writing (it is incomplete),
    and clears per-encode state. Completed segments stay on disk so the
    render can be resumed.

    Safe to call even when no encode is in progress (returns ok=true).
    """
    global _concerto_out, _concerto_video_tmp, _concerto_preset, _concerto_segments
    with _concerto_lock:
        _kill_concerto_ffmpeg()
        # Clean the pre-mux tmp file if it exists
        if _concerto_video_tmp and os.path.exists(_concerto_video_tmp):
            try: os.remove(_concerto_video_tmp)
            except OSError: pass
        _concerto_out       = None
        _concerto_video_tmp = None
        _concerto_preset    = None
        _concerto_segments  = []
    return jsonify({"ok": True, "cancelled": True})


@app.route("/concerto_frames", methods=["POST"])
def concerto_frames():
    """Batch frame upload — multiple frames packed in one request.

    Frames go into a reorder buffer under _concerto_lock. Taking the next
    in-order run and writing it to ffmpeg happen together under
    _concerto_write_lock, so concurrent batches can't interleave their writes.
    """
    global _concerto_next, _concerto_buf, _concerto_ffmpeg
    if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
        return jsonify({"error": "No active concerto render"}), 400
    batch_blob = request.files.get('frames')
    if not batch_blob:
        return jsonify({"error": "No frame data"}), 400
    try:
        start_idx_form = request.form.get('start_index')
        count          = int(request.form.get('count', 1))
        lengths_form   = request.form.get('lengths', '')
        raw_all        = batch_blob.read()

        if lengths_form:
            lengths = [int(x) for x in lengths_form.split(',')]
            if len(lengths) != count:
                return jsonify({"error": f"lengths count mismatch: {len(lengths)} vs {count}"}), 400
            if sum(lengths) != len(raw_all):
                return jsonify({"error": f"lengths sum {sum(lengths)} != body {len(raw_all)}"}), 400
        else:
            fsize   = len(raw_all) // count if count > 0 else len(raw_all)
            lengths = [fsize] * count

        chunks = []
        with _concerto_write_lock:
            with _concerto_lock:
                if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
                    return jsonify({"error": "No active concerto render"}), 400
                start_idx = int(start_idx_form) if start_idx_form is not None else _concerto_next
                offset = 0
                for i, length in enumerate(lengths):
                    _concerto_buf[start_idx + i] = raw_all[offset : offset + length]
                    offset += length
                while _concerto_next in _concerto_buf:
                    chunks.append(_concerto_buf.pop(_concerto_next))
                    _concerto_next += 1
                proc = _concerto_ffmpeg  # snapshot under lock
                buf_lag = len(_concerto_buf)  # frames waiting out of order
            t0 = _time.time()
            for chunk in chunks:
                proc.stdin.write(chunk)
            write_ms = (_time.time() - t0) * 1000
        return jsonify({"ok": True, "write_ms": round(write_ms, 1), "lag": buf_lag})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/concerto_finish", methods=["POST"])
def concerto_finish():
    """Concatenate all encoded segments, mux audio, return final path.

    Expects /concerto_finish_segment to have been called for the last segment
    so no ffmpeg subprocess is still open. With one segment we skip the concat
    step entirely.
    """
    global _concerto_ffmpeg, _concerto_out, _concerto_video_tmp, _concerto_preset
    global _concerto_segments
    if _concerto_ffmpeg is not None:
        return jsonify({"error": "A segment is still open — call /concerto_finish_segment first"}), 400
    if not _concerto_segments:
        return jsonify({"error": "No segments to finalise"}), 400
    try:
        # Verify all segment files exist
        missing = [s for s in _concerto_segments if not os.path.exists(s)]
        if missing:
            return jsonify({"error": f"Segment files missing: {missing[:3]}"}), 500

        # Sort segments by index so concat is in the right order
        # (resume may have added them out of order: existing first, new after)
        _concerto_segments.sort()

        # Step 1: stitch segments → _concerto_video_tmp (lossless, -c copy)
        if len(_concerto_segments) == 1:
            # Single segment — just rename
            import shutil
            shutil.move(_concerto_segments[0], _concerto_video_tmp)
        else:
            concat_list = _concerto_video_tmp + '.concat.txt'
            with open(concat_list, 'w') as f:
                for seg in _concerto_segments:
                    # ffmpeg concat demuxer: single-quote the path, escape any quotes
                    escaped = seg.replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")
            concat_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', concat_list,
                '-c', 'copy',
                _concerto_video_tmp,
            ]
            cp = subprocess.run(concat_cmd, capture_output=True, timeout=600)
            try:
                os.remove(concat_list)
            except OSError:
                pass
            if cp.returncode != 0:
                tail = cp.stderr.decode('utf-8', errors='replace')[-500:]
                return jsonify({"error": f"Concat failed: {tail}"}), 500

        if not os.path.exists(_concerto_video_tmp):
            return jsonify({"error": "Concat produced no output file"}), 500

        # Step 2: mux audio (or just rename if no_audio)
        if _concerto_no_audio:
            import shutil
            shutil.move(_concerto_video_tmp, _concerto_out)
        else:
            # Pass 2: mux video + audio into final output
            audio_trim = []
            if _concerto_time_from > 0 or _concerto_time_to > 0:
                if _concerto_time_from > 0:
                    audio_trim = ['-ss', str(_concerto_time_from)]
                if _concerto_time_to > _concerto_time_from:
                    audio_trim += ['-t', str(_concerto_time_to - _concerto_time_from)]

            # Audio filter for lead-in/out: delay the audio start by
            # lead_in seconds, pad with silence at the end so audio
            # duration matches the video (which includes lead_out).
            audio_filter = []
            if _concerto_lead_in > 0 or _concerto_lead_out > 0:
                parts = []
                if _concerto_lead_in > 0:
                    ms = int(_concerto_lead_in * 1000)
                    parts.append(f'adelay={ms}|{ms}')  # delay both channels
                if _concerto_lead_out > 0:
                    parts.append(f'apad=pad_dur={_concerto_lead_out}')
                audio_filter = ['-af', ','.join(parts)]

            mux_cmd = _concerto_mux_cmd(_concerto_preset, _concerto_video_tmp, PREVIEW_TMP,
                                        _concerto_out, audio_trim, audio_filter)
            subprocess.run(mux_cmd, check=True, capture_output=True, timeout=120)

        # Clean up temps: stitched video tmp and segment files. The render
        # metadata (<base>.trace.json) is kept: later meta/viz passes of the
        # same download may still need it to resume.
        if os.path.exists(_concerto_video_tmp):
            try: os.remove(_concerto_video_tmp)
            except OSError: pass
        for seg in _concerto_segments:
            if os.path.exists(seg):
                try: os.remove(seg)
                except OSError: pass
        legacy_trace = _concerto_out + '.trace.json'
        if os.path.exists(legacy_trace):
            try: os.remove(legacy_trace)
            except OSError: pass

        path = _concerto_out
        _concerto_out       = None
        _concerto_video_tmp = None
        _concerto_preset    = None
        _concerto_segments  = []

        if os.path.exists(path):
            return jsonify({"path": path})
        return jsonify({"error": "Mux finished but output file not found"}), 500
    except Exception as e:
        _concerto_ffmpeg = None
        return jsonify({"error": str(e)}), 500


@app.route("/downloads_path")
def downloads_path():
    home = os.path.expanduser("~")
    dl = os.path.join(home, "Downloads")
    if os.path.isdir(dl):
        return jsonify({"path": dl})
    return jsonify({"path": home})


@app.route("/save_png", methods=["POST"])
def save_png():
    """Save a base64 PNG to a user-chosen path on disk."""
    data = request.get_json()
    path = (data.get('path') or '').strip()
    b64  = data.get('data', '')
    if not path or not b64:
        return jsonify({"error": "Path and data required"}), 400
    try:
        path = os.path.abspath(path)
        if not path.lower().endswith('.png'):
            path += '.png'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = base64.b64decode(b64)
        with open(path, 'wb') as f:
            f.write(raw)
        return jsonify({"path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/preview_audio")
def preview_audio():
    if not os.path.exists(PREVIEW_TMP):
        return jsonify({"error": "No preview rendered yet"}), 404
    directory = os.path.dirname(PREVIEW_TMP)
    filename  = os.path.basename(PREVIEW_TMP)
    return send_from_directory(directory, filename, mimetype="audio/wav", conditional=True)


@app.route("/get_last_trace")
def get_last_trace():
    """Return the interpreter trace from the most recent /preview call.

    Used by the concerto download to ensure the viz panels show the
    exact same trace that produced the audio — not a stale trace from
    a separate Trace button click.
    """
    if _last_preview_trace is None:
        return jsonify({"trace": None})
    # Format matches what kalman-trace.js expects in _lastTraceData
    return jsonify({"trace": _last_preview_trace})


@app.route("/concerto_check_segments", methods=["POST"])
def concerto_check_segments():
    """Check if segment files exist for a given output path.

    Lightweight check — no setup, no ffmpeg. Used by the browser to
    decide whether to skip /preview on resume.
    """
    data = request.get_json()
    out_path = (data.get('out_path') or '').strip()
    if not out_path:
        return jsonify({"existing": []})
    base, _ = os.path.splitext(os.path.abspath(out_path))
    # Segments are named <base>[_meta|_<viz>]<preset ext>.seg_NNNN.mkv; the
    # preset decides the extension, and the meta/viz passes add a suffix.
    import glob, re
    existing = set()
    for seg in glob.glob(glob.escape(base) + '*.seg_*.mkv'):
        m = re.search(r'\.seg_(\d{4})\.mkv$', seg)
        if m and os.path.getsize(seg) > 0:
            existing.add(int(m.group(1)))
    return jsonify({"existing": sorted(existing)})


def _trace_file(out_path: str) -> str:
    """Saved-render metadata lives next to the output, independent of the
    preset extension: <base>.trace.json."""
    return os.path.splitext(os.path.abspath(out_path))[0] + '.trace.json'


@app.route("/concerto_save_trace", methods=["POST"])
def concerto_save_trace():
    """Persist what a resume needs to reproduce this render exactly.

    Called by the browser right after /preview on a fresh concerto download,
    with the main `out_path`. Stores the render seed, tempo map, real
    duration and the last preview trace (null in composer mode). Any extra
    keys in the request body are stored too and returned by load.
    """
    data = request.get_json() or {}
    out_path = (data.get('out_path') or _concerto_out or '').strip()
    if not out_path:
        return jsonify({"error": "out_path required"}), 400
    trace_path = _trace_file(out_path)
    try:
        payload = {k: v for k, v in data.items() if k != 'out_path'}
        payload["trace"] = _last_preview_trace
        os.makedirs(os.path.dirname(trace_path), exist_ok=True)
        with open(trace_path, 'w') as f:
            json.dump(payload, f)
        return jsonify({"ok": True, "path": trace_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/concerto_load_trace", methods=["POST"])
def concerto_load_trace():
    """Load the metadata saved by /concerto_save_trace for resume."""
    data = request.get_json()
    out_path = (data.get('out_path') or '').strip()
    if not out_path:
        return jsonify({"error": "No out_path provided"}), 400
    base, _ = os.path.splitext(os.path.abspath(out_path))
    # Current naming first, then the older <base><ext>.trace.json files.
    trace_path = None
    for candidate in [_trace_file(out_path)] + [base + ext + '.trace.json'
                                                for ext in ('.mp4', '.mkv', '.mov', '.ts')]:
        if os.path.exists(candidate):
            trace_path = candidate
            break
    if not trace_path:
        return jsonify({"error": "No saved trace found"}), 404
    try:
        with open(trace_path) as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/save_preview_audio", methods=["POST"])
def save_preview_audio():
    """Save PREVIEW_TMP (the last rendered audio) to a user-chosen path.

    Used by the concerto popup's 'Audio' output checkbox. The audio has
    already been rendered by /preview (with performance_neutral and the
    export loudness applied). Written in `audio_format` (as the Interpreter
    export: wav24 default, wav32f, flac, wav16). Optionally pads silence at
    the start (lead_in) and end (lead_out) so the file matches a video that
    has matching lead-in/lead-out — the muxed result will stay in sync.
    """
    data = request.get_json() or {}
    out_path = (data.get('out_path') or '').strip()
    if not out_path:
        return jsonify({"error": "out_path required"}), 400
    if not os.path.exists(PREVIEW_TMP):
        return jsonify({"error": "No preview rendered yet — call /preview first"}), 404
    try:
        lead_in   = max(0.0, float(data.get('lead_in', 0) or 0))
        lead_out  = max(0.0, float(data.get('lead_out', 0) or 0))
        # Optional range in real (rendered-audio) time, as for /concerto_start.
        time_from = max(0.0, float(data.get('time_from', 0) or 0))
        time_to   = max(0.0, float(data.get('time_to', 0) or 0))
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        audio, sr_in = sf.read(PREVIEW_TMP, dtype='float32', always_2d=True)
        i0 = min(len(audio), int(round(time_from * sr_in)))
        i1 = min(len(audio), int(round(time_to * sr_in))) if time_to > time_from else len(audio)
        ch = audio.shape[1]
        padded = np.concatenate([
            np.zeros((int(round(lead_in * sr_in)), ch), dtype=np.float32),
            audio[i0:i1],
            np.zeros((int(round(lead_out * sr_in)), ch), dtype=np.float32),
        ])
        if ch == 1:
            padded = padded[:, 0]
        # _write_audio sets the extension to match the format (.wav / .flac)
        out_path = _write_audio(out_path, padded, sr_in, data.get('audio_format', 'wav24'))
        return jsonify({"path": out_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export_audio", methods=["POST"])
@app.route("/export_interp_wav", methods=["POST"])
def export_audio():
    """Render and save an audio file — the Composer's or the Interpreter's.

    The Composer sends its current state as `score` (rendered like its Mix:
    engine v1 unless `engine` says otherwise); the Interpreter sends
    `score_path` plus its interpretation (`interp`). export_mode: 'interp' /
    'mix' (everything), 'score_only' (events, no source), 'raw' (the source).
    """
    import datetime
    data = request.get_json()
    path = data.get("path", "")
    score_path = data.get("score_path")
    composer = isinstance(data.get("score"), dict) and bool(data["score"])
    try:
        if composer:
            score = json.loads(json.dumps(data["score"]))       # private copy
        else:
            if not score_path or not os.path.exists(score_path):
                return jsonify({"error": f"Score not found: {score_path}"}), 404
            with open(score_path) as f:
                score = yaml.safe_load(f) or {}
        if not path:
            path = score.get("base_track", "")
        if not path or not os.path.exists(path):
            return jsonify({"error": "Audio file path required/not found"}), 404

        interp = data.get("interp", {})
        if "golems" in interp:
            score["golems"] = interp["golems"]
        if interp.get("mix_dims"):
            score["mix_dims"] = interp["mix_dims"]
        config = _load_server_config(data.get("_config") or interp.get("v2config"))
        if data.get("engine"):
            config["engine"] = data["engine"]
        elif composer:
            config["engine"] = "v1"                   # the Composer's Mix engine
        seed_everything(config)
        resolve_score(score)
        score["base_track"] = path
        score = _apply_phrase_tempo(score)
        bank, sr, base = build_bank(score)

        export_mode = data.get("export_mode", "interp")
        time_from   = float(data.get("time_from", 0) or 0)
        time_to     = float(data.get("time_to", 0) or 0)

        source = base   # the loaded recording: reference for "match source"
        if export_mode == "raw":
            # The source alone — no events, no golem
            mix = base.copy() if base is not None else np.zeros(sr, dtype=np.float32)
        else:
            # Same render path as /preview. score_only drops the base track:
            # events (+ golem) over silence of the same length.
            if config.get("engine") == "v2":
                from src.interpreter import interpret
                events, _state_trace = interpret(score, config, return_trace=True)
                score['_state_trace'] = _state_trace
            else:
                events = get_events(score)
            if export_mode == "score_only" and base is not None:
                base = np.zeros_like(base)
            mix, _tm = render_mix(score, bank, events, sr, base)

        # Loudness on the WHOLE render, before the range trim, so exporting
        # part of the piece gives it the same level it has in the whole.
        mix, loudness = finish(mix, sr, source=source, **options_from(data.get("loudness")))

        # Time range trim
        if time_to > time_from and time_from >= 0:
            s_from = max(0, int(time_from * sr))
            s_to   = min(len(mix), int(time_to * sr))
            if s_to > s_from:
                mix = mix[s_from:s_to]

        # Build output path — user-chosen path wins, then name, then auto-generated
        audio_fmt = data.get("audio_format", "wav24")
        fmt_ext   = _AUDIO_FORMATS.get(audio_fmt, _AUDIO_FORMATS['wav24'])['ext']
        user_path = (data.get("out_path") or "").strip()
        user_name = (data.get("out_name") or "").strip()
        out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        if user_path:
            # User chose a full path via the file browser
            out_path = os.path.splitext(os.path.abspath(user_path))[0] + fmt_ext
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
        elif user_name:
            os.makedirs(out_dir, exist_ok=True)
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in user_name)
            out_path = os.path.abspath(os.path.join(out_dir, os.path.splitext(safe)[0] + fmt_ext))
        else:
            os.makedirs(out_dir, exist_ok=True)
            stem = os.path.splitext(os.path.basename(score_path if not composer else path))[0]
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            out_path = os.path.abspath(os.path.join(
                out_dir, f"{'composer' if composer else 'interp'}_{stem}_{ts}{fmt_ext}"))
        out_path = _write_audio(out_path, mix, sr, audio_fmt)
        return jsonify({"path": out_path, "name": os.path.basename(out_path), "loudness": loudness,
                        "duration": round(len(mix) / sr, 3)})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/export", methods=["POST"])
def export():
    data  = request.get_json()
    v2cfg = data.get("_config")

    output_path = data.get("output_path", "")
    if output_path and os.path.isabs(output_path):
        out_path = output_path
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        name = data.get("_name", "untitled")
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip() or "untitled"
        os.makedirs(SCORES_DIR, exist_ok=True)
        out_path = os.path.join(SCORES_DIR, f"{safe_name}.yaml")

    # Build clean score dict (exclude editor metadata keys and output_path)
    clean = {k: v for k, v in data.items() if not k.startswith("_") and k != "output_path"}
    # Attach V2 config block if provided
    if v2cfg:
        clean["_v2_config"] = v2cfg

    yaml_str = yaml.dump(clean, default_flow_style=False, allow_unicode=True, sort_keys=False)

    with open(out_path, "w") as f:
        f.write(yaml_str)

    return jsonify({"path": out_path, "yaml": yaml_str})


@app.route("/image")
def serve_image():
    path = request.args.get("path", "")
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".webp": "image/webp"}.get(ext, "image/png")
    directory = os.path.dirname(os.path.abspath(path))
    return send_from_directory(directory, os.path.basename(path), mimetype=mime)


@app.route("/separate", methods=["POST"])
def separate():
    data         = request.get_json()
    path         = data.get("path", "")
    method       = data.get("method", "hpss")       # "hpss" | "nmf" | "both"
    n_components = int(data.get("n_components", 3))
    nmf_mode     = data.get("nmf_mode", "softmask") # "softmask" | "naive"
    from_t       = data.get("from_t")               # optional start time (s)
    to_t         = data.get("to_t")                 # optional end time (s)

    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    try:
        import librosa
        load_kwargs = {"sr": None, "mono": False}   # keep the channels
        if from_t is not None:
            load_kwargs["offset"] = float(from_t)
        if to_t is not None and from_t is not None:
            load_kwargs["duration"] = float(to_t) - float(from_t)
        elif to_t is not None:
            load_kwargs["duration"] = float(to_t)
        audio, sr_lib = librosa.load(path, **load_kwargs)
        audio = np.atleast_2d(audio)[:2]              # (channels, samples), L/R at most
        n_samples = audio.shape[-1]
        base_name = os.path.splitext(os.path.basename(path))[0]
        # Method-specific subdirectory prevents overwriting across different stemize runs
        out_dir   = os.path.join(os.path.dirname(os.path.abspath(path)),
                                 base_name + "_stems", method)
        os.makedirs(out_dir, exist_ok=True)

        stems = []

        def _save(name, y):
            # y is (channels, samples); files are (frames, channels)
            p = os.path.join(out_dir, f"{name}.wav")
            sf.write(p, np.asarray(y, dtype=np.float32).T, sr_lib, subtype='PCM_24')
            stems.append({"name": name, "path": p})

        # Stereo: every method analyses ONE reference magnitude (the channels'
        # average) and applies the same mask to each channel's spectrum, so a
        # stem keeps each sound's left/right placement, and stems of one sound
        # line up across channels (separate per-channel NMF would number its
        # components differently on each side). Mono reduces to the usual
        # single-channel separation.
        D     = librosa.stft(audio)                   # (channels, freq, frames)
        S_ref = np.abs(D).mean(axis=0)                # (freq, frames)

        def _istft(spec):
            return librosa.istft(spec, length=n_samples)

        if method in ("hpss", "both"):
            mask_h, mask_p = librosa.decompose.hpss(S_ref, mask=True)
            _save("harmonic",   _istft(D * mask_h))
            _save("percussive", _istft(D * mask_p))

        if method in ("nmf", "both"):
            comps, acts = librosa.decompose.decompose(S_ref, n_components=n_components, sort=True)
            components  = [np.outer(comps[:, i], acts[i, :]) for i in range(n_components)]
            if nmf_mode == "softmask":
                S_total = np.maximum(sum(components), 1e-10)
                for i, S_i in enumerate(components):
                    _save(f"nmf_{i+1}", _istft((S_i / S_total) * D))
            else:  # naive: component magnitude with each channel's own phase,
                   # shared out by that channel's share of the reference level
                share = np.abs(D) / np.maximum(S_ref, 1e-10)
                phase = np.exp(1j * np.angle(D))
                for i, S_i in enumerate(components):
                    _save(f"nmf_{i+1}", _istft(S_i * share * phase))

        if method == "freqband":
            bands = data.get("bands", [])
            if not bands:
                return jsonify({"error": "No frequency bands defined"}), 400
            freqs = librosa.fft_frequencies(sr=sr_lib, n_fft=2048)   # librosa.stft default
            for band in bands:
                low_hz  = float(band.get("low",  0))
                high_hz = float(band.get("high", sr_lib / 2))
                name    = str(band.get("name", "")).strip() or f"band_{int(low_hz)}_{int(high_hz)}"
                mask    = ((freqs >= low_hz) & (freqs <= high_hz)).reshape(-1, 1).astype(np.float32)
                _save(name, _istft(D * mask))

        return jsonify({"stems": stems})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/load_yaml", methods=["POST"])
def load_yaml_route():
    data = request.get_json()
    path = data.get("path", "")
    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404
    try:
        with open(path) as f:
            score = yaml.safe_load(f) or {}
        return jsonify({"score": score})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/save_interpretation", methods=["POST"])
def save_interpretation():
    data = request.get_json()
    name = data.get("name", "untitled_interp")
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip() or "untitled_interp"
    os.makedirs(INTERPS_DIR, exist_ok=True)
    out_path = os.path.join(INTERPS_DIR, f"{safe_name}.yaml")
    payload = {
        "score_path": data.get("score_path", ""),
        "golems": data.get("golems", []),
        "v2config": data.get("v2config", {}),
        "mix_dims": data.get("mix_dims", ["gain_db"]),
    }
    with open(out_path, "w") as f:
        yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return jsonify({"path": out_path})


@app.route("/load_interpretation", methods=["POST"])
def load_interpretation():
    data = request.get_json()
    path = data.get("path", "")
    if not os.path.exists(path):
        return jsonify({"error": f"Not found: {path}"}), 404
    try:
        with open(path) as f:
            interp = yaml.safe_load(f) or {}
        return jsonify({"interp": interp})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/trace", methods=["POST"])
def trace():
    data       = request.get_json()
    score_path = data.get("score_path", "")
    interp     = data.get("interp", {})

    if not score_path or not os.path.exists(score_path):
        return jsonify({"error": f"Score not found: {score_path}"}), 404
    try:
        with open(score_path) as f:
            score = yaml.safe_load(f) or {}
        if "golems" in interp:
            score["golems"] = interp["golems"]

        config = _load_server_config(data.get("_config") or interp.get("v2config"))
        config["engine"] = "v2"
        seed_everything(config)
        resolve_score(score)
        score = _apply_phrase_tempo(score)

        from src.interpreter import interpret
        _, trace_data = interpret(score, config, return_trace=True)

        total_dur = max((e["t"] for e in trace_data), default=1.0)

        seen = set()
        markings = []
        for entry in trace_data:
            key = (round(entry["t"], 3), entry["marking"])
            if entry["marking"] and key not in seen:
                seen.add(key)
                markings.append({"t": entry["t"], "marking": entry["marking"]})

        return jsonify({
            "trace":      trace_data,
            "total_dur":  total_dur,
            "dimensions": list(DIM_NAMES),
            "markings":   markings,
            "effective_seed": (config.get("v2") or {}).get("_effective_seed"),
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/multitrace", methods=["POST"])
def multitrace():
    data       = request.get_json()
    score_path = data.get("score_path", "")
    interp     = data.get("interp", {})
    n_walks    = min(int(data.get("n_walks", 5)), 20)

    if not score_path or not os.path.exists(score_path):
        return jsonify({"error": f"Score not found: {score_path}"}), 404
    try:
        with open(score_path) as f:
            score = yaml.safe_load(f) or {}
        if "golems" in interp:
            score["golems"] = interp["golems"]

        base_config = _load_server_config(data.get("_config") or interp.get("v2config"))
        base_config["engine"] = "v2"
        score = _apply_phrase_tempo(score)
        resolve_score(score)

        from src.interpreter import interpret

        walks = []
        markings_seen = set()
        markings = []
        total_dur = 1.0

        for seed in range(n_walks):
            # v2.seed takes priority over seed, so set it there; copy the v2
            # dict so walks don't share state.
            cfg = dict(base_config)
            cfg["v2"] = {**(base_config.get("v2") or {}), "seed": seed}
            _, trace_data = interpret(score, cfg, return_trace=True)
            walks.append(trace_data)
            if trace_data:
                total_dur = max(total_dur, max(e["t"] for e in trace_data))
            for entry in trace_data:
                key = (round(entry["t"], 3), entry["marking"])
                if entry["marking"] and key not in markings_seen:
                    markings_seen.add(key)
                    markings.append({"t": entry["t"], "marking": entry["marking"]})

        markings.sort(key=lambda m: m["t"])
        return jsonify({
            "walks":      walks,
            "total_dur":  total_dur,
            "dimensions": list(DIM_NAMES),
            "markings":   markings,
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


_TABLE_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "transition_table.yaml")

# Built-in character names — never overwritten or deleted via the API
_KALMAN_BUILTIN = {'dramatic', 'lyrical', 'sparse', 'turbulent'}
_RW_BUILTIN     = {'rw_free', 'rw_drift_up', 'rw_reverting'}


def _load_table() -> dict:
    if os.path.exists(_TABLE_PATH):
        with open(_TABLE_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_table(table: dict):
    with open(_TABLE_PATH, "w") as f:
        yaml.dump(table, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@app.route("/characters", methods=["GET"])
def get_characters():
    table = _load_table()
    # Return only user-defined (non-builtin) characters
    kalman_chars = {k: v for k, v in (table.get("characters") or {}).items()
                    if k not in _KALMAN_BUILTIN}
    rw_chars     = {k: v for k, v in (table.get("rw_characters") or {}).items()
                    if k not in _RW_BUILTIN}
    return jsonify({"kalman": kalman_chars, "random_walk": rw_chars})


@app.route("/characters", methods=["POST"])
def save_character():
    data    = request.get_json()
    name    = (data.get("name") or "").strip()
    ctype   = data.get("type", "kalman")   # "kalman" | "random_walk"
    params  = data.get("params", {})
    delete  = data.get("delete", False)

    if not name or not name.replace("_", "").isalnum():
        return jsonify({"error": "Invalid character name (alphanumeric + _ only)"}), 400

    # Disallow overwriting builtins
    if ctype == "kalman"      and name in _KALMAN_BUILTIN:
        return jsonify({"error": f"'{name}' is a built-in character and cannot be modified"}), 400
    if ctype == "random_walk" and name in _RW_BUILTIN:
        return jsonify({"error": f"'{name}' is a built-in RW character and cannot be modified"}), 400

    table    = _load_table()
    section  = "characters" if ctype == "kalman" else "rw_characters"
    if section not in table or not isinstance(table[section], dict):
        table[section] = {}

    if delete:
        table[section].pop(name, None)
    else:
        if not params:
            return jsonify({"error": "params required"}), 400
        table[section][name] = params

    _save_table(table)
    return jsonify({"ok": True})


@app.route("/browse")
def browse():
    path = request.args.get("path", "")
    if not path:
        path = os.path.expanduser("~")
    path = os.path.abspath(path)
    # Walk up until we find an existing directory
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            path = os.path.expanduser("~")
            break
        path = parent
    try:
        entries = os.listdir(path)
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403
    dirs  = sorted([e for e in entries if os.path.isdir(os.path.join(path, e))  and not e.startswith('.')], key=str.lower)
    files = sorted([e for e in entries if os.path.isfile(os.path.join(path, e)) and not e.startswith('.')], key=str.lower)
    parent = os.path.dirname(path)
    return jsonify({
        "current": path,
        "parent":  parent if parent != path else None,
        "dirs":    dirs,
        "files":   files,
    })


@app.route("/plugins")
def list_plugins():
    from plugins import load_plugins
    plugs = load_plugins()
    return jsonify([{
        "type":   k,
        "name":   v.NAME,
        "group":  v.GROUP,
        "params": v.PARAMS,
    } for k, v in plugs.items()])


if __name__ == "__main__":
    # threaded=True so concurrent batch uploads during a concerto encode don't
    # serialise behind each other while one ffmpeg write is briefly blocked.
    # Bound to 127.0.0.1 only. The Werkzeug debugger (an interactive Python
    # console on error pages) is opt-in: OPUS_DEBUG=1 python server.py
    app.run(host="127.0.0.1",
            port=int(os.environ.get("OPUS_PORT", 5000)),
            debug=os.environ.get("OPUS_DEBUG") == "1",
            use_reloader=False, threaded=True)
