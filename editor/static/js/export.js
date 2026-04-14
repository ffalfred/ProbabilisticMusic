// ─── Export helpers ───────────────────────────────────────────────────────────
function _defaultName(ext) {
  if (!state.filePath) return 'score.' + ext;
  return state.filePath.split('/').pop().replace(/\.[^.]+$/, '') + '.' + ext;
}

// ─── Export MP4 ───────────────────────────────────────────────────────────────
async function _doExportMp4(outputPath) {
  const btn = document.getElementById("export-mp4-btn");
  btn.textContent = "⏳ rendering…"; btn.disabled = true;
  try {
    const res = await fetch("/export_mp4", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        audioPath:   state.filePath,
        imagePath:   scoreView.path,
        scoreStart:  scoreView.start,
        scoreEnd:    scoreView.end,
        output_path: outputPath,
      })
    });
    const data = await res.json();
    if (data.error) { alert("MP4 error: " + data.error); }
    else { document.getElementById("export-status").textContent = "MP4 → " + data.path; }
  } catch(e) { alert("MP4 failed: " + e); }
  finally { btn.textContent = "\u21D3 MP4"; btn.disabled = false; }
}

document.getElementById("export-mp4-path").addEventListener("click", () => {
  if (!scoreView.path) { alert("Load a score image first."); return; }
  if (!state.filePath) { alert("Load an audio file first."); return; }
  const pathEl = document.getElementById("export-mp4-path");
  openSaveBrowser(p => { pathEl.value = p; _doExportMp4(p); },
    pathEl.value || _defaultName('mp4'));
});

document.getElementById("export-mp4-btn").addEventListener("click", () => {
  if (!scoreView.path) { alert("Load a score image first."); return; }
  if (!state.filePath) { alert("Load an audio file first."); return; }
  const pathEl = document.getElementById("export-mp4-path");
  const path = pathEl.value.trim();
  if (!path) {
    openSaveBrowser(p => { pathEl.value = p; _doExportMp4(p); }, _defaultName('mp4'));
    return;
  }
  _doExportMp4(path);
});

// ─── Stemize ─────────────────────────────────────────────────────────────────
let _sepBands = [
  { name: "bass",  low: 20,   high: 250  },
  { name: "mids",  low: 250,  high: 4000 },
  { name: "highs", low: 4000, high: 20000 },
];

function _iStyle() {
  return 'style="width:60px;background:#1a1a1a;border:1px solid #333;color:#ccc;font-family:inherit;font-size:11px;padding:2px 4px;"';
}
function _nStyle() {
  return 'style="width:72px;background:#1a1a1a;border:1px solid #333;color:#ccc;font-family:inherit;font-size:11px;padding:2px 4px;"';
}

function _renderBands() {
  const list = document.getElementById("sep-bands-list");
  if (!list) return;
  list.innerHTML = _sepBands.map((b, i) => `
    <div class="sep-band-row" style="display:flex;align-items:center;gap:5px;margin-bottom:4px;">
      <input class="sep-band-name" type="text" value="${b.name}" placeholder="name" ${_nStyle()} />
      <input class="sep-band-low"  type="number" value="${b.low}"  min="0" max="22050" step="1" title="Low Hz"  ${_iStyle()} />
      <span style="color:#444;font-size:10px;">–</span>
      <input class="sep-band-high" type="number" value="${b.high}" min="0" max="22050" step="1" title="High Hz" ${_iStyle()} />
      <span style="color:#444;font-size:10px;">Hz</span>
      <button onclick="_removeBand(${i})" style="padding:1px 6px;font-size:10px;color:#844;">✕</button>
    </div>`).join("") +
    `<button onclick="_addBand()" style="font-size:10px;padding:2px 8px;margin-top:2px;">+ Band</button>`;
}

function _readBandsFromDOM() {
  return Array.from(document.querySelectorAll("#sep-bands-list .sep-band-row")).map(r => ({
    name: r.querySelector(".sep-band-name").value.trim() || "band",
    low:  parseFloat(r.querySelector(".sep-band-low").value)  || 0,
    high: parseFloat(r.querySelector(".sep-band-high").value) || 20000,
  }));
}

function _addBand() {
  _sepBands = _readBandsFromDOM();
  const last = _sepBands[_sepBands.length - 1];
  _sepBands.push({ name: "band " + (_sepBands.length + 1), low: last ? last.high : 0, high: 20000 });
  _renderBands();
}

function _removeBand(i) {
  _sepBands = _readBandsFromDOM();
  if (_sepBands.length > 1) { _sepBands.splice(i, 1); _renderBands(); }
}

