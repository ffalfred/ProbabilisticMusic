// ─── Concerto View + Concerto Download ───────────────────────────────────────
// Depends on: state.js, draw.js (frameCanvas, score2Canvas), viz-panel.js,
//             kalman-trace.js, playback.js, interpreter.js, filebrowser.js (openSaveBrowser)

var _concertoActive = false;
var _concertoRaf    = null;
var _concertoViewMode = 'combined';  // 'combined' | 'score' | 'meta'
var _concertoCleanMode = false;

// Draw score/meta canvases with only the image + cursor, no annotations
function _drawCleanFrameOverlay() {
  if (typeof frameCanvas === 'undefined' || typeof frameCtx === 'undefined') return;
  var W = frameCanvas.width, H = frameCanvas.height;
  frameCtx.clearRect(0, 0, W, H);
  if (typeof scoreView !== 'undefined') {
    frameCtx.fillStyle = '#111';
    frameCtx.fillRect(0, 0, W, H);
    var img = scoreView.img;
    if (img && img.complete && img.naturalWidth > 0) {
      var s = (H / img.naturalHeight) * scoreView.scale;
      var sl = typeof scoreScrollLeft === 'function' ? scoreScrollLeft() : 0;
      var srcX = sl / s, srcW = W / s;
      var clSrcX = Math.max(0, srcX);
      var clSrcW = Math.min(srcW, img.naturalWidth - clSrcX);
      var dstX = (clSrcX - srcX) * s, dstW = clSrcW * s;
      if (clSrcW > 0 && dstW > 0) frameCtx.drawImage(img, clSrcX, 0, clSrcW, img.naturalHeight, dstX, 0, dstW, H);
    }
  }
  var cx = typeof tToXF === 'function' ? tToXF(state.currentTime) : 0;
  frameCtx.strokeStyle = 'rgba(255,255,255,0.8)';
  frameCtx.lineWidth = 1; frameCtx.setLineDash([]);
  frameCtx.beginPath(); frameCtx.moveTo(cx, 0); frameCtx.lineTo(cx, H); frameCtx.stroke();
}

function _drawCleanScoreOverlay() {
  if (typeof score2Canvas === 'undefined' || typeof score2Ctx === 'undefined' || typeof score2View === 'undefined') return;
  var c = score2Canvas, ctx = score2Ctx, view = score2View;
  var W = c.width, H = c.height;
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, W, H);
  var img = view.img;
  if (img && img.complete && img.naturalWidth > 0) {
    var s = (H / img.naturalHeight) * view.scale;
    var dur = view.end - view.start;
    var dw = typeof scoreDisplayWidthFor === 'function' ? scoreDisplayWidthFor(c, view) : W;
    var curDisp = dur > 0 ? ((state.currentTime - view.start) / dur) * dw : 0;
    var sl = curDisp - W / 2 - view.panOffset;
    var srcX = sl / s, srcW = W / s;
    var clSrcX = Math.max(0, srcX);
    var clSrcW = Math.min(srcW, img.naturalWidth - clSrcX);
    var dstX = (clSrcX - srcX) * s, dstW = clSrcW * s;
    if (clSrcW > 0 && dstW > 0) ctx.drawImage(img, clSrcX, 0, clSrcW, img.naturalHeight, dstX, 0, dstW, H);
  }
  var tx = typeof tToXFor === 'function' ? tToXFor(state.currentTime, c, view) : 0;
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 1; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(tx, 0); ctx.lineTo(tx, H); ctx.stroke();
}

// ─── Source canvases ─────────────────────────────────────────────────────────
function _getSourceCanvases() {
  return {
    score:    document.getElementById('frame-canvas'),
    meta:     document.getElementById('score2-canvas'),
    timeline: document.getElementById('kalman-trace-canvas'),
    viz:      document.getElementById('viz-panel-canvas'),
  };
}

// ─── Concerto View (live fullscreen) ─────────────────────────────────────────
function enterConcertoView() {
  const overlay = document.getElementById('concerto-overlay');
  const canvas  = document.getElementById('concerto-canvas');
  if (!overlay || !canvas) return;

  _concertoActive = true;
  _concertoViewMode = (document.getElementById('concerto-view-mode') || {}).value || 'combined';
  _concertoCleanMode = true;
  overlay.style.display = 'block';

  // Go fullscreen
  const el = document.documentElement;
  if (el.requestFullscreen) el.requestFullscreen();
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();

  // Size canvas to screen and upsize source canvases for sharp rendering
  _resizeConcertoCanvas();
  const dpr = window.devicePixelRatio || 1;
  _upsizeSourceCanvases(
    Math.round(window.innerWidth * dpr),
    Math.round(window.innerHeight * dpr)
  );
  window.addEventListener('resize', _onConcertoResize);

  // Start the composite loop
  _concertoTick();

  // Auto-start playback
  if (typeof togglePlay === 'function') togglePlay();
}

function exitConcertoView() {
  _concertoActive = false;
  _concertoCleanMode = false;
  _concertoMaxT = Infinity;  // restore full view
  const overlay = document.getElementById('concerto-overlay');
  if (overlay) overlay.style.display = 'none';
  window.removeEventListener('resize', _onConcertoResize);
  if (_concertoRaf) { cancelAnimationFrame(_concertoRaf); _concertoRaf = null; }
  _restoreSourceCanvases();
  // Redraw at normal size to restore the editor
  if (typeof draw === 'function') draw();
  if (document.fullscreenElement) document.exitFullscreen();
}

function _onConcertoResize() {
  _resizeConcertoCanvas();
  const dpr = window.devicePixelRatio || 1;
  _upsizeSourceCanvases(
    Math.round(window.innerWidth * dpr),
    Math.round(window.innerHeight * dpr)
  );
}

function _resizeConcertoCanvas() {
  const canvas = document.getElementById('concerto-canvas');
  if (!canvas) return;
  canvas.width  = window.innerWidth  * (window.devicePixelRatio || 1);
  canvas.height = window.innerHeight * (window.devicePixelRatio || 1);
}

function _concertoTick() {
  if (!_concertoActive) return;

  // Update time from audio playback
  if (typeof _waPlaying !== 'undefined' && _waPlaying && typeof _waCurrentTime === 'function') {
    state.currentTime = _waCurrentTime();
  } else if (typeof _mixPlaying !== 'undefined' && _mixPlaying && typeof mixCurrentTime === 'function' && typeof realToScore === 'function') {
    state.currentTime = realToScore(mixCurrentTime());
  } else {
    var pl = (typeof baseAudio !== 'undefined' && !baseAudio.paused && !baseAudio.ended) ? baseAudio : null;
    if (pl) state.currentTime = pl.currentTime;
  }

  _concertoMaxT = state.currentTime;
  if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = state.currentTime;

  // Draw all source canvases ourselves — no reliance on playTick
  if (_concertoCleanMode) {
    _drawCleanFrameOverlay();
    _drawCleanScoreOverlay();
  } else {
    if (typeof draw === 'function') draw();
    if (typeof drawScoreOverlay === 'function' && typeof score2Canvas !== 'undefined' && typeof score2Ctx !== 'undefined' && typeof score2View !== 'undefined')
      drawScoreOverlay(score2Canvas, score2Ctx, score2View);
  }
  if (typeof drawKalmanTrace === 'function' && _lastTraceData)
    drawKalmanTrace(_lastTraceData);

  _compositeConcerto(document.getElementById('concerto-canvas'));
  _concertoRaf = requestAnimationFrame(_concertoTick);
}

