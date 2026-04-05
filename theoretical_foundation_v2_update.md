# Theoretical Foundation — V2 Engine Update

> This document extends `theoretical_foundation_v2.md`.
> That document covers the mathematical derivation of the Kalman filter, AR(2)
> augmentation, window observations, drama/volatility Q adaptation, and the
> fuzzy future prior.
>
> This document covers everything that was added after that foundation:
> the Random Walk golem type, non-Gaussian sampling distributions, golem
> envelopes and blending, per-dimension AR coefficients, the RW scatter hybrid,
> and the exact drama and future-pull formulas as actually implemented.

---

## 1. Two Golem Types

The original foundation described a single model: a Kalman filter with AR(2)
momentum. The current engine supports two fundamentally different process
models, called **golem types**:

```
GOLEM TYPES
───────────────────────────────────────────────────────────────────────
  type: kalman         (default)
    Maintains a Gaussian belief over expressive state.
    AR(2) momentum + observation update.
    Optimal under Gaussian assumptions.
    Well-suited for: structured, score-aware interpretation.

  type: random_walk
    Expressive state evolves as unconstrained Brownian motion.
    No score observations. No Kalman update.
    Well-suited for: free improvisation character, dream-like passages.
```

The choice of type is made **per golem**, not globally. At each score event,
the engine resolves which type governs:

```python
def _resolve_golem_type(t, golems):
    active = [g for g in golems if g['from'] <= t < g['to']]
    types  = {g.get('type', 'kalman') for g in active}
    # Only pure-RW regions use the RW path
    return 'random_walk' if types == {'random_walk'} else 'kalman'
```

If a Kalman and a Random Walk golem overlap, the Kalman path is used.
The Random Walk path only activates when every active golem at time t
is explicitly of type `random_walk`. This is a safety choice: the Kalman
filter has a defined state to propagate; a mixed region falls back to it.

---

## 2. Golem Envelope — Weight, Fade In, Fade Out

Each golem in the score has an envelope that controls how much influence
it exerts over time:

```yaml
golems:
  - from: 0
    to: 60
    character: lyrical
    weight: 1.0
    fade_in: 4.0     # ramp up over first 4 seconds
    fade_out: 4.0    # ramp down over last 4 seconds
```

The effective weight at time t is:

```
              ┌─────────────────────────────────────────────┐
              │                                             │
weight        │          ╭──────────────────────╮          │
              │         ╱                        ╲         │
              │        ╱   weight = 1.0           ╲        │
              │       ╱                            ╲       │
              │──────╱                              ╲──────│
              │  fade_in                        fade_out   │
              │                                             │
              └──────────────────────────────────────────── t
                   from                                  to
```

Formally:

```
w_eff(t) = weight
           × ramp_in(t)    if (t - from) < fade_in
           × ramp_out(t)   if (to - t)   < fade_out

where:
  ramp_in(t)  = (t - from) / fade_in
  ramp_out(t) = (to - t)   / fade_out
```

The ramps are linear. `weight` is the peak value (default 1.0).

### 2.1 Why envelopes matter

Without fade envelopes, switching between golems is instantaneous — the
expressive character snaps at the golem boundary. Fade envelopes allow
characters to **bleed into each other**, creating smooth transitions that
feel more like a performer gradually shifting their interpretive stance.

```
Without fades:

  t=0─────────────────30─────────────────60
  |   dramatic (w=1)  │   lyrical (w=1)  │
                      ↑
                   hard snap

With fades (4s each):

  t=0─────────────────26──30──34──────────60
  |   dramatic (w=1)  │blend│  lyrical (w=1) │
                      ╱      ╲
                  dramatic      lyrical
                  fading out    fading in
```

During the overlap window both golems are active and their parameters
are blended by normalised weight (see Section 3).

---

## 3. Multi-Golem Blending

Multiple golems can be active simultaneously. The engine blends their
parameters using normalised effective weights before constructing the
filter matrices.

### 3.1 Kalman blending

For scalar parameters (A1, A2, Q_scale, R_scale, λ, obs_weight):

```
p_blended = Σ_i  w_i · p_i  /  Σ_i w_i
```

For string parameters (drama_curve, sample_dist): the dominant golem's
value wins (highest normalised weight).

For per-dimension A1/A2 arrays: element-wise weighted average.

```
Example — two overlapping Kalman golems at t=32:

  golem A (dramatic): w_eff=0.3,  A1=0.8, Q_scale=2.0
  golem B (lyrical):  w_eff=0.7,  A1=0.6, Q_scale=0.5

  total_w = 1.0

  A1_blended    = 0.3×0.8 + 0.7×0.6 = 0.24 + 0.42 = 0.66
  Q_scale_blend = 0.3×2.0 + 0.7×0.5 = 0.60 + 0.35 = 0.95
  drama_curve   = lyrical's value ('linear')   ← dominant by weight
```

