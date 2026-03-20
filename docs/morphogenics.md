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
      - type: morpho_saariaho_freeze
        n_partials: 20
        freeze_rate: 0.1
        dry_wet: 80
```

For FX zones:

```yaml
fx_ranges:
  - from: 10.0
    to: 18.0
    fx:
      - type: morpho_xenakis_granular
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

**Type key:** `morpho_norgaard_undertones`

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

**Type key:** `morpho_messiaen_modes`

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

The algorithm detects the fundamental frequency (F0) per window using `librosa.yin`, finds the nearest pitch class in the selected mode, and shifts that window accordingly. Windows overlap by 50% with Hanning crossfades to prevent seams.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `mode` | 1–7 | 2 | Which Messiaen mode to quantize to |
| `root_hz` | 20–2000 Hz | 440 | Root pitch of the mode (A4 = 440) |
| `window_sec` | 0.1–2.0 s | 0.5 | Analysis/processing window length. Shorter = more responsive, more artifacts. |
| `dry_wet` | 0–100% | 100 | Dry/wet mix |

**Typical use:** Transform a melodic fragment so it always sits inside a mode, creating an unmistakably Messiaen-like modal colouring. Works best on monophonic material.

---

## Penderecki: Cluster

**Type key:** `morpho_penderecki_cluster`

Inspired by Krzysztof Penderecki's Threnody for the Victims of Hiroshima. Adds N evenly-spaced pitch-shifted voices spread symmetrically around the original pitch, creating a dense tone cluster.

A cluster with `cluster_width: 4` and `n_voices: 4` places voices at −2, −0.67, +0.67, +2 semitones. With 8 voices at width 12, you get a full chromatic cluster.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `cluster_width` | 1–12 st | 4 | Total spread of the cluster in semitones |
| `n_voices` | 2–8 | 4 | Number of pitch-shifted copies |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Widen a single melodic note or texture into a cloud of close pitches. Combine with reverb for a Penderecki orchestral wall of sound.

---

## Penderecki: Aleatoric

**Type key:** `morpho_penderecki_aleatoric`

Inspired by Penderecki's Devil's Staircase and aleatoric notation. Divides the audio into ~250ms segments and applies a different random pitch shift to each, within a user-defined detune range.

The randomness is controlled per segment independently — it doesn't drift cumulatively; each segment draws a fresh value.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `detune_cents` | 0–100 cents | 25 | Maximum pitch displacement per segment. 100 cents = 1 semitone. |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Give a texture a sense of human/performer variability, or create the impression of slightly out-of-tune performers. Subtle at 10 cents, clearly unstable at 80 cents.

---

## Penderecki: Textural

**Type key:** `morpho_penderecki_textural`

Inspired by Polymorphia. Combines the Cluster and Aleatoric techniques simultaneously: a static cluster layer (0.6 weight) plus a per-segment aleatoric detune layer (0.4 weight). The result is a texture that is both clustered and subtly unstable.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `cluster_width` | 1–12 st | 4 | Cluster spread (see Cluster) |
| `n_voices` | 2–8 | 4 | Number of cluster voices |
| `detune_cents` | 0–100 cents | 25 | Aleatoric detune range per segment |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** The most complete Penderecki texture. Use on sustained tones or drones. Heavier settings create dense, seething sound masses.

---

## Penderecki: Glissando

**Type key:** `morpho_penderecki_glissando`

Creates continuous pitch slides through each segment of the audio — a linear sweep from −gliss_range/2 to +gliss_range/2 semitones over each ~200ms chunk.

Each chunk is subdivided into `n_steps` subframes. Subframe 1 is pitch-shifted to the low end of the range; subframe N is shifted to the high end. The subframes are concatenated to create a continuous rising slide. The next chunk starts the sweep again from the bottom.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `gliss_range` | 1–24 st | 12 | Total pitch sweep range in semitones |
| `n_steps` | 3–10 | 5 | Number of discrete steps in the sweep |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Use on string-like textures to get the characteristic Penderecki orchestral glissando effect. Small range (2–4 st) for a subtle shimmer; large range (12–24 st) for dramatic sweeps.

