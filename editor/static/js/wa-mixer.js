// ─── Web Audio multi-stem mixer ───────────────────────────────────────────────
let _waCtx           = null;
let _waSources       = [];    // active AudioBufferSourceNodes
let _waGains         = [];    // parallel GainNodes
let _waPlaying       = false;
let _waStartCtxTime  = 0;     // audioCtx.currentTime when playback began
let _waStartOffset   = 0;     // track position (seconds) when playback began
const _waCache       = {};    // path -> Promise<AudioBuffer>
let _waGen           = 0;    // generation counter — cancels stale in-flight starts
let _waStarting      = false; // true while buffers are being fetched/decoded
let _waRate          = 1;     // playbackRate used by the current start

function _getWaCtx() {
  if (!_waCtx) _waCtx = new AudioContext();
  return _waCtx;
}
function _loadWaBuf(path) {
  if (!_waCache[path]) {
    const p = fetch("/video?path=" + encodeURIComponent(path))
      .then(r => { if (!r.ok) throw new Error(`fetch failed (${r.status}): ${path}`); return r.arrayBuffer(); })
      .then(ab => _getWaCtx().decodeAudioData(ab));
    // Don't cache failures — the next start should retry
    p.catch(() => { if (_waCache[path] === p) delete _waCache[path]; });
    _waCache[path] = p;
  }
  return _waCache[path];
}
function _waStop() {
  _waSources.forEach(s => {
    s.onended = null;   // stopped on purpose — don't let the end handler move the cursor
    try { s.stop(); } catch(e) {}
  });
  _waSources = []; _waGains = []; _waPlaying = false;
}
function _waCurrentTime() {
  return _waPlaying ? _waStartOffset + (_getWaCtx().currentTime - _waStartCtxTime) * _waRate : state.currentTime;
}
// Automation dB at absolute score time t — linear interpolation clamped to the
// first/last point (mirror of src/sample_engine.py _build_auto_envelope).
function _waAutoDbAt(auto, t) {
  if (t <= auto[0].t) return auto[0].db || 0;
  for (let i = 0; i < auto.length - 1; i++) {
    const a = auto[i], b = auto[i + 1];
    if (t <= b.t) {
      if (b.t === a.t) return b.db || 0;
      return (a.db || 0) + ((b.db || 0) - (a.db || 0)) * (t - a.t) / (b.t - a.t);
    }
  }
  return auto[auto.length - 1].db || 0;
}
async function _waStart(offset) {
  const gen = ++_waGen;
  _waStop();
  _waStarting = true;
  const unmuted = state.tracks.filter(tk => !tk.muted);
  if (!unmuted.length) { _waStarting = false; return; }
  const btn = document.getElementById("play-base-btn");
  if (btn) btn.textContent = "⏳ Source";
  const ctx = _getWaCtx();
  let buffers;
  try {
    if (ctx.state === "suspended") await ctx.resume();
    buffers = await Promise.all(unmuted.map(tk => _loadWaBuf(tk.path)));
  } catch (e) {
    if (gen === _waGen) {
      _waStarting = false;
      if (btn) btn.textContent = "▶ Source";
      if (typeof _setPlayBtn === "function") _setPlayBtn("▶ Play");
      alert("Source playback failed: " + e);
    }
    return;
  }
  if (gen !== _waGen) {
    if (!_waPlaying && btn) btn.textContent = "▶ Source";
    return;  // a newer call superseded us — bail (it owns _waStarting)
  }
  _waStarting = false;
  const rate = (typeof _getPlaybackSpeed === "function") ? _getPlaybackSpeed() : 1;
  _waRate         = rate;
  _waStartCtxTime = ctx.currentTime;
  _waStartOffset  = offset;
  _waPlaying      = true;
  let ended = 0;
  let scheduled = 0;
  buffers.forEach((buf, i) => {
    const tk    = unmuted[i];
    const tFrom = tk.from ?? 0;
    const tTo   = tk.to   != null ? tk.to : Infinity;

    // Skip track entirely if playback cursor is past its end
    if (offset >= tTo) { ended++; return; }

    scheduled++;
    const src  = ctx.createBufferSource();
    const gain = ctx.createGain();
    src.buffer = buf;
    src.playbackRate.value = rate;
    const masterGain = 10 ** ((tk.gain_db || 0) / 20);
    const auto = (tk.automation || []).slice().sort((a, b) => a.t - b.t);
    if (auto.length) {
      // Schedule automation via Web Audio API. Start from the interpolated
      // value at the playback position (score time), then ramp to later points.
      // Score-time distances are divided by the rate to get context time.
      const now = ctx.currentTime;
      gain.gain.setValueAtTime(masterGain * 10 ** (_waAutoDbAt(auto, offset) / 20), now);
      for (const pt of auto) {
        if (pt.t <= offset) continue;
        const when = now + (pt.t - offset) / rate;
        const val = masterGain * 10 ** ((pt.db || 0) / 20);
        gain.gain.linearRampToValueAtTime(val, when);
      }
    } else {
      gain.gain.value = masterGain;
    }
    src.connect(gain); gain.connect(ctx.destination);

    if (offset <= tFrom) {
      // Cursor is before this stem's region — schedule a delayed start
      const delay = (tFrom - offset) / rate;
      src.start(ctx.currentTime + delay, 0);
    } else {
      // Cursor is inside the region — seek into buffer
      const bufOffset = offset - tFrom;
      src.start(ctx.currentTime, bufOffset);
    }

    src.onended = () => {
      if (gen !== _waGen) return;  // stale handler from a cancelled start
      ended++;
      if (ended === buffers.length) {
        state.currentTime = _waCurrentTime();
        _waStop();
        const b = document.getElementById("play-base-btn");
        if (b) b.textContent = "▶ Source";
        if (typeof _setPlayBtn === "function") _setPlayBtn("▶ Play");
        draw();
      }
    };
    _waSources.push(src); _waGains.push(gain);
  });
  // If all tracks were skipped (all past their end), stop immediately
  if (scheduled === 0) {
    state.currentTime = offset;
    _waStop();
    if (btn) btn.textContent = "▶ Source";
    draw();
    return;
  }
  if (btn) btn.textContent = "⏸ Source";
  requestAnimationFrame(playTick);
}

function activeBasePlayer() {
  return baseAudio;
}
