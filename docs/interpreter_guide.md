# Opus One — Interpreter Guide (for musicians)

This guide is for using the **Interpreter**, the part of the program that plays your score expressively. You don't need any technical background. If you know what "play this passage louder", "push forward into the crescendo" or "give it a darker sound" means, you know enough.

For how the engine works underneath, and the score and `config.yaml` settings, see [v2.md](v2.md).

---

## What the Interpreter does

You give it a score and audio. It plays the audio as a performer interpreting the score would: louder and softer as the markings ask, with its own timing, touch, colour, space and rubato. Every run is a slightly different performance, unless you fix the seed.

---

## What you're working with

1. **The audio**: the sound material that gets shaped. It can be a recording, a drone, stems, or the samples your score triggers.
2. **The score**: a `.yaml` file made in the Composer, with events (samples placed in time), dynamic markings (p, mf, ff, crescendo…), phrases and tempo changes.
3. **The golems**: the performers. You place them on a timeline and give each one a personality. Each golem plays its stretch of the piece in its own way; where golems overlap, their personalities blend.

---

## Your first interpretation

1. **Open the Interpreter.** Click the **Interpreter** tab at the top.
2. **Load the score.** In the top bar, pick your score `.yaml`. The markings and phrases appear on the score overview.
3. **Load the audio**, if the score doesn't name it already.
4. **Make a golem.** In the left sidebar click **+ New Golem**. You get a **Kalman** golem with the **lyrical** preset covering the first quarter of the piece (at most 30 s).
5. **Place it.** On the golem strip, drag the middle to move it and the edges to resize it. For a first test, cover the whole piece.
6. **Choose what it shapes.** In the top bar, the **mix dims** checkboxes choose which of the golem's decisions you hear (see [Mix dims](#mix-dims-what-the-golem-is-allowed-to-shape)). Start with **gain**, then add more.
7. **Play.** Set the play mode to **Interp** and press **▶ Play**. The trace of that performance appears in the bottom panel, with a yellow cursor following the playback.
8. **Change things while it plays.** Edit the golem, tick a mix dim or move a marking: the playing performance re-renders half a second after your last edit. **← Undo** / **→ Redo** work for all of it.
9. **Hear another performance.** Clear the **seed** box and press Play again.

The play modes in the Interpreter are:
- **Raw**: the source audio, untouched.
- **Score**: the score exactly as written, with no golems and no random variation.
- **Interp**: the golems' performance.

---

## The three golem types

Pick a type with the buttons at the top of the golem editor.

### Kalman: the musical performer

It reads the score's markings and responds like a trained musician: it follows the dynamics, anticipates the next marking, has momentum (it was loud a moment ago, so it doesn't jump), and adds its own expression around what's written. This is what most pieces want.

| Preset | Character |
|---|---|
| **dramatic** | Big contrasts and sudden jumps; dark, roomy, punchy; plays a little over the marking; loose timing; strong rubato |
| **lyrical** | Smooth and singing; bright, soft attacks, long releases; free rubato |
| **sparse** | Quiet (under the marking), stable and dry; percussive attacks; narrow; tight timing; little rubato |
| **turbulent** | Wild and unstable, with occasional extreme moments; loud, dark resonant filter, some drive; wide |
| **disciplined** | Follows the markings closely and steadily; tight timing; almost strict tempo |
| **impressionist** | Loose about the markings; soft attacks, long tails, lots of space; wide; the freest rubato |
| **impulsive** | No momentum, sudden outliers; sharp attacks, bright, some drive; loose timing |
| **volatile** | Flips between two states; quick transitions; some drive; wide |
| **sight_reading** | Doesn't anticipate: reacts to each marking as it arrives; loose timing |
| **memorised** | Knows what's coming and prepares early; steady and smooth |

### Random Walk: the drifter

It ignores the markings and wanders through its dimensions by its own rules (step size, drift, pull back home). It gives stochastic texture rather than interpretation; good for drones and sound art.

Presets:
- **rw_free**: wanders freely.
- **rw_drift_up** and **drift_down**: rise or sink steadily.
- **rw_reverting** and **anchored**: wander, but are pulled back home (anchored more strongly).
- **breathing**: swells slowly, about every 8 s.
- **free_improv**: big steps.
- **dream**: tiny, slow steps.
- **erratic**: big, sudden jumps.

