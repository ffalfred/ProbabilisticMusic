# Score Format Reference

A score is a text file written in YAML format. It describes your composition completely: which fragments to cut from the source audio, when and how to play them, what effects to add, and how the volume should evolve over time.

> **What is YAML?** It's a plain text format for structured data. Indentation matters — each level of indent means "this belongs inside the thing above it". The editor can generate score files for you (Export YAML), but they are also easy to read and edit by hand in any text editor.

---

## Minimal working example

The simplest possible score:

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

This cuts a 1.5-second fragment from the source audio (from 0.5s to 2.0s), names it `stab_a`, and plays it back at 5 seconds into the composition at half amplitude.

> The source audio file is **not** stored in the score. You supply it separately when rendering — this keeps scores reusable with different source files.

---

## All available sections

| Section | Required | What it does |
|---------|----------|-------------|
| `samples:` | yes | Names audio fragments cut from the source |
| `events:` | yes | Triggers that play samples at specific times |
| `dynamics:` | no | Volume levels and crescendo/decrescendo curves |
| `tempo:` | no | Regions where timing is compressed or stretched |
| `base_fx:` | no | Effects on the entire source track |
| `fx_ranges:` | no | Effects on a specific time range of the source track |
| `silence_start:` | no | Seconds of silence added before events are placed |

---

## `samples:`

Cuts named fragments from the source audio. Times are in seconds.

```yaml
samples:
  kick:
    from: 1.2    # start time in seconds
    to: 1.8      # end time in seconds

  texture:
    from: 8.0
    to: 12.5
```

- Names can be anything: letters, numbers, underscores (no spaces)
- Define as many as you want — unused ones are harmless
- The source audio always plays in full underneath, regardless of what you sample from it

---

## `events:`

Each event plays a sample at a specific time with specific settings.

```yaml
events:
  - sample: kick       # which sample to play (must match a name in samples:)
    t: 4.0             # when to play it, in seconds
    speed: 1.0         # playback speed (see below)
    gain_db: -6        # volume (see below)
```

### `speed` — pitch and duration together

Changes playback speed. Pitch and duration change together, like tape varispeed.

| Value | Effect |
|-------|--------|
| `1.0` | Original speed and pitch |
| `0.5` | Half speed — one octave lower, twice as long |
| `2.0` | Double speed — one octave higher, half as long |
| `0.75` | Slightly slower and lower |
| `1.5` | Slightly faster and higher |

### `speeds` — multiple pitches at once

Plays the same sample at multiple speeds simultaneously. All layers are summed together.

```yaml
  - sample: texture
    t: 10.0
    speeds: [0.5, 1.0, 2.0]    # three octaves at once
    gain_db: -12
```

Useful for chords, clusters, and rich harmonic textures. When `speeds` is set, `speed` is ignored.

### `gain_db` — volume

Volume in decibels. Negative = quieter than original.

| Value | Loudness |
|-------|---------|
| `0` | Same as the original recording |
| `-6` | About half as loud |
| `-12` | About a quarter as loud |
| `-20` | Quite quiet |
| `-40` | Barely audible |

### `loop` — repeat

How many extra times to play the clip after the first time.

```yaml
loop: 0    # play once (default)
loop: 3    # play 4 times total
```

### `reverse` — play backwards

```yaml
reverse: true    # play the sample backwards
reverse: false   # normal direction (default)
```

### `fx` — effects

A list of effects applied to this event. See the Effects section below.

```yaml
  - sample: kick
    t: 4.0
    gain_db: -9
    fx:
      - type: reverb
        reverberance: 70
      - type: delay
        delay_sec: 0.3
        feedback: 0.4
```

Multiple effects can be stacked — they are applied in order.

---

## `dynamics:`

Controls the overall volume shape of the composition. Two kinds of entry:

### Point marks — volume at a moment

```yaml
dynamics:
  - t: 0.0
    mark: pp       # very quiet at the start

  - t: 8.0
    mark: f        # suddenly louder at 8 seconds

  - t: 15.0
    mark: p        # back to quiet
```

The level holds until the next point mark. Available levels:

| Mark | Meaning | Relative volume |
|------|---------|----------------|
| `ppp` | pianississimo | very very quiet |
| `pp` | pianissimo | very quiet |
| `p` | piano | quiet |
| `mp` | mezzo-piano | medium quiet |
| `mf` | mezzo-forte | medium loud |
| `f` | forte | loud |
| `ff` | fortissimo | very loud |
| `fff` | fortississimo | maximum |

### Range marks — gradual change

```yaml
dynamics:
  - t: 0.0
    mark: p

  - from: 2.0
    to: 6.0
    mark: crescendo     # gradually get louder from p to whatever comes next

  - t: 6.0
    mark: f
```

