# Theoretical Foundation — V2 Engine Update

> This document extends `theoretical_foundation_v2_revised.md`.
> That document covers the mathematical derivation of the Kalman filter,
> AR(2) augmentation, window observations, adaptive Q via structural
> salience ω and innovation energy ε, and the lookahead prior φ.
>
> This document covers everything added after that foundation:
> the Random Walk process model, non-Gaussian sampling distributions,
> regime envelopes and blending, per-dimension AR coefficients, the
> RW scatter hybrid, and the exact formulas for ω and φ as implemented.

---

## 1. Two Process Models

The original foundation described a single model: a Kalman filter with
AR(2) momentum. The current engine supports two fundamentally different
process models, selected per region via the **filter regime** R:

```
PROCESS MODELS
───────────────────────────────────────────────────────────────────────
  type: kalman         (default)
    Maintains a Gaussian belief over expressive state.
    AR(2) momentum + observation update.
    Optimal under Gaussian assumptions.
    Well-suited for: structured, score-aware interpretation.

  type: random_walk
    Expressive state evolves as unconstrained Brownian motion.
    No score observations. No Kalman update.
    Well-suited for: free improvisation, dream-like passages.
```

The process model is chosen **per regime region**, not globally. At each
score event, the engine resolves which model governs:

```python
def _resolve_golem_type(t, golems):
    active = [g for g in golems if g['from'] <= t < g['to']]
    types  = {g.get('type', 'kalman') for g in active}
    # Only pure-RW regions use the RW path
    return 'random_walk' if types == {'random_walk'} else 'kalman'
```

If a Kalman and a Random Walk regime overlap, the Kalman path is used.
The Random Walk path only activates when every active regime at time t
is explicitly of type `random_walk`. This is a safety choice: the Kalman
filter has a defined state to propagate; a mixed region falls back to it.

---

## 2. Regime Envelope — Weight, Fade In, Fade Out

Each regime region in the score has an envelope that controls how much
influence it exerts over time:

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

Without fade envelopes, switching between regimes is instantaneous —
the filter's operating mode snaps at the regime boundary. Fade envelopes
allow regime parameters to **bleed into each other**, creating smooth
transitions that correspond to a performer gradually shifting their
interpretive stance.

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

During the overlap window both regimes are active and their parameters
are blended by normalised weight (see Section 3).

---

## 3. Multi-Regime Blending

Multiple regimes can be active simultaneously. The engine blends their
parameters using normalised effective weights before constructing the
filter matrices.

### 3.1 Kalman blending

For scalar parameters (A1, A2, Q_scale, R_scale, λ, obs_weight):

```
p_blended = Σᵢ  wᵢ · pᵢ  /  Σᵢ wᵢ
```

For string parameters (drama_curve, distribution): the dominant regime's
value wins (highest normalised weight).

For per-dimension A1/A2 arrays: element-wise weighted average.

```
Example — two overlapping Kalman regimes at t=32:

  regime A (dramatic): w_eff=0.3,  A1=0.8, Q_scale=2.0
  regime B (lyrical):  w_eff=0.7,  A1=0.6, Q_scale=0.5

  total_w = 1.0

  A1_blended    = 0.3×0.8 + 0.7×0.6 = 0.24 + 0.42 = 0.66
  Q_scale_blend = 0.3×2.0 + 0.7×0.5 = 0.60 + 0.35 = 0.95
  distribution  = lyrical's value ('linear')   ← dominant by weight
```

### 3.2 Random Walk blending

The same principle applies: step_size and drift vectors are element-wise
weighted averages. Correlation matrices cannot be blended without
non-trivial Riemannian interpolation — the dominant regime's matrix is used.

### 3.3 Inline parameter overrides

A regime region in the score YAML can override any named-regime parameter
directly:

```yaml
golems:
  - from: 0
    to: 30
    character: lyrical      # base preset
    A1: 0.85                # override just this
    Q_scale: 0.3            # and this
    distribution: laplace   # and sampling distribution
```

This allows fine-grained control without proliferating named regimes.

---

## 4. Per-Dimension AR Coefficients

