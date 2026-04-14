// ─── Track lanes — persistent canvases, no full rebuild ──────────────────────

function drawMiniWaveform(cvs, peaks, automation, trackFrom, trackTo) {
  var ctx = cvs.getContext("2d");
  var W = cvs.width, H = cvs.height, mid = H / 2;
  ctx.clearRect(0, 0, W, H);
  if (!peaks || !peaks.length) return;

  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (var i = 0; i < peaks.length; i++) {
    var x = i / peaks.length * W;
    ctx.moveTo(x, mid - peaks[i] * mid);
    ctx.lineTo(x, mid + peaks[i] * mid);
  }
  ctx.stroke();

  if (automation && automation.length) {
    var tFrom = trackFrom || 0;
    var tTo   = trackTo || state.duration || 1;
    var dur   = tTo - tFrom;
    ctx.strokeStyle = "rgba(255,180,80,0.7)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i < automation.length; i++) {
      var ax = ((automation[i].t - tFrom) / dur) * W;
      var ay = mid - (automation[i].db / 40) * mid;
      if (i === 0) ctx.moveTo(ax, ay); else ctx.lineTo(ax, ay);
    }
    ctx.stroke();
    ctx.fillStyle = "#ffb450";
    for (var j = 0; j < automation.length; j++) {
      var px = ((automation[j].t - tFrom) / dur) * W;
      var py = mid - (automation[j].db / 40) * mid;
      ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI * 2); ctx.fill();
    }
  }

  if (state.duration > 0) {
    var cx = (state.currentTime / state.duration) * W;
    ctx.strokeStyle = "rgba(255,50,50,0.85)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}

// ─── State ───────────────────────────────────────────────────────────────────
var tracksOpen = true;
var _autoLaneOpen = {};
var _autoEditorTrack = -1;
var _autoEditorDrag  = -1;
var _stemsCollapsed = false;
var _userTracksCollapsed = false;
var _trackTool = {};  // { trackIndex: 'auto' | 'fxr' } — active tool per track
var _fxrDragStart = -1;  // FXr mode: drag start time

// Track row DOM references — keyed by track index, persisted across updates
var _trackRows = [];  // [{row, waveCvs, autoCvs, autoWrap, autoCtrl, controls}]

function toggleTracksPanel() {
  tracksOpen = !tracksOpen;
  document.getElementById("tracks-panel").style.display = tracksOpen ? "" : "none";
  document.getElementById("tracks-chevron").textContent = tracksOpen ? "\u25bc" : "\u25b6";
}

// ─── Create a single track row (called once per track) ───────────────────────
function _createTrackRow(i) {
  var tk = state.tracks[i];
  var totalDur = state.duration || 1;
  var panel = document.getElementById("tracks-panel");
  var panelW = panel.offsetWidth || panel.parentElement?.offsetWidth
            || document.getElementById("left-col")?.offsetWidth || 800;

  var tFrom   = tk.from || 0;
  var tTo     = tk.to || totalDur;
  var leftPx  = Math.round(tFrom / totalDur * panelW);
  var widthPx = Math.max(10, Math.round((tTo - tFrom) / totalDur * panelW));

  var row = document.createElement("div");
  row.style.cssText = "margin-bottom:2px;background:#161616;border-radius:3px;overflow:hidden;";
  row.dataset.trackIdx = i;

  // Controls
  var ctrl = document.createElement("div");
  ctrl.style.cssText = "display:flex;align-items:center;gap:5px;padding:2px 4px;";
  row.appendChild(ctrl);

  // Waveform strip
  var waveWrap = document.createElement("div");
  waveWrap.style.cssText = "height:20px;background:#111;padding-left:" + leftPx + "px;";
  var waveCvs = document.createElement("canvas");
  waveCvs.width = widthPx;
  waveCvs.height = 20;
  waveCvs.dataset.tidx = i;
  waveCvs.style.cssText = "display:block;height:20px;background:#0d0d0d;";
  waveWrap.appendChild(waveCvs);
  row.appendChild(waveWrap);

  // Automation lane (created but hidden until expanded)
  var autoWrap = document.createElement("div");
  autoWrap.style.cssText = "height:100px;background:#0a0a0a;border-top:1px solid #222;padding-left:" + leftPx + "px;display:none;";
  var autoCvs = document.createElement("canvas");
  autoCvs.width = widthPx;
  autoCvs.height = 100;
  autoCvs.dataset.autoTidx = i;
  autoCvs.style.cssText = "display:block;height:100px;background:#0d0d0d;cursor:crosshair;";
  autoWrap.appendChild(autoCvs);
  row.appendChild(autoWrap);
  _wireAutoEvents(autoCvs, i);

  var autoCtrl = document.createElement("div");
  autoCtrl.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:1px 4px;display:none;";
  var hint = document.createElement("span");
  hint.style.cssText = "font-size:9px;color:#555;";
  hint.textContent = "click: add \u00B7 drag: move \u00B7 right-click: delete";
  autoCtrl.appendChild(hint);
  var clrBtn = document.createElement("button");
  clrBtn.style.cssText = "font-size:9px;color:#a66;padding:1px 4px;background:none;border:1px solid #533;border-radius:2px;cursor:pointer;";
  clrBtn.textContent = "clear";
  (function(idx) { clrBtn.addEventListener("click", function() {
    state.tracks[idx].automation = [];
    _updateTrackRow(idx);
  }); })(i);
  autoCtrl.appendChild(clrBtn);
  row.appendChild(autoCtrl);

  var entry = { row: row, ctrl: ctrl, waveCvs: waveCvs, autoCvs: autoCvs, autoWrap: autoWrap, autoCtrl: autoCtrl, widthPx: widthPx, leftPx: leftPx };
  return entry;
}

// ─── Update controls + labels for a track row (no DOM rebuild) ───────────────
function _updateTrackRow(i) {
  if (i >= _trackRows.length) return;
  var entry = _trackRows[i];
  var tk = state.tracks[i];
  if (!entry || !tk) return;

  var fxLabel = (tk.fx && tk.fx.length) ? tk.fx.map(function(f) { return (f.type || "").replace(/^morpho_/, ""); }).join("+") : "";
  var autoN   = (tk.automation || []).length;
  var autoCol = autoN ? "#ffb450" : "#888";
  var isOpen  = !!_autoLaneOpen[i];

  // Rebuild controls (small, no canvases — safe to use innerHTML-like approach)
  var ctrl = entry.ctrl;
  ctrl.textContent = "";

  var name = document.createElement("span");
  name.style.cssText = "width:80px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;";
  name.title = tk.name;
  name.textContent = i + ": " + tk.name;
  ctrl.appendChild(name);

  var mute = document.createElement("input");
  mute.type = "checkbox"; mute.checked = !tk.muted; mute.title = "mute/unmute";
  (function(idx) { mute.addEventListener("change", function() {
    state.tracks[idx].muted = !this.checked;
    if (typeof syncSourcePlayback === "function") syncSourcePlayback();
    _updateTrackRow(idx);
  }); })(i);
  ctrl.appendChild(mute);

  ctrl.appendChild(Object.assign(document.createElement("label"), { textContent: "dB", style: "font-size:10px;color:#666;" }));
  var dbIn = document.createElement("input");
  dbIn.type = "number"; dbIn.value = tk.gain_db; dbIn.step = "1";
  dbIn.style.cssText = "width:44px;font-size:11px;background:#111;color:#ccc;border:1px solid #333;padding:1px 3px;";
  (function(idx) { dbIn.addEventListener("change", function() { state.tracks[idx].gain_db = parseFloat(this.value) || 0; }); })(i);
  ctrl.appendChild(dbIn);

  var fxBtn = document.createElement("button");
  fxBtn.style.cssText = "font-size:10px;padding:1px 5px;background:#222;color:" + (fxLabel ? "#4a9eff" : "#888") + ";border:1px solid #444;border-radius:2px;cursor:pointer;";
  fxBtn.textContent = fxLabel ? "FX:" + fxLabel : "FX";
  fxBtn.title = "Track FX";
  (function(idx) { fxBtn.addEventListener("click", function() { openTrackFxPopup(idx); }); })(i);
  ctrl.appendChild(fxBtn);

  // Expand/collapse button (opens the larger waveform view)
  var expandBtn = document.createElement("button");
  expandBtn.style.cssText = "font-size:10px;padding:1px 5px;background:#222;color:#888;border:1px solid #444;border-radius:2px;cursor:pointer;";
  expandBtn.textContent = isOpen ? "\u25BC" : "\u25B6";
  expandBtn.title = isOpen ? "Collapse waveform" : "Expand waveform";
  (function(idx) { expandBtn.addEventListener("click", function() {
    _autoLaneOpen[idx] = !_autoLaneOpen[idx];
    if (!_autoLaneOpen[idx]) delete _trackTool[idx];
    _updateTrackRow(idx);
  }); })(i);
  ctrl.appendChild(expandBtn);

  // Tool buttons (only active when expanded)
  var activeTool = _trackTool[i] || '';
  if (isOpen) {
    var autoBtn = document.createElement("button");
    var autoActive = activeTool === 'auto';
    autoBtn.style.cssText = "font-size:10px;padding:1px 5px;background:" + (autoActive ? "#333" : "#222") + ";color:" + (autoActive ? "#ffb450" : autoCol) + ";border:1px solid " + (autoActive ? "#ffb450" : "#444") + ";border-radius:2px;cursor:pointer;";
    autoBtn.textContent = "Auto" + (autoN ? ":" + autoN : "");
    autoBtn.title = "Automation mode — click to add points, drag to move";
    (function(idx) { autoBtn.addEventListener("click", function() {
      _trackTool[idx] = _trackTool[idx] === 'auto' ? '' : 'auto';
      _updateTrackRow(idx);
    }); })(i);
    ctrl.appendChild(autoBtn);

    var fxrN = (tk.fx_regions || []).length;
    var fxrActive = activeTool === 'fxr';
    var fxrBtn = document.createElement("button");
    fxrBtn.style.cssText = "font-size:10px;padding:1px 5px;background:" + (fxrActive ? "#333" : "#222") + ";color:" + (fxrActive ? "#8844cc" : (fxrN ? "#8844cc" : "#888")) + ";border:1px solid " + (fxrActive ? "#8844cc" : "#444") + ";border-radius:2px;cursor:pointer;";
    fxrBtn.textContent = "FXr" + (fxrN ? ":" + fxrN : "");
    fxrBtn.title = "FX region mode — drag on waveform to select region, then add FX";
    (function(idx) { fxrBtn.addEventListener("click", function() {
      _trackTool[idx] = _trackTool[idx] === 'fxr' ? '' : 'fxr';
      _updateTrackRow(idx);
    }); })(i);
    ctrl.appendChild(fxrBtn);
  }

  if (i > 0) {
    var rm = document.createElement("button");
    rm.style.cssText = "font-size:10px;padding:0 3px;color:#a66;border:1px solid #533;background:none;cursor:pointer;border-radius:2px;";
    rm.textContent = "\u00D7"; rm.title = "Remove track";
    (function(idx) { rm.addEventListener("click", function() { _removeTrack(idx); }); })(i);
    ctrl.appendChild(rm);
  }

  // Toggle automation lane visibility (no destroy/recreate)
  entry.autoWrap.style.display = isOpen ? "" : "none";
  entry.autoCtrl.style.display = isOpen ? "flex" : "none";

  // Redraw canvases (they're the same elements, already composited — draws persist)
  drawMiniWaveform(entry.waveCvs, tk.waveform, tk.automation, tk.from, tk.to);
  if (isOpen) _autoEditorRedraw(entry.autoCvs, i);
}

// ─── Section header helper ───────────────────────────────────────────────────
function _sectionHeader(label, count, collapsed, toggleFn) {
  var hdr = document.createElement("div");
  hdr.style.cssText = "display:flex;align-items:center;gap:5px;padding:2px 6px;margin-top:4px;cursor:pointer;user-select:none;font-size:10px;color:#555;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #1a1a1a;";
  hdr.textContent = (collapsed ? "\u25B6" : "\u25BC") + " " + label + " (" + count + ")";
  hdr.addEventListener("click", toggleFn);
  return hdr;
}

// ─── Main render — diff-based, only creates/removes what changed ─────────────
function renderTracksPanel() {
  var panel = document.getElementById("tracks-panel");
  if (!panel) return;
  var wrap = document.getElementById("tracks-wrap");
  if (wrap) wrap.style.display = "";
  document.getElementById("tracks-title").textContent = "Tracks (" + state.tracks.length + ")";

  var nTracks = state.tracks.length;

  // Remove excess rows
  while (_trackRows.length > nTracks) {
    var removed = _trackRows.pop();
    if (removed.row.parentElement) removed.row.parentElement.removeChild(removed.row);
  }

  // Add missing rows
  while (_trackRows.length < nTracks) {
    var idx = _trackRows.length;
    var entry = _createTrackRow(idx);
    _trackRows.push(entry);
  }

  // Update all rows in place
  for (var i = 0; i < nTracks; i++) {
    _updateTrackRow(i);
  }

  // Rebuild the panel layout with section headers
  // Remove all children first (rows are detached but not destroyed)
  panel.textContent = "";

  // Base track (always visible, index 0)
  if (_trackRows.length > 0) {
    panel.appendChild(_trackRows[0].row);
  }

  // Stems section
  var stems = [];
  var userTracks = [];
  for (var i = 1; i < nTracks; i++) {
    var src = state.tracks[i].source;
    if (src === "stem") stems.push(i);
    else userTracks.push(i);
  }

  if (stems.length) {
    panel.appendChild(_sectionHeader("Stems", stems.length, _stemsCollapsed, function() {
      _stemsCollapsed = !_stemsCollapsed;
      renderTracksPanel();
    }));
    if (!_stemsCollapsed) {
      for (var j = 0; j < stems.length; j++) {
        panel.appendChild(_trackRows[stems[j]].row);
      }
    }
  }

  if (userTracks.length) {
    panel.appendChild(_sectionHeader("Tracks", userTracks.length, _userTracksCollapsed, function() {
      _userTracksCollapsed = !_userTracksCollapsed;
      renderTracksPanel();
    }));
    if (!_userTracksCollapsed) {
      for (var j = 0; j < userTracks.length; j++) {
        panel.appendChild(_trackRows[userTracks[j]].row);
      }
    }
  }

  // + Track button
  var addRow = document.createElement("div");
  addRow.style.cssText = "margin-top:4px;display:flex;gap:6px;";
  var addBtn = document.createElement("button");
  addBtn.style.cssText = "font-size:10px;padding:3px 8px;background:#1a1a1a;color:#7ab;border:1px solid #333;border-radius:2px;cursor:pointer;";
  addBtn.textContent = "+ Track";
  addBtn.addEventListener("click", _addUserTrack);
  addRow.appendChild(addBtn);
  panel.appendChild(addRow);
}

// ─── Waveform lane events — dispatch based on active tool ────────────────────
function _wireAutoEvents(cvs, idx) {
  cvs.addEventListener("mousedown", function(e) {
    var tool = _trackTool[idx] || '';
    if (e.button === 2) {
      e.preventDefault();
      if (tool === 'auto') { _autoEditorDelete(cvs, e, idx); return; }
      // Right-click: check if on an FX region → edit it
      var c = _autoEditorCoords(cvs, e, idx);
      var tk = state.tracks[idx];
      var regions = tk.fx_regions || [];
      for (var ri = 0; ri < regions.length; ri++) {
        if (c.t >= regions[ri].from && c.t <= regions[ri].to) {
          _editTrackFxRegion(idx, ri);
          return;
        }
      }
      return;
    }
    if (tool === 'auto') {
      var pt = _autoEditorHitTest(cvs, e, idx);
      if (pt >= 0) { _autoEditorDrag = pt; _autoEditorTrack = idx; }
      else { _autoEditorAdd(cvs, e, idx); }
    } else if (tool === 'fxr') {
      var c2 = _autoEditorCoords(cvs, e, idx);
      _fxrDragStart = c2.t;
    }
  });
  cvs.addEventListener("mousemove", function(e) {
    var tool = _trackTool[idx] || '';
    if (tool === 'auto') {
      if (_autoEditorDrag < 0 || _autoEditorTrack !== idx) return;
      _autoEditorMove(cvs, e, idx, _autoEditorDrag);
    }
  });
  cvs.addEventListener("mouseup", function(e) {
    var tool = _trackTool[idx] || '';
    if (tool === 'auto') {
      _autoEditorDrag = -1;
    } else if (tool === 'fxr' && _fxrDragStart >= 0) {
      var c = _autoEditorCoords(cvs, e, idx);
      var t1 = Math.min(_fxrDragStart, c.t);
      var t2 = Math.max(_fxrDragStart, c.t);
      _fxrDragStart = -1;
      if (t2 - t1 > 0.01) {
        _openTrackFxRegionAtRange(idx, t1, t2);
      }
    }
  });
  cvs.addEventListener("mouseleave", function() { _autoEditorDrag = -1; _fxrDragStart = -1; });
  cvs.addEventListener("contextmenu", function(e) { e.preventDefault(); });
}

// ─── Add / remove tracks ─────────────────────────────────────────────────────
async function _addUserTrack() {
  if (typeof openFileBrowser === "function") {
    openFileBrowser(async function(path) { await _loadAndAddTrack(path); },
                    [".wav", ".mp3", ".flac", ".ogg", ".mp4"]);
  } else {
    var path = prompt("Audio file path:");
    if (path) await _loadAndAddTrack(path.trim());
  }
}

async function _loadAndAddTrack(path) {
  if (!path) return;
  try {
    var res = await fetch("/load", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: path })
    });
    var data = await res.json();
    if (data.error) { alert("Failed to load track: " + data.error); return; }
    var name = path.split("/").pop().replace(/\.[^.]+$/, "") || "track";
    state.tracks.push({
      name: name, path: path, gain_db: 0, muted: false,
      from: 0, to: data.duration || state.duration || 0,
      waveform: data.waveform || [], fx: [], automation: [],
      source: 'user'
    });
    if (typeof _waCache !== "undefined") delete _waCache[path];
    renderTracksPanel();
  } catch (e) { alert("Failed to load track: " + e); }
}

