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

function _getWaCtx() {
  if (!_waCtx) _waCtx = new AudioContext();
  return _waCtx;
}
function _loadWaBuf(path) {
  if (!_waCache[path])
    _waCache[path] = fetch("/video?path=" + encodeURIComponent(path))
      .then(r => r.arrayBuffer())
      .then(ab => _getWaCtx().decodeAudioData(ab));
  return _waCache[path];
}
function _waStop() {
  _waSources.forEach(s => { try { s.stop(); } catch(e) {} });
  _waSources = []; _waGains = []; _waPlaying = false;
}
function _waCurrentTime() {
  return _waPlaying ? _waStartOffset + (_getWaCtx().currentTime - _waStartCtxTime) : state.currentTime;
}
async function _waStart(offset) {
  const gen = ++_waGen;
  _waStop();
  _waStarting = true;
  const unmuted = state.tracks.filter(tk => !tk.muted);
  if (!unmuted.length) { _waStarting = false; return; }
  document.getElementById("play-base-btn").textContent = "⏳ Source";
  const ctx = _getWaCtx();
  if (ctx.state === "suspended") await ctx.resume();
  const buffers = await Promise.all(unmuted.map(tk => _loadWaBuf(tk.path)));
  _waStarting = false;
  if (gen !== _waGen) {
    if (!_waPlaying) document.getElementById("play-base-btn").textContent = "▶ Source";
    return;  // a newer call superseded us — bail
  }
  _waStartCtxTime = ctx.currentTime;
  _waStartOffset  = offset;
  _waPlaying      = true;
  let ended = 0;
  buffers.forEach((buf, i) => {
    const src  = ctx.createBufferSource();
    const gain = ctx.createGain();
    src.buffer = buf;
    gain.gain.value = 10 ** ((unmuted[i].gain_db || 0) / 20);
    src.connect(gain); gain.connect(ctx.destination);
    src.start(0, offset);
    src.onended = () => {
      if (gen !== _waGen) return;  // stale handler from a cancelled start
      ended++;
      if (ended === buffers.length) {
        state.currentTime = _waStartOffset + (ctx.currentTime - _waStartCtxTime);
        _waStop();
        document.getElementById("play-base-btn").textContent = "▶ Source";
        draw();
      }
    };
    _waSources.push(src); _waGains.push(gain);
  });
  document.getElementById("play-base-btn").textContent = "⏸ Source";
  requestAnimationFrame(playTick);
}

function activeBasePlayer() {
  return baseAudio;
}
