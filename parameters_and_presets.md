# Parameters and Presets Reference

> This document enumerates all learnable and user-configurable parameters
> in the V2 engine, organised by model component, followed by a catalogue
> of named presets for regimes, salience weights, and sampling distributions.
>
> Parameters marked **[new]** do not exist in the current implementation
> and represent proposed extensions for increased flexibility.
>
> Each **[new]** parameter includes an implementation complexity rating:
>
> - **[easy]** — isolated change, no architectural impact, < 1 day
> - **[medium]** — requires changes in 2–4 files, some testing, 1–3 days
> - **[hard]** — architectural change, affects multiple subsystems, > 3 days
> - **[research]** — requires non-trivial mathematical derivation or
>   external library integration before implementation can begin

---

## Part 1 — All Learnable / User-Configurable Parameters

---

### A. Transition Model — AR(2)

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| AR(2) coefficient, step 1 | A₁ | scalar or 5-vector | per regime | exposed | — |
| AR(2) coefficient, step 2 | A₂ | scalar or 5-vector | per regime | exposed | — |
| Initial state mean | μ₀ | 5-vector | global | **[new]** hardcoded to zero | easy |
| Initial state covariance | Σ₀ | 5×5 matrix | global | **[new]** hardcoded | easy |
| Stability constraint enforcement | A₁+A₂ < 1 | boolean | global | **[new]** implicit | easy |
| Cross-dimension coupling in F | off-diagonal A₁, A₂ | 5×5 matrices | per regime | **[new]** forced diagonal | hard |

> Allowing full 5×5 A₁ and A₂ matrices would let the model encode that
> a rising gain trajectory tends to also pull brightness upward — a
> musically meaningful coupling currently not possible. Requires
> re-deriving the stability condition for the full matrix case and
> validating that the augmented F remains well-conditioned.

---

### B. Process Noise — Q

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Baseline process noise per dimension | Q_base | 5-vector (diagonal of Q) | per regime | global scalar × identity | easy |
| Regime noise scale | Q_scale | scalar | per regime | exposed | — |
| Per-dimension noise scale override | Q_scale_dims | 5-vector | per regime | **[new]** | easy |
| Salience curve shape | f(ω) | linear / square / exp / sigmoid | per regime | exposed (3 options) | easy to extend |
| Innovation energy decay rate | — | scalar ∈ (0,1) | global | **[new]** hardcoded at 0.7 | easy |
| Innovation energy window length | M | integer | global | **[new]** hardcoded | easy |
| Innovation energy mixing weight | η | scalar | global | exposed | — |
| Position curve shape | β(pos) | function shape | global | **[new]** hardcoded | medium |
| Q off-diagonal terms | full Q matrix | 5×5 PSD | per regime | **[new]** forced diagonal | hard |
| Q adaptation method | — | salience / mehra / combined | global | **[new]** salience only | hard |

> Q_base as a full 5×5 matrix (positive semi-definite) would allow
> correlated process noise — the model could know that gain_db and
> brightness tend to wander together. Requires PSD enforcement at
> input validation time.
>
> Q adaptation method: combining Mehra innovation-based estimation with
> the existing salience-driven scaling would make Q respond to both
> statistical filter miscalibration and symbolic score structure
> simultaneously. See theoretical foundation §6.2.

---

### C. Observation Model — H, R, Window

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Window size | N | integer | global | exposed, default 3 | — |
| H matrix per window pattern | H(pattern) | m×5 matrix | per pattern | transition_table.yaml | — |
| R matrix per window pattern | R(pattern) | m×m matrix | per pattern | transition_table.yaml | — |
| Observation noise scale | R_scale | scalar | per regime | exposed | — |
| Score observation trust | obs_weight | scalar | per regime | exposed | — |
| Per-dimension obs_weight | obs_weight_dims | 5-vector | per regime | **[new]** | medium |
| Dynamic marking encoding scheme | enc(m) | ordinal rank | global | **[new]** hardcoded 0–7 | medium |
| Structural marking encoding | binary indicators | fixed set | global | **[new]** hardcoded set | easy |
| Window decay weighting | γ_w | scalar ∈ (0,1] | global | **[new]** currently uniform | easy |
| R off-diagonal terms | full R matrix | m×m PSD | per pattern | **[new]** forced diagonal | medium |
| Observation likelihood | — | gaussian / student_t | global | **[new]** gaussian only | hard |

