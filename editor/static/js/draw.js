// Normalize dynamics mark field (YAML uses 'marking', JS state uses 'mark')
function _dmark(d) { return d.mark || d.marking || '?'; }

// ─── Score image viewer state ─────────────────────────────────────────────────
const scoreView = {
  img: null,       // HTMLImageElement; null = not loaded
  path: "",
  start: 0,        // audio time (s) at left edge of score image
  end: 0,          // audio time (s) at right edge
  scale: 1,        // zoom (>1 = zoomed in)
  panOffset: 0,    // manual horizontal pan in display pixels (reset on seek)
};
let viewMode = "score"; // "score" | "video"

function scoreDisplayWidth() {
  if (!scoreView.img || !scoreView.img.naturalHeight) return frameCanvas.width;
  return scoreView.img.naturalWidth
       * (frameCanvas.height / scoreView.img.naturalHeight)
       * scoreView.scale;
}
function tToScoreDisplayX(t) {
  const dur = scoreView.end - scoreView.start;
  if (dur <= 0) return 0;
  return ((t - scoreView.start) / dur) * scoreDisplayWidth();
}
function scoreScrollLeft() {
  return tToScoreDisplayX(state.currentTime) - frameCanvas.width / 2 - scoreView.panOffset;
}

// ─── Second image panel state ─────────────────────────────────────────────────
const score2Canvas = document.getElementById("score2-canvas");
const score2Ctx    = score2Canvas.getContext("2d");
const score2View   = { img: null, path: "", start: 0, end: 0, scale: 1, panOffset: 0 };

// Returns score annotation data: interpState.scoreData when Interpreter is active, else state
function _sdd() {
  if (typeof _activeWorkspace !== 'undefined' && _activeWorkspace === 'interpreter'
      && typeof interpState !== 'undefined' && interpState.scoreData)
    return interpState.scoreData;
  return state;
}

// Resize score2Canvas to match its container
function resizeScore2Canvas() {
  const cont = document.getElementById("score2-container");
  score2Canvas.width  = cont.clientWidth  || 800;
  score2Canvas.height = cont.clientHeight || 200;
  drawScoreOverlay(score2Canvas, score2Ctx, score2View);
}

const RULER_H = 22;
const EVENT_LANE_H = 30;

function resizeCanvas() {
  const r = canvasWrap.getBoundingClientRect();
  canvas.width  = r.width;
  canvas.height = r.height;
  // frame canvas is sized by ResizeObserver below
  draw();
}
window.addEventListener("resize", resizeCanvas);
setTimeout(resizeCanvas, 50);

// Size the frame canvas whenever its container changes (handles initial layout)
const frameResizeObserver = new ResizeObserver(() => {
  const p = frameCanvas.parentElement;
  if (p.offsetWidth > 0) {
    frameCanvas.width  = p.offsetWidth;
    frameCanvas.height = p.offsetHeight;
    drawFrameOverlay();
  }
});
frameResizeObserver.observe(frameCanvas.parentElement);

// Scale-corrected mouse X/Y for the frame canvas (raw canvas pixels)
function frameMouseX(e) {
  const r = frameCanvas.getBoundingClientRect();
  if (!r.width || !frameCanvas.width) return 0;
  return (e.clientX - r.left) * (frameCanvas.width / r.width);
}
function frameMouseY(e) {
  const r = frameCanvas.getBoundingClientRect();
  if (!r.height || !frameCanvas.height) return 0;
  return (e.clientY - r.top) * (frameCanvas.height / r.height);
}

// ─── Frame zoom / pan state (CSS-based — no canvas drawing involvement) ───────
const fz = { scale: 1, tx: 0, ty: 0 };

function applyFZ() {
  document.getElementById("frame-inner").style.transform =
    `translate(${fz.tx}px,${fz.ty}px) scale(${fz.scale})`;
}

function clampFZ() {
  const c = document.getElementById("frame-container");
  const W = c.offsetWidth, H = c.offsetHeight;
  fz.tx = Math.min(0, Math.max(W * (1 - fz.scale), fz.tx));
  fz.ty = Math.min(0, Math.max(H * (1 - fz.scale), fz.ty));
}

function resetFZ() {
  fz.scale = 1; fz.tx = 0; fz.ty = 0;
  applyFZ();
}

// ─── Time → pixel helpers ──────────────────────────────────────────────────
// Waveform timeline zoom state
const waveView = { zoom: 1, scrollT: 0 };

function waveVisible() { return state.duration / waveView.zoom; }

function tToX(t) {
  if (!state.duration) return 0;
  return ((t - waveView.scrollT) / waveVisible()) * canvas.width;
}
function xToT(x) {
  if (!state.duration) return 0;
  return Math.max(0, Math.min(state.duration,
    waveView.scrollT + (x / canvas.width) * waveVisible()));
}

