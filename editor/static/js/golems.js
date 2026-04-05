// ─── golems.js ────────────────────────────────────────────────────────────────
// Golem timeline, golem editor, preset management, custom character CRUD.
// Depends on: state.js (interpState), draw.js (draw)

const GOLEM_COLORS = {
  dramatic:    '#7b3a3a',
  lyrical:     '#3a5a7b',
  sparse:      '#3a7b4a',
  turbulent:   '#7b6a3a',
  rw_free:     '#7b5a1a',
  rw_drift_up: '#6a1a7b',
  rw_reverting:'#1a6a70',
};
const GOLEM_LABEL_COLORS = {
  dramatic:    '#c87070',
  lyrical:     '#70a0c8',
  sparse:      '#70c880',
  turbulent:   '#c8a870',
  rw_free:     '#c8a050',
  rw_drift_up: '#b070c8',
  rw_reverting:'#50c8c0',
};
const KALMAN_CHARS  = ['dramatic','lyrical','sparse','turbulent','disciplined','impressionist','impulsive','volatile','sight_reading','memorised'];
const RW_CHARS      = ['rw_free','rw_drift_up','rw_reverting','drift_down','breathing','free_improv','anchored','dream','erratic'];
const CHARS_BY_TYPE = { kalman: KALMAN_CHARS, random_walk: RW_CHARS };

const DIST_LABELS = {
  '':         'char default',
  gaussian:   'Natural',
  laplace:    'Edgy',
  cauchy:     'Wild',
  uniform:    'Even',
  beta:       'Curved',
  student_t:  'Heavy',
  bimodal:    'Split',
  mixture:    'Bursting',
};

const PRESET_PARAMS = {
  // Kalman presets
  dramatic:     { A1:0.80, A2:0.10, Q_scale:2.0, R_scale:1.5,  lam:0.70, obs_weight:1.2, drama_curve:'exp',    distribution:'laplace'  },
  lyrical:      { A1:0.65, A2:0.30, Q_scale:0.5, R_scale:0.8,  lam:0.85, obs_weight:1.0, drama_curve:'linear', distribution:'gaussian' },
  sparse:       { A1:0.90, A2:0.00, Q_scale:0.2, R_scale:0.5,  lam:0.40, obs_weight:1.5, drama_curve:'linear', distribution:'gaussian' },
  turbulent:    { A1:0.50, A2:0.20, Q_scale:3.0, R_scale:2.0,  lam:0.30, obs_weight:0.6, drama_curve:'square', distribution:'student_t', df:3 },
  disciplined:  { A1:0.85, A2:0.10, Q_scale:0.3, R_scale:0.3,  lam:0.80, obs_weight:2.0, drama_curve:'linear', distribution:'gaussian' },
  impressionist:{ A1:0.60, A2:0.25, Q_scale:1.0, R_scale:2.5,  lam:0.90, obs_weight:0.4, drama_curve:'linear', distribution:'beta'     },
  impulsive:    { A1:0.40, A2:0.10, Q_scale:2.5, R_scale:0.8,  lam:0.50, obs_weight:1.0, drama_curve:'exp',    distribution:'cauchy'   },
  volatile:     { A1:0.70, A2:0.15, Q_scale:1.5, R_scale:1.2,  lam:0.60, obs_weight:0.8, drama_curve:'square', distribution:'bimodal', bimodal_sep:0.75 },
  sight_reading:{ A1:0.75, A2:0.15, Q_scale:1.0, R_scale:1.0,  lam:0.20, obs_weight:1.0, drama_curve:'linear', distribution:'gaussian' },
  memorised:    { A1:0.70, A2:0.20, Q_scale:1.0, R_scale:1.0,  lam:0.95, obs_weight:1.0, drama_curve:'linear', distribution:'gaussian' },
  // Random Walk presets (12D: gain, bright, timing, attack, release, reverb, cutoff, res, stereo, drive, pitch, dyncenter)
  rw_free:      { step_size:[1.5,0.05,20,0.05,0.05,0.05,200,0.05,0.05,0.05,5,1], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0,0,0,0,0,0,0,0,0,0,0,0], boundary_mode:'reflect', distribution:'gaussian' },
  rw_drift_up:  { step_size:[1.2,0.04,15,0.04,0.04,0.04,150,0.04,0.04,0.04,4,0.8], drift:[0.3,0.01,2,0.01,0.01,0.01,50,0.01,0.01,0.01,1,0.2], mr_dims:[0,0,0,0,0,0,0,0,0,0,0,0], boundary_mode:'clip', distribution:'gaussian' },
  rw_reverting: { step_size:[1.5,0.05,20,0.05,0.05,0.05,200,0.05,0.05,0.05,5,1], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0.12,0.12,0.12,0.12,0.12,0.12,0.12,0.12,0.12,0.12,0.12,0.12], boundary_mode:'reflect', distribution:'gaussian' },
  drift_down:   { step_size:[1.0,0.03,12,0.03,0.03,0.03,100,0.03,0.03,0.03,3,0.5], drift:[-0.2,-0.01,-1.5,-0.01,-0.01,-0.01,-30,-0.01,-0.01,-0.01,-0.5,-0.1], mr_dims:[0,0,0,0,0,0,0,0,0,0,0,0], boundary_mode:'clip', distribution:'gaussian' },
  breathing:    { step_size:[0.5,0.02,8,0.02,0.02,0.02,80,0.02,0.02,0.02,2,0.4], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.05], boundary_mode:'reflect', distribution:'gaussian', breath_period:8.0, breath_amp:0.6 },
  free_improv:  { step_size:[2.5,0.08,30,0.08,0.08,0.08,300,0.08,0.08,0.08,8,1.5], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0,0,0,0,0,0,0,0,0,0,0,0], boundary_mode:'reflect', distribution:'laplace' },
  anchored:     { step_size:[1.0,0.03,12,0.03,0.03,0.03,100,0.03,0.03,0.03,3,0.5], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3], boundary_mode:'reflect', distribution:'gaussian' },
  dream:        { step_size:[0.3,0.01,5,0.01,0.01,0.01,50,0.01,0.01,0.01,1,0.2], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0.02,0.02,0.02,0.02,0.02,0.02,0.02,0.02,0.02,0.02,0.02,0.02], boundary_mode:'reflect', distribution:'beta' },
  erratic:      { step_size:[3.0,0.10,40,0.10,0.10,0.10,400,0.10,0.10,0.10,10,2], drift:[0,0,0,0,0,0,0,0,0,0,0,0], mr_dims:[0,0,0,0,0,0,0,0,0,0,0,0], boundary_mode:'clip', distribution:'cauchy' },
};

// ─── Additional character colors for new presets ──────────────────────────────
Object.assign(GOLEM_COLORS, {
  disciplined:   '#2a3a5a', impressionist: '#4a3a6a', impulsive: '#7b2a2a',
  volatile:      '#6a2a6a', sight_reading: '#3a4a3a', memorised: '#2a5a5a',
  drift_down:    '#5a3a1a', breathing:     '#1a5a3a', free_improv: '#5a1a3a',
  anchored:      '#3a5a2a', dream:         '#1a3a5a', erratic: '#5a1a1a',
});
Object.assign(GOLEM_LABEL_COLORS, {
  disciplined:   '#6080c0', impressionist: '#a080d0', impulsive: '#d06060',
  volatile:      '#d060d0', sight_reading: '#80a080', memorised: '#60c0c0',
  drift_down:    '#c08040', breathing:     '#40c080', free_improv: '#c04080',
  anchored:      '#80c060', dream:         '#4080c0', erratic: '#c04040',
});

// ─── Golem editor state ───────────────────────────────────────────────────────
let _selectedGolemIdx = null;
let _lastPresetName   = null;
let _lastPresetEngine = 'kalman';

// Neutral Kalman params — intensity=0 blends all the way to these
const _KALMAN_NEUTRAL = { A1:0.70, A2:0.10, Q_scale:1.0, R_scale:1.0, obs_weight:1.0, lam:0.70 };
let _customChars = { kalman: {}, random_walk: {} };
let _golemDrag   = null;

// Per-golem vector/matrix data held in editor memory (not in HTML inputs)
let _geVec = {
  a1dims: null, a2dims: null,
  qbase:  null, obswtdims: null,
  fpmask: null, fpscale: null,
  mrtarget:    null,
  inflatedims: null,
  clipsigmadims: null,
  correlation: null,
  // distribution config object
  dist_config: {},
};

// RW default vectors (12D)
const _RW_SS_DEF  = [1.5,0.05,20,0.05,0.05,0.05,200,0.05,0.05,0.05,5,1];
const _RW_ZERO    = [0,0,0,0,0,0,0,0,0,0,0,0];

// Dimension colors for 12D state — used by viz-panel.js and kalman-trace.js
// DIM_NAMES and DIM_LABELS are defined in state.js (loads first)
const DIM_COLORS = [
  '#c8922a','#2ac8c8','#c82ac8','#2ac85a','#8a2ac8','#c85a2a',
  '#5ac82a','#2a5ac8','#c82a5a','#aac82a','#2aaac8','#c8c82a',
];

// ─── Vector display helpers ───────────────────────────────────────────────────
function _vecStr(arr) {
  if (!arr) return '—';
  return '[' + arr.map(v => (typeof v === 'number' ? (Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(1)) : v)).join(', ') + ']';
}

function _updateVecDisplay(key, displayId) {
  const el = document.getElementById(displayId);
  if (el) el.textContent = _vecStr(_geVec[key]);
}

// ─── Vector editor popup (number inputs) ─────────────────────────────────────
function _editVector(key, title, range, step) {
  const vals = _geVec[key] || Array(DIM_NAMES.length).fill(0);
  const [lo, hi] = range || [-Infinity, Infinity];
  const body = DIM_NAMES.map((d, i) =>
    `<div class="ve-row">
       <label style="color:${DIM_COLORS[i]}">${d}</label>
       <input type="number" id="ve-${i}" value="${vals[i]}" step="${step||0.01}"
              min="${isFinite(lo)?lo:''}" max="${isFinite(hi)?hi:''}"
              style="background:#1a1a1a;border:1px solid #2a2a2a;color:#ccc;padding:2px 5px;font-size:11px;width:80px;" />
     </div>`
  ).join('');
  showPopup(title, `<div class="vector-editor">${body}</div>`).then(() => {
    _geVec[key] = DIM_NAMES.map((_, i) => {
      const v = parseFloat(document.getElementById(`ve-${i}`)?.value);
      return isNaN(v) ? 0 : v;
    });
    _updateVecDisplay(key, `ge-${key}-display`);
  });
}

