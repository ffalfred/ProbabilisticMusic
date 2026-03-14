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
| Audio file (`.wav`, etc.) | `output/output.wav` — the rendered mix |
| Video file (`.mp4`) | `output/output.mp4` — original video with replaced audio track |

The output directory is created automatically if it does not exist.

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