// ─── Draw ─────────────────────────────────────────────────────────────────────
function draw() {
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  // Background
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, W, H);

  // Ruler
  ctx.fillStyle = "#161616";
  ctx.fillRect(0, 0, W, RULER_H);
  ctx.strokeStyle = "#2a2a2a";
  ctx.beginPath(); ctx.moveTo(0, RULER_H); ctx.lineTo(W, RULER_H); ctx.stroke();
  drawRuler(W);

  // Event lane (bottom strip)
  const laneY = H - EVENT_LANE_H;
  ctx.fillStyle = "#0e0e0e";
  ctx.fillRect(0, laneY, W, EVENT_LANE_H);
  ctx.strokeStyle = "#222";
  ctx.lineWidth = 1; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(0, laneY); ctx.lineTo(W, laneY); ctx.stroke();

  const wH = H - RULER_H - EVENT_LANE_H;
  const midY = RULER_H + wH / 2;

  // Time grid (behind everything, aligned to ruler ticks)
  if (state.duration) {
    const step = niceStep(state.duration / 10);
    ctx.strokeStyle = "#191919";
    ctx.lineWidth = 1; ctx.setLineDash([]);
    for (let t = step; t < state.duration; t += step) {
      const x = tToX(t);
      ctx.beginPath(); ctx.moveTo(x, RULER_H); ctx.lineTo(x, H); ctx.stroke();
    }
  }

  // Sample regions
  for (const [name, s] of Object.entries(_sdd().samples)) {
    const x1 = tToX(s.from), x2 = tToX(s.to);
    ctx.fillStyle = hexAlpha(s.color, 0.12);
    ctx.fillRect(x1, RULER_H, x2 - x1, wH);
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, laneY); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, RULER_H); ctx.lineTo(x2, laneY); ctx.stroke();
    ctx.fillStyle = hexAlpha(s.color, 0.8);
    ctx.font = "10px 'Courier New', monospace";
    ctx.fillText("[" + name + "]", x1 + 3, RULER_H + 13);
  }

  // Dynamic ranges (crescendo/decrescendo)
  for (const d of _sdd().dynamics) {
    if (d.from !== undefined && d.to !== undefined) {
      const x1 = tToX(d.from), x2 = tToX(d.to);
      const col = _dmark(d) === "crescendo" ? "#337755" : "#775533";
      ctx.fillStyle = hexAlpha(col, 0.18);
      ctx.fillRect(x1, RULER_H, x2 - x1, wH);
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(x1, midY); ctx.lineTo(x2, midY); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = hexAlpha(col, 0.9);
      ctx.font = "10px 'Courier New', monospace";
      ctx.fillText(_dmark(d), x1 + 3, midY - 4);
    }
  }

  // Tempo ranges
  for (const tp of _sdd().tempo) {
    const x1 = tToX(tp.from), x2 = tToX(tp.to);
    const col = tp.mark === "accelerando" ? "#aa7722" : "#227799";
    ctx.fillStyle = hexAlpha(col, 0.16);
    ctx.fillRect(x1, RULER_H, x2 - x1, wH);
    ctx.strokeStyle = col;
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 4]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H + 6); ctx.lineTo(x2, RULER_H + 6); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = hexAlpha(col, 0.9);
    ctx.font = "10px 'Courier New', monospace";
    ctx.fillText(tp.mark + (tp.factor ? " ×" + tp.factor : ""), x1 + 3, RULER_H + 17);
  }

  // FX zones
  for (const fz of _sdd().fxRanges) {
    const x1 = tToX(fz.from), x2 = tToX(fz.to);
    const col = "#8844cc";
    ctx.fillStyle = hexAlpha(col, 0.14);
    ctx.fillRect(x1, RULER_H, x2 - x1, wH);
    ctx.strokeStyle = col;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, laneY); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, RULER_H); ctx.lineTo(x2, laneY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = hexAlpha(col, 0.9);
    ctx.font = "10px 'Courier New', monospace";
    const fxLabel = fz.fx.map(f => f.type).join("+");
    ctx.fillText("fx:" + fxLabel, x1 + 3, laneY - 4);
  }

  // Phrase markers
  const PHRASE_COL = "#8a6abf";
  for (const ph of _sdd().phrases) {
    const x1 = tToX(ph.from), x2 = tToX(ph.to);
    // Subtle fill only in top strip
    ctx.fillStyle = hexAlpha(PHRASE_COL, 0.10);
    ctx.fillRect(x1, RULER_H, x2 - x1, wH);
    // Solid vertical bars at edges
    ctx.strokeStyle = hexAlpha(PHRASE_COL, 0.8);
    ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, laneY); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, RULER_H); ctx.lineTo(x2, laneY); ctx.stroke();
    // Top bracket line
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x1, RULER_H + 2); ctx.lineTo(x2, RULER_H + 2); ctx.stroke();
    // Label
    ctx.fillStyle = hexAlpha(PHRASE_COL, 0.95);
    ctx.font = "10px 'Courier New', monospace";
    ctx.fillText(ph.label, x1 + 4, RULER_H + 13);
  }

  // Note relationship markers on waveform
  for (const nr of _sdd().noteRel) {
    const x1 = tToX(nr.from), x2 = tToX(nr.to ?? nr.from);
    const col = nr.type === "glissando" ? "#44aadd" : "#44ddaa";
    ctx.strokeStyle = hexAlpha(col, 0.75); ctx.lineWidth = 1.5;
    ctx.setLineDash(nr.type === "glissando" ? [4,3] : []);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, laneY); ctx.stroke();
    if (nr.to) { ctx.beginPath(); ctx.moveTo(x2, RULER_H); ctx.lineTo(x2, laneY); ctx.stroke(); }
    ctx.setLineDash([]);
    ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "9px 'Courier New', monospace";
    ctx.fillText(nr.type === "glissando" ? "gliss." : "arp.", x1 + 2, RULER_H + 24);
  }

  // Articulation markers on waveform
  const ART_WAVE_COL = { staccato: "#ffaa44", legato: "#44ffaa", fermata: "#ff88cc", accent: "#ff6644" };
  for (const ar of _sdd().articulations) {
    const col = ART_WAVE_COL[ar.type] || "#aaa";
    const xa = tToX(ar.t ?? ar.from);
    ctx.strokeStyle = hexAlpha(col, 0.7); ctx.lineWidth = 1.5; ctx.setLineDash([2,3]);
    ctx.beginPath(); ctx.moveTo(xa, RULER_H); ctx.lineTo(xa, laneY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "9px 'Courier New', monospace";
    ctx.fillText(ar.type[0].toUpperCase(), xa + 2, RULER_H + 36);
  }

  // Waveform bars
  if (state.waveform.length > 0) {
    const barW = Math.max(1, W / state.waveform.length);
    ctx.fillStyle = "#3a5a4a";
    for (let i = 0; i < state.waveform.length; i++) {
      const x = (i / state.waveform.length) * W;
      const amp = state.waveform[i] * (wH * 0.45);
      ctx.fillRect(x, midY - amp, barW, amp * 2);
    }
    // Center line
    ctx.strokeStyle = "#2a3a30";
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(0, midY); ctx.lineTo(W, midY); ctx.stroke();
  } else {
    ctx.fillStyle = "#222";
    ctx.fillRect(0, midY - 1, W, 2);
    ctx.fillStyle = "#2a2a2a";
    ctx.font = "12px 'Courier New', monospace";
    ctx.textAlign = "center";
    ctx.fillText("load a file to see waveform", W / 2, midY + 4);
    ctx.textAlign = "left";
  }

  // Event clips (drawn in the event lane as colored blocks)
  ctx.font = "9px 'Courier New', monospace";
  for (const ev of _sdd().events) {
    const col = (_sdd().samples[ev.sample] || {}).color || "#aaa";
    const samp = _sdd().samples[ev.sample];
    const rawDur = samp ? (samp.to - samp.from) : 0.5;
    const speed = typeof ev.speed === "number" ? ev.speed : 1.0;
    const clipDur = rawDur / speed;
    const x1 = tToX(ev.t);
    const x2 = tToX(ev.t + clipDur);
    const bw = Math.max(2, x2 - x1);
    // thin trigger line up through waveform area
    ctx.strokeStyle = hexAlpha(col, 0.35);
    ctx.lineWidth = 1; ctx.setLineDash([2, 3]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, laneY); ctx.stroke();
    ctx.setLineDash([]);
    // clip block in lane
    ctx.fillStyle = hexAlpha(col, 0.28);
    ctx.fillRect(x1, laneY + 2, bw, EVENT_LANE_H - 4);
    ctx.strokeStyle = hexAlpha(col, 0.8);
    ctx.lineWidth = 1;
    ctx.strokeRect(x1, laneY + 2, bw, EVENT_LANE_H - 4);
    // label clipped to block width
    ctx.save();
    ctx.beginPath(); ctx.rect(x1 + 1, laneY + 2, bw - 2, EVENT_LANE_H - 4); ctx.clip();
    ctx.fillStyle = hexAlpha(col, 0.95);
    ctx.fillText("▶" + ev.sample, x1 + 4, laneY + EVENT_LANE_H / 2 + 4);
    ctx.restore();
  }

  // Dynamic point marks
  for (const d of _sdd().dynamics) {
    if (d.t !== undefined) {
      const x = tToX(d.t);
      const col = DYNAMIC_COLORS[_dmark(d)] || "#aaa";
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(x, RULER_H); ctx.lineTo(x, H); ctx.stroke();
      ctx.fillStyle = col;
      ctx.font = "10px 'Courier New', monospace";
      ctx.fillText(_dmark(d), x + 3, laneY - 4);
    }
  }

  // Cursor line
  if (state.duration > 0) {
    const cx = tToX(state.currentTime);
    ctx.strokeStyle = "rgba(255,255,255,0.6)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(cx, RULER_H); ctx.lineTo(cx, H); ctx.stroke();
    ctx.setLineDash([]);
  }

  // Score alignment markers (green = start, orange = end; cyan/yellow for 2nd image)
  if (scoreView.img && state.duration > 0) {
    const sx = tToX(scoreView.start);
    const ex = tToX(scoreView.end);
    ctx.lineWidth = 2; ctx.setLineDash([4, 3]);
    ctx.strokeStyle = "#44ff88";
    ctx.beginPath(); ctx.moveTo(sx, RULER_H); ctx.lineTo(sx, H); ctx.stroke();
    ctx.strokeStyle = "#ff8844";
    ctx.beginPath(); ctx.moveTo(ex, RULER_H); ctx.lineTo(ex, H); ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = "10px 'Courier New', monospace";
    ctx.fillStyle = "#44ff88";
    ctx.fillText("\u25c4 score", sx + 3, RULER_H + 22);
    ctx.fillStyle = "#ff8844";
    ctx.fillText("score \u25ba", Math.max(0, ex - 58), RULER_H + 22);
  }
  const score2Vis = document.getElementById("score2-container").classList.contains("visible");
  if (score2Vis && score2View.img && state.duration > 0) {
    const sx2 = tToX(score2View.start);
    const ex2 = tToX(score2View.end);
    ctx.lineWidth = 2; ctx.setLineDash([2, 4]);
    ctx.strokeStyle = "#44ddff";
    ctx.beginPath(); ctx.moveTo(sx2, RULER_H); ctx.lineTo(sx2, H); ctx.stroke();
    ctx.strokeStyle = "#ffdd44";
    ctx.beginPath(); ctx.moveTo(ex2, RULER_H); ctx.lineTo(ex2, H); ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = "10px 'Courier New', monospace";
    ctx.fillStyle = "#44ddff";
    ctx.fillText("\u25c4 meta", sx2 + 3, RULER_H + 34);
    ctx.fillStyle = "#ffdd44";
    ctx.fillText("meta \u25ba", Math.max(0, ex2 - 46), RULER_H + 34);
  }

  // Frame overlay
  drawFrameOverlay();

  // Second image panel
  if (document.getElementById("score2-container").classList.contains("visible")) {
    drawScoreOverlay(score2Canvas, score2Ctx, score2View);
  }

  // Drag preview
  if (dragState.active) {
    const x1 = Math.min(dragState.startX, dragState.curX);
    const x2 = Math.max(dragState.startX, dragState.curX);
    ctx.fillStyle = "rgba(200,200,100,0.08)";
    ctx.fillRect(x1, RULER_H, x2 - x1, wH);
    ctx.strokeStyle = "rgba(200,200,100,0.5)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 2]);
    ctx.beginPath(); ctx.moveTo(x1, RULER_H); ctx.lineTo(x1, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, RULER_H); ctx.lineTo(x2, H); ctx.stroke();
    ctx.setLineDash([]);
  }

  // Redraw mini waveforms so their cursors stay in sync
  const panel = document.getElementById("tracks-panel");
  if (panel) {
    panel.querySelectorAll("canvas[data-tidx]").forEach(c => {
      const idx = parseInt(c.dataset.tidx);
      drawMiniWaveform(c, state.tracks[idx]?.waveform);
    });
  }
}