> Window decay weighting γ_w: y_weighted(t) = [enc(m(t)), γ_w·enc(m(t-1)), γ_w²·enc(m(t-2)), ...].
> Makes the most recent marking count more than older ones. A simple
> one-line change in observation.py with meaningful impact.
>
> Per-dimension obs_weight: allows the score to be trusted more for
> gain_db than for timing — a regime that follows dynamics precisely
> but loosely interprets their timing implications.
>
> Observation likelihood as student_t would make the update robust to
> outlier markings but requires the unscented Kalman filter or a
> variational approximation. Significant architectural change.

---

### D. Lookahead Prior — φ

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Familiarity / lookahead decay | λ | scalar | per regime | exposed | — |
| Lookahead prior scale | ξ | scalar | global | exposed | — |
| Per-regime ξ override | ξ_regime | scalar | per regime | **[new]** global only | easy |
| Lookahead window length | K | integer | global | **[new]** hardcoded at 10 | easy |
| Dimensions affected by φ | fp_vec mask | 5-vector binary | global | **[new]** gain_db only | easy |
| φ scaling per dimension | fp_vec scale | 5-vector | global | **[new]** gain_db × 7.0 only | easy |
| φ non-linearity | — | linear / square / exp | global | **[new]** linear | easy |
| Salience threshold for φ | ω_threshold | scalar | global | **[new]** no threshold | easy |
| Future pull direction | — | toward / away | global | **[new]** always toward | medium |

> φ dimension mask + per-dim scale: the lookahead prior currently biases
> only gain_db. Exposing a mask would let it also pull brightness or
> timing_offset_ms toward anticipated events — a two-line change in
> interpreter.py with significant expressive impact.
>
> Future pull direction: a regime could pull away from what is coming —
> appropriate for a performer who builds contrast before a climax by
> going quieter first, then releasing into the loud event.

---

### E. Structural Salience — ω

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Dynamic distance weight | α | scalar | global | exposed, default 0.4 | — |
| Structural marking weight | β | scalar | global | exposed, default 0.3 | — |
| Local contrast weight | γ | scalar | global | exposed, default 0.2 | — |
| Phrase boundary weight | δ | scalar | global | exposed, default 0.1 | — |
| Local contrast window half-width | W | integer | global | **[new]** hardcoded at 3 | easy |
| Set of structural markings | {sfz, fp, ...} | set | global | **[new]** hardcoded | easy |
| Salience normalisation clamp | ω ∈ [0,1] | boolean | global | **[new]** implicit | easy |
| ω non-linearity | — | linear / square / exp | global | **[new]** linear | easy |
| Per-regime ω weight override | ω_weight | scalar | per regime | **[new]** global only | medium |
| Temporal smoothing of ω | — | scalar (EMA) | global | **[new]** no smoothing | easy |
| Custom salience component | user_fn | function | global | **[new]** | hard |

> Temporal smoothing of ω via an exponential moving average would prevent
> Q from spiking sharply at isolated high-salience events, producing a
> smoother envelope of process noise over time.
>
> Custom salience component: allowing a user-defined Python function as a
> fifth ω component. Requires a plugin interface and sandboxing — similar
> to the existing morphogenics plugin system.

---

### F. Sampling Distribution

This section is substantially extended relative to the original document.
See also Part 3 — Distribution Reference for the full per-distribution
parameter catalogue.

#### F.1 Current parameters

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Sampling distribution choice | dist | categorical | per regime | exposed | — |
| Student-t degrees of freedom | df | scalar | per regime | exposed if student_t | — |
| Bimodal pole separation | ±sep·σ | scalar | per regime | **[new]** hardcoded ±0.75σ | easy |
| Mixture spike probability | mixture_p | scalar | per regime | exposed if mixture | — |
| Mixture spike scale | spike_scale | scalar | per regime | **[new]** hardcoded | easy |
| RW scatter magnitude | rw_scatter | scalar | per regime | exposed | — |

#### F.2 Per-dimension distribution control **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Per-dimension distribution family | dist_dims | 5-vector categorical | per regime | **[new]** | medium |
| Per-dimension df (student_t) | df_dims | 5-vector scalar | per regime | **[new]** | easy once dist_dims exists |
| Per-dimension bimodal separation | sep_dims | 5-vector scalar | per regime | **[new]** | easy once dist_dims exists |
| Per-dimension mixture_p | mixture_p_dims | 5-vector scalar | per regime | **[new]** | easy once dist_dims exists |
| Per-dimension spike_scale | spike_scale_dims | 5-vector scalar | per regime | **[new]** | easy once dist_dims exists |
| Per-dimension rw_scatter | rw_scatter_dims | 5-vector scalar | per regime | **[new]** | easy |