function _removeTrack(i) {
  if (i <= 0) return;
  // Remove the DOM row
  if (_trackRows[i] && _trackRows[i].row.parentElement) {
    _trackRows[i].row.parentElement.removeChild(_trackRows[i].row);
  }
  _trackRows.splice(i, 1);
  state.tracks.splice(i, 1);
  // Re-index remaining rows
  for (var j = i; j < _trackRows.length; j++) {
    _trackRows[j].waveCvs.dataset.tidx = j;
    _trackRows[j].autoCvs.dataset.autoTidx = j;
    _trackRows[j].row.dataset.trackIdx = j;
  }
  // Update labels
  for (var j = 0; j < _trackRows.length; j++) _updateTrackRow(j);
  if (typeof syncSourcePlayback === "function") syncSourcePlayback();
}

// ─── Track FX regions — apply FX to time ranges within a track ───────────────

// Build the HTML for creating/editing an FX region
function _fxRegionPopupHTML(t1, t2, existing) {
  var fadeOn = existing ? !!existing.fade : false;
  var fiS = existing && existing.fade_in_s != null ? existing.fade_in_s : Math.max(0.01, Math.min(1.0, (t2 - t1) / 10));
  var foS = existing && existing.fade_out_s != null ? existing.fade_out_s : fiS;

  return '<div class="popup-row"><label>from (s)</label>'
    + '<input id="p-fxr-from" type="number" value="' + t1.toFixed(3) + '" step="0.001" min="0" style="flex:none;width:80px;"></div>'
    + '<div class="popup-row"><label>to (s)</label>'
    + '<input id="p-fxr-to" type="number" value="' + t2.toFixed(3) + '" step="0.001" min="0" style="flex:none;width:80px;"></div>'
    + '<div class="popup-row"><label>fade</label>'
    + '<input id="p-fxr-fade" type="checkbox" ' + (fadeOn ? 'checked' : '') + '>'
    + ' <span style="font-size:10px;color:#666;">in</span>'
    + ' <input id="p-fxr-fi" type="number" value="' + fiS.toFixed(3) + '" min="0" max="5" step="0.01" style="flex:none;width:56px;">'
    + ' <span style="font-size:10px;color:#666;">out</span>'
    + ' <input id="p-fxr-fo" type="number" value="' + foS.toFixed(3) + '" min="0" max="5" step="0.01" style="flex:none;width:56px;">'
    + ' <span style="font-size:10px;color:#666;">s</span></div>'
    + '<div><label style="font-size:10px;color:#666;">FX chain:</label>'
    + '<div id="p-fx-chain"></div>'
    + '<div style="display:flex;gap:4px;margin-top:4px;">'
    + '<button type="button" onclick="_addFxToChain(\'classic\')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>'
    + '<button type="button" onclick="_addFxToChain(\'morpho\')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>'
    + '</div></div>';
}

