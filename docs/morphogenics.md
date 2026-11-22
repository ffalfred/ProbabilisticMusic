# Morphogenics — Spectral and Compositional Processors

Morphogenics is a collection of 20 advanced audio processors grouped under the **"Morphogenics"** section of the FX dropdown. Each plugin is inspired by a specific compositional technique or composer and operates on the audio at a spectral, granular, or structural level — well beyond what reverb or delay can do.

They can be applied per-event, as an FX zone over the base track, or as a global base FX.

---

## How to use them

### In the editor

In any FX dropdown (event popup, FX zone, or Base FX), scroll down to the **Morphogenics** group. The dropdown shows all 20 plugins by their full names.

When you select one, the parameter widgets appear automatically below the dropdown — no manual entry needed. Each plugin generates its own controls based on its parameter schema.

### In a score YAML

Morphogenics effects are stored in the score just like any other effect, using the `type:` field with the plugin's type key:

```yaml
events:
  - sample: texture
    t: 4.0
    gain_db: -6
    fx:
      - type: morpho_spectral_freeze
        mode: attacks
        n_partials: 20
        dry_wet: 80
```

For FX zones:

```yaml
fx_ranges:
  - from: 10.0
    to: 18.0
    fx:
      - type: morpho_grain_scatter
        grain_ms: 40
        pitch_spread: 6
        shuffle_pct: 30
        amplitude_var: 40
        dry_wet: 90
```

If a parameter is omitted, the plugin uses its default value.

---

## Common parameter: `dry_wet`

Every plugin has a `dry_wet` parameter (0–100%). At `0`, the output is the original unprocessed audio. At `100`, the output is entirely the processed signal. At `80` (a common default), you get a blend of 80% processed and 20% original.

---

## Nørgaard: Undertones

**Type key:** `morpho_undertones`

Inspired by Per Nørgaard's infinity series and undertone spectralism. Adds synthetic undertones below the fundamental — pitch-shifted copies at successive intervals down the harmonic series.

The undertones decay in gain with each step: the second undertone is half the gain of the first, the third a third, and so on.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `n_undertones` | 1–8 | 3 | How many undertone layers to add |
| `gain_db` | −24–0 dB | −12 | Gain of the first (closest) undertone. Subsequent ones are proportionally quieter. |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

Undertone intervals (in semitones below the source): −12, −19, −24, −28, −31, −34, −36. These correspond to the first seven subharmonics.

**Typical use:** Enrich a sparse texture with a low-frequency halo. Add weight under a high-pitched fragment.

---

## Messiaen: Modes

**Type key:** `morpho_modes`

Pitch-quantizes the audio to one of Messiaen's 7 modes of limited transposition. The mode is detected and applied in overlapping time windows so gradual pitch movement is tracked rather than applying a single global shift.

The musicologically correct mode definitions are used:

| Mode | Pitch classes (semitones from root) | Common name |
|------|-------------------------------------|-------------|
| 1 | 0, 2, 4, 6, 8, 10 | Whole-tone |
| 2 | 0, 1, 3, 4, 6, 7, 9, 10 | Octatonic (half-whole) |
| 3 | 0, 2, 3, 4, 6, 7, 8, 10, 11 | — |
| 4 | 0, 1, 2, 5, 6, 7, 8, 11 | — |
| 5 | 0, 1, 5, 6, 7, 11 | — |
| 6 | 0, 2, 4, 5, 6, 8, 10, 11 | — |
| 7 | 0, 1, 2, 3, 5, 6, 7, 8, 9, 11 | — |

The algorithm detects the fundamental frequency (F0) per window using `librosa.yin`, finds the nearest pitch class in the selected mode, and works out the shift that window needs. The shifts become one pitch curve that glides from window to window, and the whole clip is shifted along it in a single pass, so there are no seams.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `mode` | 1–7 | 2 | Which Messiaen mode to quantize to |
| `root_hz` | 20–2000 Hz | 440 | Root pitch of the mode (A4 = 440) |
| `window_sec` | 0.1–2.0 s | 0.5 | Analysis/processing window length. Shorter = more responsive, more artifacts. |
| `dry_wet` | 0–100% | 100 | Dry/wet mix |