// ─── Binary (0/1 checkbox) vector popup ───────────────────────────────────────
function _editVectorBinary(key, title) {
  const vals = _geVec[key] || Array.from({length: DIM_NAMES.length}, (_, i) => i === 0 ? 1 : 0);
  const body = DIM_NAMES.map((d, i) =>
    `<div class="ve-row">
       <label style="color:${DIM_COLORS[i]}">${d}</label>
       <input type="checkbox" id="ve-${i}" ${vals[i] ? 'checked' : ''}
              style="width:18px;height:18px;" />
     </div>`
  ).join('');
  showPopup(title, `<div class="vector-editor">${body}</div>`).then(() => {
    _geVec[key] = DIM_NAMES.map((_, i) =>
      document.getElementById(`ve-${i}`)?.checked ? 1 : 0
    );
    _updateVecDisplay(key, `ge-${key}-display`);
  });
}

// ─── 5×5 correlation matrix popup ─────────────────────────────────────────────
function _editCorrelation() {
  const vals = _geVec.correlation || null;
  const header = '<tr><th></th>' + DIM_NAMES.map(d => `<th style="font-size:9px;color:#555;">${d.substring(0,5)}</th>`).join('') + '</tr>';
  const rows = DIM_NAMES.map((r, i) =>
    `<tr><td style="font-size:9px;color:${DIM_COLORS[i]};padding-right:4px;">${r.substring(0,5)}</td>` +
    DIM_NAMES.map((c, j) => {
      const v = vals ? (vals[i]?.[j] ?? (i===j?1:0)) : (i===j?1:0);
      return `<td><input type="number" id="me-${i}-${j}" value="${v}" step="0.05" min="-1" max="1"
                style="width:40px;background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;padding:1px 2px;font-size:10px;"
                ${i===j?'readonly style="width:40px;background:#111;border:1px solid #1a1a1a;color:#444;padding:1px 2px;font-size:10px;"':''}></td>`;
    }).join('') + '</tr>'
  ).join('');
  showPopup('Correlation matrix (5×5)',
    `<p style="font-size:10px;color:#444;margin-bottom:6px;">Off-diagonal values in [-1, 1]. Diagonal is always 1.</p>
     <div style="margin-top:0"><button onclick="_applyCorrelationPreset('none')" style="font-size:9px;padding:1px 5px;margin-right:3px;">Independent</button>
     <button onclick="_applyCorrelationPreset('gain_bright')" style="font-size:9px;padding:1px 5px;margin-right:3px;">Vol↔Bright</button>
     <button onclick="_applyCorrelationPreset('expressive')" style="font-size:9px;padding:1px 5px;margin-right:3px;">Expressive</button>
     <button onclick="_applyCorrelationPreset('temporal')" style="font-size:9px;padding:1px 5px;">Temporal</button></div>
     <table class="matrix-editor" style="margin-top:6px;border-collapse:collapse;"><thead>${header}</thead><tbody>${rows}</tbody></table>`
  ).then(() => {
    const m = DIM_NAMES.map((_, i) => DIM_NAMES.map((__, j) => {
      if (i === j) return 1;
      return parseFloat(document.getElementById(`me-${i}-${j}`)?.value ?? 0);
    }));
    // Check if it's basically identity
    const isIdentity = m.every((row, i) => row.every((v, j) => Math.abs(v - (i===j?1:0)) < 0.001));
    _geVec.correlation = isIdentity ? null : m;
    const el = document.getElementById('ge-corr-display');
    if (el) el.textContent = _geVec.correlation ? 'custom' : '—';
  });
}

function _applyCorrelationPreset(name) {
  const preset = _CORR_PRESETS[name];
  DIM_NAMES.forEach((_, i) => {
    DIM_NAMES.forEach((__, j) => {
      const el = document.getElementById(`me-${i}-${j}`);
      if (el && !el.readOnly) el.value = preset ? (preset[i]?.[j] ?? 0) : (i===j?1:0);
    });
  });
}

// ─── Physical limits matrix popup (5×2) ──────────────────────────────────────
function _editPhysicalLimits() {
  const DEFAULTS = [[-30,6],[0,1],[-500,500],[0,1],[0,1]];
  const vals = (interpState.v2config.v2 || {}).physical_limits || null;
  const header = '<tr><th></th><th style="font-size:9px;color:#555;">min</th><th style="font-size:9px;color:#555;">max</th></tr>';
  const rows = DIM_NAMES.map((d, i) =>
    `<tr><td style="font-size:9px;color:${DIM_COLORS[i]};padding-right:6px;">${d}</td>` +
    [0,1].map(j => {
      const v = vals ? (vals[i]?.[j] ?? DEFAULTS[i][j]) : DEFAULTS[i][j];
      return `<td><input type="number" id="pl-${i}-${j}" value="${v}" step="0.1"
              style="width:60px;background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;padding:2px 3px;font-size:10px;"></td>`;
    }).join('') + '</tr>'
  ).join('');
  showPopup('Physical limits per dimension',
    `<p style="font-size:10px;color:#444;margin-bottom:6px;">Valid range for each expressive dimension.</p>
     <table class="matrix-editor" style="border-collapse:collapse;"><thead>${header}</thead><tbody>${rows}</tbody></table>`
  ).then(() => {
    const m = DIM_NAMES.map((_, i) => [0,1].map(j =>
      parseFloat(document.getElementById(`pl-${i}-${j}`)?.value ?? DEFAULTS[i][j])
    ));
    if (!interpState.v2config.v2) interpState.v2config.v2 = {};
    interpState.v2config.v2.physical_limits = m;
    const el = document.getElementById('gp-physlimits-display');
    if (el) el.textContent = 'custom';
  });
}

function _openSaliencePopup() {
  const cur = {
    alpha:   parseFloat(document.getElementById('gp-alpha')?.value   ?? 0.4),
    beta:    parseFloat(document.getElementById('gp-beta')?.value    ?? 0.3),
    gamma:   parseFloat(document.getElementById('gp-gamma-sal')?.value ?? 0.2),
    delta:   parseFloat(document.getElementById('gp-delta')?.value   ?? 0.1),
  };
  const body = `
    <p style="font-size:10px;color:#444;margin-bottom:10px;">
      Weights for how <em>structurally important</em> each dynamic marking is.<br>
      Must not need to sum to 1 — they are combined linearly.
    </p>
    ${[
      ['α','sp-alpha', cur.alpha, 'Dynamic distance from previous marking'],
      ['β','sp-beta',  cur.beta,  'Structural marking (sfz, fp, subito…)'],
      ['γ','sp-gamma', cur.gamma, 'Local contrast vs. surrounding markings'],
      ['δ','sp-delta', cur.delta, 'Phrase boundary bonus'],
    ].map(([lbl, id, val, desc]) => `
      <div class="popup-row" style="flex-direction:column;align-items:stretch;gap:3px;">
        <div style="display:flex;justify-content:space-between;">
          <label style="font-size:12px;font-weight:bold;color:#aaa;">${lbl}</label>
          <span style="font-size:10px;color:#555;">${desc}</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="range" id="${id}-range" min="0" max="1" step="0.05" value="${val}" style="flex:1;accent-color:#5a9a5a;"
                 oninput="document.getElementById('${id}').value=parseFloat(this.value).toFixed(2);" />
          <input type="number" id="${id}" value="${val.toFixed(2)}" min="0" max="1" step="0.05"
                 style="width:54px;background:#222;border:1px solid #333;color:#ccc;padding:2px 5px;"
                 oninput="const s=document.getElementById('${id}-range');if(!isNaN(+this.value))s.value=Math.min(Math.max(+this.value,0),1);" />
        </div>
      </div>`
    ).join('')}`;
  showPopup('Salience Weights', body).then(() => {
    const vals = {
      alpha: parseFloat(document.getElementById('sp-alpha')?.value ?? 0.4),
      beta:  parseFloat(document.getElementById('sp-beta')?.value  ?? 0.3),
      gamma: parseFloat(document.getElementById('sp-gamma')?.value ?? 0.2),
      delta: parseFloat(document.getElementById('sp-delta')?.value ?? 0.1),
    };
    // Write back to hidden inputs
    document.getElementById('gp-alpha').value     = vals.alpha;
    document.getElementById('gp-beta').value      = vals.beta;
    document.getElementById('gp-gamma-sal').value = vals.gamma;
    document.getElementById('gp-delta').value     = vals.delta;
    // Update summary display
    const s = document.getElementById('gp-salience-summary');
    if (s) s.textContent = `α ${vals.alpha.toFixed(2)}  β ${vals.beta.toFixed(2)}  γ ${vals.gamma.toFixed(2)}  δ ${vals.delta.toFixed(2)}`;
  });
}

// ─── Golem list (kept as no-ops — accordion replaces these) ──────────────────
function _renderGolemListCol() {}
function _renderInterpGolemRows() {}

// ─── Golem accordion ──────────────────────────────────────────────────────────
function _golemDisplayName(golem, idx) {
  if (golem.name) return golem.name;
  return (golem.character || 'golem') + ' #' + (idx + 1);
}

function _renderGolemCards() {
  const accordion = document.getElementById('golem-accordion');
  const editor    = document.getElementById('interp-golem-editor');
  if (!accordion || !editor) return;

  accordion.innerHTML = '';

  interpState.golems.forEach((g, i) => {
    const col      = GOLEM_LABEL_COLORS[g.character] || '#888';
    const name     = _golemDisplayName(g, i);
    const isRW     = (g.type || 'kalman') === 'random_walk';
    const selected = i === _selectedGolemIdx;

    const card = document.createElement('div');
    card.className = 'golem-card' + (selected ? ' selected' : '');

    const header = document.createElement('div');
    header.className = 'gc-header';
    header.innerHTML =
      `<span class="gc-dot" style="background:${col}"></span>` +
      `<span class="gc-name">${name}</span>` +
      `<span class="gc-time">${(g.from||0).toFixed(1)}–${(g.to||0).toFixed(1)}s</span>` +
      `<span class="gc-engine">${isRW ? 'RW' : 'K'}</span>`;
    header.addEventListener('click', () => _selectGolem(i));

    const body = document.createElement('div');
    body.className = 'gc-body';

    card.appendChild(header);
    card.appendChild(body);
    accordion.appendChild(card);

    if (selected) body.appendChild(editor);
  });

  // If nothing selected, park the editor back in its hidden home
  if (_selectedGolemIdx === null || !interpState.golems.length) {
    const home = document.getElementById('interp-golem-panel');
    if (home) home.appendChild(editor);
  }
}