// Collect FX region fields from the popup
function _collectFxRegionFromPopup() {
  var from = parseFloat(document.getElementById("p-fxr-from").value);
  var to   = parseFloat(document.getElementById("p-fxr-to").value);
  var fx   = collectFxChain();
  if (isNaN(from) || isNaN(to) || !fx.length) return null;
  var entry = { from: from, to: to, fx: fx };
  if (document.getElementById("p-fxr-fade").checked) {
    entry.fade = true;
    entry.fade_in_s  = Math.max(0, parseFloat(document.getElementById("p-fxr-fi").value) || 0);
    entry.fade_out_s = Math.max(0, parseFloat(document.getElementById("p-fxr-fo").value) || 0);
  }
  return entry;
}

// Create new FX region (from drag on expanded waveform)
async function _openTrackFxRegionAtRange(trackIdx, t1, t2) {
  var tk = state.tracks[trackIdx];
  if (!tk) return;
  if (!tk.fx_regions) tk.fx_regions = [];

  var res = await showPopup("New FX Region \u2014 " + tk.name,
    _fxRegionPopupHTML(t1, t2, null),
    function() { _initFxChain([]); });
  if (!res) return;
  var entry = _collectFxRegionFromPopup();
  if (!entry) return;
  tk.fx_regions.push(entry);
  tk.fx_regions.sort(function(a, b) { return a.from - b.from; });
  _updateTrackRow(trackIdx);
}

