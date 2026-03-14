# V2 Model Design — Expressive Interpretation Engine

## Overview

V2 sits on top of the existing V1 audio engine. It does not replace it.
V1 renders audio from a score. V2 decides *how* that score is interpreted
before V1 renders it — transforming symbolic markings into concrete expressive
parameter values.

Every run of the same score produces a different but musically coherent
rendering. The variation emerges from the model's own history during playback,
not from random noise.

---

## Dynamic Markings

The following 13 markings are supported:

### Dynamic ladder (ordered soft to loud)
- `ppp` — pianississimo
- `pp`  — pianissimo
- `p`   — piano
- `mp`  — mezzo-piano
- `mf`  — mezzo-forte
- `f`   — forte
- `ff`  — fortissimo
- `fff` — fortississimo

### Expressive markings (instantaneous events)
- `sfz`      — sforzando: sudden sharp accent, casts a short recovery shadow over next 1-2 events
- `fp`       — forte-piano: loud then immediately soft, single event
- `subito_p` — sudden jump to soft, no transition, no shadow
- `subito_f` — sudden jump to loud, no transition, no shadow

### Gradual markings (have a duration)
- `cresc`   — crescendo: gradual increase over a defined time span
- `decresc` — decrescendo: gradual decrease over a defined time span

---

## Core Idea

A score marking does not have an absolute output value.
Its value depends on:

1. The last N markings written in the score (symbolic history)
2. The last N values actually rendered (performance history) — joint mode only
3. Other contextual parameters (tempo, phrase position, piece position, event density)

This is modelled as a **Higher-order Markov chain on the joint state**
(symbolic marking, rendered output), with **multivariate Gaussian emissions**.

---

## Formal Definition

### State at time t

```
S(t) = (m(t), o(t))
```

Where:
- `m(t)` — the symbolic marking at time t, read from score
- `o(t)` — the vector of output values actually rendered at time t

### Output vector

```
o(t) = [gain_db, brightness, timing_offset_ms, attack_shape, reverb_wet]
```

Each component is a continuous scalar. More components can be added later.

### Emission distribution

At each step, the model draws o(t) from a multivariate Gaussian:

```
o(t) ~ N(μ, Σ)
```

Where μ and Σ are conditioned on the context window:

```
μ, Σ = f(
    m(t),                        # current score marking
    m(t-1), ..., m(t-N),        # previous N score markings
    o(t-1), ..., o(t-N),        # previous N rendered output vectors (joint mode only)
    context(t)                   # additional context
)
```

### Covariance structure

User-selectable in config.yaml:

**Diagonal** — parameters vary independently. Simpler, easier to hand-craft.

**Full** — parameters co-vary. Encodes musical correlations such as
"loud passages tend to also be spectrally brighter." Richer but requires
specifying correlation coefficients between parameter pairs in the
transition table.

### Order N

User-defined in config.yaml. Start with N=2.
N=3 is probably the maximum that remains musically interpretable.

---

## Context Variables

Computed deterministically from the score at parse time. Do not vary between runs.

```
context(t) = [
    tempo_direction,      # accelerating (-1) / stable (0) / decelerating (+1)
                          # computed from rubato/tempo curves in score
    phrase_position,      # 0.0 (phrase beginning) to 1.0 (phrase end)
                          # inferred automatically from event structure
    piece_position,       # 0.0 (piece beginning) to 1.0 (piece end)
                          # always computable from total duration
    event_density,        # events per second in a local window around t
                          # computed from event list
]
```

---

## Transition Types

### Continuous transitions
- Crescendo, decrescendo, gradual dynamic changes
- Emission draws from a narrow Gaussian — small variance
- Output changes smoothly relative to previous output

### Discontinuous transitions
- `subito_f`, `subito_p` — sudden jumps
- Emission draws from a wide Gaussian — large variance
- Output is not constrained by previous output history
- No shadow forward

### Shadow transitions
- `sfz` — instantaneous accent with recovery shadow
- The sfz event itself draws from a high-gain, high-brightness emission
- The next 1-2 events receive a recovery bias: gain and brightness are
  pulled slightly below what they would otherwise be, as if the performer
  is withdrawing after the outburst
- Shadow strength and length are defined per-entry in the transition table

The score marking itself determines which type applies.
The transition table encodes the type for each entry.

---

## Phrase Boundaries

Phrases are inferred automatically from the event structure for now.
In a future version they will also be definable manually in score.yaml.

### Phrase boundary behaviour (user-defined in config.yaml)

**reset** — Markov history is wiped at each phrase boundary.
Each phrase is interpreted independently. More predictable, more structured.

**continuous** — history accumulates across the whole piece.
A loud phrase casts a shadow into the next. More organic, longer-range coherence.

---

