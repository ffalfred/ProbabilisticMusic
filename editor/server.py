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
from src.mixer         import mix_events, normalise, _stretch_mix_by_tempo
from src.envelope      import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.renderer      import _apply_phrase_tempo, _remap_dynamics, _remap_phrases, _remap_events
from src.fx            import apply_section_fx, apply_global_fx

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

    return {"waveform": peaks, "duration": duration, "frame": frame}


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
        # Normalize dynamics: YAML uses 'marking', backend uses 'mark'
        for d in score.get('dynamics', []):
            if 'marking' in d and 'mark' not in d:
                d['mark'] = d.pop('marking')
        # Auto-derive audio path from score if not given
        if not path:
            path = score.get("base_track", "")

    # Merge interpretation block (golems + v2config + mix_dims)
    interp = data.get("interp", {})
    if interp.get("golems"):
        score["golems"] = interp["golems"]
    mix_dims = data.get("score", {}).get("mix_dims") or interp.get("mix_dims")
    if mix_dims:
        score["mix_dims"] = mix_dims

    config = _load_server_config(data.get("_config") or interp.get("v2config"))

    if not path:
        return jsonify({"error": "Audio file path required"}), 400
    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        score["base_track"] = path
        score = _apply_phrase_tempo(score)
        bank, sr, base = build_bank(score)

        if config.get("engine") == "v2":
            from src.interpreter import interpret
            events, _state_trace = interpret(score, config, return_trace=True)
            score['_state_trace'] = _state_trace
            # per-dim toggles for state-to-base modulation
        else:
            events = get_events(score)

        # 1. Mix in score time
        mix = mix_events(events, bank, sr, score, base)

        # 2. Stretch by tempo ranges (length may change). Returns score→real map.
        mix, tempo_map = _stretch_mix_by_tempo(mix, sr, score.get('tempo', []))

        # 3. FX after stretch, in real time
        mix = apply_section_fx(mix, sr, score.get('fx_sections', []))
        mix = apply_global_fx(mix, sr, score.get('fx_global', []))

        # 4. Envelopes (remap score-time positions → real time)
        _golem_active = bool(score.get('_state_trace')) and bool(score.get('golems'))
        if not _golem_active:
            dynamics = score.get('dynamics', [])
            if dynamics:
                mix *= build_dynamics_envelope(len(mix), sr, _remap_dynamics(dynamics, tempo_map))
            phrases = score.get('phrases', [])
            if phrases:
                mix *= build_phrase_envelope(len(mix), sr, _remap_phrases(phrases, tempo_map))
        dk = score.get('duck_key')
        if dk and dk.get('enabled') and dk.get('key') and events:
            mix *= build_duck_envelope(
                len(mix), sr, _remap_events(events, tempo_map),
                trigger_fn=lambda ev: ev.get('sample') == dk['key'],
                amount_db=dk.get('amount_db', -10.0),
                attack=dk.get('attack', 0.01),
                release=dk.get('release', 0.3),
            )
        mix = normalise(mix)
        sf.write(PREVIEW_TMP, mix, sr)
        return jsonify({
            "url": f"/preview_audio?v={int(_time.time())}",
            "tempo_map": tempo_map,
            "duration_real": float(len(mix) / sr),
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
_concerto_next      = 0     # next expected frame index WITHIN CURRENT SEGMENT
_concerto_buf       = {}    # out-of-order frame buffer {index: raw_bytes}
_concerto_segments  = []    # list of per-segment .mkv paths (for concat)
_concerto_w         = 0     # render width  (remembered across segment starts)
_concerto_h         = 0     # render height
_concerto_fps       = 60    # render fps
# Lock around _concerto_buf / _concerto_next / stdin writes — Flask is now
# threaded=True so multiple /concerto_frames requests can land in parallel.
_concerto_lock      = threading.Lock()

# Two quality presets (from Toke's ffmpeg research)
# 4 presets optimised for BrightSign gallery playback
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
    # A2: Top Quality HEVC 10-bit + lossless WAV (TS) — SLOW
    'a2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'veryslow', '-crf', '14',
            '-x265-params', 'profile=main10:ref=6:bframes=8:rc-lookahead=60',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'pcm_s16le',
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
    # B2: High Quality 4K HEVC 10-bit + lossless WAV (TS) — 5-10× faster than A2
    'b2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'medium', '-crf', '16',
            '-x265-params', 'profile=main10:ref=4:bframes=4',
            '-pix_fmt', 'yuv420p10le',
            '-c:a', 'pcm_s16le',
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
    # T2: Test HEVC 8-bit + lossless WAV (TS)
    't2': {
        'ext': '.ts',
        'args': [
            '-c:v', 'libx265', '-preset', 'fast', '-crf', '22',
            '-x265-params', 'profile=main',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'pcm_s16le',
            '-f', 'mpegts',
        ],
    },
}

def _kill_concerto_ffmpeg():
    """Kill any active ffmpeg subprocess and clear the global. Caller must hold _concerto_lock."""
    global _concerto_ffmpeg
    if _concerto_ffmpeg is None:
        return
    try:
        try: _concerto_ffmpeg.stdin.close()
        except Exception: pass
        try: _concerto_ffmpeg.kill()
        except Exception: pass
        try: _concerto_ffmpeg.wait(timeout=5)
        except Exception: pass
    finally:
        _concerto_ffmpeg = None


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

    data       = request.get_json()
    seg_index  = int(data.get('segment_index', 0))

    # Take the lock for the whole start sequence so we cannot race with a
    # late finish_segment.wait() from a previous run nulling out our fresh
    # _concerto_ffmpeg, or with concurrent /concerto_frames writes touching
    # _concerto_buf / _concerto_next while we're resetting them.
    with _concerto_lock:
        # Per-segment state always resets
        _concerto_next = 0
        _concerto_buf  = {}

        if seg_index == 0:
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
            _concerto_segments  = []
        else:
            # Resuming with a new segment — require prior init
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
            if a in ('-c:a', '-b:a', '-f'):
                skip_next = True
                continue
            if a in ('-movflags', '+faststart'):
                continue
            filtered.append(a)

        seg_path = _concerto_out + f'.seg_{seg_index:04d}.mkv'

        # Input is a stream of concatenated JPEG frames (MJPEG) produced by the
        # browser via canvas.toBlob('image/jpeg'). ffmpeg's image2pipe demuxer
        # parses JPEG markers to find frame boundaries, so we don't need to
        # specify -s (size is in the JPEG header). This replaces the previous
        # raw RGBA pipe (~33 MB/frame at 4K) with ~1-3 MB/frame — 10-30× less
        # data crossing browser → network → server → ffmpeg, with quality loss
        # negligible at q=0.95 since the output is re-encoded to HEVC anyway.
        cmd = [
            'ffmpeg', '-y',
            '-f', 'image2pipe', '-c:v', 'mjpeg',
            '-framerate', str(_concerto_fps),
            '-i', 'pipe:0',
            '-an',                          # no audio in segment encode
            *filtered,
            seg_path,
        ]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.PIPE)
        except Exception as e:
            _concerto_ffmpeg = None
            return jsonify({"error": f"ffmpeg spawn failed: {e}"}), 500

        # Catch immediate ffmpeg-startup failures (bad codec, missing binary,
        # etc.) — Popen returns even if ffmpeg exits in the next millisecond.
        # A tiny grace period is enough; we don't want to block the caller.
        _time.sleep(0.05)
        rc = proc.poll()
        if rc is not None:
            err = b''
            try: err = proc.stderr.read()
            except Exception: pass
            _concerto_ffmpeg = None
            tail = err.decode('utf-8', errors='replace')[-500:] if err else ''
            return jsonify({"error": f"ffmpeg exited immediately (rc={rc}): {tail}"}), 500

        _concerto_ffmpeg = proc
        # Track segment for later concat (avoid duplicates if the browser retries)
        if seg_path not in _concerto_segments:
            _concerto_segments.append(seg_path)
        return jsonify({"ok": True, "segment_index": seg_index})