// Edit existing FX region (from right-click on region overlay)
async function _editTrackFxRegion(trackIdx, regionIdx) {
  var tk = state.tracks[trackIdx];
  if (!tk || !tk.fx_regions || !tk.fx_regions[regionIdx]) return;
  var r = tk.fx_regions[regionIdx];

  var html = _fxRegionPopupHTML(r.from, r.to, r)
    + '<div style="margin-top:6px;"><button type="button" id="p-fxr-delete" style="font-size:10px;color:#f66;padding:2px 6px;">Delete this region</button></div>';

  var popupPromise = showPopup("Edit FX Region \u2014 " + tk.name, html,
    function() { _initFxChain(r.fx || []); });

  requestAnimationFrame(function() {
    var delBtn = document.getElementById("p-fxr-delete");
    if (delBtn) delBtn.addEventListener("click", function() {
      document.getElementById("p-fxr-from").value = "DELETE";
    });
  });

  var res = await popupPromise;
  if (!res) return;

  if (document.getElementById("p-fxr-from").value === "DELETE") {
    tk.fx_regions.splice(regionIdx, 1);
  } else {
    var entry = _collectFxRegionFromPopup();
    if (entry) {
      tk.fx_regions[regionIdx] = entry;
      tk.fx_regions.sort(function(a, b) { return a.from - b.from; });
    }
  }
  _updateTrackRow(trackIdx);
}

