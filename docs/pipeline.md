# Pipeline Internals

How the code works, module by module. You don't need to read this to use the tool — it's for anyone who wants to understand or modify the code.

---

## Data flow

```
config.yaml     score.yaml  +  source audio/video
     │               │               │
     ▼               ▼               ▼
  main.py        src/parser.py   src/sample_engine.py
  reads engine   load_score()    build_bank()
     │               │               │
     │           resolves        bank: {name → audio array}
     │           probabilistic   sr: sample rate
     │           parameters      base: mixed-down base audio
     │               │           (multi-track or single file)
     │  (V2 only)    └───────────────┘
     │     ▼
     │  v2/interpreter.py
     │  interpret(score, config)
     │     ├── v2/context.py     phrase boundaries, event density
     │     ├── v2/emission.py    Gaussian sampling from transition table
     │     ├── v2/markov_*.py    Markov chain (symbolic or joint)
     │     └── enriched events   (gain offsets, timing shifts, reverb, EQ)
     │           │
     └───────────▼
            src/mixer.py
            mix_events(events, bank, sr, score, base)
                │
                ├── base.copy() as starting mix
                ├── apply base_fx  (src/fx.py)
                ├── apply fx_ranges (src/fx.py)
                ├── duck_base envelope (src/envelope.py)
                └── for each event:
                    ├── varispeed resample (librosa)
                    ├── reverse
                    ├── loop
                    ├── fade edges — fade_in/fade_out (src/envelope.py)
                    ├── gain
                    ├── apply event fx (src/fx.py)
                    ├── articulations (staccato/accent/fermata/legato)
                    ├── pitch shift — pitch: field + note_rel: glissando (src/pitch.py)
                    └── place on timeline at warped time + silence_start
                ├── auto_mix density scale (src/envelope.py)
                │
                ▼
            src/renderer.py
            render(score, bank, events, sr, base)
                ├── merge phrases[].tempo_factor into tempo:
                ├── build dynamics envelope (src/envelope.py)
                ├── multiply envelope into mix
                ├── build phrase envelope (src/envelope.py)
                ├── multiply phrase envelope into mix
                ├── duck_key envelope (src/envelope.py)
                ├── normalise (src/mixer.normalise)
                └── write output_<score>_<base>_NNN.wav
```

---

## `src/parser.py`

Loads the YAML score and resolves all probabilistic parameters in place before anything else runs. After `load_score()` returns, all values are concrete floats/bools/ints — no distributions survive past this point.

Resolution logic (`_resolve()`):
- `[min, max]` → `np.random.uniform(min, max)`
- `{distribution: gaussian, mean, std}` → `np.random.normal(mean, std)`
- `{distribution: uniform, low, high}` → `np.random.uniform(low, high)`
- `{distribution: bernoulli, p}` → `bool(random() < p)`
- `{distribution: discrete, values, weights?}` → `np.random.choice(values, p=weights)`

FX parameters are also resolved probabilistically. The `t`, `sample`, and `speeds` keys are never resolved (structural).

---

## `src/sample_engine.py`

Reads the source audio into a mono float32 numpy array. For video files, ffmpeg extracts the audio to a temp WAV first.

**Multi-track mode** (`tracks:` in score): loads each track from its own file, applies per-track `gain_db`, skips `muted` tracks, and sums all active tracks into `combined_base`. The list of individual track arrays is kept so that samples can be sliced from a specific track via the `track:` field on the sample entry.

**Single-track mode** (legacy `base_track:`): loads one file and wraps it in a single-element list for backwards compatibility.

Each `samples:` entry is a slice:
```python
src   = tracks_audio[spec.get('track', 0)]
bank[name] = src[int(spec['from'] * sr) : int(spec['to'] * sr)].copy()
```

Returns `(bank, sr, base)`. The mixer starts with `base.copy()` so the source always underlies the composition.

---

## `src/mixer.py`

The core of the engine.

### `mix_events(events, bank, sr, score, base)`