// ─── Golem editor helpers ─────────────────────────────────────────────────────
function _distSelectHTML(currentVal) {
  return Object.entries(DIST_LABELS).map(([v, l]) =>
    `<option value="${v}"${v === (currentVal||'') ? ' selected' : ''}>${l}</option>`
  ).join('');
}

function _setSlider(id, val, valId) {
  const el = document.getElementById(id);
  if (el) el.value = val;
  if (valId) { const v = document.getElementById(valId); if (v) { const s = parseFloat(val).toFixed(2); if (v.tagName === 'INPUT') v.value = s; else v.textContent = s; } }
}

function _setActiveDist(dist) {
  document.querySelectorAll('.ge-dist-btn').forEach(b => b.classList.toggle('active', b.dataset.dist === dist));
}

function _getActiveDist() {
  const a = document.querySelector('.ge-dist-btn.active');
  return a ? a.dataset.dist : 'gaussian';
}

function _getActiveEngine() {
  const a = document.querySelector('.ge-engine-btn.active');
  return a ? a.dataset.engine : 'kalman';
}

function _setVal(id, v) {
  const el = document.getElementById(id);
  if (el && v !== undefined) el.value = v;
}

function _refreshPresets(engineType) {
  const container = document.getElementById('ge-presets');
  if (!container) return;
  const chars  = (engineType === 'random_walk') ? RW_CHARS : KALMAN_CHARS;
  const custom = Object.keys(_customChars[engineType] || {});
  container.innerHTML = [...chars, ...custom].map(name => {
    const col = GOLEM_LABEL_COLORS[name] || '#888';
    return `<button class="ge-preset-btn" data-preset="${name}" style="color:${col};border-color:${col}33;">${name}</button>`;
  }).join('');
  container.querySelectorAll('.ge-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const intensity  = parseFloat(document.getElementById('ge-preset-intensity')?.value  ?? 1);
      const smoothness = parseFloat(document.getElementById('ge-preset-smooth')?.value     ?? 1);
      _applyPresetScaled(btn.dataset.preset, engineType, intensity, smoothness);
    });
  });
  // Wire slider ↔ number sync and re-apply on change
  ['intensity', 'smooth'].forEach(which => {
    const sl = document.getElementById(`ge-preset-${which}`);
    const nu = document.getElementById(`ge-preset-${which}-val`);
    if (!sl || !nu) return;
    // Replace listeners by cloning
    const sl2 = sl.cloneNode(true); sl.replaceWith(sl2);
    const nu2 = nu.cloneNode(true); nu.replaceWith(nu2);
    sl2.addEventListener('input', () => { nu2.value = sl2.value; _reapplyPreset(); });
    nu2.addEventListener('input', () => { sl2.value = nu2.value; _reapplyPreset(); });
  });
}

function _applyPreset(name, engineType) {
  let params = PRESET_PARAMS[name];
  if (!params) params = (_customChars[engineType] || {})[name];
  if (!params) return;

  const isKalman = engineType !== 'random_walk';
  document.querySelectorAll('.ge-engine-btn').forEach(b => b.classList.remove('active'));
  const eBtn = document.querySelector(`.ge-engine-btn[data-engine="${engineType}"]`);
  if (eBtn) eBtn.classList.add('active');
  document.getElementById('ge-params-kalman').style.display = isKalman ? '' : 'none';
  document.getElementById('ge-params-rw').style.display     = isKalman ? 'none' : '';

  if (isKalman) {
    _setSlider('ge-lam',        params.lam        ?? 0.80, 'ge-lam-val');
    _setSlider('ge-A1',         params.A1         ?? 0.70, 'ge-A1-val');
    _setSlider('ge-A2',         params.A2         ?? 0.20, 'ge-A2-val');
    _setSlider('ge-Q-scale',    params.Q_scale    ?? 1.00, 'ge-Q-scale-val');
    _setSlider('ge-obs-weight', params.obs_weight ?? 1.00, 'ge-obs-weight-val');
    _setSlider('ge-R-scale',    params.R_scale    ?? 1.00, 'ge-R-scale-val');
    _setVal('ge-drama-curve', params.drama_curve ?? 'linear');
    // New Kalman params
    _setVal('ge-innov-decay', params.innov_decay ?? 0.7);
    _setSlider('ge-gamma-w', params.gamma_w ?? 1.0, 'ge-gamma-w-val');
    const xiEl = document.getElementById('ge-xi-regime');
    if (xiEl) xiEl.value = params.xi_regime != null ? params.xi_regime : '';
    // Vector params from preset
    _geVec.a1dims    = params.A1_dims    || null;
    _geVec.a2dims    = params.A2_dims    || null;
    _geVec.qbase     = params.Q_base     || null;
    _geVec.obswtdims = params.obs_weight_dims || null;
    _geVec.fpmask    = params.fp_mask    || null;
    _geVec.fpscale   = params.fp_scale   || null;
    _updateVecDisplay('a1dims', 'ge-a1dims-display');
    _updateVecDisplay('a2dims', 'ge-a2dims-display');
    _updateVecDisplay('qbase',  'ge-qbase-display');
    _updateVecDisplay('obswtdims', 'ge-obswtdims-display');
    _updateVecDisplay('fpmask',  'ge-fpmask-display');
    _updateVecDisplay('fpscale', 'ge-fpscale-display');
  } else {
    const ss = params.step_size || _RW_SS_DEF;
    const dr = params.drift     || _RW_ZERO;
    const mr = params.mr_dims   || _RW_ZERO;
    for (let i = 0; i < DIM_NAMES.length; i++) {
      _setVal(`ge-rw-step-${i}`,  ss[i]);
      _setVal(`ge-rw-drift-${i}`, dr[i]);
      _setVal(`ge-rw-mr-${i}`,    mr[i]);
    }
    _setVal('ge-rw-boundary', params.boundary_mode || 'clip');
    // New RW params
    const bpEl = document.getElementById('ge-breath-period');
    const baEl = document.getElementById('ge-breath-amp');
    const osEl = document.getElementById('ge-omega-step-scale');
    if (bpEl) bpEl.value = params.breath_period != null ? params.breath_period : '';
    if (baEl) baEl.value = params.breath_amp    != null ? params.breath_amp    : '';
    if (osEl) osEl.value = params.omega_step_scale != null ? params.omega_step_scale : '';
    _geVec.mrtarget    = params.mr_target   || null;
    _geVec.correlation = params.correlation || null;
    _updateVecDisplay('mrtarget',    'ge-mrtarget-display');
    const corrEl = document.getElementById('ge-corr-display');
    if (corrEl) corrEl.textContent = _geVec.correlation ? 'custom' : '—';
  }

  if (params.distribution) _setActiveDist(params.distribution);
  // Dist config from preset (df, bimodal_sep, etc.)
  _geVec.dist_config = {};
  if (params.df !== undefined)          _geVec.dist_config.df = params.df;
  if (params.bimodal_sep !== undefined) _geVec.dist_config.bimodal_sep = params.bimodal_sep;
  if (params.beta_a !== undefined)      _geVec.dist_config.beta_a = params.beta_a;
  if (params.beta_b !== undefined)      _geVec.dist_config.beta_b = params.beta_b;
  if (params.mixture_p !== undefined)   _geVec.dist_config.mixture_p = params.mixture_p;
  if (params.spike_scale !== undefined) _geVec.dist_config.spike_scale = params.spike_scale;
  if (params.skew !== undefined)        _geVec.dist_config.skew = params.skew;

  // Common H section
  _setVal('ge-fade-curve',  params.fade_curve  || 'linear');
  _setVal('ge-dist-blend',  params.dist_blend  || 'dominant');
  _setVal('ge-inflate',     params.inflate     ?? 1.0);
  _geVec.inflatedims = params.inflate_dims || null;
  _updateVecDisplay('inflatedims', 'ge-inflatedims-display');

  document.querySelectorAll('.ge-preset-btn').forEach(b => b.classList.remove('active'));
  const pBtn = document.querySelector(`.ge-preset-btn[data-preset="${name}"]`);
  if (pBtn) pBtn.classList.add('active');
  _lastPresetName   = name;
  _lastPresetEngine = engineType;
  if (typeof _refreshStartValPlaceholders === 'function') _refreshStartValPlaceholders();
}

// ─── Preset intensity/smoothness scaling ─────────────────────────────────────
function _reapplyPreset() {
  if (!_lastPresetName) return;
  const intensity  = parseFloat(document.getElementById('ge-preset-intensity')?.value  ?? 1);
  const smoothness = parseFloat(document.getElementById('ge-preset-smooth')?.value     ?? 1);
  _applyPresetScaled(_lastPresetName, _lastPresetEngine, intensity, smoothness);
}

