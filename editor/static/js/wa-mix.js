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
let _renderGen       = 0;      // increments on each new render or stopAll; stale renders self-cancel

function _getMixCtx() {
  if (!_mixCtx) _mixCtx = new AudioContext();
  return _mixCtx;
}

function mixCurrentTime() {
  if (!_mixPlaying) return state.currentTime;
  return _mixStartOffset + (_getMixCtx().currentTime - _mixStartCtxTime);
}

function isMixPlaying() { return _mixPlaying; }

function stopMix() {
  _renderGen++;                 // invalidate any in-flight render
  if (_mixSource) { try { _mixSource.stop(); } catch(e) {} _mixSource = null; }
  _mixPlaying = false;
}

// Returns the current render generation so callers can check for cancellation.
function _claimRenderGen() { return ++_renderGen; }

async function playMixBuffer(buf, offset) {
  stopMix();
  const ctx = _getMixCtx();
  if (ctx.state === "suspended") {
    try { await ctx.resume(); } catch(e) { console.error('AudioContext resume failed:', e); }
    if (ctx.state !== "running") { console.warn('AudioContext state:', ctx.state); return; }
  }

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
    _mixPlaying = false;
    state.currentTime = _mixStartOffset + (ctx.currentTime - _mixStartCtxTime) * src.playbackRate.value;
    try { src.disconnect(); } catch(_) {}
    if (typeof _setPlayBtn === 'function') _setPlayBtn("▶ Play");
    // Final redraw of all canvases with correct end position
    draw();
    if (typeof drawKalmanTrace === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
      drawKalmanTrace(_lastTraceData);
  };

  if (typeof _setPlayBtn === 'function') _setPlayBtn("⏸ Play");
  requestAnimationFrame(playTick);
}