### 3.2 Random Walk blending

The same principle applies: step_size and drift vectors are element-wise
weighted averages. Correlation matrices cannot be blended without
non-trivial Riemannian interpolation — the dominant golem's matrix is used.

### 3.3 Inline parameter overrides

A golem in the score YAML can override any character-level parameter
directly, without defining a new named character:

```yaml
golems:
  - from: 0
    to: 30
    character: lyrical      # base preset
    A1: 0.85                # override just this
    Q_scale: 0.3            # and this
    distribution: laplace   # and sampling distribution
```

This allows fine-grained control without proliferating named characters.

---

## 4. Per-Dimension AR Coefficients

The original foundation treats A1 and A2 as scalars multiplied by the
identity matrix. This is now extended: A1 and A2 can be specified
**per dimension**, giving each expressive dimension its own inertia.

```yaml
# In a custom character definition:
A1_dims: [0.8, 0.6, 0.4, 0.7, 0.5]
A2_dims: [0.1, 0.2, 0.1, 0.15, 0.1]
#         gain  bright  timing  attack  reverb
```

This allows, for example, gain to have high inertia (changes slowly,
sluggish) while timing has lower inertia (changes quickly, unstable).

Internally, the diagonal matrices are built as:

```
A1_mat = diag(A1_dims)    # shape (d, d)
A2_mat = diag(A2_dims)    # shape (d, d)

F = [ A1_mat   A2_mat ]
    [  I_d        0   ]
```

When `A1_dims` is not provided, the scalar A1 is broadcast to all
dimensions (original behaviour preserved).

---

## 5. Non-Gaussian Sampling Distributions

The Kalman filter always maintains a **Gaussian belief** (mean μ, covariance Σ).
However, the sample drawn from that belief at each event can use a
non-Gaussian distribution whose spread matches the posterior variance.

This is the critical architectural choice: the Kalman update is always
Gaussian; the sampling is not required to be.

### 5.1 Why non-Gaussian sampling

Gaussian samples are unimodal, symmetric, and tail-light. Real
performance behaviour includes:

- Heavy tails (sudden jumps in expression)
- Bimodal tendencies (a performer swings between two expressive poles)
- Uniform-like uncertainty (all values equally plausible in a range)
- Occasional large outliers on top of a normal background (mixture)

### 5.2 Available distributions

All distributions are parameterised by σ — the posterior standard
deviation at each dimension. The σ is the same regardless of distribution.

```
DISTRIBUTION    NAME IN UI    BEHAVIOUR
────────────────────────────────────────────────────────────────────────
gaussian        Natural       Standard bell curve. Baseline.
laplace         Edgy          Sharper peak, heavier tails than Gaussian.
                              More sudden jumps, less moderate values.
cauchy          Wild          Very heavy tails, no defined variance.
                              Occasional extreme outliers. Clipped at ±5σ.
uniform         Even          All values in [-√3·σ, +√3·σ] equally likely.
                              No preference for the posterior mean.
beta            Curved        Symmetric beta(2,2), peaks at mean, bounded.
                              Smoother than Gaussian, never extreme.
student_t       Heavy         Student-t with df degrees of freedom.
                              At df=3 very heavy tails; df→∞ approaches Gaussian.
bimodal         Bipolar       Two mirrored Gaussians at ±0.75σ.
                              Performer swings between two expressive poles.
mixture         Bursting      Gaussian base + rare large spikes (mixture_p % of events).
                              Normal most of the time; occasional outbursts.
```

The normalisation convention for all distributions: E[noise²] ≈ σ² per
dimension. This ensures the spread is comparable to the Gaussian case
regardless of which distribution is chosen.

### 5.3 How sampling works

For the Gaussian case, the posterior is sampled directly as a
multivariate normal (preserving correlations across dimensions):

```python
x_sample = rng.multivariate_normal(mu, Sigma)
```

For all other distributions, independence is assumed across dimensions
and per-dimension σ is extracted from the diagonal of Σ:

```python
std   = sqrt(diag(Sigma))                    # shape (d,)
noise = sample_noise(dist, scale=std)        # shape (d,)
x_sample = mu + noise
```

This is an approximation: off-diagonal covariances are ignored. The
justification is that the expressive dimensions are largely independent
in musical performance, and non-Gaussian distributions do not have a
standard multivariate form that preserves their tail properties.

