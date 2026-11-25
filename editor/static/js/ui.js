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
// Existing values may be a number, a [lo, hi] range, a {distribution:"gaussian",
// mean, std} object, or another distribution object the widget can't edit.
// The latter is kept verbatim ("keep" mode) unless the user switches mode.
const _paramKeep = {};   // id → original non-editable value

function paramWidget(id, label, defaultVal, step, min, hint) {
  const minAttr = min != null ? `min="${min}"` : "";
  const hintHtml = hint ? `<span style="font-size:9px;color:#444;margin-left:2px;">${hint}</span>` : "";
  delete _paramKeep[id];
  let mode = "fixed", inputs;
  const v = defaultVal;
  if (Array.isArray(v) && v.length === 2 && v.every(x => typeof x === "number")) {
    mode = "range";
    inputs = `<input id="${id}-lo" type="number" value="${v[0]}" step="0.05" style="flex:1;" placeholder="min" />
              <span style="color:#444;align-self:center;">–</span>
              <input id="${id}-hi" type="number" value="${v[1]}" step="0.05" style="flex:1;" placeholder="max" />`;
  } else if (v && typeof v === "object" && !Array.isArray(v) && v.distribution === "gaussian"
             && typeof v.mean === "number" && typeof v.std === "number") {
    mode = "gauss";
    inputs = `<input id="${id}-mean" type="number" value="${v.mean}" step="0.05" style="flex:1;" placeholder="mean" />
              <span style="color:#444;align-self:center;">±</span>
              <input id="${id}-std"  type="number" value="${v.std}"  step="0.01" min="0" style="flex:1;" placeholder="std" />`;
  } else if (v != null && typeof v === "object") {
    mode = "keep";
    _paramKeep[id] = v;
    inputs = `<input type="text" value="${escapeHtml(JSON.stringify(v))}" readonly style="flex:1;color:#666;" title="kept as-is — pick another mode to replace" />`;
  } else {
    inputs = `<input id="${id}-v" type="number" value="${escapeHtml(v)}" step="${step}" ${minAttr} style="flex:1;" />`;
  }
  const sel = m => (m === mode ? " selected" : "");
  return `<div class="popup-row">
    <label>${label}</label>
    <select id="${id}-mode" onchange="updateParamWidget('${id}')"
      style="width:80px;flex:none;font-size:11px;background:#1a1a1a;border:1px solid #333;color:#888;font-family:inherit;">
      ${mode === "keep" ? `<option value="keep" selected>… keep</option>` : ""}
      <option value="fixed"${sel("fixed")}>= fixed</option>
      <option value="range"${sel("range")}>↔ range</option>
      <option value="gauss"${sel("gauss")}>~ gauss</option>
    </select>
    <span id="${id}-inputs" style="display:flex;gap:4px;flex:1;">
      ${inputs}
    </span>${hintHtml}
  </div>`;
}

