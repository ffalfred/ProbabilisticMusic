# The Visual Editor

The editor is a web page that runs locally on your computer. You open it in your browser and use it to visually build a score by drawing on a waveform — no text file editing required.

---

## Launching the editor

> Make sure you've completed [installation.md](installation.md) first.

**1. Open a terminal and go to the project folder:**

```bash
cd /path/to/ProbabilisticMusic
```

**2. Activate the virtual environment:**

```bash
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

**3. Go into the editor folder and start the server:**

```bash
cd editor
python server.py
```

You should see something like:
```
 * Running on http://127.0.0.1:5000
```

**4. Open your browser and go to:**

**http://localhost:5000**

> `localhost` means "this computer". Port `5000` is where the editor is listening. This is not a website — it only works on your machine while `server.py` is running.

Leave the terminal open while you use the editor. To stop the editor, press `Ctrl+C` in the terminal.

> The server only answers the editor page itself: other websites and other programs on your machine can't use it to read your files. Open the editor at `localhost` or `127.0.0.1`; other addresses are refused.
>
> Options: `OPUS_PORT=5001 python server.py` uses another port. `OPUS_DEBUG=1 python server.py` turns on Flask's debug mode. Only use that while developing, because its error pages include a Python console.

---

## Workspaces

The editor is divided into three workspaces, selectable from the tab bar at the very top:

| Workspace | Purpose |
|-----------|---------|
| **Composer** | Draw samples, events, dynamics, tempo, and effects on the waveform. Export clean score YAML. |
| **Interpreter** | Configure how the score is performed — Golems (piece characters), V2 Kalman parameters, seed. Preview and save interpretation configs separately from the score. |
| **Conductor** | Reserved for future features (batch rendering, multi-score sequencing). |

The Composer and Interpreter are separate by design: one score can be performed many different ways by loading different interpretation configs in the Interpreter — without changing the composition itself.

---

## Composer workspace

### Loading a file

At the top of the Composer, there is a text bar. Type or paste the **full path** to your audio or video file and press **Load** (or Enter).

Examples:
```
/home/yourname/recordings/session.wav
/Users/yourname/Desktop/performance.mp4
```

> **How to find the full path:** On macOS, right-click the file in Finder → Get Info → the path is shown under "Where". On Linux, drag the file into the terminal window and it will paste the path.

Supported formats: `.wav`, `.mp3`, `.flac`, `.mp4`

After loading:
- **Audio files**: the waveform appears as a scrollable graph of the sound.
- **Video files**: the waveform appears, and the first frame of the video is shown below it.

### Layout

```
┌───────────────────────────────────────────────────────────────────────┐
│  [ Composer ]  [ Interpreter ]  [ Conductor ]                          │  ← workspace tabs
├──────────────────────────────────────────────────────────────────────┤
│  [ full path to your file ]                              [ Load ]      │  ← header bar
├──────────────┬───────────────────────────────┬───────────────────────┤
│ tools        │  waveform                      │  score panel          │
│              │  (draw samples, events, etc.)  │  (live summary)       │
│ [ Sample ]   │                                │                       │
│ [▶ Event ]   │  ─ Tracks panel (collapsible)─ │                       │
│ [~ Dynamics] │  stem 1 ░░░░░░░░░░░            │                       │
│ [⏱ Tempo ]   │  stem 2 ░░░░░░░░░░░            │                       │
│ [◆ FX    ]   │                                │                       │
│              │  video frame / image           │                       │
│ [⚙ Stemize]  │  (score overlay, metadata img) │                       │
├──────────────┴───────────────────────────────┴───────────────────────┤
│  view:  ⊕ Zoom  ↑ Pointer  |  ⌟ Quantize  |  ← Undo  → Redo         │  ← controls bar
├──────────────────────────────────────────────────────────────────────┤
│  name: [untitled]  [Base FX]  |  [↓ Export YAML]  [↓ Export audio]  │
│        [path/to/score.yaml]  [↑ Import YAML]  |                      │  ← export bar
│        [▶ Source]  [▶ Mix]   speed: [1.0]                            │
└──────────────────────────────────────────────────────────────────────┘
```

### Playing back

| Button | What it does |
|--------|-------------|
| **▶ Source** | Plays the original file. If you have loaded stems (see [Stemize](#stemize--audio-source-separation)), plays the mix of all unmuted stems instead. |
| **Space** | Same as ▶ Source |
| **▶ Mix** | Renders your full composition using the score you've drawn, and plays it. Takes a second or two. Always uses V1 engine — expressive interpretation is done in the Interpreter workspace. |

Click on the waveform or video frame to jump to that point in time.

The current time is shown in the overlay at the bottom of the video/image area.

Pressing **▶ Mix** again while audio is playing will pause it. Pressing it again re-renders and plays from the start.

### Loudness and the safety brake

Renders keep the level the performance produced. Nothing turns a render up or down automatically, so a quiet interpretation sounds quiet and a loud one sounds loud, and you can compare takes directly.

The **brake** switch next to the workspace tabs is the safety brake, a limiter that pulls down only the moments that would go above −1 dB so loud passages don't distort. Everything else is untouched. It is on by default and applies to everything you play in the editor. After a render, the number next to it shows how much it reduced the loudest moment (for example `−2.1 dB`). With the brake off, the indicator turns red (`clips +1.5 dB`) when a render goes over the maximum and will distort.

Exports have their own **Loudness** setting:

| Choice | What it does |
|--------|--------------|
| **Leave it** | The level as performed (default). |
| **Match source** | As loud overall as the loaded audio. |
| **Target loudness** | −14 LUFS (streaming), −16 (Apple Music, podcasts), −23 (broadcast), or a custom value. |

An adjustment is one volume change for the whole piece. It is measured on the whole render, so exporting a time range gives that range the same level it has in the full piece. The export's **Safety brake** checkbox is ticked by default. The status line shows the result: the loudness, the adjustment, and how much the brake worked. If the brake had to work hard at a target, the target is too loud for this piece.

> **About ▶ Source with stems:** When you use Stemize to split the audio into separate tracks, ▶ Source plays through the **Web Audio mixer** and plays all unmuted stems together. Muting/unmuting a stem takes effect immediately — you don't need to press play again.

---

## Tools

Click a tool button to select it. The selected tool determines what happens when you click or drag on the waveform or video frame.

### [ Sample ]

**Drag** across a region to define a sample — a named piece of the audio that you can reuse in your composition.

A popup will ask for:
- **name** — what to call this sample (e.g. `kick`, `texture_a`)
- **track** — which track to cut it from (when there are several)
- **fade in / fade out** — as a percentage of the sample's length
- **carry from track** — which of the track's processing the sample keeps: its **FX chain** (ticked by default), **FX regions**, **automation** and **gain**. Tick all four to get exactly what you hear on the track there; untick all for the file as it is. A track's mute is never carried, so you can keep a track muted and still sample from it.

The sample is stored as a start and end time on the timeline (so on a track that starts later, it is cut from the right place in that track). The name is what you use when placing events.

### ▶ Event

**Click** anywhere on the timeline to place a trigger — a moment where a sample will play.

A popup opens with these options:

| Option | What it does |
|--------|-------------|
| **sample** | Which sample to play (choose from a dropdown of samples you've defined) |
| **time (s)** | Exact start time in seconds — you can type a precise value here |
| **speed** | Playback speed. `1.0` = normal. `0.5` = half speed (lower pitch, slower). `2.0` = double speed (higher pitch, faster). This is varispeed — pitch and duration change together, like tape. |
| **speeds** | Play multiple speeds at once (type space-separated values, e.g. `0.5 1.0 2.0`). Good for chords and clusters. |
| **gain_db** | Volume. `0` = full volume. `-6` = half amplitude (quieter). `-20` = very quiet. |
| **loop** | How many extra times to repeat. `0` = play once. `3` = play 4 times total. |
| **reverse** | Play the sample backwards. |
| **fx** | Add an effect to this event (see [Effects](#effects)). |

> **Editing an existing event:** Click on the event in the score panel on the right to reopen its popup and change any value.

### ~ Dynamics

Controls the overall loudness shape of the piece. Two gestures:

- **Click** → place a **dynamic mark** at that moment. Sets the volume level from that point forward.
  Available marks: `ppp` (very quiet) → `pp` → `p` → `mp` → `mf` → `f` → `ff` → `fff` (very loud)

- **Drag** → draw a **crescendo or decrescendo** (gradual volume change) across that time span.

Dynamic marks and ranges work together: marks define levels, ranges smoothly interpolate between surrounding levels.

> Dynamics marks are also read by the V2 Kalman engine in the Interpreter workspace to derive expressive variation — the more markings you add, the richer the interpretation.

### ⏱ Tempo

**Drag** to define a region where time is stretched or compressed.

- **accelerando** with factor > 1: events happen sooner (time compressed)
- **ritardando** with factor < 1: events happen later (time stretched)

This affects the *timing* of events, not the pitch or length of individual clips.

### ◆ FX

**Drag** to apply an effect to the **base track itself** across a time range. For example, add reverb to a 3-second section of the original recording.

### Note relationship tools

These are applied after placing events, to shape how consecutive notes relate:

| Button | What it does |
|--------|-------------|
| **⌒ Slur** | Connects two notes in a legato phrase — smooth, joined playback |
| **∼ Glissando** | Continuous pitch slide between two notes |
| **∿ Arpeggio** | Plays chord notes as a rapid sequence rather than simultaneously |

### Articulation tools

| Button | What it does |
|--------|-------------|
| **• Staccato** | Cut short: only the first `keep` seconds play |
| **⌒ Legato** | Connected: the sound rings on into what comes next |
| **𝄐 Fermata** | Held: the sound sustains for `hold` seconds |
| **> Accent** | Emphasised: the attack is louder |

Each mark's popup has a **target**:
- **event** (default) — the mark shapes the event(s) it covers: a click covers the event starting nearest to it (within 0.5 s), a drag covers every event starting inside the range. The source audio is untouched.
- **whole mix** — the mark shapes everything sounding then. Over a range it acts at the attacks detected in the sound, or every `every` seconds if you fill that in. A whole-mix fermata makes the whole piece wait: the sound is held, then everything resumes (the piece gets longer, and the cursor stops during the hold).

Whole-mix marks are labelled "(mix)" on the score. Full details: [score_reference.md](score_reference.md#articulations).

---

## View controls (controls bar)

These buttons change how you navigate the canvas, not what you draw:

| Button | What it does |
|--------|-------------|
| **⊕ Zoom** | Click to zoom in, right-click to zoom out. Or scroll with the mouse wheel. |
| **↑ Pointer** | Click to seek to that time. Drag to pan the score image left/right. |
| **⌟ Quantize** | Snap all event times to the nearest beat grid. A popup lets you choose the grid size. |
| **← Undo** | Removes the last action |
| **→ Redo** | Re-applies an undone action |

> Undo and redo history is lost when you refresh the page or load a new file.

---

## ⚙ Stemize — audio source separation

**Stemize** splits your audio file into separate layers (called "stems") that you can listen to and mute independently. This is useful when working with a complex recording — for example, separating a drum track from a melodic layer, or isolating a repeated texture.

### How to use Stemize

1. Load an audio file using the path bar at the top.
2. Click **⚙ Stemize** at the right end of the tools row.
3. A popup appears with these options:

| Option | What it does |
|--------|-------------|
| **Method** | How to split the audio. `hpss` separates harmonic (tonal) from percussive (rhythmic) content. `nmf` finds N abstract components. `both` runs both. |
| **NMF components** | Only used when method is `nmf` or `both`. How many layers to split into (default 3). More components = finer separation, but slower. |
| **NMF reconstruction** | `softmask` (recommended): each component keeps only the energy it "owns" from the original signal. `naive`: uses the component magnitudes directly with the original phase — may be louder but less clean. |

4. Click **OK**. The server analyses the file — this can take several seconds for long audio.
5. When done, a **Tracks panel** appears below the waveform, showing one row per stem.

### The Tracks panel

Each row in the Tracks panel shows:
- A **mini waveform** of that stem with a moving playback cursor
- A **mute checkbox** — uncheck to silence that stem
- A **gain slider** — adjust the relative level of each stem in dB
- The **stem name** (e.g. `harmonic`, `percussive`, `nmf_1`)

The panel can be **collapsed or expanded** by clicking its header bar ("Tracks ▼").

### Playback with stems

Once stems are loaded:
- **▶ Source** plays the **mix of all unmuted stems** through the Web Audio mixer in your browser.
- Muting or unmuting a stem takes effect immediately while audio is playing — no need to stop and restart.
- The **▶ Mix** button still plays the rendered composition (which uses the original file as its base track, not the stems).
- If you load a new file, stems are cleared automatically.

> **Note:** Stem separation is approximate — some bleed between stems is normal. HPSS is fast and good for drum/melody separation. NMF finds more abstract patterns and works well on textural material. Try both to see what works for your source.

---

## Effects

Effects can be added per-event (in the Event popup) or to a region of the base track (using the FX tool). The same effect types are available in both places.

The FX dropdown is divided into two groups:
- **Standard effects** — classic audio processing (reverb, delay, pitch, EQ, etc.)
- **Morphogenics** — 20 advanced spectral and compositional processors inspired by Xenakis, Penderecki, Saariaho, Wagner, Messiaen, Desyatnikov, and Nørgaard

Selecting a Morphogenics effect generates its parameter widgets automatically below the dropdown. See [morphogenics.md](morphogenics.md) for a full description of every plugin.

---

### Standard effects

### reverb
Makes a sound feel like it's in a room. The reverb is added on top of the sound and rings on after it ends.
```
reverberance: 0–100   (how long it rings: 20 ≈ 0.3 s, 50 ≈ 2 s, 100 ≈ 11 s; default 50)
dry:          0–1     (level of the original — 1 = full, 0 = reverb only)
wet:          0–1     (level of the reverb — 1 = as loud as the original)
```

### delay
Repeating echoes after the sound.
```
delay_sec: 0.1–2.0    (time between echoes, in seconds)
dry:       0–1        (level of the original — 1 = full, 0 = echoes only)
wet:       0–1        (level of the first echo)
feedback:  0.0–0.95   (each echo is this much of the previous one — 0 = a single echo)
```
For example dry 1, wet 0.5, feedback 0.6: the sound at full level, then echoes at 0.5, 0.3, 0.18, …

### overdrive
Adds distortion and warmth, like turning an amp up too loud.
```
gain:   0–100    (how much drive — higher = more distortion)
colour: 0–100    (0 = harsh and hard, 100 = warm and soft)
```

### flanger
A sweeping, whooshing comb-filter effect.
```
delay_ms: 0–30     (base delay in milliseconds)
depth_ms: 0–10     (how wide the sweep is)
speed_hz: 0.1–10   (how fast the sweep moves, in cycles per second)
```

### pitch
Shifts pitch without changing duration.
```
cents: any integer    (100 = +1 semitone up, 1200 = +1 octave up, -100 = 1 semitone down)
```

### compress
Reduces the difference between loud and quiet parts. Makes the sound more consistent.
```
threshold_db: where compression starts, in dB (e.g. -20)
ratio:        how much to compress (4 means 4:1 — for every 4dB above threshold, output rises 1dB)
attack:       how quickly compression kicks in, in seconds (default 0.01)
release:      how quickly it releases, in seconds (default 0.3)
makeup_db:    add gain after compressing to bring the level back up (default 0)
```

### eq
Boosts or cuts a specific frequency range.
```
freq_hz: which frequency to target, in Hz (e.g. 200 for bass, 5000 for brightness, 10000 for air)
gain_db: how much to boost (positive) or cut (negative), in dB
q:       how narrow the band is — higher = more focused, lower = wider
```

You can add multiple EQ entries to the same event to build a multi-band shape.

### spectral_inversion

Inverts the spectral phase of the audio, creating hollow and flanged timbres.
No additional parameters.

### overtones

Adds synthetic overtones above the fundamental — harmonics at +12, +19, +24 semitones.
```
n_harmonics: 1–8    (how many overtone layers)
gain_db:     dB     (level of first overtone; subsequent ones are proportionally quieter)
```

---

### Morphogenics effects

All 20 Morphogenics plugins are available in the same FX dropdown under the **Morphogenics** group.
Parameters are generated automatically when you select a plugin.

See [morphogenics.md](morphogenics.md) for the full reference — every plugin, parameter, and usage note.

Quick reference: the available plugins are:
- **Nørgaard: Undertones** — synthetic harmonic undertones below the fundamental
- **Messiaen: Modes** — pitch quantization to Messiaen's 7 modes of limited transposition
- **Penderecki: Cluster** — a band of every semitone or quarter tone, voices drifting, optional staggered entries
- **Penderecki: Aleatoric** — random per-segment pitch displacement
- **Penderecki: Textural** — a restless cluster: every voice jumps, swells and is scattered in stereo
- **Penderecki: Glissando** — continuous pitch sweep through each segment
- **Xenakis: Grain Scatter** — stochastic granular resynthesis (shuffled, re-pitched grains)
- **Xenakis: Stochastic Cloud** — dense probabilistic sine-burst layers
- **Xenakis: GENDY** — Xenakis's dynamic stochastic synthesis: on the input, as a synth layer, or as a random envelope
- **Saariaho: Spectral Freeze** — holds each attack's sound (or a slowly following one) as a sustained chord
- **Saariaho: Microtonal** — brightness-driven microtonal detuning
- **Desyatnikov: Minimalism** — polystylistic quote displacement at every Nth onset
- **Desyatnikov: Lyricism** — two parallel non-functional intervals (default maj 7th + perfect 11th above)
- **Desyatnikov: Glissandi** — portamento slides into random onset boundaries
- **Spectral: Harmonic Stretch** — stretches or squeezes the spacing of the partials (bell-like)
- **Spectral: Inharmonic** — frequency shifter: every partial moves by the same Hz (metallic)
- **Spectral: Smooth** — frequency-axis spectral envelope smoothing
- **Wagner: Leitmotif** — onset-segmented motif transformation with transposition
- **Wagner: Tristan** — Tristan chord (F–B–D♯–G♯ voicing) overlay on onset segments
- **Wagner: Endless Melody** — legato bridges (the previous note rings on) + passing tones at note boundaries

---

## Base FX

The **Base FX** buttons in the toolbar apply effects to the **entire base track** — not just a region. This runs before everything else, so your events and FX zones sit on top of the processed base. Useful for a global room reverb or a slight compression on the source.

## Automation: effect settings that change over time

In any effect chain (an event's FX, an FX zone, Base FX, Output FX, a track's FX), the **~** button next to a numeric setting switches it to a **curve**: type points as `seconds: value`, separated by commas — e.g. `0s: 200, 2s: 3000, 5s: 400` for a filter cutoff that opens and closes. Straight lines join the points; the value holds before the first and after the last. Times count from the start of what the effect processes (the event, the zone, the track, or the whole piece). Click **~** again to go back to a single value (the curve's first).

Dry/wet levels, filter cutoff/resonance, tremolo rate/depth and pitch move exactly; other settings are approximated by blending renders taken along the curve (see [score_reference.md](score_reference.md#automation--effect-settings-that-change-over-time)).

## Fade shapes

Sample, event, slur and FX-zone popups have a **fade shape**: *smooth* (equal-power, the default), *linear*, *exponential* or *S-curve*. An event's shape defaults to its sample's.

## Output FX, and FX zones on the whole output

Base FX and FX zones work on the **source** only: events play on top, unaffected. To process **everything** — source and events together, after tempo changes — use:

- **Output FX** (toolbar, next to Base FX): an effect chain on the whole output, start to end — a master chain (`fx_global`).
- **FX zone → Applies to: the whole output**: in any FX zone's popup, switch *Applies to* from *the source* to *the whole output* (`fx_sections`). Output zones are drawn in orange and labelled `out:`; source zones stay purple.

| | Source only | Whole output |
|---|---|---|
| Whole piece | Base FX | Output FX |
| A time range | FX zone (applies to: the source) | FX zone (applies to: the whole output) |

## Lead-in and tail

**⏱ Lead / tail** in the toolbar sets:
- **lead-in** — events start this many seconds later, while the source plays from 0 (`silence_start`);
- **tail** — seconds of silence added after the piece (`silence_end`).

The button shows the current values when either is set.

---

## Probabilistic parameters

Any number field in the event popup can be switched from a fixed value to a range or a distribution. Click the small dropdown next to any field to change the mode:

| Mode | What it does |
|------|-------------|
| **fixed** | Always uses exactly this value — same every render |
| **range** | Picks a random value between min and max each time you render |
| **gaussian** | Picks a value near the mean, with random variation controlled by std |

This means the same score can sound different every time you press **▶ Mix**. See [score_reference.md](score_reference.md) for how to write these in YAML.

---

## Right-click to delete

Right-click on any annotation on either canvas — a sample boundary, event marker, dynamic mark, tempo zone, or FX zone — to delete the nearest one.

---

## Undo / Redo

| Button | Keyboard shortcut | What it does |
|--------|------------------|-------------|
| **← Undo** | — | Removes the last action |
| **→ Redo** | — | Re-applies the last undone action |

Undo/redo history is stored in memory and lost when you refresh the page or load a new file. Note: Golem edits in the Interpreter workspace do not participate in undo/redo — delete and re-add as needed.

---

## Exporting the score

When you're happy with your composition:

1. Type a name in the **name:** field at the bottom (e.g. `my_composition`)
2. Click **↓ Export YAML**

The score is saved as `scores/my_composition.yaml` inside the ProbabilisticMusic folder. The full path is shown in the status bar.

The exported score is a **clean composition file** — it does not include engine config or Golems. Those live in the Interpreter workspace. This keeps scores reusable with any interpretation.

This file can then be used with the [command-line renderer](cli.md) to render without opening the editor.

### Exporting audio

Click the **save audio…** field or the **↓** next to it. A popup asks:

- **What to export** — *the mix* (source + events: exactly what **▶ Mix** plays, including tempo changes, fermatas and the tail silence), *events only* (no source), or *the source only*.
- **Save to** — type a path or **Browse**; left empty, the file goes to `output/composer_<audio>_<date-time>.wav`.
- **Time range** — the whole piece by default, or a part of it. A part keeps the level it has in the whole piece.
- **Loudness** — leave as performed, match the source, or reach a target (−14 / −16 / −23 LUFS or custom), plus the safety brake (see [Loudness and the safety brake](#loudness-and-the-safety-brake)).
- **Audio quality** — 24-bit WAV (default), 32-bit float WAV, FLAC or 16-bit WAV.

The status line shows where the file went and its loudness. The Interpreter has the same export (**↓ WAV**) for its performances.

### Score videos

Score videos (the score image scrolling with the music, with the rendered sound) are made with **Concerto → Download**, from the Composer or the Interpreter. (The Composer's old ⇓ MP4 button was removed: its video carried the raw source recording, not the composition.)

### Importing a previously exported score

If you have a `.yaml` score file from a previous session:

1. Paste the full path to the file into the **import path** field
2. Click **↑ Import YAML**

All samples, events, dynamics, tempo, and FX zones will be restored in the editor. If the YAML contains a `golems:` key (from an older export), those Golems are automatically loaded into the Interpreter workspace.

---

## Score panel

The right-hand panel shows a live summary of everything in your score: samples, events, dynamics, tempo regions, and FX zones. Click on any event in the list to edit it.

The panel is divided into **collapsible sections** — click any section heading to collapse or expand it. This helps keep the panel tidy when working with large scores.

It updates automatically as you draw.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| **Space** | Play / pause source audio (same as ▶ Source) |
| Click on waveform | Seek to that time |
| Drag on waveform (Pointer tool) | Pan the waveform view |
| Scroll wheel | Zoom in/out on the waveform |

---

## Interpreter workspace

The Interpreter is where you configure **how** the score is performed. It is separate from the Composer so that the same composition can be performed with different expressive characters without changing a note.

### Layout

```
┌────────────────────────┬──────────────────────────────────────────────┐
│  score                 │                                              │
│  [path/to/score.yaml]  │  golem timeline canvas                       │
│  [ Load ]              │  ┌──────────────────────────────────────────┐│
│  status: loaded        │  │ ████ lyrical ████  ████ dramatic ████    ││
├────────────────────────┤  └──────────────────────────────────────────┘│
│  v2 parameters         │                                              │
│  engine: [V2 Golems▾]  │  Golem list                                  │
│  λ:  [0.7]             │  0.0s – 30.0s  [lyrical  ▾]  [✕]           │
│  seed: [rand]          │  30.0s – 60.0s [dramatic ▾]  [✕]           │
│  ▶ advanced            │  from:[   ] – to:[   ] [lyrical▾]  [+ Add]  │
├────────────────────────┤  dramatic (volatile) · lyrical (smooth) …   │
│  save / load           ├──────────────────────────────────────────────┤
│  name: [untitled_interp│  audio: [path/to/audio.wav]                  │
│  [↓ Save] [↑ Load]     │  [▶ Preview] [▶ Source]                     │
│  [path/to/interp.yaml] │                                              │
└────────────────────────┴──────────────────────────────────────────────┘
```

### Typical workflow

1. In the Composer, draw your score and click **↓ Export YAML**
2. Switch to the **Interpreter** tab
3. Enter the path to your exported `.yaml` score in the **score** field and click **Load**
4. Set the **audio** path to your source audio file
5. Add Golem ranges on the **canvas timeline** (drag to create) or using the add row below it
6. Adjust **V2 parameters** in the sidebar as needed
7. Click **▶ Preview** to hear the interpretation
8. Click **↓ Save** to save the interpretation as `interpretations/{name}.yaml`

You can save multiple named interpretations of the same score and load them back at any time.

### Golems — piece characters

A **Golem** assigns a musical personality to a time range of the piece. Each Golem has:
- **from / to** — start and end time in seconds (matching the score's timeline)
- **character** — one of four built-in personalities:

| Character | Behaviour |
|-----------|-----------|
| **dramatic** | Volatile — high contrast, sharp dynamics, wide expression |
| **lyrical** | Smooth — gradual changes, flowing phrasing |
| **sparse** | Literal — stays close to the written score, minimal added expression |
| **turbulent** | Unpredictable — irregular phrasing, sudden shifts |

**Adding Golems:**
- **Drag** on the timeline canvas to create a new Golem range, then set its character from the dropdown
- Or use the add row below the list: enter from/to times, choose a character, click **+ Add**

**Editing Golems:**
- Change the from/to values or character directly in the list rows — updates the canvas immediately
- Click **✕** to delete a Golem

Overlapping Golems blend linearly by time weight — the canvas shows them as coloured blocks.

### V2 parameters

| Parameter | What it does |
|-----------|-------------|
| **engine** | `V2 Golems` uses the Kalman expressive engine. `V1` renders without interpretation (same as Composer ▶ Mix). |
| **λ (lambda)** | How well the performer "knows" the piece. `0.9` = knows it well (smooth, confident). `0.3` = sight-reading (more variable, reactive). Default: `0.7`. |
| **seed** | Integer seed for reproducible renders. Leave blank for a different result each time. |

**Advanced parameters** (click "▶ advanced" to expand):

| Parameter | What it does |
|-----------|-------------|
| **A1, A2** | AR(2) momentum coefficients — how strongly the previous two states influence the current one. `A1 + A2` must be < 1 for stability. |
| **η (eta)** | Volatility mixing weight — how much dramatic events amplify process noise. |
| **ξ (xi)** | Future pull scaling — how much upcoming dynamic marks shape current expression. |
| **window** | How many past dynamic marks the engine considers when updating its state. |

### Save / Load interpretation

An interpretation file stores the Golem ranges, V2 parameters, and the associated score path together. It is saved separately from the score YAML, in `interpretations/`.

- Click **↓ Save** to write `interpretations/{name}.yaml`
- Enter a path in the load field and click **↑ Load** to restore a saved interpretation

This means one score can have many named interpretations: `lyrical_interp.yaml`, `dramatic_interp.yaml`, etc.

### Backward compatibility

Scores exported by older versions of the editor may contain a `golems:` key inside the YAML. When you **Import YAML** in the Composer workspace, any embedded Golems are automatically transferred to the Interpreter — the Composer itself no longer owns them.

See [v2.md](v2.md) for the full V2 Kalman engine documentation.

---

## Conductor workspace

The Conductor workspace is currently a placeholder. Future features planned:
- Batch rendering across seed sweeps
- Multi-score sequencing and splicing
- Automated A/B interpretation comparison
- Export report: per-seed expressive parameter trajectories