The original foundation treats A1 and A2 as scalars multiplied by the
identity matrix. This is now extended: A1 and A2 can be specified
**per dimension**, giving each expressive dimension its own inertia.

```yaml
# In a custom regime definition:
A1_dims: [0.8, 0.6, 0.4, 0.7, 0.5]
A2_dims: [0.1, 0.2, 0.1, 0.15, 0.1]
#         gain  bright  timing  attack  reverb
```

This allows, for example, gain_db to have high inertia (changes slowly)
while timing_offset_ms has lower inertia (changes quickly, volatile).

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

The Kalman filter always maintains a **Gaussian belief** (mean μ,
covariance Σ). However, the sample drawn from that belief at each event
can use a non-Gaussian distribution whose spread matches the posterior
variance.

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
deviation at each dimension from √diag(Σ).

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
                              At df=3 very heavy tails; df→∞ → Gaussian.
bimodal         Bipolar       Two mirrored Gaussians at ±0.75σ.
                              State swings between two expressive poles.
mixture         Bursting      Gaussian base + rare large spikes.
                              Normal most of the time; occasional outbursts.
```

The normalisation convention: E[noise²] ≈ σ² per dimension across all
distributions. This ensures spread is comparable to the Gaussian case.

### 5.3 How sampling works

For the Gaussian case, the posterior is sampled directly as a
multivariate normal (preserving off-diagonal covariances):

```python
x_sample = rng.multivariate_normal(mu, Sigma)
```

For all other distributions, independence is assumed across dimensions
and per-dimension σ is extracted from the diagonal of Σ:

```python
std      = sqrt(diag(Sigma))          # shape (d,)
noise    = sample_noise(dist, scale=std)  # shape (d,)
x_sample = mu + noise
```

This is an approximation: off-diagonal covariances are ignored. The
justification is that the expressive dimensions are largely independent
in musical performance, and non-Gaussian distributions do not have a
standard multivariate form that preserves their tail properties.

---

## 6. The Random Walk Process Model — Full Specification

### 6.1 Basic Brownian motion

The simplest RW step: the state diffuses by additive noise each event.

```
x(t) = x(t-1) + noise(t)

noise(t) ~ dist(0, step_size)
```

Where `step_size ∈ ℝ^d` sets the noise magnitude independently per
dimension. There is no observation update, no score awareness. The state
wanders freely in all directions.

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
- `mr = 0.15`: gentle pull toward zero, reversion timescale ~6 events
- `mr = 1.0`: state snaps to zero each step (degenerate)

```
Intuition — mean reversion as memory decay:

  Without mean reversion: the state may drift to an extreme and stay.
  With mean reversion: the state is pulled toward a resting level
  unless actively pushed outward by the drift term.
  The further the departure from centre, the stronger the pull back.
```

### 6.3 Drift

A directional drift shifts the expected trajectory over time:

```
x(t) = x(t-1) + drift + ...

drift ∈ ℝ^d
```

A positive drift on dimension 0 (gain_db) makes the state gradually
increase over time, independent of score markings.

### 6.4 Boundary handling

The RW state can reach physical limits (e.g. gain_db > +6 or < -40).
Two boundary modes:

```
CLIP:
  Values outside [lo, hi] are clamped to the boundary.
  The state accumulates at the edge.

REFLECT:
  Values outside [lo, hi] are reflected back in.
  x = 2·lo - x   (if x < lo)
  x = 2·hi - x   (if x > hi)
```

Reflect is preferable to avoid the state getting permanently stuck at
an extreme value.

### 6.5 Correlated noise

By default, each dimension's noise is sampled independently. Optionally,
a correlation matrix defines how dimensions co-vary:

```yaml
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
engine falls back to independent sampling.

### 6.6 Breathing walk

A sinusoidal drift component creates a slow periodic oscillation:

```
drift(t) += step_size × 0.6 × sin(2π · t / breath_period)
```

With `breath_period = 8.0` seconds, the state oscillates with an 8-second
cycle. This is not derived from the score — it is an intrinsic periodic
component imposed on the passage.

---

## 7. RW Scatter — Kalman-Noise Hybrid

A Kalman process model can have its posterior samples augmented with
additional noise controlled by the `rw_scatter` parameter (range [0, 1]):