## Cold Start

At the beginning of the piece the Markov history is empty.
For the first N steps, history is initialised with neutral default values:

- Default marking: `mf`
- Default output vector: mid-range values for all parameters

This ensures the first N events are interpreted as if following a neutral
mezzo-forte passage. After N steps the real history takes over.

The cold start default values are configurable in config.yaml so they
can be changed in the future without touching the code.

---

## Sforzando Recovery — Detail

`sfz` is encoded in the transition table with two additional fields:

```yaml
sfz_recovery:
  length: 2           # number of events affected after the sfz
  gain_bias: -4.0     # dB subtracted from normal emission mean for recovery events
  brightness_bias: -0.15  # subtracted from normal brightness mean
```

The recovery bias is applied additively on top of whatever the next
transition's emission would normally produce. It fades linearly across
the recovery length — full bias on event +1, half bias on event +2.

---

## File Structure

```
project/
│
├── config.yaml                 # user-facing mode selector
├── score.yaml                  # score — add dynamic markings section
│
├── src/                        # v1 engine — unchanged
│   ├── parser.py
│   ├── sample_engine.py
│   ├── scheduler.py
│   ├── envelope.py
│   ├── fx.py
│   ├── mixer.py
│   └── renderer.py
│
├── v2/
│   ├── transition_table.yaml   # expert prior parameters — fill this in
│   ├── context.py              # computes context vector from score
│   ├── emission.py             # samples o(t) from Gaussian given context
│   ├── markov_symbolic.py      # conditions only on score markings
│   ├── markov_joint.py         # conditions on markings + rendered outputs
│   ├── interpreter.py          # entry point: score → interpreted parameter stream
│   └── bayes_update.py         # optional: updates priors from MAESTRO data
│
└── main.py                     # reads config, routes to v1 or v2
```

---

## config.yaml

```yaml
# --- Engine version ---
# options: v1, v2
engine: v2

# --- Markov mode (v2 only) ---
# symbolic: conditions only on previous score markings
# joint:    conditions on previous markings AND previous rendered outputs
markov_mode: joint

# --- Markov order (v2 only) ---
# how many previous steps to consider — recommended: start with 2
markov_order: 2

# --- Covariance structure (v2 only) ---
# diagonal: parameters vary independently
# full:     parameters co-vary (requires correlation coefficients in transition table)
covariance: diagonal

# --- Phrase boundary behaviour (v2 only) ---
# reset:      Markov history resets at each phrase boundary
# continuous: history accumulates across the whole piece
phrase_boundary: reset

# --- History decay weight (joint mode only) ---
# how strongly older history influences current emission
# 1.0 = all steps weighted equally
# 0.5 = each step half as influential as the previous one
history_decay: 0.7

# --- Cold start defaults (v2 only) ---
cold_start_marking: mf
cold_start_outputs:
  gain_db: -12.0
  brightness: 0.5
  timing_offset_ms: 0.0
  attack_shape: 0.5
  reverb_wet: 0.3

# --- Output files ---
# each run writes a new numbered file — output/output_<score>_<base>_001.wav etc.
# set seed to an integer to reproduce a specific run, null for random
seed: null

# --- V1 stochastic parameters ---
# which v1 parameters should vary randomly within a range each run
v1_stochastic:
  speed:    {enabled: true,  std: 0.05}
  gain_db:  {enabled: true,  std: 1.0}
  timing:   {enabled: false, std: 0.0}

# --- Bayesian update (v2 only) ---
# false: use expert priors only
# true:  update priors with MAESTRO data
bayesian_update: false
maestro_path: null
```

---

## Score Changes for V2

Add a `dynamics` section to score.yaml. Each entry has a time, a marking,
and optionally a duration (for cresc/decresc) and phrase label.

```yaml
dynamics:
  - t: 0.0
    marking: p

  - t: 10.0
    marking: mp

  - t: 19.0
    marking: f

  - t: 21.0
    marking: sfz

  - t: 24.0
    marking: subito_p

  - t: 30.0
    marking: cresc
    duration: 8.0     # grows from current level to next marking over 8 seconds

  - t: 38.0
    marking: ff
```

Phrase labels are optional for now — the engine infers phrase boundaries
automatically. They can be added manually later:

```yaml
  - t: 0.0
    marking: p
    phrase: 1
```

---

## transition_table.yaml — How to Fill It In

This file encodes your musical intuitions as probability distributions.
For each transition (previous marking → current marking) you define:

- `mean`  — the expected output value for this transition
- `std`   — how much variation is allowed around that mean
- `type`  — continuous / discontinuous / shadow

**Higher std = more expressive freedom. Lower std = tighter, more controlled.**

A large jump (p → f) should have a more extreme mean and wider std
than a small jump (mp → f). A subito should have the widest std of all.