The range smoothly interpolates between the levels of the surrounding point marks. `crescendo` and `decrescendo` (or `diminuendo`) are the valid range marks.

You can mix point marks and ranges freely in the same list.

---

## `tempo:`

Stretches or compresses when events are triggered. Does not affect the source track or the duration of individual clips.

```yaml
tempo:
  - from: 4.0
    to: 7.0
    mark: accelerando    # label (optional, shown in editor)
    factor: 1.4          # > 1 = accelerando, < 1 = ritardando
```

A `factor` of `1.4` means events in that region arrive 1.4× earlier than their `t` values imply. A `factor` of `0.7` spreads them out.

---

## `base_fx:`

Effects on the entire source audio, applied before anything else.

```yaml
base_fx:
  - type: reverb
    reverberance: 25
```

---

## `fx_ranges:`

Effects on a specific time segment of the source audio.

```yaml
fx_ranges:
  - from: 10.0
    to: 16.0
    fx:
      - type: reverb
        reverberance: 80
```

---

## Effects reference

### `reverb`
Adds room reverberation.
```yaml
- type: reverb
  reverberance: 60    # 0 = completely dry, 100 = maximum reverb
```

### `delay`
Repeating echoes.
```yaml
- type: delay
  delay_sec: 0.3    # time between echoes in seconds
  feedback: 0.4     # 0 = one echo, 0.9 = many slowly-fading echoes
```

### `overdrive`
Adds distortion.
```yaml
- type: overdrive
  gain: 20      # 0–100, how much distortion
  colour: 20    # 0 = harsh, 100 = warm
```

### `flanger`
Sweeping comb-filter effect.
```yaml
- type: flanger
  delay_ms: 0     # 0–30
  depth_ms: 2     # 0–10
  speed_hz: 0.5   # 0.1–10
```

### `pitch`
Shifts pitch without changing duration.
```yaml
- type: pitch
  cents: 300    # 100 = 1 semitone up, -100 = 1 semitone down, 1200 = 1 octave up
```

### `compress`
Reduces the dynamic range.
```yaml
- type: compress
  threshold_db: -20   # compression starts here
  ratio: 4            # 4:1 compression ratio
  attack: 0.01        # response time in seconds
  release: 0.3        # release time in seconds
  makeup_db: 0        # gain after compressing
```

### `eq`
Boosts or cuts a specific frequency.
```yaml
- type: eq
  freq_hz: 5000    # which frequency (Hz)
  gain_db: 6       # positive = boost, negative = cut
  q: 1.0           # higher = narrower band
```

Stack multiple `eq` entries for multi-band shaping:
```yaml
fx:
  - type: eq
    freq_hz: 200
    gain_db: 4
    q: 1.0
  - type: eq
    freq_hz: 8000
    gain_db: -3
    q: 0.8
```

---

## Probabilistic parameters

Any numeric value in an event can be replaced with a random distribution. The value is drawn fresh every time you render — so the same score produces a different performance each time.

### Uniform range (simplest)
```yaml
speed: [0.8, 1.2]     # random value between 0.8 and 1.2
```

### Gaussian (bell curve around a centre)
```yaml
speed:
  distribution: gaussian
  mean: 0.75     # centre of the distribution
  std: 0.08      # spread — smaller = closer to the mean
```

### Discrete choice
```yaml
loop:
  distribution: discrete
  values: [0, 1, 2, 4]
  weights: [0.5, 0.25, 0.15, 0.1]    # probabilities (must add up to 1.0)
```

If `weights` is omitted, all choices are equally likely.

### Bernoulli (random yes/no)
```yaml
reverse:
  distribution: bernoulli
  p: 0.3    # 30% chance of true
```

Probabilistic parameters work on: `speed`, `gain_db`, `loop`, `reverse`, and any effect parameter (e.g. `reverberance`, `delay_sec`, `feedback`). The `t` (time) and `sample` fields are always fixed.

---

## Complete example

```yaml
samples:
  stab_a:
    from: 0.5
    to: 2.0
  texture_b:
    from: 2.0
    to: 4.0

dynamics:
  - t: 0.0
    mark: pp
  - from: 1.0
    to: 3.5
    mark: crescendo
  - t: 3.5
    mark: mf
  - from: 8.0
    to: 10.0
    mark: decrescendo
  - t: 10.0
    mark: p

tempo:
  - from: 4.0
    to: 6.5
    mark: accelerando
    factor: 1.4

events:
  # simple playback
  - sample: stab_a
    t: 1.0
    speed: 1.0
    gain_db: -6

  # reversed with random speed, delay effect
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

  # three octaves at once with reverb
  - sample: texture_b
    t: 6.0
    speeds: [0.5, 1.0, 2.0]
    gain_db: -12
    fx:
      - type: reverb
        reverberance: 60
```