```
x_sample = kalman_posterior_sample + rng.normal(0, std × rw_scatter)

where std = sqrt(diag(Sigma))
```

At `rw_scatter = 0`: pure Kalman posterior (default).
At `rw_scatter = 1`: posterior sample plus a full additional σ of noise.

This relaxes the Kalman filter's confidence in its own posterior. At
high scatter, the Kalman's disciplined tracking of the score is
contaminated with random deviation. The filter still runs, but its
output is treated as a rough guide rather than a precise model.

```
rw_scatter = 0.0  →  precise, score-following
rw_scatter = 0.3  →  slightly loose, occasional surprises
rw_scatter = 0.8  →  barely following the score, regime-driven
rw_scatter = 1.0  →  Kalman structure present but overwhelmed
```

Statistically: rw_scatter intentionally breaks the optimality of the
Kalman posterior. This is a creative control, not a modelling error.

---

## 8. Observation Score Weight (obs_weight)

The `obs_weight` parameter scales how closely this regime follows the
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

Low obs_weight:   a performer who takes broad interpretive liberties
High obs_weight:  a performer who executes written dynamics precisely
```

This is distinct from `R_scale`, which scales the entire R matrix
including the physics of the window observation. `obs_weight` is a
purely musical control: "how much does this regime care about the score?"

---

## 9. Structural Salience ω — Exact Implementation

The theoretical foundation describes ω conceptually. The exact
four-component formula, as implemented in `v2/drama.py`:

```
ω(i) = w_dist · distance(i)
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

The dynamic ranking ladder:

```
ppp=0  pp=1  p=2  mp=3  mf=4  f=5  ff=6  fff=7
Structural / gradual markings (sfz, cresc, etc.) → treated as 3.5 (mid-range)
```

---

## 10. Lookahead Prior φ — Exact Implementation

The lookahead prior at marking i is a salience-weighted decaying sum
over the next K markings ahead:

```
φ(i) = Σ_{k=1}^{K}  λᵏ · ω(i+k) · enc(m(i+k))

where:
  ω(j)    = structural salience at future event j   (same formula, forward direction)
  enc(m)  = rank(m) / 7                             (normalised rank, ∈ [0, 1])
  λ       = familiarity ∈ (0,1)                     (how far ahead is known)
  K       = look-ahead window                        (default 10 markings)
```

```
Interpretation:

  λ high (0.9) — the filter knows the score well. Events 8-10
  markings ahead still influence the current state.

  λ low (0.3) — essentially sight-reading. Only the next 1-2
  markings ahead meaningfully influence the current state.

  Example with λ = 0.7, K = 4:

    i+1: ω=0.2, enc=0.7  →  0.7¹ × 0.2 × 0.7 = 0.098
    i+2: ω=0.8, enc=1.0  →  0.7² × 0.8 × 1.0 = 0.392  ← climax ahead
    i+3: ω=0.1, enc=0.4  →  0.7³ × 0.1 × 0.4 = 0.014
    i+4: ω=0.3, enc=0.6  →  0.7⁴ × 0.3 × 0.6 = 0.062

    φ = 0.098 + 0.392 + 0.014 + 0.062 = 0.566

  The high-salience climax at i+2 dominates even though i+1 is closer.
  Structural significance beats proximity.
```

The lookahead prior biases the predicted mean on the gain_db dimension:

```python
fp_vec    = np.zeros(D)
fp_vec[0] = φ(i) * 7.0     # convert normalised enc back to gain_db range
μ̄(t)    += ξ * fp_vec
```

The scaling by 7.0 converts the normalised enc back to the gain_db range.
`ξ` (default 0.05) keeps the pull subtle.

---

## 11. Innovation Energy — Exact Formula

Process noise Q scales with both structural salience ω and innovation
energy ε — the recent history of how much the filter has been surprised.
The exact formula:

```
ε(t) = Σ_{k=0}^{M-1}  0.7^(M-1-k) × ||ν_{t-k}||²  /  M

where ν_t = innovation at step t  (the Kalman residual vector)
```

This is an exponentially weighted mean of squared innovation norms.
Recent innovations count more than older ones (decay rate 0.7).

