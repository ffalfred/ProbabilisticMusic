// ─── Playback ─────────────────────────────────────────────────────────────────
function _useWebAudio() {
  // Use Web Audio mixer when there are multiple tracks (stems loaded)
  return state.tracks.length > 1;
}

function _getPlaybackSpeed() {
  const el = document.getElementById("playback-speed");
  return el ? (parseFloat(el.value) || 1.0) : 1.0;
}

function _applyPlaybackSpeed() {
  const s = _getPlaybackSpeed();
  vid.playbackRate       = s;
  baseAudio.playbackRate = s;
  // Update Web Audio mix source rate if currently playing
  if (_mixSource) _mixSource.playbackRate.value = s;
}

function goToBeginning() {
  seekTo(0);
}

async function toggleBase() {
  if (_useWebAudio()) {
    if (!baseAudio.paused) baseAudio.pause();
    if (!vid.paused) vid.pause();
    if (_waPlaying) {
      state.currentTime = _waCurrentTime();
      _waStop();
      document.getElementById("play-base-btn").textContent = "▶ Source";
    } else {
      if (!state.tracks.filter(tk => !tk.muted).length) return;
      await _waStart(state.currentTime);
    }
    return;
  }
  const pl = activeBasePlayer();
  if (!pl) return;
  if (!pl.paused) { pl.pause(); return; }
  const targetPath = state.filePath;
  if (!targetPath) return;
  if (currentSourcePath !== targetPath) {
    pl.src = "/video?path=" + encodeURIComponent(targetPath);
    pl.currentTime = state.currentTime;
    currentSourcePath = targetPath;
  }
  pl.muted = false;
  _applyPlaybackSpeed();
  pl.play();
}

async function toggleMix() {
  if (_mixPlaying) {
    state.currentTime = mixCurrentTime();
    stopMix();
    document.getElementById("play-mix-btn").textContent = "▶ Mix";
    return;
  }
  await renderAndPlay();
}

function syncSourcePlayback() {
  if (_useWebAudio()) {
    if (!_waPlaying && !_waStarting) return;
    const unmuted = state.tracks.filter(tk => !tk.muted);
    if (!unmuted.length) {
      state.currentTime = _waCurrentTime();
      _waStop();
      document.getElementById("play-base-btn").textContent = "▶ Source";
    } else {
      _waStart(_waCurrentTime());
    }
    return;
  }
  const pl = activeBasePlayer();
  if (!pl || pl.paused) return;
  if (!state.filePath) { pl.pause(); return; }
}

// ─── Cursor seek ──────────────────────────────────────────────────────────────
function seekTo(t) {
  scoreView.panOffset = 0;
  state.currentTime = t;
  document.getElementById("cur-time").textContent = t.toFixed(3);
  const pl = activeBasePlayer();
  if (pl && pl.src && pl.readyState >= 1) pl.currentTime = t;
  if (vid.src && vid.readyState >= 1) vid.currentTime = t;
  if (_waPlaying) { _waStart(t); }
  if (_mixPlaying && _mixBuf) { playMixBuffer(_mixBuf, t); }
  draw();
}

async function renderAndPlay() {
  const btn = document.getElementById("play-mix-btn");
  if (!state.filePath) return;
  btn.textContent = "⏳ rendering…";
  btn.disabled = true;
  try {
    const samplesClean = {};
    for (const [k, v] of Object.entries(state.samples))
      samplesClean[k] = { from: v.from, to: v.to,
        fade_in: v.fade_in ?? 0.05, fade_out: v.fade_out ?? 0.05,
        ...(v.track ? { track: v.track } : {}) };
    const score = {
      samples: samplesClean,
      dynamics: state.dynamics,
      tempo: state.tempo,
      base_fx: state.baseFx,
      fx_ranges: state.fxRanges,
      events: state.events,
      phrases: state.phrases.map(p => ({
        from: p.from, to: p.to, label: p.label,
        gain_db: p.gain_db ?? 0, fade_in: p.fade_in ?? 0,
        fade_out: p.fade_out ?? 0, tempo_factor: p.tempo_factor ?? 1.0,
      })),
      ...(state.tracks.length > 1 ? { tracks: state.tracks.map(tk => ({
        path: tk.path, name: tk.name, gain_db: tk.gain_db, muted: tk.muted
      })) } : {}),
      ...(state.duckBase.enabled ? { duck_base: state.duckBase } : {}),
      ...(state.duckKey.enabled  ? { duck_key:  state.duckKey  } : {}),
      ...(state.autoMix.enabled  ? { auto_mix:  state.autoMix  } : {}),
      ...(state.articulations.length ? { articulations: state.articulations } : {}),
      ...(state.noteRel.length       ? { note_rel: state.noteRel }            : {}),
    };

    // 1. Ask the server to render and get back the audio URL
    const res = await fetch("/preview", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.filePath, score, _config: state.v2config })
    });
    const data = await res.json();
    if (data.error) { alert("Render error: " + (data.detail || data.error)); return; }

    // 2. Fetch the rendered audio and decode via Web Audio API.
    //    This replaces <audio>.canplay which would silently hang on load errors.
    const audioRes = await fetch(data.url);
    if (!audioRes.ok) throw new Error(`Audio fetch failed (${audioRes.status})`);
    const ab  = await audioRes.arrayBuffer();
    const buf = await _getMixCtx().decodeAudioData(ab);

    // 3. Play
    await playMixBuffer(buf, state.currentTime);
  } catch(e) {
    alert("Render failed: " + e);
  } finally {
    btn.disabled = false;
    if (!_mixPlaying) btn.textContent = "▶ Mix";
  }
}

function playTick() {
  if (_waPlaying) {
    state.currentTime = _waCurrentTime();
    document.getElementById("cur-time").textContent = state.currentTime.toFixed(3);
    draw();
    requestAnimationFrame(playTick);
    return;
  }
  if (_mixPlaying) {
    state.currentTime = mixCurrentTime();
    document.getElementById("cur-time").textContent = state.currentTime.toFixed(3);
    draw();
    requestAnimationFrame(playTick);
    return;
  }
  const playing = (!vid.paused       && !vid.ended)       ? vid
                : (!baseAudio.paused && !baseAudio.ended) ? baseAudio
                : null;
  if (!playing) return;
  state.currentTime = playing.currentTime;
  document.getElementById("cur-time").textContent = state.currentTime.toFixed(3);
  draw();
  requestAnimationFrame(playTick);
}


vid.addEventListener("play",  () => { document.getElementById("play-base-btn").textContent = "⏸ Source"; requestAnimationFrame(playTick); });
vid.addEventListener("pause", () => { document.getElementById("play-base-btn").textContent = "▶ Source"; });
vid.addEventListener("ended", () => { document.getElementById("play-base-btn").textContent = "▶ Source"; state.currentTime = vid.currentTime; draw(); });

baseAudio.addEventListener("play",  () => { document.getElementById("play-base-btn").textContent = "⏸ Source"; requestAnimationFrame(playTick); });
baseAudio.addEventListener("pause", () => { document.getElementById("play-base-btn").textContent = "▶ Source"; });
baseAudio.addEventListener("ended", () => { document.getElementById("play-base-btn").textContent = "▶ Source"; state.currentTime = baseAudio.currentTime; draw(); });

document.addEventListener("keydown", e => {
  if (e.target.matches("input, textarea, select")) return;
  if (e.code === "Space") {
    e.preventDefault();
    toggleMix();
  } else if (e.code === "KeyS") {
    e.preventDefault();
    toggleBase();
  }
});