---

## Xenakis: Granular Cloud

**Type key:** `morpho_xenakis_granular`

Stochastic granular synthesis in the spirit of Xenakis's formalized music theory. Divides the audio into grains, randomly shuffles a percentage of them, applies random pitch shifts and amplitude variations to each, and reassembles with Hanning-windowed overlap.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `grain_ms` | 10–100 ms | 40 | Length of each grain |
| `pitch_spread` | 0–24 st | 6 | Maximum random pitch shift per grain (±spread/2) |
| `shuffle_pct` | 0–100% | 30 | Percentage of grains whose playback order is randomly permuted |
| `amplitude_var` | 0–100% | 40 | Random amplitude reduction per grain (each grain is attenuated by a random factor) |
| `dry_wet` | 0–100% | 90 | Dry/wet mix |

**Typical use:** Break apart a recognizable texture into a cloud of fragments. Lower shuffle produces a smeared version of the original; higher shuffle creates something entirely new.

---

## Xenakis: Stochastic Cloud

**Type key:** `morpho_xenakis_stochastic`

Generates a dense probabilistic layer of short sine-burst grains at random frequencies within a user-defined range. The frequency distribution is log-uniform (equal density per octave), meaning you get as many grains between 200–400 Hz as between 1600–3200 Hz.

All grains are Hanning-windowed and summed additively into a new signal that is then mixed with the dry audio.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `density` | 10–200 grains/sec | 80 | How many sine bursts per second |
| `low_hz` | 50–2000 Hz | 200 | Lower frequency bound |
| `high_hz` | 500–8000 Hz | 3000 | Upper frequency bound |
| `grain_ms` | 5–30 ms | 10 | Duration of each burst |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a shimmering or buzzing background texture inspired by Xenakis's GENDYN system. A narrow frequency range creates a pitched cluster; a wide range creates wideband noise-like texture.

---

## Xenakis: GENDY

**Type key:** `morpho_xenakis_gendy`

Inspired by Xenakis's GENDY stochastic synthesis system. Applies a Weibull-distributed step amplitude envelope to the audio: the clip is divided into short grains, and each grain receives an independently drawn Weibull-distributed amplitude weight.

The Weibull distribution is parameterized by its shape (k):
- k < 1: heavy exponential distribution — most grains are very quiet, a few are loud
- k = 1: exponential distribution — gradual dropoff
- k ≈ 2: Rayleigh-like — bell-shaped with a moderate peak
- k > 3: approaches normal — most grains are near the mean amplitude

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `weibull_shape` | 0.5–5.0 | 1.5 | Shape parameter of the Weibull distribution |
| `grain_ms` | 5–50 ms | 20 | Duration of each envelope grain |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Create abrupt, mathematically-derived amplitude patterns. Low shape values produce dramatically spiky dynamics; high values produce smooth, relatively even amplitude. Combine with Stochastic Cloud for a full GENDY-style texture.

---

## Saariaho: Spectral Freeze

**Type key:** `morpho_saariaho_freeze`

Inspired by Kaija Saariaho's spectral technique of sustained, slowly evolving harmonic fields. Uses STFT analysis to extract the top N partials (by magnitude) from each frame, then reconstructs the audio with very slowly advancing phases — creating a sustained, pad-like drone from any sound.

The `freeze_rate` controls how much the phase advances per frame:
- `1.0` = natural phase evolution (sounds like the original)
- `0.1` = very slow phase advance (sustained drone with subtle movement)
- `0.01` = nearly static frozen spectrum

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `n_partials` | 5–50 | 20 | How many spectral partials to retain per frame |
| `freeze_rate` | 0.01–1.0 | 0.1 | Rate of phase evolution (lower = more frozen) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Turn any audio fragment into a sustained spectral pad. Use low `n_partials` (5–8) for a pure harmonic tone; high values retain more of the original character. Mix at `dry_wet: 50–80` to blend the frozen layer under the original.

---

## Saariaho: Microtonal

**Type key:** `morpho_saariaho_microtonal`