function _applyPresetScaled(name, engineType, intensity, smoothness) {
  // First apply at full strength to get all the non-scalar fields set correctly
  _applyPreset(name, engineType);

  if (engineType !== 'random_walk') {
    const p = PRESET_PARAMS[name] || (_customChars[engineType] || {})[name] || {};
    // Blend each scalar Kalman param toward neutral based on intensity
    const interp = (key) => _KALMAN_NEUTRAL[key] + ((p[key] ?? _KALMAN_NEUTRAL[key]) - _KALMAN_NEUTRAL[key]) * intensity;
    let a1 = interp('A1'), q = interp('Q_scale'), r = interp('R_scale'), ow = interp('obs_weight'), lam = interp('lam');
    // Smoothness: >1 pushes A1 toward 0.95 and halves Q_scale, <1 does the opposite
    if (smoothness !== 1) {
      a1 = smoothness >= 1
        ? a1 + (0.95 - a1) * (smoothness - 1)
        : a1 * (0.3 + smoothness * 0.7);
      q  = q / (0.5 + smoothness * 0.5);
    }
    a1 = Math.min(0.95, Math.max(0.1, a1));
    q  = Math.max(0.05, q);
    _setSlider('ge-A1',         a1,  'ge-A1-val');
    _setSlider('ge-Q-scale',    q,   'ge-Q-scale-val');
    _setSlider('ge-R-scale',    Math.max(0.1, r),   'ge-R-scale-val');
    _setSlider('ge-obs-weight', Math.max(0.1, ow),  'ge-obs-weight-val');
    _setSlider('ge-lam',        Math.min(0.99, Math.max(0.05, lam)), 'ge-lam-val');
  } else {
    // RW: intensity scales step_size; smoothness scales mr_dims (higher = more reversion)
    const p = PRESET_PARAMS[name] || (_customChars[engineType] || {})[name] || {};
    const baseSS = p.step_size || _RW_SS_DEF;
    for (let i = 0; i < DIM_NAMES.length; i++) {
      const v = baseSS[i] * intensity;
      _setVal(`ge-rw-step-${i}`, v.toFixed(3));
    }
    if (smoothness !== 1) {
      const baseMR = p.mr_dims || _RW_ZERO;
      for (let i = 0; i < DIM_NAMES.length; i++) {
        const v = Math.max(0, baseMR[i] * smoothness);
        _setVal(`ge-rw-mr-${i}`, v.toFixed(3));
      }
    }
  }
}

function _readGolemEditor() {
  const engine  = _getActiveEngine();
  const dist    = _getActiveDist();
  const from    = parseFloat(document.getElementById('ge-from')?.value)    || 0;
  const to      = parseFloat(document.getElementById('ge-to')?.value)      || 0;
  const weight  = parseFloat(document.getElementById('ge-weight')?.value)  || 1.0;
  const fadeIn  = parseFloat(document.getElementById('ge-fadein')?.value)  || 0;
  const fadeOut = parseFloat(document.getElementById('ge-fadeout')?.value) || 0;

  const golem = {
    from, to, type: engine, character: 'custom', weight,
    fade_in: fadeIn, fade_out: fadeOut,
    distribution: dist,
    fade_curve:  document.getElementById('ge-fade-curve')?.value  || 'linear',
    dist_blend:  document.getElementById('ge-dist-blend')?.value  || 'dominant',
  };

  // Section F — inflate
  const inflateVal = parseFloat(document.getElementById('ge-inflate')?.value);
  if (!isNaN(inflateVal) && inflateVal > 1) golem.inflate = inflateVal;
  if (_geVec.inflatedims) golem.inflate_dims = _geVec.inflatedims;

  // Section F — tame outliers (clip_sigma)
  const tameEl = document.getElementById('ge-tame-outliers');
  if (tameEl && tameEl.checked) {
    const clipSig = parseFloat(document.getElementById('ge-clip-sigma')?.value);
    if (!isNaN(clipSig) && clipSig > 0) golem.clip_sigma = clipSig;
  }
  if (_geVec.clipsigmadims) golem.clip_sigma_dims = _geVec.clipsigmadims;

  // Section I — per-dim starting values (cold_start_bias override)
  const _svBias = {};
  DIM_NAMES.forEach((name, i) => {
    const el = document.getElementById(`ge-sv-${i}`);
    if (el && el.value.trim() !== '') {
      const v = parseFloat(el.value);
      if (!isNaN(v)) _svBias[name] = v;
    }
  });
  if (Object.keys(_svBias).length > 0) golem.cold_start_bias = _svBias;

  // Distribution config
  if (_geVec.dist_config && Object.keys(_geVec.dist_config).length > 0)
    Object.assign(golem, _geVec.dist_config);

  if (engine === 'kalman') {
    golem.lam         = parseFloat(document.getElementById('ge-lam')?.value)         ?? 0.80;
    golem.A1          = parseFloat(document.getElementById('ge-A1')?.value)          ?? 0.70;
    golem.A2          = parseFloat(document.getElementById('ge-A2')?.value)          ?? 0.20;
    golem.Q_scale     = parseFloat(document.getElementById('ge-Q-scale')?.value)     ?? 1.00;
    golem.R_scale     = parseFloat(document.getElementById('ge-R-scale')?.value)     ?? 1.00;
    golem.obs_weight  = parseFloat(document.getElementById('ge-obs-weight')?.value)  ?? 1.00;
    golem.drama_curve = document.getElementById('ge-drama-curve')?.value || 'linear';
    golem.rw_scatter  = parseFloat(document.getElementById('ge-rw-scatter')?.value)  || 0;
    // New Kalman params
    const innovDecay = parseFloat(document.getElementById('ge-innov-decay')?.value);
    if (!isNaN(innovDecay)) golem.innov_decay = innovDecay;
    const gammaW = parseFloat(document.getElementById('ge-gamma-w')?.value);
    if (!isNaN(gammaW) && gammaW < 1) golem.gamma_w = gammaW;
    const xiEl = document.getElementById('ge-xi-regime');
    if (xiEl?.value !== '') golem.xi_regime = parseFloat(xiEl.value);
    // Vector params
    if (_geVec.a1dims)    golem.A1_dims           = _geVec.a1dims;
    if (_geVec.a2dims)    golem.A2_dims           = _geVec.a2dims;
    if (_geVec.qbase)     golem.Q_base            = _geVec.qbase;
    if (_geVec.obswtdims) golem.obs_weight_dims   = _geVec.obswtdims;
    if (_geVec.fpmask)    golem.fp_mask           = _geVec.fpmask;
    if (_geVec.fpscale)   golem.fp_scale          = _geVec.fpscale;
  } else if (engine === 'random_walk') {
    const _D = DIM_NAMES.length;
    golem.step_size     = Array.from({length: _D}, (_, i) => parseFloat(document.getElementById(`ge-rw-step-${i}`)?.value)  || 0);
    golem.drift         = Array.from({length: _D}, (_, i) => parseFloat(document.getElementById(`ge-rw-drift-${i}`)?.value) || 0);
    golem.mr_dims       = Array.from({length: _D}, (_, i) => parseFloat(document.getElementById(`ge-rw-mr-${i}`)?.value)    || 0);
    golem.boundary_mode = document.getElementById('ge-rw-boundary')?.value || 'clip';
    // New RW params
    if (_geVec.mrtarget)    golem.mr_target   = _geVec.mrtarget;
    if (_geVec.correlation) golem.correlation = _geVec.correlation;
    const bpEl = document.getElementById('ge-breath-period');
    const baEl = document.getElementById('ge-breath-amp');
    const osEl = document.getElementById('ge-omega-step-scale');
    if (bpEl?.value !== '') golem.breath_period     = parseFloat(bpEl.value);
    if (baEl?.value !== '') golem.breath_amp         = parseFloat(baEl.value);
    if (osEl?.value !== '') golem.omega_step_scale   = parseFloat(osEl.value);
  } else if (engine === 'discrete') {
    golem.state = {};
    DIM_NAMES.forEach((name, i) => {
      const v = parseFloat(document.getElementById(`ge-disc-${i}`)?.value);
      if (!isNaN(v)) golem.state[name] = v;
    });
  }

  const activePreset = document.querySelector('.ge-preset-btn.active');
  if (activePreset) golem.character = activePreset.dataset.preset;
  return golem;
}

