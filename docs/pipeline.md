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
     │  src/interpreter.py
     │  interpret(score, config) → (events, trace)
     │     ├── src/character.py   golem characters + blending
     │     ├── src/drama.py       marking salience + look-ahead pull
     │     ├── src/kalman.py      AR(2) predict / update
     │     ├── src/observation.py marking window → H, R (transition_table.yaml)
     │     └── enriched events    (timing offset, attack/release shape)
     │         + trace            (13-dim state per step → applied to the mix)
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
                    ├── varispeed resample (librosa), or time-stretch if pitch_lock (src/stretch.py)
                    ├── reverse
                    ├── loop
                    ├── articulations on this event: staccato / legato / fermata (src/articulations.py)
                    ├── fade edges — fade_in/fade_out (src/envelope.py)
                    ├── accent on this event
                    ├── gain
                    ├── apply event fx (src/fx.py)
                    ├── pitch shift — pitch: field + note_rel: glissando (src/pitch.py)
                    └── place on timeline at warped time + silence_start
                ├── whole-mix articulations: staccato / accent / legato (target: mix)
                ├── auto_mix density scale (src/envelope.py)
                │
                ▼
            src/renderer.py
            render(score, bank, events, sr, base)
                ├── merge phrases[].tempo_factor into tempo:
                ├── tempo stretch (accelerando / ritardando) → tempo map
                ├── whole-mix fermatas: insert the held sound, tempo map stands still
                ├── build dynamics envelope (src/envelope.py)
                ├── multiply envelope into mix
                ├── build phrase envelope (src/envelope.py)
                ├── multiply phrase envelope into mix
                ├── duck_key envelope (src/envelope.py)
                ├── loudness: adjust + safety brake (src/loudness.finish)
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

Reads the source audio as a float32 numpy array of shape `(frames, channels)`, keeping its channels (more than two keep the first two, L/R). For video files (mp4, mov, avi, mkv, webm), ffmpeg extracts the audio to a temp WAV first, also keeping its channels.

**Sample rate:** the piece runs at track 0's sample rate. Other tracks are resampled to it on load (librosa / soxr), before their track FX.

