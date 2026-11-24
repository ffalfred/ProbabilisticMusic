// ─── Drawn automation curves, inside effect popups ──────────────────────────
// An automated effect setting (see the "~" button in an effect chain) gets a
// small canvas under its text: click to add a point, drag to move it,
// right-click to delete it. It covers the time the effect processes — the
// zone, the event's sound, the track or the whole piece — and, where that
// stretch of the timeline is known, shows its waveform behind the curve.
// The canvas and the text ("0s: 200, 2s: 3000") stay in sync both ways.

// Seconds the effect covers, and where they start on the timeline (for the
// waveform backdrop; null when unknown). Popups set this before opening.
let _curveCtx = { span: 10, t0: null };
function setCurveContext(span, t0) {
  _curveCtx = { span: Math.max(0.1, +span || 10), t0: (t0 == null || isNaN(+t0)) ? null : +t0 };
}

// Vertical ranges for settings whose schema has no min/max
const _CURVE_RANGES = {
  cutoff: [20, 20000], freq_hz: [20, 20000], low_hz: [20, 20000], high_hz: [20, 20000],
  resonance: [0, 1], rate: [0.1, 20], depth: [0, 1], delay_sec: [0.01, 2], time: [0.01, 2],
  threshold_db: [-60, 0], ratio: [1, 20], attack: [0.001, 0.5], release: [0.01, 3],
  makeup_db: [-12, 24], gain_db: [-24, 24], q: [0.1, 10], cents: [-1200, 1200],
  semitones: [-12, 12], delay_ms: [0, 20], shift_hz: [-1000, 1000],
};

function _curveRange(spec, pts) {
  let lo, hi;
  if (spec.min != null && spec.max != null) { lo = +spec.min; hi = +spec.max; }
  else if (_CURVE_RANGES[spec.key]) [lo, hi] = _CURVE_RANGES[spec.key];
  else { lo = spec.min != null ? +spec.min : 0; hi = Math.max(lo + 1, Math.abs(+spec.def || 1) * 2); }
  for (const p of pts) { if (p[1] < lo) lo = p[1]; if (p[1] > hi) hi = p[1]; }
  const log = /cutoff|freq|_hz$/.test(spec.key) && lo > 0;
  return { lo, hi: hi > lo ? hi : lo + 1, log };
}

function _curveCanvasHTML(id, spec) {
  return `<canvas id="${id}-cvs" class="fx-curve-cvs" data-input="${id}" data-key="${spec.key}"
            width="420" height="80" title="click: add a point · drag: move · right-click: delete"
            style="display:block;width:100%;height:80px;margin:2px 0 4px 94px;max-width:calc(100% - 94px);
                   background:#0d0d0d;border:1px solid #2a2040;cursor:crosshair;"></canvas>`;
}

// Wire every curve canvas in a freshly rendered FX chain
function _initCurveCanvases(root) {
  (root || document).querySelectorAll("canvas.fx-curve-cvs").forEach(cvs => {
    const input = document.getElementById(cvs.dataset.input);
    if (!input) return;
    const m = cvs.dataset.input.match(/^p-fxr-(\d+)-/);
    const fx = m ? _fxChain[+m[1]] : null;
    const spec = (fx ? _fxParamSpecs(fx.type) : []).find(s => s.key === cvs.dataset.key) || { key: cvs.dataset.key, def: 0 };
    const ed = { cvs, input, spec, drag: -1 };
    cvs._curve = ed;
    input.addEventListener("input", () => _curveDraw(ed));
    cvs.addEventListener("contextmenu", e => e.preventDefault());
    cvs.addEventListener("mousedown", e => _curveDown(ed, e));
    cvs.addEventListener("mousemove", e => { if (ed.drag >= 0) _curveMove(ed, e); });
    cvs.addEventListener("mouseup", () => { ed.drag = -1; });
    cvs.addEventListener("mouseleave", () => { ed.drag = -1; });
    _curveDraw(ed);
  });
}

function _curvePoints(ed) {
  const c = _parseCurve(ed.input.value);
  return c ? c.curve : [[0, +ed.spec.def || 0]];
}

function _curveGeom(ed, pts) {
  const W = ed.cvs.width, H = ed.cvs.height, pad = 6;
  const span = Math.max(_curveCtx.span, ...pts.map(p => p[0] * 1.05), 0.1);
  const r = _curveRange(ed.spec, pts);
  const norm = v => r.log ? Math.log(v / r.lo) / Math.log(r.hi / r.lo) : (v - r.lo) / (r.hi - r.lo);
  const unnorm = u => r.log ? r.lo * Math.pow(r.hi / r.lo, u) : r.lo + u * (r.hi - r.lo);
  return {
    W, H, span, r,
    x: t => (t / span) * W,
    y: v => pad + (1 - Math.min(1, Math.max(0, norm(v)))) * (H - 2 * pad),
    t: x => Math.max(0, Math.min(span, (x / W) * span)),
    v: y => unnorm(Math.min(1, Math.max(0, 1 - (y - pad) / (H - 2 * pad)))),
  };
}