---

## 6. The Random Walk Golem — Full Model

### 6.1 Basic Brownian motion

The simplest RW step: the state diffuses by additive noise each event.

```
x(t) = x(t-1) + noise(t)

noise(t) ~ dist(0, step_size)
```

Where `step_size ∈ ℝ^d` sets the spread independently per dimension.

There is no observation update, no score awareness. The state wanders
freely in all directions.

### 6.2 Ornstein-Uhlenbeck: mean reversion

A mean-reverting term pulls the state back toward zero:

```
x(t) = x(t-1) + drift - mr · x(t-1) + noise(t)
        ────────   ──────  ─────────────  ────────
        previous   trend   reversion      random
        state             force           step
```

Where `mr ∈ [0, 1]` per dimension (mean_reversion or mr_dims).

The O-U dynamics:
- `mr = 0`: pure Brownian motion, state wanders without limit
- `mr = 0.15`: gentle pull toward zero, characteristic reversion timescale ~6 events
- `mr = 1.0`: state snaps to zero each step (degenerate)

```
Intuition — mean_reversion as memory decay:

  A performer starts loud. With mean reversion, the state is
  gradually pulled toward the neutral point even without a
  dynamic marking instructing it. Like a rubber band — the further
  the state departs from centre, the stronger the pull back.

  Without mean reversion: the performer may stay loud indefinitely.
  With mean reversion: the performance returns to a resting level
  unless actively pushed outward by the drift term.
```

### 6.3 Drift

A directional drift shifts the expected trajectory over time:

```
x(t) = x(t-1) + drift + ...

drift ∈ ℝ^d
```

A positive drift on dimension 0 (gain_db) makes the performance
gradually get louder over time, independent of score markings.

### 6.4 Boundary handling

The RW state can reach physical limits (e.g. gain_db > +6 or < -40).
Two boundary modes:

```
CLIP:
  Values outside [lo, hi] are clamped to the boundary.
  The state piles up at the edge — like a wall.

REFLECT:
  Values outside [lo, hi] are reflected back in.
  The state bounces off boundaries — like a mirror.

  x = 2·lo - x   (if x < lo)
  x = 2·hi - x   (if x > hi)
```

Reflect is preferable for RW golems to avoid the state getting stuck
at an extreme value.

### 6.5 Correlated noise

By default, each dimension's noise is sampled independently. Optionally,
a correlation matrix defines how dimensions co-vary:

```yaml
# A performer who tends to be both louder AND brighter simultaneously:
correlation:
  - [1.0, 0.7, 0.0, 0.0, 0.0]   # gain_db
  - [0.7, 1.0, 0.0, 0.0, 0.0]   # brightness
  - [0.0, 0.0, 1.0, 0.0, 0.0]   # timing
  - [0.0, 0.0, 0.0, 1.0, 0.0]   # attack
  - [0.0, 0.0, 0.0, 0.0, 1.0]   # reverb
```

Correlated noise is generated via Cholesky decomposition:

```
L = cholesky(Corr)
noise = L · (white_noise × step_size)

where white_noise ~ dist(0, 1)^d
```

If Cholesky decomposition fails (matrix not positive definite), the
engine falls back to independent sampling silently.

### 6.6 Breathing walk

A sinusoidal drift component creates a slow periodic oscillation in
the expressive state:

```
drift(t) += step_size × 0.6 × sin(2π · t / breath_period)
```

With `breath_period = 8.0` seconds, the expression oscillates with an
8-second cycle. This is not derived from the score — it is an intrinsic
periodic character imposed on the passage.

---

## 7. RW Scatter — Kalman-Noise Hybrid

A Kalman golem can have its posterior samples augmented with additional
noise controlled by the `rw_scatter` parameter (range [0, 1]):

```
x_sample = kalman_posterior_sample + rng.normal(0, std × rw_scatter)

where std = sqrt(diag(Sigma))
```

At `rw_scatter = 0`: pure Kalman posterior (default behaviour).
At `rw_scatter = 1`: posterior sample plus a full additional σ of noise.

Musically: this relaxes the Kalman filter's confidence in its own
posterior. At high scatter, the performance becomes more erratic —
the Kalman's disciplined tracking of the score is contaminated with
random deviation. The filter still runs, but its output is treated as
a rough guide rather than a precise model.

```
When to use rw_scatter:

  A passage where the score's dynamic structure matters (use Kalman)
  but the performer is emotionally volatile (scatter > 0) is a common
  case. The filter provides the broad shape; scatter provides the jitter.

  rw_scatter = 0.0  →  precise, score-following
  rw_scatter = 0.3  →  slightly loose, occasional surprises
  rw_scatter = 0.8  →  barely following the score, character-driven
  rw_scatter = 1.0  →  Kalman structure present but overwhelmed by noise
```