> Per-dimension distribution is the single highest-impact extension in
> this section. Each expressive dimension has a different natural
> statistical character:
>
> | Dimension | Natural family | Reason |
> |-----------|----------------|--------|
> | gain_db | gaussian or laplace | Smooth, occasionally jumpy |
> | brightness | beta | Bounded [0,1], smooth |
> | timing_offset_ms | laplace or cauchy | Most volatile, heavy tails |
> | attack_shape | beta | Bounded, slow-changing |
> | reverb_wet | beta or gaussian | Bounded, very slow-changing |
>
> Implementation: dist_dims is a 5-element list resolved at sampling time.
> If null, the regime-level dist is broadcast to all dimensions (backward
> compatible). Changes confined to a new `sample_per_dim()` function.

#### F.3 Salience-conditioned distribution **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| ω threshold for distribution switch | ω_dist_threshold | scalar or 3-vector | per regime | **[new]** | medium |
| Distribution at low ω | dist_low | categorical | per regime | **[new]** | medium |
| Distribution at mid ω | dist_mid | categorical | per regime | **[new]** | medium |
| Distribution at high ω | dist_high | categorical | per regime | **[new]** | medium |
| Continuous tail weight as function of ω | tail_fn | linear / exp | per regime | **[new]** | medium |
| df as continuous function of ω | df_fn | monotone function | per regime | **[new]** | medium |

> The sampling distribution shifts automatically with structural salience.
> At low ω (stable passage) the filter samples conservatively; at high ω
> (structural event) it switches to a heavier-tailed distribution, producing
> more extreme samples at exactly the moments where extremes are musically
> appropriate.
>
> The continuous version is more elegant:
> ```
> df(t) = df_max - (df_max - df_min) · ω(t)
> df_max = 20  (near-Gaussian at low salience)
> df_min = 2   (very heavy tails at high salience)
> ```

#### F.4 Time-varying distribution within a regime **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Distribution schedule | dist_schedule | list of (t, dist) | per regime | **[new]** | medium |
| Schedule interpolation | — | step / blend | per regime | **[new]** | medium |
| Distribution ramp duration | dist_ramp | scalar (seconds) | per regime | **[new]** | medium |

> A regime can specify a planned arc of distributions:
> ```yaml
> dist_schedule:
>   - at: 0.0   dist: gaussian
>   - at: 0.5   dist: laplace
>   - at: 0.8   dist: cauchy
> ```
> With blend interpolation, the engine draws a mixture sample from both
> adjacent distributions weighted by temporal position. With step
> interpolation, it switches abruptly.

#### F.5 Regime-level distribution blending **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Distribution blending method | dist_blend | dominant / mixture | global | **[new]** dominant only | medium |
| Mixture sample weighting | — | by w_eff | global | **[new]** | medium |

> Currently when two regimes overlap, the dominant regime's distribution
> wins entirely. With mixture blending, the engine draws a sample from
> each active regime's distribution and takes a weighted average by w_eff.
> This is a convex combination of samples rather than a proper mixture
> model, but it is smooth and well-behaved in practice.

#### F.6 Covariance structure for non-Gaussian sampling **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Copula type | copula | independent / gaussian / t | per regime | **[new]** independent only | hard |
| Copula df (t-copula) | copula_df | scalar | per regime | **[new]** | hard |

> Currently non-Gaussian distributions ignore off-diagonal covariances
> in Σ and sample each dimension independently. A Gaussian copula would
> preserve the correlation structure from Σ while applying non-Gaussian
> marginals per dimension — the statistically correct combination.
>
> Procedure:
> 1. Compute Cholesky L of Σ
> 2. Draw z ~ N(0,I), transform to u = Φ(Lz) — uniform marginals, correlated
> 3. Apply inverse CDF of the chosen distribution to each u_i
>
> Requires implementing inverse CDFs for all distributions and careful
> numerical handling at the tails.

#### F.7 Posterior covariance inflation **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Covariance inflation factor | inflate | scalar ≥ 1 | per regime | **[new]** | easy |
| Per-dimension inflation | inflate_dims | 5-vector | per regime | **[new]** | easy |
| ω-driven inflation | inflate_fn | function of ω | per regime | **[new]** | easy |