Inspired by Saariaho's microtonal language tied to spectral brightness. Analyzes the spectral centroid of the input (a measure of brightness), maps it to a detune value, and applies a small pitch shift in the range ±max_cents.

Bright audio (high centroid → near 5000 Hz) is detuned upward (sharpened). Dark audio (low centroid → near 500 Hz) is detuned downward (flattened). The relationship is linear between these anchor points.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `max_cents` | 0–50 cents | 25 | Maximum detune at the extreme of the brightness range |
| `dry_wet` | 0–100% | 100 | Dry/wet mix |

**Typical use:** Gives audio a subtle spectral-brightness-aware intonation — brighter passages drift slightly sharp, darker ones drift flat. Even `max_cents: 5` creates a barely-perceptible microtonal colour; 25–50 cents is clearly audible. Effective on sustained tones.

---

## Desyatnikov: Minimalism

**Type key:** `morpho_desyatnikov_minimalism`

Inspired by Leonid Desyatnikov's polystylistic compositional language. Uses onset detection to locate note boundaries, then displaces every Nth onset segment by a fixed interval (the "quote interval"). The displaced segments sound like a sudden tonal intrusion from a different harmonic world — a polystylistic quote.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `nth_onset` | 2–8 | 4 | Every Nth detected onset is displaced |
| `quote_interval` | 1–12 st | 6 | How far to shift the displaced segment (6 st = tritone — maximally dissonant; 7 st = fifth — consonant) |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Introduce unexpected harmonic intrusions into a melodic line. A tritone (6 st) creates a jarring polystylistic effect; a major second (2 st) is more subtle. Works well on material with clearly detectable attacks.

---

## Desyatnikov: Lyricism

**Type key:** `morpho_desyatnikov_lyricism`

Inspired by Desyatnikov's characteristic warm, non-functional harmonic language. Adds two pitch-shifted copies of the audio under the main signal: one at +11 semitones (major 7th — a close, rich interval) and one at +17 semitones (a compound interval between a diminished 11th and a perfect 11th). Both are attenuated to sit underneath rather than above the melodic line.

The result is a subtle harmonic haze — the source melody remains clear but surrounded by a warm, complex harmonic cloud.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `harm_gain_db` | −24–−6 dB | −18 | Volume of the added harmony layers |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a discreet harmonic richness to any melodic or tonal fragment. The layers should barely be audible as distinct pitches — they blend into the timbre of the source. Use `harm_gain_db: -24` for a very subtle effect; `-12` is more pronounced.

---

## Desyatnikov: Glissandi

**Type key:** `morpho_desyatnikov_glissandi`

Inspired by Desyatnikov's portamento-inflected melodic language. Detects onsets in the audio, then randomly selects a percentage of them as glide targets. At each selected onset, a 50ms portamento slide (from +port_st down to 0) is added additively, creating the impression of the pitch gliding into the note from above.

The portamento is Hanning-windowed and blended additively at 0.5× gain so it adds colour without overwhelming the original.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `portamento_st` | 1–7 st | 3 | How far above the note the slide starts |
| `density_pct` | 1–30% | 10 | What percentage of detected onsets get a glide |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** At 10% density and 3 st, only a few notes get the glide — subtle and lyrical. At 30% density and 7 st, almost every note has a dramatic slide into it. Works best on melodic material with clear note attacks.

---

## Spectral: Harmonic Stretch

**Type key:** `morpho_spectral_harmonic`

Stretches the upper partials outward by remapping STFT frequency bins. Each output bin `k` draws from input bin `k / stretch_ratio`. With `stretch_ratio: 2.0`, the content normally at bin 100 now appears at bin 200 — effectively spreading the harmonic series wider than natural.

Ratios > 1 stretch partials apart (makes harmonics sharper and more widely spaced). Ratios < 1 compress them inward. At exactly 1.0, the output is unchanged.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `stretch_ratio` | 0.5–4.0 | 1.5 | How much to stretch the harmonic spacing |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Give a pitched sound an inharmonic, bell-like or metallic quality by spreading its overtones. Subtle values (1.2–1.5) work well for metallic shimmer; extreme values (3.0–4.0) create very foreign-sounding textures.

