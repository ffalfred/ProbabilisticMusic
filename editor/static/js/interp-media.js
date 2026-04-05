// ─── interp-media.js ──────────────────────────────────────────────────────────
// Interpreter workspace: waveform strip + score/metadata image panels.
// Reads/writes shared globals: state, scoreView, score2View (from state.js/draw.js).
// Depends on: kalman-trace.js (_niceTickInterval), draw.js (drawScoreOverlay, loadFile)

// ─── Dynamics colors ─────────────────────────────────────────────────────────
const _DCOLORS = {
  ppp:'#3a5a8a', pp:'#4a70aa', p:'#5a88cc', mp:'#70a0cc',
  mf:'#80aa60', f:'#aaaa40', ff:'#ccaa20', fff:'#cc8020',
  sfz:'#cc4020', fp:'#cc6040',
  crescendo:'#4a8a5a', decrescendo:'#8a5a4a',
};

// ─── Waveform ─────────────────────────────────────────────────────────────────
async function _loadInterpWave() {
  const pathEl   = document.getElementById('interp-audio-path');
  const statusEl = document.getElementById('interp-render-status');
  const path = pathEl ? pathEl.value.trim() : '';
  if (!path) { if (statusEl) statusEl.textContent = 'select audio first'; return; }
  const composerPathEl = document.getElementById('path-input');
  if (composerPathEl) composerPathEl.value = path;
  await loadFile();
  if (!interpState.scoreDuration) interpState.scoreDuration = state.duration;
  if (statusEl) statusEl.textContent = path.split('/').pop() + (state.duration ? ` (${state.duration.toFixed(1)}s)` : '');
  _drawInterpWave();
}

function _drawInterpWave() {
  const wrap   = document.getElementById('interp-wave-wrap');
  const canvas = document.getElementById('interp-wave-canvas');
  if (!wrap || !canvas) return;
  const W = wrap.clientWidth  || 800;
  const H = wrap.clientHeight || 140;
  canvas.width  = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, W, H);

  const dur = interpState.scoreDuration || state.duration || 1;
  const midY = H / 2;

  // Time grid
  const step = _niceTickInterval(dur, Math.floor(W / 80));
  ctx.strokeStyle = '#191919';
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  for (let t = step; t < dur; t += step) {
    const x = (t / dur) * W;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
  }

  // Waveform bars
  const peaks = state.waveform;
  if (peaks && peaks.length) {
    const barW = Math.max(1, W / peaks.length);
    ctx.fillStyle = '#3a5a4a';
    for (let i = 0; i < peaks.length; i++) {
      const x = (i / peaks.length) * W;
      const amp = peaks[i] * (H * 0.45);
      ctx.fillRect(x, midY - amp, barW, amp * 2);
    }
    ctx.strokeStyle = '#2a3a30';
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(0, midY); ctx.lineTo(W, midY); ctx.stroke();
  }

  // Ruler labels
  ctx.font = '9px Courier New';
  ctx.fillStyle = '#333';
  for (let t = step; t < dur; t += step) {
    const x = (t / dur) * W;
    ctx.fillText(t.toFixed(1), x + 2, H - 3);
  }

  // Dynamics overlay
  const dynamics = (interpState.scoreDynamics && interpState.scoreDynamics.length)
    ? interpState.scoreDynamics
    : (state.dynamics || []);
  if (dynamics.length) _drawInterpDynamicsOverlay(ctx, W, H, dur, dynamics);

  // Playback cursor
  if (state.currentTime > 0 && dur > 0) {
    const cx = (state.currentTime / dur) * W;
    ctx.strokeStyle = 'rgba(255,80,80,0.6)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}

function _drawInterpDynamicsOverlay(ctx, W, H, dur, dynamics) {
  const midY = H / 2;
  dynamics.forEach(d => {
    const mark = d.mark || d.marking || '';
    if (!mark) return;
    const color = _DCOLORS[mark] || '#555';

    if (mark === 'crescendo' || mark === 'decrescendo') {
      const x0 = ((d.from != null ? d.from : (d.t || 0)) / dur) * W;
      const x1 = ((d.to   != null ? d.to   : dur)        / dur) * W;
      const spread = Math.min(H * 0.28, (x1 - x0) * 0.4);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);
      ctx.beginPath();
      if (mark === 'crescendo') {
        ctx.moveTo(x0, midY); ctx.lineTo(x1, midY - spread);
        ctx.moveTo(x0, midY); ctx.lineTo(x1, midY + spread);
      } else {
        ctx.moveTo(x0, midY - spread); ctx.lineTo(x1, midY);
        ctx.moveTo(x0, midY + spread); ctx.lineTo(x1, midY);
      }
      ctx.stroke();
      ctx.font = '8px Courier New';
      ctx.fillStyle = color;
      ctx.fillText(mark === 'crescendo' ? 'cresc' : 'decresc', x0 + 3, midY - spread - 3);
    } else {
      const x = ((d.t || 0) / dur) * W;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.5;
      ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
      ctx.font = 'bold 10px Courier New';
      const tw = ctx.measureText(mark).width;
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(x + 2, 3, tw + 4, 14);
      ctx.fillStyle = color;
      ctx.fillText(mark, x + 4, 14);
    }
  });
}