@app.route("/concerto_finish_segment", methods=["POST"])
def concerto_finish_segment():
    """Close the current segment's ffmpeg subprocess and wait for it to flush.

    Keeps overall encode state (output path, preset, segments list) intact so
    the next /concerto_start call can spawn the next segment.
    """
    global _concerto_ffmpeg
    # Snapshot the proc under the lock and clear the global immediately so
    # concurrent /concerto_frames see "no active render" and don't write to
    # a closing pipe. The subsequent .wait() can then run outside the lock.
    with _concerto_lock:
        proc = _concerto_ffmpeg
        if proc is None:
            # Diagnostic detail: distinguish between "never started" and
            # "already finished" so the browser can tell what's happening.
            seg_count = len(_concerto_segments)
            has_state = bool(_concerto_preset and _concerto_out)
            return jsonify({
                "error": "No active concerto segment",
                "segments_done": seg_count,
                "init_state_present": has_state,
            }), 400
        _concerto_ffmpeg = None
        try:
            proc.stdin.close()
        except Exception:
            pass

    # Outside the lock: ffmpeg flush can take seconds (HEVC encoder cleanup),
    # we don't want to hold the lock that long.
    try:
        seg_stderr = proc.stderr.read() if proc.stderr else b''
        proc.wait(timeout=300)
        if seg_stderr:
            tail = seg_stderr.decode('utf-8', errors='replace')[-300:]
            print(f"[concerto seg {len(_concerto_segments) - 1} stderr]", tail)
        return jsonify({"ok": True, "segments_done": len(_concerto_segments)})
    except Exception as e:
        try: proc.kill()
        except Exception: pass
        return jsonify({"error": str(e)}), 500

