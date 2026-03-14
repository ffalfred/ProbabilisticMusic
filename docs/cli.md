# CLI Renderer

The command-line renderer takes a source file and a score file and produces a rendered output.

## Usage

```bash
cd beta_interpreter
python main.py -i <input_file> -s <score_file>
```

| Argument | Description |
|----------|-------------|
| `-i` / `--input` | Path to the base audio or video file (`.wav`, `.mp3`, `.flac`, `.mp4`) |
| `-s` / `--score` | Path to the YAML score file |

## Output

| Input type | Output |
|------------|--------|
| Audio file (`.wav`, etc.) | `output/output_<score>_<base>_001.wav` — numbered per run |
| Video file (`.mp4`) | `output/output_<score>_<base>_001.mp4` — original video with replaced audio track |

The output directory is created automatically. The run counter increments on each render — running the same command twice produces `_001` and `_002`. To reproduce a specific run, set `seed` in `config.yaml`.

---

## Engine mode and config.yaml

`beta_interpreter/config.yaml` controls which engine runs and how:

```yaml
engine: v1    # v1 (default) or v2
seed: null    # integer for reproducible runs, null for random
```

When `engine: v2`, V2's Expressive Interpretation Engine runs before V1. It reads the score's `dynamics:` markings and applies a Markov-sampled expressive offset to each event's gain, timing, reverb, attack, and brightness. See [v2.md](v2.md) for the full config reference.

When `engine: v1` or no `config.yaml` exists, behaviour is identical to previous versions.

After rendering, the terminal prints the output path and the total duration in seconds.

## Examples

```bash
# Render with a WAV source
python main.py -i /home/user/recordings/session.wav -s scores/score1.yaml

# Render with a video source (output will be .mp4 with new audio)
python main.py -i /home/user/videos/performance.mp4 -s scores/score_reverb.yaml
```

## Probabilistic scores

If the score contains probabilistic parameters (Gaussian speeds, discrete loop counts, Bernoulli reverses), they are resolved fresh on every run. Running the same command twice produces two different performances:

```bash
python main.py -i session.wav -s scores/stochastic_score.yaml
# → output/output.wav  (performance A)

python main.py -i session.wav -s scores/stochastic_score.yaml
# → output/output.wav  (performance B — different)
```

To keep multiple takes, rename or move `output/output.wav` between runs.

## What happens during a render

1. **Parse** — the score YAML is loaded and probabilistic parameters are resolved.
2. **Build bank** — the base track is read, and each `samples:` entry is sliced into a named numpy array.
3. **Schedule** — events are sorted by time.
4. **Mix** — for each event: the clip is varispeed-resampled, reversed (if set), looped, faded, gained, and FX-processed. Then placed on the mix timeline at its warped time position.
5. **Dynamics** — the dynamics envelope is built from point marks and crescendo/decrescendo ranges, and multiplied into the mix.
6. **Normalise** — the mix is normalised to 0.9 peak amplitude.
7. **Write** — for audio input: writes `output/output.wav`. For video input: muxes the rendered WAV back into the original video container using ffmpeg, keeping the original video stream untouched.