// ─── Score / metadata image panels ───────────────────────────────────────────
function _loadInterpImg(pathId, which) {
  const pathEl = document.getElementById(pathId);
  if (!pathEl) return;
  const path = pathEl.value.trim();
  if (!path) return;

  const img = new Image();
  img.onload = () => {
    if (which === 'score') {
      scoreView.img       = img;
      scoreView.path      = path;
      scoreView.start     = 0;
      scoreView.end       = interpState.scoreDuration || state.duration || 0;
      scoreView.panOffset = 0;
      const el = document.getElementById('score-path-input');
      if (el) el.value = path;
      document.getElementById('interp-frame-container').style.display = '';
      document.getElementById('interp-toggle-score-btn')?.classList.add('active');
      _drawInterpFrameCanvas();
    } else {
      score2View.img       = img;
      score2View.path      = path;
      score2View.start     = 0;
      score2View.end       = interpState.scoreDuration || state.duration || 0;
      score2View.panOffset = 0;
      const el = document.getElementById('score2-path-input');
      if (el) el.value = path;
      document.getElementById('interp-score2-wrap').style.display = '';
      _drawInterpScore2Canvas();
    }
    if (typeof draw === 'function') draw();
  };
  img.onerror = () => console.warn('Failed to load image:', path);
  img.src = `/image?path=${encodeURIComponent(path)}`;
}

function _drawInterpFrameCanvas() {
  const cont = document.getElementById('interp-frame-container');
  const cvs  = document.getElementById('interp-frame-canvas');
  if (!cont || !cvs || cont.style.display === 'none') return;
  cvs.width  = cont.clientWidth  || 800;
  cvs.height = cont.clientHeight || 180;
  drawScoreOverlay(cvs, cvs.getContext('2d'), scoreView);
}

function _drawInterpScore2Canvas() {
  const cont = document.getElementById('interp-score2-wrap');
  const cvs  = document.getElementById('interp-score2-canvas');
  if (!cont || !cvs || cont.style.display === 'none') return;
  cvs.width  = cont.clientWidth  || 800;
  cvs.height = cont.clientHeight || 160;
  drawScoreOverlay(cvs, cvs.getContext('2d'), score2View);
}

function _drawInterpScoreCanvas() {
  _drawInterpFrameCanvas();
  _drawInterpScore2Canvas();
}

// ─── DOMContentLoaded wiring ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const loadWaveBtn = document.getElementById('interp-load-wave-btn');
  if (loadWaveBtn) loadWaveBtn.addEventListener('click', _loadInterpWave);

  const loadScoreImgBtn = document.getElementById('interp-load-score-img-btn');
  if (loadScoreImgBtn) loadScoreImgBtn.addEventListener('click', () => _loadInterpImg('interp-score-img-path', 'score'));

  const loadMetaImgBtn = document.getElementById('interp-load-meta-img-btn');
  if (loadMetaImgBtn) loadMetaImgBtn.addEventListener('click', () => _loadInterpImg('interp-meta-img-path', 'meta'));

  const toggleScoreBtn = document.getElementById('interp-toggle-score-btn');
  if (toggleScoreBtn) {
    toggleScoreBtn.addEventListener('click', () => {
      const fc = document.getElementById('interp-frame-container');
      const s2 = document.getElementById('interp-score2-wrap');
      const visible = fc && fc.style.display !== 'none';
      const next = visible ? 'none' : '';
      if (fc) fc.style.display = next;
      if (s2 && score2View.img) s2.style.display = next;
      toggleScoreBtn.classList.toggle('active', !visible);
      if (!visible) setTimeout(_drawInterpScoreCanvas, 10);
    });
  }

  // Redraw image panels when Interpreter tab is activated
  document.addEventListener('workspace:activated', e => {
    if (e.detail !== 'interpreter') return;
    if (scoreView.img) {
      const fc = document.getElementById('interp-frame-container');
      if (fc) fc.style.display = '';
      document.getElementById('interp-toggle-score-btn')?.classList.add('active');
    }
    if (score2View.img) {
      const s2 = document.getElementById('interp-score2-wrap');
      if (s2) s2.style.display = '';
    }
    if (scoreView.img || score2View.img) setTimeout(_drawInterpScoreCanvas, 25);
  });
});