@app.route("/concerto_frame", methods=["POST"])
def concerto_frame():
    global _concerto_ffmpeg, _concerto_next, _concerto_buf
    if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
        return jsonify({"error": "No active concerto render"}), 400
    frame_blob = request.files.get('frame')
    if not frame_blob:
        return jsonify({"error": "No frame data"}), 400
    try:
        # Read body OUTSIDE the lock so concurrent uploads can fetch in parallel
        idx_form = request.form.get('index')
        raw      = frame_blob.read()
        with _concerto_lock:
            if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
                return jsonify({"error": "No active concerto render"}), 400
            idx = int(idx_form) if idx_form is not None else _concerto_next
            _concerto_buf[idx] = raw
            while _concerto_next in _concerto_buf:
                _concerto_ffmpeg.stdin.write(_concerto_buf.pop(_concerto_next))
                _concerto_next += 1
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/concerto_frames", methods=["POST"])
def concerto_frames():
    """Batch frame upload — multiple JPEG frames packed in one request.

    The request body is the concatenation of `count` JPEG files. The form
    field `lengths` is a comma-separated list of per-frame byte counts so we
    can split the blob (JPEGs are variable-size). For backward compat with
    fixed-size raw frames, if `lengths` is omitted we assume equal sizes.
    """
    global _concerto_ffmpeg, _concerto_next, _concerto_buf
    if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
        return jsonify({"error": "No active concerto render"}), 400
    batch_blob = request.files.get('frames')
    if not batch_blob:
        return jsonify({"error": "No frame data"}), 400
    try:
        # Read body OUTSIDE the lock so concurrent uploads can fetch in parallel
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
            # Backward compat: fixed-size frames
            fsize   = len(raw_all) // count if count > 0 else len(raw_all)
            lengths = [fsize] * count

        with _concerto_lock:
            if not _concerto_ffmpeg or _concerto_ffmpeg.stdin.closed:
                return jsonify({"error": "No active concerto render"}), 400
            start_idx = int(start_idx_form) if start_idx_form is not None else _concerto_next
            offset = 0
            for i, length in enumerate(lengths):
                _concerto_buf[start_idx + i] = raw_all[offset : offset + length]
                offset += length
            # Flush in order
            while _concerto_next in _concerto_buf:
                _concerto_ffmpeg.stdin.write(_concerto_buf.pop(_concerto_next))
                _concerto_next += 1
        return jsonify({"ok": True})
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
            audio_args = []
            args = _concerto_preset['args']
            i = 0
            while i < len(args):
                if args[i] in ('-c:a', '-b:a'):
                    audio_args.extend([args[i], args[i + 1]])
                    i += 2
                else:
                    i += 1
            if not audio_args:
                audio_args = ['-c:a', 'copy']

            fmt_args = []
            if '-f' in args:
                fi = args.index('-f')
                fmt_args = ['-f', args[fi + 1]]

            audio_trim = []
            if _concerto_time_from > 0 or _concerto_time_to > 0:
                if _concerto_time_from > 0:
                    audio_trim = ['-ss', str(_concerto_time_from)]
                if _concerto_time_to > _concerto_time_from:
                    audio_trim += ['-t', str(_concerto_time_to - _concerto_time_from)]

            mux_cmd = [
                'ffmpeg', '-y',
                '-i', _concerto_video_tmp,
                *audio_trim,
                '-i', PREVIEW_TMP,
                '-c:v', 'copy',
                *audio_args,
                *(['-movflags', '+faststart'] if '-movflags' in args else []),
                *fmt_args,
                '-shortest',
                _concerto_out,
            ]
            subprocess.run(mux_cmd, check=True, capture_output=True, timeout=120)

        # Clean up temps: stitched video tmp + any leftover segment files
        if os.path.exists(_concerto_video_tmp):
            try: os.remove(_concerto_video_tmp)
            except OSError: pass
        for seg in _concerto_segments:
            if os.path.exists(seg):
                try: os.remove(seg)
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