// ─── Composite: draw 4 source canvases into the concerto canvas ──────────────
// Layout mirrors the interpreter DAW proportions:
//   Left column (72%): score (flex 5 ≈ 50%), metadata (flex 1 ≈ 10%), timeline (flex 4 ≈ 40%)
//   Right column (28%): viz panel (full height)
//   Panel borders: 1px #1a1a1a — same as DAW chrome
const _CONCERTO_VIZ_RATIO    = 0.18;
const _LEFT_SCORE_RATIO      = 0.42;  // of total height
const _LEFT_META_RATIO       = 0.35;
const _LEFT_TIMELINE_RATIO   = 0.23;

// Index of the first trace sample with .t > maxT, or trace.length if all
// samples have .t <= maxT. Used to slice the trace prefix without scanning
// the whole array each frame — replaces an O(n) filter with O(log n) and
// turns an O(n²) total cost (across all frames) into O(n log n).
function _upperBoundTrace(trace, maxT) {
  var lo = 0, hi = trace.length;
  while (lo < hi) {
    var mid = (lo + hi) >>> 1;
    if (trace[mid].t <= maxT) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function _compositeConcerto(target, W, H, mode) {
  if (!target) return;
  const ctx = target.getContext('2d');
  W = W || target.width;
  H = H || target.height;
  mode = mode || _concertoViewMode || 'combined';

  const src = _getSourceCanvases();

  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, W, H);

  if (mode === 'score') {
    // Draw score image + cursor directly (no reliance on frameCanvas)
    var sv = (typeof scoreView !== 'undefined') ? scoreView : null;
    if (sv && sv.img && sv.img.complete && sv.img.naturalWidth > 0) {
      var s   = (H / sv.img.naturalHeight) * sv.scale;
      var dur = sv.end - sv.start;
      var dw  = sv.img.naturalWidth * s;
      var curDisp = dur > 0 ? ((state.currentTime - sv.start) / dur) * dw : 0;
      var sl  = curDisp - W / 2;
      var srcX = sl / s, srcW = W / s;
      var clSrcX = Math.max(0, srcX);
      var clSrcW = Math.min(srcW, sv.img.naturalWidth - clSrcX);
      var dstX = (clSrcX - srcX) * s, dstW = clSrcW * s;
      if (clSrcW > 0 && dstW > 0) {
        ctx.drawImage(sv.img, clSrcX, 0, clSrcW, sv.img.naturalHeight, dstX, 0, dstW, H);
      }
    } else if (src.score && src.score.width > 0 && src.score.height > 0) {
      ctx.drawImage(src.score, 0, 0, W, H);
    }
    // Cursor
    var cDur = sv ? (sv.end - sv.start) : (state.duration || 1);
    var cx = cDur > 0 ? ((state.currentTime - (sv ? sv.start : 0)) / cDur) * W : 0;
    ctx.strokeStyle = 'rgba(255,255,255,0.8)';
    ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx + W/2, 0); ctx.lineTo(cx + W/2, H); ctx.stroke();
  } else if (mode === 'meta') {
    // Dashboard layout: metadata centered, viz panels top + bottom
    const gap    = Math.round(W * 0.003);
    const stripH = Math.round(H * 0.25);  // top/bottom strips = 25% each
    const midH   = H - stripH * 2 - gap * 4;  // middle = 50%

    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, W, H);

    // Metadata centered in middle area at 70% width
    if (src.meta && src.meta.width > 0 && src.meta.height > 0) {
      const metaW = Math.floor(W * 0.7);
      const metaH = Math.min(midH - gap * 2, Math.round(metaW * (src.meta.height / src.meta.width)));
      const mx = Math.floor((W - metaW) / 2);
      const my = stripH + gap * 2 + Math.floor((midH - metaH) / 2);
      ctx.drawImage(src.meta, mx, my, metaW, metaH);
    }

    // Draw 4 different viz types + timeline
    // Viz panels are square (stripH × stripH), centered with black space between
    var sqSz = stripH;  // square side = strip height
    var botY = stripH + gap * 2 + midH + gap;

    // Top strip: 2 square viz panels centered
    var topTotalW = sqSz * 2 + gap;
    var topX0 = Math.floor((W - topTotalW) / 2);

    // Bottom strip: 2 square viz panels + timeline in the middle
    var tlW = W - sqSz * 2 - gap * 4;  // timeline fills remaining width
    var botX0 = gap;

    if (src.viz && _lastTraceData && _lastTraceData.trace && _lastTraceData.trace.length) {
      src.viz.width  = sqSz;
      src.viz.height = sqSz;
      var vizCtx = src.viz.getContext('2d');
      // Binary-search the upper-bound index (trace is sorted by .t). Slicing
      // is still required because the viz functions iterate the trace array,
      // but the slice is O(k) on the kept prefix instead of O(n) per frame.
      var trace = _lastTraceData.trace;
      var hi    = (_concertoMaxT < Infinity) ? _upperBoundTrace(trace, _concertoMaxT) : trace.length;
      var fData = (hi === trace.length)
        ? _lastTraceData
        : (hi === 0 ? _lastTraceData : { ..._lastTraceData, trace: trace.slice(0, hi) });

      // Top left: Marginal Gaussians
      vizCtx.fillStyle = '#0a0a0a'; vizCtx.fillRect(0, 0, sqSz, sqSz);
      try { _drawMarginalGaussians(vizCtx, sqSz, sqSz, fData); } catch(e) {}
      ctx.drawImage(src.viz, topX0, gap, sqSz, sqSz);

      // Top right: Phase Portrait
      vizCtx.fillStyle = '#0a0a0a'; vizCtx.fillRect(0, 0, sqSz, sqSz);
      try { _drawPhasePortrait(vizCtx, sqSz, sqSz, fData); } catch(e) {}
      ctx.drawImage(src.viz, topX0 + sqSz + gap, gap, sqSz, sqSz);

      // Bottom left: Innovation Energy
      vizCtx.fillStyle = '#0a0a0a'; vizCtx.fillRect(0, 0, sqSz, sqSz);
      try { _drawInnovationEnergy(vizCtx, sqSz, sqSz, fData); } catch(e) {}
      ctx.drawImage(src.viz, botX0, botY, sqSz, sqSz);

      // Bottom center: Timeline (wide, not square)
      if (src.timeline && src.timeline.width > 0 && src.timeline.height > 0) {
        ctx.drawImage(src.timeline, botX0 + sqSz + gap, botY, tlW, stripH);
      }

      // Bottom right: State Trajectory
      vizCtx.fillStyle = '#0a0a0a'; vizCtx.fillRect(0, 0, sqSz, sqSz);
      try { _drawStateTrajectory(vizCtx, sqSz, sqSz, fData); } catch(e) {}
      ctx.drawImage(src.viz, botX0 + sqSz + gap * 2 + tlW, botY, sqSz, sqSz);
    } else {
      if (src.timeline && src.timeline.width > 0 && src.timeline.height > 0) {
        ctx.drawImage(src.timeline, gap, botY, W - gap * 2, stripH);
      }
    }
  } else if (mode === 'timeline') {
    // Standalone timeline strip — fills the full frame
    ctx.fillStyle = '#0a0a0a'; ctx.fillRect(0, 0, W, H);
    if (src.timeline && src.timeline.width > 0 && src.timeline.height > 0) {
      ctx.drawImage(src.timeline, 0, 0, W, H);
    }

  } else if (mode === 'marginal' || mode === 'phase' || mode === 'energy' || mode === 'trajectory') {
    // Standalone single viz panel — draw the specific viz function at full W×H
    ctx.fillStyle = '#0a0a0a'; ctx.fillRect(0, 0, W, H);
    if (_lastTraceData && _lastTraceData.trace && _lastTraceData.trace.length) {
      var trace = _lastTraceData.trace;
      var hi    = (_concertoMaxT < Infinity) ? _upperBoundTrace(trace, _concertoMaxT) : trace.length;
      var fData = (hi === trace.length)
        ? _lastTraceData
        : (hi === 0 ? _lastTraceData : { ..._lastTraceData, trace: trace.slice(0, hi) });
      try {
        if      (mode === 'marginal')   _drawMarginalGaussians(ctx, W, H, fData);
        else if (mode === 'phase')      _drawPhasePortrait(ctx, W, H, fData);
        else if (mode === 'energy')     _drawInnovationEnergy(ctx, W, H, fData);
        else if (mode === 'trajectory') _drawStateTrajectory(ctx, W, H, fData);
      } catch (e) {}
    }

  } else {
    // Combined layout — all panels with gaps
    const gap = Math.round(W * 0.003);
    const vizW  = Math.floor(W * _CONCERTO_VIZ_RATIO) - gap;
    const leftW = W - vizW - gap * 2;
    const scoreH    = Math.floor(H * _LEFT_SCORE_RATIO) - gap;
    const metaH     = Math.floor(H * _LEFT_META_RATIO) - gap;
    const timelineH = H - scoreH - metaH - gap * 3;

    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, W, H);

    if (src.score && src.score.width > 0 && src.score.height > 0) {
      ctx.drawImage(src.score, gap, gap, leftW, scoreH);
    }
    if (src.meta && src.meta.width > 0 && src.meta.height > 0) {
      ctx.drawImage(src.meta, gap, gap * 2 + scoreH, leftW, metaH);
    }
    if (src.timeline && src.timeline.width > 0 && src.timeline.height > 0) {
      ctx.drawImage(src.timeline, gap, gap * 3 + scoreH + metaH, leftW, timelineH);
    }
    if (src.viz && src.viz.width > 0 && src.viz.height > 0) {
      ctx.drawImage(src.viz, gap + leftW + gap, gap, vizW, H - gap * 2);
    }
  }
}

