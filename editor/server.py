import os
import sys
import base64
import tempfile
import subprocess
import json
import time as _time

import numpy as np
import soundfile as sf
import yaml
from flask import Flask, request, jsonify, send_from_directory

# Allow importing src.* and v2.* from the parent beta_interpreter directory
_BETA_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_BETA_DIR))
from src.sample_engine import build_bank
from src.scheduler     import get_events
from src.mixer         import mix_events, normalise
from src.envelope      import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.renderer      import _apply_phrase_tempo

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def _load_server_config(override: dict = None) -> dict:
    """Load config.yaml defaults, then apply any per-request override."""
    cfg = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
    if override:
        cfg.update(override)
    return cfg

PREVIEW_TMP = os.path.join(tempfile.gettempdir(), "opacity_toke_preview.wav")

app = Flask(__name__, static_folder="static", static_url_path="")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR = os.path.join(BASE_DIR, "..", "scores")


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
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-vn", "-ar", "44100", "-ac", "1", tmp_wav.name],
                capture_output=True, check=True
            )
            audio_data, samplerate = sf.read(tmp_wav.name, always_2d=True)
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
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-vframes", "1", "-q:v", "2", tmp_path],
                capture_output=True, check=True
            )
            with open(tmp_path, "rb") as f:
                frame_bytes = f.read()
            frame = "data:image/png;base64," + base64.b64encode(frame_bytes).decode()
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
    config = _load_server_config(data.get("_config"))

    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        score["base_track"] = path
        score = _apply_phrase_tempo(score)
        bank, sr, base = build_bank(score)

        if config.get("engine") == "v2":
            from v2.interpreter import interpret
            events = interpret(score, config)
        else:
            events = get_events(score)

        mix = mix_events(events, bank, sr, score, base)
        dynamics = score.get('dynamics', [])
        if dynamics:
            mix *= build_dynamics_envelope(len(mix), sr, dynamics)
        phrases = score.get('phrases', [])
        if phrases:
            mix *= build_phrase_envelope(len(mix), sr, phrases)
        dk = score.get('duck_key')
        if dk and dk.get('enabled') and dk.get('key') and events:
            mix *= build_duck_envelope(
                len(mix), sr, events,
                trigger_fn=lambda ev: ev.get('sample') == dk['key'],
                amount_db=dk.get('amount_db', -10.0),
                attack=dk.get('attack', 0.01),
                release=dk.get('release', 0.3),
                tempo_ranges=score.get('tempo', []),
            )
        mix = normalise(mix)
        sf.write(PREVIEW_TMP, mix, sr)
        return jsonify({"url": f"/preview_audio?v={int(_time.time())}"})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/preview_audio")
def preview_audio():
    if not os.path.exists(PREVIEW_TMP):
        return jsonify({"error": "No preview rendered yet"}), 404
    directory = os.path.dirname(PREVIEW_TMP)
    filename  = os.path.basename(PREVIEW_TMP)
    return send_from_directory(directory, filename, mimetype="audio/wav", conditional=True)


@app.route("/export", methods=["POST"])
def export():
    data  = request.get_json()
    name  = data.get("_name", "untitled")
    v2cfg = data.get("_config")
    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip() or "untitled"

    os.makedirs(SCORES_DIR, exist_ok=True)
    out_path = os.path.join(SCORES_DIR, f"{safe_name}.yaml")

    # Build clean score dict (exclude editor metadata keys)
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
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
    out_name    = data.get("name", "score_video")
    fps         = int(data.get("fps", 30))
    out_h       = int(data.get("height", 540))
    out_w       = int(data.get("width", 960))

    if not os.path.exists(audio_path) or not os.path.exists(image_path):
        return jsonify({"error": "File not found"}), 404

    dur = score_end - score_start
    if dur <= 0:
        return jsonify({"error": "scoreEnd must be > scoreStart"}), 400

    safe_name = "".join(c for c in out_name if c.isalnum() or c in "-_").strip() or "score_video"
    os.makedirs(SCORES_DIR, exist_ok=True)
    out_path = os.path.join(SCORES_DIR, f"{safe_name}.mp4")

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

    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    try:
        import librosa
        audio, sr_lib = librosa.load(path, sr=None, mono=True)
        base_name = os.path.splitext(os.path.basename(path))[0]
        out_dir   = os.path.join(os.path.dirname(os.path.abspath(path)),
                                 base_name + "_stems")
        os.makedirs(out_dir, exist_ok=True)

        stems = []

        def _save(name, y):
            p = os.path.join(out_dir, f"{name}.wav")
            sf.write(p, y.astype(np.float32), sr_lib)
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


if __name__ == "__main__":
    app.run(port=5000, debug=True)