```
Q_t = Q_base × Q_scale × max(f(ω_t), 1e-4) × (1 + η × ε_t)
```

`η` (eta, default 0.3) controls how much innovation energy amplifies Q.

```
Intuition:

  If recent markings have been surprising (large ν), the filter
  increases its process noise — it loosens its predictions, staying
  open to further surprises.

  This is the model updating its own uncertainty estimate based on
  empirical evidence that the process is more erratic than expected.
  Structural salience ω keeps this grounded: a symbolically quiet
  passage holds Q low even if the filter has been recently surprised.
```

---

## 12. Complete Process Model Execution Flow

Putting it all together, for each score event:

```
                    ┌─────────────────────────────────────────┐
                    │  For each event at time t               │
                    └──────────────────┬──────────────────────┘
                                       │
                         resolve_process_model(t, regimes)
                                       │
               ┌───────────────────────┴──────────────────────┐
               │ type = 'random_walk'                         │ type = 'kalman'
               │                                               │
               │ regime_params = rw_params_at(t)              │ regime_params = kalman_params_at(t)
               │ x(t) = rw_step(x(t-1), regime_params)       │  ↓
               │         ├ drift                              │ ω(t) → Q_t
               │         ├ mean_reversion                     │ φ(t) → fp_vec
               │         ├ correlated noise                   │
               │         └ boundary handling                  │ predict(μ, Σ, F, Q_t, fp_vec)
               │                                               │  ↓
               │                                              │ observation y(t), H(t), R(t)
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

### Kalman process model parameters

| Parameter | Default | Range | What it controls |
|-----------|---------|-------|-----------------|
| `A1` | 0.7 | [0, 0.95] | Momentum from previous state |
| `A2` | 0.2 | [0, 0.95] | Momentum from two steps back |
| `A1_dims` | null | per-dim | Per-dimension A1 override |
| `A2_dims` | null | per-dim | Per-dimension A2 override |
| `Q_scale` | 1.0 | [0.05, 5] | Process noise scale |
| `R_scale` | 1.0 | [0.05, 5] | Observation noise scale |
| `lam` (λ) | 0.7 | [0.1, 0.99] | Familiarity — lookahead decay rate |
| `obs_weight` | 1.0 | [0, 2] | Score observation trust |
| `drama_curve` | linear | linear/square/exp | Non-linearity applied to ω before scaling Q |
| `distribution` | gaussian | see §5.2 | Posterior sampling distribution |
| `rw_scatter` | 0.0 | [0, 1] | Additional noise on Kalman posterior sample |

### Random Walk process model parameters

| Parameter | Default | Range | What it controls |
|-----------|---------|-------|-----------------|
| `step_size` | [1.5, 0.05, 20, 0.05, 0.05] | per-dim | Noise magnitude per dimension |
| `drift` | [0, 0, 0, 0, 0] | per-dim | Systematic directional drift |
| `mean_reversion` | 0.0 | [0, 1] | Global pull-back toward zero |
| `mr_dims` | null | per-dim | Per-dimension mean reversion override |
| `distribution` | gaussian | see §5.2 | Noise distribution |
| `boundary_mode` | clip | clip/reflect | What happens at physical limits |
| `correlation` | null | 5×5 matrix | Covariance between dimensions |

### Regime envelope parameters (both process models)

| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| `weight` | 1.0 | Blend weight relative to other active regimes |
| `fade_in` | 0.0 | Seconds to ramp from 0 to `weight` at region start |
| `fade_out` | 0.0 | Seconds to ramp from `weight` to 0 at region end |

---

## 14. Notation Summary (additions to base document)

| Symbol | Name | Description |
|--------|------|-------------|
| R | Filter regime | Named parameter bundle + process model type |
| w_eff(t) | Effective regime weight | Weight after fade envelope applied |
| ω_future(t+k) | Future structural salience | ω evaluated looking forward |
| φ(t) | Lookahead prior | Salience-weighted decaying future influence (same as base doc) |
| rw_scatter | RW scatter | Additional posterior noise parameter |
| obs_weight | Observation score weight | Score-following intensity multiplier |
| mr | Mean reversion | Ornstein-Uhlenbeck pull-back coefficient |