> Covariance inflation multiplies Σ before sampling without changing the
> Kalman update: x ~ p(μ, inflate·Σ). Widens the sampling distribution
> without affecting the filter's internal belief. A simple expressive
> freedom knob — trivial to implement, high musical impact.

#### F.8 Asymmetric distributions **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Skewness per dimension | skew_dims | 5-vector scalar | per regime | **[new]** | medium |
| Skew-normal distribution | skew_normal | — | per regime | **[new]** | medium |
| Asymmetric Laplace | asym_laplace | — | per regime | **[new]** | medium |
| Per-dimension upper/lower tail ratio | tail_ratio_dims | 5-vector | per regime | **[new]** | medium |

> All current distributions are symmetric around the posterior mean.
> Asymmetric distributions allow gain_db to be more likely to overshoot
> than undershoot a dynamic marking — capturing the tendency of some
> performers to play louder than written. Both skew-normal and asymmetric
> Laplace are available in scipy.stats and straightforward to implement.

#### F.9 Truncated distributions **[new]**

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Truncation bounds per dimension | trunc_dims | 5×2 matrix | per regime | **[new]** | medium |
| Truncation relative to σ | trunc_sigma | 5-vector scalar | per regime | **[new]** | medium |
| Hard clip vs truncated resample | — | clip / resample | per regime | **[new]** | easy |

> Truncated distributions constrain samples to a range without the
> abrupt clipping currently applied at physical limits. A truncated
> Gaussian samples only from the part of the bell curve within [lo, hi],
> shifting both the effective mean and variance. More statistically
> principled than post-hoc clipping, smoother near boundaries.

---

### G. Random Walk Process Model

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Step size per dimension | step_size | 5-vector | per RW regime | exposed | — |
| Drift per dimension | drift | 5-vector | per RW regime | exposed | — |
| Mean reversion per dimension | mr_dims | 5-vector | per RW regime | exposed | — |
| Mean reversion target | target | 5-vector | per RW regime | **[new]** hardcoded to zero | easy |
| Boundary mode per dimension | boundary_mode | 5-vector categorical | per RW regime | global per regime | easy |
| Correlation matrix | Corr | 5×5 | per RW regime | exposed | — |
| Breath period | breath_period | scalar (seconds) | per RW regime | **[new]** hardcoded at 8.0 | easy |
| Breath amplitude | breath_amp | scalar | per RW regime | **[new]** hardcoded at 0.6 | easy |
| Breath phase offset | breath_phase | scalar (radians) | per RW regime | **[new]** | easy |
| RW distribution | dist | categorical | per RW regime | exposed | — |
| Step size schedule | step_size_schedule | list of (t, step_size) | per RW regime | **[new]** | medium |
| ω-driven step size scaling | — | function of ω | per RW regime | **[new]** | medium |
| Lévy flight exponent | alpha | scalar ∈ (0,2] | per RW regime | **[new]** | hard |
| Fractional Brownian motion Hurst exponent | H | scalar ∈ (0,1) | per RW regime | **[new]** | research |

> Mean reversion target hardcoded to zero: a non-zero target lets the
> RW wander around a musically meaningful resting level rather than
> always pulling back to the neutral origin.
>
> ω-driven step size: step_size(t) = step_size_base · f(ω(t)). Makes
> the RW more volatile at structurally significant moments — bringing
> salience awareness into the random walk process, which currently has
> none.
>
> Lévy flight: a stable distribution with exponent α < 2 produces
> occasional very large jumps. α=2 recovers Gaussian. Available via
> scipy.stats.levy_stable but slow for real-time use.
>
> Fractional Brownian motion H ≠ 0.5: H > 0.5 is persistent (trending),
> H < 0.5 is anti-persistent (mean-reverting at the increment level).
> Requires circulant embedding or full Cholesky — expensive for long
> sequences. Research-level effort.

---

### H. Regime Envelope and Blending

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| Regime weight | weight | scalar | per regime region | exposed | — |
| Fade in duration | fade_in | scalar (seconds) | per regime region | exposed | — |
| Fade out duration | fade_out | scalar (seconds) | per regime region | exposed | — |
| Fade curve shape | — | linear / exp / sigmoid / cosine | per regime region | **[new]** linear only | easy |
| Per-parameter fade curves | — | dict of param → curve | per regime region | **[new]** | medium |
| Blending method for string params | — | dominant / probabilistic | global | **[new]** dominant | easy |
| Blending method for correlation matrices | — | dominant / Riemannian | global | **[new]** dominant | hard |
| Regime priority ordering | priority | integer | per regime region | **[new]** | easy |
| Conditional regime activation | condition | function of ω or ε | per regime | **[new]** | hard |

