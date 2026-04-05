# Opus One — V0.5 Update Plan

---

## 1. FX System Overhaul

### 1.1 Two groups

**Classic FX** — standard audio processing:
- reverb
- delay / echo
- distortion / overdrive
- flanger
- compressor
- EQ
- filter (lowpass / highpass / bandpass)
- chorus
- tremolo
- pitch shift

**Morphogenics** — spectral and granular techniques. Renamed by technique only, composer names removed from all plugin files and documentation:
- undertones
- spectral freeze
- grain scatter
- spectral morph
- spectral mask
- ring modulation
- granular stretch
- spectral blur
- spectral gate
- noise injection
- (remaining plugins follow same convention)

### 1.2 FX scope

Each FX — classic or morphogenics — can be applied at three scopes:

- **Per event** — applied at a single triggered event, as currently implemented
- **Per section** — applied across a time range
- **Global** — applied to the entire track output

```yaml
fx_sections:
  - from: 10
    to: 40
    type: filter
    cutoff: 800
    resonance: 0.4

fx_global:
  - type: reverb
    room: 0.6
    wet: 0.3
```

### 1.3 New and extended FX parameters

| FX | Parameters |
|---|---|
| reverb | `wet`, `room`, `pre_delay`, `damping` |
| delay | `time`, `feedback`, `wet`, `ping_pong` |
| filter | `cutoff`, `resonance`, `type` (lp / hp / bp) |
| overdrive | `drive`, `tone` |
| flanger | `rate`, `depth`, `feedback` |
| compressor | `threshold`, `ratio`, `attack`, `release` |
| eq | `bands` — list of `{freq, gain, q}` |
| chorus | `rate`, `depth`, `wet` |
| tremolo | `rate`, `depth` |
| pitch shift | `semitones` |

### 1.4 State-promotable FX parameters

The following FX parameters can be promoted to state dimensions — meaning the Kalman filter maintains a belief over them and they drift expressively across events. When promoted, a base value can still be set explicitly in the score; the state drifts around that base.

| Parameter | Promoted state dimension |
|---|---|
| filter cutoff | `filter_cutoff` |
| filter resonance | `filter_resonance` |
| reverb wet | `reverb_wet` — already in state |
| overdrive drive | `overdrive_drive` |
| stereo width | `stereo_width` |
| delay wet | `delay_wet` |
| delay feedback | `delay_feedback` |
| tremolo depth | `tremolo_depth` |

Parameters that remain discrete only — compositional choices, not expressive drift:

- `delay_time` — rhythmic relationship to tempo
- `flanger_rate` — rate choice
- `eq bands` — authored timbral color
- `pitch shift semitones` — fixed transposition

---

## 2. Expressive State — 12D

The V2 engine expressive state x(t) is expanded from 5 to 12 dimensions.

```
x(t) = [
  gain_db,            dim 0
  brightness,         dim 1
  timing_offset_ms,   dim 2
  attack_shape,       dim 3  *
  release_shape,      dim 4  *
  reverb_wet,         dim 5
  filter_cutoff,      dim 6
  filter_resonance,   dim 7
  stereo_width,       dim 8
  overdrive_drive,    dim 9
  pitch_dev_cents,    dim 10
  dynamic_center,     dim 11
]

* sample-trigger-dependent — only has effect at the moment a sample is triggered
```

### 2.1 Dimension reference

| Dimension | Range | Inertia | Distribution | Notes |
|---|---|---|---|---|
| `gain_db` | −40 to +6 db | medium | gaussian | Overall loudness |
| `brightness` | 0 to 1 | medium | beta | Spectral tilt |
| `timing_offset_ms` | −50 to +50 ms | low | laplace | Micro-timing push/pull |
| `attack_shape` | 0 to 1 | medium | beta | Onset sharpness. Sample trigger only |
| `release_shape` | 0 to 1 | medium | beta | Note ending shape. Sample trigger only |
| `reverb_wet` | 0 to 1 | high | beta | Spatial depth |
| `filter_cutoff` | 20 to 20000 hz | medium | gaussian (log scale) | Spectral filtering. Critical for noisy material |
| `filter_resonance` | 0 to 1 | medium | beta | Filter Q |
| `stereo_width` | 0 to 1 | high | beta | Stereo image width |
| `overdrive_drive` | 0 to 1 | medium | beta | Saturation / distortion level |
| `pitch_dev_cents` | −50 to +50 cents | low | laplace | Deviation from written pitch |
| `dynamic_center` | −30 to 0 db | very high | gaussian | Slow-moving baseline dynamic level. Mean reversion target for gain_db |

### 2.2 Key correlations seeded in Σ₀

| Dimensions | Correlation | Direction |
|---|---|---|
| `gain_db` ↔ `brightness` | 0.4 | positive |
| `gain_db` ↔ `pitch_dev_cents` | 0.3 | positive — louder tends sharper |
| `gain_db` ↔ `overdrive_drive` | 0.4 | positive |
| `gain_db` ↔ `dynamic_center` | 0.6 | positive |
| `filter_cutoff` ↔ `brightness` | 0.5 | positive — brighter when more open |
| `reverb_wet` ↔ `stereo_width` | 0.4 | positive |
| `timing_offset_ms` ↔ `pitch_dev_cents` | 0.2 | positive |