For `sfz`, also fill in the `sfz_recovery` block.

If `covariance: full` is set in config.yaml, also fill in the
`correlations` block for each transition, specifying how strongly
each pair of output parameters moves together (range: -1.0 to 1.0).

```yaml
# transition_table.yaml
# Fill in mean and std for each transition.
# The values below are starting suggestions — adjust to taste.
# All gain_db values are relative offsets from a nominal 0dB reference.

transitions:

  # --- Small steps up ---
  p_to_mp:
    type: continuous
    gain_db:          {mean: -2.0,  std: 1.0}
    brightness:       {mean:  0.1,  std: 0.05}
    timing_offset_ms: {mean:  5.0,  std: 3.0}
    attack_shape:     {mean:  0.1,  std: 0.05}
    reverb_wet:       {mean: -0.05, std: 0.02}

  mp_to_mf:
    type: continuous
    gain_db:          {mean: -2.0,  std: 1.0}
    brightness:       {mean:  0.1,  std: 0.05}
    timing_offset_ms: {mean:  5.0,  std: 3.0}
    attack_shape:     {mean:  0.1,  std: 0.05}
    reverb_wet:       {mean: -0.05, std: 0.02}

  mf_to_f:
    type: continuous
    gain_db:          {mean: -3.0,  std: 1.5}
    brightness:       {mean:  0.15, std: 0.07}
    timing_offset_ms: {mean:  8.0,  std: 4.0}
    attack_shape:     {mean:  0.15, std: 0.07}
    reverb_wet:       {mean: -0.05, std: 0.02}

  f_to_ff:
    type: continuous
    gain_db:          {mean: -3.0,  std: 1.5}
    brightness:       {mean:  0.15, std: 0.07}
    timing_offset_ms: {mean:  8.0,  std: 4.0}
    attack_shape:     {mean:  0.15, std: 0.07}
    reverb_wet:       {mean: -0.05, std: 0.02}

  # --- Large steps up ---
  p_to_f:
    type: continuous
    gain_db:          {mean: -1.0,  std: 2.0}
    brightness:       {mean:  0.25, std: 0.12}
    timing_offset_ms: {mean: 20.0,  std: 8.0}
    attack_shape:     {mean:  0.3,  std: 0.1}
    reverb_wet:       {mean: -0.1,  std: 0.04}

  pp_to_ff:
    type: continuous
    gain_db:          {mean:  0.0,  std: 3.0}
    brightness:       {mean:  0.4,  std: 0.15}
    timing_offset_ms: {mean: 30.0,  std: 12.0}
    attack_shape:     {mean:  0.4,  std: 0.15}
    reverb_wet:       {mean: -0.15, std: 0.05}

  # --- Small steps down ---
  f_to_mf:
    type: continuous
    gain_db:          {mean:  2.0,  std: 1.0}
    brightness:       {mean: -0.1,  std: 0.05}
    timing_offset_ms: {mean: -5.0,  std: 3.0}
    attack_shape:     {mean: -0.1,  std: 0.05}
    reverb_wet:       {mean:  0.05, std: 0.02}

  mf_to_mp:
    type: continuous
    gain_db:          {mean:  2.0,  std: 1.0}
    brightness:       {mean: -0.1,  std: 0.05}
    timing_offset_ms: {mean: -5.0,  std: 3.0}
    attack_shape:     {mean: -0.1,  std: 0.05}
    reverb_wet:       {mean:  0.05, std: 0.02}

  # --- Large steps down ---
  f_to_p:
    type: continuous
    gain_db:          {mean:  4.0,  std: 2.0}
    brightness:       {mean: -0.25, std: 0.12}
    timing_offset_ms: {mean: -15.0, std: 8.0}
    attack_shape:     {mean: -0.3,  std: 0.1}
    reverb_wet:       {mean:  0.1,  std: 0.04}

  ff_to_pp:
    type: continuous
    gain_db:          {mean:  5.0,  std: 3.0}
    brightness:       {mean: -0.4,  std: 0.15}
    timing_offset_ms: {mean: -25.0, std: 12.0}
    attack_shape:     {mean: -0.4,  std: 0.15}
    reverb_wet:       {mean:  0.15, std: 0.05}

  # --- Sudden changes ---
  any_to_subito_f:
    type: discontinuous
    gain_db:          {mean:  0.0,  std: 4.0}
    brightness:       {mean:  0.5,  std: 0.2}
    timing_offset_ms: {mean:  0.0,  std: 2.0}
    attack_shape:     {mean:  0.9,  std: 0.1}
    reverb_wet:       {mean: -0.2,  std: 0.08}

  any_to_subito_p:
    type: discontinuous
    gain_db:          {mean:  5.0,  std: 4.0}
    brightness:       {mean: -0.5,  std: 0.2}
    timing_offset_ms: {mean:  0.0,  std: 2.0}
    attack_shape:     {mean: -0.5,  std: 0.1}
    reverb_wet:       {mean:  0.2,  std: 0.08}

  # --- Sforzando ---
  any_to_sfz:
    type: shadow
    gain_db:          {mean: -0.5,  std: 1.5}
    brightness:       {mean:  0.6,  std: 0.1}
    timing_offset_ms: {mean:  0.0,  std: 2.0}
    attack_shape:     {mean:  1.0,  std: 0.05}
    reverb_wet:       {mean: -0.1,  std: 0.04}
    sfz_recovery:
      length: 2
      gain_bias: -4.0
      brightness_bias: -0.15

  # --- Forte-piano ---
  any_to_fp:
    type: discontinuous
    gain_db:          {mean: -1.0,  std: 2.0}
    brightness:       {mean:  0.4,  std: 0.15}
    timing_offset_ms: {mean:  0.0,  std: 3.0}
    attack_shape:     {mean:  0.8,  std: 0.1}
    reverb_wet:       {mean:  0.1,  std: 0.05}
    # fp immediately collapses to soft after the attack —
    # handle in emission.py: apply a fast gain_db ramp back to p level
    # within the same event duration

  # --- Crescendo / Decrescendo ---
  # These are gradual and span a duration defined in the score.
  # The emission here defines the *rate* of change, not a single value.
  cresc:
    type: continuous
    gain_db_per_sec:  {mean:  1.5,  std: 0.3}
    brightness_per_sec: {mean: 0.03, std: 0.01}

  decresc:
    type: continuous
    gain_db_per_sec:  {mean: -1.5,  std: 0.3}
    brightness_per_sec: {mean: -0.03, std: 0.01}
```