@app.route("/export_interp_wav", methods=["POST"])
def export_interp_wav():
    """Render the interpreter mix and save to ProbabilisticMusic/output/."""
    import datetime
    data = request.get_json()
    path = data.get("path", "")
    score_path = data.get("score_path")
    if not score_path or not os.path.exists(score_path):
        return jsonify({"error": f"Score not found: {score_path}"}), 404
    try:
        with open(score_path) as f:
            score = yaml.safe_load(f) or {}
        for d in score.get('dynamics', []):
            if 'marking' in d and 'mark' not in d:
                d['mark'] = d.pop('marking')
        if not path:
            path = score.get("base_track", "")
        if not path or not os.path.exists(path):
            return jsonify({"error": "Audio file path required/not found"}), 404

        interp = data.get("interp", {})
        if interp.get("golems"):
            score["golems"] = interp["golems"]
        config = _load_server_config(interp.get("v2config"))
        score["base_track"] = path
        score = _apply_phrase_tempo(score)
        bank, sr, base = build_bank(score)

        export_mode = data.get("export_mode", "interp")
        time_from   = float(data.get("time_from", 0) or 0)
        time_to     = float(data.get("time_to", 0) or 0)

        from src.interpreter import interpret

        if export_mode == "raw":
            # Raw base — no events, no golem
            mix = base.copy() if base is not None else np.zeros(sr, dtype=np.float32)
        elif export_mode == "score_only":
            # Events + golem, no base (events_only mix mode)
            score['mix_mode'] = 'events_only'
            events, _state_trace = interpret(score, config, return_trace=True)
            score['_state_trace'] = _state_trace
            mix = mix_events(events, bank, sr, score, base)
        else:
            # Full interpreter render (base + events + golem)
            events, _state_trace = interpret(score, config, return_trace=True)
            score['_state_trace'] = _state_trace
            mix = mix_events(events, bank, sr, score, base)

        # Apply tempo stretch so interpreter export matches preview behavior
        if export_mode != "raw":
            mix, _tm = _stretch_mix_by_tempo(mix, sr, score.get('tempo', []))
        mix = normalise(mix)

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
        if user_path:
            # User chose a full path via the file browser
            out_path = os.path.abspath(user_path)
            base_p, _ = os.path.splitext(out_path)
            out_path = base_p + fmt_ext
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            out_name = os.path.basename(out_path)
        elif user_name:
            out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
            os.makedirs(out_dir, exist_ok=True)
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in user_name)
            base_n, _ = os.path.splitext(safe)
            safe = base_n + fmt_ext
            out_name = safe
            out_path = os.path.abspath(os.path.join(out_dir, out_name))
        else:
            out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
            os.makedirs(out_dir, exist_ok=True)
            score_name = os.path.splitext(os.path.basename(score_path))[0]
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            out_name = f"interp_{score_name}_{ts}{fmt_ext}"
            out_path = os.path.abspath(os.path.join(out_dir, out_name))
        out_path = _write_audio(out_path, mix, sr, audio_fmt)
        out_name = os.path.basename(out_path)
        return jsonify({"path": out_path, "name": out_name})
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