**Typical use:** Transform a melodic fragment so it always sits inside a mode, creating an unmistakably Messiaen-like modal colouring. Works best on monophonic material.

---

## Penderecki: Cluster

**Type key:** `morpho_cluster`

Inspired by the string clusters of Penderecki's *Threnody for the Victims of Hiroshima*. The sound is copied onto **every semitone (or quarter tone) across a band** of `cluster_width`, centred on its own pitch: width 4 in semitones gives −2, −1, 0, +1, +2; in quarter tones, nine voices from −2 to +2. Up to 25 voices.

Each voice is alive rather than a static copy:
- **Drift** — every voice wanders slowly and independently by up to ±`drift_cents`, gliding to a new target about every 0.7 s, so the band shimmers and beats like a section of players instead of sounding like a harmoniser.
- **Entries** — with `entry_s` above 0, the voices enter one by one, in random order, spread over that many seconds (each fading in over 0.3 s): the cluster builds up.
- **Stereo** — the voices are laid out across the field from low (left) to high (right), as wide as `spread`.

The cluster is matched to the input's loudness.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `cluster_width` | 1–24 st | 4 | Width of the band |
| `step` | semitone / quarter tone | semitone | Spacing of the voices |
| `drift_cents` | 0–50 cents | 10 | How far each voice wanders (0 = static) |
| `entry_s` | 0–10 s | 0 | Voices enter one by one over this time (0 = all together) |
| `spread` | 0–100% | 60 | Stereo width (stereo pieces only) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** A wide quarter-tone band (`cluster_width: 6`, `step: quarter tone`) with `entry_s: 4` for a Threnody-like build-up on a sustained sound; a narrow semitone band with 20–30 cents of drift for a dense, beating halo. Combine with reverb for an orchestral wall of sound.

*Changed in this version:* the old Cluster placed `n_voices` static copies evenly across the width (−2, −0.67, +0.67, +2 at the defaults), so it was neither a semitone band nor alive. `n_voices` is gone; the band's steps set the number of voices.

---

## Penderecki: Aleatoric

**Type key:** `morpho_aleatoric`

Inspired by Penderecki's Devil's Staircase and aleatoric notation. Divides the audio into ~250ms segments and applies a different random pitch shift to each, within a user-defined detune range.

The randomness is controlled per segment independently — it doesn't drift cumulatively; each segment draws a fresh value. Neighbouring segments are joined by short glides rather than jumps.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `detune_cents` | 0–100 cents | 25 | Maximum pitch displacement per segment. 100 cents = 1 semitone. |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Give a texture a sense of human/performer variability, or create the impression of slightly out-of-tune performers. Subtle at 10 cents, clearly unstable at 80 cents.

---

## Penderecki: Textural

**Type key:** `morpho_textural`

Inspired by *Polymorphia*: the restless, aleatoric counterpart to Cluster. The same band of voices (every semitone or quarter tone across `cluster_width`), but every voice is unstable:
- each jumps to a new random detune, up to ±`detune_cents`, about every 250 ms (with a 60 ms glide), independently of the others;
- each swells and fades on its own, between full level and `1 − swell`;
- in stereo, the voices are scattered at random across the field, as wide as `spread`.

The result is a seething sound mass rather than a chord.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `cluster_width` | 1–12 st | 4 | Width of the band |
| `step` | semitone / quarter tone | semitone | Spacing of the voices |
| `detune_cents` | 0–100 cents | 25 | How far each voice jumps |
| `swell` | 0–100% | 50 | How deep each voice's level swells (0 = steady) |
| `spread` | 0–100% | 80 | Stereo width (stereo pieces only) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Sustained tones or drones. Moderate settings give a nervous, living texture; quarter tones with 60–100 cents of detune and full swell give dense, seething masses. Quarter-tone bands have many voices, so they take longer to render.

*Changed in this version:* Textural used to be a static cluster plus one randomly detuned copy. `n_voices` is gone.

---

## Penderecki: Glissando

**Type key:** `morpho_glissando`

