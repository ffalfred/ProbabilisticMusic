// ─── Concerto score lanes: dynamics + tempo ──────────────────────────────────
// Visual layer for sources without a performance trace (the Composer), drawn
// from the score itself. Work in progress — a first, plain rendering.
// Depends on: state.js (state). Time axis is SCORE time over [0, state.duration].
// Reveal follows _concertoMaxT (concerto.js) like the trace panels do.

// Same levels and rules as src/envelope.py (DYNAMIC_LEVELS, build_dynamics_envelope)
const _LANE_DYN_LEVELS = { ppp: 0.05, pp: 0.10, p: 0.20, mp: 0.45, mf: 0.65, f: 0.85, ff: 1.00, fff: 1.20 };
const _LANE_DYN_MAX = 1.2;

function _laneMark(d) { return d.mark || d.marking || ''; }

function _laneIsCresc(m)   { m = m.toLowerCase().replace(/\.$/, ''); return m === 'crescendo' || m === 'cresc' || m === 'cr'; }
function _laneIsDecresc(m) { m = m.toLowerCase().replace(/\.$/, ''); return ['decrescendo', 'decresc', 'diminuendo', 'dim', 'decr'].includes(m); }

// Loudness level (linear, as the renderer applies it) at n points over [0, dur].
function _laneDynamicsCurve(dynamics, dur, n) {
  const env = new Float32Array(n).fill(1);
  const active = (dynamics || []).filter(d => !d.muted);
  if (!active.length || dur <= 0) return env;
  const idx = t => Math.round(t / dur * (n - 1));
  const points = active.filter(d => d.t != null && _LANE_DYN_LEVELS[_laneMark(d)] != null)
                       .map(d => [d.t, _LANE_DYN_LEVELS[_laneMark(d)]])
                       .sort((a, b) => a[0] - b[0]);
  const events = points.map(([t, lv]) => ({ i: idx(t), kind: 'set', level: lv }));
  for (const d of active) {
    if (d.from == null || d.to == null || d.to <= d.from) continue;
    const m = _laneMark(d);
    if (!_laneIsCresc(m) && !_laneIsDecresc(m)) continue;
    const next = points.find(([t]) => t >= d.to);
    events.push({ i: idx(d.from), kind: 'ramp', to: idx(d.to), target: next ? next[1] : null,
                  up: _laneIsCresc(m) });
  }
  events.sort((a, b) => a.i - b.i);

  let level = points.length ? points[0][1] : 0.65;
  let cursor = 0;
  for (const ev of events) {
    const i = Math.max(0, Math.min(n, ev.i));
    for (let k = cursor; k < i; k++) env[k] = level;
    if (ev.kind === 'set') {
      level = ev.level; cursor = i;
    } else {
      const end = Math.min(n, ev.to);
      const target = ev.target != null ? ev.target
                   : ev.up ? Math.min(level * 2.5, 1.2) : Math.max(level * 0.4, 0.05);
      for (let k = i; k < end; k++) env[k] = level + (target - level) * (k - i) / Math.max(1, end - i);
      level = target; cursor = Math.max(cursor, end);
    }
  }
  for (let k = cursor; k < n; k++) env[k] = level;
  return env;
}

// Same resolution as src/mixer.py _resolve_tempo_factor: ranges → midpoint.
function _laneTempoFactor(f) {
  if (Array.isArray(f) && f.length === 2) f = (f[0] + f[1]) / 2;
  else if (f && typeof f === 'object') f = f.mean ?? f.default ?? 1;
  return Math.max(parseFloat(f) || 1, 0.01);
}

// Playback rate at n points over [0, dur] — product of overlapping tempo
// ranges ('ramp': 1 → factor, 'step': constant) and phrase tempo factors,
// as in src/mixer.py _stretch_mix_by_tempo.
function _laneTempoCurve(tempo, phrases, dur, n) {
  const rate = new Float32Array(n).fill(1);
  if (dur <= 0) return rate;
  const ranges = (tempo || []).filter(r => !r.muted && r.to > r.from)
    .map(r => ({ from: r.from, to: r.to, f: _laneTempoFactor(r.factor), ramp: (r.shape || 'ramp') === 'ramp' }))
    .concat((phrases || []).filter(p => !p.muted && Math.abs((p.tempo_factor ?? 1) - 1) > 1e-4)
      .map(p => ({ from: p.from, to: p.to, f: _laneTempoFactor(p.tempo_factor), ramp: false })));
  for (let k = 0; k < n; k++) {
    const s = k / (n - 1) * dur;
    for (const r of ranges) {
      if (s < r.from || s >= r.to) continue;
      rate[k] *= r.ramp ? 1 + (s - r.from) / (r.to - r.from) * (r.f - 1) : r.f;
    }
  }
  return rate;
}