// ─── High-res canvas rendering for concerto ──────────────────────────────────
// Before compositing, temporarily resize source canvases to their target size
// in the concerto frame so they render at full resolution (not upscaled from
// their small on-screen size).
let _savedCanvasSizes = null;

function _setConcertoFixedSize(on) {
  if (typeof _traceFixedSize !== 'undefined') _traceFixedSize = on;
  if (typeof _vizFixedSize   !== 'undefined') _vizFixedSize   = on;
}

function _upsizeSourceCanvases(W, H) {
  _setConcertoFixedSize(true);
  const src = _getSourceCanvases();
  const vizW      = Math.floor(W * _CONCERTO_VIZ_RATIO);
  const leftW     = W - vizW;
  const scoreH    = Math.floor(H * _LEFT_SCORE_RATIO);
  const metaH     = Math.floor(H * _LEFT_META_RATIO);
  const timelineH = H - scoreH - metaH;

  _savedCanvasSizes = {};
  // Save and resize each canvas to its target region size
  const targets = [
    ['score',    leftW, scoreH],
    ['meta',     leftW, metaH],
    ['timeline', leftW, timelineH],
    ['viz',      vizW,  H],
  ];
  for (const [key, tw, th] of targets) {
    const c = src[key];
    if (!c) continue;
    _savedCanvasSizes[key] = { w: c.width, h: c.height };
    c.width  = tw;
    c.height = th;
  }
}

function _restoreSourceCanvases() {
  _setConcertoFixedSize(false);
  if (!_savedCanvasSizes) return;
  const src = _getSourceCanvases();
  for (const [key, saved] of Object.entries(_savedCanvasSizes)) {
    const c = src[key];
    if (c) { c.width = saved.w; c.height = saved.h; }
  }
  _savedCanvasSizes = null;
}

// ─── Concerto Download (4K 60fps video) ──────────────────────────────────────
let _concertoDownloading = false;