### 2.3 Pipeline wiring

Each dimension maps to an existing pipeline location:

| Dimension | Pipeline location | Change required |
|---|---|---|
| `gain_db` | mixer.py | Already wired |
| `brightness` | fx.py / eq | Already wired |
| `timing_offset_ms` | scheduler.py | Already wired |
| `attack_shape` | envelope.py | Already wired |
| `release_shape` | envelope.py | Add state-driven release curve |
| `reverb_wet` | fx.py reverb | Already wired |
| `filter_cutoff` | fx.py filter | Add continuous state read |
| `filter_resonance` | fx.py filter | Add continuous state read |
| `stereo_width` | mixer.py | Add state-driven width |
| `overdrive_drive` | fx.py overdrive | Add continuous state read |
| `pitch_dev_cents` | pitch.py | Add additive offset on written pitch |
| `dynamic_center` | kalman.py | Internal — mean reversion target for gain_db |

---

## 3. New Process Model — Discrete Golem

A third process model alongside Kalman and Random Walk.

The state is fixed for the duration of the region. No drift, no AR(2) momentum, no reaction to score markings. The user sets explicit values for each dimension.

```yaml
golems:
  - from: 0
    to: 30
    type: discrete
    state:
      gain_db: -6
      brightness: 0.3
      filter_cutoff: 800
      filter_resonance: 0.2
      reverb_wet: 0.5
      overdrive_drive: 0.0
      pitch_dev_cents: 0.0
      stereo_width: 0.6
      timing_offset_ms: 0.0
      attack_shape: 0.5
      release_shape: 0.5
      dynamic_center: -12
```

Unspecified dimensions fall back to their default values.

Implementation: in `interpreter.py`, when `_resolve_golem_type` returns `discrete`, skip the predict/update cycle entirely and return the fixed state vector directly.

---

## 4. Dimension Output Visualization

A line plot panel showing the output value of each state dimension over time as the piece renders.

- One line per dimension, color coded
- X axis — time in seconds
- Y axis — normalized to each dimension's range
- Score events shown as vertical markers on the time axis
- Can be toggled per dimension
- Available as both live (scrolling during render) and post-render (static)

Location: interpreter workspace, below the existing panels.

---

## 5. Dimension Configuration in the Interface

Each dimension exposes two additional controls in the interpreter workspace:

**Range** — the user can set the minimum and maximum value for each dimension. The Kalman state is clipped to this range after sampling. Defaults are the physical limits listed in section 2.1.

```yaml
dimension_config:
  gain_db:       {min: -40, max: 6}
  filter_cutoff: {min: 200, max: 8000}
  pitch_dev_cents: {min: -20, max: 20}
```

**Distribution** — the user can select the sampling distribution per dimension. Options are the distributions supported by the engine: gaussian, laplace, beta, student_t, cauchy, uniform, bimodal, mixture. Defaults are listed in section 2.1.

```yaml
dimension_config:
  timing_offset_ms: {distribution: laplace}
  pitch_dev_cents:  {distribution: laplace}
  brightness:       {distribution: beta}
  gain_db:          {distribution: gaussian}
```

Both are set per dimension and per regime — a lyrical regime can have a narrow range for pitch_dev_cents while a turbulent regime has a wide one, using different distributions for the same dimension.

### 5.1 Interface location

In the interpreter workspace, each dimension in the golem editor has:
- A range slider with min/max handles
- A distribution dropdown

These apply to the currently selected golem region.

### 5.2 Files to modify for this feature

| File | Change |
|---|---|
| `editor/static/js/interpreter.js` | Add range slider and distribution dropdown per dimension in golem editor |
| `editor/static/js/state.js` | Store dimension_config per golem in interpState |
| `src/kalman.py` | Read per-dimension range and distribution from config at sampling time |
| `src/character.py` | Include dimension_config in regime preset definitions |

---

## 6. Files to modify

| File | Change |
|---|---|
| `src/fx.py` | Add filter, chorus, tremolo. Add section and global scope. Remove composer names from morphogenics dispatch. Add new parameters to existing FX. |
| `src/mixer.py` | Add stereo_width state read. Add release_shape state read. |
| `src/pitch.py` | Add pitch_dev_cents additive offset from state. |
| `src/envelope.py` | Add release_shape state read. |
| `src/kalman.py` | Expand state to 12D. Update Q_base, A1, A2 defaults. Add dynamic_center as mean reversion target for gain_db. Seed Σ₀ with correlations. Read per-dimension range and distribution from config at sampling time. |
| `src/interpreter.py` | Add discrete golem type. Add 12D state wiring. |
| `src/character.py` | Update regime presets for 12D state. Include dimension_config in preset definitions. |
| `src/transition_table.yaml` | Update H and R matrices for 12D state. |
| `plugins/__init__.py` | Remove composer name grouping. Rename plugins by technique. |
| `editor/static/js/interpreter.js` | Add dimension output line plot. Add discrete golem UI. Add range slider and distribution dropdown per dimension. |
| `editor/static/js/state.js` | Update interpState for 12D. Store dimension_config per golem. |
| `docs/score_reference.md` | Document fx_sections, fx_global, discrete golem, new dimensions, dimension_config. |