// Draw a curve: the whole piece dim, the part already played bright.
function _laneStroke(ctx, x0, w, ys, revealN, dim, bright) {
  const n = ys.length;
  const path = (from, to) => {
    ctx.beginPath();
    for (let k = from; k < to; k++) {
      const x = x0 + k / (n - 1) * w;
      if (k === from) ctx.moveTo(x, ys[k]); else ctx.lineTo(x, ys[k]);
    }
    ctx.stroke();
  };
  ctx.lineWidth = Math.max(1, w / 1200);
  ctx.strokeStyle = dim;    path(0, n);
  if (revealN > 1) { ctx.lineWidth *= 2; ctx.strokeStyle = bright; path(0, Math.min(n, revealN)); }
}

function _laneFrame(ctx, x, y, w, h, title) {
  ctx.fillStyle = '#0a0a0a';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = '#555';
  ctx.font = `${Math.max(9, Math.round(h * 0.07))}px Courier New`;
  ctx.textBaseline = 'top';
  ctx.fillText(title, x + 6, y + 4);
}

function _laneCursor(ctx, x, y, w, h, dur) {
  const t = state.currentTime;
  if (!(dur > 0) || t < 0 || t > dur) return;
  const cx = x + t / dur * w;
  ctx.strokeStyle = 'rgba(220,220,220,0.6)';
  ctx.lineWidth = Math.max(1, w / 1600);
  ctx.beginPath(); ctx.moveTo(cx, y); ctx.lineTo(cx, y + h); ctx.stroke();
}

function _laneRevealN(n, dur) {
  const maxT = (typeof _concertoMaxT !== 'undefined') ? _concertoMaxT : Infinity;
  if (maxT === Infinity) return n;
  if (maxT < 0 || !(dur > 0)) return 0;
  return Math.ceil(Math.min(1, maxT / dur) * (n - 1)) + 1;
}

function drawDynamicsLane(ctx, x, y, w, h) {
  const dur = state.duration || 0;
  const n = Math.max(2, Math.min(4000, Math.round(w)));
  _laneFrame(ctx, x, y, w, h, 'dynamics');
  if (!(dur > 0)) return;
  const env = _laneDynamicsCurve(state.dynamics, dur, n);
  const pad = h * 0.18;
  const ys = Array.from(env, v => y + h - pad * 0.5 - (v / _LANE_DYN_MAX) * (h - pad * 1.5));
  _laneStroke(ctx, x, w, ys, _laneRevealN(n, dur), '#2a2a2a', '#d0d0d0');

  // Marking labels (ff, p, cresc…) at their positions
  ctx.fillStyle = '#777';
  ctx.font = `italic ${Math.max(9, Math.round(h * 0.09))}px Georgia, serif`;
  ctx.textBaseline = 'bottom';
  for (const d of (state.dynamics || []).filter(d => !d.muted)) {
    const t = d.t != null ? d.t : d.from;
    if (t == null) continue;
    const label = d.t != null ? _laneMark(d) : (_laneIsCresc(_laneMark(d)) ? 'cresc.' : 'dim.');
    ctx.fillText(label, x + t / dur * w + 3, y + h - 2);
  }
  _laneCursor(ctx, x, y, w, h, dur);
}

function drawTempoLane(ctx, x, y, w, h) {
  const dur = state.duration || 0;
  const n = Math.max(2, Math.min(4000, Math.round(w)));
  _laneFrame(ctx, x, y, w, h, 'tempo');
  if (!(dur > 0)) return;
  const rate = _laneTempoCurve(state.tempo, state.phrases, dur, n);
  // log2 scale around the unchanged tempo: ×2 / ×0.5 at the top / bottom edge
  const mid = y + h / 2, span = h * 0.38;
  ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x, mid); ctx.lineTo(x + w, mid); ctx.stroke();
  const ys = Array.from(rate, r => mid - Math.max(-1, Math.min(1, Math.log2(r))) * span);
  _laneStroke(ctx, x, w, ys, _laneRevealN(n, dur), '#2a2a2a', '#d0d0d0');

  ctx.fillStyle = '#777';
  ctx.font = `${Math.max(9, Math.round(h * 0.08))}px Courier New`;
  ctx.textBaseline = 'bottom';
  for (const r of (state.tempo || []).filter(r => !r.muted && r.to > r.from)) {
    const f = _laneTempoFactor(r.factor);
    ctx.fillText((f > 1 ? 'accel. ' : 'rit. ') + '×' + f.toFixed(2), x + r.from / dur * w + 3, y + h - 2);
  }
  _laneCursor(ctx, x, y, w, h, dur);
}

// Both lanes stacked in one rectangle.
function drawScoreLanes(ctx, x, y, w, h) {
  const gap = Math.max(2, Math.round(h * 0.03));
  const hDyn = Math.round((h - gap) * 0.6);
  drawDynamicsLane(ctx, x, y, w, hDyn);
  drawTempoLane(ctx, x, y + hDyn + gap, w, h - hDyn - gap);
}