function _onSepMethodChange() {
  const method = document.getElementById("p-sep-method")?.value;
  const nmfEl = document.getElementById("sep-nmf-opts");
  const fbEl  = document.getElementById("sep-freqband-opts");
  if (nmfEl) nmfEl.style.display = (method === "nmf" || method === "both") ? "" : "none";
  if (fbEl)  fbEl.style.display  = method === "freqband" ? "" : "none";
}

document.getElementById("separate-btn").addEventListener("click", async () => {
  if (!state.tracks.length || !state.tracks[0].path) { alert("Load an audio file first."); return; }
  const durStr = state.duration ? state.duration.toFixed(2) : "";
  const html = row("method", `<select id="p-sep-method" onchange="_onSepMethodChange()">
      <option value="hpss">Harmonic / Percussive (HPSS)</option>
      <option value="nmf">NMF components</option>
      <option value="both">Both (HPSS + NMF)</option>
      <option value="freqband">Frequency bands</option>
    </select>`)
    + `<div id="sep-nmf-opts">`
    + row("NMF components", `<input id="p-sep-n" type="number" value="3" min="2" max="8" step="1" style="width:60px;">`)
    + row("NMF reconstruction", `<select id="p-sep-nmf-mode">
      <option value="softmask">Soft mask (stems sum to original)</option>
      <option value="naive">Naive (raw components, quieter)</option>
    </select>`)
    + `</div>`
    + `<div id="sep-freqband-opts" style="display:none;">`
    + `<div class="popup-row"><label>bands</label><div id="sep-bands-list"></div></div>`
    + `</div>`
    + row("time range (s)", `<input id="p-sep-from" type="number" value="0" min="0" step="0.1" style="width:70px;" placeholder="start">
      &nbsp;–&nbsp;
      <input id="p-sep-to" type="number" value="${durStr}" min="0" step="0.1" style="width:70px;" placeholder="end (blank=full)">
      <span style="font-size:10px;color:#777;margin-left:6px;">leave blank for full file</span>`)
    + `<div class="popup-row" style="margin-top:6px;">
        <label><input type="checkbox" id="stem-replace"> Replace existing stems</label>
        <span style="font-size:10px;color:#666;margin-left:6px;">unchecked = append new stems to tracks</span>
      </div>`;

  const popupPromise = showPopup("&#9881; Separate audio", html);
  _renderBands();   // populate band list immediately after innerHTML is set
  const ok = await popupPromise;
  if (!ok) return;

  const method   = document.getElementById("p-sep-method").value;
  const n        = parseInt(document.getElementById("p-sep-n").value) || 3;
  const nmf_mode = document.getElementById("p-sep-nmf-mode").value;
  const fromVal  = document.getElementById("p-sep-from").value.trim();
  const toVal    = document.getElementById("p-sep-to").value.trim();
  const from_t   = fromVal !== "" ? parseFloat(fromVal) : null;
  const to_t     = toVal   !== "" ? parseFloat(toVal)   : null;
  const bands    = method === "freqband" ? _readBandsFromDOM() : [];
  const btn    = document.getElementById("separate-btn");
  const status = document.getElementById("export-status");
  btn.textContent = "⏳…"; btn.disabled = true;
  status.textContent = "separating…";
  try {
    const r = await fetch("/separate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.tracks[0].path, method, n_components: n, nmf_mode, bands,
                             ...(from_t !== null ? { from_t } : {}),
                             ...(to_t   !== null ? { to_t   } : {}) })
    });
    const data = await r.json();
    if (data.error) { status.textContent = "error: " + data.error; return; }
    baseAudio.pause();
    vid.pause();
    const replaceStem = document.getElementById('stem-replace')?.checked;
    if (replaceStem) state.tracks.splice(1);
    Object.keys(_waCache).forEach(k => delete _waCache[k]);
    for (const stem of data.stems) {
      const wr = await fetch("/load", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ path: stem.path })
      });
      const wd = await wr.json();
      state.tracks.push({ name: stem.name, path: stem.path,
                          gain_db: 0, muted: false,
                          from: from_t || 0, to: to_t || state.duration,
                          waveform: wd.waveform || [],
                          source: 'stem' });
    }
    currentSourcePath = null;
    renderTracksPanel();
    status.textContent = `${data.stems.length} stems added as tracks`;
  } catch(e) {
    status.textContent = "separate failed: " + e;
  } finally {
    btn.textContent = "⚙ Stemize"; btn.disabled = false;
  }
});

