# opacity_toke

A score-driven audio composition tool in the tradition of musique concrète. Take a single source audio or video file, cut samples from it like tape, and compose them back on top of the original using a YAML score — with dynamics, tempo warping, effects, and probabilistic parameters.

The base track always plays in full. Composed samples are layered on top. Every render with probabilistic parameters produces a different result.

---

## Concept

The core metaphor is **tape cutting**. You work entirely from one source file:

1. You listen to the source and decide which moments to cut out — these become your **samples**.
2. You write a **score** that describes when to play each sample back, at what speed, with what effects, at what dynamic level.
3. You **render** — the original plays underneath, your score plays over it.

Because parameters can be probabilistic (a speed drawn from a Gaussian, a loop count drawn from a discrete set), each render is a unique performance of the same score.

---

## Documentation

| File | What it covers |
|------|----------------|
| [installation.md](installation.md) | Dependencies, setup, virtual environment |
| [editor.md](editor.md) | The visual score editor — tools, workflow, playback |
| [score_reference.md](score_reference.md) | Complete YAML score format reference |
| [cli.md](cli.md) | Command-line renderer |
| [pipeline.md](pipeline.md) | How the code works internally |
| [v2.md](v2.md) | V2 Expressive Interpretation Engine (beta) |

---

## V2 — Expressive Interpretation Engine (beta)

V2 adds musical expressiveness on top of V1. Instead of rendering the score as-written, V2 interprets the `dynamics:` markings through a higher-order Markov chain with Gaussian emissions — producing a different but musically coherent performance on every run.

Set `engine: v2` in `config.yaml` (or select **V2 β** in the editor) and add a `dynamics:` section to your score. See [v2.md](v2.md) for full documentation.

---

## Quick start

```bash
# Install dependencies
pip install -r beta_interpreter/requirements.txt
# SoX must also be installed system-wide (see installation.md)

# Launch the editor
cd beta_interpreter/editor
python server.py

# Open http://localhost:5000 in your browser
# Load a .wav or .mp4 file and start composing

# Or render directly from a score file
cd beta_interpreter
python main.py -i /path/to/audio.wav -s scores/my_score.yaml
```

---

## Project layout

```
opacity_toke/
├── docs/                        ← you are here
│
└── beta_interpreter/
    ├── main.py                  ← CLI renderer entry point
    ├── requirements.txt
    │
    ├── src/
    │   ├── parser.py            ← YAML score loader + validation
    │   ├── sample_engine.py     ← slices base audio into named clips
    │   ├── scheduler.py         ← orders events on the timeline
    │   ├── envelope.py          ← dynamics envelope builder
    │   ├── fx.py                ← reverb + delay via SoX subprocess
    │   ├── mixer.py             ← places clips on timeline, tempo warp, mix
    │   └── renderer.py          ← ties everything together, writes output
    │
    ├── editor/
    │   ├── server.py            ← Flask dev server
    │   └── static/
    │       └── index.html       ← the entire editor UI (single file)
    │
    ├── scores/                  ← saved YAML scores
    └── output/                  ← rendered files land here
```
