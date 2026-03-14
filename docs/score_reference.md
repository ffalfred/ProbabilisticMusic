# Score Format Reference

Scores are YAML files. They fully describe a composition: which audio fragments to extract from the base track, when and how to play them back, how the dynamics should evolve, and what effects to apply.

The editor can generate these files for you (Export YAML), but they are also human-readable and hand-editable.

---

## Minimal example

```yaml
samples:
  stab_a:
    from: 0.5
    to: 2.0

events:
  - sample: stab_a
    t: 5.0
    speed: 1.0
    gain_db: -6
```

`base_track` is not stored in the score file itself — it is supplied as a CLI argument when rendering. This keeps scores portable (the same score can be applied to different source files).

---

## Top-level keys

| Key | Required | Description |
|-----|----------|-------------|
| `samples` | yes | Named audio fragments cut from the base track |
| `events` | yes | Playback triggers referencing samples |
| `dynamics` | no | Dynamic levels and crescendo/decrescendo curves |
| `tempo` | no | Time-warp regions (accelerando / ritardando) |
| `base_fx` | no | FX applied globally to the entire base track |
| `fx_ranges` | no | FX applied to specific time regions of the base track |
| `silence_start` | no | Seconds of silence prepended before events are placed |
| `duration` | no | Used for validation — triggers assertions if events/samples exceed it |

---

## `samples:`

Defines named audio fragments by cutting time ranges from the base track. The base track always plays in full regardless of what samples are defined.

```yaml
samples:
  fragment_name:
    from: 4.2      # start time in seconds (inclusive)
    to: 7.8        # end time in seconds (exclusive)
```

Sample names can be anything (letters, numbers, underscores). They are referenced by name in `events:`. Define as many or as few as you need — unused samples are harmless.

---

## `events:`

Each event is one playback trigger: "play this sample at this time with these transformations."

```yaml
events:
  - sample: fragment_name    # required — must match a key in samples:
    t: 10.0                  # required — playback start time in seconds

    # --- optional parameters ---
    speed: 1.0               # varispeed factor (default: 1.0)
    speeds: [0.5, 1.0, 2.0]  # layered transpositions (see below)
    gain_db: -6              # amplitude in dB (default: -6)
    loop: 0                  # repeat count after first play (default: 0)
    reverse: false           # play clip backwards (default: false)
    fx:                      # list of effects applied to this event
      - type: reverb
        reverberance: 60
```

### `speed`
Varispeed factor. Changes both pitch and duration simultaneously, like tape varispeed.

| Value | Effect |
|-------|--------|
| `1.0` | original speed and pitch |
| `0.5` | half speed, one octave down, twice as long |
| `2.0` | double speed, one octave up, half as long |
| `0.75` | slightly slower, slightly lower pitch |

### `speeds`
A list of speed values played simultaneously as separate layers. The layers are summed before gain and FX are applied. Useful for:
- **chords**: `[0.5, 0.595, 0.75]` plays three harmonic ratios at once
- **clusters**: many closely-spaced values create a dense texture
- **octave doublings**: `[0.5, 1.0, 2.0]`

When `speeds` is set, the `speed` key is ignored.

### `gain_db`
Amplitude gain in decibels. Negative values are quiet, positive values are louder than the original.

| Value | Amplitude |
|-------|-----------|
| `0` | unity gain (same as original) |
| `-6` | half amplitude (−6 dB ≈ 0.5×) |
| `-12` | quarter amplitude |
| `-20` | quite quiet |
| `-40` | barely audible |

### `loop`
Number of additional repeats. `loop: 0` plays once. `loop: 3` plays the clip 4 times total. The entire looped clip (all repetitions) then has gain and FX applied to it as a unit.

### `reverse`
`true` or `false`. The clip is reversed before all other processing.

### `fx`
A list of effect objects. Applied to the event's clip after speed, loop, and gain. Currently supported: `reverb`, `delay` (see Effects Reference below).

---

## `dynamics:`

A list of dynamic markings. Two kinds are mixed freely in the same list:

### Point marks
Set the amplitude level at a moment in time. Holds until the next point mark.

```yaml
dynamics:
  - t: 0.0
    mark: pp        # starts very quiet

  - t: 4.5
    mark: mf        # jumps to medium-forte at 4.5s

  - t: 12.0
    mark: p         # drops back to piano
```

Available levels (quietest to loudest):

| Mark | Amplitude | Name |
|------|-----------|------|
| `ppp` | 0.10 | pianississimo |
| `pp` | 0.20 | pianissimo |
| `p` | 0.35 | piano |
| `mp` | 0.50 | mezzo-piano |
| `mf` | 0.65 | mezzo-forte |
| `f` | 0.80 | forte |
| `ff` | 0.90 | fortissimo |
| `fff` | 1.00 | fortississimo |

### Range marks
Define a crescendo or decrescendo across a time span. Linearly interpolates between the amplitude values of the surrounding point marks.

```yaml
dynamics:
  - t: 0.0
    mark: pp

  - from: 1.0
    to: 4.0
    mark: crescendo    # pp → mf over 3 seconds

  - t: 4.0
    mark: mf
```