// ─── Segment-based render loop ───────────────────────────────────────────────
// Long downloads (~8 min at 4K/60) used to fail with NetworkError because a
// single ffmpeg subprocess + a single long-lived browser→server stream
// accumulated memory pressure and pipe back-pressure that compounded over
// time. The fix: render in ~30 s segments, each with its own short-lived
// ffmpeg subprocess on the server. After all segments, the server stitches
// them losslessly with `ffmpeg -c copy`.
//
// Tier 3: when OffscreenCanvas + Worker is available, the per-frame JPEG
// encode and HTTP upload are pushed to a Web Worker (concerto-worker.js),
// freeing the main thread to start rendering frame N+1 while the worker is
// still processing frame N. Backpressure is enforced by counting `frameAck`
// messages from the worker. When unavailable, falls back to the in-process
// path (toBlob on main thread, batch + fetch from main thread).
//
// `drawFrame(realT, scoreT)` is called per-frame to update the source
// canvases before compositing. `mode` is passed through to _compositeConcerto.
async function _runConcertoSegments(opts) {
  const { W, H, FPS, totalFrames, startTime, frameDur,
          drawFrame, mode, isTest, statusLabel,
          wireFormat = 'raw' } = opts;

  // Factory: make a fresh offscreen canvas. Called once here and again at
  // the start of each segment to release accumulated native (GPU/texture)
  // state that grows Chromium's per-canvas memory even when the JS heap
  // stays flat. The rising encode time we observed is consistent with
  // this sort of native-side accumulation.
  function _makeOffscreen() {
    if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(W, H);
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    return c;
  }
  let offscreen = _makeOffscreen();

  // Pick the right MIME + filename extension for the wire format. Quality=1
  // for WebP/JPEG in Chromium means the encoder's best setting (WebP is
  // near-lossless, JPEG is the max-quality preset).
  const isRaw = (wireFormat === 'raw');
  const MIME_BY_WIRE = { jpeg: 'image/jpeg', png: 'image/png' };
  const EXT_BY_WIRE  = { jpeg: 'batch.mjpeg', png: 'batch.png', raw: 'batch.raw' };
  const QUAL_BY_WIRE = { jpeg: 0.92, png: undefined };
  const mime    = MIME_BY_WIRE[wireFormat] || 'image/png';
  const fname   = EXT_BY_WIRE[wireFormat]  || 'batch.raw';
  const wireQ   = QUAL_BY_WIRE[wireFormat];

  const SEG_DURATION       = 30;           // seconds per segment
  const SEG_FRAMES         = SEG_DURATION * FPS;
  const numSegments        = Math.max(1, Math.ceil(totalFrames / SEG_FRAMES));
  const MAX_INFLIGHT       = 3;            // concurrent uploads
  const BATCH_SIZE         = 3;            // frames per HTTP request (small for raw RGBA)
  // PNG (lossless) is used for the wire format — fine mesh / line-art
  // content suffers visible JPEG DCT ringing at any quality. Final output
  // quality is set by the HEVC encoder; JPEG compression in between would
  // just throw away pixels that the encoder would otherwise preserve.
  const MAX_FRAMES_BEHIND  = 8;            // how far renderer can race ahead of worker
  const renderStart        = performance.now();
  let totalRendered        = 0;
  // Sliding window for instantaneous fps in the status bar display.
  // Each entry: {t: performance.now(), f: totalRendered}. Keeps the last
  // ~6 seconds of samples so the fps + ETA reflect CURRENT speed.
  const _fpsWin = [];

  // TEMP: forcing main-thread encode path to test whether WebP is faster
  // there than on the worker. Set back to the feature-detect expression
  // if main-thread is not an improvement.
  const useWorker = false;

  let worker              = null;
  let framesSent          = 0;
  let framesAcked         = 0;
  let workerError         = null;
  let ackResolvers        = [];   // pending awaiters for the next ack
  let segmentDoneResolver = null;

  if (useWorker) {
    // Flask serves static/ at the root (static_url_path=""), so this is /js/*.
    worker = new Worker('/js/concerto-worker.js');
    worker.onmessage = (e) => {
      const m = e.data || {};
      if (m.type === 'frameAck') {
        framesAcked++;
        const r = ackResolvers; ackResolvers = [];
        for (const fn of r) fn();
      } else if (m.type === 'segmentDone') {
        const r = segmentDoneResolver; segmentDoneResolver = null;
        if (r) r();
      } else if (m.type === 'error') {
        workerError = m.message || 'unknown worker error';
        // Wake everything waiting so the main loop can throw promptly.
        const r = ackResolvers; ackResolvers = [];
        for (const fn of r) fn();
        const sd = segmentDoneResolver; segmentDoneResolver = null;
        if (sd) sd();
      }
    };
    worker.onerror = (e) => {
      workerError = `worker fatal: ${(e && e.message) || (e && e.type) || 'unknown'}`;
      const r = ackResolvers; ackResolvers = [];
      for (const fn of r) fn();
      const sd = segmentDoneResolver; segmentDoneResolver = null;
      if (sd) sd();
    };
    worker.postMessage({
      type: 'init',
      batchSize:   BATCH_SIZE,
      maxInflight: MAX_INFLIGHT,
      wireFormat:  wireFormat,
    });
  }

  try {
    for (let seg = 0; seg < numSegments; seg++) {
      if (!_concertoDownloading) return;
      if (workerError) throw new Error(workerError);

      // Spawn next segment's ffmpeg (segment 0 was started by the caller).
      if (seg > 0) {
        const r = await fetch('/concerto_start', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ segment_index: seg })
        });
        const d = await r.json();
        if (d.error) throw new Error(`segment ${seg} start: ${d.error}`);
        // (Earlier tried recreating offscreen canvas here; didn't help,
        // and may have hurt throughput in chunked mode. Removed.)
      }

      const segStartFrame = seg * SEG_FRAMES;
      const segEndFrame   = Math.min(segStartFrame + SEG_FRAMES, totalFrames);
      const segCount      = segEndFrame - segStartFrame;

      // Per-segment state (only used by the in-process fallback path).
      let inflight      = [];
      let batchBuf      = [];
      let batchStartIdx = 0;

      if (useWorker) {
        // Reset per-segment counters on both sides (each segment's ffmpeg
        // starts from frame 0).
        framesSent = 0;
        framesAcked = 0;
        worker.postMessage({ type: 'beginSegment' });
      }

      // PROFILE: per-stage timing accumulators (per-segment)
      let _profDrawMs = 0, _profEncodeMs = 0, _profUploadWaitMs = 0;
      let _profFrames = 0;

      for (let sf = 0; sf < segCount; sf++) {
        if (!_concertoDownloading) return;
        if (workerError) throw new Error(workerError);
        const f      = segStartFrame + sf;
        const realT  = startTime + f * frameDur;
        const scoreT = (typeof realToScore === 'function') ? realToScore(realT) : realT;
        state.currentTime = scoreT;
        _concertoMaxT = scoreT;
        if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = realT;

        const _tDraw0 = performance.now();
        drawFrame(realT, scoreT);
        _compositeConcerto(offscreen, W, H, mode);
        const _tDraw1 = performance.now();
        _profDrawMs += (_tDraw1 - _tDraw0);

        if (useWorker) {
          // Snapshot the offscreen as ImageBitmap (zero-copy on Chromium)
          // and transfer ownership to the worker — frees main thread to
          // render the next frame immediately.
          const bitmap = offscreen.transferToImageBitmap();
          worker.postMessage({ type: 'frame', bitmap, frameIdx: sf }, [bitmap]);
          framesSent++;

          // Backpressure: don't let the renderer race more than
          // MAX_FRAMES_BEHIND frames ahead of the worker's encode rate.
          const _tWait0 = performance.now();
          while (framesSent - framesAcked >= MAX_FRAMES_BEHIND) {
            await new Promise(r => ackResolvers.push(r));
            if (workerError) throw new Error(workerError);
            if (!_concertoDownloading) return;
          }
          _profUploadWaitMs += (performance.now() - _tWait0);
        } else {
          // Main-thread encode path.
          const _tEnc0 = performance.now();
          let frameChunk;
          if (isRaw) {
            // Raw RGBA: getImageData is a fixed-cost GPU→CPU copy with no
            // encoder state — immune to the fps-decay that toBlob suffers.
            const ctx2d = offscreen.getContext('2d');
            const imageData = ctx2d.getImageData(0, 0, W, H);
            frameChunk = new Uint8Array(imageData.data.buffer);
          } else if (typeof offscreen.convertToBlob === 'function') {
            const opts = (wireQ === undefined)
              ? { type: mime }
              : { type: mime, quality: wireQ };
            frameChunk = await offscreen.convertToBlob(opts);
          } else {
            frameChunk = await new Promise(r =>
              wireQ === undefined
                ? offscreen.toBlob(r, mime)
                : offscreen.toBlob(r, mime, wireQ)
            );
          }
          _profEncodeMs += (performance.now() - _tEnc0);
          if (!frameChunk) throw new Error('encode returned null');
          batchBuf.push(frameChunk);

          if (batchBuf.length >= BATCH_SIZE || sf === segCount - 1) {
            // For raw RGBA, all frames have the same size so `lengths` is
            // not strictly needed, but we send it anyway for consistency.
            const lengths = batchBuf.map(b => b.size || b.byteLength || b.length).join(',');
            const blob = new Blob(batchBuf, { type: 'application/octet-stream' });
            const fd = new FormData();
            fd.append('frames', blob, fname);
            fd.append('start_index', String(batchStartIdx));
            fd.append('count', String(batchBuf.length));
            fd.append('lengths', lengths);

            const upload = fetch('/concerto_frames', { method: 'POST', body: fd })
              .then(() => { inflight = inflight.filter(p => p !== upload); });
            inflight.push(upload);

            batchStartIdx = sf + 1;
            batchBuf = [];

            if (inflight.length >= MAX_INFLIGHT) {
              const _tWait0 = performance.now();
              await inflight[0];
              _profUploadWaitMs += (performance.now() - _tWait0);
            }
          }
        }

        _profFrames++;
        // Every 30 frames: dump the per-stage averages + browser heap usage.
        // If heap grows monotonically while encode time rises, the cause is
        // memory pressure (GC churn / blob retention).
        if (_profFrames >= 30) {
          const ad = (_profDrawMs    / _profFrames).toFixed(1);
          const ae = (_profEncodeMs  / _profFrames).toFixed(1);
          const au = (_profUploadWaitMs / _profFrames).toFixed(1);
          const heapMB = (performance.memory && performance.memory.usedJSHeapSize)
            ? (performance.memory.usedJSHeapSize / 1048576).toFixed(0)
            : '?';
          console.log(`[concerto] f=${f+1} draw=${ad}ms encode=${ae}ms uploadWait=${au}ms heap=${heapMB}MB (avg over ${_profFrames} frames)`);
          _profDrawMs = 0; _profEncodeMs = 0; _profUploadWaitMs = 0; _profFrames = 0;
        }

        totalRendered = f + 1;
        if (sf % 10 === 0 || sf === segCount - 1) {
          const elapsed = (performance.now() - renderStart) / 1000;
          // Instantaneous fps = last ~30 frames, so the display reflects
          // CURRENT speed. Prevents cumulative-average from drifting and
          // making the ETA look like it's rising when it's actually stable.
          const nowT = performance.now();
          _fpsWin.push({ t: nowT, f: totalRendered });
          while (_fpsWin.length > 2 && (nowT - _fpsWin[0].t) > 6000) _fpsWin.shift();
          let instFps;
          if (_fpsWin.length >= 2) {
            const dt = (_fpsWin[_fpsWin.length-1].t - _fpsWin[0].t) / 1000;
            const df = _fpsWin[_fpsWin.length-1].f - _fpsWin[0].f;
            instFps = df / Math.max(dt, 0.001);
          } else {
            instFps = totalRendered / Math.max(elapsed, 0.001);
          }
          const remain  = (totalFrames - totalRendered) / Math.max(instFps, 0.5);
          const pct     = Math.round(totalRendered / totalFrames * 100);
          const eta     = remain < 60
            ? `${Math.round(remain)}s`
            : `${Math.floor(remain / 60)}m ${Math.round(remain % 60)}s`;
          const res     = isTest ? '1080p' : '4K';
          const tag     = useWorker ? '' : ' [no-worker]';
          setConcertoStatus(`${statusLabel} ${res}${tag}: seg ${seg + 1}/${numSegments} ${pct}% (${instFps.toFixed(1)} fps) — ETA ${eta}`);
        }

        if (sf % 5 === 0) await new Promise(r => setTimeout(r, 0));
      }

      // Drain remaining uploads for this segment, then close its ffmpeg.
      if (useWorker) {
        // Tell worker to flush any partial batch + drain inflight, then ack.
        await new Promise((resolve) => {
          segmentDoneResolver = resolve;
          worker.postMessage({ type: 'flushSegment' });
        });
        if (workerError) throw new Error(workerError);
      } else {
        if (inflight.length) await Promise.all(inflight);
        inflight = null;
      }

      const r = await fetch('/concerto_finish_segment', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      const d = await r.json();
      if (d.error) throw new Error(`segment ${seg} finish: ${d.error}`);
    }
  } finally {
    if (worker) {
      try { worker.postMessage({ type: 'shutdown' }); } catch (e) {}
      try { worker.terminate(); } catch (e) {}
    }
  }
}