---

## Spectral: Inharmonic

**Type key:** `morpho_spectral_inharmonic`

Creates inharmonic spectra by mixing four copies of the magnitude spectrum, each remapped by a different ratio scaled by `inharmonic_factor`. The ratios are 1.0, 1.3, 2.7, and 4.5 (times the factor). This distributes energy to non-harmonic bin positions, destroying the harmonic series in favor of a deliberately inharmonic one.

The four layers are averaged together and recombined with the original phase.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `inharmonic_factor` | 1.0–3.0 | 1.5 | Scales all four remapping ratios. Higher = more inharmonic. |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Create bell, gong, or metallic percussion timbres from any source material. Works well on pitched sounds; on noise or percussion, it creates complex spectral textures.

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

**Type key:** `morpho_wagner_leitmotif`

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

**Type key:** `morpho_wagner_tristan`

Overlays the famous Tristan chord voicing on every Nth onset segment. The chord uses just-intonation ratios 4:5:6:7, expressed in semitones as 0, 3.86, 7.02, 9.69 — a harmonic 7th chord with natural (slightly flat) intonation. All four voices are summed and mixed under the original at a user-defined gain.

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `tristan_interval` | 2–8 | 3 | Apply the chord overlay to every Nth detected onset segment |
| `chord_gain_db` | −24–−6 dB | −12 | Volume of the chord overlay |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Add a Wagnerian harmonic weight to occasional segments. Use low `chord_gain_db` (−18 to −24 dB) for a subtle subliminal harmonic colour; −6 to −9 dB makes the chord clearly audible. Works on any source material — the chord will be transposed relative to whatever pitch is in the segment.

---

## Wagner: Endless Melody

**Type key:** `morpho_wagner_endless`

Inspired by Wagner's technique of seamlessly connecting melodic segments to create an unbroken melodic line. At each detected onset boundary, two things happen:
1. **Crossfade**: the audio fades out before the boundary and fades in after it, removing hard cuts and creating a smooth transition
2. **Passing tone**: a 50ms Hanning-windowed burst of the boundary region is pitch-shifted by ±1 semitone (randomly chosen) and added additively — a chromatic passing note connecting the two segments

| Parameter | Range | Default | What it does |
|-----------|-------|---------|-------------|
| `crossfade_ms` | 50–300 ms | 200 | Length of the fade-out and fade-in regions around each boundary |
| `dry_wet` | 0–100% | 80 | Dry/wet mix |

**Typical use:** Smooth out the transitions between short, choppy events or samples. Long `crossfade_ms` (200–300ms) creates flowing legato connections; short (50–80ms) just removes clicks while keeping the rhythm. The passing tone adds a brief chromatic grace note at each seam.

---

## Technical notes

### Plugin auto-discovery

Plugins live in `ProbabilisticMusic/plugins/`. When the server starts, `plugins/__init__.py` scans the directory and loads every `.py` file that defines `NAME`, `PARAMS`, and `process()`. New plugins appear in the editor automatically without any configuration change.

The `/plugins` endpoint returns the full schema as JSON — the editor uses this to generate parameter widgets on the fly.

### Processing requirements

Most plugins use `librosa`. The spectral bin-remapping plugins (Harmonic Stretch, Inharmonic) additionally require `scipy`, which is listed in `requirements.txt`. Both are installed by `pip install -r requirements.txt`.

### Performance

Some plugins call `librosa.effects.pitch_shift` many times per clip — particularly granular plugins with many short grains. On a 10-second clip at default settings:

| Plugin | Approximate processing time |
|--------|----------------------------|
| Saariaho: Spectral Freeze | ~0.5–1s |
| Xenakis: Granular Cloud | ~5–15s (many pitch_shift calls) |
| Penderecki: Cluster (8 voices) | ~3–5s |
| Spectral: Harmonic Stretch | ~0.3–0.5s |
| Xenakis: Stochastic Cloud | ~0.1–0.3s |

Granular and cluster plugins are the slowest because they call `pitch_shift` once per grain or voice. Use shorter `grain_ms` values or fewer voices if rendering is slow.

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