Range marks require surrounding point marks to know what values to interpolate between. A range without nearby point marks will interpolate from/to whatever the envelope holds at those positions (which defaults to 1.0 if no point marks have been set before it).

---

## `tempo:`

Time-warp regions. These compress or expand the timeline for event placement — they do not affect the base track's playback speed or individual sample durations.

```yaml
tempo:
  - from: 8.0
    to: 11.0
    mark: accelerando    # optional label (for editor display)
    factor: 1.4          # > 1 = accelerando; < 1 = ritardando
```

A `factor` of `1.4` means events in this region are placed 1.4× sooner than their score time implies. A `factor` of `0.7` spreads them out — ritardando.

Tempo ranges are applied to event `t` values only. They do not affect the base track or the duration of played samples.

---

## `base_fx:`

A list of effects applied to the entire base track before any samples are mixed in. Same format as per-event `fx:`.

```yaml
base_fx:
  - type: reverb
    reverberance: 30
```

Applied once, at render time. Has no effect on the composed samples layered on top.

---

## `fx_ranges:`

Effects applied to specific time segments of the base track. The segment is extracted, processed, replaced. Reverb tails can bleed past the zone's `to` boundary.

```yaml
fx_ranges:
  - from: 20.0
    to: 28.0
    fx:
      - type: reverb
        reverberance: 80

  - from: 45.0
    to: 50.0
    fx:
      - type: delay
        delay_sec: 0.4
        feedback: 0.5
```

Applied after `base_fx` and before events are mixed in.

---

## Effects reference

### `reverb`

```yaml
- type: reverb
  reverberance: 60    # 0 (dry) to 100 (maximum reverb)
```

Implemented via SoX `reverb`. A value of 50 gives a medium room. 80+ gives a long hall or cave-like tail.

### `delay`

```yaml
- type: delay
  delay_sec: 0.3      # gap between echoes, in seconds
  feedback: 0.4       # echo decay per tap (0 = one echo, 0.9 = many)
```

Three echo taps are generated at `delay_sec`, `2 × delay_sec`, and `3 × delay_sec`, with amplitudes of `feedback`, `feedback²`, and `feedback³`. Implemented via SoX `echo`.

---

## Probabilistic parameters

Any numeric parameter in an event can be replaced with a probabilistic specification. The value is resolved fresh on each call to the renderer (or each press of **▶ Mix** in the editor). This means the same score produces a different performance every time.

### Uniform range

```yaml
speed: [0.6, 1.4]    # drawn uniformly between 0.6 and 1.4
```

### Gaussian distribution

```yaml
speed:
  distribution: gaussian
  mean: 0.75
  std: 0.08
```

### Uniform distribution (explicit)

```yaml
gain_db:
  distribution: uniform
  low: -12
  high: -3
```

### Discrete choice

```yaml
loop:
  distribution: discrete
  values: [0, 1, 2, 4]
  weights: [0.5, 0.25, 0.15, 0.1]    # optional; uniform if omitted
```

### Bernoulli (boolean)

```yaml
reverse:
  distribution: bernoulli
  p: 0.3    # 30% chance of reversing
```

Probabilistic parameters apply to: `speed`, `gain_db`, `loop`, `reverse`, and any FX parameter (`reverberance`, `delay_sec`, `feedback`). The `t` and `sample` fields are always fixed. The `speeds` list is resolved element-by-element (each entry can itself be probabilistic).

---

## Complete annotated example

```yaml
# --- Samples: cut from the base track ---
samples:
  stab_a:
    from: 0.5
    to: 2.0
  texture_b:
    from: 2.0
    to: 4.0

# --- Dynamics: overall composition amplitude ---
dynamics:
  - t: 0.0
    mark: pp                  # begin very quietly
  - from: 1.0
    to: 3.5
    mark: crescendo           # swell from pp to mf
  - t: 3.5
    mark: mf
  - from: 8.0
    to: 10.0
    mark: decrescendo         # fade out
  - t: 10.0
    mark: p

# --- Tempo: time-warp events into a brief acceleration ---
tempo:
  - from: 4.0
    to: 6.5
    mark: accelerando
    factor: 1.4

# --- Base FX: subtle reverb on the source material ---
base_fx:
  - type: reverb
    reverberance: 20

# --- FX Zones: heavy reverb on a specific passage ---
fx_ranges:
  - from: 7.0
    to: 9.0
    fx:
      - type: reverb
        reverberance: 85

# --- Events: the composition ---
events:
  # simple playback
  - sample: stab_a
    t: 1.0
    speed: 1.0
    gain_db: -6

  # reversed, with a randomised speed (different on every render)
  - sample: stab_a
    t: 3.5
    reverse: true
    speed:
      distribution: gaussian
      mean: 0.75
      std: 0.08
    gain_db: -9
    fx:
      - type: delay
        delay_sec: 0.3
        feedback: 0.4

  # three simultaneous pitches via layered transpositions
  - sample: texture_b
    t: 6.0
    speeds: [0.5, 1.0, 2.0]
    gain_db: -12
    fx:
      - type: reverb
        reverberance: 60
```