1. `mix = base.copy()` — source audio is the starting layer
2. Applies `base_fx` to the whole mix
3. Applies `fx_ranges` segment by segment — extracts, processes, replaces. Reverb tails extend past the zone boundary.
4. If `duck_base.enabled`, ducks `mix` before events are layered (see below)
5. For each event:
   - Copies the clip from the bank
   - **Varispeed**: `librosa.resample(clip, orig_sr=int(sr * speed), target_sr=sr)` — telling librosa the source rate is `sr × speed` while asking for `sr` output is equivalent to a tape varispeed
   - **Reverse**: `clip[::-1].copy()`
   - **Loop**: `np.tile(clip, loop + 1)`
   - **Fade**: per-event or per-sample `fade_in_pct`/`fade_out_pct`; falls back to fixed 10ms
   - **Gain**: `clip *= 10 ** (gain_db / 20.0)`
   - **FX**: `apply_fx(clip, sr, fx_list)`
   - **Articulations**: `staccato` / `accent` / `fermata` / `legato` applied if an `articulations:` entry matches this event's time
   - **Pitch**: `resolve_event_pitch(event_t, event.pitch, note_rels)` — returns a semitone value from a `note_rel:` glissando if the event falls in range, otherwise the event's own `pitch` field; then `apply_pitch_shift(clip, sr, semitones)`
   - **Placement**: `mix[i0:i1] += clip` at the tempo-warped time + `silence_start`
6. If `auto_mix.enabled`, multiplies `mix` by a density-based gain scale

### `_warp_time(t_score, tempo_ranges)`

Maps score time to real time through tempo regions. Inside an accelerando region (`factor > 1`), score time advances faster than real time. Outside any region, they are identical.

---

## `src/envelope.py`

### `build_dynamics_envelope(n_samples, sr, dynamics)`

Builds a float32 amplitude envelope multiplied into the final mix:

1. Extracts point marks (`t:` entries), sorts by time, fills the envelope step-wise with short smooth transitions between adjacent levels (12ms–500ms depending on gap duration)
2. Overlays crescendo/decrescendo ranges as `np.linspace` interpolations

The envelope affects both the source track and all composed samples equally.

### `apply_fade(clip, sr, fade_in_pct, fade_out_pct, ms=10.0)`

Linear fade-in and fade-out to prevent click artifacts. If `fade_in_pct`/`fade_out_pct` are non-zero they are used as fractions of clip length; otherwise a fixed 10ms fallback applies. Capped at half of clip length for very short clips.

### `build_duck_envelope(n_samples, sr, events, trigger_fn, amount_db, attack, release)`

Builds a gain envelope that dips on every event that passes `trigger_fn`. Attack ramps linearly from 1.0 to `duck = 10^(amount_db/20)`, release ramps back to 1.0. Used by both `duck_key:` (trigger_fn matches one sample name) and `duck_base:` (trigger_fn always returns True).

### `build_phrase_envelope(n_samples, sr, phrases)`

Multiplicative envelope: for each phrase entry applies `gain_db` gain with optional linear fade-in and fade-out (both as fractions of phrase length).

### `build_density_scale(n_samples, sr, events, samples_spec, mode)`

Counts how many event clips overlap at each sample position, then returns a gain scale array: `1/√density` (`mode: sqrt`) or `1/density` (`mode: inverse`). Used by `auto_mix:`.

---

## `src/fx.py`

All standard effects follow the same pattern: write the clip to a temp WAV, call SoX via subprocess, read the result back, delete both temp files.

Effects implemented: `reverb`, `delay`, `overdrive`, `flanger`, `pitch`, `compress`, `eq`, `spectral_inversion`, `overtones`. See [score_reference.md](score_reference.md) for parameter details.

FX types starting with `morpho_` are dispatched to the Morphogenics plugin system instead of SoX:

```python
elif t.startswith('morpho_'):
    from plugins import apply_plugin
    clip = apply_plugin(clip, sr, fx)
```

---

## `plugins/` — Morphogenics plugin system

### Auto-discovery (`plugins/__init__.py`)

On first call to `load_plugins()`, the loader scans the `plugins/` directory for every `.py` file that is not prefixed with `_`. For each file it attempts:

```python
mod = importlib.import_module(f"plugins.{mod_name}")
if hasattr(mod, "NAME") and hasattr(mod, "PARAMS") and hasattr(mod, "process"):
    _registry[mod.TYPE_KEY] = mod
```

Failed imports are silently skipped. The result is cached in `_registry` so scanning only happens once per process.

### Plugin contract

Each plugin file must define:

