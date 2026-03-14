# Pipeline Internals

How the code works, module by module.

## Data flow

```
config.yaml     score.yaml  +  base_track
     │               │               │
     ▼               ▼               ▼
  main.py        parser.py      sample_engine.py
  engine?        load_score()   build_bank()
     │               │               │
     │           ┌───┘           bank: {name → np.array}
     │           │               sr: int
     │  V2 only  │               base: np.array
     │     ▼     │
     │  v2/interpreter.py
     │  interpret(score, config)
     │     ├── v2/context.py  — phrase boundaries, event density
     │     ├── v2/emission.py — Gaussian sampling from transition table
     │     ├── v2/markov_symbolic.py or markov_joint.py
     │     └── enriched events (gain_db offsets, timing shifts, reverb, EQ)
     │           │
     └─────────── ▼
            mixer.py
            mix_events(events, bank, sr, score, base)
                │
                ├── base.copy() as starting mix
                ├── apply base_fx  (fx.py)
                ├── apply fx_ranges (fx.py, segment by segment)
                └── for each event:
                    ├── varispeed resample (librosa)
                    ├── reverse
                    ├── loop (np.tile)
                    ├── fade edges (envelope.py)
                    ├── gain (dB → linear)
                    ├── apply event fx (fx.py)
                    └── place on timeline at warped time (_warp_time)
                │
                ▼
            renderer.py
            render(score, bank, events, sr, base)
                ├── build dynamics envelope (envelope.py)
                ├── multiply envelope into mix
                ├── normalise (mixer.normalise)
                └── write output_<score>_<base>_NNN.wav (soundfile / ffmpeg)
```

---

## `src/parser.py`

Loads the YAML and resolves all probabilistic parameters **in place** before anything else runs. This means `load_score()` is called once per render, and the returned dict has all values as concrete floats/bools/ints — no distribution objects survive past this point.

Probabilistic resolution logic (`_resolve()`):
- `[min, max]` → `np.random.uniform(min, max)`
- `{distribution: gaussian, mean, std}` → `np.random.normal(mean, std)`
- `{distribution: uniform, low, high}` → `np.random.uniform(low, high)`
- `{distribution: bernoulli, p}` → `bool(random() < p)`
- `{distribution: discrete, values, weights?}` → `np.random.choice(values, p=weights)`

The `speeds` list is resolved element-by-element, so each layer of a layered transposition can independently be probabilistic.

FX parameters (e.g. `reverberance`, `delay_sec`, `feedback`) are also resolved probabilistically. The `t`, `sample`, `fx` type, and `speeds` key are never resolved (they are structural).

---

## `src/sample_engine.py`

Reads the base track into a mono float32 numpy array. For `.mp4` files, ffmpeg extracts the audio to a temp WAV first, then that temp file is loaded and deleted.

Each `samples:` entry is a simple slice:

```python
bank[name] = base[int(spec['from'] * sr) : int(spec['to'] * sr)].copy()
```

Returns `(bank, sr, base)`. `base` is returned because the mixer starts its mix buffer as `base.copy()` — so the original audio always underlies the composition.

---

## `src/mixer.py`

The core of the system.

### `mix_events(events, bank, sr, score, base)`

1. Initialises `mix = base.copy()` so the base track is the starting layer.
2. Applies `base_fx` to the entire mix via `apply_fx()`.
3. Applies `fx_ranges` segment by segment: extracts `mix[i0:i1]`, processes it, zeros out the original segment, adds the processed audio back. Reverb tails extend past `i1`.
4. For each event:
   - Copies the clip from the bank.
   - **Varispeed**: `librosa.resample(clip, orig_sr=int(sr * speed), target_sr=sr)`. The trick: telling librosa the source sample rate is `sr * speed` while requesting `sr` output is equivalent to resampling to `1/speed` of the original length while preserving the relative pitch shift.
   - **Reverse**: `clip[::-1].copy()`
   - **Loop**: `np.tile(clip, loop + 1)`
   - **Fade**: 10ms linear fade in/out to prevent clicks at boundaries (from `envelope.apply_fade`).
   - **Gain**: `clip *= 10 ** (gain_db / 20.0)`
   - **FX**: `apply_fx(clip, sr, fx_list)` from `fx.py`
   - **Placement**: computes `t_real = _warp_time(event['t'], tempo_ranges)` then places at `mix[i0:i1] += clip`

