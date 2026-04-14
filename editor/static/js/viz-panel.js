// ─── viz-panel.js — Right-panel visualizations 1–5 ───────────────────────────
// Renders from _lastTraceData (no extra fetch). Triggered by fetchAndDrawTrace().
// Depends on: kalman-trace.js (DIM_COLORS, DIM_RANGES, _hexToRgb, _lastTraceData)

let _activeViz   = 1;
let _vizCurrentT = -1;  // score-time cursor, == audio time (-1 = show full trace)
let _vizFixedSize = false;  // when true, skip auto-resize (concerto mode)

function updateVizPanel(data) {
  const playing = (typeof isMixPlaying === 'function') && isMixPlaying();
  if (playing) {
    // mixCurrentTime() returns position in the audio buffer.
    // The audio buffer is the rendered score, so audio time == score time.
    _vizCurrentT = mixCurrentTime();
    // Also animate bottom-panel timeline cursor
    if (typeof drawKalmanTrace === 'function' && data) drawKalmanTrace(data);
    requestAnimationFrame(() => updateVizPanel(data));
  } else {
    if (_vizCurrentT >= 0) {
      // Final redraw of the bottom canvas to clear the cursor line
      if (typeof drawKalmanTrace === 'function' && data) drawKalmanTrace(data);
    }
    _vizCurrentT = -1;
  }

  const canvas = document.getElementById('viz-panel-canvas');
  if (!canvas) return;
  if (!_vizFixedSize) {
    const r  = canvas.getBoundingClientRect();
    const rW = Math.round(r.width  || canvas.clientWidth  || 220);
    const rH = Math.round(r.height || canvas.clientHeight || 400);
    if (rH < 10) { requestAnimationFrame(() => updateVizPanel(data)); return; }
    canvas.width  = rW;
    canvas.height = rH;
  }
  const W = canvas.width, H = canvas.height;
  if (H < 10) return;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#080808';
  ctx.fillRect(0, 0, W, H);

  const statusEl = document.getElementById('viz-panel-status');
  const dimRow   = document.getElementById('viz-dim-row');

  if (!data || !data.trace || !data.trace.length) {
    if (statusEl) statusEl.textContent = 'press ◈ Trace to visualize';
    return;
  }
  if (statusEl) statusEl.textContent = '';

  // Progressive reveal: in concerto mode, only pass accumulated history to viz
  const vizData = (typeof _concertoMaxT !== 'undefined' && _concertoMaxT < Infinity && data.trace)
    ? { ...data, trace: data.trace.filter(s => s.t <= _concertoMaxT) }
    : data;
  if (!vizData.trace.length) return;

  const showDims = (_activeViz === 4 || _activeViz === 5 || _activeViz === 10);
  if (dimRow) dimRow.style.display = showDims ? 'flex' : 'none';

  const drawFns = {
    1: _drawMarginalGaussians, 2: _drawKalmanGainHeatmap,
    3: _drawInnovationTrace,   4: _drawPhasePortrait,
    5: _drawStateTrajectory,   6: _drawSalienceBackdrop,
    7: _drawLookaheadPhi,      8: _drawProcessNoise,
    9: _drawInnovationEnergy,  10: _drawSampleScatter,
    11: _drawRegimeBlend,      12: _drawCovarianceMatrix,
    16: _drawCorrelationWeb,   17: _drawDistributionShape,
    20: _drawStepHistogram,    21: _drawDriftTrajectory,
    22: _drawFixedStateBars,
  };
  const fn = drawFns[_activeViz];
  if (!fn) return;
  try {
    fn(ctx, W, H, vizData);
  } catch(e) {
    console.error('viz-panel draw error (viz ' + _activeViz + '):', e);
    ctx.fillStyle = '#c87070';
    ctx.font = '10px monospace';
    ctx.fillText('draw error: ' + e.message, 6, H / 2 - 6);
    ctx.fillStyle = '#555';
    ctx.font = '8px monospace';
    ctx.fillText('see browser console for details', 6, H / 2 + 10);
  }
}

// ─── Viz 1: Marginal Gaussians ────────────────────────────────────────────────
function _drawMarginalGaussians(ctx, W, H, data) {
  const D    = DIM_NAMES.length;
  const rowH = H / D;
  const trace = data.trace;
  const curIdx = _cursorIdx(trace);
  const last   = trace[curIdx];
  const NAMES = DIM_LABELS;
  const STEPS = 100;

  for (let d = 0; d < D; d++) {
    const y0 = d * rowH;
    const y1 = (d + 1) * rowH - 1;
    const mid = (y0 + y1) / 2;
    const [lo, hi] = DIM_RANGES[d];
    const col  = DIM_COLORS[d];
    const [r, g, b] = _hexToRgb(col);
    const mu  = last.mu[d];
    const sig = Math.max(last.sigma_diag[d], 1e-6);

    const toX = v => ((v - lo) / (hi - lo)) * W;
    const scaleY = rowH * 0.38;   // how tall the peak is in pixels

    // Gaussian PDF peak (at sigma=1, pdf(mu) ≈ 0.399)
    const peakPdf = 1 / (Math.sqrt(2 * Math.PI) * sig);

    const drawBell = (muVal, sigVal, alpha, lw) => {
      ctx.beginPath();
      for (let i = 0; i <= STEPS; i++) {
        const v  = lo + (hi - lo) * (i / STEPS);
        const z  = (v - muVal) / sigVal;
        const p  = Math.exp(-0.5 * z * z) / (Math.sqrt(2 * Math.PI) * sigVal);
        const py = mid - (p / peakPdf) * scaleY;
        const px = toX(v);
        i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      }
      ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.lineWidth   = lw;
      ctx.stroke();
    };

    // Prior ghost (mu_bar)
    if (last.mu_bar) {
      drawBell(last.mu_bar[d], sig * 1.35, 0.25, 1);
    }
    // Posterior (solid)
    drawBell(mu, sig, 0.9, 1.5);

    // 1σ fill under posterior
    ctx.beginPath();
    for (let i = 0; i <= STEPS; i++) {
      const v  = lo + (hi - lo) * (i / STEPS);
      const z  = (v - mu) / sig;
      if (Math.abs(z) > 1) { i === 0 ? ctx.moveTo(toX(v), mid) : ctx.lineTo(toX(v), mid); continue; }
      const p  = Math.exp(-0.5 * z * z) / (Math.sqrt(2 * Math.PI) * sig);
      const py = mid - (p / peakPdf) * scaleY;
      i === 0 ? ctx.moveTo(toX(v), py) : ctx.lineTo(toX(v), py);
    }
    ctx.lineTo(toX(mu + sig), mid);
    ctx.lineTo(toX(mu - sig), mid);
    ctx.closePath();
    ctx.fillStyle = `rgba(${r},${g},${b},0.08)`;
    ctx.fill();

    // Historical sample ticks
    ctx.lineWidth = 1;
    for (const step of trace) {
      const sx = toX(step.sample[d]);
      ctx.strokeStyle = `rgba(${r},${g},${b},0.35)`;
      ctx.beginPath(); ctx.moveTo(sx, mid - 6); ctx.lineTo(sx, mid + 6); ctx.stroke();
    }
    // Most recent sample — brighter
    const latestSx = toX(last.sample[d]);
    ctx.strokeStyle = col; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(latestSx, mid - 9); ctx.lineTo(latestSx, mid + 9); ctx.stroke();

    // Dim label
    ctx.fillStyle = `rgba(${r},${g},${b},0.55)`;
    ctx.font = '9px monospace';
    ctx.fillText(NAMES[d], 3, y0 + 11);

    // σ label
    ctx.fillStyle = '#333';
    ctx.font = '8px monospace';
    ctx.fillText(`σ=${sig.toFixed(2)}`, W - 40, y0 + 11);

    // Row separator
    ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, y1 + 1); ctx.lineTo(W, y1 + 1); ctx.stroke();
  }
}

