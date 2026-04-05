# Opus One — Interpreter Guide (for musicians)

This is a guide for using the **Interpreter**, the part of the program that plays your score expressively. You don't need any technical background. If you know what "play this passage louder", "hold that chord longer", or "give it a darker sound" means, you know enough.

---

## What the Interpreter does, in one sentence

You give it a score and an audio file. It plays back the audio as if a performer were interpreting the score — with gentle or wild expressive variations. Every time you press play, you get a slightly different performance.

---

## The three things you're working with

1. **The audio file** (base track) — the raw sound material. Could be a drone, a recording, a bed of noise, whatever. This is what will be *shaped*.

2. **The score** — a YAML file that tells the performer what's where: samples, dynamic markings (p, mf, ff), phrases, tempos. Already created in the Composer and exported as `.yaml`.

3. **The golems** — these are the performers you create inside the Interpreter. You place them on a timeline and configure their personality. Each golem plays a region of the piece in its own way.

---

## Step-by-step: your first interpretation

### 1. Open the Interpreter

There are three workspace tabs at the very top of the app: **Composer**, **Interpreter**, **Conductor**. Click **Interpreter**.

### 2. Load your score

At the top of the Interpreter there's a row of inputs. The first one says "click to select score…". Click it, pick your `.yaml` file, then click **Load**.

If it worked, you'll see the dynamics markings and any phrases drawn on the score overview.

### 3. Load your audio

Right next to the score row, find the **audio** input. Click it, pick your `.wav` or audio file, click **Load**. The waveform appears at the top of the main view.

If the score already knows which audio belongs to it, this might auto-fill.

### 4. (Optional) Load score images

If you have reference images — a PDF page, a diagram, notes — you can load them via **Score Img** and **Meta Img**. They're just visual aids; they don't affect the sound.

### 5. Create your first golem

Look at the left sidebar. Near the top you'll see **+ New Golem**. Click it.

A new golem appears:
- on the **golem timeline** (the thin strip above the waveform),
- in the **golem editor** (in the left sidebar, where you configure it).

It defaults to a **Kalman** golem with the **lyrical** preset, covering the first 25% of the audio.

### 6. Place the golem

On the golem timeline strip, you can:
- **Drag its middle** to move it.
- **Drag its left/right edge** to resize it.

For a first test, make it cover the whole piece. Drag the left edge to 0s, drag the right edge to the end.

### 7. Trace it

At the bottom, click **◈ Trace**. This runs the golem silently and draws what it decided to do across all 12 "dimensions" (more on this below). A big timeline appears in the bottom panel.

You now see, visually, what the performer intends to do.

### 8. Play it

Top right corner, click **▶ Play**. The audio renders and plays with the golem's expressive shaping applied.

A yellow dashed cursor on the timeline tracks the playback. Loud moments in the audio correspond to the gain line moving up. Quiet moments correspond to it going down.

### 9. Try another run

Make sure the **seed** field (top bar) is empty. Click **Trace** again → you get a different expressive plan. Click **Play** → you hear a different performance of the same piece.

Every run is unique. That's the point.

---

## The three golem types

You pick a golem type from the three buttons at the top of the golem editor (**Kalman** / **Random Walk** / **Discrete**). Each behaves very differently:

### Kalman — the "musical performer"

Reads your score's dynamics markings (p, mf, ff, sfz, etc.) and responds to them like a real trained musician. Has memory: if it was loud a moment ago, it knows that, and drifts smoothly rather than jumping randomly.

**Use Kalman when:** you want the golem to *interpret* the score. Crescendos rise, ff moments push loud, p moments pull back, phrases are shaped musically. It's the "default" behavior most pieces will want.

Presets: `dramatic` (bold, punchy), `lyrical` (smooth, singing), `sparse` (quiet, minimal), `turbulent` (wild, unstable).

### Random Walk — the "drifter"

Ignores the score's dynamics markings entirely. Just wanders through the 12 dimensions according to its step size and distribution. Pure stochastic texture.

**Use Random Walk when:** you want unpredictable, noisy, experimental textures that don't follow the score's written dynamics. Good for drone pieces, sound art, chaos.

