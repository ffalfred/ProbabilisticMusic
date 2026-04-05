# Axes of Movement — Design Roadmap

## Context

The V2 Kalman engine has two sources of state variation:

1. **Marking-driven (structural)** — dynamics markings (pp, ff, sfz…) pull the posterior mean μ toward target values. This is deterministic and creates the large "expected" jumps in gain, brightness, etc.
2. **Process-noise-driven (micro-expressive drift)** — between markings, the AR(2) process + Q_base causes μ and σ to drift. This is the "breathing" of a real performer between score events.

Currently, **only (1) is audible** because the filter state is read exactly once per score event (at event trigger time), held constant for the note's entire duration, and only events produce sound. Between events the filter keeps running, but those intermediate state values are never heard.

Concrete consequence: with a score containing `pp` then `ff` and 2 audio events, you hear 2 note-level expressions separated by a dynamics jump. You do **not** hear continuous pitch drift, attack shape modulation, or reverb swelling within a note — even though the state is tracking those things invisibly.

The user asked whether that's correct for *all* dimensions, or whether some dims (pitch_dev_cents especially) should be continuously micro-varying.

This document records three implementation levels for introducing continuous/micro variation, from cheapest to most involved.

---

## Level 1 — Broaden per-event state draws

**What:** Keep the current "one sample per event" model, but widen Q_base on dimensions that should feel "alive" (pitch, timing, brightness) so their per-event sample has meaningful spread around μ.

**What it fixes:** Each note gets a more distinct expressive fingerprint. With σ_pitch ≈ 10-15 cents per event, consecutive identical notes already sound different.

**What it doesn't fix:** Within a single note, values are still frozen. A 3-second sustained note has the same pitch_dev_cents, same brightness, same reverb_wet from start to end.

**Implementation scope:**
- `config.yaml` — increase `Q_base[10]` (pitch_dev_cents) from 10 to 20-25.
- `config.yaml` — increase `Q_base[1]` (brightness), `Q_base[2]` (timing_offset_ms).
- Potentially adjust per-golem `Q_base` overrides for characters.
- No pipeline changes.

**Cost:** 5 minutes. Just tuning numbers.

**Use when:** Short/percussive notes, event-dense scores, user wants a clean "digital" expressivity.

---

## Level 2 — Render-time modulation on top of state

**What:** The filter still produces one state vector per event. At render time in `mixer.py`, **apply time-varying modulation across the note's duration** on dimensions that should breathe. Modulation sources:
- Low-frequency oscillator (LFO) — e.g. pitch drifts sinusoidally by ±3 cents at 0.5-2 Hz for the duration of the note (classic vibrato).
- Random walk — per-sample brightness wobbles ±5% over the note's lifetime.
- Envelope — reverb_wet swells 20% over the first half of the note.

**What it fixes:** Long notes stop feeling like static "stamped" samples. Pitch breathes, brightness opens, reverb swells. The note has internal shape.

**What it doesn't fix:** The note's *overall expressive character* is still set at trigger time — if the filter samples pitch_dev = -8 cents for this event, the note centres at -8 cents and wobbles around that. The wobble itself is not linked to the Kalman state between events.

**Implementation scope:**
- `mixer.py` — new helpers `_apply_vibrato(clip, sr, depth_cents, rate_hz)`, `_apply_timbral_breath(clip, sr, depth, rate)`, `_apply_reverb_swell(...)`.
- Per-dimension config in `config.yaml` declaring which dims get LFO modulation and their depth/rate ranges.
- Optionally: modulation depth driven by the event's sampled `drama` or `dynamic_center` so expressive peaks have more vibrato than calm passages.
- Plug modulation calls into the existing event loop in `mix_events()` at [src/mixer.py](ProbabilisticMusic/src/mixer.py).

**Cost:** 1-2 hours. Audio-side DSP, preserves the deterministic filter structure.

**Use when:** Sustained notes / vocal / string-like material / scores with slow pacing. User wants "breathing" notes.

---

## Level 3 — Continuous state-driven rendering

**What:** The Kalman filter already produces a continuous trajectory `state(t)` on a dense time grid (trace_step = 0.5s by default, plus marking times, plus event times — ~170 samples over 80s). **Make the renderer sample the state continuously across each note's duration**, not just at trigger.

A 3-second note starting at t=10s would read:
- state(t=10.0) → attack phase
- state(t=11.5) → sustain midpoint
- state(t=13.0) → release phase