// ─── Viz 2: Kalman Gain Heatmap ───────────────────────────────────────────────
function _drawKalmanGainHeatmap(ctx, W, H, data) {
  const withK = data.trace.filter(s => s.K && s.K.length);
  if (!withK.length) {
    ctx.fillStyle = '#444'; ctx.font = '10px monospace';
    ctx.fillText('K not in trace data', 8, H / 2 - 6);
    ctx.fillStyle = '#333';
    ctx.fillText('(re-run Trace)', 8, H / 2 + 10);
    return;
  }
  const D     = DIM_NAMES.length;
  const NAMES = DIM_LABELS;
  const padL  = 26, padT = 20, padR = 4, padB = 14;
  const cellW = (W - padL - padR) / D;
  const cellH = (H - padT - padB) / D;
  const lastK = withK[withK.length - 1].K;

  // Column headers (observation)
  ctx.fillStyle = '#444'; ctx.font = '8px monospace';
  NAMES.forEach((n, i) => ctx.fillText(n, padL + i * cellW + 2, padT - 5));
  // Row headers (state)
  NAMES.forEach((n, i) => ctx.fillText(n, 1, padT + i * cellH + cellH * 0.65));

  for (let row = 0; row < D; row++) {
    for (let col = 0; col < D; col++) {
      const v = Math.abs((lastK[row] || [])[col] || 0);
      const brightness = Math.min(1, v * 5);  // K values typically 0–0.3
      const [r, g, b] = _hexToRgb(DIM_COLORS[row]);
      ctx.fillStyle = `rgba(${r},${g},${b},${brightness * 0.85 + 0.04})`;
      const cx = padL + col * cellW + 1;
      const cy = padT + row * cellH + 1;
      ctx.fillRect(cx, cy, cellW - 2, cellH - 2);
      if (cellW > 20) {
        ctx.fillStyle = '#666'; ctx.font = '7px monospace';
        ctx.fillText(v.toFixed(2), cx + 2, cy + cellH * 0.65);
      }
    }
  }

  // Timestamp
  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText(`t=${withK[withK.length - 1].t.toFixed(1)}s`, padL, H - 3);
}