> Per-parameter fade curves: Q_scale might fade with an exponential curve
> (appropriate for a multiplicative parameter) while obs_weight fades
> linearly. Currently all parameters share the same fade shape.
>
> Conditional regime activation: a regime activates only when a condition
> is met, e.g. when ω > 0.6 or ε > 2.0. Allows structurally triggered
> regime changes without pre-specifying time ranges — significant
> architectural extension.

---

### I. Global / Engine-Level

| Parameter | Symbol | Type | Scope | Status | Complexity |
|-----------|--------|------|-------|--------|------------|
| State dimension | d | integer | global | **[new]** hardcoded at 5 | hard |
| Physical limits per dimension | [lo, hi] | 5×2 matrix | global | **[new]** partially hardcoded | easy |
| Position curve α(pos) shape | α | function shape | global | **[new]** hardcoded | medium |
| Innovation energy decay rate | — | scalar ∈ (0,1) | global | **[new]** hardcoded at 0.7 | easy |
| Pre-render pass parallelism | — | boolean | global | **[new]** sequential | easy |
| Random seed | seed | integer | global | **[new]** not exposed | easy |
| Output clipping method | — | hard / soft / tanh | global | **[new]** hard clip | easy |
| Dimension names | — | 5-vector string | global | **[new]** hardcoded | easy |

> State dimension d: exposing d allows adding new expressive dimensions
> (e.g. vibrato_rate, portamento) without changing engine architecture.
> Requires all downstream consumers of x(t) to be dimension-agnostic —
> a significant refactor.
>
> Output clipping: replacing the hard clip with a soft clip (tanh scaled
> to [lo, hi]) produces smoother behaviour near boundaries with no
> discontinuity.

---

## Part 2 — Presets

---

### Kalman Regime Presets

| Preset | A₁ | A₂ | Q_scale | R_scale | λ | dist | obs_weight | Character |
|--------|----|----|---------|---------|---|------|------------|-----------|
| `disciplined` | 0.85 | 0.10 | 0.3 | 0.3 | 0.80 | gaussian | 2.0 | Precise, literal, low variance |
| `lyrical` | 0.65 | 0.30 | 0.5 | 0.8 | 0.85 | gaussian | 1.0 | Smooth momentum, follows shape |
| `dramatic` | 0.80 | 0.10 | 2.0 | 1.5 | 0.70 | laplace | 1.2 | Volatile, responsive to markings |
| `turbulent` | 0.50 | 0.20 | 3.0 | 2.0 | 0.30 | student_t | 0.6 | Unpredictable, score loosely followed |
| `sparse` | 0.90 | 0.00 | 0.2 | 0.5 | 0.40 | gaussian | 1.5 | Static, low drift, literal |
| `impressionist` | 0.60 | 0.25 | 1.0 | 2.5 | 0.90 | beta | 0.4 | Score as suggestion, smooth deviations |
| `impulsive` | 0.40 | 0.10 | 2.5 | 0.8 | 0.50 | cauchy | 1.0 | Sudden large jumps, low inertia |
| `bipolar` | 0.70 | 0.15 | 1.5 | 1.2 | 0.60 | bimodal | 0.8 | Swings between two expressive poles |
| `sight_reading` | 0.75 | 0.15 | 1.0 | 1.0 | 0.20 | gaussian | 1.0 | No future awareness, reactive only |
| `memorised` | 0.70 | 0.20 | 1.0 | 1.0 | 0.95 | gaussian | 1.0 | Full piece awareness, anticipates climaxes |

---

### Random Walk Regime Presets

| Preset | step_size (gain) | drift | mean_reversion | dist | boundary | Character |
|--------|------------------|-------|----------------|------|----------|-----------|
| `drift_up` | 1.0 | +0.2/step | 0.0 | gaussian | reflect | Gradual crescendo over time |
| `drift_down` | 1.0 | -0.2/step | 0.0 | gaussian | reflect | Gradual decrescendo |
| `breathing` | 0.5 | sinusoidal | 0.05 | gaussian | reflect | Slow oscillation around neutral |
| `free_improv` | 2.5 | 0 | 0.0 | laplace | reflect | Unconstrained, heavy-tailed jumps |
| `anchored` | 1.0 | 0 | 0.3 | gaussian | reflect | Wanders but snaps back toward centre |
| `dream` | 0.3 | 0 | 0.02 | beta | reflect | Very slow, smooth, bounded drift |
| `erratic` | 3.0 | 0 | 0.0 | cauchy | clip | Extreme, no structure |

