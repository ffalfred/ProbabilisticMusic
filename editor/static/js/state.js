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
  lastScorePath: "",  // last exported or imported YAML score path
  duckBase: { enabled: false, amount_db: -6,  attack: 0.01, release: 0.30 },
  duckKey:  { enabled: false, key: "",  amount_db: -10, attack: 0.01, release: 0.30 },
  autoMix:  { enabled: false, mode: "sqrt" },
  history: [],        // for undo
  tempoMap: [],       // [[score_t, real_t], ...] — set after each render, empty = identity
  durationReal: 0,    // rendered mix duration in real seconds (may differ from score duration when tempo stretches)
};

// ─── Tempo map helpers: translate between score time and real (wall-clock) time
// ────────────────────────────────────────────────────────────────────────────
function scoreToReal(t) {
  const tm = state.tempoMap;
  if (!tm || tm.length < 2) return t;
  if (t <= tm[0][0]) return tm[0][1];
  for (let i = 0; i < tm.length - 1; i++) {
    const [s0, r0] = tm[i], [s1, r1] = tm[i + 1];
    if (t <= s1) {
      if (s1 === s0) return r0;
      return r0 + (t - s0) * (r1 - r0) / (s1 - s0);
    }
  }
  const [sL, rL] = tm[tm.length - 1];
  return rL + (t - sL);
}
function realToScore(t) {
  const tm = state.tempoMap;
  if (!tm || tm.length < 2) return t;
  if (t <= tm[0][1]) return tm[0][0];
  for (let i = 0; i < tm.length - 1; i++) {
    const [s0, r0] = tm[i], [s1, r1] = tm[i + 1];
    if (t <= r1) {
      if (r1 === r0) return s0;
      return s0 + (t - r0) * (s1 - s0) / (r1 - r0);
    }
  }
  const [sL, rL] = tm[tm.length - 1];
  return sL + (t - rL);
}

// ─── 12D state dimension metadata ────────────────────────────────────────────
const DIM_NAMES = [
  'gain_db','brightness','timing_offset_ms','attack_shape','release_shape',
  'reverb_wet','filter_cutoff','filter_resonance','stereo_width',
  'overdrive_drive','pitch_dev_cents','dynamic_center',
];
const DIM_LABELS = [
  'Gain dB','Brightness','Timing ms','Attack','Release',
  'Reverb','Filter Cutoff','Filter Q','Stereo Width',
  'Overdrive','Pitch Cents','Dyn Center',
];
const DIM_RANGES_DEFAULT = [
  [-40,6],[0,1],[-50,50],[0,1],[0,1],
  [0,1],[20,20000],[0,1],[0,1],
  [0,1],[-50,50],[-30,0],
];
const DIM_DEFAULTS = {
  gain_db:0, brightness:0.5, timing_offset_ms:0, attack_shape:0.5,
  release_shape:0.5, reverb_wet:0.3, filter_cutoff:5000, filter_resonance:0,
  stereo_width:0.5, overdrive_drive:0, pitch_dev_cents:0, dynamic_center:-12,
};

// Character cold-start biases (mirror of src/character.py BUILTIN.cold_start_bias)
// Used by the golem editor's "Starting values" section to show per-character defaults.
const CHAR_COLD_START_BIAS = {
  dramatic: {
    gain_db:3.0, brightness:0.25, timing_offset_ms:0.0, attack_shape:0.35,
    release_shape:0.3, reverb_wet:0.65, filter_cutoff:3000.0, filter_resonance:0.2,
    stereo_width:0.7, overdrive_drive:0.15, pitch_dev_cents:0.0, dynamic_center:-6.0,
  },
  lyrical: {
    gain_db:0.0, brightness:0.75, timing_offset_ms:0.0, attack_shape:0.75,
    release_shape:0.7, reverb_wet:0.40, filter_cutoff:8000.0, filter_resonance:0.0,
    stereo_width:0.5, overdrive_drive:0.0, pitch_dev_cents:0.0, dynamic_center:-12.0,
  },
  sparse: {
    gain_db:-4.0, brightness:0.50, timing_offset_ms:0.0, attack_shape:0.10,
    release_shape:0.4, reverb_wet:0.05, filter_cutoff:5000.0, filter_resonance:0.0,
    stereo_width:0.3, overdrive_drive:0.0, pitch_dev_cents:0.0, dynamic_center:-18.0,
  },
  turbulent: {
    gain_db:4.0, brightness:0.55, timing_offset_ms:0.0, attack_shape:0.20,
    release_shape:0.2, reverb_wet:0.55, filter_cutoff:2000.0, filter_resonance:0.4,
    stereo_width:0.8, overdrive_drive:0.3, pitch_dev_cents:0.0, dynamic_center:-4.0,
  },
};

// ─── Interpreter state (V2 engine + Golems) ──────────────────────────────────
const interpState = {
  scorePath: "",        // path to the score YAML being interpreted
  scoreDuration: 0,     // cached duration for timeline drawing
  scoreDynamics: [],    // dynamics from the loaded score YAML (for trace overlay)
  golems: [],           // [{from, to, character, type, state, dimension_config}]
  mix_dims: ['gain_db'],// which golem dimensions to apply to the mix
  v2config: {
    engine: 'v2',
    seed: null,
    v2: { lambda: 0.7, A1: 0.7, A2: 0.2, eta: 0.3, xi: 0.05, window_size: 3, trace_step: 0.5 },
  },
};

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