// ─── Viz 3: Innovation Trace ──────────────────────────────────────────────────
function _drawInnovationTrace(ctx, W, H, data) {
  const withNu = data.trace.filter(s => s.nu && s.nu.length);
  if (!withNu.length) {
    ctx.fillStyle = '#888'; ctx.font = '11px monospace';
    ctx.fillText('ν not in trace — re-run Trace', 8, H / 2);
    return;
  }
  const D   = DIM_NAMES.length;
  const dur = data.total_dur || 1;
  const toX = t => (t / dur) * W;
  // Auto-scale: find max |nu| across all dims and steps
  let maxNu = 0.01;
  withNu.forEach(s => s.nu.forEach(v => { if (Math.abs(v) > maxNu) maxNu = Math.abs(v); }));
  const toY = (v) => H * 0.5 - (v / maxNu) * H * 0.45;

  // Zero line
  ctx.strokeStyle = '#222'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();

  // Per-dim traces
  for (let d = 0; d < D; d++) {
    const col = DIM_COLORS[d];
    const [r, g, b] = _hexToRgb(col);
    ctx.strokeStyle = `rgba(${r},${g},${b},0.65)`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    withNu.forEach((step, i) => {
      const x = toX(step.t);
      const y = toY(step.nu[d]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    // Dots
    ctx.fillStyle = `rgba(${r},${g},${b},0.45)`;
    withNu.forEach(step => {
      ctx.beginPath();
      ctx.arc(toX(step.t), toY(step.nu[d], d), 2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Label + autocorrelation hint
  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('ν(t) — innovation', 4, H - 4);
  ctx.fillStyle = '#222'; ctx.font = '8px monospace';
  ctx.fillText(`n=${withNu.length} events`, W - 65, H - 4);
  _drawTimeCursor(ctx, _vizCurrentT, dur, W, H);
}

// ─── Viz 4: AR(2) Phase Portrait ──────────────────────────────────────────────
function _drawPhasePortrait(ctx, W, H, data) {
  const trace = data.trace;
  const dx  = parseInt(document.getElementById('viz-dim-x')?.value ?? '0');
  const dy  = parseInt(document.getElementById('viz-dim-y')?.value ?? '1');
  // Auto-scale to actual data range with 10% padding
  const xVals = trace.map(s => s.sample[dx]);
  const yVals = trace.map(s => s.sample[dy]);
  const pad = 24;
  let lox = Math.min(...xVals), hix = Math.max(...xVals);
  let loy = Math.min(...yVals), hiy = Math.max(...yVals);
  const xPad = (hix - lox) * 0.15 || 0.1, yPad = (hiy - loy) * 0.15 || 0.1;
  lox -= xPad; hix += xPad; loy -= yPad; hiy += yPad;
  const toX = v => pad + ((v - lox) / (hix - lox)) * (W - pad * 2);
  const toY = v => (H - pad) - ((v - loy) / (hiy - loy)) * (H - pad * 2);
  const N = _cursorIdx(trace) + 1;   // draw only up to current playback position

  // Axis lines
  ctx.strokeStyle = '#1e1e1e'; ctx.lineWidth = 1;
  const x0 = toX(0), y0 = toY(0);
  if (x0 > pad && x0 < W - pad) {
    ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0, H); ctx.stroke();
  }
  if (y0 > pad && y0 < H - pad) {
    ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(W, y0); ctx.stroke();
  }

  // Trail: x(t-1) vs x(t)
  for (let i = 1; i < N; i++) {
    const age  = i / N;  // 0=oldest, 1=newest
    const [r, g, b] = _hexToRgb(DIM_COLORS[dx]);
    ctx.strokeStyle = `rgba(${r},${g},${b},${0.1 + age * 0.75})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(toX(trace[i - 1].sample[dx]), toY(trace[i - 1].sample[dy]));
    ctx.lineTo(toX(trace[i].sample[dx]),     toY(trace[i].sample[dy]));
    ctx.stroke();
  }
  // Current point (bright)
  if (N > 0) {
    ctx.fillStyle = DIM_COLORS[dx];
    ctx.beginPath();
    ctx.arc(toX(trace[N - 1].sample[dx]), toY(trace[N - 1].sample[dy]), 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // Axis labels
  const NAMES = DIM_LABELS;
  ctx.fillStyle = '#444'; ctx.font = '9px monospace';
  ctx.fillText(NAMES[dx], W - 48, H - 4);
  ctx.save(); ctx.translate(11, H / 2 + 20); ctx.rotate(-Math.PI / 2);
  ctx.fillText(NAMES[dy], 0, 0); ctx.restore();
}

// ─── Viz 5: State Trajectory 2D ───────────────────────────────────────────────
function _drawStateTrajectory(ctx, W, H, data) {
  const trace = data.trace;
  const dx  = parseInt(document.getElementById('viz-dim-x')?.value ?? '0');
  const dy  = parseInt(document.getElementById('viz-dim-y')?.value ?? '1');
  // Auto-scale to actual μ range with padding
  const xVals = trace.map(s => s.mu[dx]);
  const yVals = trace.map(s => s.mu[dy]);
  const pad = 24;
  let lox = Math.min(...xVals), hix = Math.max(...xVals);
  let loy = Math.min(...yVals), hiy = Math.max(...yVals);
  const xPad = (hix - lox) * 0.2 || 0.1, yPad = (hiy - loy) * 0.2 || 0.1;
  lox -= xPad; hix += xPad; loy -= yPad; hiy += yPad;
  const toX = v => pad + ((v - lox) / (hix - lox)) * (W - pad * 2);
  const toY = v => (H - pad) - ((v - loy) / (hiy - loy)) * (H - pad * 2);
  const N = _cursorIdx(trace) + 1;   // draw only up to current playback position
  const pxW = W - pad * 2, pxH = H - pad * 2;

  // Axis lines
  ctx.strokeStyle = '#1e1e1e'; ctx.lineWidth = 1;
  const x0 = toX(0), y0 = toY(0);
  if (x0 > pad && x0 < W - pad) {
    ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0, H); ctx.stroke();
  }
  if (y0 > pad && y0 < H - pad) {
    ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(W, y0); ctx.stroke();
  }

  // Covariance ellipses (axis-aligned, fading older ones)
  for (let i = 0; i < N; i++) {
    const step = trace[i];
    const age  = i / N;
    const cx   = toX(step.mu[dx]);
    const cy   = toY(step.mu[dy]);
    const rx   = Math.max(2, (step.sigma_diag[dx] / (hix - lox)) * pxW);
    const ry   = Math.max(2, (step.sigma_diag[dy] / (hiy - loy)) * pxH);
    const [r, g, b] = _hexToRgb(DIM_COLORS[dx]);
    ctx.strokeStyle = `rgba(${r},${g},${b},${0.05 + age * 0.2})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Mean trajectory trail
  for (let i = 1; i < N; i++) {
    const age  = i / N;
    const [r, g, b] = _hexToRgb(DIM_COLORS[dx]);
    ctx.strokeStyle = `rgba(${r},${g},${b},${0.15 + age * 0.75})`;
    ctx.lineWidth   = 1.5;
    ctx.beginPath();
    ctx.moveTo(toX(trace[i - 1].mu[dx]), toY(trace[i - 1].mu[dy]));
    ctx.lineTo(toX(trace[i].mu[dx]),     toY(trace[i].mu[dy]));
    ctx.stroke();
  }

  // Current mean (bold dot + σ ellipse)
  if (N > 0) {
    const last = trace[N - 1];
    const cx   = toX(last.mu[dx]);
    const cy   = toY(last.mu[dy]);
    const rx   = Math.max(3, (last.sigma_diag[dx] / (hix - lox)) * pxW);
    const ry   = Math.max(3, (last.sigma_diag[dy] / (hiy - loy)) * pxH);
    const [r, g, b] = _hexToRgb(DIM_COLORS[dx]);
    ctx.strokeStyle = `rgba(${r},${g},${b},0.7)`;
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = DIM_COLORS[dx];
    ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2); ctx.fill();
  }

  // Axis labels
  const NAMES = DIM_LABELS;
  ctx.fillStyle = '#444'; ctx.font = '9px monospace';
  ctx.fillText(NAMES[dx], W - 48, H - 4);
  ctx.save(); ctx.translate(11, H / 2 + 20); ctx.rotate(-Math.PI / 2);
  ctx.fillText(NAMES[dy], 0, 0); ctx.restore();
}

// ─── Viz 6: Structural Salience ω Backdrop ───────────────────────────────────
function _drawSalienceBackdrop(ctx, W, H, data) {
  const trace = data.trace;
  const dur   = data.total_dur || 1;
  const toX   = t => (t / dur) * W;
  const pad   = 16;
  const maxOm = Math.max(...trace.map(s => s.drama || 0), 0.01);

  // Background bands by character
  const CHAR_COLORS = {
    dramatic: '#7b3a3a', lyrical: '#3a5a7b', sparse: '#3a7b4a', turbulent: '#7b6a3a',
    volatile: '#6a2a6a', disciplined: '#2a3a5a', impressionist: '#4a3a6a',
    impulsive: '#7b2a2a', sight_reading: '#3a4a3a', memorised: '#2a5a5a',
  };
  let prevChar = null, prevX = 0;
  for (let i = 0; i < trace.length; i++) {
    const step = trace[i];
    if (step.character !== prevChar) {
      if (prevChar) {
        const col = CHAR_COLORS[prevChar] || '#333';
        ctx.fillStyle = col + '44';
        ctx.fillRect(prevX, 0, toX(step.t) - prevX, H);
      }
      prevChar = step.character;
      prevX = toX(step.t);
    }
  }
  if (prevChar) {
    const col = CHAR_COLORS[prevChar] || '#333';
    ctx.fillStyle = col + '44';
    ctx.fillRect(prevX, 0, W - prevX, H);
  }

  // ω bar chart (filled columns)
  for (let i = 0; i < trace.length; i++) {
    const step  = trace[i];
    const x     = toX(step.t);
    const bh    = ((step.drama || 0) / maxOm) * (H - pad * 2);
    const age   = i / trace.length;
    const alpha = 0.35 + age * 0.45;
    // Color by component if available — use drama as proxy
    const hue   = 220 - (step.drama / maxOm) * 180;
    ctx.fillStyle = `hsla(${hue},70%,55%,${alpha})`;
    ctx.fillRect(x - 2, H - pad - bh, 4, bh);
  }

  // Line overlay
  ctx.beginPath();
  trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = (H - pad) - ((step.drama || 0) / maxOm) * (H - pad * 2);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = 'rgba(200,200,255,0.55)';
  ctx.lineWidth   = 1.5;
  ctx.stroke();

  // Playhead: last trace point = "current"
  const lastX = toX(trace[trace.length - 1].t);
  ctx.strokeStyle = '#ff6'; ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(lastX, 0); ctx.lineTo(lastX, H); ctx.stroke();
  ctx.setLineDash([]);

  // Labels
  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('ω(t) — structural salience', 4, H - 4);
  ctx.fillStyle = '#222'; ctx.font = '8px monospace';
  ctx.fillText(`max=${maxOm.toFixed(3)}`, W - 62, H - 4);
  _drawTimeCursor(ctx, _vizCurrentT, dur, W, H);
}

// ─── Viz 7: Lookahead Prior φ Horizon Bars ────────────────────────────────────
function _drawLookaheadPhi(ctx, W, H, data) {
  const withPhi = data.trace.filter(s => s.phi && s.phi.length);
  if (!withPhi.length) {
    ctx.fillStyle = '#444'; ctx.font = '10px monospace';
    ctx.fillText('φ not in trace data', 8, H / 2 - 6);
    ctx.fillStyle = '#333'; ctx.font = '9px monospace';
    ctx.fillText('(re-run Trace)', 8, H / 2 + 10);
    return;
  }
  const D     = DIM_NAMES.length;
  const NAMES = DIM_LABELS;
  const last  = withPhi[withPhi.length - 1];
  const phi   = last.phi;

  const barH  = (H - 24) / D;
  const maxPhi = Math.max(...phi.map(Math.abs), 0.01);

  // Time-series sparklines (dim rows)
  for (let d = 0; d < D; d++) {
    const y0  = 12 + d * barH;
    const mid = y0 + barH / 2;
    const col = DIM_COLORS[d];
    const [r, g, b] = _hexToRgb(col);

    // Sparkline of phi[d] over time
    ctx.beginPath();
    withPhi.forEach((step, i) => {
      const x = (i / (withPhi.length - 1 || 1)) * W;
      const v = (step.phi[d] || 0);
      const y = mid - (v / maxPhi) * (barH * 0.45);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = `rgba(${r},${g},${b},0.5)`;
    ctx.lineWidth = 1;
    ctx.stroke();

    // Current bar
    const v    = phi[d] || 0;
    const bw   = (Math.abs(v) / maxPhi) * (W * 0.7);
    ctx.fillStyle = `rgba(${r},${g},${b},0.35)`;
    ctx.fillRect(v >= 0 ? W * 0.15 : W * 0.15 - bw, mid - barH * 0.3, bw, barH * 0.6);

    // Dim label + value
    ctx.fillStyle = `rgba(${r},${g},${b},0.7)`;
    ctx.font = '9px monospace';
    ctx.fillText(NAMES[d], 2, mid + 4);
    ctx.fillStyle = '#444'; ctx.font = '8px monospace';
    ctx.fillText(v.toFixed(2), W - 34, mid + 4);

    // Row separator
    ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, y0 + barH); ctx.lineTo(W, y0 + barH); ctx.stroke();
  }

  // Label
  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText(`φ @ t=${last.t.toFixed(1)}s`, 4, 10);
}

// ─── Viz 8: Process Noise Q(t) Envelope ──────────────────────────────────────
function _drawProcessNoise(ctx, W, H, data) {
  const withQ = data.trace.filter(s => s.Q_diag && s.Q_diag.length);
  if (!withQ.length) {
    ctx.fillStyle = '#444'; ctx.font = '10px monospace';
    ctx.fillText('Q not in trace data', 8, H / 2 - 6);
    ctx.fillStyle = '#333'; ctx.font = '9px monospace';
    ctx.fillText('(re-run Trace)', 8, H / 2 + 10);
    return;
  }
  const D   = DIM_NAMES.length;
  const dur = data.total_dur || 1;
  const toX = t => (t / dur) * W;
  const pad = 14;

  // Find max Q value for scaling
  let maxQ = 0;
  withQ.forEach(s => s.Q_diag.forEach(v => { if (v > maxQ) maxQ = v; }));
  maxQ = Math.max(maxQ, 1e-6);

  const toY = v => (H - pad) - (v / maxQ) * (H - pad * 2);

  // Also draw ω as grey backdrop
  const maxOm = Math.max(...data.trace.map(s => s.drama || 0), 0.01);
  ctx.beginPath();
  data.trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = (H - pad) - ((step.drama || 0) / maxOm) * (H - pad * 2) * 0.5;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = 'rgba(100,100,120,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Per-dim Q traces
  for (let d = 0; d < D; d++) {
    const col = DIM_COLORS[d];
    const [r, g, b] = _hexToRgb(col);
    ctx.strokeStyle = `rgba(${r},${g},${b},0.7)`;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    withQ.forEach((step, i) => {
      const x = toX(step.t);
      const y = toY(step.Q_diag[d] || 0);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  // ε(t) innovation energy as white dashed overlay
  ctx.strokeStyle = 'rgba(200,200,200,0.4)';
  ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
  const maxVol = Math.max(...data.trace.map(s => s.volatility || 0), 1e-6);
  ctx.beginPath();
  data.trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = (H - pad) - ((step.volatility || 0) / maxVol) * (H - pad * 2);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke(); ctx.setLineDash([]);

  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('Q(t) — process noise', 4, H - 4);
  ctx.fillStyle = '#222'; ctx.font = '8px monospace';
  ctx.fillText('ω grey  ε dash', W - 68, H - 4);
  _drawTimeCursor(ctx, _vizCurrentT, dur, W, H);
}

// ─── Viz 9: Innovation Energy ε(t) ───────────────────────────────────────────
function _drawInnovationEnergy(ctx, W, H, data) {
  const trace = data.trace;
  const dur   = data.total_dur || 1;
  const toX   = t => (t / dur) * W;
  const pad   = 14;

  // ε is in trace as `volatility`
  const maxVol = Math.max(...trace.map(s => s.volatility || 0), 1e-6);
  const toY    = v => (H - pad) - (v / maxVol) * (H - pad * 2);

  // Fill under curve
  ctx.beginPath();
  trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = toY(step.volatility || 0);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.lineTo(toX(trace[trace.length - 1].t), H - pad);
  ctx.lineTo(toX(trace[0].t), H - pad);
  ctx.closePath();
  ctx.fillStyle = 'rgba(180,120,60,0.15)';
  ctx.fill();

  // Line
  ctx.beginPath();
  trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = toY(step.volatility || 0);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#c8922a';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Tick marks at each contributing innovation event
  const withNu = trace.filter(s => s.nu && s.nu.length);
  withNu.forEach(step => {
    const nuNorm = step.nu.reduce((a, v) => a + v * v, 0);
    if (nuNorm > maxVol * 0.1) {
      const x = toX(step.t);
      const y = toY(step.volatility || 0);
      ctx.strokeStyle = 'rgba(255,200,100,0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); ctx.stroke();
    }
  });

  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('ε(t) — innovation energy', 4, H - 4);
  _drawTimeCursor(ctx, _vizCurrentT, dur, W, H);
}

// ─── Viz 10: Sample Scatter vs Posterior ─────────────────────────────────────
function _drawSampleScatter(ctx, W, H, data) {
  const trace = data.trace;
  const dx  = parseInt(document.getElementById('viz-dim-x')?.value ?? '0');
  const dy  = parseInt(document.getElementById('viz-dim-y')?.value ?? '1');
  // Auto-scale to actual sample range
  const xVals = trace.map(s => s.sample[dx]);
  const yVals = trace.map(s => s.sample[dy]);
  const pad = 24;
  let lox = Math.min(...xVals), hix = Math.max(...xVals);
  let loy = Math.min(...yVals), hiy = Math.max(...yVals);
  const xPad = (hix - lox) * 0.15 || 0.1, yPad = (hiy - loy) * 0.15 || 0.1;
  lox -= xPad; hix += xPad; loy -= yPad; hiy += yPad;
  const toX = v => pad + ((v - lox) / (hix - lox)) * (W - pad * 2);
  const toY = v => (H - pad) - ((v - loy) / (hiy - loy)) * (H - pad * 2);

  // Axis lines
  ctx.strokeStyle = '#1e1e1e'; ctx.lineWidth = 1;
  const ax = toX(0), ay = toY(0);
  if (ax > pad && ax < W - pad) { ctx.beginPath(); ctx.moveTo(ax, 0); ctx.lineTo(ax, H); ctx.stroke(); }
  if (ay > pad && ay < H - pad) { ctx.beginPath(); ctx.moveTo(0, ay); ctx.lineTo(W, ay); ctx.stroke(); }

  const N = trace.length;
  const [rx, gx, bx] = _hexToRgb(DIM_COLORS[dx]);
  const [ry, gy, by] = _hexToRgb(DIM_COLORS[dy]);

  const pxW = W - pad * 2, pxH = H - pad * 2;
  // 2σ and 1σ bands (evolving — draw all historical ellipses, fading)
  for (let i = 0; i < N; i++) {
    const step = trace[i];
    const cx   = toX(step.mu[dx]);
    const cy   = toY(step.mu[dy]);
    const rx2  = Math.max(2, (step.sigma_diag[dx] * 2 / (hix - lox)) * pxW);
    const ry2  = Math.max(2, (step.sigma_diag[dy] * 2 / (hiy - loy)) * pxH);
    const age  = i / N;
    ctx.strokeStyle = `rgba(${rx},${gx},${bx},${0.04 + age * 0.12})`;
    ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.ellipse(cx, cy, rx2, ry2, 0, 0, Math.PI * 2); ctx.stroke();
  }

  // Historical dots
  for (let i = 0; i < N; i++) {
    const step = trace[i];
    const age  = i / N;
    ctx.fillStyle = `rgba(${rx},${gx},${bx},${0.2 + age * 0.65})`;
    ctx.beginPath();
    ctx.arc(toX(step.sample[dx]), toY(step.sample[dy]), 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // Current mean
  if (N > 0) {
    const last = trace[N - 1];
    ctx.fillStyle = DIM_COLORS[dx];
    ctx.beginPath(); ctx.arc(toX(last.mu[dx]), toY(last.mu[dy]), 4, 0, Math.PI * 2); ctx.fill();
  }

  const NAMES = DIM_LABELS;
  ctx.fillStyle = '#444'; ctx.font = '9px monospace';
  ctx.fillText(NAMES[dx], W - 48, H - 4);
  ctx.save(); ctx.translate(11, H / 2 + 20); ctx.rotate(-Math.PI / 2);
  ctx.fillText(NAMES[dy], 0, 0); ctx.restore();
}

// ─── Viz 11: Regime Blend Timeline ───────────────────────────────────────────
function _drawRegimeBlend(ctx, W, H, data) {
  const trace  = data.trace;
  const golems = (typeof interpState !== 'undefined' && interpState.golems) || [];
  const dur    = data.total_dur || 1;
  const toX    = t => (t / dur) * W;
  const pad    = 16;

  // Build color map for character names
  const CHAR_COLS = {};
  if (typeof GOLEM_LABEL_COLORS !== 'undefined') Object.assign(CHAR_COLS, GOLEM_LABEL_COLORS);

  // Compute effective weight of each golem at each trace time
  if (!golems.length) {
    // No golem data — show character regions from trace
    let prevChar = null, prevX = 0;
    trace.forEach((step, i) => {
      if (step.character !== prevChar) {
        if (prevChar !== null) {
          const col = CHAR_COLS[prevChar] || '#555';
          ctx.fillStyle = col + '66';
          ctx.fillRect(prevX, pad, toX(step.t) - prevX, H - pad * 2);
          ctx.fillStyle = col + 'aa';
          ctx.font = '9px monospace';
          ctx.fillText(prevChar, prevX + 3, pad + 14);
        }
        prevChar = step.character;
        prevX = toX(step.t);
      }
    });
    if (prevChar !== null) {
      const col = CHAR_COLS[prevChar] || '#555';
      ctx.fillStyle = col + '66';
      ctx.fillRect(prevX, pad, W - prevX, H - pad * 2);
    }
  } else {
    // Draw golem blocks
    golems.forEach(g => {
      const x1  = toX(g.from || 0);
      const x2  = toX(g.to   || dur);
      const col = (typeof GOLEM_LABEL_COLORS !== 'undefined' && GOLEM_LABEL_COLORS[g.character]) || '#555';
      const [r, g2, b] = _hexToRgb(col);
      const isRW  = g.type === 'random_walk';
      ctx.fillStyle = `rgba(${r},${g2},${b},0.28)`;
      ctx.fillRect(x1, isRW ? H * 0.55 : pad, x2 - x1, isRW ? H * 0.45 - pad : H * 0.45);
      ctx.strokeStyle = `rgba(${r},${g2},${b},0.55)`;
      ctx.lineWidth = 1;
      ctx.strokeRect(x1, isRW ? H * 0.55 : pad, x2 - x1, isRW ? H * 0.45 - pad : H * 0.45);
      if (x2 - x1 > 30) {
        ctx.fillStyle = `rgba(${r},${g2},${b},0.8)`;
        ctx.font = '8px monospace';
        ctx.fillText(g.character || 'golem', x1 + 3, (isRW ? H * 0.55 : pad) + 11);
      }
    });
    // Divider line between Kalman (top) and RW (bottom) if mixed
    const hasRW = golems.some(g => g.type === 'random_walk');
    const hasK  = golems.some(g => g.type !== 'random_walk');
    if (hasRW && hasK) {
      ctx.strokeStyle = '#222'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, H * 0.55); ctx.lineTo(W, H * 0.55); ctx.stroke();
      ctx.fillStyle = '#333'; ctx.font = '8px monospace';
      ctx.fillText('Kalman', 2, pad + 10);
      ctx.fillText('RW', 2, H * 0.55 + 12);
    }
  }

  // ω line on top
  const maxOm = Math.max(...trace.map(s => s.drama || 0), 0.01);
  ctx.beginPath();
  trace.forEach((step, i) => {
    const x = toX(step.t);
    const y = H - pad - ((step.drama || 0) / maxOm) * (H * 0.25);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = 'rgba(200,200,100,0.4)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Playhead
  const lastX = toX(trace[trace.length - 1].t);
  ctx.strokeStyle = '#ff6'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(lastX, 0); ctx.lineTo(lastX, H); ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('regime blend + ω', 4, H - 4);
}

// ─── Viz 12: Full Covariance Matrix Σ(t) ─────────────────────────────────────
function _drawCovarianceMatrix(ctx, W, H, data) {
  const withSigma = data.trace.filter(s => s.Sigma && s.Sigma.length);
  if (!withSigma.length) {
    ctx.fillStyle = '#444'; ctx.font = '10px monospace';
    ctx.fillText('Σ not in trace data', 8, H / 2 - 6);
    ctx.fillStyle = '#333'; ctx.font = '9px monospace';
    ctx.fillText('(re-run Trace)', 8, H / 2 + 10);
    return;
  }
  const D     = DIM_NAMES.length;
  const NAMES = DIM_LABELS;
  const padL  = 26, padT = 20, padR = 4, padB = 14;
  const cellW = (W - padL - padR) / D;
  const cellH = (H - padT - padB) / D;
  const last  = withSigma[withSigma.length - 1];
  const Sig   = last.Sigma;

  // Max value for normalisation (use 95th percentile to avoid outlier dominance)
  const vals = [];
  Sig.forEach(row => row.forEach(v => vals.push(Math.abs(v))));
  vals.sort((a, b) => a - b);
  const maxSig = vals[Math.floor(vals.length * 0.95)] || 0.01;

  // Headers
  ctx.fillStyle = '#444'; ctx.font = '8px monospace';
  NAMES.forEach((n, i) => ctx.fillText(n, padL + i * cellW + 2, padT - 5));
  NAMES.forEach((n, i) => ctx.fillText(n, 1, padT + i * cellH + cellH * 0.65));

  for (let row = 0; row < D; row++) {
    for (let col = 0; col < D; col++) {
      const v  = Math.abs((Sig[row] || [])[col] || 0);
      const br = Math.min(1, v / maxSig);
      const isDiag = row === col;
      // Diagonal = row dim color; off-diagonal = blend
      const [r, g, b] = isDiag
        ? _hexToRgb(DIM_COLORS[row])
        : [80, 80, 100];
      ctx.fillStyle = `rgba(${r},${g},${b},${br * 0.9 + 0.04})`;
      const cx = padL + col * cellW + 1;
      const cy = padT + row * cellH + 1;
      ctx.fillRect(cx, cy, cellW - 2, cellH - 2);
      if (cellW > 20) {
        ctx.fillStyle = '#555'; ctx.font = '7px monospace';
        ctx.fillText(v.toFixed(3), cx + 1, cy + cellH * 0.65);
      }
    }
  }

  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText(`Σ(t) @ t=${last.t.toFixed(1)}s`, padL, H - 3);
}

// ─── Viz 16: Dimension Correlation Web ───────────────────────────────────────
function _drawCorrelationWeb(ctx, W, H, data) {
  const withSigma = data.trace.filter(s => s.Sigma && s.Sigma.length);
  if (!withSigma.length) {
    ctx.fillStyle = '#444'; ctx.font = '10px monospace';
    ctx.fillText('Σ not in trace data', 8, H / 2 - 6);
    ctx.fillStyle = '#333'; ctx.font = '9px monospace';
    ctx.fillText('(re-run Trace)', 8, H / 2 + 10);
    return;
  }
  const D    = DIM_NAMES.length;
  const Sig  = withSigma[withSigma.length - 1].Sigma;
  const NAMES = DIM_LABELS;
  const cx   = W / 2, cy = H / 2;
  const rad  = Math.min(W, H) * 0.36;

  // Node positions (pentagon)
  const nodes = Array.from({ length: D }, (_, i) => {
    const angle = (i / D) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(angle) * rad, y: cy + Math.sin(angle) * rad };
  });

  // Compute correlation matrix from covariance: r_ij = Σ_ij / sqrt(Σ_ii * Σ_jj)
  const corr = Array.from({ length: D }, (_, i) =>
    Array.from({ length: D }, (_, j) => {
      const denom = Math.sqrt(Math.abs((Sig[i] || [])[i] || 0) * Math.abs((Sig[j] || [])[j] || 0));
      return denom > 1e-8 ? ((Sig[i] || [])[j] || 0) / denom : 0;
    })
  );

  // Draw edges (thickness = |correlation|, color = sign)
  for (let i = 0; i < D; i++) {
    for (let j = i + 1; j < D; j++) {
      const r   = corr[i][j];
      const abs = Math.abs(r);
      if (abs < 0.05) continue;
      ctx.lineWidth   = abs * 6;
      ctx.strokeStyle = r > 0 ? `rgba(100,200,120,${abs * 0.85})` : `rgba(200,100,100,${abs * 0.85})`;
      ctx.beginPath();
      ctx.moveTo(nodes[i].x, nodes[i].y);
      ctx.lineTo(nodes[j].x, nodes[j].y);
      ctx.stroke();
      // Midpoint label for strong correlations
      if (abs > 0.3) {
        const mx = (nodes[i].x + nodes[j].x) / 2;
        const my = (nodes[i].y + nodes[j].y) / 2;
        ctx.fillStyle = r > 0 ? 'rgba(100,200,120,0.8)' : 'rgba(200,100,100,0.8)';
        ctx.font = '8px monospace';
        ctx.fillText(r.toFixed(2), mx - 10, my + 3);
      }
    }
  }

  // Draw nodes
  for (let i = 0; i < D; i++) {
    const n   = nodes[i];
    const col = DIM_COLORS[i];
    const [r, g, b] = _hexToRgb(col);
    // Self-correlation = sqrt(sigma)
    const selfSig = Math.sqrt(Math.abs((Sig[i] || [])[i] || 0));
    const nodeR   = Math.max(5, Math.min(16, selfSig * 8 + 5));
    ctx.fillStyle = `rgba(${r},${g},${b},0.7)`;
    ctx.beginPath(); ctx.arc(n.x, n.y, nodeR, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#ddd'; ctx.font = '8px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(NAMES[i], n.x, n.y + 3);
    ctx.textAlign = 'left';
  }

  ctx.fillStyle = '#333'; ctx.font = '9px monospace';
  ctx.fillText('correlation web — off-diag Σ', 4, H - 4);
}

// ─── Viz 17: Distribution Shape Indicator ────────────────────────────────────
function _drawDistributionShape(ctx, W, H, data) {
  const trace = data.trace;
  const D     = DIM_NAMES.length;
  const rowH  = H / D;
  const STEPS = 80;
  const NAMES = DIM_LABELS;

  // Distribution PDF functions (all normalised to peak=1)
  const pdfs = {
    gaussian:  (z) => Math.exp(-0.5 * z * z),
    laplace:   (z) => Math.exp(-Math.abs(z)),
    cauchy:    (z) => 1 / (1 + z * z),
    uniform:   (z) => Math.abs(z) <= 1.73 ? 1 : 0,
    beta:      (z) => { const u = (z + 3) / 6; return (u > 0 && u < 1) ? Math.pow(u * (1 - u), 1) * 4 : 0; },
    student_t: (z) => Math.pow(1 + z * z / 3, -2),
    bimodal:   (z) => Math.exp(-0.5 * (z - 1.5) * (z - 1.5)) + Math.exp(-0.5 * (z + 1.5) * (z + 1.5)),
    mixture:   (z) => Math.exp(-0.5 * z * z) * 0.85 + Math.exp(-0.5 * ((z - 3) / 0.4) * ((z - 3) / 0.4)) * 0.4,
    skew_normal: (z) => Math.exp(-0.5 * z * z) * (1 + Math.tanh(z * 1.5)),
    truncated: (z) => Math.abs(z) <= 2 ? Math.exp(-0.5 * z * z) : 0,
  };

  const last = trace[trace.length - 1];
  const dist = last.distribution || 'gaussian';
  const pdfFn = pdfs[dist] || pdfs.gaussian;

  for (let d = 0; d < D; d++) {
    const y0  = d * rowH;
    const y1  = (d + 1) * rowH - 1;
    const mid = (y0 + y1) / 2;
    const col = DIM_COLORS[d];
    const [r, g, b] = _hexToRgb(col);

    // Draw mini density curve
    ctx.beginPath();
    const scaleH = rowH * 0.42;
    for (let i = 0; i <= STEPS; i++) {
      const z  = -3.5 + (i / STEPS) * 7;   // z from -3.5 to +3.5
      const px = (i / STEPS) * W;
      const py = mid - pdfFn(z) * scaleH;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.strokeStyle = col;
    ctx.lineWidth   = 1.5;
    ctx.stroke();

    // Fill under curve
    ctx.beginPath();
    for (let i = 0; i <= STEPS; i++) {
      const z  = -3.5 + (i / STEPS) * 7;
      const px = (i / STEPS) * W;
      const py = mid - pdfFn(z) * scaleH;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.lineTo(W, mid); ctx.lineTo(0, mid); ctx.closePath();
    ctx.fillStyle = `rgba(${r},${g},${b},0.08)`;
    ctx.fill();

    // Current sample tick
    const mu  = last.mu[d];
    const sig = Math.max(last.sigma_diag[d], 1e-6);
    const [lo, hi] = DIM_RANGES[d];
    const z_sample = (last.sample[d] - mu) / sig;
    const sx = ((z_sample + 3.5) / 7) * W;
    ctx.strokeStyle = col; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(sx, mid - 8); ctx.lineTo(sx, mid + 8); ctx.stroke();

    // Dim label and distribution name
    ctx.fillStyle = `rgba(${r},${g},${b},0.6)`;
    ctx.font = '9px monospace';
    ctx.fillText(NAMES[d], 3, y0 + 11);

    ctx.fillStyle = '#333'; ctx.font = '8px monospace';
    ctx.fillText(dist, W - dist.length * 5 - 4, y0 + 11);

    // Row separator
    ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, y1 + 1); ctx.lineTo(W, y1 + 1); ctx.stroke();
  }
}

// ─── Playback cursor helpers ──────────────────────────────────────────────────
// ─── Viz 20: Step Histogram (Random Walk) ────────────────────────────────────
function _drawStepHistogram(ctx, W, H, data) {
  const trace = data.trace;
  if (!trace.length) return;
  const D = DIM_NAMES.length;
  // Compute step increments per dim (Δ sample between consecutive trace points)
  const deltas = []; // array of per-dim delta arrays
  for (let d = 0; d < D; d++) deltas.push([]);
  for (let i = 1; i < trace.length; i++) {
    const a = trace[i - 1].sample, b = trace[i].sample;
    if (!a || !b) continue;
    for (let d = 0; d < D; d++) deltas[d].push(b[d] - a[d]);
  }
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(0, 0, W, H);
  const rows = 4, cols = 3;
  const cellW = W / cols, cellH = H / rows;
  const NBINS = 20;
  ctx.font = '8px Courier New';
  for (let d = 0; d < D; d++) {
    const col = d % cols, row = Math.floor(d / cols);
    const x0 = col * cellW, y0 = row * cellH;
    const vals = deltas[d];
    if (!vals.length) continue;
    const absMax = Math.max(...vals.map(Math.abs)) || 1;
    const bins = new Array(NBINS).fill(0);
    for (const v of vals) {
      const bi = Math.floor(((v / absMax + 1) / 2) * NBINS);
      bins[Math.max(0, Math.min(NBINS - 1, bi))]++;
    }
    const maxBin = Math.max(...bins);
    const [r, g, b] = _hexToRgb(DIM_COLORS[d % DIM_COLORS.length]);
    const barW = (cellW - 8) / NBINS;
    ctx.fillStyle = `rgba(${r},${g},${b},0.7)`;
    for (let bi = 0; bi < NBINS; bi++) {
      const h = (bins[bi] / maxBin) * (cellH - 14);
      ctx.fillRect(x0 + 4 + bi * barW, y0 + cellH - 4 - h, barW - 1, h);
    }
    // Center line (delta = 0)
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.beginPath();
    ctx.moveTo(x0 + 4 + cellW / 2 - 4, y0 + 10);
    ctx.lineTo(x0 + 4 + cellW / 2 - 4, y0 + cellH - 4);
    ctx.stroke();
    // Label
    ctx.fillStyle = 'rgba(200,200,200,0.55)';
    ctx.fillText(DIM_LABELS[d], x0 + 4, y0 + 9);
  }
}

// ─── Viz 21: Drift Trajectory (Random Walk) ──────────────────────────────────
function _drawDriftTrajectory(ctx, W, H, data) {
  const trace = data.trace;
  if (!trace.length) return;
  const D = DIM_NAMES.length;
  const padL = 22, padR = 8, padT = 6, padB = 14;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  ctx.fillStyle = '#0a0a0a'; ctx.fillRect(0, 0, W, H);
  // Y-axis label
  ctx.fillStyle = '#555'; ctx.font = '9px Courier New';
  ctx.fillText('drift', 3, padT + 10);
  // Zero line
  ctx.strokeStyle = '#222'; ctx.setLineDash([2, 4]);
  const y0 = padT + plotH / 2;
  ctx.beginPath(); ctx.moveTo(padL, y0); ctx.lineTo(W - padR, y0); ctx.stroke();
  ctx.setLineDash([]);

  // For each dim, compute cumulative deviation from sample[0]
  const n = trace.length;
  for (let d = 0; d < D; d++) {
    const base = trace[0].sample ? trace[0].sample[d] : 0;
    const vals = trace.map(s => (s.sample ? s.sample[d] : 0) - base);
    const absMax = Math.max(...vals.map(Math.abs)) || 1;
    const [r, g, b] = _hexToRgb(DIM_COLORS[d % DIM_COLORS.length]);
    ctx.strokeStyle = `rgba(${r},${g},${b},0.8)`;
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = padL + (i / (n - 1 || 1)) * plotW;
      const y = y0 - (vals[i] / absMax) * (plotH / 2 - 4);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.fillStyle = '#444'; ctx.font = '8px Courier New';
  ctx.fillText('cumulative deviation from initial sample, per dim', padL, H - 3);
}

// ─── Viz 22: Fixed State Bars (Discrete) ─────────────────────────────────────
function _drawFixedStateBars(ctx, W, H, data) {
  const trace = data.trace;
  if (!trace.length) return;
  const D = DIM_NAMES.length;
  // Take the first step's sample (all steps identical for discrete)
  const vals = trace[0].sample || trace[0].mu;
  if (!vals) return;
  ctx.fillStyle = '#0a0a0a'; ctx.fillRect(0, 0, W, H);
  const padL = 80, padR = 20, padT = 6;
  const rowH = Math.floor((H - 10) / D);
  ctx.font = '10px Courier New';
  for (let d = 0; d < D; d++) {
    const [lo, hi] = DIM_RANGES[d];
    const frac = Math.max(0, Math.min(1, (vals[d] - lo) / (hi - lo)));
    const y = padT + d * rowH;
    const barW = frac * (W - padL - padR);
    // Label
    ctx.fillStyle = DIM_COLORS[d % DIM_COLORS.length];
    ctx.fillText(DIM_LABELS[d], 4, y + rowH * 0.7);
    // Bar background
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(padL, y + 2, W - padL - padR, rowH - 4);
    // Bar fill
    const [r, g, b] = _hexToRgb(DIM_COLORS[d % DIM_COLORS.length]);
    ctx.fillStyle = `rgba(${r},${g},${b},0.85)`;
    ctx.fillRect(padL, y + 2, barW, rowH - 4);
    // Value text
    ctx.fillStyle = '#ccc';
    const v = vals[d];
    const vstr = Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
    ctx.fillText(vstr, W - padR - 3 - ctx.measureText(vstr).width, y + rowH * 0.7);
  }
}

// ─── Viz dropdown dynamic population ─────────────────────────────────────────
const _VIZ_CATALOG = [
  { v: 1,  label: 'Marginal Gaussians',     scope: 'kalman'    },
  { v: 2,  label: 'Kalman Gain',            scope: 'kalman'    },
  { v: 3,  label: 'Innovation Trace',       scope: 'kalman'    },
  { v: 4,  label: 'Phase Portrait',         scope: 'universal' },
  { v: 5,  label: 'State Trajectory',       scope: 'universal' },
  { v: 6,  label: 'Salience Backdrop ω',    scope: 'kalman'    },
  { v: 7,  label: 'Lookahead Prior φ',      scope: 'kalman'    },
  { v: 8,  label: 'Process Noise Q(t)',     scope: 'kalman'    },
  { v: 9,  label: 'Innovation Energy ε',    scope: 'kalman'    },
  { v: 10, label: 'Sample Scatter',         scope: 'universal' },
  { v: 11, label: 'Regime Blend',           scope: 'universal' },
  { v: 12, label: 'Covariance Σ(t)',        scope: 'kalman'    },
  { v: 16, label: 'Correlation Web',        scope: 'universal' },
  { v: 17, label: 'Distribution Shape',     scope: 'universal' },
  { v: 20, label: 'Step Histogram',         scope: 'random_walk' },
  { v: 21, label: 'Drift Trajectory',       scope: 'random_walk' },
  { v: 22, label: 'Fixed State Bars',       scope: 'discrete'  },
];

function refreshVizDropdown(traceData) {
  const sel = document.getElementById('viz-panel-select');
  if (!sel) return;
  // Determine active golem types from the user's explicit golems.
  // (Trace steps outside any golem default to Kalman internally — we ignore that.)
  const types = new Set();
  if (typeof interpState !== 'undefined' && interpState.golems && interpState.golems.length > 0) {
    for (const g of interpState.golems) types.add(g.type || 'kalman');
  } else {
    // No explicit golems → default Kalman runs
    types.add('kalman');
  }

  // Filter: universal always in; type-specific if that type is active
  const allowed = _VIZ_CATALOG.filter(v =>
    v.scope === 'universal' || types.has(v.scope)
  );
  const prev = _activeViz;
  const stillAvailable = allowed.some(v => v.v === prev);
  const defaultViz = allowed[0] ? allowed[0].v : 1;
  const selectedViz = stillAvailable ? prev : defaultViz;
  sel.innerHTML = allowed.map(v =>
    `<option value="${v.v}"${v.v === selectedViz ? ' selected' : ''}>${v.v} — ${v.label}</option>`
  ).join('');
  _activeViz = selectedViz;
}


function _cursorIdx(trace) {
  if (_vizCurrentT < 0 || !trace.length) return trace.length - 1;
  let best = 0;
  for (let i = 0; i < trace.length; i++) {
    if (trace[i].t <= _vizCurrentT) best = i;
    else break;
  }
  return best;
}

function _drawTimeCursor(ctx, t, totalDur, W, H) {
  if (_vizCurrentT < 0) return;
  const x = (t / (totalDur || 1)) * W;
  ctx.save();
  ctx.strokeStyle = 'rgba(255,240,100,0.7)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
}

// ─── Wiring ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  refreshVizDropdown(null);
  const sel = document.getElementById('viz-panel-select');
  if (sel) {
    sel.addEventListener('change', () => {
      _activeViz = parseInt(sel.value);
      if (typeof _lastTraceData !== 'undefined' && _lastTraceData)
        updateVizPanel(_lastTraceData);
    });
  }
  // Populate dimension selectors from DIM_NAMES (12D)
  ['viz-dim-x', 'viz-dim-y'].forEach((id, si) => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = DIM_NAMES.map((_, i) =>
        `<option value="${i}"${(si === 0 && i === 0) || (si === 1 && i === 1) ? ' selected' : ''}>${DIM_LABELS[i]}</option>`
      ).join('');
      el.addEventListener('change', () => {
        if (typeof _lastTraceData !== 'undefined' && _lastTraceData)
          updateVizPanel(_lastTraceData);
      });
    }
  });
});
