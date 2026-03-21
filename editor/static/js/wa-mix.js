// ─── Web Audio mix player ────────────────────────────────────────────────────
// Handles playback of the rendered mix via Web Audio API.
// Mirrors the approach in wa-mixer.js (used for Source) for reliability:
// fetch → arrayBuffer → decodeAudioData → AudioBufferSourceNode.
// This avoids the <audio>.canplay event which silently hangs on load errors.

let _mixCtx          = null;
let _mixSource       = null;
let _mixBuf          = null;   // last decoded AudioBuffer (kept for seek re-play)
let _mixPlaying      = false;
let _mixStartCtxTime = 0;
let _mixStartOffset  = 0;

function _getMixCtx() {
  if (!_mixCtx) _mixCtx = new AudioContext();
  return _mixCtx;
}

function mixCurrentTime() {
  if (!_mixPlaying) return state.currentTime;
  return _mixStartOffset + (_getMixCtx().currentTime - _mixStartCtxTime);
}

function stopMix() {
  if (_mixSource) { try { _mixSource.stop(); } catch(e) {} _mixSource = null; }
  _mixPlaying = false;
}

async function playMixBuffer(buf, offset) {
  stopMix();
  const ctx = _getMixCtx();
  if (ctx.state === "suspended") await ctx.resume();

  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.playbackRate.value = _getPlaybackSpeed();
  src.connect(ctx.destination);

  _mixBuf          = buf;
  _mixSource       = src;
  _mixStartCtxTime = ctx.currentTime;
  _mixStartOffset  = Math.max(0, Math.min(offset, buf.duration - 0.001));
  _mixPlaying      = true;

  src.start(0, _mixStartOffset);
  src.onended = () => {
    state.currentTime = mixCurrentTime();
    _mixPlaying = false;
    document.getElementById("play-mix-btn").textContent = "▶ Mix";
    draw();
  };

  document.getElementById("play-mix-btn").textContent = "⏸ Mix";
  requestAnimationFrame(playTick);
}