---

## 8. Observation Weight (obs_weight)

The `obs_weight` parameter scales how closely this golem follows the
score's dynamic markings, without changing any other model parameter.

Mechanically, it divides the observation noise covariance R by obs_weight:

```
R_effective = R × R_scale / max(obs_weight, 0.01)
```

Since dividing R by a large number makes observations more trusted
(see foundation §3.3), high obs_weight means strong score-following.

```
obs_weight = 0.0   →  score markings ignored entirely (R → ∞)
obs_weight = 1.0   →  default trust in markings
obs_weight = 2.0   →  very literal, disciplined score-following

Musical analogy:
  obs_weight low:   a performer who takes broad interpretive liberties
  obs_weight high:  a performer who executes the written dynamics precisely
```

This is distinct from `R_scale`, which scales the entire R matrix
including the physics of the window observation. `obs_weight` is a
purely musical control: "how much does this character care about the score?"

---

## 9. Drama Formula — Exact Implementation

The theoretical foundation describes drama conceptually. The exact
four-component formula, as implemented in `src/drama.py`:

```
drama(i) = w_dist · distance(i)
         + w_str  · structural(i)
         + w_cont · contrast(i)
         + w_bnd  · boundary(i)
```

Where:

```
distance(i)   = |rank(m_i) - rank(m_{i-1})| / 7
                ← jump in dynamic level from previous marking
                ← 0 if same level, 1 if ppp→fff

structural(i) = 1  if m_i ∈ {sfz, fp, subito_p, subito_f}
                0  otherwise
                ← binary: is this marking an emphatic structural event?

contrast(i)   = |rank(m_i) - local_mean| / 7
                ← how unusual is this marking in its neighbourhood?
                ← local window W=3 markings on each side

boundary(i)   = 1  if marking i is at a phrase boundary
                0  otherwise
```

Default weights:
```
w_dist = 0.4   w_str = 0.3   w_cont = 0.2   w_bnd = 0.1
```

These weights are tunable via `config.yaml` under `v2.drama_weights`.

The ranking ladder:

```
ppp=0  pp=1  p=2  mp=3  mf=4  f=5  ff=6  fff=7
Structural / gradual markings (sfz, cresc, etc.) → treated as 3.5 (mid-range)
```

---

## 10. Future Pull Formula — Exact Implementation

The future pull at marking i is a decaying weighted sum over the next
K markings ahead:

```
future_pull(i) = Σ_{k=1}^{K}  λᵏ · salience(i+k) · enc(m(i+k))

where:
  salience(j) = drama(j)              (same importance formula, different direction)
  enc(m)      = rank(m) / 7           (normalised rank, ∈ [0, 1])
  λ           = familiarity ∈ (0,1)   (how far ahead the performer knows the score)
  K           = look-ahead window     (default 10 markings)
```

```
Interpretation:

  λ high (0.9) — the performer knows the piece well. Events 8-10
  markings ahead still influence the current state. Like a professional
  who has memorised the score.

  λ low (0.3) — the performer is sight-reading. Only the next 1-2
  markings ahead meaningfully influence the current state.

  Example with λ = 0.7, K = 4:

    i+1: salience=0.2, enc=0.7  →  0.7¹ × 0.2 × 0.7 = 0.098
    i+2: salience=0.8, enc=1.0  →  0.7² × 0.8 × 1.0 = 0.392  ← climax ahead
    i+3: salience=0.1, enc=0.4  →  0.7³ × 0.1 × 0.4 = 0.014
    i+4: salience=0.3, enc=0.6  →  0.7⁴ × 0.3 × 0.6 = 0.062

    future_pull = 0.098 + 0.392 + 0.014 + 0.062 = 0.566

  The big climax at i+2 dominates, even though i+1 is closer.
  This is why λ² × salience outweighs λ¹ × low salience:
  importance beats proximity.
```

The future pull biases the predicted mean upward (toward louder/brighter)
by `xi × future_pull × 7.0` on the gain_db dimension:

```python
fp_vec    = np.zeros(D)
fp_vec[0] = future_pull * 7.0     # only gain_db for now
X_mu_bar += xi * fp_vec
```

The scaling by 7.0 converts the normalised enc back to the gain_db range.
`xi` (default 0.05) keeps the pull subtle.

---

## 11. Volatility — Exponentially Weighted Innovation History