function drawRuler(W) {
  if (!state.duration) return;
  const step = niceStep(state.duration / 10);
  ctx.fillStyle = "#555";
  ctx.font = "9px 'Courier New', monospace";
  for (let t = 0; t <= state.duration; t += step) {
    const x = tToX(t);
    ctx.strokeStyle = "#333";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, RULER_H - 5); ctx.lineTo(x, RULER_H); ctx.stroke();
    ctx.fillText(t.toFixed(1), x + 2, RULER_H - 8);
  }
}

function niceStep(approx) {
  const steps = [0.1,0.2,0.5,1,2,5,10,20,30,60,120];
  for (const s of steps) if (s >= approx) return s;
  return 120;
}

function hexAlpha(hex, a) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}

// ─── Generic score-view helpers (used by both frame canvas and score2 canvas) ──
function scoreDisplayWidthFor(c, view) {
  if (!view.img || !view.img.naturalHeight) return c.width;
  return view.img.naturalWidth * (c.height / view.img.naturalHeight) * view.scale;
}
function tToXFor(t, c, view) {
  if (!state.duration) return 0;
  const dur = view.end - view.start;
  if (dur <= 0) return 0;
  const dw = scoreDisplayWidthFor(c, view);
  const tDisp   = ((t                   - view.start) / dur) * dw;
  const curDisp = ((state.currentTime   - view.start) / dur) * dw;
  return tDisp - curDisp + c.width / 2 + view.panOffset;
}
function xToTFor(x, c, view) {
  if (!state.duration) return 0;
  const dur = view.end - view.start;
  if (dur <= 0) return 0;
  const dw = scoreDisplayWidthFor(c, view);
  const curDisp = ((state.currentTime - view.start) / dur) * dw;
  const displayX = x - c.width / 2 - view.panOffset + curDisp;
  return Math.max(0, Math.min(state.duration, view.start + (displayX / dw) * dur));
}

