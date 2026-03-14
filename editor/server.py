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

# Allow importing src.* from the parent beta_interpreter directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sample_engine import build_bank
from src.mixer import mix_events, normalise

PREVIEW_TMP = os.path.join(tempfile.gettempdir(), "opacity_toke_preview.wav")

app = Flask(__name__, static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR = os.path.join(BASE_DIR, "..", "scores")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/load", methods=["POST"])
def load():
    data = request.get_json()
    path = data.get("path", "")

    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404

    # Extract waveform — for mp4/video extract audio first via ffmpeg
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
        # Mix down to mono
        mono = audio_data.mean(axis=1)
        duration = len(mono) / samplerate

        # Downsample to 2000 peak values
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

        waveform = peaks
    except Exception as e:
        return jsonify({"error": f"Could not read audio: {e}"}), 500

    # Extract first video frame if mp4
    frame = None
    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", path,
                    "-vframes", "1", "-q:v", "2",
                    tmp_path
                ],
                capture_output=True, check=True
            )
            with open(tmp_path, "rb") as f:
                frame_bytes = f.read()
            frame = "data:image/png;base64," + base64.b64encode(frame_bytes).decode()
            os.unlink(tmp_path)
        except Exception:
            frame = None

    return jsonify({"waveform": waveform, "duration": duration, "frame": frame})


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
    data  = request.get_json()
    path  = data.get("path", "")
    score = data.get("score", {})

    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        score["base_track"] = path
        bank, sr, base = build_bank(score)
        events = sorted(score.get("events", []), key=lambda e: e["t"])
        mix = mix_events(events, bank, sr, score, base)
        mix = normalise(mix)
        sf.write(PREVIEW_TMP, mix, sr)
        return jsonify({"url": f"/preview_audio?v={int(_time.time())}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/preview_audio")
def preview_audio():
    if not os.path.exists(PREVIEW_TMP):
        return jsonify({"error": "No preview rendered yet"}), 404
    directory = os.path.dirname(PREVIEW_TMP)
    filename  = os.path.basename(PREVIEW_TMP)
    return send_from_directory(directory, filename, mimetype="audio/wav", conditional=True)


@app.route("/export", methods=["POST"])
def export():
    score = request.get_json()
    name = score.get("_name", "untitled")
    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip() or "untitled"

    os.makedirs(SCORES_DIR, exist_ok=True)
    out_path = os.path.join(SCORES_DIR, f"{safe_name}.yaml")

    # Build clean score dict (exclude _name)
    clean = {k: v for k, v in score.items() if k != "_name"}
    yaml_str = yaml.dump(clean, default_flow_style=False, allow_unicode=True, sort_keys=False)

    with open(out_path, "w") as f:
        f.write(yaml_str)

    return jsonify({"path": out_path, "yaml": yaml_str})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