function _populateEditorFromGolem(golem) {
  const engine   = golem.type || 'kalman';

  document.querySelectorAll('.ge-engine-btn').forEach(b => b.classList.remove('active'));
  const eBtn = document.querySelector(`.ge-engine-btn[data-engine="${engine}"]`);
  if (eBtn) eBtn.classList.add('active');
  document.getElementById('ge-params-kalman').style.display  = engine === 'kalman' ? '' : 'none';
  document.getElementById('ge-params-rw').style.display      = engine === 'random_walk' ? '' : 'none';
  const discEl = document.getElementById('ge-params-discrete');
  if (discEl) discEl.style.display = engine === 'discrete' ? '' : 'none';
  const presetSec = document.getElementById('ge-presets-section');
  if (presetSec) presetSec.style.display = engine === 'discrete' ? 'none' : '';

  _setActiveDist(golem.distribution || 'gaussian');
  if (engine !== 'discrete') _refreshPresets(engine);

  if (engine === 'discrete') {
    // Populate discrete state values
    const st = golem.state || {};
    DIM_NAMES.forEach((name, i) => {
      const el = document.getElementById(`ge-disc-${i}`);
      if (el) el.value = st[name] ?? DIM_DEFAULTS[name] ?? 0;
    });
  } else if (engine === 'kalman') {
    _setSlider('ge-lam',        golem.lam        ?? 0.80, 'ge-lam-val');
    _setSlider('ge-A1',         golem.A1         ?? 0.70, 'ge-A1-val');
    _setSlider('ge-A2',         golem.A2         ?? 0.20, 'ge-A2-val');
    _setSlider('ge-Q-scale',    golem.Q_scale    ?? 1.00, 'ge-Q-scale-val');
    _setSlider('ge-obs-weight', golem.obs_weight ?? 1.00, 'ge-obs-weight-val');
    _setSlider('ge-R-scale',    golem.R_scale    ?? 1.00, 'ge-R-scale-val');
    _setSlider('ge-rw-scatter', golem.rw_scatter ?? 0.00, 'ge-rw-scatter-val');
    _setVal('ge-drama-curve', golem.drama_curve ?? 'linear');
    // New Kalman params
    _setVal('ge-innov-decay', golem.innov_decay ?? 0.7);
    _setSlider('ge-gamma-w', golem.gamma_w ?? 1.0, 'ge-gamma-w-val');
    const xiEl = document.getElementById('ge-xi-regime');
    if (xiEl) xiEl.value = golem.xi_regime != null ? golem.xi_regime : '';
    // Vector params
    _geVec.a1dims    = golem.A1_dims           || null;
    _geVec.a2dims    = golem.A2_dims           || null;
    _geVec.qbase     = golem.Q_base            || null;
    _geVec.obswtdims = golem.obs_weight_dims   || null;
    _geVec.fpmask    = golem.fp_mask           || null;
    _geVec.fpscale   = golem.fp_scale          || null;
    _updateVecDisplay('a1dims',    'ge-a1dims-display');
    _updateVecDisplay('a2dims',    'ge-a2dims-display');
    _updateVecDisplay('qbase',     'ge-qbase-display');
    _updateVecDisplay('obswtdims', 'ge-obswtdims-display');
    _updateVecDisplay('fpmask',    'ge-fpmask-display');
    _updateVecDisplay('fpscale',   'ge-fpscale-display');
  } else if (engine === 'random_walk') {
    const ss = golem.step_size || _RW_SS_DEF;
    const dr = golem.drift     || _RW_ZERO;
    const mr = golem.mr_dims   || _RW_ZERO;
    for (let i = 0; i < DIM_NAMES.length; i++) {
      _setVal(`ge-rw-step-${i}`,  ss[i]);
      _setVal(`ge-rw-drift-${i}`, dr[i]);
      _setVal(`ge-rw-mr-${i}`,    mr[i]);
    }
    _setVal('ge-rw-boundary', golem.boundary_mode || 'clip');
    // New RW params
    const bpEl = document.getElementById('ge-breath-period');
    const baEl = document.getElementById('ge-breath-amp');
    const osEl = document.getElementById('ge-omega-step-scale');
    if (bpEl) bpEl.value = golem.breath_period     != null ? golem.breath_period     : '';
    if (baEl) baEl.value = golem.breath_amp         != null ? golem.breath_amp         : '';
    if (osEl) osEl.value = golem.omega_step_scale   != null ? golem.omega_step_scale   : '';
    _geVec.mrtarget    = golem.mr_target    || null;
    _geVec.correlation = golem.correlation  || null;
    _updateVecDisplay('mrtarget', 'ge-mrtarget-display');
    const corrEl = document.getElementById('ge-corr-display');
    if (corrEl) corrEl.textContent = _geVec.correlation ? 'custom' : '—';
  }

  // Section F
  _setVal('ge-inflate', golem.inflate ?? 1.0);
  _geVec.inflatedims = golem.inflate_dims || null;
  _updateVecDisplay('inflatedims', 'ge-inflatedims-display');
  // Tame outliers
  const tameEl = document.getElementById('ge-tame-outliers');
  if (tameEl) tameEl.checked = (golem.clip_sigma != null);
  _setVal('ge-clip-sigma', golem.clip_sigma ?? 3.0);
  _geVec.clipsigmadims = golem.clip_sigma_dims || null;
  _updateVecDisplay('clipsigmadims', 'ge-clipsigmadims-display');
  // Starting values
  const _csb = golem.cold_start_bias || {};
  DIM_NAMES.forEach((name, i) => {
    const el = document.getElementById(`ge-sv-${i}`);
    if (el) el.value = (_csb[name] != null) ? _csb[name] : '';
  });
  // Track character for placeholder display even if no preset button was clicked yet
  if (golem.character) _lastPresetName = golem.character;
  if (typeof _refreshStartValPlaceholders === 'function') _refreshStartValPlaceholders();
  // Distribution config
  _geVec.dist_config = {};
  ['df','bimodal_sep','beta_a','beta_b','mixture_p','spike_scale','skew',
   'cauchy_clip','trunc_lo','trunc_hi','trunc_base_dist',
   'dist_dims','dist_dims_params','salience_conditioned'].forEach(k => {
    if (golem[k] !== undefined) _geVec.dist_config[k] = golem[k];
  });

  // Section H
  _setVal('ge-fade-curve', golem.fade_curve || 'linear');
  _setVal('ge-dist-blend', golem.dist_blend || 'dominant');

  _setVal('ge-from',    golem.from     ?? 0);
  _setVal('ge-to',      golem.to       ?? 0);
  _setVal('ge-weight',  golem.weight   ?? 1.0);
  _setVal('ge-fadein',  golem.fade_in  ?? 0);
  _setVal('ge-fadeout', golem.fade_out ?? 0);

  document.querySelectorAll('.ge-preset-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.preset === golem.character);
  });
}

function _selectGolem(idx) {
  _selectedGolemIdx = idx;
  _populateEditorFromGolem(interpState.golems[idx]);
  _renderGolemCards();
  drawGolemTimeline();
}

function _newGolem() {
  // Prepare editor with defaults
  Object.keys(_geVec).forEach(k => { _geVec[k] = k === 'dist_config' ? {} : null; });
  _applyPreset('lyrical', 'kalman');
  const dur = state.duration || interpState.scoreDuration || 60;
  const gTo = Math.min(dur * 0.25, 30);
  _setVal('ge-from',    0);
  _setVal('ge-to',      gTo);
  _setVal('ge-weight',  1.0);
  _setVal('ge-fadein',  0);
  _setVal('ge-fadeout', 0);
  _setSlider('ge-rw-scatter', 0, 'ge-rw-scatter-val');

  // Push a new golem immediately and select it
  const golem = _readGolemEditor();
  golem.from = 0;
  golem.to   = parseFloat(gTo.toFixed(2));
  golem.character = golem.character || 'lyrical';
  const charCount = interpState.golems.filter(g => g.character === golem.character).length;
  golem.name = golem.character + ' #' + (charCount + 1);
  interpState.golems.push(golem);
  interpState.golems.sort((a, b) => a.from - b.from);
  _selectedGolemIdx = interpState.golems.indexOf(golem);
  _renderGolemCards();
  _redrawAllInterpCanvases();
}

// ─── Golem timeline canvas ────────────────────────────────────────────────────
// Unified redraw: waveform first (resizes to current #canvas-wrap width),
// then golem timeline which will match it.
function _redrawAllInterpCanvases() {
  if (typeof resizeCanvas === 'function') resizeCanvas();
  drawGolemTimeline();
}

function drawGolemTimeline() {
  const canvas = document.getElementById('golem-canvas');
  if (!canvas) return;

  const wrap = canvas.parentElement;
  const r = wrap ? wrap.getBoundingClientRect() : null;
  const W = (r && r.width > 0) ? Math.round(r.width) : 800;
  const H = 28;
  canvas.width  = W;
  canvas.height = H;

  const c   = canvas.getContext('2d');
  const dur = state.duration || interpState.scoreDuration || 60;

  // Background
  c.fillStyle = '#111';
  c.fillRect(0, 0, W, H);

  // Grid lines — thin, no labels (too tight at 28px)
  const step = dur <= 30 ? 5 : dur <= 120 ? 10 : 30;
  c.strokeStyle = '#222';
  c.lineWidth = 1;
  for (let t = 0; t <= dur; t += step) {
    const x = Math.round((t / dur) * W);
    c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke();
  }

  // Golem blocks
  const golems = interpState.golems || [];
  for (let gi = 0; gi < golems.length; gi++) {
    const g   = golems[gi];
    const x1  = Math.round((g.from / dur) * W);
    const x2  = Math.round((g.to   / dur) * W);
    const bw  = Math.max(4, x2 - x1);
    const col = GOLEM_COLORS[g.character] || '#3a4a6a';
    const lbl = GOLEM_LABEL_COLORS[g.character] || '#8ab';

    c.fillStyle = col;
    c.globalAlpha = 0.85;
    c.fillRect(x1, 3, bw, H - 6);
    c.globalAlpha = 1;

    c.strokeStyle = gi === _selectedGolemIdx ? '#fff' : lbl;
    c.lineWidth   = gi === _selectedGolemIdx ? 2 : 1;
    c.strokeRect(x1, 3, bw, H - 6);

    if (bw > 40) {
      c.fillStyle = lbl;
      c.font = '9px monospace';
      c.fillText(g.character || 'golem', x1 + 4, H - 9);
    }
  }
}

// ─── Golem canvas interaction ─────────────────────────────────────────────────
const _EDGE_PX = 8; // px near left/right edge that triggers resize

function _golemHitTest(canvas, x) {
  // Returns { idx, mode: 'move'|'resize-left'|'resize-right' } or null
  const dur = state.duration || interpState.scoreDuration || 60;
  const W = canvas.getBoundingClientRect().width || canvas.width;
  for (let i = interpState.golems.length - 1; i >= 0; i--) {
    const g  = interpState.golems[i];
    const x1 = (g.from / dur) * W;
    const x2 = (g.to   / dur) * W;
    if (x < x1 - _EDGE_PX || x > x2 + _EDGE_PX) continue;
    if (x <= x1 + _EDGE_PX) return { idx: i, mode: 'resize-left'  };
    if (x >= x2 - _EDGE_PX) return { idx: i, mode: 'resize-right' };
    return { idx: i, mode: 'move' };
  }
  return null;
}

function _golemCanvasMousedown(e) {
  const canvas = document.getElementById('golem-canvas');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const x    = e.clientX - rect.left;
  const dur  = state.duration || interpState.scoreDuration || 60;

  const hit = _golemHitTest(canvas, x);
  if (hit) {
    const g = interpState.golems[hit.idx];
    _golemDrag = {
      mode: hit.mode, golemIdx: hit.idx,
      startX: x,
      origFrom: g.from, origTo: g.to,
    };
  } else {
    _golemDrag = { mode: 'create', startX: x, startT: (x / rect.width) * dur };
  }
}

function _golemCanvasMousemove(e) {
  const canvas = document.getElementById('golem-canvas');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const x    = e.clientX - rect.left;
  const dur  = state.duration || interpState.scoreDuration || 60;

  if (_golemDrag && _golemDrag.mode !== 'create') {
    const dx = x - _golemDrag.startX;
    const dt = (dx / rect.width) * dur;
    const g  = interpState.golems[_golemDrag.golemIdx];
    if (_golemDrag.mode === 'move') {
      const span    = _golemDrag.origTo - _golemDrag.origFrom;
      let newFrom   = Math.max(0, _golemDrag.origFrom + dt);
      let newTo     = newFrom + span;
      if (newTo > dur) { newTo = dur; newFrom = dur - span; }
      g.from = parseFloat(newFrom.toFixed(3));
      g.to   = parseFloat(newTo.toFixed(3));
    } else if (_golemDrag.mode === 'resize-left') {
      g.from = parseFloat(Math.max(0, Math.min((x / rect.width) * dur, g.to - 0.1)).toFixed(3));
    } else if (_golemDrag.mode === 'resize-right') {
      g.to = parseFloat(Math.max(g.from + 0.1, Math.min((x / rect.width) * dur, dur)).toFixed(3));
    }
    // Live-update editor from/to if this is the selected golem
    if (_golemDrag.golemIdx === _selectedGolemIdx) {
      _setVal('ge-from', g.from);
      _setVal('ge-to',   g.to);
      // Update card header time label live
      const card = document.querySelector(`.golem-card.selected .gc-time`);
      if (card) card.textContent = `${g.from.toFixed(1)}–${g.to.toFixed(1)}s`;
    }
    drawGolemTimeline();
    return;
  }

  // Hover cursor (no drag)
  if (!_golemDrag) {
    const hit = _golemHitTest(canvas, x);
    if (!hit)                           canvas.style.cursor = 'crosshair';
    else if (hit.mode === 'move')       canvas.style.cursor = 'grab';
    else                                canvas.style.cursor = 'ew-resize';
  }
}

