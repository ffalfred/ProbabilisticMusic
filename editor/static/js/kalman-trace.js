// ─── kalman-trace.js ──────────────────────────────────────────────────────────
// Kalman belief-state trace visualization + shared tick/color utilities.
// Must load before golems.js (provides _niceTickInterval).
// Depends on: state.js (interpState)

// ─── Trace constants ──────────────────────────────────────────────────────────
// DIM_COLORS defined in golems.js; DIM_NAMES, DIM_RANGES_DEFAULT in state.js
// Use DIM_RANGES_DEFAULT from state.js as the canonical trace ranges
const DIM_RANGES = DIM_RANGES_DEFAULT;

// Greyscale palette for concerto export — shades from white to dark grey,
// one per Kalman state dimension. Used instead of DIM_COLORS when
// _concertoGreyscaleMode is true. Editor stays colorful; only the concerto
// render (video export) uses this palette.
var _concertoGreyscaleMode = false;
// Cached viz dimension selection for concerto mode — phase portrait and
// state trajectory read these instead of the DOM selects during render.
var _concertoDimX = 0;
var _concertoDimY = 1;
const _GREY_PALETTE = [
  '#ffffff', '#e8e8e8', '#d0d0d0', '#b8b8b8',
  '#a0a0a0', '#888888', '#707070', '#585858',
  '#404040', '#282828', '#181818', '#101010', '#c0c0c0',
];
// The dimensions you hear with the current settings: the mix dims that are
// on (filter resonance goes with the filter, width only on stereo audio), and
// the per-event ones (timing, attack, release) when the score has events.
function _audibleDims(data) {
  const on = new Set(interpState.mix_dims || ['gain_db']);
  if (on.has('filter_cutoff')) on.add('filter_resonance');
  const hasEvents = !data || data.n_events == null || data.n_events > 0;
  if (hasEvents) ['timing_offset_ms', 'attack_shape', 'release_shape'].forEach(d => on.add(d));
  else on.delete('pitch_dev_cents');
  const mono = (state.channels || 1) < 2 && !(state.tracks || []).some(t => (t.channels || 1) > 1);
  if (mono) on.delete('stereo_width');
  return on;
}

// Fixed vertical scale per dimension: its full range (the physical limits),
// so a small wobble looks small. Filter cutoff on a log scale.
function _dimScale(d) {
  const lim = (interpState.v2config.v2 || {}).physical_limits;
  const [lo, hi] = (lim && lim[d] && lim[d].length >= 2) ? lim[d].map(Number) : DIM_RANGES[d];
  if (DIM_NAMES[d] === 'filter_cutoff') {
    const a = Math.log(Math.max(lo, 1)), b = Math.log(Math.max(hi, lo + 1));
    return v => Math.max(0, Math.min(1, (Math.log(Math.max(v, 1)) - a) / (b - a)));
  }
  return v => (hi > lo) ? Math.max(0, Math.min(1, (v - lo) / (hi - lo))) : 0.5;
}

function _dimColor(d) {
  return _concertoGreyscaleMode
    ? _GREY_PALETTE[d % _GREY_PALETTE.length]
    : DIM_COLORS[d % DIM_COLORS.length];
}
const CHAR_BG    = {
  dramatic:    'rgba(80,10,10,0.22)',
  lyrical:     'rgba(10,25,80,0.22)',
  sparse:      'rgba(10,60,20,0.22)',
  turbulent:   'rgba(90,60,5,0.22)',
  rw_free:     'rgba(80,50,10,0.18)',
  rw_drift_up: 'rgba(60,10,70,0.18)',
  rw_reverting:'rgba(10,55,60,0.18)',
  discrete:    'rgba(40,40,40,0.22)',
};

var _lastTraceData  = null;
let _lastLayout     = null;   // { padL, padT, plotW, plotH, W, H, t0, totalDur }
let _hoverX         = -1;     // mouse x in canvas px, -1 = no hover