Presets: `rw_free`, `breathing`, `dream`, `erratic`, `free_improv`, `anchored`, etc. Try `rw_free` first, then experiment.

### Discrete — the "fixed timbre block"

Sets all 12 dimensions to specific values you choose, holds them constant for the whole region. No movement, no randomness.

**Use Discrete when:** you want a fixed character for a section — e.g. "this whole passage is loud, dark, heavy reverb, narrow stereo". You set each dimension's value explicitly.

---

## Presets and tuning

Once you pick a golem type, you can apply a **style preset** (like `lyrical` or `turbulent`) by clicking the buttons that appear. The preset sets all the golem's internal parameters at once.

Then two sliders let you fine-tune:

- **Intensity**: how strongly the preset's character shows. 0 = neutral (almost no variation), 1 = preset, 2 = amplified (more extreme).
- **Smoothness**: how much the performer "commits" vs "hesitates" between moments. Higher = smoother, more stable. Lower = jittery, more jumpy.

For a first pass, leave both at 1.0. Play with them later.

---

## The 12 dimensions (what the golem is deciding)

At every moment, the golem decides 12 things simultaneously. Most you'll never need to touch directly — they're just there, being shaped by the preset. But knowing what they are helps you read the timeline.

| Dimension | What it controls |
|---|---|
| **Gain dB** | Overall loudness |
| **Brightness** | How bright/dark the sound is (treble content) |
| **Timing ms** | Micro-timing: push-early or drag-late |
| **Attack** | How sharp onsets are |
| **Release** | How long tails linger |
| **Reverb** | Sense of space / wetness |
| **Filter cutoff** | Frequency at which highs get cut |
| **Filter Q** | How resonant the filter is |
| **Stereo width** | Narrow vs wide stereo image |
| **Overdrive** | Saturation / distortion amount |
| **Pitch cents** | Micro-pitch detuning |
| **Dyn center** | Slow-moving baseline loudness level |

Each one has a color on the timeline. You can hover over the timeline to see the exact values at any moment.

---

## The timeline (what you're looking at in the bottom panel)

After pressing **◈ Trace**, the bottom panel shows the 12 dimensions as colored lines over time. Think of it as the performer's plan, written out.

- **Bold colored lines**: the mean (what the performer is going to do, broadly).
- **Small dots around the lines**: individual random decisions moment-by-moment.
- **Dashed horizontal lines**: 0%, 25%, 50%, 75%, 100% of each dimension's range.
- **Grey vertical lines**: time ticks in seconds.
- **Yellow dashed vertical line (during play)**: where you are in the audio.

**Tip**: hover your mouse anywhere on the timeline. A cyan line appears with a tooltip showing the exact values at that instant. Useful for understanding what's happening at a specific moment you're hearing.

---

## Base modulation (how the golem shapes the base track itself)

This is important. By default, the golem's shaping is applied to every sample *event* triggered by the score. But if your base track is a continuous drone or recording, you'll want the golem to also shape the base audio itself.

In the left sidebar, under **base modulation**, there's a dropdown:

- **off** — only events are shaped. The base track plays raw. Use if events carry most of the sound.
- **gain** — the base's loudness breathes with the golem's gain decisions.
- **gain+center** (default) — loudness breathes, plus a slow underlying dynamic drift. Recommended starting point.
- **timbre** — no loudness change, but brightness and filter sweep the base. Gives timbral motion without volume changes.
- **full** — everything: gain + center + brightness + filter. Maximum expressivity.
- **custom…** — opens a gear popup where you pick each dimension individually.

**If your base track is a drone, noise, or continuous recording, start with "gain+center" or "full".**

---

## The seed — reproducibility

The **seed** field in the top bar controls randomness.

- **Empty** → every Trace generates new randomness. Different every time.
- **A number (e.g. 42)** → same trace, same audio, every time.

After clicking Trace, the seed field auto-fills with the seed that was used. That way, the audio you play next will **match** exactly what's on the timeline. If you want another variation, clear the seed field and Trace again.

**To share a specific run with someone**: save the interpretation (see below) — the seed is stored.

---

## Saving and loading your work

The golems you've placed + their configuration + the seed = an **interpretation**. You can save it as a `.yaml` file.