async function _openTrackFxRegionPopup(trackIdx) {
  var tk = state.tracks[trackIdx];
  if (!tk) return;
  if (!tk.fx_regions) tk.fx_regions = [];
  var tFrom = tk.from || 0;
  var tTo   = tk.to || state.duration || 1;

  // Build list of existing regions
  var listHtml = tk.fx_regions.map(function(r, j) {
    var fxStr = r.fx.map(function(f) { return f.type; }).join("+");
    return '<div style="display:flex;gap:4px;align-items:center;font-size:11px;margin:2px 0;">'
      + '<span style="color:#8844cc;">\u25A0</span>'
      + '<span style="color:#aaa;">' + r.from.toFixed(2) + 's \u2192 ' + r.to.toFixed(2) + 's</span>'
      + '<span style="color:#ccc;">' + fxStr + '</span>'
      + '<button onclick="document.getElementById(\'p-fxr-del\').value=\'' + j + '\'" style="font-size:9px;padding:0 3px;color:#a66;border:1px solid #533;background:none;cursor:pointer;">\u00D7</button>'
      + '</div>';
  }).join('') || '<div style="font-size:10px;color:#444;">No FX regions yet</div>';

  var html = '<div style="max-height:120px;overflow-y:auto;">' + listHtml + '</div>'
    + '<input type="hidden" id="p-fxr-del" value="-1">'
    + '<div style="margin-top:6px;border-top:1px solid #222;padding-top:6px;">'
    + '<div style="font-size:10px;color:#666;margin-bottom:4px;">Add new FX region:</div>'
    + '<div class="popup-row"><label>from (s)</label><input id="p-fxr-from" type="number" value="' + tFrom.toFixed(2) + '" step="0.01" min="0" style="flex:none;width:80px;"></div>'
    + '<div class="popup-row"><label>to (s)</label><input id="p-fxr-to" type="number" value="' + tTo.toFixed(2) + '" step="0.01" min="0" style="flex:none;width:80px;"></div>'
    + '<div><label style="font-size:10px;color:#666;">FX chain:</label>'
    + '<div id="p-fx-chain"></div>'
    + '<div style="display:flex;gap:4px;margin-top:4px;">'
    + '<button type="button" onclick="_addFxToChain(\'classic\')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>'
    + '<button type="button" onclick="_addFxToChain(\'morpho\')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>'
    + '</div></div></div>';

  var res = await showPopup("FX Regions \u2014 " + tk.name, html, function() { _initFxChain([]); });
  if (!res) return;

  // Handle delete
  var delIdx = document.getElementById("p-fxr-del").value;
  if (delIdx !== "-1") {
    var di = parseInt(delIdx);
    if (!isNaN(di) && di < tk.fx_regions.length) tk.fx_regions.splice(di, 1);
  }

  // Handle add
  var newFx = collectFxChain();
  if (newFx.length) {
    var from = parseFloat(document.getElementById("p-fxr-from").value) || tFrom;
    var to   = parseFloat(document.getElementById("p-fxr-to").value) || tTo;
    tk.fx_regions.push({ from: from, to: to, fx: newFx });
    tk.fx_regions.sort(function(a, b) { return a.from - b.from; });
  }

  _updateTrackRow(trackIdx);
}

