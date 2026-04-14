// ─── Concerto View + Concerto Download ───────────────────────────────────────
// Depends on: state.js, draw.js (frameCanvas, score2Canvas), viz-panel.js,
//             kalman-trace.js, playback.js, interpreter.js, filebrowser.js (openSaveBrowser)

let _concertoActive = false;
let _concertoRaf    = null;

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
  _concertoMaxT = state.currentTime;
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

function _compositeConcerto(target, W, H) {
  if (!target) return;
  const ctx = target.getContext('2d');
  W = W || target.width;
  H = H || target.height;

  const src = _getSourceCanvases();

  // ~3mm gap between panels (12px at 4K, scales proportionally)
  const gap = Math.round(W * 0.003);

  const vizW  = Math.floor(W * _CONCERTO_VIZ_RATIO) - gap;
  const leftW = W - vizW - gap * 2;  // gap on both sides of the vertical split
  const scoreH    = Math.floor(H * _LEFT_SCORE_RATIO) - gap;
  const metaH     = Math.floor(H * _LEFT_META_RATIO) - gap;
  const timelineH = H - scoreH - metaH - gap * 3;

  // Clear — dark grey background (visible as the gap between panels)
  ctx.fillStyle = '#222';
  ctx.fillRect(0, 0, W, H);

  // Score image — top-left
  if (src.score && src.score.width > 0 && src.score.height > 0) {
    ctx.drawImage(src.score, gap, gap, leftW, scoreH);
  }

  // Metadata image — middle-left
  if (src.meta && src.meta.width > 0 && src.meta.height > 0) {
    ctx.drawImage(src.meta, gap, gap * 2 + scoreH, leftW, metaH);
  }

  // Dimension timeline — bottom-left
  if (src.timeline && src.timeline.width > 0 && src.timeline.height > 0) {
    ctx.drawImage(src.timeline, gap, gap * 3 + scoreH + metaH, leftW, timelineH);
  }

  // Visualization — right column (full height, inset by gap)
  if (src.viz && src.viz.width > 0 && src.viz.height > 0) {
    ctx.drawImage(src.viz, gap + leftW + gap, gap, vizW, H - gap * 2);
  }
  ctx.beginPath();
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

  const quality = document.getElementById('concerto-quality')?.value || 'top';
  const outPath = document.getElementById('concerto-path')?.value.trim();
  if (!outPath) { alert('Please choose a save location.'); return; }

  // Time range
  const rangeFrom = parseFloat(document.getElementById('concerto-from')?.value) || 0;
  const rangeTo   = parseFloat(document.getElementById('concerto-to')?.value) || 0;

  const statusEl = document.getElementById('concerto-status');
  const setStatus = (msg) => { if (statusEl) statusEl.textContent = msg; };

  _concertoDownloading = true;
  const dlBtn     = document.getElementById('concerto-download-btn');
  const cancelBtn = document.getElementById('concerto-cancel-btn');
  if (dlBtn)     dlBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = '';
  setStatus('starting render…');

  // Resolution + framerate: 4K 60fps for top quality, 1080p 30fps for test
  const isTest = quality.startsWith('t');
  const W   = isTest ? 1920 : 3840;
  const H   = isTest ? 1080 : 2160;
  const FPS = isTest ? 30 : 60;
  // Use real (audio) duration for frame count — the WAV is in real time
  const fullDur     = state.durationReal || state.duration || 0;
  const startTime   = Math.max(0, Math.min(rangeFrom, fullDur));
  const endTime     = rangeTo > startTime ? Math.min(rangeTo, fullDur) : fullDur;
  const audioDur    = endTime - startTime;
  const totalFrames = Math.ceil(audioDur * FPS);
  const frameDur    = 1.0 / FPS;
  const BATCH_SIZE  = 10;  // frames per HTTP request

  const offscreen = document.createElement('canvas');
  offscreen.width  = W;
  offscreen.height = H;
  const offCtx = offscreen.getContext('2d');

  try {
    // 1. Start the ffmpeg pipeline on the server
    const startRes = await fetch('/concerto_start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ width: W, height: H, fps: FPS, duration: audioDur,
                             quality, out_path: outPath,
                             time_from: startTime, time_to: endTime })
    });
    const startData = await startRes.json();
    if (startData.error) { setStatus('error: ' + startData.error); _concertoDownloading = false; return; }

    // 2. Upsize source canvases to target resolution for sharp rendering
    _upsizeSourceCanvases(W, H);

    // 3. Render frame by frame — raw RGBA, batched uploads
    const renderStart = performance.now();
    const MAX_INFLIGHT = 3;
    let inflight = [];
    const frameSize = W * H * 4;  // bytes per raw RGBA frame
    let batchBuf = [];  // accumulated raw frame buffers
    let batchStartIdx = 0;

    for (let f = 0; f < totalFrames; f++) {
      if (!_concertoDownloading) { setStatus('cancelled'); break; }

      const realT  = startTime + f * frameDur;
      // Convert real (audio) time to score time so cursor position matches the audio
      const scoreT = (typeof realToScore === 'function') ? realToScore(realT) : realT;
      state.currentTime = scoreT;
      _concertoMaxT = scoreT;
      if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = realT;

      // Redraw all source canvases at this time
      if (typeof draw === 'function') draw();
      // Force metadata canvas draw even if panel isn't "visible" in the composer
      if (typeof drawScoreOverlay === 'function' && typeof score2Canvas !== 'undefined' && typeof score2Ctx !== 'undefined' && typeof score2View !== 'undefined')
        drawScoreOverlay(score2Canvas, score2Ctx, score2View);
      if (typeof drawKalmanTrace === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
        drawKalmanTrace(_lastTraceData);
      if (typeof updateVizPanel === 'function' && typeof _lastTraceData !== 'undefined' && _lastTraceData)
        updateVizPanel(_lastTraceData);

      // Composite into offscreen canvas
      _compositeConcerto(offscreen, W, H);

      // Extract raw RGBA
      const imageData = offCtx.getImageData(0, 0, W, H);
      batchBuf.push(new Uint8Array(imageData.data.buffer));

      // Flush batch when full or last frame
      if (batchBuf.length >= BATCH_SIZE || f === totalFrames - 1) {
        const combined = new Uint8Array(batchBuf.length * frameSize);
        for (let b = 0; b < batchBuf.length; b++) {
          combined.set(batchBuf[b], b * frameSize);
        }
        const blob = new Blob([combined], { type: 'application/octet-stream' });
        const formData = new FormData();
        formData.append('frames', blob, 'batch.raw');
        formData.append('start_index', String(batchStartIdx));
        formData.append('count', String(batchBuf.length));

        const upload = fetch('/concerto_frames', { method: 'POST', body: formData })
          .then(() => { inflight = inflight.filter(p => p !== upload); });
        inflight.push(upload);

        batchStartIdx = f + 1;
        batchBuf = [];

        // Throttle
        if (inflight.length >= MAX_INFLIGHT) {
          await Promise.race(inflight);
        }
      }

      // Progress + time estimate
      if (f % 10 === 0 || f === totalFrames - 1) {
        const elapsed = (performance.now() - renderStart) / 1000;
        const fps     = (f + 1) / elapsed;
        const remain  = (totalFrames - f - 1) / fps;
        const pct     = Math.round((f + 1) / totalFrames * 100);
        const eta     = remain < 60
          ? `${Math.round(remain)}s`
          : `${Math.floor(remain / 60)}m ${Math.round(remain % 60)}s`;
        const res     = isTest ? '1080p' : '4K';
        setStatus(`rendering ${res}: ${pct}% (${Math.round(fps)} fps) — ETA ${eta}`);
      }

      // Yield to browser every 5 frames
      if (f % 5 === 0) await new Promise(r => setTimeout(r, 0));
    }

    // Wait for remaining uploads
    if (inflight.length) await Promise.all(inflight);

    // 3. Finish — server closes ffmpeg, muxes audio, returns path
    setStatus('encoding video…');
    const finishRes = await fetch('/concerto_finish', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    const finishData = await finishRes.json();
    if (finishData.error) { setStatus('error: ' + finishData.error); }
    else { setStatus('saved → ' + finishData.path); setTimeout(() => setStatus(''), 8000); }

  } catch (e) {
    setStatus('download failed: ' + e);
  } finally {
    _concertoMaxT = Infinity;  // restore full view
    if (typeof _vizCurrentT !== 'undefined') _vizCurrentT = -1;
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
