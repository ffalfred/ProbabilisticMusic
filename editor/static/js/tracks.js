// ─── Track lanes ──────────────────────────────────────────────────────────────
function drawMiniWaveform(cvs, peaks, automation, trackFrom, trackTo) {
  if (cvs.offsetWidth > 0) cvs.width = cvs.offsetWidth;
  const ctx = cvs.getContext("2d");
  const W = cvs.width, H = cvs.height, mid = H / 2;
  ctx.clearRect(0, 0, W, H);
  if (!peaks || !peaks.length) return;

  // Waveform
  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 1;
  ctx.beginPath();
  peaks.forEach((v, i) => {
    const x = i / peaks.length * W;
    ctx.moveTo(x, mid - v * mid);
    ctx.lineTo(x, mid + v * mid);
  });
  ctx.stroke();

  // Automation envelope overlay
  if (automation && automation.length) {
    const tFrom = trackFrom || 0;
    const tTo   = trackTo   || state.duration || 1;
    const dur   = tTo - tFrom;
    ctx.strokeStyle = 'rgba(255,180,80,0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < automation.length; i++) {
      const pt = automation[i];
      const x  = ((pt.t - tFrom) / dur) * W;
      const y  = mid - (pt.db / 40) * mid;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.fillStyle = '#ffb450';
    for (const pt of automation) {
      const x = ((pt.t - tFrom) / dur) * W;
      const y = mid - (pt.db / 40) * mid;
      ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Playback cursor
  if (state.duration > 0) {
    const cx = (state.currentTime / state.duration) * W;
    ctx.strokeStyle = "rgba(255,50,50,0.85)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}

let tracksOpen = true;
const _autoLaneOpen = {};

function _toggleAutoLane(i) {
  _autoLaneOpen[i] = !_autoLaneOpen[i];
  renderTracksPanel();
}

function _autoLaneClear(i) {
  state.tracks[i].automation = [];
  renderTracksPanel();
}

function toggleTracksPanel() {
  tracksOpen = !tracksOpen;
  document.getElementById("tracks-panel").style.display = tracksOpen ? "" : "none";
  document.getElementById("tracks-chevron").textContent = tracksOpen ? "\u25bc" : "\u25b6";
}

function renderTracksPanel() {
  const panel = document.getElementById("tracks-panel");
  if (!panel) return;
  const wrap = document.getElementById("tracks-wrap");
  if (wrap) wrap.style.display = "";
  document.getElementById("tracks-title").textContent = `Tracks (${state.tracks.length})`;

  const totalDur = state.duration || 1;

  let html = state.tracks.map((tk, i) => {
    const fxLabel = (tk.fx && tk.fx.length) ? tk.fx.map(f => (f.type||'').replace(/^morpho_/,'')).join('+') : '';
    const autoCount = (tk.automation || []).length;
    const autoColor = autoCount ? '#ffb450' : '#888';
    const autoOpen  = !!_autoLaneOpen[i];
    const autoChev  = autoOpen ? '▼' : '▶';
    const removeBtn = i > 0
      ? `<button onclick="_removeTrack(${i})" style="font-size:10px;padding:0 3px;color:#a66;border:1px solid #533;background:none;cursor:pointer;border-radius:2px;" title="Remove track">&times;</button>`
      : '';

    // Position offset for stems with from/to
    const tFrom = tk.from || 0;
    const tTo   = tk.to   || totalDur;
    const leftPct  = (tFrom / totalDur * 100).toFixed(2);
    const widthPct = ((tTo - tFrom) / totalDur * 100).toFixed(2);

    return `
    <div style="margin-bottom:2px;background:#161616;border-radius:3px;overflow:hidden;">
      <!-- Controls row -->
      <div style="display:flex;align-items:center;gap:5px;padding:2px 4px;">
        <span style="width:80px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;" title="${tk.name}">${i}: ${tk.name}</span>
        <input type="checkbox" ${tk.muted ? "" : "checked"} title="mute/unmute"
               onchange="state.tracks[${i}].muted=!this.checked; syncSourcePlayback(); renderTracksPanel();">
        <label style="font-size:10px;color:#666;">dB</label>
        <input type="number" value="${tk.gain_db}" step="1" style="width:44px;font-size:11px;background:#111;color:#ccc;border:1px solid #333;padding:1px 3px;"
               onchange="state.tracks[${i}].gain_db=parseFloat(this.value)||0;">
        <button onclick="openTrackFxPopup(${i})" style="font-size:10px;padding:1px 5px;background:#222;color:${fxLabel ? '#4a9eff' : '#888'};border:1px solid #444;border-radius:2px;cursor:pointer;" title="Track FX">${fxLabel ? 'FX:'+fxLabel : 'FX'}</button>
        <button onclick="_toggleAutoLane(${i})" style="font-size:10px;padding:1px 5px;background:#222;color:${autoColor};border:1px solid #444;border-radius:2px;cursor:pointer;" title="Volume automation">${autoChev} Auto${autoCount ? ':'+autoCount : ''}</button>
        ${removeBtn}
      </div>
      <!-- Waveform strip — always visible, positioned to align with main waveform -->
      <div style="display:flex;height:20px;background:#111;">
        <div style="flex:none;width:${leftPct}%;"></div>
        <canvas data-tidx="${i}" data-wpct="${widthPct}" height="20"
                style="flex:none;width:${widthPct}%;height:20px;background:#0d0d0d;"></canvas>
      </div>
      <!-- Automation lane — expanded, positioned to align -->
      ${autoOpen ? `
      <div style="display:flex;height:100px;background:#0a0a0a;border-top:1px solid #222;">
        <div style="flex:none;width:${leftPct}%;"></div>
        <canvas data-auto-tidx="${i}" data-wpct="${widthPct}" height="100"
                style="flex:none;width:${widthPct}%;height:100px;background:#0d0d0d;cursor:crosshair;"></canvas>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:1px 4px;">
        <span style="font-size:9px;color:#555;">click: add · drag: move · right-click: delete</span>
        <button onclick="_autoLaneClear(${i})" style="font-size:9px;color:#a66;padding:1px 4px;background:none;border:1px solid #533;border-radius:2px;cursor:pointer;">clear</button>
      </div>
      ` : ''}
    </div>`;
  }).join('');

  html += `<div style="margin-top:4px;display:flex;gap:6px;">
    <button onclick="_addUserTrack()" style="font-size:10px;padding:3px 8px;background:#1a1a1a;color:#7ab;border:1px solid #333;border-radius:2px;cursor:pointer;">+ Track</button>
  </div>`;

  panel.innerHTML = html;

  // Compute canvas pixel widths from panel width × percentage (no offsetWidth needed)
  const panelW = panel.offsetWidth || panel.parentElement?.offsetWidth || 600;

  // Mini waveforms — draw immediately, no RAF needed
  panel.querySelectorAll("canvas[data-tidx]").forEach(c => {
    const pct = parseFloat(c.dataset.wpct) || 100;
    c.width = Math.round(panelW * pct / 100);
    const idx = parseInt(c.dataset.tidx);
    const tk  = state.tracks[idx];
    drawMiniWaveform(c, tk.waveform, tk.automation, tk.from, tk.to);
  });

  // Automation lane canvases
  panel.querySelectorAll("canvas[data-auto-tidx]").forEach(cvs => {
    const pct = parseFloat(cvs.dataset.wpct) || 100;
    cvs.width = Math.round(panelW * pct / 100);
    const idx = parseInt(cvs.dataset.autoTidx);
    _autoEditorRedraw(cvs, idx);

    cvs.addEventListener('mousedown', (e) => {
      if (e.button === 2) {
        e.preventDefault();
        _autoEditorDelete(cvs, e, idx);
        return;
      }
      const pt = _autoEditorHitTest(cvs, e, idx);
      if (pt >= 0) {
        _autoEditorDrag = pt;
        _autoEditorTrack = idx;
      } else {
        _autoEditorAdd(cvs, e, idx);
      }
    });
    cvs.addEventListener('mousemove', (e) => {
      if (_autoEditorDrag < 0 || _autoEditorTrack !== idx) return;
      _autoEditorMove(cvs, e, idx, _autoEditorDrag);
    });
    cvs.addEventListener('mouseup', () => { _autoEditorDrag = -1; });
    cvs.addEventListener('mouseleave', () => { _autoEditorDrag = -1; });
    cvs.addEventListener('contextmenu', (e) => e.preventDefault());
  });
}

// ─── Add user track ──────────────────────────────────────────────────────────
async function _addUserTrack() {
  if (typeof openFileBrowser === 'function') {
    openFileBrowser(async (path) => { await _loadAndAddTrack(path); },
                    ['.wav', '.mp3', '.flac', '.ogg', '.mp4']);
  } else {
    const path = prompt('Audio file path:');
    if (path) await _loadAndAddTrack(path.trim());
  }
}

async function _loadAndAddTrack(path) {
  if (!path) return;
  try {
    const res = await fetch('/load', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (data.error) { alert('Failed to load track: ' + data.error); return; }
    const name = path.split('/').pop().replace(/\.[^.]+$/, '') || 'track';
    state.tracks.push({
      name, path,
      gain_db: 0, muted: false,
      from: 0, to: data.duration || state.duration || 0,
      waveform: data.waveform || [],
      fx: [], automation: [],
    });
    if (typeof _waCache !== 'undefined') delete _waCache[path];
    renderTracksPanel();
  } catch (e) {
    alert('Failed to load track: ' + e);
  }
}

// ─── Remove track ────────────────────────────────────────────────────────────
function _removeTrack(i) {
  if (i <= 0) return;
  state.tracks.splice(i, 1);
  renderTracksPanel();
  if (typeof syncSourcePlayback === 'function') syncSourcePlayback();
}

// ─── Inline automation lane editor ───────────────────────────────────────────
let _autoEditorTrack = -1;
let _autoEditorDrag  = -1;

function _autoEditorCoords(cvs, e, trackIdx) {
  const tk = state.tracks[trackIdx];
  const rect = cvs.getBoundingClientRect();
  const scaleX = cvs.width / rect.width;
  const scaleY = cvs.height / rect.height;
  const x = (e.clientX - rect.left) * scaleX;
  const y = (e.clientY - rect.top) * scaleY;
  const tFrom = tk.from || 0;
  const tTo   = tk.to || state.duration || 1;
  const t  = tFrom + (x / cvs.width) * (tTo - tFrom);
  const db = (1 - y / cvs.height) * 46 - 40;
  return { t: Math.max(tFrom, Math.min(tTo, t)), db: Math.max(-40, Math.min(6, Math.round(db))) };
}

function _autoEditorHitTest(cvs, e, trackIdx) {
  const tk = state.tracks[trackIdx];
  const auto = tk.automation || [];
  if (!auto.length) return -1;
  const { t, db } = _autoEditorCoords(cvs, e, trackIdx);
  const tFrom = tk.from || 0;
  const tTo   = tk.to || state.duration || 1;
  const dur = tTo - tFrom;
  for (let i = 0; i < auto.length; i++) {
    const dx = Math.abs(auto[i].t - t) / dur * cvs.width;
    const dy = Math.abs(auto[i].db - db) / 46 * cvs.height;
    if (dx < 8 && dy < 8) return i;
  }
  return -1;
}

function _autoEditorAdd(cvs, e, trackIdx) {
  const tk = state.tracks[trackIdx];
  const { t, db } = _autoEditorCoords(cvs, e, trackIdx);
  if (!tk.automation) tk.automation = [];
  tk.automation.push({ t, db });
  tk.automation.sort((a, b) => a.t - b.t);
  _autoEditorRedraw(cvs, trackIdx);
}

function _autoEditorMove(cvs, e, trackIdx, ptIdx) {
  const tk = state.tracks[trackIdx];
  const pt = (tk.automation || [])[ptIdx];
  if (!pt) return;
  const { t, db } = _autoEditorCoords(cvs, e, trackIdx);
  pt.t  = t;
  pt.db = db;
  tk.automation.sort((a, b) => a.t - b.t);
  _autoEditorRedraw(cvs, trackIdx);
}

function _autoEditorDelete(cvs, e, trackIdx) {
  const pt = _autoEditorHitTest(cvs, e, trackIdx);
  if (pt < 0) return;
  state.tracks[trackIdx].automation.splice(pt, 1);
  _autoEditorRedraw(cvs, trackIdx);
}

function _autoEditorRedraw(cvs, trackIdx) {
  const tk  = state.tracks[trackIdx];
  const ctx = cvs.getContext('2d');
  const W = cvs.width, H = cvs.height;
  if (W <= 0 || H <= 0) return;
  const tFrom = tk.from || 0;
  const tTo   = tk.to || state.duration || 1;
  const dur   = tTo - tFrom;
  const auto  = tk.automation || [];

  ctx.fillStyle = '#0d0d0d';
  ctx.fillRect(0, 0, W, H);

  // Waveform (larger, visible)
  const peaks = tk.waveform;
  if (peaks && peaks.length) {
    const mid = H / 2;
    ctx.strokeStyle = 'rgba(74,158,255,0.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    peaks.forEach((v, i) => {
      const x = (i / peaks.length) * W;
      ctx.moveTo(x, mid - v * mid);
      ctx.lineTo(x, mid + v * mid);
    });
    ctx.stroke();
  }

  // dB gridlines
  ctx.strokeStyle = '#1a1a1a';
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 4]);
  ctx.font = '9px Courier New';
  ctx.fillStyle = '#333';
  for (const db of [-40, -30, -20, -10, 0, 6]) {
    const y = H * (1 - (db + 40) / 46);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.fillText(`${db}`, 2, y - 2);
  }
  ctx.setLineDash([]);

  // 0 dB reference line
  ctx.strokeStyle = 'rgba(100,200,100,0.25)';
  ctx.lineWidth = 1;
  const zeroY = H * (1 - 40 / 46);
  ctx.beginPath(); ctx.moveTo(0, zeroY); ctx.lineTo(W, zeroY); ctx.stroke();

  // Automation envelope
  if (auto.length) {
    ctx.strokeStyle = 'rgba(255,180,80,0.8)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < auto.length; i++) {
      const x = ((auto[i].t - tFrom) / dur) * W;
      const y = H * (1 - (auto[i].db + 40) / 46);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.fillStyle = '#ffb450';
    for (let i = 0; i < auto.length; i++) {
      const x = ((auto[i].t - tFrom) / dur) * W;
      const y = H * (1 - (auto[i].db + 40) / 46);
      ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#000';
      ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#ffb450';
    }
  }

  // Playback cursor
  if (state.duration > 0) {
    const ct = state.currentTime;
    if (ct >= tFrom && ct <= tTo) {
      const cx = ((ct - tFrom) / dur) * W;
      ctx.strokeStyle = 'rgba(255,50,50,0.7)';
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
    }
  }

  // Update mini waveform too
  const miniCvs = document.querySelector(`canvas[data-tidx="${trackIdx}"]`);
  if (miniCvs) drawMiniWaveform(miniCvs, tk.waveform, auto, tk.from, tk.to);
}

// ─── Track FX popup ──────────────────────────────────────────────────────────
async function openTrackFxPopup(i) {
  const tk = state.tracks[i];
  if (!tk) return;
  const html = `<div style="margin-bottom:4px;"><label style="font-size:10px;color:#666;">FX chain for "${tk.name}":</label>
      <div id="p-fx-chain"></div>
      <div style="display:flex;gap:4px;margin-top:4px;">
        <button type="button" onclick="_addFxToChain('classic')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>
        <button type="button" onclick="_addFxToChain('morpho')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>
      </div></div>
      ${tk.fx && tk.fx.length ? `<button type="button" onclick="_initFxChain([])" style="font-size:10px;padding:2px 6px;color:#f66;">Clear all FX</button>` : ''}`;
  const res = await showPopup(`FX — ${tk.name}`, html, () => _initFxChain(tk.fx || []));
  if (!res) return;
  state.tracks[i].fx = collectFxChain();
  renderTracksPanel();
}
