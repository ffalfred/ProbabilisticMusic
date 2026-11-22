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
| `fx_sections:` | no | Effects on a time range of the whole output (source + events) |
| `fx_global:` | no | Effects on the whole output (source + events) |
| `silence_start:` | no | Seconds of lead-in: events start this much later |
| `silence_end:` | no | Seconds of silence added after the piece |
| `tracks:` | no | Multiple source audio files mixed into one base |
| `phrases:` | no | Per-phrase gain, fades, and local tempo changes |
| `articulations:` | no | Staccato, accent, fermata, legato applied to events |
| `note_rel:` | no | Glissando pitch curves across time ranges |
| `duck_key:` | no | One sample ducks the whole mix when it plays |
| `duck_base:` | no | Base track ducks whenever any event plays |
| `auto_mix:` | no | Automatic gain scaling to prevent dense passages from clipping |

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

### Optional sample fields

| Field | Type | Default | What it does |
|-------|------|---------|-------------|
| `track` | int | `0` | Which track index to slice from (see `tracks:`). `from`/`to` are timeline times, like everything else: on a track that starts at `from: 10`, a sample at 12–13 s is that track's own seconds 2–3. Parts of the range where the track isn't playing are silent. |
| `include` | list / `all` / `none` | `[fx]` | What the sample carries over from its track, out of `fx` (the track's FX chain), `fx_regions`, `automation` and `gain` — applied in that order. `all` = exactly what you hear on the track there; `none` = the file as it is. A track's mute is never carried, so a muted track can still be sampled. |
| `fade_in` | float | `0.05` | Fade-in as fraction of clip length (0–1) |
| `fade_out` | float | `0.05` | Fade-out as fraction of clip length (0–1) |
| `fade_curve` | string | `smooth` | Shape of the fades — see [Fade shapes](#fade-shapes) |

`fade_in` and `fade_out` set defaults for every event that uses this sample. An event can override them with its own `fade_in`/`fade_out` fields.

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

### `pitch` — semitone shift

Shifts the pitch of this event by a fixed number of semitones, without changing duration. Independent of `speed`.

```yaml
  - sample: kick
    t: 4.0
    pitch: -5      # 5 semitones down
    gain_db: -6
```

Fractional semitones are supported. Shifts smaller than 0.05 st are skipped as a no-op. Pitch from a `note_rel:` glissando overrides this value for events that fall inside the glissando range.

### `fade_in` / `fade_out` — per-event fades

Override the sample's default fades for this event. Values are fractions of clip length (0.0–1.0).

```yaml
  - sample: texture
    t: 8.0
    fade_in: 0.2     # fade in over the first 20% of the clip
    fade_out: 0.1    # fade out over the last 10%
    gain_db: -9
```

If omitted, the sample-level defaults apply (both default to `0.05`). An event can also set its own `fade_curve` (otherwise the sample's is used).

### Fade shapes

Every fade — sample and event fades (`fade_curve`), phrase fades (`fade_curve`) and FX-zone fades (`fade_curve`) — can take one of these shapes:

| `fade_curve` | Shape |
|---|---|
| `smooth` (default) | Equal-power (a quarter sine): sounds even, with no late drop. Two smooth fades crossing keep the total power steady. |
| `linear` | A straight line in amplitude (the only shape before this version). A linear fade-out seems to hold on and then drop away at the end. |
| `exponential` | A straight line in decibels over 60 dB: steady in loudness. A fade-in stays very quiet for a while, then rises; a fade-out falls away quickly, then lingers. |
| `s-curve` | Slow at both ends, faster in the middle. |

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

## Where effects go

| | Source only (before events are added) | Whole output (source + events, after tempo changes) |
|---|---|---|
| Whole piece | `base_fx:` | `fx_global:` |
| A time range | `fx_ranges:` | `fx_sections:` |

Per-event effects go in the event's own `fx:`, and per-track effects in `tracks:`.

## `fx_ranges:`

An FX zone on the source audio, before events are added (events play on top, unaffected).

```yaml
fx_ranges:
  - from: 10.0
    to: 16.0
    fx:
      - type: reverb
        reverberance: 80
    fade: true          # optional: blend the effect in and out
    fade_in_s: 0.5      # default: a tenth of the zone (0.01–1 s)
    fade_curve: smooth  # fade shape: smooth (default), linear, exponential, s-curve
    fade_out_s: 0.5
```

Without `fade`, the zone is replaced by its processed version, and any tail the effects add (reverb, delay) rings on past the zone. With `fade: true`, the original stays and the effect fades in and out over it.

## `fx_sections:`

An FX zone on the **whole output** — the source and every event — written exactly like `fx_ranges`. It is applied after tempo changes, but its times are score times (where you drew it), so it lands in the right place even after a ritardando.

```yaml
fx_sections:
  - from: 20.0
    to: 24.0
    fx:
      - type: filter
        cutoff: 400
    fade: true
```

The older form with one effect written flat in the section (`- {from: 20, to: 24, type: filter, cutoff: 400}`) still works; it gets short crossfades and no tail.

## `fx_global:`

An effect chain on the whole output, from start to end (a master chain). Applied after `fx_sections`.

```yaml
fx_global:
  - type: compress
    threshold: -18
```

---

## `silence_start:`

A lead-in: shifts all events later by the given number of seconds, while the source still plays from 0. Does not affect dynamics or phrase envelopes — those are still measured from time 0.

```yaml
silence_start: 2.0    # 2 seconds of source audio before the first event
```

## `silence_end:`

Seconds of silence added after the end of the piece (after any reverb tails), e.g. room before a video ends.

```yaml
silence_end: 3.0
```

Muted entries (`muted: true` — set by the editor's mute toggle) are left out of the render everywhere: events, dynamics, articulations, tempo ranges, phrases, note relations and FX zones.

---

## `tracks:`

Load multiple audio files as source material and mix them into a single base track. When `tracks:` is present, the top-level `base_track:` field is replaced by this list.

```yaml
tracks:
  - path: /path/to/drums.wav
    gain_db: -3
  - path: /path/to/pad.wav
    gain_db: -6
  - path: /path/to/bass.wav
    muted: true     # present but silenced
```

Each track entry accepts:

| Field | Type | Default | What it does |
|-------|------|---------|-------------|
| `path` | string | required | File path (`.wav`, `.mp3`, `.mp4`) |
| `gain_db` | float | `0` | Gain applied before mixing |
| `muted` | bool | `false` | Include in bank but exclude from base mix |

Tracks are indexed from 0 in order of appearance. Samples can be sliced from a specific track using the `track:` field on the sample:

```yaml
samples:
  kick:
    from: 1.2
    to: 1.8
    track: 0    # slice from the first track (default)
  bass_note:
    from: 3.0
    to: 3.4
    track: 2    # slice from the third track
```

---

## `phrases:`

Applies a multiplicative gain envelope to specific time regions of the final mix. Useful for shaping sections independently — quieting a dense passage, adding breath between phrases, or creating a local ritardando.

```yaml
phrases:
  - from: 0.0
    to: 8.0
    gain_db: -3        # reduce this section by 3 dB
    fade_in: 0.1       # fade in over the first 10% of the phrase
    fade_out: 0.15     # fade out over the last 15% of the phrase
    tempo_factor: 0.9  # local ritardando: events in this phrase arrive 10% later
```

| Field | Type | Default | What it does |
|-------|------|---------|-------------|
| `from` | float | required | Phrase start (seconds) |
| `to` | float | required | Phrase end (seconds) |
| `gain_db` | float | `0` | Gain offset for the phrase |
| `fade_in` | float | `0` | Fade-in as fraction of phrase length |
| `fade_out` | float | `0` | Fade-out as fraction of phrase length |
| `fade_curve` | string | `smooth` | Shape of the fades — see [Fade shapes](#fade-shapes) |
| `tempo_factor` | float | `1.0` | Local time compression/expansion (merged into `tempo:`) |

Phrase envelopes are applied after dynamics and after event mixing, so they shape the entire rendered result including the source track.

---

## `articulations:`

Performance marks: staccato, accent, legato and fermata. Each mark has a **target**:

- **`event`** (default) — the mark shapes the events it covers, before they are mixed. A point mark (`t:`) covers the event starting nearest to `t` (within 0.5 s); a range mark (`from:`/`to:`) covers every event starting inside the range. The source audio and other events are untouched; a point mark with no event within 0.5 s does nothing.
- **`mix`** — the mark shapes everything sounding at that time: the source plus all events. Over a range, staccato, accent and legato act at the **attacks detected in the mix** (moments where the sound suddenly gets louder), or on a regular grid every `every_s` seconds if you set it — useful on smooth material with no attacks.

```yaml
articulations:
  - type: staccato
    t: 4.0          # the event starting nearest to 4.0 s
    keep_s: 0.1     # plays only its first 0.1 s

  - type: accent
    from: 6.0
    to: 10.0        # every event starting between 6 and 10 s

  - type: staccato
    target: mix
    from: 12.0
    to: 14.0
    every_s: 0.25   # chop everything into 250 ms pulses

  - type: fermata
    target: mix
    t: 20.0
    hold_s: 3.0     # the whole piece waits 3 s, holding the sound at 20 s
```

| Type | On an event (`target: event`) | On the whole mix (`target: mix`) |
|------|-------------------------------|----------------------------------|
| `staccato` | Plays only its first `keep_s` (default 0.15 s), then a quick fade. Its effects (e.g. reverb) still ring after the cut. | Point: everything plays `keep_s`, then is silent for `silence_s` (default 0.07 s). Range: each attack plays `keep_s`, then silence until the next attack. |
| `accent` | Its first 50 ms are louder by `boost_db` (default 6 dB), easing back. | Point: everything is boosted at `t`. Range: every attack in the range is boosted. |
| `legato` | It rings on until the next event starts — if its sample runs out first, its last moment is held — then fades as the next event enters. With no later event, it ends on a long fade. | At `t` (point) or at each attack (range), the sound just before rings on across it while the new sound eases in. |
| `fermata` | Its last moment is held for `hold_s` (default 2 s), then fades. Nothing else moves. | The whole piece waits: the sound at `t` (a range: at `to`) is held for `hold_s` and inserted into the timeline, then everything — source and events — resumes. The piece gets `hold_s` longer, and the editor's cursor stops during the hold. |

| Field | Applies to | Default | What it does |
|-------|------------|---------|-------------|
| `target` | all | `event` | `event` or `mix` |
| `keep_s` | staccato | 0.15 | How much of the start plays |
| `silence_s` | staccato, mix point | 0.07 | Length of the cut |
| `boost_db` | accent | 6 | How much louder the attack is |
| `hold_s` | fermata | 2.0 | How long the hold lasts |
| `every_s` | mix ranges (staccato, accent, legato) | — | Act on a grid of this period instead of detected attacks |
| `freq_from` / `freq_to` | all | — | Limit the mark to a frequency band; the rest of the spectrum passes through |

Articulations are skipped in the performance-neutral ("Source / Raw") render.

---

## `note_rel:`

Applies a continuous pitch curve across a time range. Events that fall inside a glissando range have their `pitch` field replaced by an interpolated value.

```yaml
note_rel:
  - type: glissando
    from: 3.0         # start of the glissando in seconds
    to: 7.0           # end of the glissando
    from_pitch: 0.0   # pitch at t=from (semitones)
    to_pitch: 5.0     # pitch at t=to (semitones)
```

An event at `t: 5.0` would receive a pitch of `2.5` semitones — halfway between 0 and 5. The `pitch` field on individual events acts as the base value; `note_rel:` overrides it when the event falls inside a range.

Currently `glissando` is the only supported `type`. `from_pitch` defaults to `0.0` and `to_pitch` defaults to `2.0` if omitted.

---

## `duck_key:`

Triggers sidechain-style ducking whenever a specific sample plays. Every time the key sample is triggered, the whole mix dips and recovers.

```yaml
duck_key:
  enabled: true
  key: kick          # sample name that triggers ducking
  amount_db: -10.0   # how far to duck (negative = quieter)
  attack: 0.01       # time to reach full duck, in seconds
  release: 0.3       # time to recover back to full level
```

| Field | Type | Default | What it does |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Must be `true` to activate |
| `key` | string | required | Sample name that triggers ducking |
| `amount_db` | float | `-10` | Duck depth in dB |
| `attack` | float | `0.01` | Attack time in seconds |
| `release` | float | `0.3` | Release time in seconds |

Applied to the entire final mix after dynamics and phrases.

---

## `duck_base:`

Ducks the source (base) track whenever any event plays. Creates a pumping effect where your composed samples push down the underlying source audio.

```yaml
duck_base:
  enabled: true
  amount_db: -6.0
  attack: 0.01
  release: 0.3
```

Same fields as `duck_key:` except there is no `key` — every event triggers the ducking. Applied to the base track only, before events are layered on top.

---

## `auto_mix:`

Automatically reduces gain in regions where many events overlap, preventing clipping without manual gain adjustments.

```yaml
auto_mix:
  enabled: true
  mode: sqrt    # "sqrt" (default) or "inverse"
```

With `mode: sqrt`, a region with N simultaneous events is scaled by `1 / √N`. With `mode: inverse`, it is scaled by `1 / N`. `sqrt` is the musical default — it preserves more energy while still controlling peaks.

---

## Effects reference

### `reverb`
Adds room reverberation on top of the sound. The reverb rings on after the sound ends until it dies away.
```yaml
- type: reverb
  reverberance: 60    # default 50; how long it rings: 20 ≈ 0.3 s, 50 ≈ 2 s, 100 ≈ 11 s
  damping: 50         # 0–100, higher = darker tail
  room_scale: 100     # 0–100, room size
  pre_delay: 0        # ms before the reverb starts
  dry: 1.0            # level of the original (1 = full, 0 = reverb only)
  wet: 0.5            # level of the reverb (1 = as loud as the original)
```

### `delay`
Repeating echoes after the sound.
```yaml
- type: delay
  delay_sec: 0.3    # time between echoes in seconds
  dry: 1.0          # level of the original (1 = full, 0 = echoes only)
  wet: 0.5          # level of the first echo
  feedback: 0.6     # each echo is this much of the previous one (0 = a single echo)
```
With these values: the sound at full level, then echoes at 0.5, 0.3, 0.18, … until they fade below hearing.

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

### `spectral_inversion`
Inverts the spectral phase, creating hollow and flanged timbres. No parameters.
```yaml
- type: spectral_inversion
```

### `overtones`
Adds synthetic overtones (pitch-shifted copies) above the fundamental.
```yaml
- type: overtones
  n_harmonics: 3     # 1–8 overtone layers
  gain_db: -12       # level of first harmonic; subsequent ones taper off
```

### Morphogenics plugins
Any Morphogenics plugin can be used as an FX type directly in YAML. The type key always starts with `morpho_`:

```yaml
fx:
  - type: morpho_spectral_freeze
    mode: attacks
    n_partials: 20
    dry_wet: 80

  - type: morpho_grain_scatter
    grain_ms: 40
    pitch_spread: 6
    shuffle_pct: 30
    amplitude_var: 40
    dry_wet: 90
```

Any omitted parameter uses the plugin's default value. See [morphogenics.md](morphogenics.md) for the full list of plugins, their type keys, and all parameters.

---

## Automation — effect settings that change over time

Any numeric effect setting can be a **curve** instead of a number: a list of `[seconds, value]` points, joined by straight lines. Before the first point and after the last, the value holds.

```yaml
fx:
  - type: filter
    cutoff: {curve: [[0, 200], [2, 3000], [5, 400]]}   # opens over 2 s, closes over 3 s
  - type: reverb
    wet: {curve: [[0, 0], [4, 0.8]]}                   # the reverb swells in
```

Times are seconds from the **start of the audio the effect processes**: the event's sound (for an event's `fx`), the zone (`fx_ranges` / `fx_sections`), the track (a track's `fx`), or the whole piece (`base_fx`, `fx_global`).

**Exact** — every sample gets its own value:
- `reverb`, `delay`: `dry`, `wet`. A delay's `wet` is a send level: an echo keeps the level its sound was sent at.
- every Morphogenics plugin: `dry_wet`.
- `filter`: `cutoff`, `resonance`.
- `tremolo`: `rate`, `depth`.
- `pitch`: `semitones` / `cents` (Rubber Band follows the pitch curve).

**Approximated** — every other setting (e.g. `overdrive` drive, `reverberance`, `eq` gains, any Morphogenics setting): the effect is rendered with the values the curves have at a series of moments — every point, plus extra moments so they are at most 0.25 s apart, up to 12 — and the result moves smoothly from one render to the next. It is exact at those moments and blended in between: a sweep sounds like a crossfade of renders rather than one moving setting, and the effect costs one render per moment.

In the editor, the **~** button next to any numeric setting in an effect chain switches it to a curve, written `0s: 200, 2s: 3000, 5s: 400`.

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
