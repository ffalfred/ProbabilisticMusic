// ─── Track lanes ──────────────────────────────────────────────────────────────
function drawMiniWaveform(cvs, peaks) {
  if (cvs.offsetWidth > 0) cvs.width = cvs.offsetWidth;
  const ctx = cvs.getContext("2d");
  const W = cvs.width, H = cvs.height, mid = H / 2;
  ctx.clearRect(0, 0, W, H);
  if (!peaks || !peaks.length) return;
  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 1;
  ctx.beginPath();
  peaks.forEach((v, i) => {
    const x = i / peaks.length * W;
    ctx.moveTo(x, mid - v * mid);
    ctx.lineTo(x, mid + v * mid);
  });
  ctx.stroke();
  if (state.duration > 0) {
    const cx = (state.currentTime / state.duration) * W;
    ctx.strokeStyle = "rgba(255,50,50,0.85)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}

let tracksOpen = true;

function toggleTracksPanel() {
  tracksOpen = !tracksOpen;
  document.getElementById("tracks-panel").style.display = tracksOpen ? "" : "none";
  document.getElementById("tracks-chevron").textContent = tracksOpen ? "\u25bc" : "\u25b6";
}

function renderTracksPanel() {
  const panel = document.getElementById("tracks-panel");
  if (!panel) return;
  const wrap = document.getElementById("tracks-wrap");
  if (state.tracks.length <= 1) { panel.innerHTML = ""; if (wrap) wrap.style.display = "none"; return; }
  if (wrap) wrap.style.display = "";
  document.getElementById("tracks-title").textContent = `Tracks (${state.tracks.length})`;
  panel.innerHTML = state.tracks.map((tk, i) => {
    const fxLabel = (tk.fx && tk.fx.length) ? tk.fx.map(f => (f.type||'').replace(/^morpho_/,'')).join('+') : '';
    return `
    <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px;padding:2px 4px;background:#161616;border-radius:3px;">
      <span style="width:90px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;" title="${tk.name}">${i}: ${tk.name}</span>
      <input type="checkbox" ${tk.muted ? "" : "checked"} title="mute/unmute"
             onchange="state.tracks[${i}].muted=!this.checked; syncSourcePlayback(); renderTracksPanel();">
      <label style="font-size:10px;color:#666;">dB</label>
      <input type="number" value="${tk.gain_db}" step="1" style="width:44px;font-size:11px;background:#111;color:#ccc;border:1px solid #333;padding:1px 3px;"
             onchange="state.tracks[${i}].gain_db=parseFloat(this.value)||0;">
      <button onclick="openTrackFxPopup(${i})" style="font-size:10px;padding:1px 5px;background:#222;color:${fxLabel ? '#4a9eff' : '#888'};border:1px solid #444;border-radius:2px;cursor:pointer;" title="Track FX">${fxLabel ? 'FX:'+fxLabel : 'FX'}</button>
      <canvas data-tidx="${i}" width="300" height="26" style="flex:1;background:#1a1a1a;"></canvas>
    </div>`;
  }).join('');
  panel.querySelectorAll("canvas[data-tidx]").forEach(c => {
    const idx = parseInt(c.dataset.tidx);
    drawMiniWaveform(c, state.tracks[idx].waveform);
  });
}

async function openTrackFxPopup(i) {
  const tk = state.tracks[i];
  if (!tk) return;
  const html = `<div style="margin-bottom:4px;"><label style="font-size:10px;color:#666;">FX chain for stem "${tk.name}":</label>
      <div id="p-fx-chain"></div>
      <div style="display:flex;gap:4px;margin-top:4px;">
        <button type="button" onclick="_addFxToChain('classic')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>
        <button type="button" onclick="_addFxToChain('morpho')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>
      </div></div>
      ${tk.fx && tk.fx.length ? `<button type="button" onclick="_initFxChain([])" style="font-size:10px;padding:2px 6px;color:#f66;">Clear all FX</button>` : ''}`;
  const res = await showPopup(`FX — ${tk.name}`, html, () => _initFxChain(tk.fx || []));
  if (!res) return;
  const fx = collectFxChain();
  state.tracks[i].fx = fx;
  renderTracksPanel();
}
