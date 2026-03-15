// ─── Popup helpers ─────────────────────────────────────────────────────────────
const overlay = document.getElementById("popup-overlay");
const popupTitle = document.getElementById("popup-title");
const popupBody = document.getElementById("popup-body");
let popupResolve = null;

document.getElementById("popup-cancel").addEventListener("click", () => {
  overlay.classList.remove("visible");
  if (popupResolve) popupResolve(null);
});
document.getElementById("popup-confirm").addEventListener("click", () => {
  overlay.classList.remove("visible");
  if (popupResolve) popupResolve("confirm");
});

function showPopup(title, bodyHTML) {
  popupTitle.innerHTML = title;
  popupBody.innerHTML = bodyHTML;
  overlay.classList.add("visible");
  return new Promise(res => { popupResolve = res; });
}

function row(label, inputHTML) {
  return `<div class="popup-row"><label>${label}</label>${inputHTML}</div>`;
}

// ─── Probabilistic param widgets ──────────────────────────────────────────────
function paramWidget(id, label, defaultVal, step, min) {
  const minAttr = min != null ? `min="${min}"` : "";
  return `<div class="popup-row">
    <label>${label}</label>
    <select id="${id}-mode" onchange="updateParamWidget('${id}')"
      style="width:80px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
      <option value="fixed">= fixed</option>
      <option value="range">↔ range</option>
      <option value="gauss">~ gauss</option>
    </select>
    <span id="${id}-inputs" style="display:flex;gap:4px;flex:1;">
      <input id="${id}-v" type="number" value="${defaultVal}" step="${step}" ${minAttr} style="flex:1;" />
    </span>
  </div>`;
}

function updateParamWidget(id) {
  const mode = document.getElementById(id + "-mode").value;
  const el   = document.getElementById(id + "-inputs");
  const prev = document.getElementById(id + "-v");
  const val  = prev ? parseFloat(prev.value) : 1;
  if (mode === "fixed") {
    el.innerHTML = `<input id="${id}-v" type="number" value="${val}" step="0.1" style="flex:1;" />`;
  } else if (mode === "range") {
    const lo = (val * 0.75).toFixed(2), hi = (val * 1.25).toFixed(2);
    el.innerHTML = `<input id="${id}-lo" type="number" value="${lo}" step="0.05" style="flex:1;" placeholder="min" />
                    <span style="color:#444;align-self:center;">–</span>
                    <input id="${id}-hi" type="number" value="${hi}" step="0.05" style="flex:1;" placeholder="max" />`;
  } else {
    el.innerHTML = `<input id="${id}-mean" type="number" value="${val}" step="0.05" style="flex:1;" placeholder="mean" />
                    <span style="color:#444;align-self:center;">±</span>
                    <input id="${id}-std"  type="number" value="0.1"  step="0.01" min="0" style="flex:1;" placeholder="std" />`;
  }
}

function collectParam(id) {
  const mode = document.getElementById(id + "-mode").value;
  if (mode === "range") {
    return [parseFloat(document.getElementById(id + "-lo").value),
            parseFloat(document.getElementById(id + "-hi").value)];
  } else if (mode === "gauss") {
    return { distribution: "gaussian",
             mean: parseFloat(document.getElementById(id + "-mean").value),
             std:  parseFloat(document.getElementById(id + "-std").value) };
  }
  return parseFloat(document.getElementById(id + "-v").value);
}