---

### Structural Salience Presets — ω

| Preset | α (distance) | β (structural) | γ (contrast) | δ (boundary) | Character |
|--------|-------------|----------------|--------------|--------------|-----------|
| `default` | 0.4 | 0.3 | 0.2 | 0.1 | Balanced across all components |
| `jump_sensitive` | 0.7 | 0.1 | 0.1 | 0.1 | Reacts strongly to dynamic leaps |
| `structure_sensitive` | 0.1 | 0.6 | 0.2 | 0.1 | Reacts strongly to sfz, subito, fp |
| `phrase_sensitive` | 0.2 | 0.1 | 0.2 | 0.5 | Reacts strongly to phrase beginnings |
| `context_sensitive` | 0.2 | 0.1 | 0.6 | 0.1 | Reacts strongly to local anomalies |
| `flat` | 0.25 | 0.25 | 0.25 | 0.25 | All components equally weighted |

---

### Sampling Distribution Presets

| Preset | dist | Extra params | Character |
|--------|------|-------------|-----------|
| `natural` | gaussian | — | Symmetric, moderate variation |
| `edgy` | laplace | — | More sudden jumps, fewer median values |
| `heavy` | student_t | df=3 | Occasional large outliers |
| `wild` | cauchy | clipped ±5σ | Extreme outliers, unpredictable |
| `bounded` | beta | — | Never reaches extremes, smooth |
| `flat` | uniform | — | No preference for posterior mean |
| `bipolar` | bimodal | sep=0.75σ | Two expressive poles |
| `mostly_normal` | mixture | p=0.05 | Normal with rare large spikes |
| `performer_a` | per-dim | gain=gaussian, timing=laplace, bright=beta, attack=beta, reverb=gaussian | Realistic performer profile |
| `nervous` | per-dim | gain=gaussian, timing=cauchy, bright=laplace, attack=laplace, reverb=gaussian | Timing-volatile, dynamically unstable |
| `controlled` | per-dim | gain=beta, timing=beta, bright=beta, attack=beta, reverb=beta | All dimensions bounded, no extremes |
| `salience_adaptive` | ω-conditioned | low=gaussian, mid=laplace, high=student_t df=2 | Tails grow with structural significance |

---

## Part 3 — Distribution Reference

Complete parameter catalogue for every supported and proposed distribution.

---

### gaussian

Standard multivariate normal. The only distribution that preserves
off-diagonal covariance structure from Σ.

| Parameter | Default | Status |
|-----------|---------|--------|
| — | — | No additional parameters |

Sampling: `x ~ N(μ, Σ)` (full covariance). All other distributions
sample independently per dimension using σ_i = √Σ_ii.

---

### laplace

Sharper peak, heavier tails than Gaussian. Scale b = σ/√2.

| Parameter | Default | Status | Complexity |
|-----------|---------|--------|------------|
| Per-dimension scale multiplier | 1.0 | **[new]** | easy |

---

### student_t

Gaussian with heavier tails controlled by degrees of freedom df.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Degrees of freedom | df | 3 | (0, ∞) | exposed | — |
| Per-dimension df | df_dims | null | (0, ∞) | **[new]** | easy once dist_dims exists |
| ω-driven df | df_fn | null | — | **[new]** df decreases as ω increases | medium |

df=1 → Cauchy. df→∞ → Gaussian.

---

### cauchy

student_t with df=1. No defined mean or variance.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Clip threshold | clip_sigma | 5.0 | (1, ∞) | **[new]** hardcoded | easy |

---

### uniform

All values in [-√3·σ, +√3·σ] equally likely. Matches Gaussian variance.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Range multiplier | √3 | (0, ∞) | **[new]** hardcoded | easy |
| Asymmetric range [lo_mult, hi_mult] | symmetric | — | **[new]** | medium |

---

### beta

Symmetric Beta(2,2) scaled to [μ-k·σ, μ+k·σ]. Bounded, smooth,
peaks at mean.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Shape parameter a | 2 | (0, ∞) | **[new]** hardcoded symmetric | easy |
| Shape parameter b | 2 | (0, ∞) | **[new]** hardcoded symmetric | easy |
| Range multiplier k | derived | (0, ∞) | **[new]** hardcoded | easy |