interpolating the state vector along the note. Pitch drifts as the filter drifts. Brightness opens as μ_brightness climbs toward the next ff. Reverb_wet tracks the regime transition.

**What it fixes:** Audio is now a **direct sonification of the filter trajectory**. The μ line you see on the dimension timeline is literally audible. When markings pull the state, notes that are *sustaining* at that moment hear the transition happen inside them. The visual and the audio become one thing.

**What it doesn't fix:** Performance cost is higher — render must resample FX parameters per note across the note's duration, not once per event. Reverb/delay/filter plugins need per-note time-varying parameter evaluation.

**Implementation scope:**
- `interpreter.py` — expose the trace trajectory to the renderer (currently only enriched events are returned).
- `mixer.py` — event rendering loop reads `state(t)` by interpolating the trace at N points across note duration.
- `fx.py` — FX types that currently take scalar params need a time-varying variant or per-sub-block re-application.
- `envelope.py` — attack/release shape curves interact with state(t) modulation.
- Interpretive decision: **which dims are continuous vs per-event?** E.g. `attack_shape` and `release_shape` are inherently trigger-time only; `pitch_dev_cents`, `brightness`, `reverb_wet`, `filter_cutoff`, `dynamic_center`, `stereo_width`, `overdrive_drive` are candidates for continuous rendering. `gain_db` can be either (continuous = amplitude envelope; per-event = note-level dynamics).

**Cost:** 1-2 days. Largest change, but musically the most authentic. Matches how live performers continuously adjust tone and intonation while a note sounds.

**Use when:** Scores with long sustained material, ambient/drone work, tight coupling between filter state and audio result is musically important, or the user wants the visualization and audio to be "the same thing".

---

## Per-dimension recommendation matrix

| Dimension | Level 1 | Level 2 | Level 3 | Rationale |
|---|---|---|---|---|
| gain_db | ✓ | ✓ | ✓ | All three work; Level 3 → expressive envelope |
| brightness | ✓ | ✓✓ | ✓✓ | L2 vibrato-like timbral breath sounds great |
| timing_offset_ms | ✓ | — | — | Per-event only; drift during a note has no meaning |
| attack_shape | ✓ | — | — | Only matters at trigger moment |
| release_shape | ✓ | — | — | Only matters at release moment |
| reverb_wet | ✓ | ✓ | ✓✓ | L3 reverb swell is expressive |
| filter_cutoff | ✓ | ✓ | ✓✓ | L3 filter sweeps inside notes = classic |
| filter_resonance | ✓ | ✓ | ✓ | Any level |
| stereo_width | ✓ | ✓ | ✓✓ | L3 continuous panning is musical |
| overdrive_drive | ✓ | — | ✓ | Skip L2, L3 good for evolving distortion |
| pitch_dev_cents | ✓ | ✓✓ | ✓✓ | L2 vibrato is the classical pitch case |
| dynamic_center | — | — | ✓ | Slow-moving baseline; only L3 makes sense |

---

## Recommended approach

**Phase A (now):** Level 1 everywhere. Tune `Q_base` to taste. Cheap wins.

**Phase B (later):** Level 2 for `pitch_dev_cents` (vibrato), `brightness` (timbral breath), optionally `reverb_wet` (swell). This is the classical "performer expressivity" layer and adds enormous realism for ~1-2 hours of work.

**Phase C (eventually):** Level 3 for `filter_cutoff`, `dynamic_center`, `stereo_width`, and possibly `reverb_wet`/`brightness` if Phase B's LFO approach feels too mechanical. This locks audio to the visualization and gives the engine its signature sound.

## Implementation notes to self

- Level 2's LFO should be **seeded by the event's random-state hash** so identical re-renders give the same vibrato shape.
- Level 3's trace-to-note interpolation should be linear, not nearest-neighbour — the trace density (0.5s by default) is coarser than audio samples.
- For Level 3, consider exposing a per-golem `continuous_dims` list so the user chooses which dims render continuously vs discretely. Default lists per character preset.
- The dimension timeline UI already shows trace density; could annotate which portions of the timeline a given note actually "hears" (shaded segments matching note durations).

---

## Files involved across all levels

| File | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| `config.yaml` | ✓ | ✓ | ✓ |
| `src/mixer.py` | — | ✓ | ✓ |
| `src/fx.py` | — | — | ✓ |
| `src/envelope.py` | — | — | ✓ |
| `src/interpreter.py` | — | — | ✓ |
| `editor/static/js/viz-panel.js` | — | — | optional (show note-coverage shading) |