// Status setter used by _runConcertoSegments — must reach the same status
// element startConcertoDownload uses. We re-resolve every call because the
// element may not exist when _runConcertoSegments is first defined.
function setConcertoStatus(msg) {
  const el = document.getElementById('concerto-status');
  if (el) el.textContent = msg;
}

async function startConcertoDownload() {
  if (_concertoDownloading) return;
  if (!state.duration || state.duration <= 0) {
    alert('Load audio and run a trace first.');
    return;
  }

  // Show export popup
  const dur = state.duration || 0;
  const html = `
    <div style="display:flex;flex-direction:column;gap:8px;">
      <div>
        <label style="font-size:11px;color:#888;">Quality:</label>
        <select id="concerto-quality" style="width:100%;margin-top:3px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;">
          <option value="b1" selected>B1: High Quality 4K — HEVC 10-bit CRF 16 + AAC 320k (.mp4) — best for fine detail / mesh</option>
          <option value="b2">B2: High Quality 4K — HEVC 10-bit CRF 16 + lossless WAV (.ts) — best for fine detail / mesh</option>
          <option value="a1">A1: Maximum Quality 4K — HEVC 10-bit CRF 14, very slow (.mp4)</option>
          <option value="a2">A2: Maximum Quality 4K — HEVC 10-bit CRF 14, very slow (.ts)</option>
          <option value="h1">H1: Hardware HEVC (Intel VAAPI) + AAC 320k (.mp4) — fast preview (weaker on fine line/mesh)</option>
          <option value="h2">H2: Hardware HEVC (Intel VAAPI) + lossless WAV (.ts) — fast preview (weaker on fine line/mesh)</option>
          <option value="t1">T1: Test 1080p — HEVC 8-bit CRF 22 + AAC 256k (.mp4)</option>
          <option value="t2">T2: Test 1080p — HEVC 8-bit CRF 22 + lossless WAV (.ts)</option>
        </select>
      </div>
      <div>
        <label style="font-size:11px;color:#888;">Wire format (browser → server):</label>
        <select id="concerto-wire" style="width:100%;margin-top:3px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;">
          <option value="raw" selected>RGBA raw (no compression — stable fps, lossless)</option>
          <option value="png">PNG (lossless, compressed — may slow down over long renders)</option>
          <option value="jpeg">JPEG q=0.92 (faster but slight ringing on fine mesh)</option>
        </select>
      </div>
      <div>
        <label style="font-size:11px;color:#888;">ffmpeg decode threads (PNG only — leave blank for auto):</label>
        <input id="concerto-decode-threads" type="number" min="1" max="64" step="1" value="" placeholder="auto"
               style="width:100%;margin-top:3px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
        <div style="font-size:9px;color:#555;margin-top:2px;">Server caps ffmpeg's CPU so it doesn't starve the browser's encoder. Lower = more CPU for Chrome. Auto ≈ cores/4.</div>
      </div>
      <div>
        <label style="font-size:11px;color:#888;">Save to:</label>
        <div style="display:flex;gap:4px;margin-top:3px;">
          <input id="concerto-path" type="text" value="" placeholder="click Browse to choose…" readonly
                 style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;cursor:pointer;" />
          <button id="concerto-browse-btn" style="padding:4px 8px;font-size:11px;">Browse</button>
        </div>
      </div>
      <div>
        <label style="font-size:11px;color:#888;">Resolution:</label>
        <div style="display:flex;gap:6px;margin-top:3px;">
          <input id="concerto-width" type="number" value="3840" min="640" step="1" placeholder="width"
                 style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
          <span style="color:#555;align-self:center;">\u00D7</span>
          <input id="concerto-height" type="number" value="2160" min="360" step="1" placeholder="height"
                 style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
          <span style="font-size:9px;color:#555;align-self:center;">px</span>
        </div>
      </div>
      <div>
        <label style="font-size:11px;color:#888;">Time range (seconds):</label>
        <div style="display:flex;gap:6px;margin-top:3px;">
          <input id="concerto-from" type="number" value="0" min="0" step="0.1" placeholder="from"
                 style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
          <span style="color:#555;align-self:center;">\u2192</span>
          <input id="concerto-to" type="number" value="${dur.toFixed(1)}" min="0" step="0.1" placeholder="to"
                 style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
        </div>
        <div style="font-size:9px;color:#555;margin-top:2px;">Full duration: ${dur.toFixed(1)}s. Leave as-is for whole piece.</div>
      </div>
      <div style="border-top:1px solid #333; padding-top:8px; margin-top:4px;">
        <label style="font-size:11px;color:#ccc;display:block;margin-bottom:4px;"><b>Outputs</b> (pick any combination):</label>
        <label style="font-size:11px;color:#ccc;display:block;">
          <input id="concerto-out-score" type="checkbox" checked> Score video
        </label>
        <label style="font-size:11px;color:#ccc;display:block;">
          <input id="concerto-meta-video" type="checkbox"> Metadata video (no sound, meta canvas centered)
        </label>
        <label style="font-size:11px;color:#ccc;display:block;">
          <input id="concerto-out-audio" type="checkbox"> Audio (.wav)
        </label>
        <div style="margin-top:6px;padding-left:4px;">
          <label style="font-size:10px;color:#888;display:block;margin-bottom:2px;">Individual viz videos (greyscale, no sound):</label>
          <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
            <input id="concerto-out-timeline" type="checkbox" style="margin:0;">
            <span style="font-size:10px;color:#aaa;width:120px;">Timeline</span>
            <input id="concerto-viz-timeline-w" type="number" value="1920" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
            <span style="font-size:9px;color:#555;">\u00d7</span>
            <input id="concerto-viz-timeline-h" type="number" value="540" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
          </div>
          <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
            <input id="concerto-out-marginal" type="checkbox" style="margin:0;">
            <span style="font-size:10px;color:#aaa;width:120px;">Marginal Gaussians</span>
            <input id="concerto-viz-marginal-w" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
            <span style="font-size:9px;color:#555;">\u00d7</span>
            <input id="concerto-viz-marginal-h" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
          </div>
          <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
            <input id="concerto-out-phase" type="checkbox" style="margin:0;">
            <span style="font-size:10px;color:#aaa;width:120px;">Phase Portrait</span>
            <input id="concerto-viz-phase-w" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
            <span style="font-size:9px;color:#555;">\u00d7</span>
            <input id="concerto-viz-phase-h" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
          </div>
          <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
            <input id="concerto-out-energy" type="checkbox" style="margin:0;">
            <span style="font-size:10px;color:#aaa;width:120px;">Innovation Energy</span>
            <input id="concerto-viz-energy-w" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
            <span style="font-size:9px;color:#555;">\u00d7</span>
            <input id="concerto-viz-energy-h" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
          </div>
          <div style="display:flex;align-items:center;gap:4px;">
            <input id="concerto-out-trajectory" type="checkbox" style="margin:0;">
            <span style="font-size:10px;color:#aaa;width:120px;">State Trajectory</span>
            <input id="concerto-viz-trajectory-w" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
            <span style="font-size:9px;color:#555;">\u00d7</span>
            <input id="concerto-viz-trajectory-h" type="number" value="1080" min="100" step="1" style="width:55px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px;font-size:10px;">
          </div>
        </div>
      </div>
      <div style="border-top:1px solid #333; padding-top:8px; margin-top:4px;">
        <label style="font-size:11px;color:#ccc;">
          <input id="concerto-neutral" type="checkbox"> <b>Performance-neutral</b> (strips tempo/timing expression from audio)
        </label>
        <div style="font-size:9px;color:#555;margin-top:2px;">No accelerando/ritardando, no Kalman timing jitter, no articulation stretch. Pitch/dynamics/FX unchanged.</div>
      </div>
    </div>`;

  const popupPromise = showPopup('Concerto Download — 4K Video', html);

  // Wire browse button
  requestAnimationFrame(() => {
    const browseBtn = document.getElementById('concerto-browse-btn');
    const pathInput = document.getElementById('concerto-path');
    if (browseBtn && pathInput) {
      browseBtn.addEventListener('click', () => {
        const name = (interpState.scorePath || 'concerto').split('/').pop()
                      .replace(/\.ya?ml$/, '') || 'concerto';
        const selQ = document.getElementById('concerto-quality')?.value || 'a1';
        // All *2 quality presets (a2/b2/h2/t2) use the .ts container.
        const ext  = selQ.endsWith('2') ? '.ts' : '.mp4';
        openSaveBrowser((fullPath) => { pathInput.value = fullPath; },
                        name + '_concerto' + ext, ['.mp4', '.ts']);
      });
    }
  });

  const ok = await popupPromise;
  if (!ok) return;

  const quality    = document.getElementById('concerto-quality')?.value || 'b1';
  const wireFormat = document.getElementById('concerto-wire')?.value || 'png';
  // decode_threads: blank/invalid -> omit (server uses its computed default).
  const _dtRaw = document.getElementById('concerto-decode-threads')?.value;
  const decodeThreads = (_dtRaw && !isNaN(parseInt(_dtRaw))) ? parseInt(_dtRaw) : null;
  const outPath    = document.getElementById('concerto-path')?.value.trim();
  if (!outPath) { alert('Please choose a save location.'); return; }

  // Custom resolution
  const userW = parseInt(document.getElementById('concerto-width')?.value) || 3840;
  const userH = parseInt(document.getElementById('concerto-height')?.value) || 2160;

  // Output selection — any combination; at least one must be checked.
  const wantScore   = !!document.getElementById('concerto-out-score')?.checked;
  const wantMeta    = !!document.getElementById('concerto-meta-video')?.checked;
  const wantAudio   = !!document.getElementById('concerto-out-audio')?.checked;
  const wantNeutral = !!document.getElementById('concerto-neutral')?.checked;

  // Individual viz video outputs — each with its own resolution
  const vizOutputs = [
    { id: 'timeline',   mode: 'timeline',   label: 'Timeline' },
    { id: 'marginal',   mode: 'marginal',   label: 'Marginal Gaussians' },
    { id: 'phase',      mode: 'phase',      label: 'Phase Portrait' },
    { id: 'energy',     mode: 'energy',     label: 'Innovation Energy' },
    { id: 'trajectory', mode: 'trajectory', label: 'State Trajectory' },
  ].filter(v => !!document.getElementById('concerto-out-' + v.id)?.checked)
   .map(v => ({
     ...v,
     w: parseInt(document.getElementById('concerto-viz-' + v.id + '-w')?.value) || 1080,
     h: parseInt(document.getElementById('concerto-viz-' + v.id + '-h')?.value) || 1080,
   }));

  const anyOutput = wantScore || wantMeta || wantAudio || vizOutputs.length > 0;
  if (!anyOutput) {
    alert('Select at least one output.');
    return;
  }

  // Time range
  const rangeFrom = parseFloat(document.getElementById('concerto-from')?.value) || 0;
  const rangeTo   = parseFloat(document.getElementById('concerto-to')?.value) || 0;

  const statusEl = document.getElementById('concerto-status');
  const setStatus = (msg) => { if (statusEl) statusEl.textContent = msg; };

  _concertoDownloading = true;
  _concertoCleanMode = true;
  _concertoGreyscaleMode = true;  // all viz renders use greyscale palette
  const dlBtn     = document.getElementById('concerto-download-btn');
  const cancelBtn = document.getElementById('concerto-cancel-btn');
  if (dlBtn)     dlBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = '';
  setStatus('starting render…');

  // Screen Wake Lock: ask the OS to keep the display / GPU active for the
  // duration of the render. Without this, a long 4K encode (minutes) can
  // be stalled by the laptop entering power-save mode. Wake Lock is only
  // available on HTTPS / localhost in Chromium-based browsers; failure
  // here is cosmetic (render still works, just may stall on idle laptop).
  let _wakeLock = null;
  try {
    if (navigator.wakeLock && navigator.wakeLock.request) {
      _wakeLock = await navigator.wakeLock.request('screen');
    }
  } catch (e) { /* ignore — render continues without lock */ }

  // Resolution + framerate
  const isTest = quality.startsWith('t');
  const W   = isTest ? 1920 : userW;
  const H   = isTest ? 1080 : userH;
  const FPS = isTest ? 30 : 60;
  // Use real (audio) duration for frame count — the WAV is in real time
  const fullDur     = state.durationReal || state.duration || 0;
  const startTime   = Math.max(0, Math.min(rangeFrom, fullDur));
  const endTime     = rangeTo > startTime ? Math.min(rangeTo, fullDur) : fullDur;
  const audioDur    = endTime - startTime;
  const totalFrames = Math.ceil(audioDur * FPS);
  const frameDur    = 1.0 / FPS;
  // The offscreen canvas is created (and recreated per segment) inside
  // `_runConcertoSegments` now, so we don't pass one in.

  try {
    // 0. Regenerate the audio via /preview if audio is requested OR if
    //    performance-neutral is on (which means the current PREVIEW_TMP
    //    may not reflect neutral mode). We always re-render when the user
    //    ticks either of those; otherwise assume PREVIEW_TMP is fresh
    //    from the main editor and reuse it.
    if (wantAudio || wantNeutral) {
      setStatus(wantNeutral ? 'rendering neutral audio…' : 'rendering audio…');
      try {
        const body = {
          path: state.filePath,
          score_path: (typeof interpState !== 'undefined' ? interpState.scorePath : null),
          interp: (typeof interpState !== 'undefined') ? {
            golems:   interpState.golems,
            v2config: interpState.v2config,
          } : {},
          performance_neutral: wantNeutral,
        };
        const pr = await fetch('/preview', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body),
        });
        const pd = await pr.json();
        if (pd.error) throw new Error('audio render: ' + (pd.detail || pd.error));
      } catch (e) {
        setStatus('audio render failed: ' + e.message);
        _concertoDownloading = false;
        return;
      }
    }

    // If the user ONLY wants audio, save it and return — no video render.
    if (wantAudio && !wantScore && !wantMeta) {
      setStatus('saving audio…');
      try {
        const sr = await fetch('/save_preview_audio', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ out_path: outPath }),
        });
        const sd = await sr.json();
        if (sd.error) throw new Error(sd.error);
        setStatus('saved → ' + sd.path);
      } catch (e) {
        setStatus('audio save failed: ' + e.message);
      }
      setTimeout(() => setStatus(''), 8000);
      _concertoDownloading = false;
      return;
    }

    // If score video is disabled but meta is enabled, skip the score
    // render entirely — jump to meta below. Otherwise do the score render.
    if (!wantScore) {
      // Just upsize canvases so meta render has them at target size.
      _upsizeSourceCanvases(W, H);
    } else {
    // 1. Start the ffmpeg pipeline for segment 0 (also sets up encode state)
    const startRes = await fetch('/concerto_start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ width: W, height: H, fps: FPS, duration: audioDur,
                             quality, out_path: outPath,
                             time_from: startTime, time_to: endTime,
                             wire_format: wireFormat,
                             ...(decodeThreads != null ? { decode_threads: decodeThreads } : {}),
                             segment_index: 0 })
    });
    const startData = await startRes.json();
    if (startData.error) { setStatus('error: ' + startData.error); _concertoDownloading = false; return; }

    // 2. Upsize source canvases to target resolution for sharp rendering
    _upsizeSourceCanvases(W, H);

    // 3. Render in segments — each segment has its own short-lived ffmpeg
    //    Score compositing in _compositeConcerto reads ONLY `src.score`;
    //    it does NOT read src.timeline or src.viz. So this drawFrame
    //    callback intentionally skips drawKalmanTrace and updateVizPanel,
    //    which otherwise run O(N) per frame and dominate the render as
    //    the trace grows.
    await _runConcertoSegments({
      W, H, FPS, totalFrames, startTime, frameDur, wireFormat,
      mode: 'score', isTest,
      statusLabel: 'rendering',
      drawFrame: () => {
        if (_concertoCleanMode) {
          _drawCleanFrameOverlay();
          _drawCleanScoreOverlay();
        } else {
          if (typeof draw === 'function') draw();
          if (typeof drawScoreOverlay === 'function' && typeof score2Canvas !== 'undefined' && typeof score2Ctx !== 'undefined' && typeof score2View !== 'undefined')
            drawScoreOverlay(score2Canvas, score2Ctx, score2View);
        }
      },
    });

    // If the user cancelled mid-render, _runConcertoSegments returned early
    // leaving the server's ffmpeg open. Tell the server to tear it down and
    // skip both /concerto_finish AND the meta-video pass.
    if (!_concertoDownloading) {
      try {
        await fetch('/concerto_cancel', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({})
        });
      } catch (e) { /* best effort */ }
      setStatus('cancelled');
      return;
    }

    // 4. Finish — server concatenates segments + muxes audio, returns path
    setStatus('encoding video…');
    const finishRes = await fetch('/concerto_finish', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    var finishData = await finishRes.json();
    if (finishData.error) { setStatus('error: ' + finishData.error); }
    else { setStatus('saved → ' + finishData.path); }
    }  // end of "if (wantScore) { ... } else { ... }" branch

    // ── Meta video (metadata canvas centered, no sound) ──────────────────
    if (wantMeta && _concertoDownloading) {
      const metaPath = outPath.replace(/(\.[^.]+)$/, '_meta$1');
      setStatus('starting meta video…');

      const metaStartRes = await fetch('/concerto_start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ width: W, height: H, fps: FPS, duration: audioDur,
                               quality, out_path: metaPath,
                               time_from: startTime, time_to: endTime,
                               wire_format: wireFormat,
                               ...(decodeThreads != null ? { decode_threads: decodeThreads } : {}),
                               no_audio: true,
                               segment_index: 0 })
      });
      const metaStartData = await metaStartRes.json();
      if (metaStartData.error) { setStatus('meta error: ' + metaStartData.error); }
      else {
        await _runConcertoSegments({
          W, H, FPS, totalFrames, startTime, frameDur, wireFormat,
          mode: 'meta', isTest,
          statusLabel: 'meta video',
          drawFrame: () => {
            if (_concertoCleanMode) {
              _drawCleanFrameOverlay();
              _drawCleanScoreOverlay();
            } else {
              if (typeof draw === 'function') draw();
            }
            if (typeof drawScoreOverlay === 'function' && typeof score2Canvas !== 'undefined')
              drawScoreOverlay(score2Canvas, score2Ctx, score2View);
          },
        });

        // Cancel during meta pass — same teardown as the main pass.
        if (!_concertoDownloading) {
          try {
            await fetch('/concerto_cancel', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({})
            });
          } catch (e) { /* best effort */ }
          setStatus('cancelled');
          return;
        }

        setStatus('encoding meta video…');
        const metaFinishRes = await fetch('/concerto_finish', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})
        });
        const metaFinishData = await metaFinishRes.json();
        if (metaFinishData.error) { setStatus('meta error: ' + metaFinishData.error); }
        else {
          // Build a summary of what got saved: score (if any) + meta.
          const scorePart = (typeof finishData !== 'undefined' && finishData && !finishData.error) ? (finishData.path + ' + ') : '';
          setStatus('saved → ' + scorePart + metaFinishData.path);
        }
      }
    }

    // ── Individual viz videos (greyscale, no sound) ──────────────────────
    for (const vizOut of vizOutputs) {
      if (!_concertoDownloading) break;
      const vizPath = outPath.replace(/(\.[^.]+)$/, `_${vizOut.id}$1`);
      setStatus(`starting ${vizOut.label} video…`);

      const vizStartRes = await fetch('/concerto_start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ width: vizOut.w, height: vizOut.h, fps: FPS,
                               duration: audioDur, quality, out_path: vizPath,
                               time_from: startTime, time_to: endTime,
                               wire_format: wireFormat,
                               ...(decodeThreads != null ? { decode_threads: decodeThreads } : {}),
                               no_audio: true,
                               segment_index: 0 })
      });
      const vizStartData = await vizStartRes.json();
      if (vizStartData.error) { setStatus(`${vizOut.label} error: ` + vizStartData.error); continue; }

      await _runConcertoSegments({
        W: vizOut.w, H: vizOut.h, FPS, totalFrames, startTime, frameDur,
        wireFormat, mode: vizOut.mode, isTest,
        statusLabel: vizOut.label,
        drawFrame: () => {
          // Viz modes draw directly inside _compositeConcerto using
          // _lastTraceData + _concertoMaxT for progressive reveal.
          // drawKalmanTrace is needed only for 'timeline' mode (it writes
          // to src.timeline which _compositeConcerto reads).
          if (vizOut.mode === 'timeline') {
            if (typeof drawKalmanTrace === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
              drawKalmanTrace(_lastTraceData);
          }
        },
      });

      if (!_concertoDownloading) {
        try { await fetch('/concerto_cancel', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); } catch(e){}
        setStatus('cancelled');
        return;
      }

      setStatus(`encoding ${vizOut.label}…`);
      const vizFinRes = await fetch('/concerto_finish', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      const vizFinData = await vizFinRes.json();
      if (vizFinData.error) { setStatus(`${vizOut.label} error: ` + vizFinData.error); }
      else { setStatus(`saved → ${vizFinData.path}`); }
    }

    // ── Audio (.wav) — save a copy of PREVIEW_TMP alongside the videos.
    //    Only reached when at least one video was rendered (otherwise the
    //    audio-only fast path above already handled and returned).
    if (wantAudio && _concertoDownloading) {
      try {
        setStatus('saving audio…');
        const sr = await fetch('/save_preview_audio', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ out_path: outPath }),
        });
        const sd = await sr.json();
        if (sd.error) setStatus('audio save error: ' + sd.error);
        else setStatus('saved → ' + sd.path);
      } catch (e) {
        setStatus('audio save failed: ' + e.message);
      }
    }

    setTimeout(() => setStatus(''), 8000);

  } catch (e) {
    setStatus('download failed: ' + e);
  } finally {
    _concertoMaxT = Infinity;
    if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = -1;
    _concertoCleanMode = false;
    _concertoGreyscaleMode = false;
    _restoreSourceCanvases();
    // Redraw at normal size to restore the editor view
    if (typeof draw === 'function') draw();
    _concertoDownloading = false;
    if (dlBtn)     dlBtn.style.display = '';
    if (cancelBtn) cancelBtn.style.display = 'none';
    if (_wakeLock) { try { await _wakeLock.release(); } catch (e) {} _wakeLock = null; }
  }
}

function cancelConcertoDownload() {
  _concertoDownloading = false;
}

// ─── Keyboard / fullscreen exit ──────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && _concertoActive) {
    e.preventDefault();
    exitConcertoView();
  }
});
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement && _concertoActive) {
    exitConcertoView();
  }
});

// ─── Wire buttons ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const viewBtn = document.getElementById('concerto-view-btn');
  if (viewBtn) viewBtn.addEventListener('click', enterConcertoView);

  const dlBtn = document.getElementById('concerto-download-btn');
  if (dlBtn) dlBtn.addEventListener('click', startConcertoDownload);

  const cancelBtn = document.getElementById('concerto-cancel-btn');
  if (cancelBtn) cancelBtn.addEventListener('click', cancelConcertoDownload);
});