// ─── Quantize ────────────────────────────────────────────────────────────────
document.getElementById("quantize-btn").addEventListener("click", async () => {
  if (!state.events.length) { alert("No events to quantize.\n\nEvents are time-placed notes created with the \u25ba Event tool (click on the waveform). Samples define audio clips but are not quantized — only placed events are snapped to the grid."); return; }
  const html =
      row("BPM", `<input id="q-bpm" type="number" value="120" min="1" step="0.5" style="width:70px;">`)
    + row("subdivision", `<select id="q-sub">
        <option value="1">1/4 (quarter note)</option>
        <option value="2" selected>1/8 (eighth note)</option>
        <option value="4">1/16 (sixteenth note)</option>
        <option value="8">1/32 (thirty-second note)</option>
        <option value="0.5">1/2 (half note)</option>
      </select>`)
    + row("strength %", `<input id="q-str" type="number" value="100" min="0" max="100" step="5" style="width:60px;">`
        + `<span style="font-size:10px;color:#666;"> (100 = full snap, 50 = halfway)</span>`);
  const ok = await showPopup("Quantize events", html);
  if (!ok) return;
  try {
    const bpm      = parseFloat(document.getElementById("q-bpm").value)  || 120;
    const subdiv   = parseFloat(document.getElementById("q-sub").value)  || 2;
    const strength = (parseFloat(document.getElementById("q-str").value) || 100) / 100;
    const grid = (60 / bpm) / subdiv;
    pushHistory();
    state.events = state.events.map(ev => {
      const snapped = Math.round(ev.t / grid) * grid;
      return Object.assign({}, ev, { t: ev.t + (snapped - ev.t) * strength });
    });
    updateScoreInfo();
    draw();
  } catch(e) { alert("Quantize error: " + e); }
});

// ─── Export YAML ──────────────────────────────────────────────────────────────
async function _doExportYaml(outputPath) {
  const samplesClean = {};
  for (const [k, v] of Object.entries(state.samples)) {
    samplesClean[k] = { from: v.from, to: v.to,
      fade_in: v.fade_in ?? 0.05, fade_out: v.fade_out ?? 0.05,
      ...(v.track ? { track: v.track } : {}) };
  }
  const score = {
    output_path: outputPath,
    samples: samplesClean,
    dynamics: state.dynamics.map(d => {
      // Export using 'marking' field (Kalman engine format)
      const { mark, ...rest } = d;
      return { ...rest, marking: mark };
    }),
    tempo: state.tempo,
    base_fx: state.baseFx,
    fx_ranges: state.fxRanges,
    events: state.events,
    phrases: state.phrases.map(p => ({
      from: p.from, to: p.to, label: p.label,
      gain_db: p.gain_db ?? 0, fade_in: p.fade_in ?? 0,
      fade_out: p.fade_out ?? 0, tempo_factor: p.tempo_factor ?? 1.0,
    })),
    ...(state.noteRel.length ? { note_rel: state.noteRel } : {}),
    ...(state.articulations.length ? { articulations: state.articulations } : {}),
    ...(state.tracks.length > 1 ? { tracks: state.tracks.map(tk => ({
      path: tk.path, name: tk.name, gain_db: tk.gain_db, muted: tk.muted,
      ...(tk.from != null ? { from: tk.from } : {}),
      ...(tk.to   != null ? { to:   tk.to   } : {}),
      ...(tk.fx?.length         ? { fx:   tk.fx   } : {}),
      ...(tk.automation?.length ? { automation: tk.automation } : {}),
      ...(tk.fx_regions?.length ? { fx_regions: tk.fx_regions } : {}),
    })) } : {}),
    ...(scoreView.path ? {
      score_image: scoreView.path,
      score_start: scoreView.start,
      score_end:   scoreView.end,
    } : {}),
    ...(score2View.path ? {
      score2_image: score2View.path,
      score2_start: score2View.start,
      score2_end:   score2View.end,
    } : {}),
    ...(state.duckBase.enabled ? { duck_base: state.duckBase } : {}),
    ...(state.duckKey.enabled  ? { duck_key:  state.duckKey  } : {}),
    ...(state.autoMix.enabled  ? { auto_mix:  state.autoMix  } : {}),
  };
  const statusEl = document.getElementById("export-status");
  statusEl.textContent = "saving…";
  try {
    const res = await fetch("/export", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(score)
    });
    const data = await res.json();
    statusEl.textContent = "saved → " + data.path;
    state.lastScorePath = data.path;
    setTimeout(() => { statusEl.textContent = ""; }, 4000);
  } catch(e) { statusEl.textContent = "export failed: " + e; }
}

document.getElementById("export-yaml-path").addEventListener("click", () => {
  const pathEl = document.getElementById("export-yaml-path");
  openSaveBrowser(p => { pathEl.value = p; _doExportYaml(p); },
    pathEl.value || _defaultName('yaml'));
});

