# Changelog

All notable changes to ProbabilisticMusic are recorded here.
The version number follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR** — incompatible change (e.g. score format breaks)
- **MINOR** — new capability, backwards compatible
- **PATCH** — bug fix, no new functionality

---

## [0.3.0] — Morphogenics Plugin System

### Added
- **Morphogenics plugin system** — 20 individual spectral/granular/compositional processors
  accessible as a dedicated "Morphogenics" group in the FX dropdown.
  Each plugin is a self-contained `.py` file in `plugins/` with a PARAMS schema
  that drives both backend processing and frontend widget generation automatically.
- **Per-composer plugin breakdown** — one technique per file, grouped by composer:
  - **Nørgaard: Undertones** — synthetic undertones shifted down in the harmonic series
  - **Messiaen: Modes** — sliding-window pitch quantization to Messiaen's 7 modes
  - **Penderecki: Cluster** — dense pitch-cluster chords (Threnody style)
  - **Penderecki: Aleatoric** — random pitch displacement per segment
  - **Penderecki: Textural** — combined cluster + aleatoric layering
  - **Penderecki: Glissando** — continuous pitch sweep through each segment
  - **Xenakis: Granular Cloud** — stochastic granular synthesis with pitch/time randomization
  - **Xenakis: Stochastic Cloud** — dense sine-burst clusters at log-uniform random frequencies
  - **Xenakis: GENDY** — Weibull-distributed step amplitude envelope
  - **Saariaho: Spectral Freeze** — STFT-based sustain: top-N partials, slow phase evolution
  - **Saariaho: Microtonal** — spectral-centroid-driven microtonal detuning
  - **Desyatnikov: Minimalism** — polystylistic quote: every Nth onset shifted by an interval
  - **Desyatnikov: Lyricism** — maj7 (+11 st) + dim11 (+17 st) harmonic layers
  - **Desyatnikov: Glissandi** — portamento slides at random onset boundaries
  - **Spectral: Harmonic Stretch** — bin remapping to stretch upper partials outward
  - **Spectral: Inharmonic** — partial shifting to inharmonic ratios (×1.3, ×2.7, ×4.5)
  - **Spectral: Smooth** — spectral envelope smoothing via frequency-bin blurring
  - **Wagner: Leitmotif** — onset-segmented motifs with random transposition + time-stretch
  - **Wagner: Tristan** — Tristan chord overlay (4:5:6:7 just-intonation) on onset segments
  - **Wagner: Endless Melody** — smooth crossfades + chromatic passing tones at boundaries
- `GET /plugins` endpoint — returns all plugin schemas as JSON for UI auto-generation
- `scipy` added to `requirements.txt` (used by spectral bin-remapping plugins)
- `docs/morphogenics.md` — full plugin reference documentation

### Fixed
- `messiaen_modes.py` — `break` → `continue` in sliding-window loop (prevented audio tail from
  being processed)
- `desyatnikov_minimalism.py`, `wagner_leitmotif.py`, `wagner_tristan.py` — onset guard changed
  from `< 2` to `< 1` (prevented processing on audio with a single detected onset)
- `penderecki_aleatoric.py`, `penderecki_textural.py` — ceiling division for segment count
  (floor division silently dropped the last partial segment)
- `xenakis_gendy.py` — ceiling division for grain count (last samples kept full amplitude
  instead of getting a Weibull weight)

---

## [0.2.0] — Expressive Engine + Web Editor

### Added
- **V2 Expressive Interpretation Engine** — higher-order Markov chain on the joint state
  (symbolic marking, rendered output vector). Every run of the same score produces a
  different but musically coherent performance.
  - Symbolic and joint Markov modes
  - Multivariate Gaussian emission with diagonal or full covariance
  - 13 supported dynamic markings: ppp–fff, sfz, fp, subito_p, subito_f, cresc, decresc
  - sfz recovery shadow: next 1–2 events pulled quieter after a sforzando
  - Phrase boundary detection (automatic) with reset or continuous history
  - History decay weighting (configurable)
  - Cold-start defaults for the first N events
  - Expert priors in `v2/transition_table.yaml` (editable without touching code)
  - Optional Bayesian update with MAESTRO data (stub, not yet implemented)
- **Web editor** (`editor/`) — browser-based visual score editor
  - Waveform display with zoom, pan, seek
  - Sample, Event, Dynamics, Tempo, FX tools
  - Score panel with live summary
  - Stemize (HPSS + NMF audio source separation)
  - Export YAML, Import YAML, Export MP4 (scrolling score video)
  - Engine selector (V1 / V2 β) with inline V2 config panel
  - Probabilistic parameter fields (fixed / range / gaussian)
  - Undo / Redo
  - `GET /plugins` endpoint for Morphogenics auto-discovery (added in 2.1.0)
- `config.yaml` — user-facing engine selector and V2 settings
- Auto-incrementing numbered output files (`output_score_base_001.wav`, `002.wav`, …)
- Articulation and note-relationship tools: Slur, Glissando, Arpeggio, Staccato, Legato,
  Fermata, Accent
- Score image overlay with scrolling MP4 export

### Changed
- `score.yaml` extended with `dynamics:`, `tempo:`, `base_fx:`, `fx_ranges:`,
  `silence_start:` sections
- Effects expanded: `reverb`, `delay`, `overdrive`, `flanger`, `pitch`, `compress`, `eq`
- `main.py` refactored: `--input` / `--score` CLI arguments, config routing, V2 dispatch
- `src/` pipeline split into `parser.py`, `sample_engine.py`, `scheduler.py`,
  `envelope.py`, `fx.py`, `mixer.py`, `renderer.py`

---

## [0.1.0] — Initial Release

### Added
- Core audio synthesis engine: render a YAML score against a source audio file
- `samples:` / `events:` score schema
- Varispeed (tape-style pitch + duration change via `speed:`)
- Sample looping, gain, reverse
- Global amplitude envelope (`envelope: points:`)
- SoX-backed effects: `delay`, `reverb`
- V1 stochastic parameters: uniform range and Gaussian distributions on event fields
- Probabilistic parameters: `[min, max]`, `{distribution: gaussian}`, `{distribution: bernoulli}`,
  `{distribution: discrete}`
- Output rendered to `output/output.wav`
- `requirements.txt` with `numpy`, `soundfile`, `librosa`, `pyyaml`, `flask`