### `_warp_time(t_score, tempo_ranges)`

Maps a score time to real time by accumulating offsets through each tempo range. Inside an accelerando region, score time advances faster than real time; inside a ritardando, slower. Outside any tempo range, score time and real time are identical.

---

## `src/envelope.py`

### `build_dynamics_envelope(n_samples, sr, dynamics)`

Builds a float32 amplitude envelope of length `n_samples`:

1. Extracts all point marks (those with `t:`), sorts by time, fills the envelope step-wise: each level holds until the next point mark.
2. Overlays crescendo/decrescendo ranges as `np.linspace` interpolations between the envelope values at the range boundaries.

The envelope is multiplied into the mix after all events have been placed. This affects both the base track and all composed samples equally.

### `apply_fade(clip, sr, ms=10.0)`

Applies a 10ms linear fade-in and fade-out to a clip to prevent clicks. The fade is capped at 1/4 of the clip length to avoid distorting very short clips.

---

## `src/fx.py`

Both effects follow the same pattern: write the clip to a temp WAV, call SoX via subprocess, read the result back, delete both temp files.

### `_delay(clip, sr, fx)`

Calls `sox input.wav output.wav echo 0.8 0.9 D1ms F1 D2ms F2 D3ms F3` where:
- D1/D2/D3 are `delay_sec × 1000`, `× 2000`, `× 3000` (SoX uses milliseconds)
- F1/F2/F3 are `feedback`, `feedback²`, `feedback³`

### `_reverb(clip, sr, fx)`

Calls `sox input.wav output.wav reverb <reverberance>`.

Both functions always return a mono float32 array regardless of the SoX output channel count.

---

## `src/renderer.py`

Wraps the full pipeline for the CLI:

1. Calls `mix_events()`.
2. Builds and applies the dynamics envelope (via `envelope.build_dynamics_envelope()`).
3. Normalises (via `mixer.normalise()`).
4. For audio input: writes `output/output.wav` with soundfile.
5. For video input (`.mp4`): writes a temp WAV, then calls:
   ```
   ffmpeg -i original.mp4 -i rendered.wav -c:v copy -map 0:v:0 -map 1:a:0 output.mp4
   ```
   This replaces the audio track while copying the video stream byte-for-byte, preserving the original quality.

---

## `v2/` package

The V2 Expressive Interpretation Engine. Only active when `config.yaml` has `engine: v2`.

| Module | Role |
|--------|------|
| `v2/interpreter.py` | Entry point: `interpret(score, config) → list[dict]`. Orchestrates all other modules. |
| `v2/context.py` | Computes context vectors (phrase position, tempo direction, event density) and infers phrase boundaries. |
| `v2/emission.py` | `sample_output()`: looks up transition table entry, builds Gaussian (diagonal or full covariance), draws o(t). |
| `v2/markov_symbolic.py` | `SymbolicMarkov`: history tracks score markings only. |
| `v2/markov_joint.py` | `JointMarkov`: history tracks markings + rendered outputs; history_decay weighting. |
| `v2/transition_table.yaml` | Expert priors for every dynamic transition (mean, std per output parameter). |

---

## `editor/server.py`

Flask server that backs the web editor. Endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves `static/index.html` |
| `/load` | POST | Reads audio/video, returns waveform peaks + first frame (base64 PNG) + duration |
| `/video` | GET | Serves the raw media file for `<video>` / `<audio>` playback |
| `/frame` | GET | Extracts a single video frame at time `t` via ffmpeg |
| `/preview` | POST | Renders a full mix from score JSON; routes to V2 if `_config.engine == 'v2'`; returns playback URL |
| `/preview_audio` | GET | Serves the last rendered preview WAV |
| `/export` | POST | Saves score JSON as YAML to `scores/`; includes `_v2_config:` block if V2 was active |

The `/preview` endpoint accepts an optional `_config` key in the POST body containing the engine/markov settings. If absent, it falls back to `config.yaml` defaults.