// ─── Automation editor ───────────────────────────────────────────────────────
function _autoEditorCoords(cvs, e, trackIdx) {
  var tk = state.tracks[trackIdx];
  var rect = cvs.getBoundingClientRect();
  var x = (e.clientX - rect.left) * (cvs.width / rect.width);
  var y = (e.clientY - rect.top) * (cvs.height / rect.height);
  var tFrom = tk.from || 0, tTo = tk.to || state.duration || 1;
  var t  = tFrom + (x / cvs.width) * (tTo - tFrom);
  var db = (1 - y / cvs.height) * 46 - 40;
  return { t: Math.max(tFrom, Math.min(tTo, t)), db: Math.max(-40, Math.min(6, Math.round(db))) };
}

function _autoEditorHitTest(cvs, e, trackIdx) {
  var auto = (state.tracks[trackIdx] || {}).automation || [];
  if (!auto.length) return -1;
  var c = _autoEditorCoords(cvs, e, trackIdx);
  var tk = state.tracks[trackIdx];
  var dur = (tk.to || state.duration || 1) - (tk.from || 0);
  for (var i = 0; i < auto.length; i++) {
    if (Math.abs(auto[i].t - c.t) / dur * cvs.width < 8 &&
        Math.abs(auto[i].db - c.db) / 46 * cvs.height < 8) return i;
  }
  return -1;
}