Setting a ≠ b produces a skewed Beta — a simple way to introduce
asymmetry without a separate distribution family.

---

### bimodal

Two mirrored Gaussians at μ ± sep·σ.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Pole separation | sep | 0.75 | (0, ∞) | **[new]** hardcoded | easy |
| Pole weight asymmetry [w_lo, w_hi] | [0.5, 0.5] | [0,1] | **[new]** always symmetric | easy |
| Number of modes | n_modes | 2 | {2, 3, 4} | **[new]** | hard |
| Per-dimension sep | sep_dims | null | — | **[new]** | easy once sep exposed |

---

### mixture

Gaussian base with rare large spikes drawn from a wide Gaussian.

| Parameter | Default | Range | Status | Complexity |
|-----------|---------|-------|--------|------------|
| Spike probability | mixture_p | 0.1 | [0,1] | exposed | — |
| Spike scale multiplier | spike_scale | — | (1, ∞) | **[new]** hardcoded | easy |
| Spike distribution | spike_dist | gaussian | categorical | **[new]** always Gaussian | medium |
| Number of components | n_components | 2 | {2,3,4} | **[new]** | medium |
| Component weights | comp_weights | [1-p, p] | simplex | **[new]** | medium |
| Component means | comp_means | [0, 0] | ℝ | **[new]** always centred | medium |
| Component scales | comp_scales | [σ, k·σ] | (0, ∞) | **[new]** | medium |

Full mixture model with n_components, comp_weights, comp_means, and
comp_scales subsumes all other distributions as special cases and
provides maximal flexibility at the cost of a much larger parameter space.

---

### skew_normal **[new]** — medium

Gaussian with skewness parameter. α=0 → standard Gaussian.
α > 0 → right-skewed (overshoots more). α < 0 → left-skewed.

| Parameter | Default | Range | Complexity |
|-----------|---------|-------|------------|
| Skewness | skew | 0 | (-∞, ∞) | medium |
| Per-dimension skewness | skew_dims | null | — | medium |
| ω-driven skewness | skew_fn | null | — | hard |

---

### asym_laplace **[new]** — medium

Laplace with different decay rates on each side of the mean.
Captures asymmetric jump tendencies — e.g. more likely to overshoot
than undershoot.

| Parameter | Default | Range | Complexity |
|-----------|---------|-------|------------|
| Left scale | b_left | σ/√2 | (0, ∞) | medium |
| Right scale | b_right | σ/√2 | (0, ∞) | medium |
| Per-dimension [b_left, b_right] | null | — | medium |

---

### truncated **[new]** — medium

Wraps any base distribution and resamples until within bounds.
More principled than post-hoc clipping.

| Parameter | Default | Range | Complexity |
|-----------|---------|-------|------------|
| Base distribution | base_dist | gaussian | categorical | medium |
| Lower bound (σ units) | trunc_lo | -3 | (-∞, 0) | medium |
| Upper bound (σ units) | trunc_hi | +3 | (0, ∞) | medium |
| Max resample attempts | max_attempts | 100 | integer | medium |
| Per-dimension bounds | trunc_dims | null | — | medium |

---

## Part 4 — Implementation Priority

Ranked by impact-to-effort ratio.

### Tier 1 — High impact, easy to implement

| Parameter | Section | Complexity | Why it matters |
|-----------|---------|------------|----------------|
| Q_base as 5-vector per dimension | B | easy | Gain and timing drift at different rates |
| Per-dimension dist_dims | F.2 | medium | Each dimension has a natural distribution family |
| Mean reversion target (non-zero) | G | easy | RW anchors to musically meaningful level |
| φ dimension mask + per-dim scale | D | easy | Lookahead influences timing and brightness |
| Covariance inflation inflate / inflate_dims | F.7 | easy | Simple expressive freedom knob |
| Innovation energy decay rate + window M | B | easy | Finer control over filter sensitivity history |
| Bimodal pole separation sep | F.1 | easy | Meaningful shape parameter |
| Breath period + amplitude | G | easy | Breathing walk more controllable |
| Physical limits [lo, hi] | I | easy | Range and safety control |
| Random seed | I | easy | Reproducible renderings |
| Output soft clipping | I | easy | Smoother boundary behaviour |
| Fade curve shape | H | easy | More natural regime transitions |
| Salience normalisation clamp | E | easy | Explicit ω ∈ [0,1] enforcement |
| Cauchy clip threshold | F (cauchy) | easy | Control over how extreme wild samples get |
| Beta shape parameters a, b | F (beta) | easy | Skew-free asymmetry within existing family |

