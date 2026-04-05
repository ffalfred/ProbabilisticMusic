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

# Allow importing src.* from the parent directory
_BETA_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_BETA_DIR))
from src.sample_engine import build_bank
from src.scheduler     import get_events
from src.mixer         import mix_events, normalise
from src.envelope      import build_dynamics_envelope, build_duck_envelope, build_phrase_envelope
from src.renderer      import _apply_phrase_tempo

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

    # Merge interpretation block (golems + v2config)
    interp = data.get("interp", {})
    if interp.get("golems"):
        score["golems"] = interp["golems"]

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
            score['_interp_base_dims'] = (config.get('v2') or {}).get('base_dims', [])
        else:
            events = get_events(score)

        mix = mix_events(events, bank, sr, score, base)
        # When a golem is interpreting (v2), the golem IS the performer — it has
        # already read dynamics/phrases and shaped the audio. Skip the blind
        # envelopes that would otherwise fight the golem's decisions.
        _golem_active = bool(score.get('_state_trace'))
        if not _golem_active:
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

        from src.interpreter import interpret
        events, _state_trace = interpret(score, config, return_trace=True)
        score['_state_trace'] = _state_trace
        score['_interp_base_dims'] = (config.get('v2') or {}).get('base_dims', [])

        mix = mix_events(events, bank, sr, score, base)
        # Golem is the performer — skip blind dynamics/phrase envelopes.
        mix = normalise(mix)

        # Build output path
        out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(out_dir, exist_ok=True)
        # User-supplied name wins; fall back to score name + timestamp
        user_name = (data.get("out_name") or "").strip()
        if user_name:
            # Sanitize and ensure .wav extension
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in user_name)
            if not safe.lower().endswith(".wav"):
                safe += ".wav"
            out_name = safe
        else:
            score_name = os.path.splitext(os.path.basename(score_path))[0]
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            out_name = f"interp_{score_name}_{ts}.wav"
        out_path = os.path.abspath(os.path.join(out_dir, out_name))
        sf.write(out_path, mix, sr)
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
    app.run(port=5000, debug=True)