function updateParamWidget(id) {
  const mode = document.getElementById(id + "-mode").value;
  const el   = document.getElementById(id + "-inputs");
  // Seed the new mode from whatever the current inputs hold
  const num  = sid => parseFloat((document.getElementById(id + sid) || {}).value);
  let val = num("-v");
  if (isNaN(val)) val = num("-mean");
  if (isNaN(val)) { const lo = num("-lo"), hi = num("-hi"); if (!isNaN(lo) && !isNaN(hi)) val = (lo + hi) / 2; }
  if (isNaN(val)) val = 1;
  if (mode === "keep") {
    el.innerHTML = `<input type="text" value="${escapeHtml(JSON.stringify(_paramKeep[id]))}" readonly style="flex:1;color:#666;" />`;
  } else if (mode === "fixed") {
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
  if (mode === "keep") return _paramKeep[id];
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
  reverb:             [{ key: "reverberance", label: "reverberance", def: 50,  step: 5,  min: 0, max: 100 },
                       { key: "damping",      label: "damping",      def: 50,  step: 5,  min: 0, max: 100 },
                       { key: "room_scale",   label: "room_scale",   def: 100, step: 5,  min: 0, max: 100 },
                       { key: "pre_delay",    label: "pre_delay_ms", def: 0,   step: 5,  min: 0, max: 500 },
                       // dry = level of the original, wet = level of the reverb (1 = as loud as the original)
                       { key: "dry",          label: "dry",          def: 1.0, step: 0.05, min: 0, max: 1 },
                       { key: "wet",          label: "wet",          def: 0.5, step: 0.05, min: 0, max: 1 }],
  delay:              [{ key: "delay_sec",    label: "delay_sec",    def: 0.3, step: 0.05, min: 0.01 },
                       // each echo = feedback × the previous one; wet = level of the first echo
                       { key: "feedback",     label: "feedback",     def: 0.6, step: 0.05, min: 0, max: 0.95 },
                       { key: "dry",          label: "dry",          def: 1.0, step: 0.05, min: 0, max: 1 },
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
// ─── Automation: a numeric FX setting can be a curve ─────────────────────────
// Shown as text "0s: 200, 2s: 3000, 5s: 400" — seconds from the start of what
// the effect processes (the event, the zone, the track or the whole output).
function _isCurve(v) { return v && typeof v === "object" && Array.isArray(v.curve); }
function _curveText(v) { return v.curve.map(([t, x]) => `${+t}s: ${+x}`).join(", "); }
function _parseCurve(text) {
  const pts = String(text).split(/[,;]/).map(p => p.trim()).filter(Boolean).map(p => {
    const m = p.match(/^(-?[\d.]+)\s*s?\s*[:=]\s*(-?[\d.]+)$/);
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
  });
  if (!pts.length || pts.some(p => !p || p.some(isNaN))) return null;
  return { curve: pts.sort((a, b) => a[0] - b[0]) };
}
function _fxNumberInputHTML(id, spec, val) {
  const style = "flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-family:inherit;font-size:11px;";
  if (_isCurve(val))
    return `<input id="${id}" data-curve="1" type="text" value="${escapeHtml(_curveText(val))}"
       placeholder="0s: 200, 2s: 3000" title="seconds: value, … — straight lines between points" style="${style}color:#c9b6ff;" />`;
  const minAttr = spec.min != null ? `min="${spec.min}"` : "";
  const maxAttr = spec.max != null ? `max="${spec.max}"` : "";
  const step    = spec.step != null ? spec.step : 0.1;
  const v = (typeof val === "number" || typeof val === "string") ? val : spec.def;
  return `<input id="${id}" type="number" value="${v}" step="${step}" ${minAttr} ${maxAttr} style="${style}" />`;
}
function _toggleFxCurve(id, idx, key) {
  _syncRowsToModel();
  const fx = _fxChain[idx];
  const spec = _fxParamSpecs(fx.type).find(s => s.key === key) || { def: 0 };
  const cur = fx[key];
  if (_isCurve(cur)) fx[key] = cur.curve[0][1];                         // back to one value
  else {
    const v = (typeof cur === "number" && !isNaN(cur)) ? cur : spec.def;
    fx[key] = { curve: [[0, v], [2, v]] };                              // a starting curve to edit
  }
  _renderFxChain();
}

function _readFxParamInput(id, spec) {
  const el = document.getElementById(id);
  if (!el) return spec.def;
  if (el.dataset && el.dataset.curve === "1") {
    const c = _parseCurve(el.value);
    if (c) return c;
    alert(`Couldn't read the curve for "${spec.label}": use  seconds: value, …  (e.g. 0s: 200, 2s: 3000). Keeping its first value.`);
    const first = parseFloat(String(el.value).split(/[:=]/)[1]);
    return isNaN(first) ? spec.def : first;
  }
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
    // Freq targeting (global, not per-type)
    const ffEl = document.getElementById(`p-fxr-${i}-freq_from`);
    const ftEl = document.getElementById(`p-fxr-${i}-freq_to`);
    const ff = ffEl ? parseFloat(ffEl.value) : NaN;
    const ft = ftEl ? parseFloat(ftEl.value) : NaN;
    if (!isNaN(ff) && ff > 0) fx.freq_from = ff; else delete fx.freq_from;
    if (!isNaN(ft) && ft > 0) fx.freq_to   = ft; else delete fx.freq_to;
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
  if (typeof _initCurveCanvases === "function") _initCurveCanvases(container);
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
      input = _fxNumberInputHTML(id, spec, val)
        + `<button type="button" onclick="_toggleFxCurve('${id}', ${idx}, '${spec.key}')"
             title="automate: let this setting change over time (points: seconds: value)"
             style="flex:none;font-size:11px;padding:0 5px;border:1px solid #333;background:${_isCurve(val) ? '#2a2040' : '#1a1a1a'};color:#a8c;cursor:pointer;">~</button>`;
    }
    return `<div style="display:flex;gap:4px;align-items:center;margin:1px 0;">
      <span style="font-size:10px;color:#666;width:90px;flex:none;">${spec.label}</span>
      ${input}
    </div>` + (spec.type !== "select" && _isCurve(val) && typeof _curveCanvasHTML === "function"
               ? _curveCanvasHTML(id, spec) : "");
  }).join("");

  // Freq targeting — global to all FX types, rendered outside per-type params
  const freqFrom = fx.freq_from != null ? fx.freq_from : '';
  const freqTo   = fx.freq_to   != null ? fx.freq_to   : '';
  const freqHTML = `<div style="border-top:1px solid #282828;margin-top:4px;padding-top:4px;">
    <div style="display:flex;gap:4px;align-items:center;margin:1px 0;">
      <span style="font-size:10px;color:#557;width:90px;flex:none;">freq range</span>
      <input id="p-fxr-${idx}-freq_from" type="number" value="${freqFrom}" placeholder="20"
             min="20" max="20000" step="100"
             style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-size:11px;">
      <span style="font-size:10px;color:#666;">–</span>
      <input id="p-fxr-${idx}-freq_to" type="number" value="${freqTo}" placeholder="20000"
             min="20" max="20000" step="100"
             style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-size:11px;">
      <span style="font-size:10px;color:#666;">Hz</span>
    </div>
  </div>`;

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
    <div style="display:${collapsed ? 'none' : 'block'};">${paramHTML}${freqHTML}</div>
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

// ─── Fade shape ───────────────────────────────────────────────────────────────
// smooth (equal-power) is the default; others are stored as `fade_curve`.
const _FADE_SHAPES = [["smooth", "smooth"], ["linear", "linear"], ["exponential", "exponential"], ["s-curve", "S-curve"]];
function _fadeShapeRow(id, cur, inheritLabel) {
  const v = cur || (inheritLabel ? "" : "smooth");
  const opts = (inheritLabel ? `<option value=""${v === "" ? " selected" : ""}>${inheritLabel}</option>` : "")
    + _FADE_SHAPES.map(([k, lab]) => `<option value="${k}"${k === v ? " selected" : ""}>${lab}</option>`).join("");
  return row("fade shape", `<select id="${id}" style="width:auto;">${opts}</select>`);
}
function _setFadeShape(entry, id, keepDefault) {
  const v = document.getElementById(id)?.value ?? "";
  if (!v || (v === "smooth" && !keepDefault)) delete entry.fade_curve; else entry.fade_curve = v;
}

// ─── What a sample carries from its track ────────────────────────────────────
// A track shapes its sound in this order; a sample can carry any of the
// stages. Default (no `include` field): the FX chain only. Mute is never carried.
const _SAMPLE_STAGES = [["fx", "FX chain"], ["fx_regions", "FX regions"], ["automation", "automation"], ["gain", "gain"]];

function _sampleIncludeRow(s) {
  const inc = !s || s.include == null ? ["fx"]
            : s.include === "all" ? _SAMPLE_STAGES.map(x => x[0])
            : s.include === "none" ? [] : [].concat(s.include);
  const boxes = _SAMPLE_STAGES.map(([k, label]) =>
    `<label style="font-size:10px;color:#aaa;margin-right:6px;white-space:nowrap;">
       <input type="checkbox" class="p-s-inc" value="${k}"${inc.includes(k) ? " checked" : ""}> ${label}</label>`).join("");
  return row("carry from track", `<span style="display:inline-flex;flex-wrap:wrap;">${boxes}</span>`);
}

function _collectSampleInclude(entry) {
  const inc = [...document.querySelectorAll(".p-s-inc")].filter(el => el.checked).map(el => el.value);
  if (inc.length === 1 && inc[0] === "fx") delete entry.include;          // the default
  else if (inc.length === _SAMPLE_STAGES.length) entry.include = "all";
  else if (!inc.length) entry.include = "none";
  else entry.include = inc;
}

// ─── Sample popup ─────────────────────────────────────────────────────────────
async function openSamplePopup(t1, t2) {
  const trackOpts = state.tracks.length > 1
    ? state.tracks.map((tk, i) => `<option value="${i}">${i}: ${escapeHtml(tk.name)}</option>`).join('')
    : '<option value="0">0: base</option>';
  let n = Object.keys(state.samples).length + 1;
  while (state.samples["s" + n]) n++;   // default name must not collide after deletions
  const html = row("name", `<input id="p-name" type="text" value="s${n}" />`)
    + (state.tracks.length > 1 ? row("track", `<select id="p-track">${trackOpts}</select>`) : "")
    + row("fade in",  `<input id="p-fi" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + row("fade out", `<input id="p-fo" type="number" value="5" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + _fadeShapeRow("p-fshape", null)
    + _sampleIncludeRow(null)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">range: ${t1.toFixed(3)}s → ${t2.toFixed(3)}s</div>`;
  const res = await showPopup("[ Sample ] — define range", html);
  if (!res) return;
  const name = document.getElementById("p-name").value.trim() || ("s" + Date.now());
  if (state.samples[name]) { alert(`A sample named "${name}" already exists — choose another name.`); return; }
  const fi = Math.max(0, Math.min(0.5, _numOr(document.getElementById("p-fi").value, 5) / 100));
  const fo = Math.max(0, Math.min(0.5, _numOr(document.getElementById("p-fo").value, 5) / 100));
  const trackEl = document.getElementById("p-track");
  const trackIdx = trackEl ? (parseInt(trackEl.value) || 0) : 0;
  const color = nextColor();
  pushHistory();
  state.samples[name] = { from: t1, to: t2, color, fade_in: fi, fade_out: fo, track: trackIdx };
  _collectSampleInclude(state.samples[name]);
  _setFadeShape(state.samples[name], "p-fshape");
  updateScoreInfo();
  draw();
}

// ─── Event popup ──────────────────────────────────────────────────────────────
async function openEventPopup(t) {
  const sampleOptions = Object.keys(state.samples).map(n =>
    `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("") || `<option value="">— no samples —</option>`;
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
    + _fadeShapeRow("p-ev-fshape", null, "— sample's")
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
  { const s0 = state.samples[Object.keys(state.samples)[0]];
    setCurveContext(s0 ? s0.to - s0.from : 2, s0 ? s0.from : null); }
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
    t: _numOr(document.getElementById("p-t").value, t),
    gain_db: collectParam("p-gain"),
    loop:    parseInt(document.getElementById("p-loop").value) || 0,
    reverse: reverseVal,
    mix_mode: _mixMode,
    ...(_mixMode === 'sidechain' ? { blend: _numOr(document.getElementById("p-blend")?.value, 0.5) } : {}),
    fx:      collectFxChain()
  };
  const fiRaw = document.getElementById("p-ev-fi").value.trim();
  const foRaw = document.getElementById("p-ev-fo").value.trim();
  if (fiRaw !== "") ev.fade_in  = Math.max(0, Math.min(0.5, parseFloat(fiRaw) / 100));
  if (foRaw !== "") ev.fade_out = Math.max(0, Math.min(0.5, parseFloat(foRaw) / 100));
  _setFadeShape(ev, "p-ev-fshape", true);
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
    `<option value="${escapeHtml(n)}"${n === ev.sample ? " selected" : ""}>${escapeHtml(n)}</option>`).join("");
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
    + _fadeShapeRow("p-ev-fshape", ev.fade_curve, "— sample's")
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
  { const s0 = state.samples[ev.sample], sp = (typeof ev.speed === "number" && ev.speed > 0) ? ev.speed : 1;
    const len = s0 ? (s0.to - s0.from) / sp * ((ev.loop || 0) + 1) : 2;
    setCurveContext(len, s0 && sp === 1 && !ev.loop && !ev.reverse ? s0.from : null); }
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
    t: _numOr(document.getElementById("p-t").value, ev.t),
    gain_db: collectParam("p-gain"),
    loop:    parseInt(document.getElementById("p-loop").value) || 0,
    reverse: reverseVal,
    mix_mode: document.getElementById("p-mix-mode")?.value || 'layer',
    ...(document.getElementById("p-mix-mode")?.value === 'sidechain'
        ? { blend: _numOr(document.getElementById("p-blend")?.value, 0.5) } : {}),
    fx:      collectFxChain()
  };
  const fiRaw2 = document.getElementById("p-ev-fi").value.trim();
  const foRaw2 = document.getElementById("p-ev-fo").value.trim();
  if (fiRaw2 !== "") updated.fade_in  = Math.max(0, Math.min(0.5, parseFloat(fiRaw2) / 100));
  if (foRaw2 !== "") updated.fade_out = Math.max(0, Math.min(0.5, parseFloat(foRaw2) / 100));
  _setFadeShape(updated, "p-ev-fshape", true);
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
  const html = row("name", `<input id="p-name" type="text" value="${escapeHtml(name)}" />`)
    + row("fade in",  `<input id="p-fi" type="number" value="${fiVal}" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + row("fade out", `<input id="p-fo" type="number" value="${foVal}" min="0" max="50" step="1" style="width:60px;"> %`, "of clip length")
    + _fadeShapeRow("p-fshape", s.fade_curve)
    + _sampleIncludeRow(s)
    + row("from (s)", `<input id="p-s-from" type="number" value="${s.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-s-to"   type="number" value="${s.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("✎ Edit Sample", html);
  if (!res) return;
  const newName = document.getElementById("p-name").value.trim() || name;
  if (newName !== name && state.samples[newName]) {
    alert(`A sample named "${newName}" already exists — rename refused.`);
    return;
  }
  const fi = Math.max(0, Math.min(0.5, _numOr(document.getElementById("p-fi").value, 5) / 100));
  const fo = Math.max(0, Math.min(0.5, _numOr(document.getElementById("p-fo").value, 5) / 100));
  const newFrom = parseFloat(document.getElementById("p-s-from").value);
  const newTo   = parseFloat(document.getElementById("p-s-to").value);
  pushHistory();
  const updated = { ...s, fade_in: fi, fade_out: fo,
    from: isNaN(newFrom) ? s.from : newFrom,
    to:   isNaN(newTo)   ? s.to   : newTo };
  _collectSampleInclude(updated);
  _setFadeShape(updated, "p-fshape");
  if (newName !== name) {
    delete state.samples[name];
    state.events.forEach(ev => { if (ev.sample === name) ev.sample = newName; });
    if (state.duckKey.key === name) state.duckKey.key = newName;
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
  const html = row("label",    `<input id="p-phrase-label" type="text" value="${escapeHtml(ph.label || '')}" />`)
    + row("gain dB",  `<input id="p-ph-gain"  type="number" value="${ph.gain_db ?? 0}"   step="0.5" style="width:60px;">`, "-20–20")
    + row("fade in",  `<input id="p-ph-fi"    type="number" value="${Math.round((ph.fade_in  ?? 0) * 100)}" min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-ph-fo"    type="number" value="${Math.round((ph.fade_out ?? 0) * 100)}" min="0" max="50" step="1" style="width:60px;"> %`)
    + _fadeShapeRow("p-ph-fshape", ph.fade_curve)
    + row("tempo ×",  `<input id="p-ph-tempo" type="number" value="${ph.tempo_factor ?? 1.0}" step="0.05" min="0.1" style="width:60px;"> <span style="font-size:10px;color:#666;">(1.0 = no change)</span>`)
    + row("from (s)", `<input id="p-ph-from" type="number" value="${ph.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
    + row("to (s)",   `<input id="p-ph-to"   type="number" value="${ph.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`);
  const res = await showPopup("✎ Edit Slur", html);
  if (!res) return;
  const newFrom = parseFloat(document.getElementById("p-ph-from").value);
  const newTo   = parseFloat(document.getElementById("p-ph-to").value);
  pushHistory();
  state.phrases[i] = {
    ...ph,                                            // keeps mute and other fields
    from: isNaN(newFrom) ? ph.from : newFrom,
    to:   isNaN(newTo)   ? ph.to   : newTo,
    label:        document.getElementById("p-phrase-label").value.trim() || ph.label,
    gain_db:      parseFloat(document.getElementById("p-ph-gain").value)  || 0,
    fade_in:      Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fi").value)  || 0) / 100)),
    fade_out:     Math.max(0, Math.min(0.5, (parseFloat(document.getElementById("p-ph-fo").value)  || 0) / 100)),
    tempo_factor: parseFloat(document.getElementById("p-ph-tempo").value) || 1.0,
  };
  _setFadeShape(state.phrases[i], "p-ph-fshape");
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
     <div class="popup-row">
       <label>shape</label>
       <select class="p-fz-fade-input" id="p-fz-fshape" style="flex:none;" ${fadeOn ? '' : 'disabled'}>
         ${_FADE_SHAPES.map(([k, lab]) => `<option value="${k}"${k === ((fz && fz.fade_curve) || 'smooth') ? ' selected' : ''}>${lab}</option>`).join('')}
       </select>
     </div>
     <div style="font-size:10px;color:#444;padding-left:98px;">default 1:10 of zone duration</div>`);

  const isOut = !!(fz && fz.target === "output");
  const targetSection = _popupSection("Applies to",
    `<div class="popup-row">
       <select id="p-fz-target" style="flex:none;">
         <option value="source"${isOut ? "" : " selected"}>the source</option>
         <option value="output"${isOut ? " selected" : ""}>the whole output</option>
       </select>
     </div>
     <div style="font-size:10px;color:#555;">source: the base audio only, before events are added.
       whole output: everything — source and events — after tempo changes.</div>`);

  return chainSection + targetSection + rangeSection + fadeSection;
}
function _collectFxZoneTarget() {
  return document.getElementById("p-fz-target")?.value === "output" ? { target: "output" } : {};
}
function _collectFxZoneFade() {
  const cb = document.getElementById("p-fz-fade");
  if (!cb || !cb.checked) return null;
  return {
    fade: true,
    fade_in_s:  Math.max(0, parseFloat(document.getElementById("p-fz-fi").value) || 0),
    fade_out_s: Math.max(0, parseFloat(document.getElementById("p-fz-fo").value) || 0),
    ...((v => v && v !== "smooth" ? { fade_curve: v } : {})(document.getElementById("p-fz-fshape")?.value)),
  };
}

// ─── Edit FX zone ─────────────────────────────────────────────────────────────
async function editFxZoneAt(i) {
  const fz = state.fxRanges[i];
  setCurveContext(fz.to - fz.from, fz.from);
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
    ...(fade || {}),
    ..._collectFxZoneTarget(),
    ...(fz.muted ? { muted: true } : {}),
    ...(fz.label ? { label: fz.label } : {}) };
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
    + row("gain dB",  `<input id="p-ph-gain"  type="number" value="2"   step="0.5" style="width:60px;">`, "-20–20")
    + row("fade in",  `<input id="p-ph-fi"    type="number" value="10"  min="0" max="50" step="1" style="width:60px;"> %`)
    + row("fade out", `<input id="p-ph-fo"    type="number" value="15"  min="0" max="50" step="1" style="width:60px;"> %`)
    + _fadeShapeRow("p-ph-fshape", null)
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
  _setFadeShape(state.phrases[state.phrases.length - 1], "p-ph-fshape");
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
    + _freqTargetRow(null)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${label} — ${rangeStr}</div>`;
  const res = await showPopup(label, html);
  if (!res) return;
  pushHistory();
  const entry = { type, from: t1, label: document.getElementById("p-nr-label").value.trim() || undefined };
  if (!isPoint) entry.to = t2;
  if (type === "glissando") {
    entry.from_pitch = _numOr(document.getElementById("p-nr-fp").value, 0);
    entry.to_pitch   = _numOr(document.getElementById("p-nr-tp").value, 2);
  }
  _collectFreqTarget(entry);
  state.noteRel.push(entry);
  updateScoreInfo(); draw();
}

// ─── Articulation popup ───────────────────────────────────────────────────────
// ─── Shared freq-targeting row for articulations / note-relationships ────────
function _freqTargetRow(obj) {
  const ff = (obj && obj.freq_from != null) ? obj.freq_from : '';
  const ft = (obj && obj.freq_to   != null) ? obj.freq_to   : '';
  return `<div style="display:flex;gap:4px;align-items:center;margin:4px 0;">
    <span style="font-size:10px;color:#557;width:90px;flex:none;">freq range</span>
    <input id="p-art-freq-from" type="number" value="${ff}" placeholder="20"
           min="20" max="20000" step="100"
           style="flex:none;width:64px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-size:11px;">
    <span style="font-size:10px;color:#666;">–</span>
    <input id="p-art-freq-to" type="number" value="${ft}" placeholder="20000"
           min="20" max="20000" step="100"
           style="flex:none;width:64px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:2px 4px;font-size:11px;">
    <span style="font-size:10px;color:#666;">Hz</span>
  </div>`;
}
function _collectFreqTarget(entry) {
  const ff = parseFloat(document.getElementById("p-art-freq-from")?.value);
  const ft = parseFloat(document.getElementById("p-art-freq-to")?.value);
  if (!isNaN(ff) && ff > 0) entry.freq_from = ff; else delete entry.freq_from;
  if (!isNaN(ft) && ft > 0) entry.freq_to   = ft; else delete entry.freq_to;
}

// Shared fields for a new or edited articulation. Target "event" shapes the
// events the mark covers; "mix" shapes everything sounding then (source + events).
const _ART_TITLES = { staccato: "• Staccato", legato: "⌢ Legato", fermata: "𝄐 Fermata", accent: "> Accent" };
const _ART_DESCS = {
  event: {
    staccato: "The marked event plays only its first 'keep' seconds, then is cut short.",
    accent:   "The marked event's first 50 ms are louder.",
    legato:   "Each marked event rings on until the next event starts, then fades as it enters.",
    fermata:  "The marked event's last moment is held for 'hold' seconds. Nothing else moves.",
  },
  mix: {
    staccato: "Everything is cut: after 'keep', silence (a point) or until the next attack (a range).",
    accent:   "Everything is louder at the mark (a point) or at each attack in the range.",
    legato:   "At the mark / each attack in the range, the sound before it rings on across it.",
    fermata:  "The whole piece waits: the sound at the mark is held for 'hold' seconds, then everything resumes.",
  },
};

function _articulationFields(type, isRange, ar) {
  ar = ar || {};
  const tgt = ar.target === "mix" ? "mix" : "event";
  const num = (id, v, min, max, step) =>
    `<input id="${id}" type="number" value="${v}" min="${min}" max="${max}" step="${step}" style="width:60px;">`;
  let h = row("target", `<select id="p-art-target" onchange="_artTargetSync('${type}', ${isRange})">
      <option value="event"${tgt === "event" ? " selected" : ""}>event</option>
      <option value="mix"${tgt === "mix" ? " selected" : ""}>whole mix</option></select>`);
  if (type === "staccato") h += row("keep (s)", num("p-art-keep", ar.keep_s ?? 0.15, 0.01, 10, 0.01), "how much of the start plays");
  if (type === "staccato" && !isRange) h += `<div class="art-mix-only">${row("silence (s)", num("p-art-silence", ar.silence_s ?? 0.07, 0.01, 2, 0.01), "whole mix: length of the cut")}</div>`;
  if (type === "accent") h += row("boost (dB)", num("p-art-boost", ar.boost_db ?? 6, 0, 24, 0.5));
  if (type === "fermata") h += row("hold (s)", num("p-art-hold", ar.hold_s ?? 2, 0.1, 30, 0.1));
  if (isRange && type !== "fermata") h += `<div class="art-mix-only">${row("every (s)", `<input id="p-art-every" type="number" value="${ar.every_s ?? ""}" min="0.02" max="10" step="0.05" placeholder="attacks" style="width:60px;">`, "blank = at detected attacks")}</div>`;
  h += _freqTargetRow(ar);
  h += `<div id="p-art-desc" style="font-size:10px;color:#555;margin-top:4px;"></div>`;
  return h;
}

function _artTargetSync(type, isRange) {
  const tgt = document.getElementById("p-art-target")?.value || "event";
  document.querySelectorAll("#popup-body .art-mix-only, .art-mix-only").forEach(el => {
    el.style.display = tgt === "mix" ? "" : "none";
  });
  const d = document.getElementById("p-art-desc");
  if (d) d.textContent = (_ART_DESCS[tgt] || {})[type] || "";
}

function _collectArticulationFields(type, entry) {
  const tgt = document.getElementById("p-art-target")?.value || "event";
  if (tgt === "mix") entry.target = "mix"; else delete entry.target;
  const val = id => parseFloat(document.getElementById(id)?.value);
  const set = (key, v, keep) => { if (!isNaN(v)) entry[key] = v; else if (!keep) delete entry[key]; };
  if (type === "staccato") { set("keep_s", val("p-art-keep")); set("silence_s", val("p-art-silence")); }
  if (type === "accent")   set("boost_db", val("p-art-boost"));
  if (type === "fermata")  set("hold_s", val("p-art-hold"));
  const every = val("p-art-every");
  if (!isNaN(every) && every > 0 && tgt === "mix") entry.every_s = every; else delete entry.every_s;
  _collectFreqTarget(entry);
}

async function openArticulationPopup(type, t1, t2) {
  const isRange = (t2 !== undefined && Math.abs(t2 - t1) >= 0.01);
  const posStr = isRange ? `${t1.toFixed(3)}s → ${t2.toFixed(3)}s` : `@${t1.toFixed(3)}s`;
  const html = row("label", `<input id="p-art-label" type="text" placeholder="optional label" />`)
    + _articulationFields(type, isRange, null)
    + `<div style="font-size:10px;color:#444;margin-top:4px;">${_ART_TITLES[type] || type} — ${posStr}</div>`;
  const res = await showPopup(_ART_TITLES[type] || type, html, () => _artTargetSync(type, isRange));
  if (!res) return;
  pushHistory();
  const entry = { type, label: document.getElementById("p-art-label").value.trim() || undefined };
  if (isRange) { entry.from = t1; entry.to = t2; }
  else { entry.t = t1; }
  _collectArticulationFields(type, entry);
  state.articulations.push(entry);
  updateScoreInfo(); draw();
}

// ─── Edit existing note relationship ─────────────────────────────────────────
async function editNoteRelAt(i) {
  const nr = state.noteRel[i];
  const isPoint = !nr.to || Math.abs((nr.to || nr.from) - nr.from) < 0.01;
  const label = nr.type === "glissando" ? "⟿ Glissando" : "⁑ Arpeggiate Chord";
  const html = row("label", `<input id="p-nr-label" type="text" value="${escapeHtml(nr.label || '')}" placeholder="optional label" />`)
    + (nr.type === "glissando"
        ? row("from pitch", `<input id="p-nr-fp" type="number" value="${nr.from_pitch ?? 0}" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
          + row("to pitch", `<input id="p-nr-tp" type="number" value="${nr.to_pitch ?? 2}" min="-24" max="24" step="0.5" style="width:60px;"> st`, "-24 – +24")
        : "")
    + _freqTargetRow(nr)
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
    entry.from_pitch = _numOr(document.getElementById("p-nr-fp").value, 0);
    entry.to_pitch   = _numOr(document.getElementById("p-nr-tp").value, 2);
  }
  _collectFreqTarget(entry);
  state.noteRel[i] = entry;
  updateScoreInfo(); draw();
}

// ─── Edit existing articulation ───────────────────────────────────────────────
async function editArticulationAt(i) {
  const ar = state.articulations[i];
  const isRange = ar.from !== undefined;
  const html = row("label", `<input id="p-art-label" type="text" value="${escapeHtml(ar.label || '')}" placeholder="optional label" />`)
    + _articulationFields(ar.type, isRange, ar)
    + (isRange
        ? row("from (s)", `<input id="p-ar-from" type="number" value="${ar.from.toFixed(3)}" step="0.001" min="0" style="width:90px;">`)
          + row("to (s)", `<input id="p-ar-to"   type="number" value="${ar.to.toFixed(3)}"   step="0.001" min="0" style="width:90px;">`)
        : row("at (s)", `<input id="p-ar-t" type="number" value="${ar.t.toFixed(3)}" step="0.001" min="0" style="width:90px;">`));
  const res = await showPopup("✎ Edit " + (_ART_TITLES[ar.type] || ar.type), html, () => _artTargetSync(ar.type, isRange));
  if (!res) return;
  pushHistory();
  const updated = { ...ar, label: document.getElementById("p-art-label").value.trim() || undefined };
  _collectArticulationFields(ar.type, updated);
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

// Re-render after an edit: if a rendered mix is playing, restart it from the
// same score position with the new render; otherwise just drop the stale buffer.
function _autoReRender() {
  const mode = (document.getElementById("play-mode-select") || {}).value || "source";
  if (mode === "source" || mode === "raw") return;
  const wasPlaying = typeof isMixPlaying === 'function' && isMixPlaying();
  if (wasPlaying) { state.currentTime = realToScore(mixCurrentTime()); stopMix(); }
  if (typeof clearMixBuf === 'function') clearMixBuf();
  if (!wasPlaying) return;
  if      (mode === "mix")    renderAndPlay();
  else if (mode === "score")  renderScoreAndPlay();
  else if (mode === "interp") renderInterpAndPlay();
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
  setCurveContext(t2 - t1, t1);
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
    ...(fade || {}),
    ..._collectFxZoneTarget()
  });
  updateScoreInfo();
  draw();
}

// ─── Base FX ──────────────────────────────────────────────────────────────────
async function openBaseFxPopup(scope, which) {
  scope = scope || 'all';
  const output = which === 'output';
  const key = output ? 'fxGlobal' : 'baseFx';
  const title = output ? 'Output FX — applied to the whole output (source + events)'
              : scope === 'morpho' ? '✦ Morpho Base FX'
              : scope === 'classic' ? '◆ Classic Base FX'
              : 'Base FX — applied to base audio';
  const html = `<div><label style="font-size:10px;color:#666;">FX chain:</label>
      <div id="p-fx-chain"></div>
      <div style="display:flex;gap:4px;margin-top:4px;">
        ${scope !== 'morpho' ? '<button type="button" onclick="_addFxToChain(\'classic\')" style="font-size:10px;padding:2px 6px;">+ Classic FX</button>' : ''}
        ${scope !== 'classic' ? '<button type="button" onclick="_addFxToChain(\'morpho\')" style="font-size:10px;padding:2px 6px;">+ Morpho FX</button>' : ''}
      </div></div>`;
  setCurveContext(state.durationReal || state.duration || 10, 0);
  const res = await showPopup(title, html, () => _initFxChain(state[key] || []));
  if (!res) return;
  pushHistory();
  state[key] = collectFxChain();
  _updateBaseFxLabel();
  _updateOutputFxLabel();
}

function _updateOutputFxLabel() {
  const el = document.getElementById("output-fx-label");
  if (el) el.textContent = (state.fxGlobal && state.fxGlobal.length)
    ? state.fxGlobal.map(f => f.type.replace(/^morpho_/, '')).join(' + ') : 'none';
  const tb = document.getElementById("timing-btn");
  if (tb) tb.textContent = (state.silenceStart || state.silenceEnd)
    ? `⏱ lead ${+(state.silenceStart || 0).toFixed(2)}s · tail ${+(state.silenceEnd || 0).toFixed(2)}s`
    : '⏱ Lead / tail';
}

// Lead-in (events start later; the source plays from 0) and silence after the piece
async function openTimingPopup() {
  const html = row("lead-in (s)", `<input id="p-lead" type="number" value="${state.silenceStart || 0}" min="0" max="600" step="0.1" style="width:70px;">`,
                   "events start this much later; the source plays from 0")
    + row("tail (s)", `<input id="p-tail" type="number" value="${state.silenceEnd || 0}" min="0" max="600" step="0.1" style="width:70px;">`,
          "silence added after the piece");
  const res = await showPopup("⏱ Lead-in / tail silence", html);
  if (!res) return;
  pushHistory();
  state.silenceStart = Math.max(0, parseFloat(document.getElementById("p-lead").value) || 0);
  state.silenceEnd   = Math.max(0, parseFloat(document.getElementById("p-tail").value) || 0);
  _updateOutputFxLabel();
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
  // Output FX (fx_global) and lead-in / tail
  const oClassic = document.getElementById("output-fx-classic-btn");
  const oMorpho  = document.getElementById("output-fx-morpho-btn");
  const oClear   = document.getElementById("output-fx-clear-btn");
  const timing   = document.getElementById("timing-btn");
  if (oClassic) oClassic.addEventListener("click", () => openBaseFxPopup('classic', 'output'));
  if (oMorpho)  oMorpho.addEventListener("click",  () => openBaseFxPopup('morpho', 'output'));
  if (oClear)   oClear.addEventListener("click",   () => {
    if (!state.fxGlobal || !state.fxGlobal.length) return;
    pushHistory();
    state.fxGlobal = [];
    _updateOutputFxLabel();
  });
  if (timing)   timing.addEventListener("click", openTimingPopup);
  _updateOutputFxLabel();
});

// ─── Undo / Redo ──────────────────────────────────────────────────────────────
const redoStack = [];

// Waveform peaks are kept out of history snapshots (large, never edited) and
// restored by file path from this cache, filled whenever a snapshot is taken.
const _trackWaveforms = {};

function _snapshotTracks() {
  return (state.tracks || []).map(tk => {
    const { waveform, ...rest } = tk;
    if (waveform && tk.path) _trackWaveforms[tk.path] = waveform;
    return rest;
  });
}

function _snapshotState() {
  return JSON.stringify({ samples: state.samples, dynamics: state.dynamics, events: state.events, tempo: state.tempo, baseFx: state.baseFx, fxRanges: state.fxRanges, fxGlobal: state.fxGlobal, silenceStart: state.silenceStart, silenceEnd: state.silenceEnd, phrases: state.phrases, noteRel: state.noteRel, articulations: state.articulations, duckBase: state.duckBase, duckKey: state.duckKey, autoMix: state.autoMix,
    tracks: _snapshotTracks(),
    golems: (typeof interpState !== 'undefined') ? interpState.golems : undefined,
    // the Interpreter's mix dims and engine settings, so they are undoable too
    interp: (typeof interpState !== 'undefined')
      ? { mix_dims: interpState.mix_dims, v2config: interpState.v2config } : undefined });
}

function _applySnapshot(snap) {
  const s = JSON.parse(snap);
  if (s.tracks) {
    state.tracks = s.tracks.map(tk => ({ ...tk, waveform: _trackWaveforms[tk.path] || [] }));
    // Track rows and per-track UI state are keyed by index; rebuild them.
    if (typeof _trackRows !== 'undefined') _trackRows = [];
    if (typeof _autoLaneOpen !== 'undefined') Object.keys(_autoLaneOpen).forEach(k => delete _autoLaneOpen[k]);
    if (typeof _trackTool !== 'undefined') Object.keys(_trackTool).forEach(k => delete _trackTool[k]);
  }
  if (s.golems && typeof interpState !== 'undefined') {
    interpState.golems = s.golems;
    if (typeof _selectedGolemIdx !== 'undefined') _selectedGolemIdx = null;
  }
  if (s.interp && typeof interpState !== 'undefined') {
    interpState.mix_dims = s.interp.mix_dims || ['gain_db'];
    interpState.v2config = s.interp.v2config || interpState.v2config;
    document.querySelectorAll('.mix-dim-cb').forEach(cb => { cb.checked = interpState.mix_dims.includes(cb.dataset.dim); });
    if (typeof _lastTraceData !== 'undefined' && _lastTraceData) drawKalmanTrace(_lastTraceData);
    const v2 = interpState.v2config.v2 || {};
    const tp = document.getElementById('interp-timbral-pull');
    if (tp && v2.timbral_pull != null) tp.value = v2.timbral_pull;
    const st = document.getElementById('interp-trace-step');
    if (st && v2.trace_step != null) st.value = v2.trace_step;
    if (typeof _populateGlobalSettings === 'function') _populateGlobalSettings();
  }
  state.samples = s.samples;
  state.dynamics = s.dynamics;
  state.events = s.events;
  state.tempo = s.tempo || [];
  state.baseFx = s.baseFx || [];
  state.fxRanges = s.fxRanges || [];
  state.fxGlobal = s.fxGlobal || [];
  state.silenceStart = s.silenceStart || 0;
  state.silenceEnd   = s.silenceEnd   || 0;
  state.phrases  = s.phrases  || [];
  state.noteRel  = s.noteRel  || [];
  state.articulations = s.articulations || [];
  if (s.duckBase) Object.assign(state.duckBase, s.duckBase);
  if (s.duckKey)  Object.assign(state.duckKey,  s.duckKey);
  if (s.autoMix)  Object.assign(state.autoMix,  s.autoMix);
  _updateBaseFxLabel();
  _updateOutputFxLabel();
  scheduleReRender();                      // undo / redo is heard too
}

// An edit made while the Mix / Score / Interp render is playing re-renders it
// (shortly after, so a burst of edits renders once). Every edit calls
// pushHistory just before changing anything, so that is where it is scheduled.
let _reRenderTimer = null;
function scheduleReRender() {
  clearTimeout(_reRenderTimer);
  _reRenderTimer = setTimeout(() => { _reRenderTimer = null; _autoReRender(); }, 500);
}

// Record the current state before an edit. Drags pass the snapshot taken when
// they started, so a whole drag is one undo step (and a plain click is none).
function pushHistory(snap) {
  scheduleReRender();
  state.history.push(snap || _snapshotState());
  if (state.history.length > 50) state.history.shift();
  redoStack.length = 0;
}

// Loading a score, interpretation or new audio starts a new document: undo
// must not reach back into the previous one.
function clearHistory() {
  state.history.length = 0;
  redoStack.length = 0;
}

function _afterHistoryRestore() {
  updateScoreInfo();
  draw();
  if (typeof renderTracksPanel === 'function') renderTracksPanel();
  if (typeof syncSourcePlayback === 'function') syncSourcePlayback();
  if (typeof _renderGolemCards === 'function') _renderGolemCards();
  if (typeof drawGolemTimeline === 'function') drawGolemTimeline();
}

function undo() {
  if (!state.history.length) return;
  redoStack.push(_snapshotState());
  _applySnapshot(state.history.pop());
  _afterHistoryRestore();
}

function redo() {
  if (!redoStack.length) return;
  state.history.push(_snapshotState());
  _applySnapshot(redoStack.pop());
  _afterHistoryRestore();
}

document.getElementById("undo-btn").addEventListener("click", undo);
document.getElementById("redo-btn").addEventListener("click", redo);

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
      // Name passed via data- attribute so quotes/markup in it can't break out
      html += `<div class="info-item info-clickable" data-name="${escapeHtml(n)}" onclick="editSampleAt(this.dataset.name)"><span style="color:${s.color}">[${escapeHtml(n)}]</span> ${s.from.toFixed(2)}s → ${s.to.toFixed(2)}s</div>`;
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
      let line = `✎ <span style="color:${col}">${escapeHtml(ev.sample)}</span> @${ev.t.toFixed(2)}s`;
      const _pv = v => escapeHtml(v != null && typeof v === "object" ? JSON.stringify(v) : v);
      line += ` spd:${ev.speed != null ? _pv(ev.speed) : (ev.speeds ? "[…]" : "?")} db:${_pv(ev.gain_db)}`;
      if (ev.loop) line += " loop";
      if (ev.reverse) line += " rev";
      if (ev.fx && ev.fx.length > 0) line += ` fx:${escapeHtml(ev.fx.map(f => f.type).join("+"))}`;
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
          `<span style="color:${DYNAMIC_COLORS[dm0]}">${escapeHtml(dm0)}</span> @${d.t.toFixed(2)}s`, !!d.muted);
      } else {
        const dm0 = d.mark || d.marking || '?';
        const col = dm0 === "crescendo" ? "#337755" : "#775533";
        html += _ha(`openRangeEditPopup(${i})`, 'dynamic', 'dynamic', i,
          `<span style="color:${col}">${escapeHtml(dm0)}</span> ${d.from.toFixed(2)}s → ${d.to.toFixed(2)}s`, !!d.muted);
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
        `<span style="color:${col}">${escapeHtml(tp.mark)}</span> ×${escapeHtml(JSON.stringify(tp.factor))} ${tp.from.toFixed(2)}s → ${tp.to.toFixed(2)}s`, !!tp.muted);
    });
  }

  // FX zones
  html += _sh("fxzones", `fx zones (${state.fxRanges.length})`);
  if (!infoCollapsed["fxzones"]) {
    if (!state.fxRanges.length) html += `<div class="info-item" style="color:#2a2a2a;">—</div>`;
    state.fxRanges.forEach((fz, i) => {
      html += _ha(`editFxZoneAt(${i})`, 'fxzone', 'fxzone', i,
        `<span style="color:${fxZoneColor(fz)}">${fz.target === "output" ? "output: " : ""}${escapeHtml(fz.fx.map(f => f.type).join("+"))}</span> ${fz.from.toFixed(2)}s → ${fz.to.toFixed(2)}s`, !!fz.muted);
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
        `<span style="color:#8a6abf">${escapeHtml(ph.label)}</span> ${ph.from.toFixed(2)}s → ${ph.to.toFixed(2)}s${extras.length ? ' <span style="color:#666;font-size:10px;">' + extras.join(' ') + '</span>' : ''}`, !!ph.muted);
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
        `<span style="color:${col}">${escapeHtml(nr.type)}</span> ${range}${nr.label ? ' <span style="color:#666;font-size:10px;">' + escapeHtml(nr.label) + '</span>' : ''}`, !!nr.muted);
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
        `<span style="color:${col}">${escapeHtml(ar.type)}</span> ${pos}${ar.label ? ' <span style="color:#666;font-size:10px;">' + escapeHtml(ar.label) + '</span>' : ''}`, !!ar.muted);
    });
  }

  // Sidechain
  html += _sh("sidechain", `sidechain / mix`);
  if (!infoCollapsed["sidechain"]) {
    const scInputStyle = `background:#1a1a1a;border:1px solid #333;color:#aaa;font-family:inherit;font-size:11px;`;
    // The dropdown shows the first sample when the key is unset/stale — keep state in sync with it
    if (sNames.length && !state.samples[state.duckKey.key]) state.duckKey.key = sNames[0];
    else if (!sNames.length) state.duckKey.key = "";
    const keyOpts = sNames.map(n => `<option value="${escapeHtml(n)}"${state.duckKey.key===n?" selected":""}>${escapeHtml(n)}</option>`).join("") || `<option value="">—</option>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-db-on"${state.duckBase.enabled?" checked":""}
        onchange="state.duckBase.enabled=this.checked;" title="duck base: reduce base audio when events play">
      <span style="color:#7ab;min-width:68px;">duck base</span>
      dB:<input id="sc-db-amt" type="number" value="${state.duckBase.amount_db}" step="1" style="width:38px;${scInputStyle}" onchange="state.duckBase.amount_db=+this.value;">
      atk:<input id="sc-db-atk" type="number" value="${state.duckBase.attack}" step="0.005" min="0.001" style="width:44px;${scInputStyle}" onchange="state.duckBase.attack=+this.value;">
      rel:<input id="sc-db-rel" type="number" value="${state.duckBase.release}" step="0.05" min="0.01" style="width:44px;${scInputStyle}" onchange="state.duckBase.release=+this.value;">
    </div>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-dk-on"${state.duckKey.enabled?" checked":""}
        onchange="state.duckKey.enabled=this.checked;" title="duck key: one sample ducks entire mix (pump effect)">
      <span style="color:#7ab;min-width:68px;">duck key</span>
      key:<select id="sc-dk-key" style="width:54px;${scInputStyle}" onchange="state.duckKey.key=this.value;">${keyOpts}</select>
      dB:<input id="sc-dk-amt" type="number" value="${state.duckKey.amount_db}" step="1" style="width:38px;${scInputStyle}" onchange="state.duckKey.amount_db=+this.value;">
      atk:<input id="sc-dk-atk" type="number" value="${state.duckKey.attack}" step="0.005" min="0.001" style="width:44px;${scInputStyle}" onchange="state.duckKey.attack=+this.value;">
      rel:<input id="sc-dk-rel" type="number" value="${state.duckKey.release}" step="0.05" min="0.01" style="width:44px;${scInputStyle}" onchange="state.duckKey.release=+this.value;">
    </div>`;
    html += `<div class="info-item" style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:2px 0;">
      <input type="checkbox" id="sc-am-on"${state.autoMix.enabled?" checked":""}
        onchange="state.autoMix.enabled=this.checked;" title="auto-mix: reduce gain when events overlap">
      <span style="color:#7ab;min-width:68px;">auto-mix</span>
      mode:<select id="sc-am-mode" style="width:54px;${scInputStyle}" onchange="state.autoMix.mode=this.value;">
        <option value="sqrt"${state.autoMix.mode==="sqrt"?" selected":""}>sqrt</option>
        <option value="inverse"${state.autoMix.mode==="inverse"?" selected":""}>inverse</option>
      </select>
    </div>`;
  }

  el.innerHTML = html;
}