---

## Runtime Flow

```
1. Read config.yaml → determine engine, markov_mode, markov_order,
   covariance, phrase_boundary, history_decay, seed, cold start defaults

2. Parse score → extract events, marking sequence, context vectors

3. If engine == v1:
   → apply v1_stochastic perturbations if enabled
   → pass score directly to v1 renderer
   → output is near-deterministic, same seed = same output

4. If engine == v2:
   a. Initialise Markov history with cold start defaults (N steps)
   b. Infer phrase boundaries from event structure
   c. For each event in chronological order:

      If markov_mode == symbolic:
        - context = (m(t-N)...m(t), context(t))
        - history tracks score markings only

      If markov_mode == joint:
        - context = (m(t-N)...m(t), o(t-N)...o(t), context(t))
        - history tracks both markings and rendered outputs
        - older history weighted by history_decay^n

      d. Look up transition in transition_table.yaml
      e. Sample o(t) ~ N(μ, Σ) from emission distribution
      f. If previous event was sfz and we are within recovery length:
         apply recovery bias to this emission
      g. Update history with (m(t), o(t))
      h. If phrase_boundary == reset and t is a phrase boundary:
         wipe history, reinitialise with cold start defaults
      i. Pass o(t) to v1 engine as expressive parameters for this event

5. V1 engine renders audio using interpreted parameters
6. Write output/output_<scorename>_<basename>_<NNN>.wav
```

---

## Output Naming

Output files are named automatically:

```
output/output_<score_name>_<base_name>_<NNN>.wav
```

Where:
- `score_name` — stem of the score file (e.g. `score` from `score.yaml`)
- `base_name`  — stem of the base audio file (e.g. `base` from `base.wav`)
- `NNN`        — zero-padded run counter, incrementing automatically

Example: `output/output_score_base_001.wav`

If a seed is set in config.yaml, the same seed always produces the same
numbered file with identical content.

---

## Key Difference Between Markov Modes

**Symbolic markov** — each run varies because of random draws from
emission distributions, but the context window only sees score markings.
Two runs with the same score see the same context, just draw different values.
Variation is independent between runs.

**Joint markov** — each run varies AND the context window sees what was
actually rendered in previous steps. An early loud draw makes subsequent
emissions shift. The piece develops its own performance personality during
each run. Variation is cumulative and self-reinforcing.

---

## What V2 Does NOT Do

- It does not generate events — the score is fixed
- It does not change which samples are played or when
- It does not replace V1 — it feeds into it
- It does not require data to run — expert priors are sufficient

---

## Open Questions — Deferred

- **Full covariance** — correlation coefficients between output parameters
  per transition. Implement after diagonal mode is working.
- **Bayesian update with MAESTRO** — deferred to after expert priors are tuned.
- **Manual phrase labels in score** — currently inferred, manual override later.
- **Gaussian Process for continuous curves between markings** — deferred to v3.