function _curveEventXY(ed, e) {
  const rect = ed.cvs.getBoundingClientRect();
  return [(e.clientX - rect.left) * (ed.cvs.width / rect.width),
          (e.clientY - rect.top) * (ed.cvs.height / rect.height)];
}

function _curveRound(ed, t, v) {
  const step = +ed.spec.step || 0;
  const vr = step >= 1 ? Math.round(v / step) * step
           : Math.abs(v) >= 100 ? Math.round(v) : +v.toPrecision(3);
  return [Math.round(t * 100) / 100, vr];
}

function _curveWrite(ed, pts) {
  pts.sort((a, b) => a[0] - b[0]);
  ed.input.value = _curveText({ curve: pts });
  _curveDraw(ed);
}

function _curveDown(ed, e) {
  const pts = _curvePoints(ed), g = _curveGeom(ed, pts);
  const [x, y] = _curveEventXY(ed, e);
  const hit = pts.findIndex(p => Math.abs(g.x(p[0]) - x) < 8 && Math.abs(g.y(p[1]) - y) < 8);
  if (e.button === 2) {                              // delete (keep at least one point)
    if (hit >= 0 && pts.length > 1) { pts.splice(hit, 1); _curveWrite(ed, pts); }
    return;
  }
  if (hit >= 0) { ed.drag = hit; return; }
  pts.push(_curveRound(ed, g.t(x), g.v(y)));
  _curveWrite(ed, pts);
  ed.drag = _curvePoints(ed).findIndex(p => p[0] === pts[pts.length - 1][0]);
}

function _curveMove(ed, e) {
  const pts = _curvePoints(ed), g = _curveGeom(ed, pts);
  const [x, y] = _curveEventXY(ed, e);
  if (!pts[ed.drag]) return;
  const moved = _curveRound(ed, g.t(x), g.v(y));
  pts[ed.drag] = moved;
  _curveWrite(ed, pts);
  ed.drag = _curvePoints(ed).findIndex(p => p[0] === moved[0] && p[1] === moved[1]);
}

function _curveDraw(ed) {
  const ctx = ed.cvs.getContext("2d");
  const pts = _curvePoints(ed), g = _curveGeom(ed, pts);
  ctx.fillStyle = "#0d0d0d"; ctx.fillRect(0, 0, g.W, g.H);

  // The waveform of that stretch of the timeline, if known
  const wf = state.waveform || [];
  if (_curveCtx.t0 != null && wf.length && state.duration > 0) {
    ctx.strokeStyle = "rgba(74,158,255,0.25)"; ctx.lineWidth = 1; ctx.beginPath();
    const mid = g.H / 2;
    for (let px = 0; px < g.W; px += 2) {
      const t = _curveCtx.t0 + (px / g.W) * g.span;
      const i = Math.floor((t / state.duration) * wf.length);
      if (i < 0 || i >= wf.length) continue;
      ctx.moveTo(px, mid - wf[i] * mid); ctx.lineTo(px, mid + wf[i] * mid);
    }
    ctx.stroke();
  }

  // Range labels and a time grid every second (or every 10 s on long spans)
  ctx.font = "9px Courier New"; ctx.fillStyle = "#555";
  const fmt = v => Math.abs(v) >= 100 ? Math.round(v) : +(+v).toPrecision(3);
  ctx.fillText(fmt(g.r.hi) + (g.r.log ? " (log)" : ""), 2, 10);
  ctx.fillText(fmt(g.r.lo), 2, g.H - 3);
  const tick = g.span > 30 ? 10 : 1;
  ctx.strokeStyle = "#1c1c1c";
  for (let t = tick; t < g.span; t += tick) {
    ctx.beginPath(); ctx.moveTo(g.x(t), 0); ctx.lineTo(g.x(t), g.H); ctx.stroke();
  }
  ctx.fillText(g.span.toFixed(g.span < 10 ? 1 : 0) + "s", g.W - 30, g.H - 3);

  // The curve: held before the first and after the last point
  ctx.strokeStyle = "#a88cff"; ctx.lineWidth = 2; ctx.beginPath();
  ctx.moveTo(0, g.y(pts[0][1]));
  pts.forEach(p => ctx.lineTo(g.x(p[0]), g.y(p[1])));
  ctx.lineTo(g.W, g.y(pts[pts.length - 1][1]));
  ctx.stroke();
  pts.forEach(p => {
    ctx.fillStyle = "#c9b6ff"; ctx.beginPath(); ctx.arc(g.x(p[0]), g.y(p[1]), 4, 0, Math.PI * 2); ctx.fill();
  });
}