// ─── FX params helper ─────────────────────────────────────────────────────────
function fxParamsHTML(fxType) {
  if (fxType === "none") return "";
  let html = "";
  if (fxType === "reverb" || fxType === "reverb+delay") {
    html += paramWidget("p-reverberance", "reverberance", 60, 5, 0);
  }
  if (fxType === "delay" || fxType === "reverb+delay") {
    html += paramWidget("p-delay-sec", "delay_sec", 0.3, 0.05, 0);
    html += paramWidget("p-feedback",  "feedback",  0.4, 0.05, 0);
  }
  if (fxType === "overdrive") {
    html += paramWidget("p-od-gain",   "gain",   20, 5, 0);
    html += paramWidget("p-od-colour", "colour", 20, 5, 0);
  }
  if (fxType === "flanger") {
    html += paramWidget("p-fl-delay", "delay_ms", 0,   1,   0);
    html += paramWidget("p-fl-depth", "depth_ms", 2,   1,   0);
    html += paramWidget("p-fl-speed", "speed_hz", 0.5, 0.1, 0.1);
  }
  if (fxType === "pitch") {
    html += paramWidget("p-pitch-cents", "cents", 0, 100, null);
  }
  if (fxType === "compress") {
    html += paramWidget("p-cmp-threshold", "threshold_db", -20, 1,   null);
    html += paramWidget("p-cmp-ratio",     "ratio",          4, 0.5, 1);
    html += paramWidget("p-cmp-attack",    "attack",      0.01, 0.005, 0.001);
    html += paramWidget("p-cmp-release",   "release",      0.3, 0.05, 0.01);
    html += paramWidget("p-cmp-makeup",    "makeup_db",      0, 1,   null);
  }
  if (fxType === "eq") {
    html += paramWidget("p-eq-freq",  "freq_hz", 1000, 50,  20);
    html += paramWidget("p-eq-gain",  "gain_db",    0,  1, null);
    html += paramWidget("p-eq-q",     "q",         1.0, 0.1, 0.1);
  }
  return html;
}

function updateFxParams() {
  const fxType = document.getElementById("p-fx").value;
  document.getElementById("p-fx-params").innerHTML = fxParamsHTML(fxType);
}

function collectFx() {
  const fxType = document.getElementById("p-fx").value;
  if (fxType === "none") return [];
  const result = [];
  if (fxType === "reverb" || fxType === "reverb+delay") {
    result.push({ type: "reverb", reverberance: collectParam("p-reverberance") });
  }
  if (fxType === "delay" || fxType === "reverb+delay") {
    result.push({ type: "delay", delay_sec: collectParam("p-delay-sec"), feedback: collectParam("p-feedback") });
  }
  if (fxType === "overdrive") {
    result.push({ type: "overdrive", gain: collectParam("p-od-gain"), colour: collectParam("p-od-colour") });
  }
  if (fxType === "flanger") {
    result.push({ type: "flanger", delay_ms: collectParam("p-fl-delay"), depth_ms: collectParam("p-fl-depth"), speed_hz: collectParam("p-fl-speed") });
  }
  if (fxType === "pitch") {
    result.push({ type: "pitch", cents: collectParam("p-pitch-cents") });
  }
  if (fxType === "compress") {
    result.push({ type: "compress", threshold_db: collectParam("p-cmp-threshold"), ratio: collectParam("p-cmp-ratio"), attack: collectParam("p-cmp-attack"), release: collectParam("p-cmp-release"), makeup_db: collectParam("p-cmp-makeup") });
  }
  if (fxType === "eq") {
    result.push({ type: "eq", freq_hz: collectParam("p-eq-freq"), gain_db: collectParam("p-eq-gain"), q: collectParam("p-eq-q") });
  }
  return result;
}

