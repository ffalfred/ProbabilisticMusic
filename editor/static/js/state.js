// ─── State ───────────────────────────────────────────────────────────────────
const state = {
  waveform: [],       // 2000 peak values
  duration: 0,
  filePath: "",
  currentTime: 0,
  samples: {},        // name → {from, to, color}
  dynamics: [],       // [{t, mark}] or [{from, to, mark}]
  events: [],         // [{sample, t, speed, gain_db, loop, reverse, fx, speeds}]
  tempo: [],          // [{from, to, mark, factor}]
  baseFx: [],         // [{type, ...params}] — fx on the base audio track
  fxRanges: [],       // [{from, to, fx: [...]}] — fx on a time range of the base
  phrases: [],        // [{from, to, label, gain_db, fade_in, fade_out, tempo_factor}]
  noteRel: [],        // [{type:"glissando"|"arpeggiate", from, to, label}]
  articulations: [],  // [{type:"staccato"|"legato"|"fermata"|"accent", t?, from?, to?, label?}]
  tracks:  [],        // [{name, path, gain_db, muted, waveform}] — track 0 = original file
  duckBase: { enabled: false, amount_db: -6,  attack: 0.01, release: 0.30 },
  duckKey:  { enabled: false, key: "",  amount_db: -10, attack: 0.01, release: 0.30 },
  autoMix:  { enabled: false, mode: "sqrt" },
  history: [],        // for undo
  v2config: {
    engine: 'v1',
    markov_mode: 'joint',
    markov_order: 2,
    covariance: 'diagonal',
    phrase_boundary: 'reset',
    history_decay: 0.7,
    seed: null,
  },
};

// ─── Engine selector wiring ───────────────────────────────────────────────────
function _syncV2Config() {
  const sel   = document.getElementById('engine-select');
  const panel = document.getElementById('v2-panel');
  const mode  = document.getElementById('v2-mode');
  const seed  = document.getElementById('v2-seed');
  const order = document.getElementById('v2-order');
  if (!sel) return;
  const isV2 = sel.value === 'v2';
  panel.style.display = isV2 ? 'inline-flex' : 'none';
  state.v2config.engine       = sel.value;
  state.v2config.markov_mode  = mode  ? mode.value  : 'joint';
  state.v2config.markov_order = order ? parseInt(order.value) || 2 : 2;
  const rawSeed = seed ? seed.value.trim() : '';
  state.v2config.seed = rawSeed === '' ? null : parseInt(rawSeed);
}

document.addEventListener('DOMContentLoaded', () => {
  const sel   = document.getElementById('engine-select');
  const mode  = document.getElementById('v2-mode');
  const seed  = document.getElementById('v2-seed');
  const order = document.getElementById('v2-order');
  if (sel)   sel.addEventListener('change', _syncV2Config);
  if (mode)  mode.addEventListener('change', _syncV2Config);
  if (seed)  seed.addEventListener('input',  _syncV2Config);
  if (order) order.addEventListener('input',  _syncV2Config);
  _syncV2Config();
});

const DYNAMIC_COLORS = {
  ppp: "#2244aa", pp: "#3355bb", p: "#5577cc",
  mp: "#7799bb", mf: "#99aaaa", f: "#bbbb88",
  ff: "#ddcc66", fff: "#eeeeee"
};
const PALETTE_COLORS = [
  "#c87070","#c8a470","#c8c870","#70c870","#70c8c8","#7070c8","#c870c8","#a0a0a0"
];
let colorIdx = 0;
function nextColor() { return PALETTE_COLORS[colorIdx++ % PALETTE_COLORS.length]; }

// ─── Canvas setup ─────────────────────────────────────────────────────────────
const canvasWrap   = document.getElementById("canvas-wrap");
const canvas       = document.getElementById("waveform-canvas");
const ctx          = canvas.getContext("2d");
const frameCanvas  = document.getElementById("frame-canvas");
const frameCtx     = frameCanvas.getContext("2d");
const vid          = document.getElementById("frame-vid");
const baseAudio    = document.getElementById("base-audio");
const mixAudio     = document.getElementById("mix-audio");
let   currentSourcePath = null;
