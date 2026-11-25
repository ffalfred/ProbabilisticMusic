# Changelog

All notable changes to ProbabilisticMusic are recorded here.
The version number follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR** — incompatible change (e.g. score format breaks)
- **MINOR** — new capability, backwards compatible
- **PATCH** — bug fix, no new functionality

---

## [Unreleased]

### Added — stereo
- Audio keeps its channels from loading to output. Stereo sources (including video audio, previously extracted as mono) render in stereo; mono sources still render mono, and mono renders are bit-identical to before. Mixed mono and stereo tracks render stereo, with mono tracks on both sides.
- All effects handle stereo. SoX effects process both channels together, so reverb and flanger now spread a stereo signal; chorus and spectral inversion run per channel with the same random choices on both sides. (Morphogenics: see "Morphogenics in stereo" below.)
- Chorus is vectorised (it was a per-sample Python loop) — much faster.
- Tracks at a different sample rate from the base are resampled to the base's rate (high-quality soxr) on load, before their track FX. Previously they played at the wrong speed and pitch (a 48 kHz stem on a 44.1 kHz base ran ~9% slow and flat). Video audio keeps its native rate instead of being forced to 44.1 kHz.
- Stemize keeps the stereo image: every method (HPSS, NMF, frequency bands) analyses one shared spectrum and applies the same mask to each channel, so each stem keeps its sounds' left/right placement and the components line up across channels. Mono files separate exactly as before.

### Changed — loudness
- Renders keep the level the performance produced. Previously every render was scaled so its single loudest instant sat at 0.9. That made renders impossible to compare: a loud performance with one strong hit came out quieter than a calm one, and a deliberately quiet golem (e.g. *sparse*) was turned up to match the others. Concerto's Source/Raw audio now also plays at its real level.
- Safety brake: a look-ahead limiter that pulls down only the moments that would go above −1 dBFS. Audio below that is untouched (bit-identical), and both channels get the same gain. In the editor it is a shared **brake** switch next to the workspace tabs (on by default), with an indicator showing how much it reduced peaks, or that a render clips with it off.
- Export loudness (Interpreter **↓ WAV** and Concerto Download): leave as performed (default), match the source's loudness, or reach a target (−14 / −16 / −23 LUFS or custom), plus a Safety brake checkbox (ticked by default). Loudness is measured in LUFS (ITU-R BS.1770-4) on the whole render, so a range export has the same level it has in the full piece. The status line reports loudness, adjustment and brake.
- CLI: an `output:` block in `config.yaml` (`brake`, `adjust`, `target_lufs`); each render prints its loudness.
- The editor's preview audio is written as 32-bit float (the exact render) instead of 16-bit. Concerto's audio output and the videos' soundtracks are now converted once, from the full-quality render.
- Concerto Download has a **Sound** choice: *Together* (in the score video, one file — the default), *Apart* (a silent score video plus a sound file, two files), *Both*, or *None*. It replaces the "Audio (.wav)" checkbox. The sound file sits next to the video with the same name and lead-in/out, so they stay in sync; with no video selected, *Apart* saves only the sound.
- Concerto's sound file has the same format choice as the Interpreter export: 24-bit WAV (default), 32-bit float WAV, FLAC or 16-bit WAV. It was always 16-bit WAV.

### Changed — reverb and delay (breaking: scores with reverb/delay sound different)
- Reverb and delay have two level knobs: **dry** (the original, default 1 = kept in full) and **wet** (the effect). Previously one `wet` knob crossfaded the original away as the effect came in: at wet 1 the original disappeared entirely. The old behaviour is a setting of the new knobs (old wet 0.5 ≈ dry 0.71, wet 0.71).
- Reverb `wet` 1 = the reverb as loud as the original while it sounds.
- Delay: `wet` is the level of the first echo and `feedback` scales each next one (wet 0.5, feedback 0.6 → 0.5, 0.3, 0.18, …). Previously the echo train was rescaled as a whole, so echoes could be louder than the note (feedback 0.3, wet 0.5: first echo ~2× the note) and `feedback` didn't set echo levels. Echoes now continue until −60 dB (at most 30 s) instead of stopping after 8.
- Default `reverberance` lowered from 100 to 50 (~2 s, a normal room). Now that tails ring out, 100 meant an ~11 s tail on every reverb.