@app.route("/export_mp4", methods=["POST"])
def export_mp4():
    data        = request.get_json()
    audio_path  = data["audioPath"]
    image_path  = data["imagePath"]
    score_start = float(data.get("scoreStart", 0))
    score_end   = float(data.get("scoreEnd", 0))
    fps         = int(data.get("fps", 30))
    out_h       = int(data.get("height", 540))
    out_w       = int(data.get("width", 960))

    if not os.path.exists(audio_path) or not os.path.exists(image_path):
        return jsonify({"error": "File not found"}), 404

    dur = score_end - score_start
    if dur <= 0:
        return jsonify({"error": "scoreEnd must be > scoreStart"}), 400

    output_path = data.get("output_path", "")
    if output_path and os.path.isabs(output_path):
        out_path = output_path
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        out_name  = data.get("name", "score_video")
        safe_name = "".join(c for c in out_name if c.isalnum() or c in "-_").strip() or "score_video"
        os.makedirs(SCORES_DIR, exist_ok=True)
        out_path  = os.path.join(SCORES_DIR, f"{safe_name}.mp4")

    try:
        from PIL import Image as PILImage, ImageDraw
        img = PILImage.open(image_path).convert("RGB")
        scale = out_h / img.height
        img = img.resize((int(img.width * scale), out_h), PILImage.LANCZOS)
        img_w = img.width

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{out_w}x{out_h}", "-r", str(fps),
            "-i", "pipe:0",
            "-i", audio_path,
            "-ss", str(score_start), "-t", str(dur),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            out_path
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        n_frames = int(dur * fps)
        for i in range(n_frames):
            t = score_start + i / fps
            cursor_display = (t - score_start) / dur * img_w
            scroll_left = int(cursor_display - out_w / 2)
            src_x  = max(0, scroll_left)
            src_x2 = min(img_w, scroll_left + out_w)
            crop  = img.crop((src_x, 0, src_x2, out_h))
            frame = PILImage.new("RGB", (out_w, out_h), (17, 17, 17))
            frame.paste(crop, (src_x - scroll_left, 0))
            draw = ImageDraw.Draw(frame)
            cx = out_w // 2
            draw.line([(cx, 0), (cx, out_h)], fill=(255, 50, 50), width=2)
            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            return jsonify({"error": "ffmpeg failed"}), 500
        return jsonify({"path": out_path})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


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
        load_kwargs = {"sr": None, "mono": True}
        if from_t is not None:
            load_kwargs["offset"] = float(from_t)
        if to_t is not None and from_t is not None:
            load_kwargs["duration"] = float(to_t) - float(from_t)
        elif to_t is not None:
            load_kwargs["duration"] = float(to_t)
        audio, sr_lib = librosa.load(path, **load_kwargs)
        base_name = os.path.splitext(os.path.basename(path))[0]
        # Method-specific subdirectory prevents overwriting across different stemize runs
        out_dir   = os.path.join(os.path.dirname(os.path.abspath(path)),
                                 base_name + "_stems", method)
        os.makedirs(out_dir, exist_ok=True)

        stems = []

        def _save(name, y):
            p = os.path.join(out_dir, f"{name}.wav")
            sf.write(p, y.astype(np.float32), sr_lib, subtype='PCM_24')
            stems.append({"name": name, "path": p})

        if method in ("hpss", "both"):
            harmonic, percussive = librosa.effects.hpss(audio)
            _save("harmonic", harmonic)
            _save("percussive", percussive)

        if method in ("nmf", "both"):
            D     = librosa.stft(audio)
            S     = np.abs(D)
            comps, acts = librosa.decompose.decompose(S, n_components=n_components, sort=True)
            components  = [np.outer(comps[:, i], acts[i, :]) for i in range(n_components)]
            if nmf_mode == "softmask":
                S_total = np.maximum(sum(components), 1e-10)
                for i, S_i in enumerate(components):
                    y_i = librosa.istft((S_i / S_total) * D)
                    _save(f"nmf_{i+1}", y_i)
            else:  # naive
                phase = np.angle(D)
                for i, S_i in enumerate(components):
                    y_i = librosa.istft(S_i * np.exp(1j * phase))
                    _save(f"nmf_{i+1}", y_i)

        if method == "freqband":
            bands = data.get("bands", [])
            if not bands:
                return jsonify({"error": "No frequency bands defined"}), 400
            n_fft = 2048
            D     = librosa.stft(audio, n_fft=n_fft)
            freqs = librosa.fft_frequencies(sr=sr_lib, n_fft=n_fft)
            for band in bands:
                low_hz  = float(band.get("low",  0))
                high_hz = float(band.get("high", sr_lib / 2))
                name    = str(band.get("name", "")).strip() or f"band_{int(low_hz)}_{int(high_hz)}"
                mask    = ((freqs >= low_hz) & (freqs <= high_hz)).reshape(-1, 1).astype(np.float32)
                y_band  = librosa.istft(D * mask, length=len(audio))
                _save(name, y_band)

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
        if interp.get("golems"):
            score["golems"] = interp["golems"]

        config = _load_server_config(data.get("_config") or interp.get("v2config"))
        config["engine"] = "v2"

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
            "dimensions": ["gain_db", "brightness", "timing_offset_ms", "attack_shape", "reverb_wet"],
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
        if interp.get("golems"):
            score["golems"] = interp["golems"]

        base_config = _load_server_config(data.get("_config") or interp.get("v2config"))
        base_config["engine"] = "v2"
        score = _apply_phrase_tempo(score)

        from src.interpreter import interpret

        walks = []
        markings_seen = set()
        markings = []
        total_dur = 1.0

        for seed in range(n_walks):
            cfg = dict(base_config)
            cfg["seed"] = seed
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
            "dimensions": ["gain_db", "brightness", "timing_offset_ms", "attack_shape", "reverb_wet"],
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
    app.run(port=5000, debug=True, threaded=True)