```python
NAME     = "Composer: Technique"   # shown in the FX dropdown
GROUP    = "morphogenics"          # always this value
TYPE_KEY = "morpho_plugin_name"    # must be unique; used as the fx type key in scores

PARAMS = {
    "param_key": {
        "label":   "human label",
        "type":    "float" | "int" | "select",
        "min":     0,
        "max":     100,
        "default": 50,
        # "options": [...]  # only for type: "select"
    },
    ...
}

def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    ...  # returns processed audio, same length as clip
```

### Dispatch (`apply_plugin`)

```python
def apply_plugin(clip, sr, fx):
    mod    = _registry.get(fx["type"])
    params = {k: fx.get(k, spec["default"]) for k, spec in mod.PARAMS.items()}
    return mod.process(clip, sr, params)
```

Missing parameters in the FX dict are filled in with the plugin's declared defaults.

### `GET /plugins` endpoint (`editor/server.py`)

Returns the full plugin registry as JSON for the editor's FX dropdown:

```json
[
  {
    "type":   "morpho_saariaho_freeze",
    "name":   "Saariaho: Spectral Freeze",
    "group":  "morphogenics",
    "params": {
      "n_partials":  {"label": "partials",    "type": "int",   "min": 5, "max": 50, "default": 20},
      "freeze_rate": {"label": "freeze rate", "type": "float", "min": 0.01, "max": 1.0, "default": 0.1},
      "dry_wet":     {"label": "dry/wet %",   "type": "float", "min": 0, "max": 100, "default": 80}
    }
  },
  ...
]
```

The UI calls this endpoint once at startup and uses the schema to auto-generate input widgets — no frontend code changes are needed when a new plugin is added.

See [morphogenics.md](morphogenics.md) for documentation on all 20 plugins.

---

## `src/renderer.py`

Ties the full pipeline together for the CLI:

1. Merges any `phrases[].tempo_factor` values into the score's `tempo:` list (so `_warp_time` handles them transparently)
2. Calls `mix_events()`
3. Builds and applies the dynamics envelope
4. Builds and applies the phrase envelope
5. Applies `duck_key:` envelope if enabled
6. Normalises to 0.9 peak
7. For audio input: writes `output/output_<score>_<base>_NNN.wav`
8. For video input: writes a temp WAV, then calls:
   ```
   ffmpeg -i original.mp4 -i rendered.wav -c:v copy -map 0:v:0 -map 1:a:0 output.mp4
   ```
   Replaces the audio track while copying the video byte-for-byte.

Also adds `src/pitch.py`:

| Function | What it does |
|----------|-------------|
| `resolve_event_pitch(event_t, base_pitch, note_rels)` | Returns interpolated semitone value if event falls in a `glissando` range, else `base_pitch` |
| `apply_pitch_shift(clip, sr, semitones)` | Wraps `librosa.effects.pitch_shift`; no-ops for shifts < 0.05 st |

---

## `v2/` package

Only active when `config.yaml` has `engine: v2`.

| Module | Role |
|--------|------|
| `v2/interpreter.py` | Entry point: `interpret(score, config) → list[dict]`. Orchestrates all other V2 modules. |
| `v2/context.py` | Computes context vectors (phrase position, tempo direction, event density) and infers phrase boundaries from inter-event gaps. |
| `v2/emission.py` | `sample_output()`: looks up the transition table, builds a Gaussian (diagonal or full covariance), draws the output vector. |
| `v2/markov_symbolic.py` | `SymbolicMarkov`: history tracks score markings only. |
| `v2/markov_joint.py` | `JointMarkov`: history tracks markings + rendered outputs; applies history_decay weighting. |
| `v2/transition_table.yaml` | Expert priors for every dynamic transition (mean and std per output parameter). |

---

## `editor/server.py`

Flask server that backs the web editor.

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/` | GET | Serves the editor HTML |
| `/load` | POST | Reads the source file, returns waveform peaks + first video frame + duration |
| `/video` | GET | Serves the raw media file for browser playback |
| `/frame` | GET | Extracts a video frame at time `t` via ffmpeg |
| `/preview` | POST | Renders the current score; routes to V2 if `_config.engine == 'v2'`; returns audio URL |
| `/preview_audio` | GET | Serves the last rendered preview WAV |
| `/export` | POST | Saves the score as YAML to `scores/`; includes `_v2_config:` if V2 was active |

The `/preview` endpoint accepts an optional `_config` key in the POST body. If absent, it reads `config.yaml` from the root folder.
