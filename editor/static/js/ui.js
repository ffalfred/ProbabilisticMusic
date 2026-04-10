// ─── Morphogenics plugin registry (fetched once from /plugins) ────────────────
let _morphoPlugins = [];  // [{type, name, group, params}]

async function _loadMorphoPlugins() {
  try {
    const r = await fetch("/plugins");
    if (r.ok) _morphoPlugins = await r.json();
  } catch (_) {}
}
_loadMorphoPlugins();

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

function showPopup(title, bodyHTML, onShow) {
  popupTitle.innerHTML = title;
  popupBody.innerHTML = bodyHTML;
  overlay.classList.add("visible");
  // Run onShow AFTER the body is in the DOM but BEFORE awaiting OK/Cancel.
  // This is the correct place to initialise widgets that need to look up
  // freshly-rendered elements (e.g. _initFxChain → _renderFxChain).
  if (typeof onShow === "function") onShow();
  return new Promise(res => { popupResolve = res; });
}

function row(label, inputHTML, hint) {
  const hintHtml = hint ? `<span style="font-size:10px;color:#444;margin-left:4px;">${hint}</span>` : "";
  return `<div class="popup-row"><label>${label}</label>${inputHTML}${hintHtml}</div>`;
}

// ─── Probabilistic param widgets ──────────────────────────────────────────────
function paramWidget(id, label, defaultVal, step, min, hint) {
  const minAttr = min != null ? `min="${min}"` : "";
  const hintHtml = hint ? `<span style="font-size:9px;color:#444;margin-left:2px;">${hint}</span>` : "";
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
    </span>${hintHtml}
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

// ─── Classic FX param schema ──────────────────────────────────────────────────
// Single source of truth for classic FX params: render and collect both walk
// this object. Each entry: {key, label, def, step, min?, max?, type?, options?}
// type defaults to 'number'. Use 'select' for enum dropdowns.
const FX_CLASSIC_SCHEMA = {
  reverb:             [{ key: "reverberance", label: "reverberance", def: 100, step: 5,  min: 0, max: 100 },
                       { key: "damping",      label: "damping",      def: 50,  step: 5,  min: 0, max: 100 },
                       { key: "room_scale",   label: "room_scale",   def: 100, step: 5,  min: 0, max: 100 },
                       { key: "pre_delay",    label: "pre_delay_ms", def: 0,   step: 5,  min: 0, max: 500 },
                       { key: "wet",          label: "wet",          def: 0.5, step: 0.05, min: 0, max: 1 }],
  delay:              [{ key: "delay_sec",    label: "delay_sec",    def: 0.3, step: 0.05, min: 0.01 },
                       { key: "feedback",     label: "feedback",     def: 0.6, step: 0.05, min: 0, max: 0.95 },
                       { key: "wet",          label: "wet",          def: 0.5, step: 0.05, min: 0, max: 1 }],
  overdrive:          [{ key: "gain",         label: "gain",         def: 60, step: 5, min: 0, max: 100 },
                       { key: "colour",       label: "colour",       def: 20, step: 5, min: 0, max: 100 },
                       { key: "wet",          label: "wet",          def: 1.0, step: 0.05, min: 0, max: 1 }],
  flanger:            [{ key: "delay_ms",     label: "delay_ms",     def: 0,   step: 1,   min: 0 },
                       { key: "depth_ms",     label: "depth_ms",     def: 6,   step: 1,   min: 0, max: 10 },
                       { key: "speed_hz",     label: "speed_hz",     def: 2.0, step: 0.1, min: 0.1, max: 10 },
                       { key: "feedback",     label: "feedback",     def: 80,  step: 5,   min: -95, max: 95 },
                       { key: "wet",          label: "wet",          def: 0.7, step: 0.05, min: 0, max: 1 }],
  filter:             [{ key: "filter_type",  label: "type",         def: "lp", type: "select",
                         options: [["lp","lowpass"],["hp","highpass"],["bp","bandpass"]] },
                       { key: "cutoff",       label: "cutoff",       def: 1000, step: 100, min: 20 },
                       { key: "resonance",    label: "resonance",    def: 0.0, step: 0.05, min: 0 }],
  chorus:             [{ key: "rate",         label: "rate",         def: 1.5, step: 0.1,  min: 0.1 },
                       { key: "depth",        label: "depth",        def: 0.5, step: 0.05, min: 0 },
                       { key: "wet",          label: "wet",          def: 0.5, step: 0.05, min: 0 }],
  tremolo:            [{ key: "rate",         label: "rate",         def: 5.0, step: 0.5, min: 0.1 },
                       { key: "depth",        label: "depth",        def: 0.5, step: 0.05, min: 0 }],
  pitch:              [{ key: "cents",        label: "cents",        def: 0,   step: 100 }],
  compress:           [{ key: "threshold_db", label: "threshold_db", def: -20,   step: 1 },
                       { key: "ratio",        label: "ratio",        def: 4,     step: 0.5, min: 1 },
                       { key: "attack",       label: "attack",       def: 0.01,  step: 0.005, min: 0.001 },
                       { key: "release",      label: "release",      def: 0.3,   step: 0.05,  min: 0.01 },
                       { key: "makeup_db",    label: "makeup_db",    def: 0,     step: 1 }],
  eq:                 [{ key: "freq_hz",      label: "freq_hz",      def: 1000, step: 50,  min: 20 },
                       { key: "gain_db",      label: "gain_db",      def: 0,    step: 1 },
                       { key: "q",            label: "q",            def: 1.0,  step: 0.1, min: 0.1 }],
  spectral_inversion: [{ key: "low_hz",       label: "low_hz",       def: 20,    step: 10,  min: 0 },
                       { key: "high_hz",      label: "high_hz",      def: 10000, step: 500, min: 20 },
                       { key: "threshold_db", label: "threshold_db", def: -60,   step: 5 },
                       { key: "amount",       label: "amount %",     def: 100,   step: 5, min: 0 },
                       { key: "fft_size",     label: "fft_size",     def: 2048,  type: "select",
                         options: [["512","512"],["1024","1024"],["2048","2048"]] },
                       { key: "dry_wet",      label: "dry/wet %",    def: 100,   step: 5, min: 0 }],
  overtones:          [{ key: "n_harmonics", label: "n_harmonics", def: 3,    step: 1, min: 1, max: 8 },
                       { key: "gain_db",     label: "gain_db",     def: -6,   step: 1 }],
};

const FX_CLASSIC_TYPES = Object.keys(FX_CLASSIC_SCHEMA);

// Build the param spec list for an FX type (classic or morpho)
function _fxParamSpecs(fxType) {
  if (FX_CLASSIC_SCHEMA[fxType]) return FX_CLASSIC_SCHEMA[fxType];
  if (fxType.startsWith("morpho_")) {
    const plug = _morphoPlugins.find(p => p.type === fxType);
    if (!plug) return [];
    return Object.entries(plug.params).map(([key, spec]) => ({
      key,
      label:   spec.label,
      def:     spec.default,
      type:    spec.type === "select" ? "select" :
               spec.type === "int" ? "int" : "float",
      step:    spec.type === "int" ? 1 : 0.1,
      min:     spec.min,
      max:     spec.max,
      options: spec.options ? spec.options.map(o => [o, o]) : null,
    }));
  }
  return [];
}

// Build a default fx object for a given type
function _fxDefaults(fxType) {
  const fx = { type: fxType };
  for (const spec of _fxParamSpecs(fxType)) fx[spec.key] = spec.def;
  return fx;
}

// Read a single param input by id, parsing according to spec type
function _readFxParamInput(id, spec) {
  const el = document.getElementById(id);
  if (!el) return spec.def;
  if (spec.type === "select") return el.value;
  if (spec.type === "int")    return parseInt(el.value);
  return parseFloat(el.value);
}

// ─── FX chain builder (shared by event / FX zone / base FX popups) ──────────
//
// Each FX in the chain renders as a fully editable row: type dropdown,
// inline param inputs, delete button. Clicking + Classic FX / + Morpho FX
// immediately appends a default FX of that scope. Type-changes within a row
// replace its params with the new type's defaults (each FX type has different
// params; cross-type carry-over would be nonsensical).
let _fxChain = [];   // [{type, ...params}]
let _fxCollapsed = []; // parallel bool[] — true means row is minimised

function _initFxChain(existingFx) {
  _fxChain = existingFx ? existingFx.map(fx => ({ ...fx })) : [];
  _fxCollapsed = _fxChain.map(() => false);
  _renderFxChain();
}

function collectFxChain() {
  // Walk every row and read its current input values back into _fxChain so
  // edits made after init propagate to the saved chain.
  _syncRowsToModel();
  return _fxChain.map(fx => ({ ...fx }));
}

// Read all current row inputs into _fxChain (used before any structural edit
// — add/remove/type-change — and at final collect time)
function _syncRowsToModel() {
  _fxChain.forEach((fx, i) => {
    for (const spec of _fxParamSpecs(fx.type)) {
      const id = `p-fxr-${i}-${spec.key}`;
      const el = document.getElementById(id);
      if (el) fx[spec.key] = _readFxParamInput(id, spec);
    }
  });
}

function _renderFxChain() {
  const container = document.getElementById('p-fx-chain');
  if (!container) return;
  if (_fxChain.length === 0) {
    container.innerHTML = '<div style="font-size:10px;color:#444;padding:4px 0;">no FX — click + Classic FX or + Morpho FX below</div>';
    return;
  }
  container.innerHTML = _fxChain.map((fx, i) => _fxRowHTML(fx, i)).join('');
}

// Render a single editable FX row
function _fxRowHTML(fx, idx) {
  const isMorpho = fx.type.startsWith("morpho_");
  const collapsed = !!_fxCollapsed[idx];
  // Type dropdown — listing only types within the same scope
  let typeOpts;
  if (isMorpho) {
    typeOpts = _morphoPlugins.map(p =>
      `<option value="${p.type}"${p.type === fx.type ? " selected" : ""}>${p.name}</option>`).join("");
    if (!typeOpts) typeOpts = `<option value="${fx.type}" selected>${fx.type.replace(/^morpho_/, "")}</option>`;
  } else {
    typeOpts = FX_CLASSIC_TYPES.map(t =>
      `<option value="${t}"${t === fx.type ? " selected" : ""}>${t}</option>`).join("");
  }

  // Param inputs (rendered even when collapsed, but wrapped in a hideable div
  // so that _syncRowsToModel still finds them; collapse only hides visually
  // via display:none on the wrapper)
  const paramHTML = _fxParamSpecs(fx.type).map(spec => {
    const id  = `p-fxr-${idx}-${spec.key}`;
    const val = fx[spec.key] != null ? fx[spec.key] : spec.def;
    let input;
    if (spec.type === "select") {
      const opts = (spec.options || []).map(o => {
        const [v, label] = Array.isArray(o) ? o : [o, String(o)];
        return `<option value="${v}"${String(v) === String(val) ? " selected" : ""}>${label}</option>`;
      }).join("");
      input = `<select id="${id}" style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;font-family:inherit;font-size:11px;padding:2px 4px;">${opts}</select>`;
    } else {
      const minAttr = spec.min != null ? `min="${spec.min}"` : "";
      const maxAttr = spec.max != null ? `max="${spec.max}"` : "";
      const step    = spec.step != null ? spec.step : 0.1;
      input = `<input id="${id}" type="number" value="${val}" step="${step}" ${minAttr} ${maxAttr}
         style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-family:inherit;font-size:11px;" />`;
    }
    return `<div style="display:flex;gap:4px;align-items:center;margin:1px 0;">
      <span style="font-size:10px;color:#666;width:90px;flex:none;">${spec.label}</span>
      ${input}
    </div>`;
  }).join("");

  const chev = collapsed ? "▶" : "▼";
  return `<div style="border:1px solid #222;background:#0d0d0d;padding:4px 6px;margin-bottom:4px;border-radius:2px;">
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:3px;">
      <button type="button" onclick="_toggleFxRowCollapse(${idx})" title="${collapsed ? 'expand' : 'collapse'}"
              style="font-size:10px;color:#888;width:16px;flex:none;border:none;background:none;cursor:pointer;padding:0;">${chev}</button>
      <span style="font-size:10px;color:#555;flex:none;">${idx + 1}.</span>
      <select onchange="_changeFxRowType(${idx}, this.value)"
              style="flex:1;min-width:0;background:#1a1a1a;border:1px solid #333;color:#7ab;font-family:inherit;font-size:11px;padding:2px 4px;">${typeOpts}</select>
      <button type="button" onclick="_removeFxFromChain(${idx})"
              title="remove this FX"
              style="font-size:14px;color:#a66;padding:0 6px;border:none;background:none;cursor:pointer;flex:none;">×</button>
    </div>
    <div style="display:${collapsed ? 'none' : 'block'};">${paramHTML}</div>
  </div>`;
}

function _toggleFxRowCollapse(idx) {
  _syncRowsToModel();
  _fxCollapsed[idx] = !_fxCollapsed[idx];
  _renderFxChain();
}

function _changeFxRowType(idx, newType) {
  // Sync other rows first so their unsaved edits aren't lost
  _syncRowsToModel();
  _fxChain[idx] = _fxDefaults(newType);
  _renderFxChain();
}

function _removeFxFromChain(idx) {
  _syncRowsToModel();
  _fxChain.splice(idx, 1);
  _fxCollapsed.splice(idx, 1);
  _renderFxChain();
}

function _addFxToChain(scope) {
  _syncRowsToModel();
  // Default to the first available type in the chosen scope
  let defaultType;
  if (scope === 'morpho') {
    if (!_morphoPlugins.length) {
      alert("No morphogenics plugins loaded.");
      return;
    }
    defaultType = _morphoPlugins[0].type;
  } else {
    defaultType = FX_CLASSIC_TYPES[0];   // 'reverb'
  }
  _fxChain.push(_fxDefaults(defaultType));
  _fxCollapsed.push(false);
  _renderFxChain();
}

// ─── Sample popup ─────────────────────────────────────────────────────────────
async function openSamplePopup(t1, t2) {
  const trackOpts = state.tracks.length > 1
    ? state.tracks.map((tk, i) => `<option value="${i}">${i}: ${tk.name}</option>`).join('')
    : '<option value="0">0: base</option>';
  const html = row("name", `<input id="p-name" type="text" value="s${Object.keys(state.samples).length + 1}" />`)
    + (state.tracks.length > 1 ? row("track", `<select id="p-track">${trackOpts}</select>`) : "")
    + row("fade in",  `<input id="p-fi" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + row("fade out", `<input id="p-fo" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
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
    + row("lock pitch", `<input id="p-pitchlock" type="checkbox" /> <span style="font-size:10px;color:#666;">time-stretch without changing pitch</span>`)
    + row("speeds", `<input id="p-speeds" type="text" placeholder="0.5, 1.0, 2.0  (layers, overrides speed)" style="font-size:11px;" />`)
    + paramWidget("p-gain",   "gain_db", "0",   "1",    null)
    + row("loop", `<input id="p-loop" type="number" value="0" min="0" step="1" style="width:60px;" title="extra repeats (0 = play once)" />`)
    + row("fade in",  `<input id="p-ev-fi" type="number" value="" min="0" max="50" step="1" style="width:60px;" placeholder="—"> %`,
          "overrides sample default")
    + row("fade out", `<input id="p-ev-fo" type="number" value="" min="0" max="50" step="1" style="width:60px;" placeholder="—"> %`,
          "overrides sample default")
    + row("pitch", `<input id="p-ev-pitch" type="number" value="0" min="-24" max="24" step="0.5" style="width:60px;"> st`,
          "-24 – +24 semitones")
    + row("reverse", `<select id="p-rev-mode" onchange="updateRevWidget()"
        style="width:90px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
        <option value="no">no</option>
        <option value="yes">yes</option>
        <option value="p">~ bernoulli</option>
      </select><span id="p-rev-inputs" style="display:flex;gap:4px;flex:1;"></span>`)
    + row("mix", `<select id="p-mix-mode" style="width:100px;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;"
        onchange="document.getElementById('p-blend-row').style.display=this.value==='sidechain'?'flex':'none';">
        <option value="layer" selected>Layer</option><option value="sidechain">Sidechain</option></select>`)
    + `<div id="p-blend-row" style="display:none;align-items:center;gap:6px;margin-top:2px;">
        <label style="font-size:10px;color:#555;" title="0=all base, 0.5=equal mix, 1=all clip">blend:</label>
        <input id="p-blend" type="range" min="0" max="1" step="0.05" value="0.50" style="flex:1;"
               oninput="document.getElementById('p-blend-val').textContent=parseFloat(this.value).toFixed(2);" />
        <span id="p-blend-val" style="font-size:10px;color:#888;width:28px;">0.50</span>
      </div>`
    + `<div style="margin-top:4px;"><label style="font-size:10px;color:#666;">FX chain:</label>
        <div id="p-fx-chain"></div>
        <div style="display:flex;gap:4px;margin-top:4px;">
          <button type="button" onclick="_addFxToChain('classic')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>
          <button type="button" onclick="_addFxToChain('morpho')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>
        </div></div>`
    + row("time (s)", `<input id="p-t" type="number" value="${t.toFixed(3)}" step="0.01" style="width:90px;" />`);
  const res = await showPopup("▶ Event — place playback", html, () => _initFxChain([]));
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

  const _mixMode = document.getElementById("p-mix-mode")?.value || 'layer';
  const ev = {
    sample,
    t: parseFloat(document.getElementById("p-t").value) || t,
    gain_db: collectParam("p-gain"),
    loop:    parseInt(document.getElementById("p-loop").value) || 0,
    reverse: reverseVal,
    mix_mode: _mixMode,
    ...(_mixMode === 'sidechain' ? { blend: parseFloat(document.getElementById("p-blend")?.value) || 0.5 } : {}),
    fx:      collectFxChain()
  };
  const fiRaw = document.getElementById("p-ev-fi").value.trim();
  const foRaw = document.getElementById("p-ev-fo").value.trim();
  if (fiRaw !== "") ev.fade_in  = Math.max(0, Math.min(0.5, parseFloat(fiRaw) / 100));
  if (foRaw !== "") ev.fade_out = Math.max(0, Math.min(0.5, parseFloat(foRaw) / 100));
  const pitchVal = parseFloat(document.getElementById("p-ev-pitch").value);
  if (!isNaN(pitchVal) && pitchVal !== 0) ev.pitch = pitchVal;
  if (speedsArr.length > 0) ev.speeds = speedsArr;
  else ev.speed = collectParam("p-speed");
  if (document.getElementById("p-pitchlock")?.checked) ev.pitch_lock = true;

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
  const fiVal = ev.fade_in  != null ? Math.round(ev.fade_in  * 100) : "";
  const foVal = ev.fade_out != null ? Math.round(ev.fade_out * 100) : "";
  const html = row("sample", `<select id="p-sample">${sampleOptions}</select>`)
    + paramWidget("p-speed",  "speed",   ev.speed ?? 1.0, "0.1", "0.01")
    + row("lock pitch", `<input id="p-pitchlock" type="checkbox"${ev.pitch_lock ? " checked" : ""} /> <span style="font-size:10px;color:#666;">time-stretch without changing pitch</span>`)
    + row("speeds", `<input id="p-speeds" type="text" value="${speedsVal}" placeholder="0.5, 1.0, 2.0  (layers, overrides speed)" style="font-size:11px;" />`)
    + paramWidget("p-gain",   "gain_db", ev.gain_db ?? -6, "1", null)
    + row("loop", `<input id="p-loop" type="number" value="${ev.loop ?? 0}" min="0" step="1" style="width:60px;" />`)
    + row("fade in",  `<input id="p-ev-fi" type="number" value="${fiVal}" min="0" max="50" step="1" style="width:60px;" placeholder="—"> %`,
          "overrides sample default")
    + row("fade out", `<input id="p-ev-fo" type="number" value="${foVal}" min="0" max="50" step="1" style="width:60px;" placeholder="—"> %`,
          "overrides sample default")
    + row("pitch", `<input id="p-ev-pitch" type="number" value="${ev.pitch ?? 0}" min="-24" max="24" step="0.5" style="width:60px;"> st`,
          "-24 – +24 semitones")
    + row("reverse", `<select id="p-rev-mode" onchange="updateRevWidget()"
        style="width:90px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
        <option value="no"${revDefault==="no"?" selected":""}>no</option>
        <option value="yes"${revDefault==="yes"?" selected":""}>yes</option>
        <option value="p"${revDefault==="p"?" selected":""}>~ bernoulli</option>
      </select><span id="p-rev-inputs" style="display:flex;gap:4px;flex:1;">${revDefault==="p" ? `<input id="p-rev-p" type="number" value="${revP}" min="0" max="1" step="0.05" style="flex:1;" />` : ""}</span>`)
    + row("mix", `<select id="p-mix-mode" style="width:100px;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;"
        onchange="document.getElementById('p-blend-row').style.display=this.value==='sidechain'?'flex':'none';">
        <option value="layer"${(ev.mix_mode||'layer')==='layer'?' selected':''}>Layer</option>
        <option value="sidechain"${ev.mix_mode==='sidechain'?' selected':''}>Sidechain</option></select>`)
    + `<div id="p-blend-row" style="display:${ev.mix_mode==='sidechain'?'flex':'none'};align-items:center;gap:6px;margin-top:2px;">
        <label style="font-size:10px;color:#555;" title="0=all base, 0.5=equal mix, 1=all clip">blend:</label>
        <input id="p-blend" type="range" min="0" max="1" step="0.05" value="${ev.blend ?? 0.50}" style="flex:1;"
               oninput="document.getElementById('p-blend-val').textContent=parseFloat(this.value).toFixed(2);" />
        <span id="p-blend-val" style="font-size:10px;color:#888;width:28px;">${(ev.blend ?? 0.50).toFixed(2)}</span>
      </div>`
    + `<div style="margin-top:4px;"><label style="font-size:10px;color:#666;">FX chain:</label>
        <div id="p-fx-chain"></div>
        <div style="display:flex;gap:4px;margin-top:4px;">
          <button type="button" onclick="_addFxToChain('classic')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>
          <button type="button" onclick="_addFxToChain('morpho')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>
        </div></div>`
    + row("time (s)", `<input id="p-t" type="number" value="${ev.t.toFixed(3)}" step="0.01" style="width:90px;" />`);
  const res = await showPopup("✎ Edit Event", html, () => _initFxChain(ev.fx || []));
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
    mix_mode: document.getElementById("p-mix-mode")?.value || 'layer',
    ...(document.getElementById("p-mix-mode")?.value === 'sidechain'
        ? { blend: parseFloat(document.getElementById("p-blend")?.value) || 0.5 } : {}),
    fx:      collectFxChain()
  };
  const fiRaw2 = document.getElementById("p-ev-fi").value.trim();
  const foRaw2 = document.getElementById("p-ev-fo").value.trim();
  if (fiRaw2 !== "") updated.fade_in  = Math.max(0, Math.min(0.5, parseFloat(fiRaw2) / 100));
  if (foRaw2 !== "") updated.fade_out = Math.max(0, Math.min(0.5, parseFloat(foRaw2) / 100));
  const pitchVal2 = parseFloat(document.getElementById("p-ev-pitch").value);
  if (!isNaN(pitchVal2) && pitchVal2 !== 0) updated.pitch = pitchVal2;
  if (speedsArr.length > 0) updated.speeds = speedsArr;
  else updated.speed = collectParam("p-speed");
  if (document.getElementById("p-pitchlock")?.checked) updated.pitch_lock = true;
  pushHistory();
  state.events[i] = updated;
  state.events.sort((a, b) => a.t - b.t);
  updateScoreInfo();
  draw();
}

// ─── Edit sample ─────────────────────────────────────────────────────────────
async function editSampleAt(name) {
  const s = state.samples[name];
  const fiVal = Math.round((s.fade_in  ?? 0.05) * 100);
  const foVal = Math.round((s.fade_out ?? 0.05) * 100);
  const html = row("name", `<input id="p-name" type="text" value="${name}" />`)
    + row("fade in",  `<input id="p-fi" type="number" value="${fiVal}" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + row("fade out", `<input id="p-fo" type="number" value="${foVal}" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + row("from (s)", `<input id="p-s-from" type="number" value="${s.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-s-to"   type="number" value="${s.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("✎ Edit Sample", html);
  if (!res) return;
  const newName = document.getElementById("p-name").value.trim() || name;
  const fi = Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-fi").value) || 5) / 100));
  const fo = Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-fo").value) || 5) / 100));
  const newFrom = parseFloat(document.getElementById("p-s-from").value);
  const newTo   = parseFloat(document.getElementById("p-s-to").value);
  pushHistory();
  const updated = { ...s, fade_in: fi, fade_out: fo,
    from: isNaN(newFrom) ? s.from : newFrom,
    to:   isNaN(newTo)   ? s.to   : newTo };
  if (newName !== name) {
    delete state.samples[name];
    state.events.forEach(ev => { if (ev.sample === name) ev.sample = newName; });
  }
  state.samples[newName] = updated;
  updateScoreInfo(); draw();
}

// ─── Edit tempo range ─────────────────────────────────────────────────────────
async function editTempoAt(i) {
  const tp = state.tempo[i];
  const curShape = tp.shape || 'ramp';
  const html = row("direction", `<select id="p-tdir">
      <option value="accelerando"${tp.mark==="accelerando"?" selected":""}>accelerando</option>
      <option value="ritardando"${tp.mark==="ritardando"?" selected":""}>ritardando</option>
    </select>`)
    + row("shape", `<select id="p-tshape">
        <option value="ramp"${curShape==='ramp'?' selected':''}>ramp (gradual)</option>
        <option value="step"${curShape==='step'?' selected':''}>step (constant)</option>
      </select> <span style="font-size:10px;color:#666;">ramp = rate interpolates 1.0→factor</span>`)
    + paramWidget("p-tfactor", "end factor", tp.factor ?? 2.0, "0.1", "0.01")
    + row("from (s)", `<input id="p-tp-from" type="number" value="${tp.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-tp-to"   type="number" value="${tp.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("✎ Edit Tempo", html);
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-tp-from").value);
  const newTo   = parseFloat(document.getElementById("p-tp-to").value);
  pushHistory();
  state.tempo[i] = {
    from: isNaN(newFrom) ? tp.from : newFrom,
    to:   isNaN(newTo)   ? tp.to   : newTo,
    mark:   document.getElementById("p-tdir").value,
    factor: collectParam("p-tfactor"),
    shape:  document.getElementById("p-tshape").value,
  };
  updateScoreInfo(); draw();
}

// ─── Edit phrase (slur) ───────────────────────────────────────────────────────
async function editPhraseAt(i) {
  const ph = state.phrases[i];
  const html = row("label",    `<input id="p-phrase-label" type="text" value="${ph.label || ''}" />`)
    + row("gain dB",  `<input id="p-ph-gain"  type="number" value="${ph.gain_db ?? 0}"   step="0.5" style="width:60px;">`, "-20–20")
    + row("fade in",  `<input id="p-ph-fi"    type="number" value="${Math.round((ph.fade_in  ?? 0) * 100)}" min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-ph-fo"    type="number" value="${Math.round((ph.fade_out ?? 0) * 100)}" min="0" max="50" step="1" style="width:60px;"> %`)
    + row("tempo ×",  `<input id="p-ph-tempo" type="number" value="${ph.tempo_factor ?? 1.0}" step="0.05" min="0.1" style="width:60px;"> <span style="font-size:10px;color:#666;">(1.0 = no change)</span>`)
    + row("from (s)", `<input id="p-ph-from" type="number" value="${ph.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-ph-to"   type="number" value="${ph.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("✎ Edit Slur", html);
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-ph-from").value);
  const newTo   = parseFloat(document.getElementById("p-ph-to").value);
  pushHistory();
  state.phrases[i] = {
    from: isNaN(newFrom) ? ph.from : newFrom,
    to:   isNaN(newTo)   ? ph.to   : newTo,
    label:        document.getElementById("p-phrase-label").value.trim() || ph.label,
    gain_db:      parseFloat(document.getElementById("p-ph-gain").value)  || 0,
    fade_in:      Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fi").value)  || 0) / 100)),
    fade_out:     Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fo").value)  || 0) / 100)),
    tempo_factor: parseFloat(document.getElementById("p-ph-tempo").value) || 1.0,
  };
  updateScoreInfo(); draw();
}

// ─── FX zone popup helpers ────────────────────────────────────────────────────
function _fxZoneDefaultFadeS(durationS) {
  // Mirror of src/mixer.py: default 1:10 of segment duration, clamped [0.01, 1.0] s
  return Math.max(0.01, Math.min(1.0, durationS / 10));
}
function _popupSection(title, innerHTML) {
  return `<div class="popup-group">
    <div class="popup-group-title">${title}</div>
    ${innerHTML}
  </div>`;
}
function _fxZoneBodyHTML(t1, t2, fz, scope) {
  const addBtns = `<div class="popup-addfx-row">
      ${scope !== 'morpho'  ? `<button type="button" class="btn-addfx" onclick="_addFxToChain('classic')">+ Classic FX</button>` : ''}
      ${scope !== 'classic' ? `<button type="button" class="btn-addfx" onclick="_addFxToChain('morpho')">+ Morpho FX</button>` : ''}
    </div>`;
  const chainSection = _popupSection("FX chain",
    `<div id="p-fx-chain" class="popup-fx-chain"></div>${addBtns}`);

  const rangeSection = _popupSection("Range",
    `<div class="popup-row">
       <label>from (s)</label>
       <input id="p-fz-from" type="number" value="${t1.toFixed(3)}" step="0.001" min="0" style="flex:none;width:90px;">
     </div>
     <div class="popup-row">
       <label>to (s)</label>
       <input id="p-fz-to" type="number" value="${t2.toFixed(3)}" step="0.001" min="0" style="flex:none;width:90px;">
     </div>`);

  const defS   = _fxZoneDefaultFadeS(t2 - t1);
  const fadeOn = !!(fz && fz.fade);
  const fiCur  = (fz && fz.fade_in_s  != null) ? fz.fade_in_s  : defS;
  const foCur  = (fz && fz.fade_out_s != null) ? fz.fade_out_s : defS;
  const fadeSection = _popupSection("Fade (optional)",
    `<div class="popup-row">
       <label style="width:auto;">
         <input id="p-fz-fade" type="checkbox" ${fadeOn ? 'checked' : ''}
                onchange="document.querySelectorAll('.p-fz-fade-input').forEach(el=>el.disabled=!this.checked);">
         smooth enter/exit
       </label>
     </div>
     <div class="popup-row">
       <label>fade in</label>
       <input class="p-fz-fade-input" id="p-fz-fi" type="number" value="${fiCur.toFixed(3)}"
              min="0" max="5" step="0.01" style="flex:none;width:72px;" ${fadeOn ? '' : 'disabled'}>
       <span style="font-size:10px;color:#666;">s</span>
     </div>
     <div class="popup-row">
       <label>fade out</label>
       <input class="p-fz-fade-input" id="p-fz-fo" type="number" value="${foCur.toFixed(3)}"
              min="0" max="5" step="0.01" style="flex:none;width:72px;" ${fadeOn ? '' : 'disabled'}>
       <span style="font-size:10px;color:#666;">s</span>
     </div>
     <div style="font-size:10px;color:#444;padding-left:98px;">default 1:10 of zone duration</div>`);

  return chainSection + rangeSection + fadeSection;
}
function _collectFxZoneFade() {
  const cb = document.getElementById("p-fz-fade");
  if (!cb || !cb.checked) return null;
  return {
    fade: true,
    fade_in_s:  Math.max(0, parseFloat(document.getElementById("p-fz-fi").value) || 0),
    fade_out_s: Math.max(0, parseFloat(document.getElementById("p-fz-fo").value) || 0),
  };
}

// ─── Edit FX zone ─────────────────────────────────────────────────────────────
async function editFxZoneAt(i) {
  const fz = state.fxRanges[i];
  const res = await showPopup("✎ Edit FX Zone",
    _fxZoneBodyHTML(fz.from, fz.to, fz, 'all'),
    () => _initFxChain(fz.fx || []));
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-fz-from").value);
  const newTo   = parseFloat(document.getElementById("p-fz-to").value);
  const fade    = _collectFxZoneFade();
  pushHistory();
  state.fxRanges[i] = {
    from: isNaN(newFrom) ? fz.from : newFrom,
    to:   isNaN(newTo)   ? fz.to   : newTo,
    fx: collectFxChain(),
    ...(fade || {}) };
  updateScoreInfo(); draw();
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

// ─── Edit existing dynamic mark ───────────────────────────────────────────────
async function openMarkEditPopup(idx) {
  const d = state.dynamics[idx];
  const marks = ["ppp","pp","p","mp","mf","f","ff","fff"];
  const current = d.mark || d.marking || "mp";
  const opts = marks.map(m =>
    `<option value="${m}" ${m === current ? "selected" : ""} style="color:${DYNAMIC_COLORS[m]}">${m}</option>`).join("");
  const html = row("mark", `<select id="p-mark">${opts}</select>`)
    + row("at (s)", `<input id="p-mk-t" type="number" value="${d.t.toFixed(3)}" step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("• Edit mark", html);
  if (!res) return;
  const newT = parseFloat(document.getElementById("p-mk-t").value);
  pushHistory();
  state.dynamics[idx] = { t: isNaN(newT) ? d.t : newT, mark: document.getElementById("p-mark").value };
  updateScoreInfo();
  draw();
}

async function openRangeEditPopup(idx) {
  const d = state.dynamics[idx];
  const current = d.mark || d.marking || "crescendo";
  const html = row("type", `<select id="p-rtype">
      <option value="crescendo" ${current === "crescendo" ? "selected" : ""}>crescendo</option>
      <option value="decrescendo" ${current === "decrescendo" ? "selected" : ""}>decrescendo</option>
    </select>`)
    + row("from (s)", `<input id="p-rg-from" type="number" value="${d.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-rg-to"   type="number" value="${d.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("~ Edit range", html);
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-rg-from").value);
  const newTo   = parseFloat(document.getElementById("p-rg-to").value);
  pushHistory();
  state.dynamics[idx] = {
    from: isNaN(newFrom) ? d.from : newFrom,
    to:   isNaN(newTo)   ? d.to   : newTo,
    mark: document.getElementById("p-rtype").value };
  updateScoreInfo();
  draw();
}

// ─── Tempo popup ──────────────────────────────────────────────────────────────
async function openTempoPopup(t1, t2) {
  const html = row("direction", `<select id="p-tdir">
      <option value="accelerando">accelerando</option>
      <option value="ritardando">ritardando</option>
    </select>`)
    + row("shape", `<select id="p-tshape">
        <option value="ramp" selected>ramp (gradual)</option>
        <option value="step">step (constant)</option>
      </select> <span style="font-size:10px;color:#666;">ramp = rate interpolates 1.0→factor</span>`)
    + paramWidget("p-tfactor", "end factor", "2.0", "0.1", "0.01")
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s<br>ramp: rate goes 1.0 → factor across the range<br>step: rate stays at factor throughout</div>`;
  const res = await showPopup("⏱ Tempo — accelerando/ritardando", html);
  if (!res) return;
  pushHistory();
  state.tempo.push({
    from: t1,
    to: t2,
    mark:   document.getElementById("p-tdir").value,
    factor: collectParam("p-tfactor"),
    shape:  document.getElementById("p-tshape").value,
  });
  updateScoreInfo();
  draw();
}

// ─── Phrase popup ─────────────────────────────────────────────────────────────
async function openPhrasePopup(t1, t2) {
  const n = state.phrases.length + 1;
  const html = row("label",    `<input id="p-phrase-label" type="text" value="slur ${n}" />`)
    + row("gain dB",  `<input id="p-ph-gain"  type="number" value="0"   step="0.5" style="width:60px;">`, "-20–20")
    + row("fade in",  `<input id="p-ph-fi"    type="number" value="0"   min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-ph-fo"    type="number" value="0"   min="0" max="50" step="1" style="width:60px;"> %`)
    + row("tempo ×",  `<input id="p-ph-tempo" type="number" value="1.0" step="0.05" min="0.1" style="width:60px;"> <span style="font-size:10px;color:#666;">(1.0 = no change; affects event timing only)</span>`)
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
    + (type === "glissando"
        ? row("from pitch", `<input id="p-nr-fp" type="number" value="0" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
          + row("to pitch", `<input id="p-nr-tp" type="number" value="2" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
        : "")
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${label} — ${rangeStr}</div>`;
  const res = await showPopup(label, html);
  if (!res) return;
  pushHistory();
  const entry = { type, from: t1, label: document.getElementById("p-nr-label").value.trim() || undefined };
  if (!isPoint) entry.to = t2;
  if (type === "glissando") {
    entry.from_pitch = parseFloat(document.getElementById("p-nr-fp").value) || 0;
    entry.to_pitch   = parseFloat(document.getElementById("p-nr-tp").value) || 2;
  }
  state.noteRel.push(entry);
  updateScoreInfo(); draw();
}

// ─── Articulation popup ───────────────────────────────────────────────────────
async function openArticulationPopup(type, t1, t2) {
  const isRange = (t2 !== undefined && Math.abs(t2 - t1) >= 0.01);
  const titles = { staccato: "• Staccato", legato: "⌢ Legato", fermata: "𝄐 Fermata", accent: "> Accent" };
  const descs  = {
    staccato: "Short punchy cut — 20 ms attack, then silence.",
    accent:   "Boosts the attack of the note by 2×.",
    fermata:  "Extends the note by holding its tail.",
    legato:   "Smooth connection — notes flow into each other.",
  };
  const posStr = isRange ? `${t1.toFixed(3)}s → ${t2.toFixed(3)}s` : `@${t1.toFixed(3)}s`;
  const silenceRow = (!isRange && type === 'staccato')
    ? row("silence (s)", `<input id="p-art-silence" type="number" value="0.07" min="0.01" max="2" step="0.01" style="width:60px;">`)
    : '';
  const fermataRow = (type === 'fermata')
    ? row("tail (s)", `<input id="p-art-hold" type="number" value="2" min="0.1" max="10" step="0.1" style="width:60px;">`)
    : '';
  const html = row("label", `<input id="p-art-label" type="text" placeholder="optional label" />`)
    + silenceRow
    + fermataRow
    + `<div style="font-size:10px;color:#555;margin-top:4px;">${descs[type] || ""}</div>`
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${titles[type] || type} — ${posStr}</div>`;
  const res = await showPopup(titles[type] || type, html);
  if (!res) return;
  pushHistory();
  const entry = { type, label: document.getElementById("p-art-label").value.trim() || undefined };
  if (isRange) { entry.from = t1; entry.to = t2; }
  else { entry.t = t1; }
  if (type === 'staccato') {
    const silEl = document.getElementById("p-art-silence");
    if (silEl) entry.silence_s = parseFloat(silEl.value) || 0.07;
  }
  if (type === 'fermata') {
    const holdEl = document.getElementById("p-art-hold");
    if (holdEl) entry.hold_s = parseFloat(holdEl.value) || 2.0;
  }
  state.articulations.push(entry);
  updateScoreInfo(); draw();
}

// ─── Edit existing note relationship ─────────────────────────────────────────
async function editNoteRelAt(i) {
  const nr = state.noteRel[i];
  const isPoint = !nr.to || Math.abs((nr.to || nr.from) - nr.from) < 0.01;
  const label = nr.type === "glissando" ? "⟿ Glissando" : "⁑ Arpeggiate Chord";
  const html = row("label", `<input id="p-nr-label" type="text" value="${nr.label || ''}" placeholder="optional label" />`)
    + (nr.type === "glissando"
        ? row("from pitch", `<input id="p-nr-fp" type="number" value="${nr.from_pitch || 0}" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
          + row("to pitch", `<input id="p-nr-tp" type="number" value="${nr.to_pitch || 2}" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
        : "")
    + row("from (s)", `<input id="p-nr-from" type="number" value="${nr.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + (!isPoint ? row("to (s)", `<input id="p-nr-to" type="number" value="${(nr.to||nr.from).toFixed(3)}" step="0.001" min="0" style="width:90px;">`) : '');
  const res = await showPopup("✎ Edit " + label, html);
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-nr-from").value);
  const newTo   = !isPoint ? parseFloat(document.getElementById("p-nr-to").value) : NaN;
  pushHistory();
  const entry = { ...nr,
    from: isNaN(newFrom) ? nr.from : newFrom,
    label: document.getElementById("p-nr-label").value.trim() || undefined };
  if (!isPoint) entry.to = isNaN(newTo) ? nr.to : newTo;
  if (nr.type === "glissando") {
    entry.from_pitch = parseFloat(document.getElementById("p-nr-fp").value) || 0;
    entry.to_pitch   = parseFloat(document.getElementById("p-nr-tp").value) || 2;
  }
  state.noteRel[i] = entry;
  updateScoreInfo(); draw();
}

// ─── Edit existing articulation ───────────────────────────────────────────────
async function editArticulationAt(i) {
  const ar = state.articulations[i];
  const isRange = ar.from !== undefined;
  const titles  = { staccato: "• Staccato", legato: "⌢ Legato", fermata: "𝄐 Fermata", accent: "> Accent" };
  const silenceRow = (!isRange && ar.type === 'staccato')
    ? row("silence (s)", `<input id="p-art-silence" type="number" value="${ar.silence_s ?? 0.07}" min="0.01" max="2" step="0.01" style="width:60px;">`)
    : '';
  const fermataRow = (ar.type === 'fermata')
    ? row("tail (s)", `<input id="p-art-hold" type="number" value="${ar.hold_s ?? 2}" min="0.1" max="10" step="0.1" style="width:60px;">`)
    : '';
  const html = row("label", `<input id="p-art-label" type="text" value="${ar.label || ''}" placeholder="optional label" />`)
    + silenceRow + fermataRow
    + (isRange
        ? row("from (s)", `<input id="p-ar-from" type="number" value="${ar.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
          + row("to (s)", `<input id="p-ar-to"   type="number" value="${ar.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`)
        : row("at (s)", `<input id="p-ar-t" type="number" value="${ar.t.toFixed(3)}" step="0.001" min="0" style="width:90px;">`));
  const res = await showPopup("✎ Edit " + (titles[ar.type] || ar.type), html);
  if (!res) return;
  pushHistory();
  const updated = { ...ar, label: document.getElementById("p-art-label").value.trim() || undefined };
  if (ar.type === 'staccato') {
    const silEl = document.getElementById("p-art-silence");
    if (silEl) updated.silence_s = parseFloat(silEl.value) || 0.07;
  }
  if (ar.type === 'fermata') {
    const holdEl = document.getElementById("p-art-hold");
    if (holdEl) updated.hold_s = parseFloat(holdEl.value) || 2.0;
  }
  if (isRange) {
    const newFrom = parseFloat(document.getElementById("p-ar-from").value);
    const newTo   = parseFloat(document.getElementById("p-ar-to").value);
    if (!isNaN(newFrom)) updated.from = newFrom;
    if (!isNaN(newTo))   updated.to   = newTo;
  } else {
    const newT = parseFloat(document.getElementById("p-ar-t").value);
    if (!isNaN(newT)) updated.t = newT;
  }
  state.articulations[i] = updated;
  updateScoreInfo(); draw();
}

// ─── History panel delete / duplicate helpers ─────────────────────────────────
function _muteHist(type, i) {
  pushHistory();
  const arr = type === 'event'        ? state.events
            : type === 'dynamic'      ? state.dynamics
            : type === 'tempo'        ? state.tempo
            : type === 'fxzone'       ? state.fxRanges
            : type === 'phrase'       ? state.phrases
            : type === 'noteRel'      ? state.noteRel
            : type === 'articulation' ? state.articulations : null;
  if (arr && arr[i]) arr[i].muted = !arr[i].muted;
  updateScoreInfo(); draw();
  // Auto re-render so mute takes effect immediately
  _autoReRender();
}

function _autoReRender() {
  const mode = (document.getElementById("play-mode-select") || {}).value || "source";
  if (mode === "source" || mode === "raw") return;
  if (typeof clearMixBuf === 'function') clearMixBuf();
  if (typeof togglePlay === 'function') togglePlay();
}

function _delHist(type, i) {
  pushHistory();
  if      (type === 'event')        state.events.splice(i, 1);
  else if (type === 'dynamic')      state.dynamics.splice(i, 1);
  else if (type === 'tempo')        state.tempo.splice(i, 1);
  else if (type === 'fxzone')       state.fxRanges.splice(i, 1);
  else if (type === 'phrase')       state.phrases.splice(i, 1);
  else if (type === 'noteRel')      state.noteRel.splice(i, 1);
  else if (type === 'articulation') state.articulations.splice(i, 1);
  updateScoreInfo(); draw();
}

function _dupHist(type, i) {
  pushHistory();
  const SHIFT = 0.1;
  if (type === 'event') {
    const e = { ...state.events[i] }; e.t = +(e.t + SHIFT).toFixed(4);
    state.events.splice(i + 1, 0, e);
  } else if (type === 'dynamic') {
    const d = { ...state.dynamics[i] };
    if (d.t !== undefined) d.t = +(d.t + SHIFT).toFixed(4);
    else { d.from = +(d.from + SHIFT).toFixed(4); d.to = +(d.to + SHIFT).toFixed(4); }
    state.dynamics.splice(i + 1, 0, d);
  } else if (type === 'tempo') {
    const t = { ...state.tempo[i] };
    t.from = +(t.from + SHIFT).toFixed(4); t.to = +(t.to + SHIFT).toFixed(4);
    state.tempo.splice(i + 1, 0, t);
  } else if (type === 'fxzone') {
    const f = JSON.parse(JSON.stringify(state.fxRanges[i]));
    f.from = +(f.from + SHIFT).toFixed(4); f.to = +(f.to + SHIFT).toFixed(4);
    state.fxRanges.splice(i + 1, 0, f);
  } else if (type === 'phrase') {
    const p = { ...state.phrases[i] };
    p.from = +(p.from + SHIFT).toFixed(4); p.to = +(p.to + SHIFT).toFixed(4);
    state.phrases.splice(i + 1, 0, p);
  }
  updateScoreInfo(); draw();
}

// ─── FX Zone popup ────────────────────────────────────────────────────────────
async function openFxZonePopup(t1, t2, scope) {
  scope = scope || 'all';
  const title = scope === 'morpho'  ? '✦ Morpho Zone'
              : scope === 'classic' ? '◆ Classic FX Zone'
              : '◆ FX Zone';
  const res = await showPopup(title,
    _fxZoneBodyHTML(t1, t2, null, scope),
    () => _initFxChain([]));
  if (!res) return;
  const fx = collectFxChain();
  if (!fx.length) return;
  const newFrom = parseFloat(document.getElementById("p-fz-from").value);
  const newTo   = parseFloat(document.getElementById("p-fz-to").value);
  const fade    = _collectFxZoneFade();
  pushHistory();
  state.fxRanges.push({
    from: isNaN(newFrom) ? t1 : newFrom,
    to:   isNaN(newTo)   ? t2 : newTo,
    fx,
    ...(fade || {})
  });
  updateScoreInfo();
  draw();
}

// ─── Base FX ──────────────────────────────────────────────────────────────────
async function openBaseFxPopup(scope) {
  scope = scope || 'all';
  const title = scope === 'morpho' ? '✦ Morpho Base FX'
              : scope === 'classic' ? '◆ Classic Base FX'
              : 'Base FX — applied to base audio';
  const html = `<div><label style="font-size:10px;color:#666;">FX chain:</label>
      <div id="p-fx-chain"></div>
      <div style="display:flex;gap:4px;margin-top:4px;">
        ${scope !== 'morpho' ? '<button type="button" onclick="_addFxToChain(\'classic\')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>' : ''}
        ${scope !== 'classic' ? '<button type="button" onclick="_addFxToChain(\'morpho\')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>' : ''}
      </div></div>`;
  const res = await showPopup(title, html, () => _initFxChain(state.baseFx || []));
  if (!res) return;
  pushHistory();
  state.baseFx = collectFxChain();
  _updateBaseFxLabel();
}

function _updateBaseFxLabel() {
  const label = (state.baseFx && state.baseFx.length)
    ? state.baseFx.map(f => f.type.replace(/^morpho_/, '')).join(' + ')
    : 'none';
  const el = document.getElementById("base-fx-label");
  if (el) el.textContent = label;
}

// Wire the two new base-FX buttons
document.addEventListener('DOMContentLoaded', () => {
  const classicBtn = document.getElementById("base-fx-classic-btn");
  const morphoBtn  = document.getElementById("base-fx-morpho-btn");
  const clearBtn   = document.getElementById("base-fx-clear-btn");
  if (classicBtn) classicBtn.addEventListener("click", () => openBaseFxPopup('classic'));
  if (morphoBtn)  morphoBtn.addEventListener("click",  () => openBaseFxPopup('morpho'));
  if (clearBtn)   clearBtn.addEventListener("click",   () => {
    if (!state.baseFx || !state.baseFx.length) return;
    pushHistory();
    state.baseFx = [];
    _updateBaseFxLabel();
  });
  _updateBaseFxLabel();
});

// ─── Undo / Redo ──────────────────────────────────────────────────────────────
const redoStack = [];

function _snapshotState() {
  return JSON.stringify({ samples: state.samples, dynamics: state.dynamics, events: state.events, tempo: state.tempo, baseFx: state.baseFx, fxRanges: state.fxRanges, phrases: state.phrases, noteRel: state.noteRel, articulations: state.articulations, duckBase: state.duckBase, duckKey: state.duckKey, autoMix: state.autoMix });
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
  if (s.duckBase) Object.assign(state.duckBase, s.duckBase);
  if (s.duckKey)  Object.assign(state.duckKey,  s.duckKey);
  if (s.autoMix)  Object.assign(state.autoMix,  s.autoMix);
  _updateBaseFxLabel();
}

function pushHistory() {
  state.history.push(_snapshotState());
  if (state.history.length > 50) state.history.shift();
  redoStack.length = 0;
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

// ─── Score info panel (History) ───────────────────────────────────────────────
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
  const el = document.getElementById("history-body") || document.getElementById("score-info-panel");
  let html = ``;

  // Samples
  const sNames = Object.keys(state.samples);
  html += _sh("samples", `samples (${sNames.length})`);
  if (!infoCollapsed["samples"]) {
    if (sNames.length === 0) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    for (const n of sNames) {
      const s = state.samples[n];
      html += `<div class="info-item info-clickable" onclick="editSampleAt('${n.replace(/'/g,"\\'")}')"><span style="color:${s.color}">[${n}]</span> ${s.from.toFixed(2)}s → ${s.to.toFixed(2)}s</div>`;
    }
  }

  // ─ shared helper: wrap an info-item with edit/dup/del action buttons ─────────
  const _ha = (editCall, dupType, delType, idx, content, isMuted) => {
    const actS = `font-size:8px;padding:0 3px;line-height:1.4;border-radius:2px;cursor:pointer;`;
    const muteIcon = isMuted ? '🔇' : '🔊';
    const muteTitle = isMuted ? 'Unmute' : 'Mute';
    const muteBtn = `<button onclick="event.stopPropagation();_muteHist('${delType}',${idx})" style="${actS}color:${isMuted?'#744':'#474'};border:1px solid ${isMuted?'#522':'#343'};" title="${muteTitle}">${muteIcon}</button>`;
    const dupBtn = dupType ? `<button onclick="event.stopPropagation();_dupHist('${dupType}',${idx})" style="${actS}color:#557;border:1px solid #334;" title="Duplicate">⎘</button>` : '';
    const delBtn = `<button onclick="event.stopPropagation();_delHist('${delType}',${idx})" style="${actS}color:#744;border:1px solid #522;" title="Delete">✕</button>`;
    const rowStyle = isMuted ? 'display:flex;align-items:center;gap:2px;opacity:0.35;' : 'display:flex;align-items:center;gap:2px;';
    return `<div class="info-item" style="${rowStyle}"><span class="info-clickable" style="flex:1;${isMuted?'text-decoration:line-through;':''}" onclick="${editCall}">${content}</span>${muteBtn}${dupBtn}${delBtn}</div>`;
  };

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
      html += _ha(`editEventAt(${i})`, 'event', 'event', i, line, !!ev.muted);
    });
  }

  // Dynamics
  const pts = state.dynamics.filter(d => d.t !== undefined);
  const ranges = state.dynamics.filter(d => d.from !== undefined);
  html += _sh("dynamics", `dynamics (${pts.length} pts, ${ranges.length} ranges)`);
  if (!infoCollapsed["dynamics"]) {
    if (!state.dynamics.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.dynamics.forEach((d, i) => {
      if (d.t !== undefined) {
        const dm0 = d.mark || d.marking || '?';
        html += _ha(`openMarkEditPopup(${i})`, 'dynamic', 'dynamic', i,
          `<span style="color:${DYNAMIC_COLORS[dm0]}">${dm0}</span> @${d.t.toFixed(2)}s`, !!d.muted);
      } else {
        const dm0 = d.mark || d.marking || '?';
        const col = dm0 === "crescendo" ? "#337755" : "#775533";
        html += _ha(`openRangeEditPopup(${i})`, 'dynamic', 'dynamic', i,
          `<span style="color:${col}">${dm0}</span> ${d.from.toFixed(2)}s → ${d.to.toFixed(2)}s`, !!d.muted);
      }
    });
  }

  // Tempo
  html += _sh("tempo", `tempo (${state.tempo.length})`);
  if (!infoCollapsed["tempo"]) {
    if (!state.tempo.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.tempo.forEach((tp, i) => {
      const col = tp.mark === "accelerando" ? "#aa7722" : "#227799";
      html += _ha(`editTempoAt(${i})`, 'tempo', 'tempo', i,
        `<span style="color:${col}">${tp.mark}</span> ×${JSON.stringify(tp.factor)} ${tp.from.toFixed(2)}s → ${tp.to.toFixed(2)}s`, !!tp.muted);
    });
  }

  // FX zones
  html += _sh("fxzones", `fx zones (${state.fxRanges.length})`);
  if (!infoCollapsed["fxzones"]) {
    if (!state.fxRanges.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.fxRanges.forEach((fz, i) => {
      html += _ha(`editFxZoneAt(${i})`, 'fxzone', 'fxzone', i,
        `<span style="color:#8844cc">${fz.fx.map(f => f.type).join("+")}</span> ${fz.from.toFixed(2)}s → ${fz.to.toFixed(2)}s`, !!fz.muted);
    });
  }

  // Slurs (phrases)
  html += _sh("slurs", `slurs (${state.phrases.length})`);
  if (!infoCollapsed["slurs"]) {
    if (!state.phrases.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.phrases.forEach((ph, i) => {
      const extras = [];
      if (ph.gain_db && ph.gain_db !== 0) extras.push(`${ph.gain_db}dB`);
      if (ph.fade_in)  extras.push(`fi:${(ph.fade_in*100).toFixed(0)}%`);
      if (ph.fade_out) extras.push(`fo:${(ph.fade_out*100).toFixed(0)}%`);
      if (ph.tempo_factor && Math.abs(ph.tempo_factor - 1.0) > 0.001) extras.push(`×${ph.tempo_factor}`);
      html += _ha(`editPhraseAt(${i})`, 'phrase', 'phrase', i,
        `<span style="color:#8a6abf">${ph.label}</span> ${ph.from.toFixed(2)}s → ${ph.to.toFixed(2)}s${extras.length ? ' <span style="color:#666;font-size:10px;">' + extras.join(' ') + '</span>' : ''}`, !!ph.muted);
    });
  }

  // Note relationships
  html += _sh("noterel", `note relationships (${state.noteRel.length})`);
  if (!infoCollapsed["noterel"]) {
    if (!state.noteRel.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    const NR_COLORS = { glissando: "#44aadd", arpeggiate: "#44ddaa" };
    state.noteRel.forEach((nr, i) => {
      const col = NR_COLORS[nr.type] || "#aaa";
      const range = nr.to ? `${nr.from.toFixed(2)}s → ${nr.to.toFixed(2)}s` : `@${nr.from.toFixed(2)}s`;
      html += _ha(`editNoteRelAt(${i})`, null, 'noteRel', i,
        `<span style="color:${col}">${nr.type}</span> ${range}${nr.label ? ' <span style="color:#666;font-size:10px;">' + nr.label + '</span>' : ''}`, !!nr.muted);
    });
  }

  // Articulations
  html += _sh("articulations", `articulations (${state.articulations.length})`);
  if (!infoCollapsed["articulations"]) {
    if (!state.articulations.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    const ART_COLORS = { staccato: "#ffaa44", legato: "#44ffaa", fermata: "#ff88cc", accent: "#ff6644" };
    state.articulations.forEach((ar, i) => {
      const col = ART_COLORS[ar.type] || "#aaa";
      const pos = ar.t !== undefined ? `@${ar.t.toFixed(2)}s` : `${ar.from.toFixed(2)}s → ${ar.to.toFixed(2)}s`;
      html += _ha(`editArticulationAt(${i})`, null, 'articulation', i,
        `<span style="color:${col}">${ar.type}</span> ${pos}${ar.label ? ' <span style="color:#666;font-size:10px;">' + ar.label + '</span>' : ''}`, !!ar.muted);
    });
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
        <option value="inverse"${state.autoMix.mode==="inverse"?" selected":""}>inverse</option>
      </select>
    </div>`;
  }

  el.innerHTML = html;
}

function scUpdate() { /* state already updated inline; just a hook for future use */ }