// ─── Sample popup ─────────────────────────────────────────────────────────────
async function openSamplePopup(t1, t2) {
  const trackOpts = state.tracks.length > 1
    ? state.tracks.map((tk, i) => `<option value="${i}">${i}: ${tk.name}</option>`).join('')
    : '<option value="0">0: base</option>';
  const html = row("name", `<input id="p-name" type="text" value="s${Object.keys(state.samples).length + 1}" />`)
    + (state.tracks.length > 1 ? row("track", `<select id="p-track">${trackOpts}</select>`) : "")
    + row("fade in",  `<input id="p-fi" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-fo" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s</div>`;
  const res = await showPopup("[ Sample ] — define range", html);
  if (!res) return;
  const name = document.getElementById("p-name").value.trim() || ("s" + Date.now());
  const fi = Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-fi").value) || 5) / 100));
  const fo = Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-fo").value) || 5) / 100));
  const trackEl = document.getElementById("p-track");
  const trackIdx = trackEl ? (parseInt(trackEl.value) || 0) : 0;
  const color = nextColor();
  pushHistory();
  state.samples[name] = { from: t1, to: t2, color, fade_in: fi, fade_out: fo, track: trackIdx };
  updateScoreInfo();
  draw();
}

// ─── Event popup ──────────────────────────────────────────────────────────────
async function openEventPopup(t) {
  const sampleOptions = Object.keys(state.samples).map(n =>
    `<option value="${n}">${n}</option>`).join("") || `<option value="">— no samples —</option>`;
  const html = row("sample", `<select id="p-sample">${sampleOptions}</select>`)
    + paramWidget("p-speed",  "speed",   "1.0", "0.1",  "0.01")
    + row("speeds", `<input id="p-speeds" type="text" placeholder="0.5, 1.0, 2.0  (layers, overrides speed)" style="font-size:11px;" />`)
    + paramWidget("p-gain",   "gain_db", "0",   "1",    null)
    + row("loop", `<input id="p-loop" type="number" value="0" min="0" step="1" style="width:60px;" title="extra repeats (0 = play once)" />`)
    + row("reverse", `<select id="p-rev-mode" onchange="updateRevWidget()"
        style="width:90px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
        <option value="no">no</option>
        <option value="yes">yes</option>
        <option value="p">~ bernoulli</option>
      </select><span id="p-rev-inputs" style="display:flex;gap:4px;flex:1;"></span>`)
    + row("fx", `<select id="p-fx" onchange="updateFxParams()">
        <option value="none">none</option>
        <option value="reverb">reverb</option>
        <option value="delay">delay</option>
        <option value="reverb+delay">reverb+delay</option>
        <option value="overdrive">overdrive</option>
        <option value="flanger">flanger</option>
        <option value="pitch">pitch</option>
        <option value="compress">compress</option>
        <option value="eq">eq</option>
      </select>`)
    + `<div id="p-fx-params"></div>`
    + row("time (s)", `<input id="p-t" type="number" value="${t.toFixed(3)}" step="0.01" style="width:90px;" />`);
  const res = await showPopup("▶ Event — place playback", html);
  if (!res) return;
  const sample = document.getElementById("p-sample").value;
  if (!sample) return;

  // collect reverse
  const revMode = document.getElementById("p-rev-mode").value;
  let reverseVal;
  if (revMode === "yes") reverseVal = true;
  else if (revMode === "p") reverseVal = { distribution: "bernoulli", p: parseFloat(document.getElementById("p-rev-p").value) || 0.5 };
  else reverseVal = false;

  // parse speeds list (overrides speed if non-empty)
  const speedsRaw = document.getElementById("p-speeds").value.trim();
  const speedsArr = speedsRaw ? speedsRaw.split(",").map(s => parseFloat(s.trim())).filter(n => !isNaN(n)) : [];

  const ev = {
    sample,
    t: parseFloat(document.getElementById("p-t").value) || t,
    gain_db: collectParam("p-gain"),
    loop:    parseInt(document.getElementById("p-loop").value) || 0,
    reverse: reverseVal,
    fx:      collectFx()
  };
  if (speedsArr.length > 0) ev.speeds = speedsArr;
  else ev.speed = collectParam("p-speed");

  pushHistory();
  state.events.push(ev);
  state.events.sort((a, b) => a.t - b.t);
  updateScoreInfo();
  draw();
}

async function editEventAt(i) {
  const ev = state.events[i];
  const sampleOptions = Object.keys(state.samples).map(n =>
    `<option value="${n}"${n === ev.sample ? " selected" : ""}>${n}</option>`).join("");
  const speedsVal = ev.speeds ? ev.speeds.join(", ") : "";
  const revDefault = ev.reverse === true ? "yes" : (ev.reverse && ev.reverse.distribution ? "p" : "no");
  const revP = (ev.reverse && ev.reverse.p != null) ? ev.reverse.p : 0.5;
  const html = row("sample", `<select id="p-sample">${sampleOptions}</select>`)
    + paramWidget("p-speed",  "speed",   ev.speed ?? 1.0, "0.1", "0.01")
    + row("speeds", `<input id="p-speeds" type="text" value="${speedsVal}" placeholder="0.5, 1.0, 2.0  (layers, overrides speed)" style="font-size:11px;" />`)
    + paramWidget("p-gain",   "gain_db", ev.gain_db ?? -6, "1", null)
    + row("loop", `<input id="p-loop" type="number" value="${ev.loop ?? 0}" min="0" step="1" style="width:60px;" />`)
    + row("reverse", `<select id="p-rev-mode" onchange="updateRevWidget()"
        style="width:90px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
        <option value="no"${revDefault==="no"?" selected":""}>no</option>
        <option value="yes"${revDefault==="yes"?" selected":""}>yes</option>
        <option value="p"${revDefault==="p"?" selected":""}>~ bernoulli</option>
      </select><span id="p-rev-inputs" style="display:flex;gap:4px;flex:1;">${revDefault==="p" ? `<input id="p-rev-p" type="number" value="${revP}" min="0" max="1" step="0.05" style="flex:1;" />` : ""}</span>`)
    + row("fx", `<select id="p-fx" onchange="updateFxParams()">
        <option value="none">none</option>
        <option value="reverb">reverb</option>
        <option value="delay">delay</option>
        <option value="reverb+delay">reverb+delay</option>
        <option value="overdrive">overdrive</option>
        <option value="flanger">flanger</option>
        <option value="pitch">pitch</option>
        <option value="compress">compress</option>
        <option value="eq">eq</option>
      </select>`)
    + `<div id="p-fx-params"></div>`
    + row("time (s)", `<input id="p-t" type="number" value="${ev.t.toFixed(3)}" step="0.01" style="width:90px;" />`);
  const res = await showPopup("✎ Edit Event", html);
  if (!res) return;
  const sample = document.getElementById("p-sample").value;
  if (!sample) return;
  const revMode = document.getElementById("p-rev-mode").value;
  let reverseVal;
  if (revMode === "yes") reverseVal = true;
  else if (revMode === "p") reverseVal = { distribution: "bernoulli", p: parseFloat(document.getElementById("p-rev-p").value) || 0.5 };
  else reverseVal = false;
  const speedsRaw = document.getElementById("p-speeds").value.trim();
  const speedsArr = speedsRaw ? speedsRaw.split(",").map(s => parseFloat(s.trim())).filter(n => !isNaN(n)) : [];
  const updated = {
    sample,
    t: parseFloat(document.getElementById("p-t").value) || ev.t,
    gain_db: collectParam("p-gain"),
    loop:    parseInt(document.getElementById("p-loop").value) || 0,
    reverse: reverseVal,
    fx:      collectFx()
  };
  if (speedsArr.length > 0) updated.speeds = speedsArr;
  else updated.speed = collectParam("p-speed");
  pushHistory();
  state.events[i] = updated;
  state.events.sort((a, b) => a.t - b.t);
  updateScoreInfo();
  draw();
}

function updateRevWidget() {
  const mode = document.getElementById("p-rev-mode").value;
  const el   = document.getElementById("p-rev-inputs");
  el.innerHTML = mode === "p"
    ? `<input id="p-rev-p" type="number" value="0.5" min="0" max="1" step="0.05" style="flex:1;" placeholder="probability" />`
    : "";
}

// ─── Mark popup ───────────────────────────────────────────────────────────────
async function openMarkPopup(t) {
  const marks = ["ppp","pp","p","mp","mf","f","ff","fff"];
  const opts = marks.map(m =>
    `<option value="${m}" style="color:${DYNAMIC_COLORS[m]}">${m}</option>`).join("");
  const html = row("mark", `<select id="p-mark">${opts}</select>`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">at: ${t.toFixed(3)}s</div>`;
  const res = await showPopup("• Mark — dynamic point", html);
  if (!res) return;
  pushHistory();
  state.dynamics.push({ t, mark: document.getElementById("p-mark").value });
  updateScoreInfo();
  draw();
}

// ─── Range popup ──────────────────────────────────────────────────────────────
async function openRangePopup(t1, t2) {
  const html = row("type", `<select id="p-rtype">
      <option value="crescendo">crescendo</option>
      <option value="decrescendo">decrescendo</option>
    </select>`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s</div>`;
  const res = await showPopup("~ Range — crescendo/decrescendo", html);
  if (!res) return;
  pushHistory();
  state.dynamics.push({ from: t1, to: t2, mark: document.getElementById("p-rtype").value });
  updateScoreInfo();
  draw();
}

// ─── Tempo popup ──────────────────────────────────────────────────────────────
async function openTempoPopup(t1, t2) {
  const html = row("direction", `<select id="p-tdir">
      <option value="accelerando">accelerando</option>
      <option value="ritardando">ritardando</option>
    </select>`)
    + paramWidget("p-tfactor", "end factor", "2.0", "0.1", "0.01")
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s<br>factor = speed ratio at end of range</div>`;
  const res = await showPopup("⏱ Tempo — accelerando/ritardando", html);
  if (!res) return;
  pushHistory();
  state.tempo.push({
    from: t1,
    to: t2,
    mark: document.getElementById("p-tdir").value,
    factor: collectParam("p-tfactor")
  });
  updateScoreInfo();
  draw();
}

// ─── Phrase popup ─────────────────────────────────────────────────────────────
async function openPhrasePopup(t1, t2) {
  const n = state.phrases.length + 1;
  const html = row("label",    `<input id="p-phrase-label" type="text" value="slur ${n}" />`)
    + row("gain dB",  `<input id="p-ph-gain"  type="number" value="0"   step="0.5" style="width:60px;">`)
    + row("fade in",  `<input id="p-ph-fi"    type="number" value="0"   min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-ph-fo"    type="number" value="0"   min="0" max="50" step="1" style="width:60px;"> %`)
    + row("tempo ×",  `<input id="p-ph-tempo" type="number" value="1.0" step="0.05" min="0.1" style="width:60px;"> <span style="font-size:10px;color:#666;">(1.0 = no change)</span>`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s</div>`;
  const res = await showPopup("&#8994; Slur", html);
  if (!res) return;
  const label = document.getElementById("p-phrase-label").value.trim() || `slur ${n}`;
  pushHistory();
  state.phrases.push({
    from: t1, to: t2, label,
    gain_db:      parseFloat(document.getElementById("p-ph-gain").value)  || 0,
    fade_in:      Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fi").value)   || 0) / 100)),
    fade_out:     Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fo").value)   || 0) / 100)),
    tempo_factor: parseFloat(document.getElementById("p-ph-tempo").value) || 1.0,
  });
  updateScoreInfo();
  draw();
}

// ─── Note Relationship popup ──────────────────────────────────────────────────
async function openNoteRelPopup(type, t1, t2) {
  const isPoint = (type === "arpeggiate" || Math.abs(t2 - t1) < 0.01);
  const rangeStr = isPoint ? `@${t1.toFixed(3)}s` : `${t1.toFixed(3)}s → ${t2.toFixed(3)}s`;
  const label = type === "glissando" ? "⟿ Glissando" : "⁑ Arpeggiate Chord";
  const html = row("label", `<input id="p-nr-label" type="text" placeholder="optional label" />`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${label} — ${rangeStr}</div>`;
  const res = await showPopup(label, html);
  if (!res) return;
  pushHistory();
  const entry = { type, from: t1, label: document.getElementById("p-nr-label").value.trim() || undefined };
  if (!isPoint) entry.to = t2;
  state.noteRel.push(entry);
  updateScoreInfo(); draw();
}

// ─── Articulation popup ───────────────────────────────────────────────────────
async function openArticulationPopup(type, t1, t2) {
  const isRange = (t2 !== undefined && Math.abs(t2 - t1) >= 0.01);
  const titles = { staccato: "• Staccato", legato: "⌢ Legato", fermata: "𝄐 Fermata", accent: "> Accent" };
  const posStr = isRange ? `${t1.toFixed(3)}s → ${t2.toFixed(3)}s` : `@${t1.toFixed(3)}s`;
  const html = row("label", `<input id="p-art-label" type="text" placeholder="optional label" />`)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${titles[type] || type} — ${posStr}</div>`;
  const res = await showPopup(titles[type] || type, html);
  if (!res) return;
  pushHistory();
  const entry = { type, label: document.getElementById("p-art-label").value.trim() || undefined };
  if (isRange) { entry.from = t1; entry.to = t2; }
  else { entry.t = t1; }
  state.articulations.push(entry);
  updateScoreInfo(); draw();
}

// ─── FX Zone popup ────────────────────────────────────────────────────────────
async function openFxZonePopup(t1, t2) {
  const html = row("fx", `<select id="p-fx" onchange="updateFxParams()">
      <option value="none">none</option>
      <option value="reverb">reverb</option>
      <option value="delay">delay</option>
      <option value="reverb+delay">reverb+delay</option>
      <option value="overdrive">overdrive</option>
      <option value="flanger">flanger</option>
      <option value="pitch">pitch</option>
      <option value="compress">compress</option>
      <option value="eq">eq</option>
    </select>`)
    + `<div id="p-fx-params"></div>`
    + `<div style="font-size:10px;color:#444;margin-top:6px;">applies to base audio ${t1.toFixed(3)}s → ${t2.toFixed(3)}s</div>`;
  const res = await showPopup("◆ FX Zone — base audio range", html);
  if (!res) return;
  const fx = collectFx();
  if (!fx.length) return;
  pushHistory();
  state.fxRanges.push({ from: t1, to: t2, fx });
  updateScoreInfo();
  draw();
}

// ─── Base FX ──────────────────────────────────────────────────────────────────
document.getElementById("base-fx-btn").addEventListener("click", openBaseFxPopup);

async function openBaseFxPopup() {
  const html = row("fx", `<select id="p-fx" onchange="updateFxParams()">
      <option value="none">none</option>
      <option value="reverb">reverb</option>
      <option value="delay">delay</option>
      <option value="reverb+delay">reverb+delay</option>
      <option value="overdrive">overdrive</option>
      <option value="flanger">flanger</option>
      <option value="pitch">pitch</option>
      <option value="compress">compress</option>
      <option value="eq">eq</option>
    </select>`)
    + `<div id="p-fx-params"></div>`;
  const res = await showPopup("Base FX — applied to base audio", html);
  if (!res) return;
  pushHistory();
  state.baseFx = collectFx();
  const label = state.baseFx.length ? state.baseFx.map(f => f.type).join("+") : "none";
  document.getElementById("base-fx-label").textContent = label;
}

// ─── Undo / Redo ──────────────────────────────────────────────────────────────
const redoStack = [];

function _snapshotState() {
  return JSON.stringify({ samples: state.samples, dynamics: state.dynamics, events: state.events, tempo: state.tempo, baseFx: state.baseFx, fxRanges: state.fxRanges, phrases: state.phrases, noteRel: state.noteRel, articulations: state.articulations });
}

function _applySnapshot(snap) {
  const s = JSON.parse(snap);
  state.samples = s.samples;
  state.dynamics = s.dynamics;
  state.events = s.events;
  state.tempo = s.tempo || [];
  state.baseFx = s.baseFx || [];
  state.fxRanges = s.fxRanges || [];
  state.phrases  = s.phrases  || [];
  state.noteRel  = s.noteRel  || [];
  state.articulations = s.articulations || [];
  document.getElementById("base-fx-label").textContent = state.baseFx.length ? state.baseFx.map(f => f.type).join("+") : "none";
}

function pushHistory() {
  state.history.push(_snapshotState());
  if (state.history.length > 50) state.history.shift();
  redoStack.length = 0; // new action clears redo
}

document.getElementById("undo-btn").addEventListener("click", () => {
  if (!state.history.length) return;
  redoStack.push(_snapshotState());
  _applySnapshot(state.history.pop());
  updateScoreInfo();
  draw();
});

document.getElementById("redo-btn").addEventListener("click", () => {
  if (!redoStack.length) return;
  state.history.push(_snapshotState());
  _applySnapshot(redoStack.pop());
  updateScoreInfo();
  draw();
});

// ─── Score info panel ─────────────────────────────────────────────────────────
const infoCollapsed = {};

function toggleInfoSection(key) {
  infoCollapsed[key] = !infoCollapsed[key];
  updateScoreInfo();
}

function _sh(key, label) {
  const open = !infoCollapsed[key];
  const arrow = open ? "\u25bc" : "\u25b6";
  return `<h3 style="cursor:pointer;user-select:none;" onclick="toggleInfoSection('${key}')">${arrow} ${label}</h3>`;
}

function updateScoreInfo() {
  const el = document.getElementById("score-info-panel");
  let html = "";

  // Samples
  const sNames = Object.keys(state.samples);
  html += _sh("samples", `samples (${sNames.length})`);
  if (!infoCollapsed["samples"]) {
    if (sNames.length === 0) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const n of sNames) {
      const s = state.samples[n];
      html += `<div class="info-item"><span style="color:${s.color}">[${n}]</span> ${s.from.toFixed(2)}s → ${s.to.toFixed(2)}s</div>`;
    }
  }

  // Events
  html += _sh("events", `events (${state.events.length})`);
  if (!infoCollapsed["events"]) {
    if (!state.events.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.events.forEach((ev, i) => {
      const col = (state.samples[ev.sample] || {}).color || "#aaa";
      let line = `✎ <span style="color:${col}">${ev.sample}</span> @${ev.t.toFixed(2)}s`;
      line += ` spd:${ev.speed ?? (ev.speeds ? "[…]" : "?")} db:${ev.gain_db}`;
      if (ev.loop) line += " loop";
      if (ev.reverse) line += " rev";
      if (ev.fx && ev.fx.length > 0) line += ` fx:${ev.fx.map(f => f.type).join("+")}`;
      html += `<div class="info-item info-clickable" onclick="editEventAt(${i})">${line}</div>`;
    });
  }

  // Dynamics
  const pts = state.dynamics.filter(d => d.t !== undefined);
  const ranges = state.dynamics.filter(d => d.from !== undefined);
  html += _sh("dynamics", `dynamics (${pts.length} pts, ${ranges.length} ranges)`);
  if (!infoCollapsed["dynamics"]) {
    if (!state.dynamics.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const d of state.dynamics) {
      if (d.t !== undefined) {
        html += `<div class="info-item"><span style="color:${DYNAMIC_COLORS[d.mark]}">${d.mark}</span> @${d.t.toFixed(2)}s</div>`;
      } else {
        const col = d.mark === "crescendo" ? "#337755" : "#775533";
        html += `<div class="info-item"><span style="color:${col}">${d.mark}</span> ${d.from.toFixed(2)}s → ${d.to.toFixed(2)}s</div>`;
      }
    }
  }

  // Tempo
  html += _sh("tempo", `tempo (${state.tempo.length})`);
  if (!infoCollapsed["tempo"]) {
    if (!state.tempo.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const tp of state.tempo) {
      const col = tp.mark === "accelerando" ? "#aa7722" : "#227799";
      html += `<div class="info-item"><span style="color:${col}">${tp.mark}</span> ×${JSON.stringify(tp.factor)} ${tp.from.toFixed(2)}s → ${tp.to.toFixed(2)}s</div>`;
    }
  }

  // FX zones
  html += _sh("fxzones", `fx zones (${state.fxRanges.length})`);
  if (!infoCollapsed["fxzones"]) {
    if (!state.fxRanges.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const fz of state.fxRanges) {
      html += `<div class="info-item"><span style="color:#8844cc">${fz.fx.map(f => f.type).join("+")}</span> ${fz.from.toFixed(2)}s → ${fz.to.toFixed(2)}s</div>`;
    }
  }

  // Slurs (phrases)
  html += _sh("slurs", `slurs (${state.phrases.length})`);
  if (!infoCollapsed["slurs"]) {
    if (!state.phrases.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const ph of state.phrases) {
      const extras = [];
      if (ph.gain_db && ph.gain_db !== 0) extras.push(`${ph.gain_db}dB`);
      if (ph.fade_in)  extras.push(`fi:${(ph.fade_in*100).toFixed(0)}%`);
      if (ph.fade_out) extras.push(`fo:${(ph.fade_out*100).toFixed(0)}%`);
      if (ph.tempo_factor && Math.abs(ph.tempo_factor - 1.0) > 0.001) extras.push(`×${ph.tempo_factor}`);
      html += `<div class="info-item"><span style="color:#8a6abf">${ph.label}</span> ${ph.from.toFixed(2)}s → ${ph.to.toFixed(2)}s${extras.length ? ' <span style="color:#666;font-size:10px;">' + extras.join(' ') + '</span>' : ''}</div>`;
    }
  }

  // Note relationships
  html += _sh("noterel", `note relationships (${state.noteRel.length})`);
  if (!infoCollapsed["noterel"]) {
    if (!state.noteRel.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    const NR_COLORS = { glissando: "#44aadd", arpeggiate: "#44ddaa" };
    for (const nr of state.noteRel) {
      const col = NR_COLORS[nr.type] || "#aaa";
      const range = nr.to ? `${nr.from.toFixed(2)}s → ${nr.to.toFixed(2)}s` : `@${nr.from.toFixed(2)}s`;
      html += `<div class="info-item"><span style="color:${col}">${nr.type}</span> ${range}${nr.label ? ' <span style="color:#666;font-size:10px;">' + nr.label + '</span>' : ''}</div>`;
    }
  }

  // Articulations
  html += _sh("articulations", `articulations (${state.articulations.length})`);
  if (!infoCollapsed["articulations"]) {
    if (!state.articulations.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    const ART_COLORS = { staccato: "#ffaa44", legato: "#44ffaa", fermata: "#ff88cc", accent: "#ff6644" };
    for (const ar of state.articulations) {
      const col = ART_COLORS[ar.type] || "#aaa";
      const pos = ar.t !== undefined ? `@${ar.t.toFixed(2)}s` : `${ar.from.toFixed(2)}s → ${ar.to.toFixed(2)}s`;
      html += `<div class="info-item"><span style="color:${col}">${ar.type}</span> ${pos}${ar.label ? ' <span style="color:#666;font-size:10px;">' + ar.label + '</span>' : ''}</div>`;
    }
  }

  // Sidechain
  html += _sh("sidechain", `sidechain / mix`);
  if (!infoCollapsed["sidechain"]) {
    const scInputStyle = `background:#1a1a1a;border:1px solid #333;color:#aaa;font-family:inherit;font-size:11px;`;
    const keyOpts = sNames.map(n => `<option value="${n}"${state.duckKey.key===n?" selected":""}>${n}</option>`).join("") || `<option value="">—</option>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-db-on"${state.duckBase.enabled?" checked":""}
        onchange="state.duckBase.enabled=this.checked;scUpdate();" title="duck base: reduce base audio when events play">
      <span style="color:#7ab;min-width:68px;">duck base</span>
      dB:<input id="sc-db-amt" type="number" value="${state.duckBase.amount_db}" step="1" style="width:38px;${scInputStyle}" onchange="state.duckBase.amount_db=+this.value;">
      atk:<input id="sc-db-atk" type="number" value="${state.duckBase.attack}" step="0.005" min="0.001" style="width:44px;${scInputStyle}" onchange="state.duckBase.attack=+this.value;">
      rel:<input id="sc-db-rel" type="number" value="${state.duckBase.release}" step="0.05" min="0.01" style="width:44px;${scInputStyle}" onchange="state.duckBase.release=+this.value;">
    </div>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-dk-on"${state.duckKey.enabled?" checked":""}
        onchange="state.duckKey.enabled=this.checked;scUpdate();" title="duck key: one sample ducks entire mix (pump effect)">
      <span style="color:#7ab;min-width:68px;">duck key</span>
      key:<select id="sc-dk-key" style="width:54px;${scInputStyle}" onchange="state.duckKey.key=this.value;">${keyOpts}</select>
      dB:<input id="sc-dk-amt" type="number" value="${state.duckKey.amount_db}" step="1" style="width:38px;${scInputStyle}" onchange="state.duckKey.amount_db=+this.value;">
      atk:<input id="sc-dk-atk" type="number" value="${state.duckKey.attack}" step="0.005" min="0.001" style="width:44px;${scInputStyle}" onchange="state.duckKey.attack=+this.value;">
      rel:<input id="sc-dk-rel" type="number" value="${state.duckKey.release}" step="0.05" min="0.01" style="width:44px;${scInputStyle}" onchange="state.duckKey.release=+this.value;">
    </div>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-am-on"${state.autoMix.enabled?" checked":""}
        onchange="state.autoMix.enabled=this.checked;scUpdate();" title="auto-mix: reduce gain when events overlap">
      <span style="color:#7ab;min-width:68px;">auto-mix</span>
      mode:<select id="sc-am-mode" style="width:54px;${scInputStyle}" onchange="state.autoMix.mode=this.value;">
        <option value="sqrt"${state.autoMix.mode==="sqrt"?" selected":""}>sqrt</option>
        <option value="linear"${state.autoMix.mode==="linear"?" selected":""}>linear</option>
      </select>
    </div>`;
  }

  el.innerHTML = html;
}

function scUpdate() { /* state already updated inline; just a hook for future use */ }