function _golemFinalizeDrag(e) {
  if (!_golemDrag) return;
  const canvas = document.getElementById('golem-canvas');

  if (_golemDrag.mode === 'move' || _golemDrag.mode === 'resize-left' || _golemDrag.mode === 'resize-right') {
    const dragged = interpState.golems[_golemDrag.golemIdx];
    interpState.golems.sort((a, b) => a.from - b.from);
    const newIdx = interpState.golems.indexOf(dragged);
    _golemDrag = null;
    _selectedGolemIdx = newIdx;
    _renderGolemCards();
    drawGolemTimeline();
    return;
  }

  // mode === 'create'
  if (!canvas) { _golemDrag = null; return; }
  const rect  = canvas.getBoundingClientRect();
  const x     = (e.clientX || 0) - rect.left;
  const dur   = state.duration || interpState.scoreDuration || 60;
  const endT  = (x / rect.width) * dur;
  const from  = Math.max(0, Math.min(_golemDrag.startT, endT));
  const to    = Math.max(0, Math.max(_golemDrag.startT, endT));
  _golemDrag  = null;

  if (to - from < 0.1) {
    // Click — select or deselect
    const clickT = (x / rect.width) * dur;
    let hit = -1;
    for (let i = interpState.golems.length - 1; i >= 0; i--) {
      const g = interpState.golems[i];
      if (clickT >= g.from && clickT <= g.to) { hit = i; break; }
    }
    if (hit >= 0) {
      _selectGolem(hit);
    } else {
      _selectedGolemIdx = null;
      _renderGolemCards();
      drawGolemTimeline();
    }
    return;
  }

  const golem = _readGolemEditor();
  golem.from  = parseFloat(from.toFixed(2));
  golem.to    = parseFloat(to.toFixed(2));
  interpState.golems.push(golem);
  const charCount = interpState.golems.filter(g => g.character === golem.character).length;
  golem.name  = golem.character + ' #' + charCount;
  interpState.golems.sort((a, b) => a.from - b.from);
  _selectedGolemIdx = interpState.golems.indexOf(golem);
  _renderGolemCards();
  _redrawAllInterpCanvases();
}

// ─── Custom character management ──────────────────────────────────────────────
function _updateGCharOptions() {
  const gTypeEl = document.getElementById('g-type');
  const gCharEl = document.getElementById('g-char');
  if (!gTypeEl || !gCharEl) return;
  const chars = _allCharsForType(gTypeEl.value);
  gCharEl.innerHTML = chars.map(c => `<option value="${c}">${c}</option>`).join('');
}

function _allCharsForType(type) {
  const builtin = CHARS_BY_TYPE[type] || KALMAN_CHARS;
  const custom  = Object.keys(_customChars[type] || {});
  return [...builtin, ...custom];
}

async function loadCustomChars() {
  try {
    const res  = await fetch('/characters');
    const data = await res.json();
    _customChars.kalman      = data.kalman      || {};
    _customChars.random_walk = data.random_walk || {};
    _renderCustomCharList();
    _updateGCharOptions();
    _renderGolemListCol();
    _refreshPresets(_getActiveEngine());
  } catch (e) { /* server may not be running */ }
}

function _renderCustomCharList() {
  const el = document.getElementById('cc-list');
  if (!el) return;
  const rows = [];
  for (const [type, chars] of [['kalman', _customChars.kalman], ['random_walk', _customChars.random_walk]]) {
    for (const name of Object.keys(chars)) {
      const badge = type === 'kalman'
        ? '<span style="color:#7b70c8;font-size:9px;">K</span>'
        : '<span style="color:#c8a050;font-size:9px;">RW</span>';
      rows.push(`<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px;">
        ${badge}
        <span style="flex:1;font-size:11px;color:#aaa;">${name}</span>
        <button onclick="ccLoad('${name}','${type}')" style="font-size:9px;padding:1px 4px;color:#555;border-color:#333;">edit</button>
        <button onclick="ccDelete('${name}','${type}')" style="font-size:9px;padding:1px 4px;color:#c87070;border-color:#c87070;">✕</button>
      </div>`);
    }
  }
  el.innerHTML = rows.length
    ? rows.join('')
    : '<div style="color:#333;font-size:10px;">No custom characters yet.</div>';
}

function ccUpdateFields() {
  const type = (document.getElementById('cc-type') || {}).value;
  const kf   = document.getElementById('cc-kalman-fields');
  const rf   = document.getElementById('cc-rw-fields');
  if (kf) kf.style.display = type === 'kalman' ? '' : 'none';
  if (rf) rf.style.display = type === 'random_walk' ? '' : 'none';
}

function ccToggleMixture() {
  const dist = document.getElementById('cc-sample-dist')?.value;
  const el   = document.getElementById('cc-mixture-fields');
  if (el) el.style.display = dist === 'mixture' ? '' : 'none';
}

function ccToggleRWMixture() {
  const dist = document.getElementById('cc-rw-dist')?.value;
  const el   = document.getElementById('cc-rw-mixture-fields');
  if (el) el.style.display = dist === 'mixture' ? '' : 'none';
}

const _CORR_PRESETS = {
  none:        null,
  gain_bright: [[1,0.7,0,0,0],[0.7,1,0,0,0],[0,0,1,0,0],[0,0,0,1,0],[0,0,0,0,1]],
  expressive:  [[1,0.6,0,0.5,0],[0.6,1,0,0.4,0],[0,0,1,0,0],[0.5,0.4,0,1,0],[0,0,0,0,1]],
  temporal:    [[1,0,0.6,0,0],[0,1,0,0,0],[0.6,0,1,0,0],[0,0,0,1,0],[0,0,0,0,1]],
};

function ccLoad(name, type) {
  const params = (_customChars[type] || {})[name];
  if (!params) return;
  const nameEl = document.getElementById('cc-name');
  const typeEl = document.getElementById('cc-type');
  if (nameEl) nameEl.value = name;
  if (typeEl) { typeEl.value = type; ccUpdateFields(); }
  if (type === 'kalman') {
    _setVal('cc-A1',            params.A1);
    _setVal('cc-A2',            params.A2);
    _setVal('cc-Qscale',        params.Q_scale);
    _setVal('cc-Rscale',        params.R_scale);
    _setVal('cc-lam',           params.lam);
    _setVal('cc-obs-weight',    params.obs_weight ?? 1.0);
    _setVal('cc-drama-curve',   params.drama_curve ?? 'linear');
    _setVal('cc-sample-dist',   params.sample_dist ?? 'gaussian');
    _setVal('cc-mixture-p',     params.mixture_p ?? 0.05);
    _setVal('cc-mixture-scale', params.mixture_scale ?? 4.0);
    ccToggleMixture();
    if (params.A1_dims) params.A1_dims.forEach((v, i) => _setVal(`cc-a1d-${i}`, v));
    if (params.A2_dims) params.A2_dims.forEach((v, i) => _setVal(`cc-a2d-${i}`, v));
  } else {
    const step  = params.step_size || _RW_SS_DEF;
    const drift = params.drift      || _RW_ZERO;
    const mr    = params.mr_dims    || Array(5).fill(params.mean_reversion||0);
    for (let i = 0; i < DIM_NAMES.length; i++) {
      _setVal(`cc-step-${i}`,  step[i]);
      _setVal(`cc-drift-${i}`, drift[i]);
      _setVal(`cc-mr-${i}`,    mr[i]);
    }
    _setVal('cc-rw-dist',          params.distribution  ?? 'gaussian');
    _setVal('cc-boundary',         params.boundary_mode ?? 'clip');
    _setVal('cc-rw-mixture-p',     params.mixture_p     ?? 0.05);
    _setVal('cc-rw-mixture-scale', params.mixture_scale ?? 4.0);
    const corrJson = JSON.stringify(params.correlation || null);
    let preset = 'none';
    for (const [k, v] of Object.entries(_CORR_PRESETS)) {
      if (JSON.stringify(v) === corrJson) { preset = k; break; }
    }
    _setVal('cc-corr-preset', preset);
    ccToggleRWMixture();
  }
}

async function ccDelete(name, type) {
  if (!confirm(`Delete custom character "${name}"?`)) return;
  const res  = await fetch('/characters', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, type, delete: true }),
  });
  const data = await res.json();
  const st   = document.getElementById('cc-status');
  if (data.ok) {
    delete (_customChars[type] || {})[name];
    _renderCustomCharList();
    _updateGCharOptions();
    _renderGolemListCol();
    _refreshPresets(_getActiveEngine());
    if (st) st.textContent = `Deleted "${name}"`;
  } else {
    if (st) st.textContent = data.error || 'Error';
  }
}

