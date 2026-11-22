# Rendering from the terminal

You can render a score without opening the editor by running `main.py` directly from a terminal. This is useful for batch rendering, scripting, or working on a machine without a browser.

---

## Before you start

Make sure you have:
- Completed [installation.md](installation.md)
- A score file (`.yaml`) in the `scores/` folder, or anywhere on your computer
- A source audio or video file

---

## How to run a render

**1. Open a terminal and go to the project folder:**

```bash
cd /path/to/ProbabilisticMusic
```

**2. Activate the virtual environment:**

```bash
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

You should see `(venv)` at the start of the prompt.

**3. Run the renderer:**

```bash
python main.py -i /path/to/your/audio.wav -s scores/your_score.yaml
```

| Argument | What it does |
|----------|-------------|
| `-i` / `--input` | Path to the source audio or video file (`.wav`, `.mp3`, `.flac`, `.mp4`) |
| `-s` / `--score` | Path to the YAML score file |

---

## Output files

Rendered files are saved in the `output/` folder inside ProbabilisticMusic. The filename is built automatically:

```
output/output_<score_name>_<source_name>_001.wav
```

For example, if your score is `scores/piano.yaml` and your source is `recordings/session.wav`, the output will be:

```
output/output_piano_session_001.wav
```

Each time you render, the number increments:
```
output/output_piano_session_001.wav   ← first render
output/output_piano_session_002.wav   ← second render
output/output_piano_session_003.wav   ← third render
```

This way you never overwrite a previous take.

For video input (`.mp4`), the output is a `.mp4` file with the original video and your rendered audio replacing the original audio track.

---

## Examples

```bash
# Render an audio file
python main.py -i /home/user/recordings/session.wav -s scores/score1.yaml

# Render with a video file (output will be a .mp4)
python main.py -i /home/user/videos/performance.mp4 -s scores/score_reverb.yaml
```

After rendering, the terminal prints the output path and total duration:
```
rendered → output/output_score1_session_001.wav  (14.3s)
```

---

## Engine mode (V1 vs V2)

The file `config.yaml` (in the ProbabilisticMusic root folder) controls which engine runs:

```yaml
engine: v1    # use v1 for standard rendering
engine: v2    # use v2 for expressive interpretation
```

Open `config.yaml` with any text editor (TextEdit on Mac, gedit on Linux, Notepad on Windows) and change the `engine:` line.

When `engine: v2`, the renderer reads the `dynamics:` section of your score and adds musical variation — different loudness, timing, and effects on each render. See [v2.md](v2.md) for how to use this.

---

## Reproducible renders with a seed

By default, renders with probabilistic parameters or V2 are different every time. To get the same result every time, set a seed in `config.yaml`:

```yaml
seed: 42       # any integer — always produces the same result
seed: null     # null means random — different every time
```

---

## What happens during a render

For reference, here is what the program does when you run it:

1. **Parse** — reads the score YAML file and resolves any probabilistic parameters (ranges, gaussians, etc.)
2. **Build bank** — reads the source audio and cuts out each named sample
3. **Schedule** — sorts events by time
4. **V2** (if enabled) — interprets dynamics markings and adds expressive offsets to each event
5. **Mix** — places each event on the timeline: resamples for speed, reverses if set, loops, applies fade, applies gain and effects
6. **Dynamics** — builds the amplitude envelope from dynamic marks and crescendo/decrescendo ranges, and multiplies it into the mix
7. **Loudness** — the level stays as the performance made it. The safety brake pulls down any moment that would go above −1 dB, and an optional adjustment sets the loudness of the whole file (see below)
8. **Write** — saves the output file

---

## Output loudness

The render keeps the level the performance produced: a quiet interpretation comes out quiet and a loud one loud, so renders can be compared directly. Two settings in the `output:` block of `config.yaml` finish the file:

```yaml
output:
  brake: true         # safety brake (recommended)
  adjust: none        # none | source | target
  target_lufs: -14    # used when adjust: target
```

- **brake** — a limiter that pulls down only the moments that would go above −1 dB, so loud passages don't distort. Everything else is left exactly as it is. With `false`, anything over the maximum clips.
- **adjust** — one volume change for the whole file. Levels inside the piece are kept.
  - `none` — keep the level as performed.
  - `source` — make the render as loud overall as the input recording.
  - `target` — reach `target_lufs`: −14 for streaming (Spotify, YouTube), −16 for Apple Music and podcasts, −23 for broadcast. Loudness is measured in LUFS (ITU-R BS.1770), which follows how loud music sounds, not its single loudest instant.

After each render the program prints the loudness, any adjustment, and how much the brake had to work. If the brake reduces peaks by several dB at a target, that target is louder than this piece comfortably allows.