Process noise Q scales with both drama and **volatility** — the recent
history of how surprising the score has been. This was described
conceptually in the foundation; the exact formula:

```
vol = Σ_{k=0}^{vol_window-1}  0.7^(vol_window-1-k) × ||ν_{t-k}||²  /  vol_window

where ν_t = innovation at step t  (the Kalman surprise vector)
```

This is an exponentially weighted mean of squared innovation norms:
recent innovations count more than older ones (decay rate 0.7).

```
Q_t = Q_base × Q_scale × max(drama_curved, 1e-4) × (1 + η × vol)
```

`η` (eta, default 0.3) controls how much volatility amplifies Q.

```
Intuition:

  If recent markings have been surprising (large innovations), the
  filter increases its process noise. It becomes less certain about
  where the state is going — it loosens its prediction.

  This is the model learning, within a performance, that the score
  is behaving erratically. It widens its uncertainty to stay open
  to further surprises.
```

---

## 12. Complete Golem Execution Flow

Putting it all together, for each score event:

```
                    ┌─────────────────────────────────────────┐
                    │  For each event at time t               │
                    └──────────────────┬──────────────────────┘
                                       │
                         resolve_golem_type(t, golems)
                                       │
               ┌───────────────────────┴──────────────────────┐
               │ type = 'random_walk'                         │ type = 'kalman'
               │                                               │
               │ rw_char = rw_character_at(t)                 │ char = character_at(t)
               │ x(t)    = rw_step(x(t-1), rw_char)          │  ↓
               │           ├ drift                            │ drama(t) → Q_t
               │           ├ mean_reversion                   │ future_pull(t) → fp_vec
               │           ├ correlated noise                 │
               │           └ boundary handling                │ predict(μ, Σ, F, Q_t, fp_vec)
               │                                               │  ↓
               │                                              │ observation y(t), H, R
               │                                              │ R_eff = R × R_scale / obs_weight
               │                                              │  ↓
               │                                              │ update(μ, Σ, y, H, R_eff)
               │                                              │  ↓
               │                                              │ sample from posterior
               │                                              │   (using chosen distribution)
               │                                              │  ↓
               │                                              │ optionally add rw_scatter noise
               │                                              │
               └───────────────────────┬──────────────────────┘
                                       │
                              clip to physical limits
                                       │
                              apply_state(event, x)
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │  enriched event with                    │
                    │    gain_db, brightness, timing_offset,  │
                    │    attack_shape, reverb_wet             │
                    └─────────────────────────────────────────┘
```

---

## 13. Parameter Quick Reference

### Kalman golem parameters

| Parameter | Default | Range | What it controls |
|-----------|---------|-------|-----------------|
| `A1` | 0.7 | [0, 0.95] | Momentum from previous state |
| `A2` | 0.2 | [0, 0.95] | Momentum from two steps back |
| `A1_dims` | null | per-dim | Per-dimension A1 override |
| `A2_dims` | null | per-dim | Per-dimension A2 override |
| `Q_scale` | 1.0 | [0.05, 5] | Process noise scale (how much state wanders) |
| `R_scale` | 1.0 | [0.05, 5] | Observation noise scale |
| `lam` | 0.7 | [0.1, 0.99] | Familiarity λ (future lookahead decay) |
| `obs_weight` | 1.0 | [0, 2] | How closely the score is followed |
| `drama_curve` | linear | linear/square/exp | Non-linearity applied to drama before scaling Q |
| `distribution` | gaussian | see §5.2 | Sampling distribution |
| `rw_scatter` | 0.0 | [0, 1] | Extra noise on top of Kalman posterior |

### Random Walk golem parameters

| Parameter | Default | Range | What it controls |
|-----------|---------|-------|-----------------|
| `step_size` | [1.5, 0.05, 20, 0.05, 0.05] | per-dim | Noise magnitude per dimension |
| `drift` | [0, 0, 0, 0, 0] | per-dim | Systematic directional drift |
| `mean_reversion` | 0.0 | [0, 1] | Global pull-back toward zero |
| `mr_dims` | null | per-dim | Per-dimension mean reversion override |
| `distribution` | gaussian | see §5.2 | Noise distribution |
| `boundary_mode` | clip | clip/reflect | What happens at physical limits |
| `correlation` | null | 5×5 matrix | Covariance between dimensions |

### Golem envelope parameters (both types)

| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| `weight` | 1.0 | Blend weight relative to other active golems |
| `fade_in` | 0.0 | Seconds to ramp from 0 to `weight` at region start |
| `fade_out` | 0.0 | Seconds to ramp from `weight` to 0 at region end |