async function ccSave() {
  const name = (document.getElementById('cc-name') || {}).value.trim();
  const type = (document.getElementById('cc-type') || {}).value;
  const st   = document.getElementById('cc-status');
  if (!name) { if (st) st.textContent = 'Name required'; return; }

  const _n  = id => parseFloat(document.getElementById(id)?.value) || 0;
  const _s  = id => document.getElementById(id)?.value || '';
  const _nz = (id, def) => { const v = parseFloat(document.getElementById(id)?.value); return isNaN(v) ? def : v; };
  let params;
  if (type === 'kalman') {
    const a1dims = [0,1,2,3,4].map(i => document.getElementById(`cc-a1d-${i}`)?.value.trim());
    const a2dims = [0,1,2,3,4].map(i => document.getElementById(`cc-a2d-${i}`)?.value.trim());
    const A1_dims = a1dims.some(v => v !== '') ? a1dims.map(v => v !== '' ? parseFloat(v) : _n('cc-A1')) : null;
    const A2_dims = a2dims.some(v => v !== '') ? a2dims.map(v => v !== '' ? parseFloat(v) : _n('cc-A2')) : null;
    params = {
      A1: _n('cc-A1'), A2: _n('cc-A2'),
      Q_scale: _n('cc-Qscale'), R_scale: _n('cc-Rscale'), lam: _n('cc-lam'),
      obs_weight:    _nz('cc-obs-weight', 1.0),
      drama_curve:   _s('cc-drama-curve') || 'linear',
      sample_dist:   _s('cc-sample-dist') || 'gaussian',
      mixture_p:     _nz('cc-mixture-p', 0.05),
      mixture_scale: _nz('cc-mixture-scale', 4.0),
    };
    if (A1_dims) params.A1_dims = A1_dims;
    if (A2_dims) params.A2_dims = A2_dims;
  } else {
    const corrPreset = _s('cc-corr-preset') || 'none';
    params = {
      step_size:      [0,1,2,3,4].map(i => _n(`cc-step-${i}`)),
      drift:          [0,1,2,3,4].map(i => _n(`cc-drift-${i}`)),
      mr_dims:        [0,1,2,3,4].map(i => _n(`cc-mr-${i}`)),
      mean_reversion: 0,
      distribution:   _s('cc-rw-dist')  || 'gaussian',
      boundary_mode:  _s('cc-boundary') || 'clip',
      correlation:    _CORR_PRESETS[corrPreset] ?? null,
      mixture_p:      _nz('cc-rw-mixture-p', 0.05),
      mixture_scale:  _nz('cc-rw-mixture-scale', 4.0),
    };
  }

  const res  = await fetch('/characters', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, type, params }),
  });
  const data = await res.json();
  if (data.ok) {
    if (!_customChars[type]) _customChars[type] = {};
    _customChars[type][name] = params;
    _renderCustomCharList();
    _updateGCharOptions();
    _renderGolemListCol();
    _refreshPresets(_getActiveEngine());
    if (st) st.textContent = `Saved "${name}"`;
  } else {
    if (st) st.textContent = data.error || 'Error saving';
  }
}

// ─── Distribution popup ───────────────────────────────────────────────────────
const _DIST_INFO = {
  gaussian:    { label:'Natural (Gaussian)',  params:[] },
  laplace:     { label:'Edgy (Laplace)',      params:[] },
  cauchy:      { label:'Wild (Cauchy)',       params:['cauchy_clip'] },
  uniform:     { label:'Even (Uniform)',      params:[] },
  beta:        { label:'Curved (Beta)',       params:['beta_a','beta_b'] },
  student_t:   { label:'Heavy (Student-t)',   params:['df'] },
  bimodal:     { label:'Bipolar (Bimodal)',   params:['bimodal_sep'] },
  mixture:     { label:'Bursting (Mixture)',  params:['mixture_p','spike_scale'] },
  skew_normal: { label:'Skewed (Skew-normal)', params:['skew'] },
  truncated:   { label:'Bounded+ (Truncated)', params:['trunc_base_dist','trunc_lo','trunc_hi'] },
};

const _DIST_PARAM_DEFS = {
  df:              { label:'Degrees of freedom (df)', min:1, max:50, step:0.5, default:3 },
  bimodal_sep:     { label:'Pole separation (σ units)', min:0, max:3, step:0.05, default:0.75 },
  beta_a:          { label:'Shape α (a)', min:0.5, max:10, step:0.1, default:2 },
  beta_b:          { label:'Shape β (b)', min:0.5, max:10, step:0.1, default:2 },
  mixture_p:       { label:'Spike probability', min:0, max:0.5, step:0.01, default:0.05 },
  spike_scale:     { label:'Spike scale (×σ)', min:1, max:20, step:0.5, default:4 },
  skew:            { label:'Skewness', min:-5, max:5, step:0.1, default:0 },
  cauchy_clip:     { label:'Clip threshold (σ)', min:1, max:20, step:0.5, default:5 },
  trunc_lo:        { label:'Lower bound (σ)', min:-10, max:0, step:0.1, default:-3 },
  trunc_hi:        { label:'Upper bound (σ)', min:0,  max:10, step:0.1, default:3 },
  trunc_base_dist: { label:'Base distribution', type:'select',
                     options:['gaussian','laplace','student_t'], default:'gaussian' },
};

function _drawDistCanvas(canvasId, distName, params) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const W = canvas.width, H = canvas.height;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle = '#0d0d0d';
  ctx.fillRect(0,0,W,H);

  // Normalised PDF (±3σ range mapped to canvas width)
  const N = 200;
  const xs = Array.from({length:N}, (_,i) => -3 + 6*i/(N-1));
  let ys;
  const df = params.df ?? 3;
  const sep = params.bimodal_sep ?? 0.75;
  const a = params.beta_a ?? 2, b_s = params.beta_b ?? 2;
  const mp = params.mixture_p ?? 0.05;
  const skew = params.skew ?? 0;

  if (distName === 'gaussian' || distName === 'truncated') {
    ys = xs.map(x => Math.exp(-0.5*x*x));
  } else if (distName === 'laplace') {
    const s = Math.SQRT2;
    ys = xs.map(x => Math.exp(-Math.abs(x)*s));
  } else if (distName === 'cauchy') {
    ys = xs.map(x => 1/(1+x*x));
  } else if (distName === 'uniform') {
    const r = Math.sqrt(3);
    ys = xs.map(x => Math.abs(x) <= r ? 1 : 0);
  } else if (distName === 'beta') {
    // Symmetric stretch
    ys = xs.map(x => {
      const u = (x+3)/6; if (u<=0||u>=1) return 0;
      return Math.pow(u,a-1)*Math.pow(1-u,b_s-1);
    });
  } else if (distName === 'student_t') {
    ys = xs.map(x => Math.pow(1+x*x/df, -(df+1)/2));
  } else if (distName === 'bimodal') {
    ys = xs.map(x => Math.exp(-0.5*(x-sep)**2) + Math.exp(-0.5*(x+sep)**2));
  } else if (distName === 'mixture') {
    ys = xs.map(x => (1-mp)*Math.exp(-0.5*x*x) + mp*0.2*Math.exp(-0.5*(x/4)**2));
  } else if (distName === 'skew_normal') {
    ys = xs.map(x => {
      const phi = Math.exp(-0.5*x*x)/Math.sqrt(2*Math.PI);
      const Phi = 0.5*(1+Math.sign(skew*x)*Math.sqrt(1-Math.exp(-2*(skew*x)**2/Math.PI)));
      return 2*phi*Phi;
    });
  } else {
    ys = xs.map(x => Math.exp(-0.5*x*x));
  }

  const maxY = Math.max(...ys, 0.001);
  ctx.beginPath();
  ctx.strokeStyle = '#6a8aaa';
  ctx.lineWidth = 1.5;
  xs.forEach((x, i) => {
    const px = (i / (N-1)) * W;
    const py = H - 4 - (ys[i]/maxY) * (H-8);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();
  // Centre line
  ctx.beginPath();
  ctx.strokeStyle = '#2a2a2a';
  ctx.lineWidth = 1;
  ctx.setLineDash([3,3]);
  ctx.moveTo(W/2, 0); ctx.lineTo(W/2, H);
  ctx.stroke();
  ctx.setLineDash([]);
}

function _openDistPopup() {
  const currentDist = _getActiveDist();
  const cfg = _geVec.dist_config || {};

  const distBtns = Object.keys(_DIST_INFO).map(d =>
    `<button class="ge-dist-btn dp-dist-btn${d===currentDist?' active':''}" data-dist="${d}"
             style="font-size:10px;padding:2px 6px;margin:2px;">${_DIST_INFO[d].label.split('(')[0].trim()}</button>`
  ).join('');

  const paramsHTML = (dist) => {
    const info = _DIST_INFO[dist] || {};
    return (info.params || []).map(pkey => {
      const def = _DIST_PARAM_DEFS[pkey];
      if (!def) return '';
      const val = cfg[pkey] ?? def.default;
      if (def.type === 'select') {
        const opts = def.options.map(o => `<option value="${o}"${o===val?' selected':''}>${o}</option>`).join('');
        return `<div class="popup-row"><label>${def.label}</label>
          <select id="dp-${pkey}" style="background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;font-size:11px;padding:2px 4px;">${opts}</select></div>`;
      }
      return `<div class="popup-row"><label>${def.label}</label>
        <input type="number" id="dp-${pkey}" value="${val}" min="${def.min}" max="${def.max}" step="${def.step}"
               style="width:80px;background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;font-size:11px;padding:2px 4px;"
               oninput="_drawDistCanvas('dp-canvas','${dist}',_dpCollectParams())" /></div>`;
    }).join('');
  };

  // Per-dimension distribution (Tier 2)
  const perDimHTML = `
    <div style="margin-top:8px;padding-top:6px;border-top:1px solid #1a1a1a;">
      <div style="cursor:pointer;display:flex;align-items:center;gap:4px;margin-bottom:4px;"
           onclick="toggleBarContent('dp-perdim-body','dp-perdim-chev')">
        <span id="dp-perdim-chev" style="font-size:9px;">&#9654;</span>
        <span style="font-size:9px;color:#555;text-transform:uppercase;letter-spacing:1px;">Per-dimension distribution</span>
      </div>
      <div id="dp-perdim-body" style="display:none;">
        ${DIM_NAMES.map((d,i) => {
          const dimDist = (cfg.dist_dims||[])[i] || '';
          const opts = [['','(same as regime)'],...Object.keys(_DIST_INFO).map(k=>[k,k])].map(
            ([v,l]) => `<option value="${v}"${v===dimDist?' selected':''}>${l}</option>`
          ).join('');
          return `<div class="popup-row"><label style="color:${DIM_COLORS[i]}">${d}</label>
            <select id="dp-dim-${i}" style="background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;font-size:10px;padding:2px 3px;">${opts}</select></div>`;
        }).join('')}
      </div>
    </div>`;

  // Salience-conditioned distribution (Tier 2)
  const sc = cfg.salience_conditioned || null;
  const salCondHTML = `
    <div style="margin-top:8px;padding-top:6px;border-top:1px solid #1a1a1a;">
      <div style="cursor:pointer;display:flex;align-items:center;gap:4px;margin-bottom:4px;"
           onclick="toggleBarContent('dp-salcond-body','dp-salcond-chev')">
        <span id="dp-salcond-chev" style="font-size:9px;">&#9654;</span>
        <span style="font-size:9px;color:#555;text-transform:uppercase;letter-spacing:1px;">Salience-conditioned distribution</span>
      </div>
      <div id="dp-salcond-body" style="display:none;">
        <div class="popup-row"><label>Enable</label>
          <input type="checkbox" id="dp-sc-enable" ${sc?'checked':''} /></div>
        <div class="popup-row"><label>ω threshold</label>
          <input type="number" id="dp-sc-threshold" value="${sc?.threshold??0.5}" min="0" max="1" step="0.05"
                 style="width:60px;background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;font-size:11px;padding:2px 4px;" /></div>
        ${['low','mid','high'].map(level => {
          const val = sc?.[`dist_${level}`]||'gaussian';
          const opts = Object.keys(_DIST_INFO).map(k=>`<option value="${k}"${k===val?' selected':''}>${k}</option>`).join('');
          return `<div class="popup-row"><label>dist @ ω-${level}</label>
            <select id="dp-sc-${level}" style="background:#1a1a1a;border:1px solid #2a2a2a;color:#aaa;font-size:10px;padding:2px 3px;">${opts}</select></div>`;
        }).join('')}
      </div>
    </div>`;

  const body = `
    <div style="font-size:10px;color:#555;margin-bottom:4px;">Distribution family</div>
    <div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:8px;">${distBtns}</div>
    <canvas id="dp-canvas" width="240" height="70"
            style="display:block;background:#0d0d0d;border:1px solid #1e1e1e;margin-bottom:8px;"></canvas>
    <div id="dp-params">${paramsHTML(currentDist)}</div>
    ${perDimHTML}${salCondHTML}`;

  showPopup('Configure distribution', body).then(() => {
    // Read selected dist
    const newDist = document.querySelector('.dp-dist-btn.active')?.dataset.dist || currentDist;
    _setActiveDist(newDist);

    // Read dist params
    const newCfg = {};
    const info = _DIST_INFO[newDist] || {};
    (info.params || []).forEach(pkey => {
      const el = document.getElementById(`dp-${pkey}`);
      if (!el) return;
      const def = _DIST_PARAM_DEFS[pkey];
      newCfg[pkey] = def?.type === 'select' ? el.value : parseFloat(el.value);
    });

    // Per-dimension distributions
    const dimDists = DIM_NAMES.map((_, i) => document.getElementById(`dp-dim-${i}`)?.value || '');
    if (dimDists.some(v => v)) newCfg.dist_dims = dimDists;

    // Salience-conditioned
    if (document.getElementById('dp-sc-enable')?.checked) {
      newCfg.salience_conditioned = {
        threshold: parseFloat(document.getElementById('dp-sc-threshold')?.value ?? 0.5),
        dist_low:  document.getElementById('dp-sc-low')?.value  || 'gaussian',
        dist_mid:  document.getElementById('dp-sc-mid')?.value  || 'laplace',
        dist_high: document.getElementById('dp-sc-high')?.value || 'student_t',
      };
    }

    _geVec.dist_config = newCfg;
  });

  // After popup shown, wire dist buttons and draw initial canvas
  setTimeout(() => {
    document.querySelectorAll('.dp-dist-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.dp-dist-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const d = btn.dataset.dist;
        document.getElementById('dp-params').innerHTML = paramsHTML(d);
        // Re-wire param inputs
        document.querySelectorAll('#dp-params input[type=number]').forEach(inp => {
          inp.addEventListener('input', () => _drawDistCanvas('dp-canvas', d, _dpCollectParams()));
        });
        _drawDistCanvas('dp-canvas', d, _dpCollectParams());
      });
    });
    _drawDistCanvas('dp-canvas', currentDist, cfg);
  }, 50);
}