// Draws score image + all annotation overlays onto any canvas/ctx/view.
// Used by both the main frame canvas (score mode) and the second image panel.
function drawScoreOverlay(c, ctx, view) {
  const W = c.width, H = c.height;
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, W, H);
  if (!state.duration) return;

  // Score image
  if (view.img && view.img.complete && view.img.naturalWidth > 0) {
    const s    = (H / view.img.naturalHeight) * view.scale;
    const imgW = view.img.naturalWidth;
    const dur  = view.end - view.start;
    const dw   = scoreDisplayWidthFor(c, view);
    const curDisp = dur > 0 ? ((state.currentTime - view.start) / dur) * dw : 0;
    const sl   = curDisp - W / 2 - view.panOffset;
    const srcX = sl / s, srcW = W / s;
    const clSrcX = Math.max(0, srcX);
    const clSrcW = Math.min(srcW, imgW - clSrcX);
    const dstX = (clSrcX - srcX) * s, dstW = clSrcW * s;
    if (clSrcW > 0 && dstW > 0) {
      ctx.drawImage(view.img, clSrcX, 0, clSrcW, view.img.naturalHeight, dstX, 0, dstW, H);
    }
  } else {
    ctx.fillStyle = "#444"; ctx.font = "11px 'Courier New', monospace";
    ctx.fillText("load image →", 10, H - 10);
  }

  const tx = t => tToXFor(t, c, view);

  // Sample regions
  for (const [name, s] of Object.entries(_sdd().samples)) {
    const x1 = tx(s.from), x2 = tx(s.to);
    ctx.fillStyle = hexAlpha(s.color, 0.18); ctx.fillRect(x1, 0, x2 - x1, H);
    ctx.strokeStyle = hexAlpha(s.color, 0.7); ctx.lineWidth = 1.5; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, 0); ctx.lineTo(x2, H); ctx.stroke();
    ctx.fillStyle = hexAlpha(s.color, 0.85); ctx.font = "11px 'Courier New', monospace";
    ctx.fillText("[" + name + "]", x1 + 4, 16);
  }
  // Dynamic ranges
  for (const d of _sdd().dynamics) {
    if (d.from !== undefined) {
      const x1 = tx(d.from), x2 = tx(d.to);
      const col = _dmark(d) === "crescendo" ? "#337755" : "#775533";
      ctx.fillStyle = hexAlpha(col, 0.15); ctx.fillRect(x1, 0, x2 - x1, H);
      ctx.strokeStyle = hexAlpha(col, 0.6); ctx.lineWidth = 1; ctx.setLineDash([4,3]);
      ctx.beginPath(); ctx.moveTo(x1, H/2); ctx.lineTo(x2, H/2); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "10px 'Courier New', monospace";
      ctx.fillText(_dmark(d), x1 + 3, H/2 - 4);
    }
  }
  // Tempo ranges
  for (const tp of _sdd().tempo) {
    const x1 = tx(tp.from), x2 = tx(tp.to);
    const col = tp.mark === "accelerando" ? "#aa7722" : "#227799";
    ctx.fillStyle = hexAlpha(col, 0.13); ctx.fillRect(x1, 0, x2 - x1, H);
    ctx.strokeStyle = hexAlpha(col, 0.7); ctx.lineWidth = 1; ctx.setLineDash([6,4]);
    ctx.beginPath(); ctx.moveTo(x1, 24); ctx.lineTo(x2, 24); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "10px 'Courier New', monospace";
    ctx.fillText(tp.mark, x1 + 3, 36);
  }
  // FX zones
  for (const fz of _sdd().fxRanges) {
    const x1 = tx(fz.from), x2 = tx(fz.to);
    ctx.fillStyle = hexAlpha("#8844cc", 0.12); ctx.fillRect(x1, 0, x2 - x1, H);
    ctx.strokeStyle = hexAlpha("#8844cc", 0.5); ctx.lineWidth = 1; ctx.setLineDash([2,3]);
    ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, 0); ctx.lineTo(x2, H); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = hexAlpha("#8844cc", 0.9); ctx.font = "10px 'Courier New', monospace";
    ctx.fillText("fx:" + fz.fx.map(f => f.type).join("+"), x1 + 3, H - 8);
  }
  // Phrase / slur markers
  for (const ph of _sdd().phrases) {
    const x1 = tx(ph.from), x2 = tx(ph.to);
    const pc = "#8a6abf";
    ctx.fillStyle = hexAlpha(pc, 0.09); ctx.fillRect(x1, 0, x2 - x1, H);
    ctx.strokeStyle = hexAlpha(pc, 0.75); ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, 0); ctx.lineTo(x2, H); ctx.stroke();
    ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x1, 2); ctx.lineTo(x2, 2); ctx.stroke();
    ctx.fillStyle = hexAlpha(pc, 0.95); ctx.font = "10px 'Courier New', monospace";
    ctx.fillText(ph.label, x1 + 4, 14);
  }
  // Note relationship markers
  for (const nr of _sdd().noteRel) {
    const x1 = tx(nr.from), x2 = tx(nr.to ?? nr.from);
    if (nr.type === "glissando") {
      ctx.strokeStyle = hexAlpha("#44aadd", 0.85); ctx.lineWidth = 2; ctx.setLineDash([5,3]);
      ctx.beginPath(); ctx.moveTo(x1, H * 0.3); ctx.lineTo(x2, H * 0.7); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = hexAlpha("#44aadd", 0.9); ctx.font = "9px 'Courier New', monospace";
      ctx.fillText("gliss.", x1 + 2, H * 0.3 - 2);
    } else if (nr.type === "arpeggiate") {
      ctx.strokeStyle = hexAlpha("#44ddaa", 0.85); ctx.lineWidth = 2; ctx.setLineDash([]);
      ctx.beginPath();
      const waveAmp = 4, waveStep = H / 8;
      for (let i = 0; i <= 8; i++) {
        const yy = H * 0.1 + i * waveStep;
        const xx = x1 + (i % 2 === 0 ? -waveAmp : waveAmp);
        i === 0 ? ctx.moveTo(xx, yy) : ctx.lineTo(xx, yy);
      }
      ctx.stroke();
      ctx.fillStyle = hexAlpha("#44ddaa", 0.9); ctx.font = "9px 'Courier New', monospace";
      ctx.fillText("arp.", x1 + 8, 22);
    }
    if (nr.label) {
      ctx.fillStyle = hexAlpha("#aaa", 0.7); ctx.font = "9px 'Courier New', monospace";
      ctx.fillText(nr.label, x1 + 2, H - 4);
    }
  }
  // Articulation markers
  for (const ar of _sdd().articulations) {
    const ART_COL = { staccato: "#ffaa44", legato: "#44ffaa", fermata: "#ff88cc", accent: "#ff6644" };
    const col = ART_COL[ar.type] || "#aaa";
    if (ar.t !== undefined) {
      const xa = tx(ar.t);
      ctx.strokeStyle = hexAlpha(col, 0.7); ctx.lineWidth = 1.5; ctx.setLineDash([2,3]);
      ctx.beginPath(); ctx.moveTo(xa, 0); ctx.lineTo(xa, H); ctx.stroke();
      ctx.setLineDash([]);
      const sym = ar.type === "staccato" ? "\u2022" : ar.type === "fermata" ? "\uD834\uDD10" : ">";
      ctx.fillStyle = hexAlpha(col, 0.95); ctx.font = "13px 'Courier New', monospace";
      ctx.fillText(sym, xa + 3, H / 2);
      ctx.font = "8px 'Courier New', monospace";
      ctx.fillText(ar.type, xa + 3, H / 2 + 13);
    } else {
      const x1 = tx(ar.from), x2 = tx(ar.to);
      ctx.fillStyle = hexAlpha(col, 0.07); ctx.fillRect(x1, 0, x2 - x1, H);
      ctx.strokeStyle = hexAlpha(col, 0.7); ctx.lineWidth = 1.5; ctx.setLineDash([3,2]);
      ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, H); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x2, 0); ctx.lineTo(x2, H); ctx.stroke();
      ctx.setLineDash([]); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1, 8); ctx.bezierCurveTo(x1, 0, x2, 0, x2, 8); ctx.stroke();
      ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "8px 'Courier New', monospace";
      ctx.fillText("legato", x1 + 3, 20);
    }
  }
  // Event markers
  for (const ev of _sdd().events) {
    const x = tx(ev.t);
    const col = (_sdd().samples[ev.sample] || {}).color || "#aaa";
    ctx.strokeStyle = hexAlpha(col, 0.8); ctx.lineWidth = 1.5; ctx.setLineDash([3,2]);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = hexAlpha(col, 0.9); ctx.font = "9px 'Courier New', monospace";
    ctx.fillText("\u25b6" + ev.sample, x + 3, 28);
  }
  // Dynamic point marks
  for (const d of _sdd().dynamics) {
    if (d.t !== undefined) {
      const x = tx(d.t);
      const col = DYNAMIC_COLORS[_dmark(d)] || "#aaa";
      ctx.strokeStyle = hexAlpha(col, 0.8); ctx.lineWidth = 2; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      ctx.fillStyle = hexAlpha(col, 0.95); ctx.font = "11px 'Courier New', monospace";
      ctx.fillText(_dmark(d), x + 3, H - 10);
    }
  }
  // Drag preview
  if (dragState.active && dragState.canvas === c) {
    const x1F = tx(Math.min(dragState.startT, dragState.curT));
    const x2F = tx(Math.max(dragState.startT, dragState.curT));
    ctx.fillStyle = "rgba(200,200,100,0.08)"; ctx.fillRect(x1F, 0, x2F - x1F, H);
    ctx.strokeStyle = "rgba(200,200,100,0.3)"; ctx.lineWidth = 1; ctx.setLineDash([4,3]);
    ctx.beginPath(); ctx.moveTo(x1F, 0); ctx.lineTo(x1F, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2F, 0); ctx.lineTo(x2F, H); ctx.stroke();
    ctx.setLineDash([]);
  }
  // Cursor
  const cx = tx(state.currentTime);
  ctx.strokeStyle = "rgba(51,204,204,0.85)"; ctx.lineWidth = 2; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
}