### Discrete: a fixed colour

It holds every dimension at values you set, for its whole range: "this passage is loud, dark, very wet, narrow". There is no movement and no randomness.

Where different types overlap, **Kalman wins**. Random Walk and Discrete apply only where every active golem has that type.

---

## Presets and tuning

Clicking a preset sets all of the golem's settings at once. Two sliders adjust it:

- **Intensity**: how strongly the preset's character shows. 0 is neutral, 1 is the preset, 2 is exaggerated.
- **Smoothness**: above 1 the performer commits and glides; below 1 it hesitates and jitters.

The editor's lettered sections hold everything else. The ones musicians reach for most:

- **B: Process noise**
  - **Q×**: how much it wanders between markings.
  - **Timing looseness**: how loosely notes are placed in time.
  - **Rubato**: how much it bends the tempo.
- **C: Observation**: how closely it follows the markings (obs weight).
- **D: Lookahead**
  - **λ**: how well it knows the piece (0.2 = sight-reading, 0.95 = memorised).
  - **Transition lead**: how early it starts moving toward the next marking.
  - **Transition shape**: the curve of that move (sigmoid, ramp, exponential, step).
- **F: Distribution**: the kind of randomness. Gaussian is even; Laplace and Cauchy have jumps and outliers; bimodal flips between two states. **Tame outliers** caps the wildest values.
- **H: Envelope and blending**: **weight**, **fade in / fade out** (to cross-fade between golems) and the fade curve.
- **I: Starting values**: where each dimension starts. Blank means the preset's own resting value.

---

## The 13 dimensions: what a golem decides

At every moment a golem decides 13 things at once. The preset shapes all of them. Which ones you **hear** depends on the mix dims (below); the per-note ones are heard whenever the score has events.

| Dimension | What you hear | Heard when |
|---|---|---|
| **Gain** | Loudness, following the markings and hairpins | `gain` ticked |
| **Brightness** | Treble up or down (a shelf around 4 kHz, ±8 dB) | `brightness` ticked |
| **Timing** | Each note a little early or late (typically 9–20 ms; up to ±50) | always, on events |
| **Attack** | Each note's onset: short and percussive (low) to a slow swell (high) | always, on events |
| **Release** | Each note's end: held then cut (low) to a long decaying tail (high) | always, on events |
| **Reverb** | Reverb added on top: 0 none, 1 as loud as the original | `reverb` ticked |
| **Filter cutoff** | A low-pass filter sweeping with the performance | `filter` ticked |
| **Filter Q** | Resonance of that filter: a peak at the cutoff | `filter` ticked |
| **Stereo width** | 0 mono, 0.5 as recorded, 1 twice as wide | `width` ticked (stereo audio only) |
| **Overdrive** | Saturation: 0 clean, 0.3 clearly driven, 1 fully saturated | `drive` ticked |
| **Pitch** | Each note a few cents sharp or flat (typically ±3–5) | `pitch` ticked, on events |
| **Dynamic centre** | A compressor's threshold: low values squeeze loud and soft together | `dynamics` ticked |
| **Tempo** | Rubato: presses forward in crescendos, holds back in decrescendos, broadens into phrase ends | `tempo` ticked |

---

## Mix dims: what the golem is allowed to shape

The **mix dims** checkboxes in the top bar decide which of the golem's decisions reach the sound. They act on the whole mix: the source audio and the events together. So even a score with no events, just a recording, gets shaped by the golems.

- **gain** (on by default): the golem carries the dynamics. With golems active it replaces the score's dynamics curve.
- **brightness, filter, reverb**: colour and space. How strongly these follow the dynamics (brighter, more open and wetter when louder) is set by **pull** in the top bar: 0 means they wander freely, 1 means they track the dynamics strictly.
- **width**: stereo image. It is dimmed when the audio is mono.
- **drive, pitch, dynamics**: grit, intonation, compression.
- **tempo**: rubato. The playback stretches with it and the cursor follows. It works together with the score's own tempo changes.

Start with gain. Add one at a time and listen to what each brings.

---

## The trace: the performance, drawn

