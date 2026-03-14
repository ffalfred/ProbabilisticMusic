# The Score Editor

The editor is a local web application. It lets you visually annotate a waveform and video frame, build a score by drawing directly on the timeline, and immediately preview or render the result — all without touching a YAML file.

## Launching

```bash
cd beta_interpreter/editor
python server.py
# → open http://localhost:5000
```

---

## Loading a file

Type or paste the **absolute path** to a `.wav`, `.mp3`, `.flac`, or `.mp4` file into the path bar at the top and press **Load** (or Enter).

- For audio files: the waveform is displayed. Playback uses an audio element.
- For video files: the waveform is displayed and the first frame of the video is shown below it. Playback uses the video element.

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  path bar                                    [ Load ]    │
├────────────────────────────────┬────────────────────────┤
│  waveform canvas               │  score panel           │
│  (annotations drawn here)      │  (sample list,        │
│                                │   event list, etc.)    │
│  video frame canvas            │                        │
│  (same annotations mirrored)   │                        │
├────────────────────────────────┴────────────────────────┤
│  tool palette           [ ▶ Base ] [ ▶ Mix ]  [ Undo ]  │
├─────────────────────────────────────────────────────────┤
│  name: [untitled]  [ Base FX ]  [ Export YAML ]         │
└─────────────────────────────────────────────────────────┘
```

Both canvases are fully interactive. Whatever you draw on the waveform appears on the video frame and vice versa. The video frame canvas is particularly useful for marking musically significant moments that correspond to visual events.

---

## Navigation and playback

| Action | Effect |
|--------|--------|
| Click on waveform or frame | Move the cursor to that time |
| Drag on waveform or frame | Scrub the video/audio in real time |
| **Space** | Play / pause the original file |
| **▶ Base** button | Same as Space — plays the original unmodified |
| **▶ Mix** button | Renders the full composition and plays it back |
| The cursor (white dashed line) | Tracks `currentTime` on both canvases |

The **▶ Mix** button sends the current score to the server, runs the full pipeline (sample extraction → effects → mixing → normalisation), and plays the result in the browser. While rendering the button shows `⏳ rendering…`. Re-click to pause. Each press re-renders fresh from the current score state.

The time display (`t = X.XXXs / Ys`) is in the bottom-left corner of the video frame.

---

## Tools

Select a tool from the palette. The active tool determines what happens when you click or drag on either canvas.

### [ Sample ]
**Drag** to define a named sample region. A popup opens asking for a name and color. The region is stored in the score's `samples:` block and can be referenced by events.

The color is only for visual identification in the editor — it is stripped when exporting to YAML.

### ▶ Event
**Click** to place a sample trigger at that time. A popup opens where you configure:

- **sample** — which sample to play (dropdown of defined samples)
- **speed** — playback rate. `1.0` = original speed. Values below 1 slow down and lower pitch; above 1 speed up and raise pitch. This is varispeed — pitch and time change together, like tape.
- **speeds** — layered transpositions. A space-separated list of speed values (e.g. `0.5 1.0 2.0`) that are all played simultaneously. Useful for chords, clusters, or dense textures.
- **gain_db** — volume in decibels. `-6` is half amplitude. `-20` is very quiet.
- **loop** — how many times to repeat the clip after the first play. `0` = play once, `3` = play 4 times total.
- **reverse** — play the clip backwards.
- **fx** — apply reverb or delay to this event (see Effects below).

All numeric parameters accept probabilistic values (see Probabilistic parameters).

### ~ Dynamics
Dual-purpose tool depending on gesture:

- **Click** → place a **dynamic mark** at a point in time. Sets the amplitude level from that point forward until the next mark. Available marks: `ppp pp p mp mf f ff fff`.
- **Drag** → draw a **dynamic range** (crescendo or decrescendo). A popup asks whether to crescendo or decrescendo across the selected time span.

Dynamic marks and ranges work together: point marks define levels, ranges interpolate linearly between the surrounding levels.

### ⏱ Tempo
**Drag** to define a tempo range — a region where playback is warped in time. A popup asks for:

- **mark** — `accelerando` or `ritardando`
- **factor** — for accelerando: a factor > 1 compresses time (events happen sooner). For ritardando: a factor < 1 expands time.

Tempo ranges affect when events are triggered, not the pitch or duration of individual clips.

### ◆ FX
**Drag** to define a time range over which the **base track itself** is processed with reverb or delay. This is applied before samples are mixed in, so the effect is heard under the composition, not over it. Configure the same effect parameters as per-event FX.

---

## Effects

Both per-event FX and FX zones support two effect types:

### reverb
```
reverberance: 0–100    (0 = dry, 100 = maximum reverb)
```
Processed via SoX's `reverb` command. The tail can bleed past the zone boundary.

### delay
```
delay_sec: 0.1–2.0    (gap between echoes, in seconds)
feedback:  0.0–1.0    (echo decay, 0 = one echo, 0.9 = many)
```
Processed via SoX's `echo` command with three taps at `delay`, `2×delay`, `3×delay`.

---

## Base FX

The **Base FX** button (export bar, bottom) opens a global FX panel that applies effects to the entire base track — not a specific time range. This is applied first, before any FX zones or event FX. Useful for adding a global room reverb or gentle delay to the source material.

---

## Probabilistic parameters

Any numeric parameter in the event popup can be set to a fixed value, a uniform range, or a Gaussian distribution. Click the dropdown next to any field to switch modes:

| Mode | What it does |
|------|-------------|
| **fixed** | Always uses exactly this value |
| **range** | Picks a random value uniformly between min and max on each render |
| **gaussian** | Picks a value from a normal distribution with given mean and std |

This means the same score can produce a different performance every time you press **▶ Mix**. The probabilistic choices are resolved fresh on each render call.

---

## Right-click to delete

Right-click on any annotation (sample region boundary, event marker, dynamic mark, tempo zone, FX zone) on either canvas to delete the nearest one within a ~12px threshold.

---

## Undo

The **← Undo** button in the palette removes the last action. The history is per-session and is lost on page refresh.

---

## Exporting the score

1. Set a name in the `name:` field at the bottom.
2. Click **Export YAML**.

The score is saved to `beta_interpreter/scores/<name>.yaml`. The status bar shows the full path. This file can then be used directly with the CLI renderer.

---

## Score panel

The right-hand panel shows a live summary of:
- All defined samples (name, time range)
- All events (sample, time, key parameters)
- Dynamics, tempo ranges, FX zones

It updates automatically as you annotate.
