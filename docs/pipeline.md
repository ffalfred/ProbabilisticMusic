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
     │           parameters      base: full audio array
     │               │               │
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
                └── for each event:
                    ├── varispeed resample (librosa)
                    ├── reverse
                    ├── loop
                    ├── fade edges (src/envelope.py)
                    ├── gain
                    ├── apply event fx (src/fx.py)
                    └── place on timeline at warped time
                │
                ▼
            src/renderer.py
            render(score, bank, events, sr, base)
                ├── build dynamics envelope (src/envelope.py)
                ├── multiply envelope into mix
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

Each `samples:` entry is a slice:
```python
bank[name] = base[int(spec['from'] * sr) : int(spec['to'] * sr)].copy()
```

Returns `(bank, sr, base)`. The mixer starts with `base.copy()` so the source always underlies the composition.

---

## `src/mixer.py`

The core of the engine.

### `mix_events(events, bank, sr, score, base)`

1. `mix = base.copy()` — source audio is the starting layer
2. Applies `base_fx` to the whole mix
3. Applies `fx_ranges` segment by segment — extracts, processes, replaces. Reverb tails extend past the zone boundary.
4. For each event:
   - Copies the clip from the bank
   - **Varispeed**: `librosa.resample(clip, orig_sr=int(sr * speed), target_sr=sr)` — telling librosa the source rate is `sr × speed` while asking for `sr` output is equivalent to a tape varispeed
   - **Reverse**: `clip[::-1].copy()`
   - **Loop**: `np.tile(clip, loop + 1)`
   - **Fade**: 10ms linear fade in/out to prevent clicks
   - **Gain**: `clip *= 10 ** (gain_db / 20.0)`
   - **FX**: `apply_fx(clip, sr, fx_list)`
   - **Placement**: `mix[i0:i1] += clip` at the tempo-warped time

### `_warp_time(t_score, tempo_ranges)`

Maps score time to real time through tempo regions. Inside an accelerando region (`factor > 1`), score time advances faster than real time. Outside any region, they are identical.

---

## `src/envelope.py`

### `build_dynamics_envelope(n_samples, sr, dynamics)`

Builds a float32 amplitude envelope multiplied into the final mix:

1. Extracts point marks (`t:` entries), sorts by time, fills the envelope step-wise
2. Overlays crescendo/decrescendo ranges as `np.linspace` interpolations

The envelope affects both the source track and all composed samples equally.

### `apply_fade(clip, sr, ms=10.0)`

Linear 10ms fade-in and fade-out to prevent click artifacts. Capped at 1/4 of clip length for very short clips.

---

## `src/fx.py`

All effects follow the same pattern: write the clip to a temp WAV, call SoX via subprocess, read the result back, delete both temp files.

Effects implemented: `reverb`, `delay`, `overdrive`, `flanger`, `pitch`, `compress`, `eq`. See [score_reference.md](score_reference.md) for parameter details.

---

## `src/renderer.py`

Ties the full pipeline together for the CLI:

1. Calls `mix_events()`
2. Builds and applies the dynamics envelope
3. Normalises to 0.9 peak
4. For audio input: writes `output/output_<score>_<base>_NNN.wav`
5. For video input: writes a temp WAV, then calls:
   ```
   ffmpeg -i original.mp4 -i rendered.wav -c:v copy -map 0:v:0 -map 1:a:0 output.mp4
   ```
   Replaces the audio track while copying the video byte-for-byte.

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
