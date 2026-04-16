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
// `drawFrame(realT, scoreT)` is called per-frame to update the source
// canvases before compositing. `mode` is passed through to _compositeConcerto.
async function _runConcertoSegments(opts) {
  const { W, H, FPS, totalFrames, startTime, frameDur,
          offscreen, drawFrame, mode, isTest, statusLabel } = opts;

  const SEG_DURATION = 30;                               // seconds per segment
  const SEG_FRAMES   = SEG_DURATION * FPS;               // frames per segment
  const numSegments  = Math.max(1, Math.ceil(totalFrames / SEG_FRAMES));
  const MAX_INFLIGHT = 2;                                // concurrent uploads
  const BATCH_SIZE   = 10;                               // frames per HTTP request
  const JPEG_QUALITY = 0.95;                             // visually transparent
  const renderStart  = performance.now();
  let totalRendered  = 0;

  for (let seg = 0; seg < numSegments; seg++) {
    if (!_concertoDownloading) return;

    // Spawn next segment's ffmpeg (segment 0 was started by the caller).
    if (seg > 0) {
      const r = await fetch('/concerto_start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ segment_index: seg })
      });
      const d = await r.json();
      if (d.error) throw new Error(`segment ${seg} start: ${d.error}`);
    }

    const segStartFrame = seg * SEG_FRAMES;
    const segEndFrame   = Math.min(segStartFrame + SEG_FRAMES, totalFrames);
    const segCount      = segEndFrame - segStartFrame;

    let inflight      = [];
    let batchBuf      = [];
    let batchStartIdx = 0;   // per-segment frame index (each segment's ffmpeg sees 0..N-1)

    for (let sf = 0; sf < segCount; sf++) {
      if (!_concertoDownloading) return;
      const f      = segStartFrame + sf;
      const realT  = startTime + f * frameDur;
      const scoreT = (typeof realToScore === 'function') ? realToScore(realT) : realT;
      state.currentTime = scoreT;
      _concertoMaxT = scoreT;
      if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = realT;

      drawFrame(realT, scoreT);
      _compositeConcerto(offscreen, W, H, mode);

      // JPEG-encode the frame off the main thread (browser uses an internal
      // worker for toBlob). At 4K q=0.95, a frame is ~1-3 MB instead of
      // 33 MB raw RGBA — 10-30× less data. Quality loss is irrelevant since
      // the final HEVC encode dominates output quality.
      const blobJpeg = await new Promise(r => offscreen.toBlob(r, 'image/jpeg', JPEG_QUALITY));
      if (!blobJpeg) throw new Error('toBlob returned null');
      batchBuf.push(blobJpeg);

      if (batchBuf.length >= BATCH_SIZE || sf === segCount - 1) {
        // Concatenate the per-frame JPEG Blobs into one body, plus a
        // parallel `lengths` form field so the server can split (JPEGs
        // are variable-size, unlike raw RGBA).
        const lengths = batchBuf.map(b => b.size).join(',');
        const blob = new Blob(batchBuf, { type: 'application/octet-stream' });
        const fd = new FormData();
        fd.append('frames', blob, 'batch.mjpeg');
        fd.append('start_index', String(batchStartIdx));
        fd.append('count', String(batchBuf.length));
        fd.append('lengths', lengths);

        const upload = fetch('/concerto_frames', { method: 'POST', body: fd })
          .then(() => { inflight = inflight.filter(p => p !== upload); });
        inflight.push(upload);

        batchStartIdx = sf + 1;
        batchBuf = [];

        // Await OLDEST inflight when full — caps in-flight memory and
        // prevents the renderer from racing ahead of the encoder.
        if (inflight.length >= MAX_INFLIGHT) await inflight[0];
      }

      totalRendered = f + 1;
      if (sf % 10 === 0 || sf === segCount - 1) {
        const elapsed = (performance.now() - renderStart) / 1000;
        const fps     = totalRendered / Math.max(elapsed, 0.001);
        const remain  = (totalFrames - totalRendered) / Math.max(fps, 1);
        const pct     = Math.round(totalRendered / totalFrames * 100);
        const eta     = remain < 60
          ? `${Math.round(remain)}s`
          : `${Math.floor(remain / 60)}m ${Math.round(remain % 60)}s`;
        const res     = isTest ? '1080p' : '4K';
        setConcertoStatus(`${statusLabel} ${res}: seg ${seg + 1}/${numSegments} ${pct}% (${Math.round(fps)} fps) — ETA ${eta}`);
      }

      if (sf % 5 === 0) await new Promise(r => setTimeout(r, 0));
    }

    // Drain remaining uploads for this segment, then close its ffmpeg.
    if (inflight.length) await Promise.all(inflight);
    inflight = null;  // help GC release any retained references

    const r = await fetch('/concerto_finish_segment', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    const d = await r.json();
    if (d.error) throw new Error(`segment ${seg} finish: ${d.error}`);
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
          <option value="b1" selected>B1: High Quality 4K — HEVC 10-bit CRF 16 + AAC 320k (.mp4)</option>
          <option value="b2">B2: High Quality 4K — HEVC 10-bit CRF 16 + lossless WAV (.ts)</option>
          <option value="a1">A1: Maximum Quality 4K — HEVC 10-bit CRF 14, very slow (.mp4)</option>
          <option value="a2">A2: Maximum Quality 4K — HEVC 10-bit CRF 14, very slow (.ts)</option>
          <option value="t1">T1: Test 1080p — HEVC 8-bit CRF 22 + AAC 256k (.mp4)</option>
          <option value="t2">T2: Test 1080p — HEVC 8-bit CRF 22 + lossless WAV (.ts)</option>
        </select>
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
      <div>
        <label style="font-size:11px;color:#888;">
          <input id="concerto-meta-video" type="checkbox"> Also export metadata video (no sound, meta canvas centered)
        </label>
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
        const ext  = (selQ === 'a2' || selQ === 'b2' || selQ === 't2') ? '.ts' : '.mp4';
        openSaveBrowser((fullPath) => { pathInput.value = fullPath; },
                        name + '_concerto' + ext, ['.mp4', '.ts']);
      });
    }
  });

  const ok = await popupPromise;
  if (!ok) return;

  const quality  = document.getElementById('concerto-quality')?.value || 'b1';
  const outPath  = document.getElementById('concerto-path')?.value.trim();
  if (!outPath) { alert('Please choose a save location.'); return; }

  // Custom resolution
  const userW = parseInt(document.getElementById('concerto-width')?.value) || 3840;
  const userH = parseInt(document.getElementById('concerto-height')?.value) || 2160;
  const wantMeta = document.getElementById('concerto-meta-video')?.checked;

  // Time range
  const rangeFrom = parseFloat(document.getElementById('concerto-from')?.value) || 0;
  const rangeTo   = parseFloat(document.getElementById('concerto-to')?.value) || 0;

  const statusEl = document.getElementById('concerto-status');
  const setStatus = (msg) => { if (statusEl) statusEl.textContent = msg; };

  _concertoDownloading = true;
  _concertoCleanMode = true;
  const dlBtn     = document.getElementById('concerto-download-btn');
  const cancelBtn = document.getElementById('concerto-cancel-btn');
  if (dlBtn)     dlBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = '';
  setStatus('starting render…');

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
  const offscreen = document.createElement('canvas');
  offscreen.width  = W;
  offscreen.height = H;
  // We pull pixels via canvas.toBlob (JPEG), not getImageData, so a
  // GPU-backed canvas is fine here — drawImage compositing benefits from
  // hardware acceleration and toBlob's internal readback is well optimised.
  // _compositeConcerto opens its own context against `offscreen` per frame.

  try {
    // 1. Start the ffmpeg pipeline for segment 0 (also sets up encode state)
    const startRes = await fetch('/concerto_start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ width: W, height: H, fps: FPS, duration: audioDur,
                             quality, out_path: outPath,
                             time_from: startTime, time_to: endTime,
                             segment_index: 0 })
    });
    const startData = await startRes.json();
    if (startData.error) { setStatus('error: ' + startData.error); _concertoDownloading = false; return; }

    // 2. Upsize source canvases to target resolution for sharp rendering
    _upsizeSourceCanvases(W, H);

    // 3. Render in segments — each segment has its own short-lived ffmpeg
    await _runConcertoSegments({
      W, H, FPS, totalFrames, startTime, frameDur,
      offscreen, mode: 'score', isTest,
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
        if (typeof drawKalmanTrace === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
          drawKalmanTrace(_lastTraceData);
        if (typeof updateVizPanel === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
          updateVizPanel(_lastTraceData);
      },
    });

    // 4. Finish — server concatenates segments + muxes audio, returns path
    setStatus('encoding video…');
    const finishRes = await fetch('/concerto_finish', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    const finishData = await finishRes.json();
    if (finishData.error) { setStatus('error: ' + finishData.error); }
    else { setStatus('saved → ' + finishData.path); }

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
                               no_audio: true,
                               segment_index: 0 })
      });
      const metaStartData = await metaStartRes.json();
      if (metaStartData.error) { setStatus('meta error: ' + metaStartData.error); }
      else {
        await _runConcertoSegments({
          W, H, FPS, totalFrames, startTime, frameDur,
          offscreen, mode: 'meta', isTest,
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

        setStatus('encoding meta video…');
        const metaFinishRes = await fetch('/concerto_finish', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})
        });
        const metaFinishData = await metaFinishRes.json();
        if (metaFinishData.error) { setStatus('meta error: ' + metaFinishData.error); }
        else { setStatus('saved → ' + finishData.path + ' + ' + metaFinishData.path); }
      }
    }

    setTimeout(() => setStatus(''), 8000);

  } catch (e) {
    setStatus('download failed: ' + e);
  } finally {
    _concertoMaxT = Infinity;
    if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = -1;
    _concertoCleanMode = false;
    _restoreSourceCanvases();
    // Redraw at normal size to restore the editor view
    if (typeof draw === 'function') draw();
    _concertoDownloading = false;
    if (dlBtn)     dlBtn.style.display = '';
    if (cancelBtn) cancelBtn.style.display = 'none';
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
