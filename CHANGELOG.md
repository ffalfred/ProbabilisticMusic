# Changelog

All notable changes to ProbabilisticMusic are recorded here.
The version number follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR** — incompatible change (e.g. score format breaks)
- **MINOR** — new capability, backwards compatible
- **PATCH** — bug fix, no new functionality

---

## [Unreleased]

### Changed — Concerto is a mode, not an Interpreter feature
- The Concerto controls (View, Download, layout, lead-in/out) sit in the shared bar next to the workspace tabs and present whichever workspace is active.
- Each workspace registers a Concerto source (how to render its audio, whether it has a performance trace). The Composer source renders the Composer's current state, saved or not, instead of the score file on disk; the Interpreter source renders the score with its golems. The Conductor has no source yet, so Concerto is disabled there.
- Without a performance trace, layouts show score lanes (dynamics and tempo curves, computed the same way the renderer applies them) instead of the trace panels; there is also a standalone "Dynamics & Tempo Lanes" video. Work in progress.
- Workspaces can't be switched while a Concerto download runs.
- An audio selector in the Concerto bar chooses what View plays and Download renders, independently of the editor's play mode: Composer — Mix or Source; Interpreter — Interp (with trace panels), Score or Raw. The choice is remembered per workspace and fixed while a View or Download runs. If audio is already playing when View starts, the chosen audio replaces it from the same position.

### Fixed — engine
- Multi-track scores loaded only the last track (indentation bug in `build_bank`); samples now slice from the right track.
- Simultaneous events (chords) were collapsed to one by the V2 interpreter.
- Random score values (`[lo, hi]`, `{distribution: …}`) were never resolved in the editor, so Mix crashed or always reversed; the editor now resolves them like the CLI.
- `seed` now reproduces the whole render: score randomness, golem performance and plugins all draw from it. `/preview` returns the seed it used.
- `filter_cutoff` is in Hz everywhere (it was Hz in the state but treated as 0–1 by the mixer, pinning the filter at 18 kHz).
- Full-band `note_rel` glissandi re-pitch events only; band-limited ones act on the mix only (previously the mix pass was a silent no-op, and banded glissandi shifted events twice).
- Brightness modulation hard-clipped the whole mix before normalisation.
- Phrase gain/fades were dropped when golems were active.
- Muted events no longer trigger `duck_base` / `duck_key` / auto-mix.
- `skew_normal` sampling crashed; random-walk golems with 5-dim vectors or 5×5 correlations (older UIs) crashed.
- SoX effects (reverb, EQ, pitch, flanger, …) went through 16-bit temp files: SoX added random dither (breaking reproducibility) and anything above full scale was hard-clipped. They now use 32-bit float with headroom.
- Crackle at segment seams in the Glissando, Aleatoric, Textural, Minimalism and Leitmotif plugins and in band-limited glissandi (overlap-add with context instead of butted blocks).
- Spectral Freeze advanced phase at 1/512 of the natural rate.
- Undertones no longer saturates the dry signal.

### Fixed — editor and export
- Composer Mix used the Kalman engine; it now renders with v1 like the concerto export.
- `/export_interp_wav` now matches `/preview` (section/global FX, dynamics, phrases, duck_key); `score_only` really drops the base.
- An empty golem list in the Interpreter now overrides golems saved in the score.
- Concerto: frames could be written out of order with concurrent uploads; resume reused truncated segments, missed `.ts` outputs and could splice two different performances — resume now re-renders from the saved seed; meta video no longer gets audio; audio export honours the time range; viz timelines use score time consistently.
- Undo/redo now covers tracks (add/remove, mute, gain, FX, FX regions, automation, stems) and golems (add, update, delete, move/resize). A drag is one undo step. Loading a score, interpretation or audio starts a fresh undo history.
- Concerto: the time range is in score time (as on the timeline) and is converted through the tempo map; leaving the end at the score's end renders to the end of the audio. Lead-out frames scroll the score on linearly with the visualisations held at their final state, instead of continuing tempo-mapped playback.
- Many UI fixes: distribution settings, Global Settings panel, random-walk dimensions, Cancel in golem popups, zero values replaced by defaults, track removal, undo/redo shortcuts, Conductor tab error, stale playback buffer, Web Audio automation preview, and HTML escaping of user-supplied names.

### Security
- The editor server only answers its own page: it listens on 127.0.0.1, rejects non-local `Host` headers (DNS rebinding) and cross-origin requests (other websites or localhost ports reading files through it). The Werkzeug debugger is off unless `OPUS_DEBUG=1`; the port can be set with `OPUS_PORT`.

### Removed
- Unused code: ~250 lines of mixer helpers, the concerto writer-thread and worker paths, the legacy `/concerto_frame` route.

### Added
- `tests/` — regression tests (`python -m unittest discover -s tests`).

---

## [0.4.0] — Golems

### Changed
- **V2 engine replaced with Kalman filter** — the Markov-chain expressive engine is gone.
  The new V2 engine implements the full theoretical foundation: AR(2) momentum transitions,
  adaptive Q (drama × volatility), window observations, fuzzy future lookahead, and piece
  characters. Every run of the same score produces a different but internally consistent
  interpretation.
- **Golems** — new score key `golems:` accepts a list of `{from, to, character}` entries
  that assign a named expressive personality to a time range. Built-in characters:
  `dramatic`, `lyrical`, `sparse`, `turbulent`. Characters are blended when ranges overlap.
- **Golems panel** in the web editor — accessible via the ◆ Golems button in the V2 toolbar.
  Allows creating, editing, and removing Golem entries with live export/import support.
- **config.yaml** restructured — old Markov params (`markov_mode`, `markov_order`,
  `covariance`, `phrase_boundary`, `history_decay`) replaced with Kalman params under
  `v2:` block (`A1`, `A2`, `Q_base`, `lambda`, `eta`, `xi`, `drama_weights`, `window_size`).
- **Engine selector label** updated from "V2 β" to "V2 Golems".

### Files added
- `v2/kalman.py` — Kalman predict/update core
- `v2/drama.py` — pre-rendering drama/salience/future_pull pass
- `v2/observation.py` — window encoding and H/R lookup
- `v2/character.py` — piece character presets and blending
- `v2/transition_table.yaml` — H/R per window pattern + character definitions

### Files removed
- `v2/markov_symbolic.py`, `v2/markov_joint.py`, `v2/emission.py`, `v2/context.py`
- `v2/transition_table.yaml` (old Markov table)

---

## [0.3.1] — Bug Fixes

### Fixed
- **Mix playback hang** — replaced `<audio>.canplay` event (no error handler, hangs forever on
  load failure) with Web Audio API `fetch → decodeAudioData → AudioBufferSourceNode`, matching
  the approach already used for Source playback (`wa-mix.js`)
- **Edit event wipes FX** — editing an event always reset its FX to none; now preserves existing
  FX if the user leaves the FX selector at "none" in the edit popup
- **auto_mix mode naming** — UI sent `mode: "linear"` but backend and docs use `"inverse"`;
  renamed the UI option to `"inverse"`
- **Export MP4 button label** — button text was permanently changed to "▶ MP4" after first export;
  now restored to "⇓ Export MP4"
- **Undo/redo missing duck/auto_mix state** — `_snapshotState()` omitted `duckBase`, `duckKey`,
  `autoMix`; these are now included in undo/redo snapshots
- **CLI renderer crash with `tracks:`** — `renderer.py` did `score['base_track']` unconditionally;
  now falls back to the first track path when `base_track:` is absent

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
