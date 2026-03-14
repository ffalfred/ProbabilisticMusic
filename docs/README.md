# ProbabilisticMusic

A tool for composing music from a single audio or video file. You cut pieces of it like tape, arrange them back on top of the original, and add effects and dynamics — all described in a simple text file called a **score**.

Every time you render, you can get a slightly different result. The same score can be performed hundreds of different ways.

---

## What it does

You start with one source file — a recording, a field recording, a video. The tool lets you:

1. **Mark sections** of that file as named samples ("stab at 2 seconds", "texture at 5 seconds")
2. **Write a score** describing when to play each sample back, at what speed, with what effects
3. **Render** — the original plays underneath, your score plays on top of it

You can do this through a **visual editor** in your browser (easiest), or by writing the score by hand and running it from the terminal.

---

## Documentation

| File | What it covers |
|------|----------------|
| [installation.md](installation.md) | How to install everything — start here |
| [editor.md](editor.md) | The visual editor — the easiest way to compose |
| [score_reference.md](score_reference.md) | Full reference for the score YAML format |
| [cli.md](cli.md) | Running renders from the terminal |
| [pipeline.md](pipeline.md) | How the code works internally |
| [v2.md](v2.md) | V2 Expressive Engine — musical variation between runs (beta) |

---

## Quick start

> If you haven't installed the dependencies yet, read [installation.md](installation.md) first.

**Step 1 — Open a terminal and go to the project folder.**

The terminal is the black window where you type commands. On macOS it's called Terminal, on Linux it's usually Terminal or Konsole.

Once it's open, type this (replace the path with wherever you downloaded ProbabilisticMusic):

```bash
cd /path/to/ProbabilisticMusic
```

`cd` means "change directory" — it moves you into that folder.

**Step 2 — Activate the virtual environment.**

```bash
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

You'll see `(venv)` appear at the start of your prompt. This means Python is ready.

**Step 3 — Launch the editor.**

```bash
cd editor
python server.py
```

**Step 4 — Open your browser.**

Go to: **http://localhost:5000**

The editor will open. Type the full path to a `.wav`, `.mp3`, or `.mp4` file into the bar at the top and press **Load**.

---

## Project layout

```
ProbabilisticMusic/
├── main.py              ← renders a score from the terminal
├── requirements.txt     ← Python packages list
├── config.yaml          ← engine settings (V1 vs V2)
│
├── src/                 ← the audio engine (you don't need to touch this)
│
├── editor/
│   ├── server.py        ← the web editor server
│   └── static/
│       └── index.html   ← the editor interface
│
├── v2/                  ← V2 expressive interpretation engine (beta)
│
├── scores/              ← your saved scores go here
├── output/              ← rendered audio/video files land here
└── docs/                ← you are here
```