### Fixed — reverb tails
- Reverb stopped dead at the end of each event's sample: SoX returns exactly as much audio as it's given, so there was no tail and the cut could click. The reverb now rings on until it dies away (−60 dB), e.g. ~2 s at reverberance 50 and ~11 s at 100. To keep this fast, each reverb setting's impulse response is recorded from SoX once and applied by FFT convolution (matches SoX to about −85 dB). Long audio (the whole mix, used by the golems' `reverb_wet`) still goes through SoX directly, and the golems' reverb is unchanged.

### Changed — pitch and time (sound changes: pitched and stretched audio is cleaner)
- Pitch shifting and time stretching use **Rubber Band** (R3 engine, via the new `pedalboard` dependency) instead of librosa's phase vocoder. This covers event pitch, `pitch_lock`, tempo steps and ramps (accelerando/ritardando), banded glissandi, the overtones effect and the Morphogenics. Attacks stay sharp: on drum-like hits, the smear in front of each hit dropped from about −2 to −17 dB below the hit to −14 to −35 dB, and hits stay close to their original length instead of spreading to 50–80 ms. Stereo channels are processed together, so the stereo image survives (they used to be shifted separately). Output is deterministic.
- All of it goes through one module, `src/stretch.py`. Tempo ramps and banded glissandi are one pass with a rate or pitch curve, replacing the hand-built variable-rate phase vocoder and the 20 ms chunked glissando.
- Morphogenics: effects that moved pitch in small overlapping pieces now follow one pitch curve (Aleatoric, Textural, Glissando, Modes). Note-based effects cut their notes from one whole-clip shift (Minimalism, Tristan, Endless Melody). Independent voices and Leitmotif's notes run in parallel. Grain Scatter and Glissandi's 50 ms slides re-pitch tape-style, the usual granular technique, because 10–100 ms is too short for any time-stretcher. Plugin speeds stay close to before.
- The classic `pitch` effect still uses SoX, which measured as clean as Rubber Band on attacks.
- Fixed: the docs gave the wrong `type:` key for 19 of the 20 Morphogenics (e.g. `morpho_penderecki_aleatoric` instead of `morpho_aleatoric`), and unknown keys were silently ignored, so a score written from the docs got no effect. Keys corrected; an unknown `morpho_` type now prints a warning listing the valid ones. (Scores made in the editor were not affected.)
- Fixed: the tempo map (which keeps the editor's cursor on the music) ran 10 ms ahead of the audio at every tempo-range boundary, because the 10 ms crossfades between segments weren't subtracted.
- **Licence:** Rubber Band and pedalboard are GPLv3; the project is Apache-2.0. This makes no difference to using the tool or to what it produces, but distributing the tool means GPL terms. Marked as an open question for later; options are in [docs/installation.md](docs/installation.md#licences).

### Changed — Morphogenics do what their names say (breaking: these effects sound different)
- **Tristan** uses the real Tristan chord, Wagner's voicing F–B–D♯–G♯ (0, +6, +10, +15 st), built on the sound. It used to stack a just 4:5:6:7 harmonic seventh, which is still available as `voicing: harmonic 7th`.
- **Lyricism**: its two parallel intervals and their side are now settings (`interval_1`, `interval_2`, `placement: above/below`). The defaults sound as before (+11 and +17 above); the description wrongly called +17 a diminished 11th (it's a perfect 11th) and said the layers sat below the line.
- **Harmonic Stretch** really stretches the partials: partial *n* moves to *f0·n^β*, set by `octave_ratio` (2 = unchanged), around the detected fundamental (or `pivot_hz`). It used to scale every frequency with the original phases, a smeared transposition. Partials are moved one by one with continuous phase (peak-based phase-vocoder shifting), so they stay clean. `stretch_ratio` → `octave_ratio`.
- **Inharmonic** is a frequency shifter (`shift_hz`): every partial moves by the same number of Hz, so harmonic sounds turn metallic. Exact (Hilbert transform). It used to average four smeared, scaled copies of the spectrum. `inharmonic_factor` → `shift_hz`.
- **Spectral Freeze** freezes: `mode: attacks` (default) holds the sound of each attack until the next one; `mode: follow` holds a sound that follows the original slowly (`freeze_rate`, 0 = hold the first moment). Held partials stay at their true frequencies. It used to keep the loudest bins of each frame and slow their phase down, which transposed everything down instead of holding it.
- **GENDY** is built on Xenakis's GENDYN (second-order random walks between reflecting barriers) with three modes: `input` (default; the walks squeeze, stretch and re-level the input itself), `synth` (a real GENDYN oscillator following the input's pitch and loudness) and `envelope` (a smooth stochastic tremolo). It used to be a stepped Weibull envelope that clicked every 20 ms. `weibull_shape` → `randomness`, plus `breakpoints` and `pitch_hz` for the synth.
- **Grain Scatter**'s grains overlap by half under Hann windows that add up to a constant. They used to sit end to end, so the sound dropped to silence between grains (a 25 Hz flutter).
- **Endless Melody** is legato: at each note boundary the previous note's last moment rings on across it (a short spectral freeze) while the new attack grows in from half level. It used to fade to silence around every boundary, which on dense material made the sound ~28 dB quieter and full of gaps.

### Changed — Morphogenics in stereo, and the Penderecki clusters
- Morphogenics receive both channels at once (all but Spectral Smooth). They analyse the mono sum, so both sides make the same decisions — previously each channel detected its own onsets and pitches, so the two sides could be cut, quoted or frozen at different moments — and their pitch shifts process both channels together, so the stereo image is kept. Mono pieces are unaffected; a mono sound on both sides with `spread: 0` gives exactly the mono result on each side.
- New `spread` setting on Cluster, Textural, Grain Scatter, Stochastic Cloud and GENDY places their voices, grains, bursts or random walks across the stereo field.
- **Cluster** is a real band: every semitone (or quarter tone, `step`) across `cluster_width`, centred on the sound, up to 25 voices. Each voice drifts slowly and independently (`drift_cents`), voices can enter one by one (`entry_s`), and in stereo they run from low-left to high-right. It used to be `n_voices` static copies spread evenly (−2, −0.67, +0.67, +2 st by default). `n_voices` is gone.
- **Textural** is the restless version: the same band, but each voice jumps to a new random detune every ~250 ms, swells on its own (`swell`) and is scattered in stereo. It used to be a static cluster plus one detuned copy. `n_voices` is gone.

### Changed — articulations act on events, or on the whole mix by choice (breaking)
- Staccato, accent, legato and fermata shape **the events they mark** (`target: event`, the default): a point mark covers the event starting nearest to it (within 0.5 s), a range every event starting inside it; the source and other events are untouched. Previously every mark acted on a time window of the whole mix, whatever was playing — and did not do what its name says: a staccato cut a 45 ms hole in everything (a range silenced the entire range), legato faded everything to silence, a fermata stacked six copies of a 70 ms snippet (a stutter), and an accent on a range boosted only its first moment.
- On an event: **staccato** keeps its first `keep_s` (default 0.15 s, adjustable) with its effects still ringing; **accent** boosts its first 50 ms by `boost_db` (default 6); **legato** lets it ring on until the next event (holding its last moment if the sample runs out), then fade as the next enters; **fermata** holds its last moment for `hold_s`.
- `target: mix` keeps a whole-mix version of each, now doing what the names say: over a range, staccato chops and accent boosts at each attack detected in the mix (or on an `every_s` grid), legato bridges each attack; a **whole-mix fermata makes the whole piece wait** — the sound is held for `hold_s` and inserted into the timeline, then everything resumes; the tempo map stands still there, so the editor's cursor stops during the hold.
- The editor's articulation popup has the target choice and the new settings; whole-mix marks show "(mix)" on the score. A range mark's label used to read "legato" whatever its type.
- The spectral helpers moved from `plugins/_spectral.py` to `src/spectral.py` (shared by the engine and the Morphogenics), with `hold_moment` and `legato_bridges`; Endless Melody uses the shared legato code.

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
- Brightness modulation hard-clipped the whole mix.
- Phrase gain/fades were dropped when golems were active.
- Muted events no longer trigger `duck_base` / `duck_key` / auto-mix.
- `skew_normal` sampling crashed; random-walk golems with 5-dim vectors or 5×5 correlations (older UIs) crashed.
- SoX effects (reverb, EQ, pitch, flanger, …) went through 16-bit temp files: SoX added random dither (breaking reproducibility) and anything above full scale was hard-clipped. They now use 32-bit float with headroom.
- Crackle at segment seams in the Glissando, Aleatoric, Textural, Minimalism and Leitmotif plugins and in band-limited glissandi (overlap-add with context instead of butted blocks).
- Spectral Freeze advanced phase at 1/512 of the natural rate.
- Undertones no longer saturates the dry signal.

### Fixed — Interpreter model (golem performances sound different)
- **Home values for every character.** Dimensions no marking pulls (width, overdrive, dynamic centre, attack, release…) relax toward each character's own resting value. Only the four original presets had one; with no golem, or the editor's other six presets, they drifted toward zero — width sank to ~0.09, nearly mono, as soon as the width mix dim was on.
- **Gain follows the markings.** Each character's resting gain was absolute (e.g. 0 dB), so the model kept pulling quiet passages up and loud ones down — pp came out 2–6 dB too loud. Gain now rests at the marking's level plus the character's offset; measured within 0.5 dB of every marking.
- **One definition of the presets.** The 10 Kalman and 9 random-walk presets are defined once (`src/character.py`, editor values) and served to the editor (`/golem_presets`); a "dramatic" golem is the same in the editor and in a score. The duplicate copy in `transition_table.yaml` is gone.
- **Hairpins** (crescendo / decrescendo ranges) shape golem performances, following the same curve as the Composer's dynamics; they were ignored.
- **Golems work on scores without events** (shaping the source audio through the mix dims). The piece's length counts every track.
- **Score mode** (Interpreter and Concerto) renders the score as written, with the plain engine — it used to add random per-note timing, attack and release from a default character.
- **Blending golems works**: each golem's own settings are blended by its faded weight instead of the dominant golem's replacing them; fades count when choosing the dominant golem; the per-golem λ (familiarity), Blend, φ mask (without φ scale), spike settings and the editor's distribution name take effect; starting values come from the golem(s) active at the start, not the first in the list; a blank per-dimension distribution follows the golem's.
- **Random-walk mean reversion** pulls toward the home values instead of zero (the "reverting" presets pulled the filter cutoff to 20 Hz).
- **Per-dimension distributions** crashed (numpy 2); fixed.

### Fixed — the Interpreter's trace shows the performance you heard
- With the seed box empty, Play rendered one random performance and the trace that followed drew another seed — the curves on screen belonged to a different performance than the audio. The trace now uses the seed the render used, and the audio that was played (its length sets the filter's time grid).
- The trace step changes the performance (the filter steps on that grid) but was left out of the render's cache key and only applied by Trace; every render now uses it, and changing it re-renders.
- Multi-walk traces start at your seed (walk k = seed + k) instead of seeds 0…N−1, and report their seeds.
- An older, slower trace can no longer overwrite a newer one.

### Fixed — Interpreter editor
- **Load interpretation** loads its score too and restores everything saved: golems, engine settings (replacing the previous ones instead of mixing with them), timbral pull and trace step.
- **Saving from the Composer** keeps a score's golems, mix dims and other settings the Composer doesn't show.
- **WAV export** of the whole piece keeps the reverb/fade tail; it was cut at the score's last second.
- **Vector editors** (per-dimension settings): pressing OK without changing anything leaves the setting unset instead of writing zeros; unset entries start from sensible values, not 0; the Q base and mean-reversion target accept their full ranges.
- The global **physical limits and clip method** apply to random-walk and discrete golems too, not only Kalman.
- The editor no longer sends its own hard-coded engine settings over `config.yaml`'s `v2:` block.
- **Edits re-render while playing**: changing a golem, a mix dim, the timbral pull, a Global Setting, the trace step or anything in the Composer (including undo/redo) re-renders the playing Mix / Score / Interp half a second after the last edit. Previously only muting a track did.
- **Undo covers the Interpreter's settings**: mix dims, timbral pull, Global Settings and trace step.
- **Transition lead and shape** in the golem editor (section D): how early a golem starts moving toward the next dynamic marking, and along which curve (sigmoid, ramp, exponential, step). The engine had these per preset, but golems made or edited in the editor always got the default (0.5, sigmoid). Presets fill them in.
- Removed dead code: `interp-media.js` (never loaded) and an unused character-list helper.

### Changed — every golem dimension is heard (golem performances sound different)
- **Filter**: the golems' filter is a resonant low-pass that follows the trace smoothly (updated every 32 samples). It used to jump between 16 fixed segments, and its "resonance" was a separate peak filter mixed in. Resonance 0 is the same Butterworth filter as before; 0.5 gives a +9 dB peak at the cutoff, 1 a +22 dB whistle. One filter (`src/resfilter.py`) now serves the golems and the Composer's filter effect.
- **The Composer's filter resonance works** (sound change for filters with resonance above 0): on low-pass and high-pass it did nothing. Band-pass is unchanged.
- **Attack and release** shape the curve of each event's fades as well as their length. A low attack is short and percussive, a high one swells in slowly. A low release holds and then drops, a high one decays into a long tail. 0.5 leaves the fade as written.
- **Timing is audible.** Per-note timing offsets had a spread of 3–9 ms, below what is heard; now 9–20 ms, depending on the character. Each preset has its own **timing looseness** (disciplined is tight; impulsive, turbulent, dramatic and sight-reading are loose), which can be changed in the golem editor (section B). The default timing noise (`Q_base`) went from 40 to 250.
- **New mix dims**, each with its own checkbox:
  - **drive**: overdrive, a tanh saturation mixed in by the golem's drive. 0 is the dry signal untouched; 0.3 is clearly driven; 1 is fully saturated. Computed at twice the sample rate to avoid aliasing.
  - **pitch**: each event a few cents sharp or flat, following the golem (up to ±50 cents, typically ±3–5). A tiny speed change, like a player slightly off; pitch-locked events are re-pitched instead.
  - **dynamics**: a 2:1 compressor whose threshold is the golem's dynamic centre (−30 to 0 dBFS), with half make-up gain. A low centre squeezes loud and soft together.
- **New 13th dimension, `tempo` (rubato)**, heard with the new **tempo** checkbox. It presses forward in crescendos and when approaching a louder marking, holds back in decrescendos, and broadens into each phrase end and the last note. Each preset has its own **rubato** amount (lyrical and impressionist free, disciplined nearly strict), changeable in the golem editor. Typical values are about +3 % in a crescendo and −8 % at a phrase end. It is combined with the score's own tempo changes into one time-stretch pass, so the editor's cursor and tempo map follow it.
  - Golems and settings saved with 12 dimensions still work: their per-dimension vectors (Q base, A1/A2, φ mask, random-walk steps, correlations, physical limits…) are padded with neutral values. The transition table's observation rows are padded with zeros (the markings don't observe tempo).
- The golem editor's "Starting values" use every preset's resting values from the server; it used to have a stale copy of four presets.

### Fixed — subito and accent markings
- `subito_p`, `subito_f`, `fp` and `sfz` (hand-written in a score) made golems aim at mezzo-forte: they weren't loudness levels, so the engine fell back to mf. The Composer's dynamics envelope ignored them. Now both follow one rule (`src/envelope.py: marking_level`):
  - `subito_p` and `subito_f` are p and f arriving at once;
  - `fp` settles at p;
  - `sfz` is an accent that keeps the level it lands in.

### Changed — the trace shows what you hear
- Only the dimensions you hear are drawn: the ticked mix dims, plus filter resonance with the filter. Timing, attack and release appear only when the score has events; width only for stereo audio. The legend lists all 13 dimensions, with the others greyed out. Ticking a mix dim or undoing redraws it.
- Each dimension is drawn on its full, fixed range (gain −40…+6 dB, filter 20 Hz–20 kHz on a log scale, tempo ±30 %, …), so a small wobble looks small. Each line used to be stretched to its own min and max, so a 0.01 change filled the whole height.
- **walks** above 1 draws every walk (the first bold, the others faint). Only the first was drawn.

### Docs
- `docs/interpreter_guide.md` and `docs/v2.md` rewritten for the current Interpreter: 13 dimensions and how each is heard, mix dims, all 19 presets, rubato and timing, the trace, the seed, saving and exporting. Hairpins are written as `from`/`to` ranges; the old docs' `cresc` with `duration:` was never read. The Interpreter section of `docs/editor.md` is replaced with a short, current summary.

### Changed — three more Morphogenics
- **Undertones** uses the exact undertone series (f/2 … f/8: −12, −19.02, −24, −27.86, −31.02, −33.69, −36 st) instead of rounding to semitones (the 5th–7th undertones were up to 31 cents off).
- **Microtonal** bends the pitch with the sound's brightness moment by moment (smoothed over ~150 ms) instead of applying one fixed detune from the clip's average brightness.
- Clearer names: *Desyatnikov: Glissandi* → **Desyatnikov: Portamento**, *Penderecki: Glissando* → **Penderecki: Glissando Sweeps** (type keys unchanged, so scores keep working).

### Fixed — Concerto's .ts videos were silent
- The "2" presets (A2, B2, T2, H2, H2Q) put 16-bit PCM in MPEG-TS, which ffmpeg writes as an unnamed data stream: the videos had no audio track, so players (and probably the BrightSign) played them silently. They now carry AC-3 (Dolby Digital) at 640 kbps, 48 kHz — the formats BrightSign documents for `.ts`.
- New "3" presets (A3, B3, T3, H3, H3Q): the same video with lossless 24-bit PCM in a QuickTime `.mov`, to test on the BrightSign (its documentation only hints at PCM in video files).
- HEVC videos in `.mp4` / `.mov` are tagged `hvc1`, so QuickTime and Safari open them (`hev1`, ffmpeg's default, they refuse).

### Changed — golems: stereo width, reverb on top (golem performances sound different)
- The golems' `stereo_width` is applied (Interpreter → mix dims → **width**): mid/side width, 0 = mono, 0.5 = as recorded, 1 = twice as wide. It follows each character's own width and wanders with it, moving together with the reverb (as the model already linked them); stereo pieces only — the checkbox is dimmed for mono audio.
- The golems' `reverb_wet` adds the reverb on top of the original (like the Composer's reverb) instead of crossfading the original away: previously a golem at 0.65 left the original at 35 %. Its tail now rings past the end of the piece instead of being cut.
- The editor learns the loaded audio's channel count (`/load` returns `channels`).

### Added — fade shapes and automation (fades sound different: smooth by default)
- **Fade shapes**: every fade — sample and event fades, slur (phrase) fades, FX-zone fades — has a shape: `smooth` (equal-power, the new default), `linear` (the only shape before), `exponential` (straight in decibels) or `s-curve`. Set with `fade_curve:` in YAML or *fade shape* in the popups; an event follows its sample's shape unless it sets its own.
- **Automation**: any numeric effect setting can change over time — a curve of `[seconds, value]` points (`cutoff: {curve: [[0, 200], [2, 3000]]}`), entered in the editor with the **~** button next to each setting: a graph to draw on (click to add, drag to move, right-click to delete; spanning the zone / event / track / piece with its waveform behind) and the same points as text (`0s: 200, 2s: 3000`). Times count from the start of what the effect processes (event, zone, track or whole piece).
  - Exact: dry/wet of reverb and delay (delay's wet as a send level), every Morphogenics' dry/wet, filter cutoff and resonance, tremolo rate and depth, and pitch (via Rubber Band's pitch curve).
  - Every other setting is approximated by rendering the effect at moments along the curves (every point plus extra moments ≤ 0.25 s apart, up to 12) and moving smoothly between the renders — exact at those moments, blended in between.
- Fixed: editing a slur dropped its mute flag.

### Added — audio export from the Composer
- The Composer's **save audio…** field and **↓** button export the mix as an audio file, with the same choices as the Interpreter's export: the mix (exactly what Mix plays), events only, or the source only; a time range; loudness (as performed / match source / target LUFS) and the safety brake; 24-bit WAV, 32-bit float WAV, FLAC or 16-bit WAV. Previously the Composer had no audio export at all.
- That field used to belong to a "scrolling score video" MP4 button whose video carried the **raw source recording**, not the composition. The button (and `/export_mp4`) is removed; score videos are made with Concerto → Download, which renders the mix.
- Server: one export route, `/export_audio`, for both workspaces (the Composer sends its current state; the Interpreter its score file + interpretation). `/export_interp_wav` remains as an alias.

### Changed — faster renders: parallel events and a render cache
- Events are processed in parallel instead of one after another, and the processed source (base FX + source FX zones) and every event's clip are cached between renders. An event whose sound didn't change is reused — even if it was moved in time — so after an edit only the edited events are processed again. Decoded source files are kept too (a video's audio is extracted once).
- With the default random seed, every Mix is still a new performance: anything that draws random numbers (probabilistic values, random effects such as most Morphogenics) is redrawn; everything else (pitch, speed, reverb, filter, delay, …) is reused. With a fixed seed, everything is reused.
- Each event now has its own random stream, seeded in order from the render's seed: renders stay reproducible (same seed → identical audio, cached or not), but a given seed's random choices differ from earlier versions.
- Measured on a 103 s stereo piece with 30 events (pitch shifts, reverb, delay, filter, Cluster) and a ritardando: a Mix took 8.4 s; now ~3.6 s cold and ~3.1–3.3 s after editing or moving an event (building the mix: 5.9 s → 0.7–1.0 s). What remains is mostly the tempo stretch and the loudness pass.
- The safety brake computes its release only where it acts (identical output; ~3× faster when peaks are sparse), and loudness measurement filters in one pass.

### Added — output effects and lead-in / tail in the editor
- **Output FX** (toolbar, next to Base FX): an effect chain on the whole output, source and events together (`fx_global`).
- **FX zones can apply to the whole output**: the zone popup's *Applies to* switches between the source (`fx_ranges`, as before) and the whole output (`fx_sections`). Output zones are drawn in orange (`out:`).
- **⏱ Lead / tail**: the lead-in (`silence_start`, events start later) and new **tail silence** (`silence_end`, seconds of silence after the piece — it was accepted in scores but did nothing).
- `fx_sections` work like FX zones: a full effect chain instead of a single effect, tails ring past the zone, optional fades, and times are score times mapped through the tempo map (they used to be applied at unmapped times, so after a ritardando they landed in the wrong place, and their tails were cut). The older single-effect form still works.
- Source FX zones, track FX regions and output sections share one implementation (`src.fx.apply_zone`); the first two render bit-identically to before.

### Fixed — the editor dropped score settings it didn't show
- Opening a score in the editor and saving it again silently deleted `fx_sections`, `fx_global`, `silence_start` and `silence_end`, and the editor's Mix ignored them, so a score sounded different in the editor and from the command line. All four are now loaded, played, saved and undoable.
- Muted tempo ranges, phrases, note relations and FX zones were left out by the editor's Mix but played by a command-line render of the saved score (the engine ignored their `muted` flag, and phrases lost it on saving). The engine now leaves out every muted entry, and saving keeps the flag.

### Fixed — samples on tracks that start later
- A sample was cut from its track as if the track started at 0 s, ignoring the track's `from`: on a track starting at 10 s, a sample marked at 12–13 s took the track's own 12–13 s instead of 2–3 s — the wrong sound, or nothing at all if the track was shorter (its events were then silent). Samples are now cut on the timeline, like the track's FX regions and automation already were. Parts of a sample's range where its track isn't playing are silent, so a sample is always as long as its marked range. Tracks starting at 0 s (including stems) are unaffected.
- New: each sample chooses what it carries over from its track — any of the track's **FX chain**, **FX regions**, **volume automation** and **gain** (`include:` in YAML, checkboxes "carry from track" in the sample popup). Default: the FX chain only, as before. `all` gives exactly what you hear on the track there, `none` the file as it is. Mute is never carried, so a muted track can still be a source. The mixed base is unchanged (bit-identical).

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