Creates continuous pitch slides through each segment of the audio — a linear sweep from −gliss_range/2 to +gliss_range/2 semitones over each ~200ms chunk.

Each chunk is subdivided into `n_steps` steps, from the low end of the range to the high end, joined by glides into one rising slide. The next chunk starts the sweep again from the bottom.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `gliss_range` | 1–24 st | 12 | Total pitch sweep range in semitones |
| `n_steps` | 3–10 | 5 | Number of discrete steps in the sweep |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Use on string-like textures to get the characteristic Penderecki orchestral glissando effect. Small range (2–4 st) for a subtle shimmer; large range (12–24 st) for dramatic sweeps.

---

## Xenakis: Grain Scatter

**Type key:** `morpho_grain_scatter`

Stochastic granular resynthesis in the spirit of Xenakis's formalized music theory. Divides the audio into grains, randomly shuffles a percentage of them, applies random pitch shifts and amplitude variations to each, and reassembles them. Grains overlap by half under Hann windows, which add up to a constant, so the grain stream itself never dips: with no randomness the output is exactly the input. Grains are re-pitched tape-style (read faster or slower), the classic granular technique: at 10–100 ms they are too short for a time-stretcher.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `grain_ms` | 10–100 ms | 40 | Length of each grain |
| `pitch_spread` | 0–24 st | 6 | Maximum random pitch shift per grain (±spread/2) |
| `shuffle_pct` | 0–100% | 30 | Percentage of grains whose playback order is randomly permuted |
| `amplitude_var` | 0–100% | 40 | Random amplitude reduction per grain (each grain is attenuated by a random factor) |
| `spread` | 0–100% | 50 | Stereo pieces: each grain lands at a random place in the field (0 = the source's own image) |
| `dry_wet` | 0–100% | 90 | Dry/wet mix |

**Typical use:** Break apart a recognizable texture into a cloud of fragments. Lower shuffle produces a smeared version of the original; higher shuffle creates something entirely new.

---

## Xenakis: Stochastic Cloud

**Type key:** `morpho_stochastic_cloud`

Generates a dense probabilistic layer of short sine-burst grains at random frequencies within a user-defined range. The frequency distribution is log-uniform (equal density per octave), meaning you get as many grains between 200–400 Hz as between 1600–3200 Hz.

All grains are Hanning-windowed and summed additively into a new signal that is then mixed with the dry audio.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `density` | 10–200 grains/sec | 80 | How many sine bursts per second |
| `low_hz` | 50–2000 Hz | 200 | Lower frequency bound |
| `high_hz` | 500–8000 Hz | 3000 | Upper frequency bound |
| `grain_ms` | 5–30 ms | 10 | Duration of each burst |
| `spread` | 0–100% | 70 | Stereo pieces: each burst sits at a random place in the field (0 = centre) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a shimmering or buzzing background texture inspired by Xenakis's GENDYN system. A narrow frequency range creates a pitched cluster; a wide range creates wideband noise-like texture.

---

## Xenakis: GENDY

**Type key:** `morpho_gendy`

Built on Xenakis's GENDYN (dynamic stochastic synthesis): a waveform is drawn through breakpoints whose heights and spacings take *second-order random walks* (a random walk whose step size is itself a random walk), each held between reflecting barriers. Steps are Cauchy-distributed, as in GENDYN: mostly small, occasionally large. `randomness` scales all the walks.

Three modes:
- **`input`** (default) — the walks act on the input itself. At breakpoints every ~`grain_ms`, the read position drifts ahead or behind and the level dips, joined by straight lines. The original is continuously squeezed, stretched (pitch wobbles) and re-levelled: it turns grainy and unstable, without clicks.
- **`synth`** — a real GENDYN oscillator with `breakpoints` points per period, centred on `pitch_hz` (0 = the input's own pitch), drifting up to ±`randomness` octaves, and following the input's loudness. It adds a new, buzzing, unstable voice; balance it with `dry_wet`.
- **`envelope`** — only the level walks, smoothly between breakpoints: a stochastic tremolo, the gentlest mode.

At `randomness: 0`, `input` and `envelope` leave the sound unchanged and `synth` holds one fixed waveform.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `mode` | input / synth / envelope | input | See above |
| `randomness` | 0–100% | 30 | Size of the random walks |
| `grain_ms` | 2–50 ms | 20 | Average breakpoint spacing (`input`, `envelope`) |
| `breakpoints` | 4–32 | 12 | Breakpoints per waveform period (`synth`) — more = brighter, noisier |
| `pitch_hz` | 0–2000 | 0 | Centre pitch (`synth`); 0 = detected from the input |
| `spread` | 0–100% | 50 | Stereo pieces: each side also gets its own random walks, blended in by this much (0 = both sides move together) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** `input` at 20–40% for an organic instability; 80–100% for a sound that keeps tearing apart. `synth` under a sustained sound for a Xenakis-like stochastic double. Combine with Stochastic Cloud for a full GENDY-style texture.

*Changed in this version:* GENDY used to multiply the audio by a random step envelope (a new Weibull-distributed level every `grain_ms`, which clicked). `weibull_shape` is gone.

---

## Saariaho: Spectral Freeze

**Type key:** `morpho_spectral_freeze`

Inspired by Kaija Saariaho's sustained, slowly evolving harmonic fields. Captures moments of the sound and holds them: a held moment keeps its magnitudes and keeps every partial at its true frequency (measured from the phase), so it sustains as a steady chord or halo.

Two modes:
- **`attacks`** (default) — at every detected attack, the sound just after it is captured and held until the next attack, then crossfades into it (50 ms). The music becomes a chain of held chords: each note sustains at its full level instead of decaying.
- **`follow`** — the held sound follows the original slowly. `freeze_rate` sets how fast: `1` follows almost at once (~50 ms), `0.1` takes about half a second, `0.01` about five seconds, and `0` holds the very first moment for the whole clip.

`n_partials` keeps only the strongest partials of the held sound — low values (5–8) purify it to a few sustained tones; `0` keeps everything. The frozen layer is matched to the input's loudness.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `mode` | attacks / follow | attacks | See above |
| `n_partials` | 0–100 | 20 | Strongest partials kept (0 = all) |
| `freeze_rate` | 0–1 | 0.1 | How fast the held sound follows (`follow` mode only) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** `attacks` turns a melody or a sequence of hits into sustained harmonies; `follow` at 0.02–0.1 makes a slowly morphing pad under the original. Mix at `dry_wet: 50–80` to keep the original audible.

*Changed in this version:* the effect used to keep the loudest bins of every frame and advance their phases at a fraction of normal speed, which did not freeze anything — it transposed everything down and smeared it.

---

## Saariaho: Microtonal

**Type key:** `morpho_microtonal`

Inspired by Saariaho's microtonal language tied to spectral brightness. Analyzes the spectral centroid of the input (a measure of brightness), maps it to a detune value, and applies a small pitch shift in the range ±max_cents.

Bright audio (high centroid → near 5000 Hz) is detuned upward (sharpened). Dark audio (low centroid → near 500 Hz) is detuned downward (flattened). The relationship is linear between these anchor points.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `max_cents` | 0–50 cents | 25 | Maximum detune at the extreme of the brightness range |
| `dry_wet` | 0–100% | 100 | Dry/wet mix |

**Typical use:** Gives audio a subtle spectral-brightness-aware intonation — brighter passages drift slightly sharp, darker ones drift flat. Even `max_cents: 5` creates a barely-perceptible microtonal colour; 25–50 cents is clearly audible. Effective on sustained tones.

---

## Desyatnikov: Minimalism

**Type key:** `morpho_minimalism`

Inspired by Leonid Desyatnikov's polystylistic compositional language. Uses onset detection to locate note boundaries, then displaces every Nth onset segment by a fixed interval (the "quote interval"). The displaced segments sound like a sudden tonal intrusion from a different harmonic world — a polystylistic quote.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `nth_onset` | 2–8 | 4 | Every Nth detected onset is displaced |
| `quote_interval` | 1–12 st | 6 | How far to shift the displaced segment (6 st = tritone — maximally dissonant; 7 st = fifth — consonant) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Introduce unexpected harmonic intrusions into a melodic line. A tritone (6 st) creates a jarring polystylistic effect; a major second (2 st) is more subtle. Works well on material with clearly detectable attacks.

---

## Desyatnikov: Lyricism

**Type key:** `morpho_lyricism`

Inspired by Desyatnikov's warm, non-functional harmonic language. Two transposed copies of the audio shadow the line in parallel — by default a major 7th (+11 st) and a perfect 11th (+17 st, an octave plus a fourth) above it — colouring it without implying functional harmony. Both are attenuated so they blend into the timbre rather than sounding as separate lines.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `interval_1` | 1–24 st | 11 | First parallel interval |
| `interval_2` | 0–24 st | 17 | Second parallel interval (0 = off) |
| `placement` | above / below | above | Which side of the line the intervals go |
| `harm_gain_db` | −24–−6 dB | −18 | Volume of the added layers |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a discreet harmonic richness to any melodic or tonal fragment. Use `harm_gain_db: -24` for a very subtle effect; `-12` is more pronounced. `placement: below` puts the shadow under the line (a darker, organ-like support).

*Changed in this version:* the description used to call +17 st a "diminished 11th" (it is a perfect 11th) and say the layers sit under the line (they were above). The defaults sound exactly as before.

---

## Desyatnikov: Glissandi

**Type key:** `morpho_glissandi`

Inspired by Desyatnikov's portamento-inflected melodic language. Detects onsets in the audio, then randomly selects a percentage of them as glide targets. At each selected onset, a 50ms portamento slide (from +port_st down to 0) is added additively, creating the impression of the pitch gliding into the note from above. The slide is tape-style: pitch and speed glide together, like a real portamento.

The portamento is Hanning-windowed and blended additively at 0.5× gain so it adds colour without overwhelming the original.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `portamento_st` | 1–7 st | 3 | How far above the note the slide starts |
| `density_pct` | 1–30% | 10 | What percentage of detected onsets get a glide |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** At 10% density and 3 st, only a few notes get the glide — subtle and lyrical. At 30% density and 7 st, almost every note has a dramatic slide into it. Works best on melodic material with clear note attacks.

---

## Spectral: Harmonic Stretch

**Type key:** `morpho_harmonic_stretch`

Stretches (or squeezes) the spacing of the partials while the fundamental stays put — like a stretched piano tuning or a bell. Partial *n* of a sound with fundamental *f0* moves from *n·f0* to *f0·n^β*, with *β = log2(octave_ratio)*: the "octave" between the first two partials becomes `octave_ratio` instead of 2, and higher partials are pushed out progressively. Below 2 the partials are squeezed together.

Each partial is moved as a whole (its spectral peak and the bins around it) with its phase kept continuous, so the result is clean rather than phasey. The fundamental is detected from the sound; set `pivot_hz` to stretch around a different frequency instead.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `octave_ratio` | 1.5–3.0 | 2.2 | Size of the stretched "octave" (2.0 = unchanged) |
| `pivot_hz` | 0–2000 | 0 | Frequency that stays fixed (0 = the sound's fundamental) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** 2.05–2.2 for a shimmering, slightly metallic colour; 2.5–3.0 for gong- and bell-like spectra; 1.6–1.9 for a squeezed, dark, out-of-tune timbre.

*Changed in this version:* the old effect scaled every frequency by `stretch_ratio` with the original phases — a smeared transposition, not a stretch. `stretch_ratio` is replaced by `octave_ratio`.

---

## Spectral: Inharmonic

**Type key:** `morpho_inharmonic`

A frequency shifter: adds the same number of Hz to every partial. A harmonic sound has partials at *f0, 2·f0, 3·f0, …*; shifting all of them by the same amount (say +100 Hz) breaks those whole-number ratios, so the sound turns metallic and bell-like — the classic frequency-shifter (Bode) effect. A few Hz give slow beating and phasing; negative shifts pull partials down, and any pushed below 0 Hz fold back up.

Done exactly with the analytic signal (Hilbert transform), so there is no smearing.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `shift_hz` | −1000–1000 Hz | 100 | How far every partial moves |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** 50–300 Hz on pitched material for bells, gongs and metallic timbres; 1–5 Hz mixed at 50% for a slow phasing shimmer; large negative shifts for growling, folded spectra.

*Changed in this version:* the old effect averaged four copies of the spectrum scaled by ×1.3, ×2.7, ×4.5 (times a factor) with the original phases, which sounded smeared. `inharmonic_factor` is replaced by `shift_hz`.

---

## Spectral: Smooth

**Type key:** `morpho_spectral_smooth`

Applies a uniform smoothing filter along the frequency axis of the STFT magnitude spectrum — effectively averaging each frequency bin with its `smooth_bins` neighbours. The phase is preserved unchanged. The result is a spectrally flattened version of the sound: transients and sharp spectral peaks are preserved in time but smeared across frequency.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `smooth_bins` | 1–10 | 3 | Smoothing radius. The filter size is `2 × smooth_bins + 1`. 1 = minimal; 10 = very smooth. |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Remove spectral definition to create a noise-like or abstract texture. At `smooth_bins: 1–2`, the effect is subtle — a slight spectral blurring. At `smooth_bins: 8–10`, the result is a nearly flat spectral profile — pitched content becomes noise-like.

---

## Wagner: Leitmotif

**Type key:** `morpho_leitmotif`

Inspired by Wagner's leitmotif technique. Uses onset detection to find natural phrase segments, then applies a random transposition and time-stretch to each segment, and tiles it (repeats it within the segment boundary). Each segment gets its own random treatment, creating a theme-and-variation structure from any source material.

The time-stretch factor is drawn from three choices: 0.75×, 1.0×, or 1.25× (randomly selected per segment).

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `transpose_range` | 0–12 st | 7 | Maximum random transposition (±range, so ±7 st for a perfect fifth above or below) |
| `repetitions` | 1–3 | 2 | How many times to tile each transformed segment before the next onset boundary |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Turn a short melodic phrase into a varying, self-quoting motif. With `repetitions: 2` and `transpose_range: 7`, each segment plays twice — the second time possibly transposed to a fifth away. Higher transpose ranges create more dramatic tonal leaps between segments.

---

## Wagner: Tristan

**Type key:** `morpho_tristan_chord`

Overlays the Tristan chord on every Nth onset segment, built on the sound itself as the chord's lowest note, in Wagner's voicing F–B–D♯–G♯: 0, +6, +10, +15 semitones (a half-diminished seventh, spread). All four voices are summed and mixed under the original at a user-defined gain.

`voicing: harmonic 7th` gives the chord the previous version used instead: a just-intonation 4:5:6:7 stack (0, +3.86, +7.02, +9.69 st) — a natural, slightly flat dominant seventh rather than the Tristan chord.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `voicing` | tristan / harmonic 7th | tristan | Which chord |
| `tristan_interval` | 2–8 | 3 | Apply the chord overlay to every Nth detected onset segment |
| `chord_gain_db` | −24–−6 dB | −12 | Volume of the chord overlay |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a Wagnerian harmonic weight to occasional segments. Use low `chord_gain_db` (−18 to −24 dB) for a subtle subliminal harmonic colour; −6 to −9 dB makes the chord clearly audible. Works on any source material — the chord is built on whatever pitch is in the segment.

---

## Wagner: Endless Melody

**Type key:** `morpho_endless_melody`

Inspired by Wagner's technique of joining melodic segments into an unbroken line. At each detected note boundary:
1. **Bridge**: the previous note's last moment is held (a short spectral freeze) and rings on across the boundary, fading out over `crossfade_ms` — so the line never breaks, even when the source cuts each note off.
2. **Soft entry**: the new note's attack comes in from half level and grows out of the held sound instead of cutting in.
3. **Passing tone**: a 50 ms burst of the boundary region, a semitone up or down (random), is added — a chromatic grace note joining the two notes.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `crossfade_ms` | 50–300 ms | 200 | How long the previous note rings on (and the new attack takes to reach full level) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Turn short, choppy events or samples into a connected line. Long `crossfade_ms` (200–300 ms) gives flowing legato; short (50–80 ms) just smooths the joins while keeping the rhythm.

*Changed in this version:* the old effect faded the audio to silence before every boundary and back in after it, which on dense material made the sound ~28 dB quieter and full of gaps — the opposite of legato.

---

## Technical notes

### Plugin auto-discovery

Plugins live in `ProbabilisticMusic/plugins/`. When the server starts, `plugins/__init__.py` scans the directory and loads every `.py` file that defines `NAME`, `PARAMS`, and `process()`. New plugins appear in the editor automatically without any configuration change.

The `/plugins` endpoint returns the full schema as JSON — the editor uses this to generate parameter widgets on the fly.

### Stereo

In a stereo piece, every plugin except Spectral Smooth receives both channels at once. Analysis (onsets, pitch, brightness) is done on the mono sum, so both sides make the same decisions (the same notes are quoted, the same attacks frozen), and pitch shifts process both channels together, so the stereo image is kept. A mono sound on both sides with `spread: 0` gives exactly the mono result on each side.

Five plugins can also place their material in the stereo field with `spread`: Cluster (voices from low-left to high-right), Textural (voices scattered), Grain Scatter (grains), Stochastic Cloud (bursts) and GENDY (independent random walks per side). In a mono piece `spread` has no effect.

A plugin opts into this by setting `STEREO = True`; it then gets a `(frames, channels)` array (use `frames_io` and `mono` from `plugins`). Without it, a plugin is mono and runs on each channel separately with the same random draws.

### Processing requirements

Pitch shifting and time stretching go through `src/stretch.py` (Rubber Band, via the `pedalboard` package). Onset and pitch detection use `librosa`; the spectral bin-remapping plugins (Harmonic Stretch, Inharmonic) use `scipy`. All are installed by `pip install -r requirements.txt`.

### Performance

Rubber Band costs more per call than a simple phase vocoder, so the plugins avoid calling it many times: effects that move pitch over time (Aleatoric, Textural, Glissando, Modes) pass one pitch curve for the whole clip; note-based effects (Minimalism, Tristan, Endless Melody) shift the whole clip once per interval and cut the notes out; independent voices and Leitmotif's per-note transforms run in parallel. Grain Scatter and Glissandi re-pitch tape-style, which is nearly free.

Measured on a 4-second clip, per channel (a stereo clip takes about twice as long):

| Plugin | Time |
|--------|------|
| Leitmotif | ~0.6 s |
| Textural | ~0.5 s |
| Tristan, Lyricism, Endless Melody, Minimalism, Cluster, Glissando, Modes, Aleatoric | ~0.25–0.4 s |
| Microtonal, Undertones | ~0.25 s |
| Spectral plugins, Stochastic Cloud, GENDY, Grain Scatter, Glissandi | < 0.15 s |

If you add a plugin, use `pitch_shift`, `time_stretch`, `transform`, `read_at_rate` and `parallel_map` from `src/stretch.py` rather than calling a pitch shifter directly.

### Adding your own plugin

Create a new `.py` file in `plugins/` with this structure:

```python
import numpy as np

NAME     = "My Plugin Name"
GROUP    = "morphogenics"
TYPE_KEY = "morpho_my_plugin_name"

PARAMS = {
    "my_param": {
        "label":   "my param",
        "type":    "float",      # "float", "int", or "select"
        "min":     0.0,
        "max":     1.0,
        "default": 0.5,
    },
    "dry_wet": {
        "label":   "dry/wet %",
        "type":    "float",
        "min":     0,
        "max":     100,
        "default": 80,
    },
}


def process(clip: np.ndarray, sr: int, params: dict) -> np.ndarray:
    my_param = float(params.get("my_param", 0.5))
    dw       = float(params.get("dry_wet", 80)) / 100.0
    audio    = clip.astype(np.float32)
    wet      = audio  # your processing here
    return (audio * (1.0 - dw) + wet * dw).astype(np.float32)
```

Restart the server and the plugin appears in the dropdown immediately.
