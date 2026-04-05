# Installation

Follow these steps in order. Do not skip any of them.

---

## Step 1 — Install system tools

Two programs need to be installed on your computer before anything else. These are not Python packages — they are separate programs.

### ffmpeg

ffmpeg handles video files: it pulls the audio out of a video, and puts your rendered audio back into the video at the end.

**macOS** (using Homebrew — if you don't have Homebrew, get it from https://brew.sh):
```bash
brew install ffmpeg
```

**Ubuntu / Debian Linux:**
```bash
sudo apt install ffmpeg
```

**Arch Linux:**
```bash
sudo pacman -S ffmpeg
```

### SoX (Sound eXchange)

SoX applies audio effects — reverb, delay, EQ, compression, and more.

**macOS:**
```bash
brew install sox
```

**Ubuntu / Debian Linux:**
```bash
sudo apt install sox
```

**Arch Linux:**
```bash
sudo pacman -S sox
```

---

## Step 2 — Check your Python version

This project requires Python 3.10 or newer. To check what version you have, open a terminal and type:

```bash
python --version
```

or:

```bash
python3 --version
```

You should see something like `Python 3.11.2`. If the number is 3.10 or higher, you're fine.

If you don't have Python, download it from https://www.python.org/downloads/.

---

## Step 3 — Go to the project folder

Open a terminal. Type `cd` followed by the path to the ProbabilisticMusic folder on your computer. For example:

```bash
cd /home/yourname/ProbabilisticMusic
```

> **What is `cd`?** It stands for "change directory". It moves you into a folder, the same way double-clicking a folder in a file browser does.

If you're not sure where the folder is, you can drag it from your file browser into the terminal window — it will paste the path automatically.

---

## Step 4 — Create a virtual environment

A virtual environment is an isolated box where Python packages are installed. It keeps this project's packages separate from everything else on your computer.

Run this once:

```bash
python -m venv venv
```

This creates a folder called `venv` inside the project. You only need to do this once.

---

## Step 5 — Activate the virtual environment

Every time you open a new terminal to use this project, you need to activate the environment:

```bash
source venv/bin/activate       # macOS / Linux
```

```
venv\Scripts\activate          # Windows
```

After running this, you'll see `(venv)` at the start of your terminal prompt:

```
(venv) yourname@computer:~/ProbabilisticMusic$
```

That `(venv)` tells you the environment is active. If you don't see it, run the activate command again.

---

## Step 6 — Install Python packages

With the environment active, install all required packages in one command:

```bash
pip install -r requirements.txt
```

> **What is pip?** It's Python's package installer. `requirements.txt` is a file that lists all the packages this project needs. This command downloads and installs all of them.

This will take a minute. You'll see a lot of text scroll by — that's normal.

| Package | What it does |
|---------|-------------|
| `numpy` | Fast math for audio arrays |
| `scipy` | Signal processing — used by Morphogenics spectral plugins |
| `soundfile` | Reads and writes WAV and FLAC files |
| `librosa` | Resamples audio, pitch-shifting, spectral analysis |
| `pyyaml` | Reads YAML score files |
| `flask` | Runs the web editor server |
| `pillow` | Image handling for score image overlays |

---

## Step 7 — Verify everything works

Run these three commands. Each should produce output without errors:

```bash
python -c "import numpy, scipy, soundfile, librosa, yaml, flask, PIL; print('Python packages OK')"
```

```bash
ffmpeg -version
```

```bash
sox --version
```

If all three work, you're ready. Go to [editor.md](editor.md) to start composing.

---

## Troubleshooting

**`python: command not found`** — Try `python3` instead of `python`. On some systems the command is `python3`.

**`pip: command not found`** — Try `pip3` instead.

**`No module named ...`** — You probably forgot to activate the virtual environment. Run `source venv/bin/activate` and try again.

**`sox: command not found` or `ffmpeg: command not found`** — The system tools were not installed correctly. Go back to Step 1 and try again.