**Channels:** all audio inside the engine is `(frames, channels)` with 1 or 2 channels, the layout soundfile reads and writes. A piece is stereo if any of its tracks is; mono tracks then play on both sides. A mono piece renders a mono file. Helpers in `src/dsp.py` keep this safe: `env_mul` applies 1-D envelopes (never `x * env`, which broadcasts `(n, 1) × (n,)` to `(n, n)`), `pad_frames` pads along time only, and `per_channel` runs mono processors (chorus, spectral inversion, mono plugins) on each channel with the same random draws. SoX effects and Rubber Band (`src/stretch.py`) process the channels together, so reverb and flanger spread a stereo signal and pitch shifts keep the image. Plugins that set `STEREO = True` (all but Spectral Smooth) get both channels at once, analyse the mono sum and can place voices with `spread` — see [morphogenics.md](morphogenics.md#stereo).

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
   - **Varispeed**: `librosa.resample(clip, orig_sr=int(sr * speed), target_sr=sr)` — telling librosa the source rate is `sr × speed` while asking for `sr` output is equivalent to a tape varispeed. With `pitch_lock`, `time_stretch(clip, sr, speed)` (src/stretch.py) changes the speed and keeps the pitch instead
   - **Reverse**: `clip[::-1].copy()`
   - **Loop**: `np.tile(clip, loop + 1)`
   - **Fade**: per-event or per-sample `fade_in_pct`/`fade_out_pct`; falls back to fixed 10ms
   - **Gain**: `clip *= 10 ** (gain_db / 20.0)`
   - **FX**: `apply_fx(clip, sr, fx_list)`
   - **Articulations** (`target: event`, src/articulations.py): marks are matched to events first (a point mark → the event starting nearest within 0.5 s; a range → every event starting inside). Staccato / legato / fermata change the clip's length before its fades and FX; accent boosts its attack after the fades. Whole-mix marks (`target: mix`) run on the mix after all events are placed; whole-mix fermatas run in `render_mix` after the tempo stretch, because they insert time
   - **Pitch**: `resolve_event_pitch(event_t, event.pitch, note_rels)` — returns a semitone value from a `note_rel:` glissando if the event falls in range, otherwise the event's own `pitch` field; then `apply_pitch_shift(clip, sr, semitones)`
   - **Placement**: `mix[i0:i1] += clip` at the tempo-warped time + `silence_start`
6. If `auto_mix.enabled`, multiplies `mix` by a density-based gain scale

### Speed: parallel events and the render cache

`mix_events` works in three steps:
1. **The source** — base FX, then source FX zones — is processed once and **cached** (`src/render_cache.py`): the same settings on the same audio are reused by the next render.
2. **Every event's clip** (`_event_clip`: speed, reverse, loop, articulations, fades, accent, gain, FX, pitch) is processed **in parallel** (a thread pool; Rubber Band, SoX and numpy release the GIL) and **cached**. The cache key is everything the clip depends on — the event's settings except where it is placed (`t`, timing offset, mix mode), its sample's audio, the marks on it, its glissando pitch — so an event that only moved is reused.
3. **Placement** — timing, arpeggio stagger, layering — runs in order, as before.

**Randomness.** Effects draw random numbers through `src.rand.rng()`. Each event gets its own random state, seeded in order from the render's seed, so parallel processing gives the same result every time and one event's randomness never depends on another's. The cache stores a result under its key alone when the work drew no random numbers (it can't depend on the seed: reused with any seed), and under key + seed when it did (reused only with the same seed). So with the default `seed: null`, every Mix still redraws random effects and probabilistic values, and reuses everything else.