document.getElementById("export-btn").addEventListener("click", () => {
  const pathEl = document.getElementById("export-yaml-path");
  const path = pathEl.value.trim();
  if (!path) {
    openSaveBrowser(p => { pathEl.value = p; _doExportYaml(p); }, _defaultName('yaml'));
    return;
  }
  _doExportYaml(path);
});

// ─── Import YAML ─────────────────────────────────────────────────────────────
document.getElementById("import-btn").addEventListener("click", async () => {
  const path = document.getElementById("import-path").value.trim();
  if (!path) { alert("Enter the path to a .yaml score file."); return; }
  const statusEl = document.getElementById("export-status");
  statusEl.textContent = "loading…";
  try {
    const res = await fetch("/load_yaml", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (data.error) { alert("Import failed: " + data.error); statusEl.textContent = ""; return; }
    const sc = data.score;

    if (sc.samples)      state.samples       = sc.samples;
    if (sc.dynamics)     state.dynamics      = sc.dynamics.map(d => {
      // Normalize YAML field 'marking' → internal field 'mark'
      if (d.marking !== undefined && d.mark === undefined) {
        const { marking, ...rest } = d;
        return { ...rest, mark: marking };
      }
      return d;
    });
    if (sc.tempo)        state.tempo         = sc.tempo;
    if (sc.events)       state.events        = sc.events;
    if (sc.phrases)      state.phrases       = (sc.phrases || []).map(p => Object.assign({ gain_db: 0, fade_in: 0, fade_out: 0, tempo_factor: 1.0 }, p));
    if (sc.note_rel)     state.noteRel       = sc.note_rel;
    if (sc.articulations) state.articulations = sc.articulations;
    if (sc.base_fx)      state.baseFx        = sc.base_fx;
    if (sc.fx_ranges)    state.fxRanges      = sc.fx_ranges;
    if (sc.duck_base)    Object.assign(state.duckBase, sc.duck_base);
    if (sc.duck_key)     Object.assign(state.duckKey,  sc.duck_key);
    if (sc.auto_mix)     Object.assign(state.autoMix,  sc.auto_mix);
    if (sc.golems)       interpState.golems = sc.golems;

    for (const k of Object.keys(state.samples)) {
      if (!state.samples[k].color) state.samples[k].color = nextColor();
    }

    state.lastScorePath = path;
    // Sync to Interpreter's score path
    interpState.scorePath = path;
    const _interpScIn = document.getElementById('interp-score-path');
    if (_interpScIn) _interpScIn.value = path;

    if (sc.base_track && !state.filePath) {
      document.getElementById("path-input").value = sc.base_track;
      await loadFile();
    }

    if (sc.score_image) {
      document.getElementById("score-path-input").value = sc.score_image;
      const sStart = sc.score_start ?? 0;
      const sEnd   = sc.score_end   ?? state.duration;
      document.getElementById("score-start-input").value = sStart.toFixed(3);
      document.getElementById("score-end-input").value   = sEnd.toFixed(3);
      const img = new Image();
      img.src = "/image?path=" + encodeURIComponent(sc.score_image);
      img.onload = () => {
        scoreView.img = img; scoreView.path = sc.score_image;
        scoreView.start = sStart; scoreView.end = sEnd; scoreView.panOffset = 0;
        draw();
      };
    }

    if (sc.score2_image) {
      document.getElementById("score2-path-input").value = sc.score2_image;
      const s2Start = sc.score2_start ?? 0;
      const s2End   = sc.score2_end   ?? state.duration;
      document.getElementById("score2-start-input").value = s2Start.toFixed(3);
      document.getElementById("score2-end-input").value   = s2End.toFixed(3);
      const img2 = new Image();
      img2.src = "/image?path=" + encodeURIComponent(sc.score2_image);
      img2.onload = () => {
        score2View.img = img2; score2View.path = sc.score2_image;
        score2View.start = s2Start; score2View.end = s2End; score2View.panOffset = 0;
        const cont = document.getElementById("score2-container");
        if (!cont.classList.contains("visible")) {
          cont.classList.add("visible");
          document.getElementById("toggle-score2-btn").classList.add("active");
          setTimeout(resizeScore2Canvas, 10);
        } else { resizeScore2Canvas(); }
      };
    }

    updateScoreInfo();
    draw();
    statusEl.textContent = "imported ← " + path;
    setTimeout(() => { statusEl.textContent = ""; }, 4000);
  } catch(e) { statusEl.textContent = "import failed: " + e; }
});