Top bar:

- **name** field: what to call the interpretation.
- **↓ Save**: writes an interpretation file to `interpretations/`.
- **↑ Load**: load a previously-saved interpretation.

You can iterate: save "version 1", change things, save "version 2", compare.

---

## Exporting audio

Also top bar: **↓ WAV** button. Renders the current interpretation and saves it to `output/<name>.wav`. Uses the `name` field you set.

If you want a bunch of different takes: press WAV, change the seed (or clear it), press Trace, press WAV again. You'll get multiple distinct renders.

---

## The right panel — visualizations

Right side of the Interpreter, there's a dropdown with different views of what the golem is doing. The list changes depending on which golem types you have active.

- For Kalman: posterior gaussians, Kalman gain, innovation, salience, etc.
- For Random Walk: step histogram, drift trajectory.
- For Discrete: fixed state bars.
- Always available: phase portrait, state trajectory, correlation web, distribution shape.

You don't need these to make the piece work — they're for understanding what's going on under the hood. Ignore them for a first pass.

---

## PNG export of the timeline

Bottom bar: **↓ PNG** button. Saves the current timeline as an image. Good for comparing the shapes of different runs side by side.

---

## Common situations and what to do

### "It sounds too wild / too extreme"

- Try a gentler preset: `lyrical` instead of `turbulent`, `anchored` instead of `erratic`.
- Lower the **Intensity** slider (in the preset controls) to 0.5 or less.
- In the golem editor, expand **Section F (Distribution)** and turn on **Tame outliers (σ cap)**. Set the cap to 2 or 2.5. This prevents the wildest random values.

### "It sounds too tame / too normal"

- Try a more extreme preset (`dramatic`, `turbulent`, `erratic`).
- Raise the **Intensity** slider to 1.5 or 2.
- Set base modulation to **full**.

### "Every run sounds the same"

- Check the **seed** field is EMPTY.
- Check base modulation is NOT "off" (otherwise the base plays identically each time, only events vary).

### "Audio doesn't match what I see on the timeline"

- Make sure you clicked **◈ Trace** first, THEN **▶ Play**. Trace locks in the seed; Play reuses it. If you reloaded the page or changed something in between, Trace again.

### "I have multiple golems and they're fighting"

- Golems in overlapping ranges blend if they're the same type (Kalman + Kalman). Their `weight` field controls who wins.
- If you mix types (Kalman + RW on the same region), the Kalman wins. If you want RW, make sure no Kalman golems cover that region.
- Use **fade_in** and **fade_out** (in the golem editor, Section H) to smooth transitions between different-character golems.

### "I want to hear the score's written dynamics"

- Use a **Kalman** golem. It reads markings and responds to them.
- **Random Walk** ignores markings by design.
- **Discrete** just holds a fixed state.

### "I want to freeze a specific take and keep tweaking"

- After Trace, copy the seed number from the top bar.
- Save the interpretation. The seed is preserved.
- Later, load it back. Clicking Trace will give the same trajectory; clicking Play will give the same audio.

---

## The workflow, in brief

1. Open Interpreter.
2. Load score and audio.
3. Click **+ New Golem**, pick a type and preset.
4. Drag it on the timeline to cover the range you want.
5. Set base modulation (start with **gain+center**).
6. Click **◈ Trace** → look at the timeline.
7. Click **▶ Play** → listen.
8. Don't like it? → clear seed, Trace again, Play again.
9. Like it? → **↓ Save** (preserves seed), **↓ WAV** (exports audio).

That's the whole loop. Repeat with different golem types, presets, and base-modulation settings until you find something you love.

---

## A few musical intuitions to keep in mind

- **Kalman = interpreter**: listens to the score, responds musically.
- **Random Walk = improviser**: has its own ideas, ignores the score's instructions.
- **Discrete = sustained color**: holds a single character for a section.

- **Base modulation** is how much the golem shapes the raw audio material. Off = only events. Full = everything breathes.

- **Seed** is reproducibility. Empty = surprise me. Fixed number = give me that exact take.

- **The timeline** is the performer's plan, not just a picture. What you see is what you'll hear.

---

Have fun. Every run is a different performance.