// ─── Frame overlay draw ───────────────────────────────────────────────────────
function tToXF(t) {
  if (!state.duration) return 0;
  if (viewMode === "score") {
    return tToScoreDisplayX(t) - scoreScrollLeft();
  }
  return (t / state.duration) * frameCanvas.width;
}

function drawFrameOverlay() {
  const W = frameCanvas.width, H = frameCanvas.height;
  frameCtx.clearRect(0, 0, W, H);
  if (!state.duration) return;

  // ── Score image (score mode only) ──────────────────────────────────────────
  if (viewMode === "score") {
    // Always fill background so video element can't bleed through transparent canvas
    frameCtx.fillStyle = "#111";
    frameCtx.fillRect(0, 0, W, H);
    if (scoreView.img && scoreView.img.complete && scoreView.img.naturalWidth > 0) {
      const s    = (H / scoreView.img.naturalHeight) * scoreView.scale;
      const imgW = scoreView.img.naturalWidth;
      const sl   = scoreScrollLeft();
      const srcX = sl / s;
      const srcW = W / s;
      const clSrcX = Math.max(0, srcX);
      const clSrcW = Math.min(srcW, imgW - clSrcX);
      const dstX   = (clSrcX - srcX) * s;
      const dstW   = clSrcW * s;
      if (clSrcW > 0 && dstW > 0) {
        frameCtx.drawImage(scoreView.img, clSrcX, 0, clSrcW, scoreView.img.naturalHeight,
                           dstX, 0, dstW, H);
      }
    } else {
      frameCtx.fillStyle = "#444";
      frameCtx.font = "12px 'Courier New', monospace";
      frameCtx.fillText("load score image →", 10, H - 36);
    }
  }

  // Sample regions
  for (const [name, s] of Object.entries(_sdd().samples)) {
    const x1 = tToXF(s.from), x2 = tToXF(s.to);
    frameCtx.fillStyle = hexAlpha(s.color, 0.18);
    frameCtx.fillRect(x1, 0, x2 - x1, H);
    frameCtx.strokeStyle = hexAlpha(s.color, 0.7);
    frameCtx.lineWidth = 1.5;
    frameCtx.setLineDash([]);
    frameCtx.beginPath(); frameCtx.moveTo(x1, 0); frameCtx.lineTo(x1, H); frameCtx.stroke();
    frameCtx.beginPath(); frameCtx.moveTo(x2, 0); frameCtx.lineTo(x2, H); frameCtx.stroke();
    frameCtx.fillStyle = hexAlpha(s.color, 0.85);
    frameCtx.font = "11px 'Courier New', monospace";
    frameCtx.fillText("[" + name + "]", x1 + 4, 16);
  }

  // Dynamic ranges
  for (const d of _sdd().dynamics) {
    if (d.from !== undefined) {
      const x1 = tToXF(d.from), x2 = tToXF(d.to);
      const col = _dmark(d) === "crescendo" ? "#337755" : "#775533";
      frameCtx.fillStyle = hexAlpha(col, 0.15);
      frameCtx.fillRect(x1, 0, x2 - x1, H);
      frameCtx.strokeStyle = hexAlpha(col, 0.6);
      frameCtx.lineWidth = 1; frameCtx.setLineDash([4,3]);
      frameCtx.beginPath(); frameCtx.moveTo(x1, H/2); frameCtx.lineTo(x2, H/2); frameCtx.stroke();
      frameCtx.setLineDash([]);
      frameCtx.fillStyle = hexAlpha(col, 0.9);
      frameCtx.font = "10px 'Courier New', monospace";
      frameCtx.fillText(d.mark, x1 + 3, H/2 - 4);
    }
  }

  // Tempo ranges
  for (const tp of _sdd().tempo) {
    const x1 = tToXF(tp.from), x2 = tToXF(tp.to);
    const col = tp.mark === "accelerando" ? "#aa7722" : "#227799";
    frameCtx.fillStyle = hexAlpha(col, 0.13);
    frameCtx.fillRect(x1, 0, x2 - x1, H);
    frameCtx.strokeStyle = hexAlpha(col, 0.7);
    frameCtx.lineWidth = 1; frameCtx.setLineDash([6,4]);
    frameCtx.beginPath(); frameCtx.moveTo(x1, 24); frameCtx.lineTo(x2, 24); frameCtx.stroke();
    frameCtx.setLineDash([]);
    frameCtx.fillStyle = hexAlpha(col, 0.9);
    frameCtx.font = "10px 'Courier New', monospace";
    frameCtx.fillText(tp.mark, x1 + 3, 36);
  }

  // FX zones
  for (const fz of _sdd().fxRanges) {
    const x1 = tToXF(fz.from), x2 = tToXF(fz.to);
    frameCtx.fillStyle = hexAlpha("#8844cc", 0.12);
    frameCtx.fillRect(x1, 0, x2 - x1, H);
    frameCtx.strokeStyle = hexAlpha("#8844cc", 0.5);
    frameCtx.lineWidth = 1; frameCtx.setLineDash([2,3]);
    frameCtx.beginPath(); frameCtx.moveTo(x1, 0); frameCtx.lineTo(x1, H); frameCtx.stroke();
    frameCtx.beginPath(); frameCtx.moveTo(x2, 0); frameCtx.lineTo(x2, H); frameCtx.stroke();
    frameCtx.setLineDash([]);
    frameCtx.fillStyle = hexAlpha("#8844cc", 0.9);
    frameCtx.font = "10px 'Courier New', monospace";
    frameCtx.fillText("fx:" + fz.fx.map(f => f.type).join("+"), x1 + 3, H - 8);
  }

  // Phrase markers
  for (const ph of _sdd().phrases) {
    const x1 = tToXF(ph.from), x2 = tToXF(ph.to);
    const pc = "#8a6abf";
    frameCtx.fillStyle = hexAlpha(pc, 0.09);
    frameCtx.fillRect(x1, 0, x2 - x1, H);
    frameCtx.strokeStyle = hexAlpha(pc, 0.75);
    frameCtx.lineWidth = 2; frameCtx.setLineDash([]);
    frameCtx.beginPath(); frameCtx.moveTo(x1, 0); frameCtx.lineTo(x1, H); frameCtx.stroke();
    frameCtx.beginPath(); frameCtx.moveTo(x2, 0); frameCtx.lineTo(x2, H); frameCtx.stroke();
    frameCtx.lineWidth = 1;
    frameCtx.beginPath(); frameCtx.moveTo(x1, 2); frameCtx.lineTo(x2, 2); frameCtx.stroke();
    frameCtx.fillStyle = hexAlpha(pc, 0.95);
    frameCtx.font = "10px 'Courier New', monospace";
    frameCtx.fillText(ph.label, x1 + 4, 14);
  }

  // Event markers
  for (const ev of _sdd().events) {
    const x = tToXF(ev.t);
    const col = (_sdd().samples[ev.sample] || {}).color || "#aaa";
    frameCtx.strokeStyle = hexAlpha(col, 0.8);
    frameCtx.lineWidth = 1.5; frameCtx.setLineDash([3,2]);
    frameCtx.beginPath(); frameCtx.moveTo(x, 0); frameCtx.lineTo(x, H); frameCtx.stroke();
    frameCtx.setLineDash([]);
    frameCtx.fillStyle = hexAlpha(col, 0.9);
    frameCtx.font = "9px 'Courier New', monospace";
    frameCtx.fillText("▶" + ev.sample, x + 3, 28);
  }

  // Dynamic point marks
  for (const d of _sdd().dynamics) {
    if (d.t !== undefined) {
      const x = tToXF(d.t);
      const col = DYNAMIC_COLORS[_dmark(d)] || "#aaa";
      frameCtx.strokeStyle = hexAlpha(col, 0.8);
      frameCtx.lineWidth = 2; frameCtx.setLineDash([]);
      frameCtx.beginPath(); frameCtx.moveTo(x, 0); frameCtx.lineTo(x, H); frameCtx.stroke();
      frameCtx.fillStyle = hexAlpha(col, 0.95);
      frameCtx.font = "11px 'Courier New', monospace";
      frameCtx.fillText(d.mark, x + 3, H - 10);
    }
  }

  // Drag range preview
  if (dragState.active && dragState.canvas === frameCanvas) {
    const x1F = tToXF(Math.min(dragState.startT, dragState.curT));
    const x2F = tToXF(Math.max(dragState.startT, dragState.curT));
    frameCtx.fillStyle = "rgba(200,200,100,0.08)";
    frameCtx.fillRect(x1F, 0, x2F - x1F, H);
    frameCtx.strokeStyle = "rgba(200,200,100,0.3)";
    frameCtx.lineWidth = 1; frameCtx.setLineDash([4,3]);
    frameCtx.beginPath(); frameCtx.moveTo(x1F, 0); frameCtx.lineTo(x1F, H); frameCtx.stroke();
    frameCtx.beginPath(); frameCtx.moveTo(x2F, 0); frameCtx.lineTo(x2F, H); frameCtx.stroke();
    frameCtx.setLineDash([]);
  }

  // Cursor
  const cx = tToXF(state.currentTime);
  if (viewMode === "score") {
    frameCtx.strokeStyle = "rgba(51,204,204,0.85)";  // #33cccc on score image
    frameCtx.lineWidth = 2; frameCtx.setLineDash([]);
  } else {
    frameCtx.strokeStyle = "rgba(255,50,50,0.85)";   // red on metadata/video
    frameCtx.lineWidth = 1; frameCtx.setLineDash([4,3]);
  }
  frameCtx.beginPath(); frameCtx.moveTo(cx, 0); frameCtx.lineTo(cx, H); frameCtx.stroke();
  frameCtx.setLineDash([]);
}
