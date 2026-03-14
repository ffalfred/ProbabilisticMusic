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

---

## Loading a file

At the top of the editor, there is a text bar. Type or paste the **full path** to your audio or video file and press **Load** (or Enter).

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

---

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [ full path to your file ]                      [ Load ]    │
├─────────────────────────────────┬───────────────────────────┤
│  waveform                       │  score panel              │
│  (draw samples, events here)    │  (live list of everything │
│                                 │   you've added)           │
│  video frame                    │                           │
│  (same tools work here too)     │                           │
├─────────────────────────────────┴───────────────────────────┤
│  [ Sample ] [ Event ] [ Dynamics ] [ Tempo ] [ FX ]         │
│                        [ ▶ Base ]  [ ▶ Mix ]  [ ← Undo ]    │
├─────────────────────────────────────────────────────────────┤
│  name: [untitled]  [Base FX]  Engine: [V1▾]  [Export YAML]  │
└─────────────────────────────────────────────────────────────┘
```

---

## Playing back

| Button | What it does |
|--------|-------------|
| **▶ Base** | Plays the original file unchanged |
| **Space** | Same as ▶ Base |
| **▶ Mix** | Renders your full composition and plays it. This takes a second or two. |

Click on the waveform or video frame to jump to that point in time. Drag to scrub through.

The current time is shown in the bottom-left corner of the video frame area.

Pressing **▶ Mix** again while audio is playing will pause it. Pressing it again re-renders and plays from the start.

---

## Tools

Click a tool button to select it. The selected tool determines what happens when you click or drag on the waveform or video frame.

### [ Sample ]

**Drag** across a region to define a sample — a named piece of the audio that you can reuse in your composition.

A popup will ask for:
- **name** — what to call this sample (e.g. `kick`, `texture_a`)
- **color** — just for visual identification in the editor

The sample is stored as a start and end time. The name is what you use when placing events.

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
| **fx** | Add an effect to this event (see Effects below). |

> **Editing an existing event:** Click on the event in the score panel on the right to reopen its popup and change any value.

### ~ Dynamics

Controls the overall loudness shape of the piece. Two gestures:

- **Click** → place a **dynamic mark** at that moment. Sets the volume level from that point forward.
  Available marks: `ppp` (very quiet) → `pp` → `p` → `mp` → `mf` → `f` → `ff` → `fff` (very loud)

- **Drag** → draw a **crescendo or decrescendo** (gradual volume change) across that time span.

Dynamic marks and ranges work together: marks define levels, ranges smoothly interpolate between surrounding levels.

### ⏱ Tempo

**Drag** to define a region where time is stretched or compressed.

- **accelerando** with factor > 1: events happen sooner (time compressed)
- **ritardando** with factor < 1: events happen later (time stretched)

This affects the *timing* of events, not the pitch or length of individual clips.

### ◆ FX

**Drag** to apply an effect to the **base track itself** across a time range. For example, add reverb to a 3-second section of the original recording. This plays *under* your events, not on top.

---

## Effects

Effects can be added per-event (in the Event popup) or to a region of the base track (using the FX tool). The same effect types are available in both places.

### reverb
Makes a sound feel like it's in a room.
```
reverberance: 0–100    (0 = completely dry, 100 = maximum reverb)
```

### delay
Repeating echoes.
```
delay_sec: 0.1–2.0    (time between echoes, in seconds)
feedback:  0.0–1.0    (how many echoes — 0 = one echo, 0.9 = many echoes that fade out slowly)
```

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

---

## Base FX

The **Base FX** button in the bottom bar opens a panel to apply effects to the **entire base track** — not just a region. This runs before everything else, so your events and FX zones sit on top of the processed base. Useful for a global room reverb or a slight compression on the source.

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

## Engine selector (V1 / V2 β)

The **Engine** dropdown in the bottom bar selects the rendering mode:

| Option | What it does |
|--------|-------------|
| **V1** | Standard render. Same score → same result (unless you use probabilistic parameters). |
| **V2 β** | Expressive Interpretation Engine. Reads the `dynamics:` marks and adds musical variation — different phrasing, timing, and loudness each run. |

When **V2 β** is selected, extra controls appear:
- **mode**: `joint` (the engine remembers its own previous choices — more organic) or `symbolic` (just reacts to the score marks — more neutral)
- **seed**: type a number to get the exact same render every time; leave blank for random
- **order**: how many past events to consider (default 2 — don't change this unless you know what you're doing)

V2 needs at least one `dynamics:` marking in your score, otherwise it uses a neutral default.

See [v2.md](v2.md) for the full V2 documentation.

---

## Right-click to delete

Right-click on any annotation on either canvas — a sample boundary, event marker, dynamic mark, tempo zone, or FX zone — to delete the nearest one.

---

## Undo

The **← Undo** button removes the last action. Undo history is lost when you refresh the page.

---

## Exporting the score

When you're happy with your composition:

1. Type a name in the **name:** field at the bottom (e.g. `my_composition`)
2. Click **Export YAML**

The score is saved as `scores/my_composition.yaml` inside the ProbabilisticMusic folder. The full path is shown in the status bar.

This file can then be used with the [command-line renderer](cli.md) to render without opening the editor.

---

## Score panel

The right-hand panel shows a live summary of everything in your score: samples, events, dynamics, tempo regions, and FX zones. Click on any event in the list to edit it.

It updates automatically as you draw.