// Collect current dist params from popup inputs
function _dpCollectParams() {
  const out = {};
  Object.keys(_DIST_PARAM_DEFS).forEach(k => {
    const el = document.getElementById(`dp-${k}`);
    if (!el) return;
    const def = _DIST_PARAM_DEFS[k];
    out[k] = def?.type === 'select' ? el.value : parseFloat(el.value);
  });
  return out;
}

// Refresh the starting-values placeholders based on the currently-selected character.
// Empty input = use default; placeholder text shows what the default would be.
function _refreshStartValPlaceholders() {
  const charName = _lastPresetName || '';
  const bias = CHAR_COLD_START_BIAS[charName] || {};
  DIM_NAMES.forEach((name, i) => {
    const el = document.getElementById(`ge-sv-${i}`);
    if (!el) return;
    const v = (bias[name] != null) ? bias[name] : (DIM_DEFAULTS[name] ?? 0);
    const valStr = Math.abs(v) >= 100 ? v.toFixed(0)
                 : Math.abs(v) >= 10  ? v.toFixed(1) : v.toFixed(2);
    el.placeholder = valStr;
  });
}

// ─── DOMContentLoaded wiring ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Populate discrete golem dimension inputs
  const discDimsEl = document.getElementById('ge-discrete-dims');
  if (discDimsEl) {
    discDimsEl.innerHTML = DIM_NAMES.map((name, i) => {
      const [lo, hi] = DIM_RANGES_DEFAULT[i];
      const def = DIM_DEFAULTS[name] ?? 0;
      return `<div style="display:flex;align-items:center;gap:4px;">
        <label style="font-size:9px;color:${DIM_COLORS[i]};width:70px;overflow:hidden;text-overflow:ellipsis;">${DIM_LABELS[i]}</label>
        <input id="ge-disc-${i}" type="number" value="${def}" step="0.01" min="${lo}" max="${hi}"
               style="flex:1;background:#1a1a1a;border:1px solid #2a2a2a;color:#ccc;padding:2px 4px;font-size:10px;" />
      </div>`;
    }).join('');
  }

  // Populate starting-values (cold_start_bias) inputs for Kalman golems
  const svDimsEl = document.getElementById('ge-startvals-dims');
  if (svDimsEl) {
    svDimsEl.innerHTML = DIM_NAMES.map((name, i) => {
      const [lo, hi] = DIM_RANGES_DEFAULT[i];
      return `<div style="display:flex;align-items:center;gap:4px;">
        <label style="font-size:9px;color:${DIM_COLORS[i]};width:70px;overflow:hidden;text-overflow:ellipsis;">${DIM_LABELS[i]}</label>
        <input id="ge-sv-${i}" type="number" placeholder="—" step="0.01" min="${lo}" max="${hi}"
               title="leave empty = use character default"
               style="flex:1;background:#1a1a1a;border:1px solid #2a2a2a;color:#ccc;padding:2px 4px;font-size:10px;" />
      </div>`;
    }).join('');
  }
  const svReset = document.getElementById('ge-startvals-reset');
  if (svReset) svReset.addEventListener('click', () => {
    DIM_NAMES.forEach((_, i) => {
      const el = document.getElementById(`ge-sv-${i}`);
      if (el) el.value = '';
    });
    _refreshStartValPlaceholders();
  });
  _refreshStartValPlaceholders();

  // Engine toggle buttons
  document.querySelectorAll('.ge-engine-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.ge-engine-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const eng = btn.dataset.engine;
      document.getElementById('ge-params-kalman').style.display  = eng === 'kalman' ? '' : 'none';
      document.getElementById('ge-params-rw').style.display      = eng === 'random_walk' ? '' : 'none';
      const discEl = document.getElementById('ge-params-discrete');
      if (discEl) discEl.style.display = eng === 'discrete' ? '' : 'none';
      const presetSec = document.getElementById('ge-presets-section');
      if (presetSec) presetSec.style.display = eng === 'discrete' ? 'none' : '';
      _lastPresetName = null;
      if (eng !== 'discrete') _refreshPresets(eng);
    });
  });

  // Distribution config popup button
  document.getElementById('ge-dist-config-btn')?.addEventListener('click', _openDistPopup);

  // Distribution buttons
  document.querySelectorAll('.ge-dist-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.ge-dist-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // New / Add / Update / Delete golem buttons
  document.getElementById('g-new-btn')?.addEventListener('click', _newGolem);

  document.getElementById('ge-add-btn')?.addEventListener('click', () => {
    const golem = _readGolemEditor();
    if (golem.to <= golem.from) { alert('end must be > start'); return; }
    interpState.golems.push(golem);
    const charCount = interpState.golems.filter(g => g.character === golem.character).length;
    golem.name = golem.character + ' #' + charCount;
    interpState.golems.sort((a, b) => a.from - b.from);
    _selectedGolemIdx = interpState.golems.indexOf(golem);
    _renderGolemCards();
    drawGolemTimeline();
  });

  document.getElementById('ge-update-btn')?.addEventListener('click', () => {
    if (_selectedGolemIdx === null || _selectedGolemIdx >= interpState.golems.length) return;
    const updated = _readGolemEditor();
    // Preserve the existing name on update
    updated.name = interpState.golems[_selectedGolemIdx].name;
    interpState.golems[_selectedGolemIdx] = updated;
    interpState.golems.sort((a, b) => a.from - b.from);
    _renderGolemCards();
    drawGolemTimeline();
  });

  document.getElementById('ge-delete-btn')?.addEventListener('click', () => {
    if (_selectedGolemIdx === null || _selectedGolemIdx >= interpState.golems.length) return;
    interpState.golems.splice(_selectedGolemIdx, 1);
    _selectedGolemIdx = null;
    _renderGolemCards();
    drawGolemTimeline();
  });

  // Canvas interaction (create / move / resize)
  const golemCanvas = document.getElementById('golem-canvas');
  if (golemCanvas) {
    golemCanvas.addEventListener('mousedown', _golemCanvasMousedown);
    golemCanvas.addEventListener('mousemove', _golemCanvasMousemove);
    golemCanvas.addEventListener('mouseleave', () => {
      if (!_golemDrag) golemCanvas.style.cursor = 'crosshair';
    });
  }
  // Finalize drag even if mouse released outside the canvas
  document.addEventListener('mouseup', _golemFinalizeDrag);


  // Custom character save
  document.getElementById('cc-save-btn')?.addEventListener('click', ccSave);
});
