# Installation

## System dependencies

Two system-level tools must be installed before the Python packages:

### ffmpeg
Used to extract audio from video files and to mux the rendered audio back into the output video.

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

### SoX (Sound eXchange)
Used to apply reverb and delay effects to audio clips.

```bash
# macOS
brew install sox

# Ubuntu / Debian
sudo apt install sox

# Arch
sudo pacman -S sox
```

---

## Python environment

Python 3.10 or newer is required (uses `tuple[...]` type hints).

```bash
# Create a virtual environment (recommended)
cd opacity_toke
python -m venv interpreter_venv
source interpreter_venv/bin/activate     # Linux / macOS
interpreter_venv\Scripts\activate        # Windows

# Install Python dependencies
pip install -r beta_interpreter/requirements.txt
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `numpy` | Audio array math, mixing, envelope building |
| `soundfile` | Reading and writing WAV/FLAC files |
| `librosa` | Varispeed resampling (pitch + time together, tape-style) |
| `pyyaml` | YAML score parsing |
| `flask` | Local web server for the editor |

---

## Verifying the setup

```bash
cd beta_interpreter
python -c "import numpy, soundfile, librosa, yaml, flask; print('OK')"
ffmpeg -version | head -1
sox --version
```

All three commands should succeed without errors before you proceed.