The bottom panel shows the performance over time, one colour per dimension:

- Only the dimensions you **hear** are drawn. In the legend (top right) the others are greyed out, so you can see what is available but off.
- Each dimension uses its **full range** from bottom to top: gain from −40 to +6 dB, the filter from 20 Hz to 20 kHz (log scale), tempo ±30 %, and so on. A small wobble looks small.
- **Bold lines** show the plan (the performer's intention). **Dots** show the actual choices, note by note and step by step.
- **Hover** to see the exact values at any moment. During playback a **yellow cursor** shows where you are.
- **◈ Trace** draws the trace without playing. Set **walks** above 1 to draw several performances at once (seeds n, n+1, …): the first in bold, the others faint, so you can see how much they vary.
- **↓ PNG** saves the picture.

After you press Play, the trace is the performance you heard.

---

## The seed: the same performance again

- **Empty seed box**: every Play is a new performance.
- **A number**: the same performance every time.

After Play or Trace, the box fills with the seed that was used, so the next Play repeats that performance while you adjust other things. Clear the box for a new one.

---

## Saving, loading and exporting

- **↓ Save** (with a **name**) writes an *interpretation* to `interpretations/`. It holds the golems, the engine settings, the mix dims, pull, trace step, seed, and which score it belongs to.
- **Load** an interpretation: its score is loaded too, and everything is restored as saved.
- **↓ WAV** renders the interpretation to `output/<name>.wav`. The export popup sets the **loudness**: leave it as performed, match the source, or reach a target (−14 / −16 / −23 LUFS). It also has a **safety brake** that keeps peaks under −1 dB. Exporting the whole piece keeps the reverb and fade tails. See [Loudness and the safety brake](editor.md#loudness-and-the-safety-brake).
- **Concerto** turns a performance into a score video; see [editor.md](editor.md).

One score can have many interpretations: `calm.yaml`, `stormy.yaml`…

---

## Common situations

### "It sounds too wild"
- Choose a calmer preset: lyrical, disciplined or memorised; anchored or dream for random walks.
- Lower **Intensity**, or turn on **Tame outliers** (section F) with a cap of 2–2.5.
- Raise **obs weight** (section C) so it follows the markings more closely.

### "It sounds too tame"
- Choose dramatic, turbulent, impulsive or volatile; erratic or free_improv for random walks.
- Raise **Intensity**, **Q×** or **Timing looseness**.
- Tick more mix dims: filter, reverb, drive, tempo.

### "Every run sounds the same"
- Clear the **seed** box. It fills after each run, so every Play after that repeats the performance until you clear it.
- Check the play mode is **Interp**, not Score.

### "I can't hear the timing, attack or pitch"
- These act on the score's **events**. A score that is only a recording has none; use the mix dims instead.

### "The rubato is too much / too little"
- Change **Rubato** (section B): 0 is strict, 1 is the default amount, 2 is very free. Disciplined uses 0.3; impressionist uses 1.6.
- Rubato needs shape to respond to: hairpins, changes of dynamics and **phrases**. Mark your phrases in the Composer, and the tempo broadens into each phrase end.

### "My golems fight each other"
- Overlapping Kalman golems blend by **weight** and fades. Use **fade in / fade out** (section H) for smooth hand-overs.
- A Kalman golem overlapping a random walk wins. Give each its own region.

### "I want the score exactly as written"
- Use play mode **Score**. Golems are off and there's no random variation.

---

## The loop, in brief

1. Load score (and audio).
2. **+ New Golem**, pick a preset, drag it into place.
3. Tick the mix dims you want.
4. **▶ Play** in **Interp** mode; look at the trace.
5. Adjust while it plays; **← Undo** if you go too far.
6. Clear the seed for another performance, or keep it to refine this one.
7. **↓ Save** the interpretation; **↓ WAV** to export.

---

## A few intuitions

- **Kalman interprets, Random Walk improvises, Discrete holds a colour.**
- **Mix dims are the performer's hands**: what it is allowed to touch.
- **Pull** decides whether colour follows the dynamics or wanders on its own.
- **The seed is the take**: empty means "surprise me", a number means "that one again".
- **The trace is the performance**: what you see is what you heard.