### Tier 2 — High impact, medium effort

| Parameter | Section | Complexity | Why it matters |
|-----------|---------|------------|----------------|
| Salience-conditioned distribution | F.3 | medium | Tails grow at structural moments automatically |
| Per-dimension df, sep, mixture_p | F.2 | medium | Fine-grained per-dimension shape control |
| ω-driven step size (RW) | G | medium | Salience-aware random walk |
| Asymmetric distributions (skew_normal) | F.8 | medium | Directional expressive tendency |
| Truncated distributions | F.9 | medium | Principled boundary handling |
| Window decay weighting γ_w | C | easy | Recent markings count more |
| Per-parameter fade curves | H | medium | Each param transitions at its own rate |
| Time-varying distribution schedule | F.4 | medium | Planned expressive arc per regime |
| Per-dimension obs_weight | C | medium | Score followed differently per dimension |
| ξ per regime | D | easy | Different regimes pull toward future differently |
| Temporal ω smoothing | E | easy | Smoother Q envelope, less spiking |
| Regime-level distribution blending | F.5 | medium | Smooth blending across overlapping regimes |

### Tier 3 — Lower priority or high complexity

| Parameter | Section | Complexity | Notes |
|-----------|---------|------------|-------|
| Gaussian copula for non-Gaussian sampling | F.6 | hard | Statistically correct but complex |
| Full Q off-diagonal | B | hard | High impact, hard to author intuitively |
| Full A₁, A₂ matrices (cross-dim coupling) | A | hard | High impact, stability condition non-trivial |
| Lévy flight exponent | G | hard | Exotic, slow sampler |
| Fractional Brownian motion H | G | research | Long-range dependency, computationally expensive |
| Q adaptation via Mehra | B | hard | Principled but requires additional derivation |
| Conditional regime activation | H | hard | High value, major architectural change |
| Observation likelihood as student_t | C | hard | Robustness to outlier markings, requires UKF |
| State dimension d | I | hard | High architectural impact across all files |
| Riemannian blending of correlation matrices | H | hard | Mathematically correct, niche |

---

## Part 5 — Summary: Parameters by Status

### Currently exposed
A₁, A₂, A₁_dims, A₂_dims, Q_scale, f(ω) curve shape, η, N,
H(pattern), R(pattern), R_scale, obs_weight, λ, ξ, α, β, γ, δ,
dist, df, mixture_p, rw_scatter, step_size, drift, mr_dims,
boundary_mode, Corr, weight, fade_in, fade_out

### Proposed — easy to add
μ₀, Σ₀, Q_base (5-vector), Q_scale_dims, innovation energy decay rate,
innovation energy window M, K (lookahead window), φ dimension mask,
φ per-dim scale, φ non-linearity, ξ_regime, ω_threshold for φ,
local contrast window W, structural marking set, salience normalisation
clamp, ω non-linearity, temporal ω smoothing, bimodal sep, spike_scale,
mean reversion target, breath_period, breath_amp, breath_phase,
physical limits [lo, hi], random seed, clip threshold (cauchy),
inflate, inflate_dims, inflate_fn, range_mult (uniform), beta shape
params a and b, regime priority, output clipping method,
per-dim boundary_mode, stability constraint boolean, dimension names

### Proposed — medium effort
dist_dims, df_dims, sep_dims, mixture_p_dims, spike_scale_dims,
rw_scatter_dims, ω-conditioned distribution (dist_low/mid/high), df_fn,
tail_fn, distribution schedule, dist_ramp, dist_blend, per-parameter
fade curves, ω-driven step size (RW), step size schedule, skew_normal,
asym_laplace, truncated distribution, window decay γ_w, per-dimension
obs_weight, R off-diagonal, future pull direction, ω weight per regime,
position curve β(pos) shape, asymmetric uniform, n_modes (bimodal),
full mixture model (n_components, comp_weights, comp_means, comp_scales),
spike_dist, per-dim laplace scale multiplier

### Proposed — hard / research
Q off-diagonal (full 5×5), A₁/A₂ off-diagonal coupling, Gaussian copula,
t-copula, Lévy flight alpha, fractional Brownian motion H, Q adaptation
via Mehra, conditional regime activation, observation likelihood as
student_t (UKF), state dimension d, Riemannian blending of correlation
matrices, ω-driven skewness, n_modes > 2 (bimodal), custom salience
component (plugin)