Decoded source files are also kept (`sample_engine._load_audio`, the last 4, until the file changes on disk), so a video's audio is extracted once. The cache holds up to 768 MB of audio in the editor's server process, least recently used dropped first; restarting the server empties it.

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
    "type":   "morpho_spectral_freeze",
    "name":   "Saariaho: Spectral Freeze",
    "group":  "morphogenics",
    "params": {
      "mode":        {"label": "mode", "type": "select", "options": ["attacks", "follow"], "default": "attacks"},
      "n_partials":  {"label": "partials (0 = all)", "type": "int", "min": 0, "max": 100, "default": 20},
      "freeze_rate": {"label": "follow rate", "type": "float", "min": 0.0, "max": 1.0, "default": 0.1},
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
6. Finishes the level with `src/loudness.finish` (config `output:` block): the level is kept as performed, an optional whole-file adjustment (match source / target LUFS) is applied, then the safety brake (look-ahead limiter at −1 dBFS)
7. For audio input: writes `output/output_<score>_<base>_NNN.wav`
8. For video input: writes a temp WAV, then calls:
   ```
   ffmpeg -i original.mp4 -i rendered.wav -c:v copy -map 0:v:0 -map 1:a:0 output.mp4
   ```
   Replaces the audio track while copying the video byte-for-byte.

Also adds `src/pitch.py`:

| Function | What it does |
|----------|-------------|
| `resolve_event_pitch(event_t, base_pitch, note_rels)` | Returns interpolated semitone value if event falls in a full-band `glissando` range, else `base_pitch`. Band-limited glissandi (`freq_from`/`freq_to`) are applied to the mix by `apply_noterel_to_mix` instead, so events are never shifted twice. |
| `apply_pitch_shift(clip, sr, semitones)` | Calls `src.stretch.pitch_shift` (channels together); no-ops for shifts < 0.05 st |
| `apply_noterel_to_mix(mix, sr, note_rels)` | Banded glissandi: one pitch-curve pass over the band; arpeggio fades |

`src/stretch.py` — every pitch shift and time stretch in the engine (event pitch, `pitch_lock`, tempo steps and ramps, banded glissandi, overtones, Morphogenics) goes through it. Back end: Rubber Band (R3 engine) via `pedalboard`; deterministic, channels processed together.

| Function | What it does |
|----------|-------------|
| `pitch_shift(x, sr, semitones)` | Same length. `semitones` may be a per-sample curve (glides, stepped detune) |
| `time_stretch(x, sr, rate)` | rate > 1 = shorter. `rate` may be a per-sample curve (tempo ramps); output length is exactly `sum(1/rate)` |
| `transform(x, sr, rate, semitones)` | Both at once, constant values |
| `read_at_rate(x, start, n_out, ratio)` | Tape-style read (pitch and speed together) for grains and short slides |
| `steps_to_curve(values, hop, n)` | One value per hop → a per-sample curve with glides between values |
| `parallel_map(fn, items)` | Runs independent Rubber Band calls on a shared thread pool; same results as serial |

Time-varying curves are followed about every 1024 samples, and timing inside a long wide curve can wander by up to ~20 ms; the ends are exact.

**Licence:** Rubber Band and `pedalboard` are GPLv3, the project is Apache-2.0 — see [installation.md](installation.md#licences).

---

## V2 interpreter (`src/`)

Only active when `config.yaml` has `engine: v2` (or a request passes `engine: 'v2'`).

| Module | Role |
|--------|------|
| `src/interpreter.py` | Entry point: `interpret(score, config, return_trace)`. Steps the state at every marking, event, element boundary and every `trace_step` s; each step = AR(2) predict → pull toward the current/next marking's target → Kalman update → sample. Simultaneous events share one sample. |
| `src/character.py` | The 13 state dimensions, their limits/defaults, and the built-in Kalman and random-walk characters; blends overlapping golems. |
| `src/kalman.py` | Augmented AR(2) state, `predict` / `update`. |
| `src/drama.py` | Per-marking salience ω and look-ahead pull φ. |
| `src/observation.py` | Encodes the marking window as an observation and looks up H / R in `src/transition_table.yaml`. |
| `src/golem_fx.py` | Mix processing for the golems' drive (saturation) and dynamic centre (compressor). |
| `src/resfilter.py` | The resonant low/high-pass shared by the golems' filter dims and the Composer's filter effect. |

In practice the target pull dominates; the Kalman update's corrections are small with the current table — see [v2.md](v2.md#how-a-kalman-golem-moves).

## Seeding and shared rendering

- `src/parser.py: seed_everything(config)` seeds numpy's global RNG and Python's `random` from `v2.seed` / `seed` (drawing one if unset) and writes it back to `config['v2']['seed']`. The interpreter's own RNG uses the same seed; plugins draw their generators via `plugins.plugin_rng()`. One seed therefore reproduces a whole render.
- `src/parser.py: resolve_score(score)` resolves random event values (ranges, distributions) and normalises `marking:` → `mark:`. Used by `load_score` and by every server render route.
- `src/renderer.py: render_mix(score, bank, events, sr, base)` is the single post-interpretation pipeline (mix → tempo stretch → section/global FX → envelopes → duck_key), shared by the CLI and the editor server. It returns the mix at the level the performance produced; nothing normalises it.
- `src/loudness.py`: `measure_lufs` (ITU-R BS.1770-4 integrated loudness), `brake` (look-ahead limiter; audio below the ceiling passes bit-identical, both channels get the same gain), `finish(mix, sr, adjust, target_lufs, source, use_brake)` → (audio, report). The editor's previews apply the brake switch; exports (Interpreter WAV, Concerto Download) apply the chosen adjustment, measured on the whole render before any range trim.
- `src/dsp.py` holds the overlap-add / crossfade helpers used wherever audio is processed in pieces (glissandi, piecewise plugins).

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