// ─── Shared utilities (used by golems.js) ──────────────────────────────────
function _niceTickInterval(dur, pxWidth) {
  const candidates = [1, 2, 5, 10, 15, 30, 60, 120, 300];
  for (const c of candidates) {
    if ((pxWidth / dur) * c < 40) continue;
    return c;
  }
  return candidates[candidates.length - 1];
}

function _hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return [r, g, b];
}

// ─── Fetch and draw ───────────────────────────────────────────────────────────
function _traceStatus(msg) {
  const el = document.getElementById('interp-render-status');
  if (el) el.textContent = msg;
  const vs = document.getElementById('viz-panel-status');
  if (vs && msg) vs.textContent = msg;
}

// opts.seed: draw the trace of this seed (Play passes the seed its render used,
// so the trace shows the performance you heard)
let _traceGen = 0;
async function fetchAndDrawTrace(opts) {
  opts = opts || {};
  if (!interpState.scorePath) { _traceStatus('⚠ load a score first (Interpreter → score path)'); return; }
  const gen = ++_traceGen;
  const btn     = document.getElementById('interp-trace-btn');
  const walksEl = document.getElementById('interp-walks');
  const nWalks  = walksEl ? Math.max(1, Math.min(20, parseInt(walksEl.value) || 1)) : 1;
  if (btn) btn.disabled = true;
  _traceStatus(nWalks > 1 ? `tracing ${nWalks} walks…` : 'tracing…');
  try {
    // Sync trace_step and seed from UI into v2config before sending
    const _stepEl = document.getElementById('interp-trace-step');
    if (_stepEl) {
      if (!interpState.v2config.v2) interpState.v2config.v2 = {};
      interpState.v2config.v2.trace_step = parseFloat(_stepEl.value) || 0;
    }
    const _seedEl = document.getElementById('interp-seed');
    if (opts.seed != null) interpState.v2config.seed = opts.seed;
    else if (_seedEl && _seedEl.value.trim()) interpState.v2config.seed = parseInt(_seedEl.value);
    else interpState.v2config.seed = null;
    const _audioEl = document.getElementById('interp-audio-path');
    const path   = (_audioEl && _audioEl.value.trim()) || state.filePath || '';
    const interp = { golems: interpState.golems, v2config: interpState.v2config };
    let data;
    if (nWalks > 1) {
      const body = { score_path: interpState.scorePath, path, interp, n_walks: nWalks };
      const res  = await fetch('/multitrace', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      data = await res.json();
      if (data.error) { _traceStatus('error: ' + (data.detail || data.error)); return; }
      if (gen !== _traceGen) return;               // a newer trace was requested
      data.trace = data.walks[0];
    } else {
      const body = { score_path: interpState.scorePath, path, interp };
      const res  = await fetch('/trace', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      data = await res.json();
      if (data.error) { _traceStatus('error: ' + (data.detail || data.error)); return; }
    }
    if (gen !== _traceGen) return;                 // a newer trace was requested
    _lastTraceData = data;
    // Lock in the seed that produced this trace so the next Preview uses
    // identical random draws → audio envelope matches timeline visual.
    if (data.effective_seed != null) {
      interpState.v2config.seed = data.effective_seed;
      // Echo to the UI seed input (so user sees it)
      const _seedEl = document.getElementById('interp-seed');
      if (_seedEl) _seedEl.value = data.effective_seed;
    }
    if (typeof refreshVizDropdown === 'function') refreshVizDropdown(data);
    drawKalmanTrace(data);
    if (typeof updateVizPanel === 'function') updateVizPanel(data);
    _traceStatus('');
  } catch(e) { _traceStatus('failed: ' + e); console.error('fetchAndDrawTrace:', e); }
  finally { if (btn) btn.disabled = false; }
}

// ─── Main canvas renderer: 12D Dimension Timeline ────────────────────────────
var _traceFixedSize = false;   // when true, skip auto-resize (concerto mode)
var _concertoMaxT  = Infinity; // progressive reveal: only draw trace up to this time

function drawKalmanTrace(data) {
  const wrap   = document.getElementById('kalman-trace-wrap');
  const canvas = document.getElementById('kalman-trace-canvas');
  if (!wrap || !canvas || !data || !data.trace || !data.trace.length) return;

  if (!_traceFixedSize) {
    const W = wrap.clientWidth;
    const H = wrap.clientHeight;
    canvas.width  = W;
    canvas.height = H;
  }
  const W = canvas.width, H = canvas.height;
  const ctx = canvas.getContext('2d');

  // Progressive reveal: in concerto mode, only show trace up to _concertoMaxT.
  // Uses binary search (_upperBoundTrace) instead of .filter() to avoid O(N)
  // scan of the full trace array every frame.
  const trace = (_concertoMaxT < Infinity)
    ? data.trace.slice(0, _upperBoundTrace(data.trace, _concertoMaxT))
    : data.trace;
  if (!trace.length) { ctx.fillStyle = '#0a0a0a'; ctx.fillRect(0, 0, W, H); return; }
  const D        = DIM_RANGES.length;
  const totalDur = data.total_dur || (data.trace[data.trace.length-1].t - data.trace[0].t) || 1;
  const t0       = data.trace[0].t;

  const padL = 22, padR = 8, padT = 6, padB = 18;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  _lastLayout = { padL, padR, padT, padB, plotW, plotH, W, H, t0, totalDur };

  // Background
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(0, 0, W, H);

  // Horizontal gridlines at 0 / 0.25 / 0.5 / 0.75 / 1 — dashed, stronger color
  ctx.strokeStyle = '#222222';
  ctx.lineWidth   = 1;
  ctx.setLineDash([2, 4]);
  [0, 0.25, 0.5, 0.75, 1].forEach(frac => {
    var y = padT + plotH * (1 - frac);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
  });
  ctx.setLineDash([]);

  // Y-axis labels: each dimension spans its own full range (hover for values)
  ctx.fillStyle = '#555';
  ctx.font      = '9px Courier New';
  [[0, 'min'], [1, 'max']].forEach(([frac, label]) => {
    var y = padT + plotH * (1 - frac);
    ctx.fillText(label, 4, y + 3);
  });

  // Vertical time ticks — solid
  var tickInt = _niceTickInterval(totalDur, plotW);
  ctx.fillStyle   = '#444';
  ctx.strokeStyle = '#1d1d1d';
  for (let t = 0; t <= totalDur; t += tickInt) {
    var x = padL + (t / totalDur) * plotW;
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    ctx.fillText(t.toFixed(0) + 's', x + 2, H - 5);
  }

  // Per-dim: bold mean line (music-driven structure) + faint sample dots
  // (stochasticity). Only the dimensions you hear are drawn.
  var _activeDims = _audibleDims(data);
  var _activeDimIndices = [];
  for (let d = 0; d < D; d++) {
    if (_activeDims.has(DIM_NAMES[d])) _activeDimIndices.push(d);
  }

  for (const d of _activeDimIndices) {
    var col      = _dimColor(d);
    var [r, g, b] = _hexToRgb(col);
    var normOf = _dimScale(d);              // fixed: the dimension's full range

    // Other walks (walks > 1): their plans, faint, behind this one
    if (data.walks && data.walks.length > 1) {
      ctx.strokeStyle = `rgba(${r},${g},${b},0.22)`;
      ctx.lineWidth   = 1;
      for (let w = 1; w < data.walks.length; w++) {
        var wt = data.walks[w];
        if (_concertoMaxT < Infinity) wt = wt.slice(0, _upperBoundTrace(wt, _concertoMaxT));
        ctx.beginPath();
        var wFirst = true;
        for (const st of wt) {
          var wv = st.mu ? st.mu[d] : null;
          if (wv == null) continue;
          var wx = padL + ((st.t - t0) / totalDur) * plotW;
          var wy = padT + plotH * (1 - normOf(wv));
          if (wFirst) { ctx.moveTo(wx, wy); wFirst = false; } else ctx.lineTo(wx, wy);
        }
        ctx.stroke();
      }
    }

    // Bold mean line (μ) — shows how markings drive the filter
    ctx.strokeStyle = `rgba(${r},${g},${b},0.9)`;
    ctx.lineWidth   = 1.5;
    ctx.beginPath();
    var first = true;
    for (let i = 0; i < trace.length; i++) {
      var step = trace[i];
      var v    = step.mu ? step.mu[d] : null;
      if (v == null) continue;                       // older trace without this dim
      var x    = padL + ((step.t - t0) / totalDur) * plotW;
      var y    = padT + plotH * (1 - normOf(v));
      if (first) { ctx.moveTo(x, y); first = false; }
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Thin sample dots (the stochastic draws that actually drive audio)
    ctx.fillStyle = `rgba(${r},${g},${b},0.35)`;
    for (let i = 0; i < trace.length; i++) {
      var step = trace[i];
      var v    = step.sample ? step.sample[d] : null;
      if (v == null) continue;
      var x = padL + ((step.t - t0) / totalDur) * plotW;
      var y = padT + plotH * (1 - normOf(v));
      ctx.beginPath(); ctx.arc(x, y, 1.2, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Compact legend (top-right, 2 cols): every dimension; the ones not
  // heard with the current settings are greyed out (outlined square)
  var legCols = 2;
  var legW    = 92;
  var legRowH = 11;
  var legX    = W - padR - legW * legCols;
  var legY    = padT + 2;
  ctx.font = '8px Courier New';
  for (let d = 0; d < D; d++) {
    var heard = _activeDims.has(DIM_NAMES[d]);
    var col = _dimColor(d);
    var cx  = legX + (d % legCols) * legW;
    var cy  = legY + Math.floor(d / legCols) * legRowH;
    if (heard) { ctx.fillStyle = col; ctx.fillRect(cx, cy, 7, 7); }
    else { ctx.strokeStyle = 'rgba(120,120,120,0.5)'; ctx.lineWidth = 1; ctx.strokeRect(cx + 0.5, cy + 0.5, 6, 6); }
    ctx.fillStyle = heard ? 'rgba(200,200,200,0.75)' : 'rgba(120,120,120,0.45)';
    ctx.fillText(DIM_LABELS[d], cx + 10, cy + 7);
  }

  // Concerto export renders must not contain editor UI (hover tooltip,
  // live playback cursor); the live concerto view hides the hover too.
  var _exporting = (typeof _concertoDownloading !== 'undefined' && _concertoDownloading);
  var _uiHidden  = _exporting || (typeof _concertoActive !== 'undefined' && _concertoActive);

  // Playback cursor (yellow dashed) — active during audio playback.
  // Trace .t is SCORE time; mixCurrentTime() is real (rendered audio) time.
  var cursorT = -1;
  if (!_exporting && typeof isMixPlaying === 'function' && isMixPlaying()
      && typeof mixCurrentTime === 'function') {
    cursorT = (typeof realToScore === 'function') ? realToScore(mixCurrentTime()) : mixCurrentTime();
  }
  if (cursorT >= 0 && cursorT <= totalDur) {
    var x = padL + ((cursorT - t0) / totalDur) * plotW;
    ctx.save();
    ctx.strokeStyle = _concertoGreyscaleMode ? 'rgba(255,255,255,0.75)' : 'rgba(255,240,100,0.75)';
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    ctx.restore();
  }

  // Hover cursor (cyan solid) + tooltip — tracks mouse position
  if (!_uiHidden && _hoverX >= padL && _hoverX <= W - padR) {
    var frac = (_hoverX - padL) / plotW;
    var tHover = t0 + frac * totalDur;

    // Vertical line
    ctx.save();
    ctx.strokeStyle = _concertoGreyscaleMode ? 'rgba(200,200,200,0.6)' : 'rgba(120,220,255,0.6)';
    ctx.lineWidth   = 1;
    ctx.beginPath(); ctx.moveTo(_hoverX, padT); ctx.lineTo(_hoverX, padT + plotH); ctx.stroke();
    ctx.restore();

    // Find nearest trace step
    var bestIdx = 0, bestDt = Infinity;
    for (let i = 0; i < trace.length; i++) {
      var dt = Math.abs(trace[i].t - tHover);
      if (dt < bestDt) { bestDt = dt; bestIdx = i; }
    }
    var step = trace[bestIdx];

    // Tooltip — only active dims
    var TT_W = 160;
    var TT_H = 10 + _activeDimIndices.length * 10 + 8;
    var ttX = _hoverX + 8;
    if (ttX + TT_W > W - 4) ttX = _hoverX - TT_W - 8;
    var ttY = padT + 4;
    if (ttY + TT_H > padT + plotH) ttY = padT + plotH - TT_H - 4;
    ctx.fillStyle = 'rgba(10,10,10,0.92)';
    ctx.fillRect(ttX, ttY, TT_W, TT_H);
    ctx.strokeStyle = _concertoGreyscaleMode ? 'rgba(200,200,200,0.4)' : 'rgba(120,220,255,0.4)';
    ctx.strokeRect(ttX, ttY, TT_W, TT_H);
    ctx.font = '9px Courier New';
    ctx.fillStyle = '#ccc';
    ctx.fillText(`t = ${step.t.toFixed(2)}s`, ttX + 5, ttY + 10);
    _activeDimIndices.forEach((d, li) => {
      var col = _dimColor(d);
      var v = (step.sample && step.sample[d] != null) ? step.sample[d] : ((step.mu && step.mu[d]) || 0);
      ctx.fillStyle = col;
      ctx.fillRect(ttX + 5, ttY + 15 + li * 10, 5, 5);
      ctx.fillStyle = '#aaa';
      var label = DIM_LABELS[d];
      var valStr = Math.abs(v) >= 100 ? v.toFixed(0)
                   : Math.abs(v) >= 10  ? v.toFixed(1)
                                        : v.toFixed(2);
      ctx.fillText(`${label.padEnd(12).slice(0,12)} ${valStr}`, ttX + 14, ttY + 20 + li * 10);
    });
  }
}

// ─── PNG download ─────────────────────────────────────────────────────────────
function _downloadTimelinePNG() {
  const canvas = document.getElementById('kalman-trace-canvas');
  if (!canvas || !_lastTraceData) return;
  _exportPNGWithPopup(canvas, () => drawKalmanTrace(_lastTraceData), 'timeline', 0.3);
}

// ─── DOMContentLoaded wiring ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const traceBtn = document.getElementById('interp-trace-btn');
  if (traceBtn) traceBtn.addEventListener('click', fetchAndDrawTrace);

  const dlBtn = document.getElementById('interp-download-btn');
  if (dlBtn) dlBtn.addEventListener('click', _downloadTimelinePNG);

  // Hover cursor over the timeline
  const traceCanvas = document.getElementById('kalman-trace-canvas');
  if (traceCanvas) {
    traceCanvas.addEventListener('mousemove', (e) => {
      const r = traceCanvas.getBoundingClientRect();
      _hoverX = e.clientX - r.left;
      if (_lastTraceData) drawKalmanTrace(_lastTraceData);
    });
    traceCanvas.addEventListener('mouseleave', () => {
      _hoverX = -1;
      if (_lastTraceData) drawKalmanTrace(_lastTraceData);
    });
  }
});