function _autoEditorAdd(cvs, e, trackIdx) {
  var tk = state.tracks[trackIdx];
  var c = _autoEditorCoords(cvs, e, trackIdx);
  if (!tk.automation) tk.automation = [];
  tk.automation.push({ t: c.t, db: c.db });
  tk.automation.sort(function(a, b) { return a.t - b.t; });
  _updateTrackRow(trackIdx);
}

function _autoEditorMove(cvs, e, trackIdx, ptIdx) {
  var pt = (state.tracks[trackIdx].automation || [])[ptIdx];
  if (!pt) return;
  var c = _autoEditorCoords(cvs, e, trackIdx);
  pt.t = c.t; pt.db = c.db;
  state.tracks[trackIdx].automation.sort(function(a, b) { return a.t - b.t; });
  _autoEditorRedraw(cvs, trackIdx);
}

function _autoEditorDelete(cvs, e, trackIdx) {
  var pt = _autoEditorHitTest(cvs, e, trackIdx);
  if (pt < 0) return;
  state.tracks[trackIdx].automation.splice(pt, 1);
  _updateTrackRow(trackIdx);
}

function _autoEditorRedraw(cvs, trackIdx) {
  var tk = state.tracks[trackIdx];
  var ctx = cvs.getContext("2d");
  var W = cvs.width, H = cvs.height;
  if (W <= 0 || H <= 0) return;
  var tFrom = tk.from || 0, tTo = tk.to || state.duration || 1, dur = tTo - tFrom;
  var auto = tk.automation || [];

  ctx.fillStyle = "#0d0d0d";
  ctx.fillRect(0, 0, W, H);

  var peaks = tk.waveform;
  if (peaks && peaks.length) {
    var mid = H / 2;
    ctx.strokeStyle = "rgba(74,158,255,0.35)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (var j = 0; j < peaks.length; j++) {
      var x = (j / peaks.length) * W;
      ctx.moveTo(x, mid - peaks[j] * mid);
      ctx.lineTo(x, mid + peaks[j] * mid);
    }
    ctx.stroke();
  }

  ctx.strokeStyle = "#1a1a1a"; ctx.lineWidth = 1; ctx.setLineDash([2, 4]);
  ctx.font = "9px Courier New"; ctx.fillStyle = "#333";
  [-40, -30, -20, -10, 0, 6].forEach(function(db) {
    var y = H * (1 - (db + 40) / 46);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.fillText(db + "", 2, y - 2);
  });
  ctx.setLineDash([]);

  ctx.strokeStyle = "rgba(100,200,100,0.25)"; ctx.lineWidth = 1;
  var zy = H * (1 - 40 / 46);
  ctx.beginPath(); ctx.moveTo(0, zy); ctx.lineTo(W, zy); ctx.stroke();

  if (auto.length) {
    ctx.strokeStyle = "rgba(255,180,80,0.8)"; ctx.lineWidth = 2;
    ctx.beginPath();
    for (var i = 0; i < auto.length; i++) {
      var ax = ((auto[i].t - tFrom) / dur) * W;
      var ay = H * (1 - (auto[i].db + 40) / 46);
      if (i === 0) ctx.moveTo(ax, ay); else ctx.lineTo(ax, ay);
    }
    ctx.stroke();
    for (var i = 0; i < auto.length; i++) {
      var ax = ((auto[i].t - tFrom) / dur) * W;
      var ay = H * (1 - (auto[i].db + 40) / 46);
      ctx.fillStyle = "#ffb450"; ctx.beginPath(); ctx.arc(ax, ay, 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#000"; ctx.beginPath(); ctx.arc(ax, ay, 2, 0, Math.PI * 2); ctx.fill();
    }
  }

  // FX regions overlay
  var fxRegions = tk.fx_regions || [];
  for (var ri = 0; ri < fxRegions.length; ri++) {
    var rx1 = ((fxRegions[ri].from - tFrom) / dur) * W;
    var rx2 = ((fxRegions[ri].to - tFrom) / dur) * W;
    ctx.fillStyle = "rgba(136,68,204,0.15)";
    ctx.fillRect(rx1, 0, rx2 - rx1, H);
    ctx.strokeStyle = "rgba(136,68,204,0.5)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(rx1, 0); ctx.lineTo(rx1, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(rx2, 0); ctx.lineTo(rx2, H); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(136,68,204,0.8)"; ctx.font = "9px Courier New";
    ctx.fillText(fxRegions[ri].fx.map(function(f) { return f.type; }).join("+"), rx1 + 3, 10);
  }

  // Playback cursor
  if (state.duration > 0 && state.currentTime >= tFrom && state.currentTime <= tTo) {
    var cx = ((state.currentTime - tFrom) / dur) * W;
    ctx.strokeStyle = "rgba(255,50,50,0.7)"; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}

// ─── Track FX popup ──────────────────────────────────────────────────────────
async function openTrackFxPopup(i) {
  var tk = state.tracks[i];
  if (!tk) return;
  var html = '<div style="margin-bottom:4px;"><label style="font-size:10px;color:#666;">FX chain for "' + tk.name + '":</label>'
    + '<div id="p-fx-chain"></div>'
    + '<div style="display:flex;gap:4px;margin-top:4px;">'
    + '<button type="button" onclick="_addFxToChain(\'classic\')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>'
    + '<button type="button" onclick="_addFxToChain(\'morpho\')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>'
    + '</div></div>'
    + (tk.fx && tk.fx.length ? '<button type="button" onclick="_initFxChain([])" style="font-size:10px;padding:2px 6px;color:#f66;">Clear all FX</button>' : '');
  var res = await showPopup("FX \u2014 " + tk.name, html, function() { _initFxChain(tk.fx || []); });
  if (!res) return;
  state.tracks[i].fx = collectFxChain();
  _updateTrackRow(i);
}
