# Theoretical Foundation — Expressive Interpretation Engine

---

## 1. Problem Statement

A musical score is a symbolic sequence of instructions. It specifies *what*
to play but not *how* to play it. The gap between the symbolic instruction
and the acoustic realisation is where musical expression lives.

Consider a simple example. A score says *piano* at second 19. What gain
value should the audio engine use? The answer depends on:

- What dynamic level was being played before
- How the performance has been evolving — was it getting louder or quieter?
- What the surrounding markings say — is this *piano* a sudden drop or a
  gentle settling?
- What is coming later — is this *piano* the beginning of a long quiet
  passage, or a brief respite before a climax?
- What kind of piece this is — a delicate nocturne or a dramatic sonata?

None of this is encoded in the score marking itself. A human performer
integrates all of it unconsciously. This engine formalises that integration
as a probabilistic model.

### What the engine produces

Given a fixed, deterministic score, the engine produces a continuous stream
of expressive parameter values at each score event:

```
x(t) = [gain_db, brightness, timing_offset_ms, attack_shape, reverb_wet]ᵀ
```

These values vary across renderings in a musically coherent way. The
variation is not random noise — it emerges from a model that is sensitive
to history, context, and structure. The same score, run twice, produces
two different but equally valid interpretations.

### The gap between score and performance

```
SCORE                          PERFORMANCE
─────────────────────────────────────────────────────────

t=10s   mp  ──────────────►  gain=-18db, bright=0.45
t=19s   f   ──────────────►  gain=-4db,  bright=0.72    <- Run 1
t=22s   sfz ──────────────►  gain=+2db,  bright=0.90

t=10s   mp  ──────────────►  gain=-20db, bright=0.42
t=19s   f   ──────────────►  gain=-6db,  bright=0.68    <- Run 2
t=22s   sfz ──────────────►  gain=+1db,  bright=0.85

         ^                           ^
    fixed symbolic              varies each run,
    instructions                musically coherent
```

The score is identical across runs. The expressive parameters differ
because the model draws from probability distributions that are sensitive
to context and history.

### Design principles

- **Authored** — the distributions encode artistic choices, not statistics
- **Generative** — each rendering is different but internally consistent
- **Causal** — the model reads the score forward in time, like a performer
- **Extensible** — learnable from data without changing the architecture
- **Transparent** — every parameter has a clear musical interpretation

---

## 2. State Space Formulation

### 2.1 The hidden state

We model the expressive state of the performance at time t as a continuous
vector in d-dimensional space:

```
x(t) ∈ ℝ^d
```

This state is **hidden** — it is never directly observed. What we observe
are score markings. The state is our best estimate of the true expressive
level of the performance at each moment.

In the current implementation, d=5:

```
x(t) = [gain_db, brightness, timing_offset_ms, attack_shape, reverb_wet]ᵀ
         ───────   ──────────   ──────────────   ────────────   ─────────
         how loud  spectral     push/pull        sharp vs soft  space/depth
                   brightness   timing           onset
```

### 2.2 Hidden state vs observations

The fundamental distinction in this model:

```
                    HIDDEN                    OBSERVED
                 ┌──────────┐              ┌──────────────┐
                 │ x(t)     │              │ y(t)         │
                 │          │              │              │
                 │ gain_db  │   H matrix   │ "forte"      │
                 │ bright   │ ──────────►  │ "mp → f"     │
                 │ timing   │              │ "subito_p"   │
                 │ attack   │              │              │
                 │ reverb   │              └──────────────┘
                 └──────────┘
                      ^
                 what we want              what the score gives us
                 to estimate
```

The observation matrix H maps the hidden state space to the observation
space. It encodes what each marking implies about each state component.

### 2.3 The two sources of information

At each event, the state is updated by combining two things:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   SOURCE 1: History         SOURCE 2: Current observation  │
│   ─────────────────         ───────────────────────────    │
│   Where was the state?      What does the score say?       │
│   Where is it going?        How much do we trust it?       │
│                                                             │
│              ↓                           ↓                 │
│         TRANSITION                  OBSERVATION            │
│           MODEL                       MODEL                │
│              ↓                           ↓                 │
│              └──────────┬────────────────┘                 │
│                         ↓                                  │
│                   KALMAN UPDATE                            │
│                   (Bayesian fusion)                        │
│                         ↓                                  │
│                   NEW STATE x(t)                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

This predict-then-update structure is the defining characteristic of a
**Bayesian filter**, and specifically of the **Kalman filter** when the
distributions are Gaussian.

### 2.4 Why Gaussian distributions?

We choose Gaussian distributions for three reasons:

1. **Tractable** — the Kalman update equations are exact and closed-form
   for Gaussians. No approximation is needed.
2. **Expressive** — a Gaussian is fully described by mean μ and covariance Σ.
   The mean is the expected value. The standard deviation encodes freedom.
3. **Authored** — easy to hand-craft as expert priors. Saying "gain for
   this transition is centered at -3db with std 1.5" is musically intuitive.

```
What a Gaussian belief looks like over gain_db:

      probability
          │
     high │        ╭───╮
          │       ╱     ╲        <- Σ small (confident)
          │      ╱       ╲
          │─────╱─────────╲─────
          │
     high │    ╭─────────╮
          │   ╱           ╲      <- Σ large (uncertain)
          │  ╱             ╲
          │─╱───────────────╲───
          │
          └─────────────────────► gain_db
               -20  -10   0

   The peak is μ (best guess).
   The width is √Σ (uncertainty).
```

---

## 3. The Kalman Filter — Full Derivation

The Kalman filter (Kalman, 1960) is the optimal Bayesian estimator for
linear Gaussian state space models.

### 3.1 What the filter maintains

At every step, the filter maintains a Gaussian belief over the hidden state:

```
p(x(t) | all observations so far) = N(μ(t), Σ(t))
```

Where:
- `μ(t) ∈ ℝ^d` — the mean vector, our best guess of the state
- `Σ(t) ∈ ℝ^(d×d)` — the covariance matrix, our uncertainty

```
Evolution of belief across three steps:

Step t-1            Step t (predicted)     Step t (updated)
────────            ──────────────────     ────────────────

  ╭─╮                    ╭───╮                  ╭──╮
 ╱   ╲    predict       ╱     ╲    update       ╱    ╲
╱     ╲  ──────────►   ╱       ╲  ──────────►  ╱      ╲
│  μ  │   (widens)    │    μ̄   │  (narrows)   │   μ  │
╲     ╱               ╲       ╱               ╲      ╱
 ╲   ╱                 ╲     ╱                 ╲    ╱
  ╰─╯                    ╰───╯                  ╰──╯

confident            less confident          more confident
                     (before seeing          (after seeing
                      the marking)            the marking)
```

After each update, Σ always decreases — new evidence always reduces
uncertainty. After each prediction, Σ increases — projecting forward
introduces uncertainty.

### 3.2 Stage 1 — Prediction

Before observing any new marking, we project the current belief forward
using the transition model.

**The transition equation:**

```
x(t) = F · x(t-1) + w(t),    w(t) ~ N(0, Q)
```

Term by term:

| Symbol | Type | Meaning |
|--------|------|---------|
| `x(t)` | vector ℝ^d | The true state we are trying to estimate |
| `F` | matrix ℝ^(d×d) | Transition matrix — how state evolves (inertia) |
| `x(t-1)` | vector ℝ^d | Previous state |
| `w(t)` | vector ℝ^d | Process noise — random drift |
| `Q` | matrix ℝ^(d×d) | Process noise covariance — how much drift |

**Propagating the belief through the transition:**

```
μ̄(t) = F · μ(t-1)                    predicted mean
Σ̄(t) = F · Σ(t-1) · Fᵀ + Q          predicted covariance
```

The bar notation (μ̄, Σ̄) means "predicted but not yet updated."

**Why does Σ̄ grow?**

```
Σ̄(t) = F · Σ(t-1) · Fᵀ  +  Q
         ───────────────     ─
         existing            new uncertainty
         uncertainty         from process noise
         propagated forward
```

The prediction step always makes us less certain. We are projecting
into the unknown, and Q adds additional drift on top.

**Musical interpretation of Q:**

```
Q small                              Q large
───────                              ───────
State is sticky.                     State wanders freely.
Resists change between markings.     Can shift substantially.
Like a performer who holds their     Like a performer who lets
dynamic level until told otherwise.  their dynamic breathe.

Good for: stable, sustained          Good for: dramatic, volatile
          passages                             passages
```

Q can and should vary during the piece. See Section 6.

### 3.3 Stage 2 — Update

A score marking arrives. We treat it as noisy evidence about the true
state and use it to correct our prediction.

**The observation equation:**

```
y(t) = H · x(t) + v(t),    v(t) ~ N(0, R)
```

Term by term:

| Symbol | Type | Meaning |
|--------|------|---------|
| `y(t)` | vector ℝ^m | The observation (score marking encoded as numbers) |
| `H` | matrix ℝ^(m×d) | Observation matrix — maps state to observation space |
| `v(t)` | vector ℝ^m | Observation noise — how imprecise the marking is |
| `R` | matrix ℝ^(m×m) | Observation noise covariance — how much we trust the marking |

**The innovation:**

```
ν(t) = y(t) - H · μ̄(t)
        ────   ─────────
        what   what we
        we     expected
        saw
```

The innovation is the surprise — how much the marking deviated from
the prior prediction.

```
Example:

  Prior predicted gain around -10db.
  Score says forte → y encodes roughly -4db.
  Innovation ν = -4 - (-10) = +6db

  The marking is louder than expected.
  The filter will pull the state upward by K · 6db.
```

**The Kalman gain:**

```
K(t) = Σ̄(t) · Hᵀ · (H · Σ̄(t) · Hᵀ + R)⁻¹
        ────────────   ──────────────────────
        uncertainty    total uncertainty
        in state       in observation space
        projected to   (state + obs noise)
        obs space
```

K answers: *how much should I trust the new observation vs my prior?*

```
R small (trust marking closely):   K large  → observation dominates
R large (marking is ambiguous):    K small  → prior dominates

Limiting cases:
  R → 0:   K → H⁻¹   (state snaps exactly to what marking implies)
  R → ∞:   K → 0     (observation completely ignored)
```

**Musical interpretation of R:**

```
R small                              R large
───────                              ───────
Follow the marking literally.        Let current state resist.
A subito forte snaps to loud.        An mp nudges gently.
Like a disciplined performer         Like an expressive performer
who executes markings precisely.     who interprets freely.

Good for: structural markings        Good for: ambiguous markings
          (sfz, subito, fp)                    (mp, mf, gradual cresc)
```

**The update equations:**

```
μ(t)  = μ̄(t) + K(t) · ν(t)
         ────   ────────────
         prior  correction
                (K scales the surprise)

Σ(t)  = (I - K(t) · H) · Σ̄(t)
          ─────────────   ────
          reduction        prior
          factor           uncertainty
          (always < 1)
```

After the update, uncertainty always decreases. New evidence always
helps.

### 3.4 The full predict-update cycle

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌─────────────┐                                           │
│  │  x(t-1)     │  Current state belief N(μ(t-1), Σ(t-1)) │
│  └──────┬──────┘                                           │
│         │                                                   │
│         │  PREDICT                                          │
│         │  μ̄(t) = F · μ(t-1)                              │
│         │  Σ̄(t) = F · Σ(t-1) · Fᵀ + Q                    │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │  prior      │  Predicted belief N(μ̄(t), Σ̄(t))         │
│  │  (wider)    │                                           │
│  └──────┬──────┘                                           │
│         │                    ┌──────────────┐              │
│         │                    │  y(t)        │              │
│         │  UPDATE            │  score mark  │              │
│         │◄───────────────────┤  encoded     │              │
│         │  ν(t) = y - H·μ̄   └──────────────┘              │
│         │  K(t) = ...                                      │
│         │  μ(t) = μ̄ + K·ν                                 │
│         │  Σ(t) = (I-K·H)·Σ̄                               │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │  x(t)       │  Updated belief N(μ(t), Σ(t))            │
│  │  (narrower) │  → sampled to produce output              │
│  └──────┬──────┘                                           │
│         │                                                   │
│         └──────────────────────────────────► next step     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Second-Order Autoregressive Transition — AR(2)

### 4.1 The problem with first-order transitions

A first-order transition (F=I) models a state that tends to stay where
it is. It has no sense of direction. It cannot distinguish between:

```
Case A: x(t-2)=-70, x(t-1)=-50  →  moving UPWARD (getting louder)
Case B: x(t-2)=-30, x(t-1)=-50  →  moving DOWNWARD (getting quieter)
```

Both cases have x(t-1)=-50, so a first-order model gives the same prior
for x(t) in both cases. But a performer would play them very differently.

### 4.2 The AR(2) model

The second-order autoregressive transition adds memory of two steps back:

```
x(t) = A₁ · x(t-1) + A₂ · x(t-2) + w(t),    w(t) ~ N(0, Q)
```

Where:
- `A₁` weights the contribution of the state one step back
- `A₂` weights the contribution of the state two steps back

**Musical interpretation of momentum:**

```
x(t-2) = -70db,  x(t-1) = -50db

Velocity = x(t-1) - x(t-2) = +20db per step  (moving upward)

AR(2) prior for x(t):
  = A₁ · (-50) + A₂ · (-70)
  ≈ -30db  (continues the upward trajectory)

Now a "piano" marking arrives, pulling toward -60db.
The innovation = -60 - (-30) = -30db  (large — fighting momentum)
The filter is torn between trajectory and instruction.
The result will be somewhere between -30 and -60,
weighted by how much we trust the marking (R).
```

This tension between momentum and instruction is musically expressive
and realistic.

### 4.3 Implementing AR(2) as standard Kalman

AR(2) is not directly a first-order system, but it becomes one by
**augmenting the state vector** to include the previous state:

```
X(t) = [x(t), x(t-1)]ᵀ  ∈ ℝ^(2d)
         ────   ────────
         current  previous
         state    state (copied)
```

The augmented transition matrix:

```
F = [ A₁  A₂ ]
    [ I    0  ]
    ─────────────────────────────────────
    top row:    x(t) = A₁·x(t-1) + A₂·x(t-2)
    bottom row: new x(t-1) = old x(t)  [just copy it]
```

The standard Kalman equations apply unchanged to X(t). This is a
standard engineering trick — any AR(p) model can be written as a
first-order state space model by augmentation.

**The augmented process noise:**

```
Q_aug = [ Q   0 ]
        [ 0   0 ]
```

Only the current state component receives process noise. The copied
previous state is deterministic — it is just a memory slot.

### 4.4 Diagram — AR(2) state evolution

```
                        w(t) ~ N(0,Q)
                              │
                              ▼
x(t-2) ──── A₂ ────►  ┌─────────────┐
                       │             │
x(t-1) ──── A₁ ────►  │    x(t)     │ ──────► to observation model
                       │             │
                       └─────────────┘

And at the next step:
x(t-1) becomes x(t-2)
x(t)   becomes x(t-1)

The system has a two-step memory. It always knows where it was
and where it came from.
```

---

## 5. Window Observation Model

### 5.1 Context changes meaning

The same marking carries different information depending on what came
before. Consider these two sequences both ending in *piano*:

```
Sequence A:  pp ──► p ──► mp ──► [piano]
             ↑ rising trajectory ↑
             "piano" is INTERRUPTING an ascent → dramatic reversal

Sequence B:  ff ──► f ──► mf ──► [piano]
             ↑ falling trajectory ↑
             "piano" is CONTINUING a descent → natural arrival
```

A single-marking observation cannot distinguish these. A window
observation encodes the full context.

### 5.2 The window observation vector

At each step, the observation is the last N markings concatenated:

```
y(t) = [enc(m(t)), enc(m(t-1)), ..., enc(m(t-N+1))]ᵀ
```

Each marking is encoded as its ordinal rank on the dynamic ladder:

```
Dynamic ladder encoding:
  ppp=0,  pp=1,  p=2,  mp=3,  mf=4,  f=5,  ff=6,  fff=7

Structural markings (encoded separately as binary indicators):
  sfz=1/0,  fp=1/0,  subito_f=1/0,  subito_p=1/0
```

**Example with N=3:**

```
Score:    ... mp  →  mf  →  f  →  [piano]  →  ...
                                      ↑
                                   t = now

Window observation y(t) = [enc(piano), enc(f), enc(mf)]
                         = [2,          5,      4      ]

The observation vector says: "I just saw piano after f after mf"
The model reads this as: dramatic downward reversal from an ascending
context.
```

### 5.3 Time-varying H and R

Because the observation depends on the window, H and R become
**time-varying** — they change at every step depending on context:

```
H(t) = H(m(t), m(t-1), ..., m(t-N+1))
R(t) = R(m(t), m(t-1), ..., m(t-N+1))
```

These are looked up from the transition table — one entry per window
pattern. For patterns not explicitly defined, a default entry is used.

```
Lookup illustration:

  Window pattern          H(t) and R(t) entry
  ──────────────          ───────────────────
  (mp → f)         ──►   moderate pull, medium trust
  (p  → f)         ──►   strong pull,   high trust
  (ff → piano)     ──►   very strong pull, very high trust
  (mp → mp)        ──►   weak pull,     low trust (stable context)
```

The Kalman equations are unchanged. Time-varying H and R are handled
simply by substituting the current values at each step.

---

## 6. Combined Q Adaptation — Drama and Volatility

### 6.1 Why Q should vary

The process noise Q determines how freely the state can move between
events. A single fixed Q is musically inappropriate:

```
A quiet, stable passage      A dramatic, turbulent passage
──────────────────────────   ──────────────────────────────
State should resist change.  State should be free to move.
Low Q.                       High Q.
```

We want Q to adapt. But what should drive the adaptation?

### 6.2 Two sources — drama and volatility

```
Q(t) = Q_base  ·  drama(t)  ·  (1 + η · volatility(t))
        ───────    ─────────    ─────────────────────────
        baseline   what the     what the filter has
        (authored) score says   been experiencing
                   about this   recently
                   passage
```

The key insight: **drama anchors volatility to musical reality**.
Volatility alone can spiral — large innovations increase Q, making the
filter more sensitive, producing more innovations. Drama prevents this
by grounding Q in the score structure. A structurally quiet passage
keeps Q low even if the filter has been surprised recently.

### 6.3 Drama — score-derived

Drama is computed from the score before rendering begins:

```
drama(t) = α · dynamic_distance(t)
         + β · is_structural(t)
         + γ · local_contrast(t)
         + δ · is_phrase_boundary(t)
```

**Component 1 — Dynamic distance:**

How large is the jump between consecutive markings?

```
dynamic_distance(t) = |rank(m(t)) - rank(m(t-1))| / 7

Examples:
  pp  → fff:   |1 - 6| / 7 = 0.71   (very large jump)
  mp  → mf:    |3 - 4| / 7 = 0.14   (small step)
  mf  → mf:    |4 - 4| / 7 = 0.00   (no change)
```

**Component 2 — Structural marking:**

Some markings are inherently dramatic regardless of distance:

```
is_structural(t) = 1  if m(t) ∈ {sfz, fp, subito_f, subito_p}
                 = 0  otherwise
```

**Component 3 — Local contrast:**

Is this marking unusual for its local context?

```
local_contrast(t) = |rank(m(t)) - local_mean(t)| / 7

local_mean(t) = average rank of markings in window [t-W, t+W]

A forte in the middle of a quiet passage has high local contrast.
A forte in the middle of a loud passage has low local contrast.
```

**Component 4 — Phrase boundary:**

```
is_phrase_boundary(t) = 1  if t is the first event of a phrase
                       = 0  otherwise
```

Phrase boundaries are structurally significant even when the dynamic
jump is small.

**Combining:**

```
α + β + γ + δ = 1   (the weights sum to 1)

Example weighting:
  α = 0.4  (distance matters most)
  β = 0.3  (structural markings matter a lot)
  γ = 0.2  (local contrast matters somewhat)
  δ = 0.1  (phrase boundaries matter least)
```

These weights are artistic choices — the user defines them.

### 6.4 Volatility — innovation-derived

Volatility is computed from the recent history of innovations:

```
volatility(t) = (1/M) Σₖ₌₁ᴹ  ||ν(t-k)||²  ·  decay^k
                               ────────────    ───────
                               squared norm    older innovations
                               of innovation   matter less
                               (how surprised
                               we were)
```

- `M` is the memory window length — how far back to look
- `decay ∈ (0,1]` downweights older innovations exponentially
- `||ν||²` is the squared Euclidean norm of the innovation vector

```
Timeline example:

  t-3: small innovation (0.5)²  · decay³  →  contributes little
  t-2: large innovation (4.0)²  · decay²  →  contributes a lot
  t-1: medium innovation (1.5)² · decay¹  →  contributes moderately

  volatility = weighted average of these squared surprises
```

**Philosophical note:** A large innovation could mean the music is
genuinely dramatic, or it could mean the model was poorly calibrated.
By multiplying with drama(t), we ensure that volatility only amplifies
Q when the score also declares the passage dramatic. The score keeps
the filter honest.

### 6.5 Diagram — combined Q adaptation

```
  SCORE (computed before rendering)
  ────────────────────────────────
  dynamic_distance(t)  ─┐
  is_structural(t)     ─┤─► drama(t) ─────────────────────────┐
  local_contrast(t)    ─┤                                     │
  is_phrase_boundary(t)─┘                                     │
                                                               │
  FILTER HISTORY (computed during rendering)                  │
  ──────────────────────────────────────────                  │
  ν(t-1), ν(t-2), ..., ν(t-M) ──► volatility(t) ──► ×η +1 ──┤
                                                               │
  Q_base (authored parameter) ──────────────────────────────── ┤
                                                               │
                                                               ▼
                                                    Q(t) = Q_base
                                                           · drama(t)
                                                           · (1 + η·vol)
```

---

## 7. Fuzzy Future Prior — Graded Score Lookahead

### 7.1 What a performer knows

A performer reading a score does not have a blank future. They have a
**graded, decaying knowledge** of what is coming:

```
Performer's knowledge of the future:

Now    +1    +2    +3    +5    +10   +20   ...end
 │      │     │     │     │     │     │     │
 ▼      ▼     ▼     ▼     ▼     ▼     ▼     ▼
clear  clear  good  ok    vague faint  ───  finale
                                             (always
                                              sensed)
```

Important upcoming events — a grand climax, a sudden subito — punch
through the decay and remain influential even from far away. A gentle
*mp* three steps ahead fades quickly.

This is not the RTS smoother (which knows all future events with equal
precision). It is a **causal model with decaying future influence** —
the filter runs forward in time, informed by a fading awareness of
upcoming events.

### 7.2 The salience function

Not all future events are equally worth knowing about:

```
salience(t) = α · dynamic_distance(t)
            + β · is_structural(t)
            + γ · local_contrast(t)
            + δ · is_phrase_boundary(t)
```

Same formula as drama(t) — this is intentional. Drama and salience
measure the same thing: how important is this event? Drama measures
it looking backward (how dramatic was this step). Salience measures it
looking forward (how much should this future event influence now).

### 7.3 Decaying future weights

```
future_pull(t) = Σₖ₌₁ᴷ  λᵏ  ·  salience(t+k)  ·  enc(m(t+k))
                          ──     ─────────────     ────────────
                          decay  importance         marking value
                          (less  (punches           (what the
                          with   through            marking says)
                          distance) decay)
```

Where λ ∈ (0,1) is the **familiarity parameter**:

```
λ = 0.9  →  Performer knows the piece well
            Near future: strong. Far future: still noticeable.
            Like a professional playing a familiar concerto.

λ = 0.5  →  Knows it moderately
            Near future: present. Far future: almost gone.

λ = 0.2  →  Essentially sight-reading
            Only the very next marking has any influence.
            Everything beyond 3-4 steps is ignored.
```

**Salience amplifying a distant event:**

```
Without salience:
  λ^10 = 0.9^10 = 0.35  →  event 10 steps ahead has 35% weight

With salience(t+10) = 0.9 (grand finale):
  λ^10 · 0.9 = 0.31  →  still substantial pull from far away

With salience(t+10) = 0.1 (gentle mp):
  λ^10 · 0.1 = 0.035  →  barely felt
```

A grand finale is sensed throughout the piece. A routine dynamic step
fades quickly.

### 7.4 Incorporating future pull into the prediction

The future pull enters as an additive bias on the prior mean:

```
μ̄(t) = F · X(t-1)  +  ξ · future_pull(t)
         ──────────     ──────────────────
         AR(2)          gentle pull toward
         transition      what is coming
```

ξ is a scaling parameter — how strongly the future knowledge biases
the prior. Small ξ means the future is a whisper. Large ξ means it
is a strong influence.

---

## 8. Structural Prior — Piece Position and Character

### 8.1 Piece position

The same marking means different things at different points in the piece:

```
                    Piece timeline

  t=0                 t=0.5                t=1.0
   ├───────────────────────┬────────────────────┤
   │                       │                    │
  start               middle               end
  (opening)           (development)        (finale)

  A "forte" here      A "forte" here       A "forte" here
  is an opening       is a passing         is probably the
  statement.          event.               climax. Play it
                                           bigger.
```

We encode this as a position-dependent drift on the prior mean:

```
μ̄(t) += α(pos(t)) · μ_direction
          ─────────   ────────────
          position     a vector in
          curve        state space
          (e.g. peaks  pointing toward
          near end)    louder/brighter
```

And a position-dependent scaling of Q:

```
Q(t) *= β(pos(t))
         ─────────
         large near climaxes (state free to reach extremes)
         small during stable passages (state is settled)
```

Where:

```
pos(t) = t_seconds / total_duration  ∈ [0, 1]
```

### 8.2 Piece character

A **piece character** is a named configuration of model parameters
that shifts the expressive personality of the entire rendering:

```
character = (A₁, A₂, Q_base, R_base, λ, η)
```

| Character | A₁ | A₂ | Q_base | R_base | λ | Feel |
|-----------|----|----|--------|--------|---|------|
| `dramatic` | 0.8I | 0.1I | large | large | 0.7 | volatile, responsive |
| `lyrical` | 0.6I | 0.3I | small | medium | 0.8 | smooth, momentum-driven |
| `sparse` | 0.9I | 0.0I | tiny | small | 0.4 | static, literal |
| `turbulent` | 0.5I | 0.2I | large | large | 0.3 | unpredictable |

**Blending characters over time:**

Multiple characters can be active simultaneously with time-varying weights:

```
θ(t) = w₁(t) · θ_dramatic + w₂(t) · θ_lyrical,    w₁ + w₂ = 1

Timeline example:
  t=0.0–0.3:  w_lyrical=0.9,  w_dramatic=0.1   (gentle opening)
  t=0.3–0.7:  w_lyrical=0.5,  w_dramatic=0.5   (building tension)
  t=0.7–1.0:  w_lyrical=0.1,  w_dramatic=0.9   (dramatic finale)
```

The character blend is encoded in the score alongside the dynamic markings.

---

## 9. Complete Model — Every Step Laid Out

At each score event t, the following sequence executes in order:

### Pre-rendering pass (runs once before rendering begins)

```
For every event t in the score:
  pos(t)          ← t_seconds / total_duration
  drama(t)        ← α·distance(t) + β·structural(t) + γ·contrast(t) + δ·boundary(t)
  salience(t)     ← same formula (used when this event is a future event)
  future_pull(t)  ← Σₖ₌₁ᴷ  λᵏ · salience(t+k) · enc(m(t+k))
```

### Per-event rendering loop

**Step 1 — Compute adaptive Q:**

```
volatility(t)   ← (1/M) Σₖ ||ν(t-k)||² · decay^k
Q(t)            ← Q_base · drama(t) · (1 + η · volatility(t)) · β(pos(t))
```

**Step 2 — Prediction:**

```
X̄(t)  ← F · X(t-1)                           AR(2) transition
μ̄(t)  ← X̄(t) + ξ · future_pull(t)            add future pull
Σ̄(t)  ← F · Σ(t-1) · Fᵀ + Q(t)              propagate uncertainty
```

**Step 3 — Build observation:**

```
y(t)  ← [enc(m(t)), enc(m(t-1)), ..., enc(m(t-N+1))]ᵀ
H(t)  ← lookup(window pattern)
R(t)  ← lookup(window pattern)
```

**Step 4 — Update:**

```
ν(t)  ← y(t) - H(t) · μ̄(t)                   innovation
K(t)  ← Σ̄(t)·H(t)ᵀ · (H(t)·Σ̄(t)·H(t)ᵀ + R(t))⁻¹   Kalman gain
μ(t)  ← μ̄(t) + K(t) · ν(t)                   updated mean
Σ(t)  ← (I - K(t)·H(t)) · Σ̄(t)              updated covariance
```

**Step 5 — Store innovation, sample, output:**

```
store ν(t) in innovation history
x(t)  ~ N(μ(t), Σ(t))                         sample the state
pass x(t) to v1 audio engine
```

### Full data flow diagram

```
SCORE (fixed)
     │
     ├──► pre-rendering pass
     │         │
     │         ├──► drama(t) for all t
     │         ├──► salience(t) for all t
     │         └──► future_pull(t) for all t
     │
     └──► per-event loop ──────────────────────────────────────┐
                │                                              │
         ┌──────▼──────┐                                       │
         │ innovation  │◄── ν(t-1), ν(t-2), ...              │
         │ history     │                                       │
         └──────┬──────┘                                       │
                │ volatility(t)                                │
                ▼                                              │
         ┌─────────────┐                                       │
         │   Q(t)      │◄── drama(t), pos(t), Q_base          │
         └──────┬──────┘                                       │
                │                                              │
         ┌──────▼──────┐                                       │
         │  PREDICT    │◄── F, future_pull(t)                 │
         │  μ̄, Σ̄      │                                       │
         └──────┬──────┘                                       │
                │                                              │
         ┌──────▼──────┐                                       │
         │  UPDATE     │◄── y(t), H(t), R(t)                  │
         │  μ, Σ       │    (window observation)               │
         └──────┬──────┘                                       │
                │                                              │
         ┌──────▼──────┐                                       │
         │  sample     │                                       │
         │  x(t)       │──► v1 audio engine                   │
         └──────┬──────┘                                       │
                │                                              │
                └──────────────────────────────────────────────┘
                              feedback to next step
```

---

## 10. Expert Elicitation — Designing the Distributions

### 10.1 What to define

The model has the following free parameters that encode musical intuition:

| Parameter | What it controls | Where defined |
|-----------|-----------------|---------------|
| `A₁, A₂` | AR(2) trajectory coefficients | config.yaml / character |
| `Q_base` | Baseline process noise | config.yaml / character |
| `R(window)` | Trust in each marking window | transition_table.yaml |
| `H(window)` | What each window implies about state | transition_table.yaml |
| `λ` | Future familiarity decay | config.yaml |
| `η` | Volatility mixing weight | config.yaml |
| `α,β,γ,δ` | Drama/salience component weights | config.yaml |
| `ξ` | Future pull scaling | config.yaml |
| `character` | Named parameter bundle | transition_table.yaml |

### 10.2 How to think about R — three questions

For each window pattern, ask three questions:

```
1. How dramatic is this transition?
   pp → fff:  very dramatic  → small R (follow it closely)
   mp → mf:   gentle step    → large R  (let context dominate)

2. How structurally marked is it?
   subito_f:  very explicit  → very small R
   cresc:     gradual        → medium R

3. How ambiguous is the musical context?
   After a long stable passage:  more ambiguous  → larger R
   Mid-phrase climax:            clear intent    → smaller R
```

### 10.3 How to think about Q_base

```
Ask: how much should the state drift between marked events?

Sparse score (few markings, long silences):
  → Large Q_base. State needs freedom to evolve between marks.

Dense score (markings every few seconds):
  → Small Q_base. Markings guide the state continuously.

For your project:
  Start with Q_base = diag(4.0, 0.01, 25.0, 0.01, 0.01)
  (gain can drift 2db, brightness barely, timing 5ms, etc.)
  Then adjust by listening.
```

---

## 11. Key References

### Foundational
- Kalman, R.E. (1960). A New Approach to Linear Filtering and Prediction
  Problems. *Journal of Basic Engineering*, 82(1), 35–45.
- Welch, G. & Bishop, G. (2006). An Introduction to the Kalman Filter.
  UNC Chapel Hill TR95-041. **[freely available as PDF — start here]**

### Autoregressive models
- Hamilton, J.D. (1994). *Time Series Analysis*. Princeton University
  Press. Chapters 1–3.

### Adaptive filtering
- Mehra, R.K. (1970). On the Identification of Variances and Adaptive
  Kalman Filtering. *IEEE Transactions on Automatic Control*, 15(2).
- Mohamed, A.H. & Schwarz, K.P. (1999). Adaptive Kalman Filtering for
  INS/GPS. *Journal of Geodesy*, 73(4).

### Time-varying observation models
- Bar-Shalom, Y., Li, X.R. & Kirubarajan, T. (2001). *Estimation with
  Applications to Tracking and Navigation*. Wiley.

### Music performance research
- Friberg, A. (1995). A Quantitative Rule System for Musical Performance.
  PhD thesis, KTH Royal Institute of Technology.
- Widmer, G. & Goebl, W. (2004). Computational Models of Expressive Music
  Performance: The State of the Art. *Journal of New Music Research*, 33(3).
- Cancino-Chacón, C. et al. (2018). Computational Models of Expressive
  Music Performance: A Comprehensive and Critical Review.
  *Frontiers in Digital Humanities*. **[freely on arXiv]**

### Closest architectural precedent
- Tokuda, K. et al. (2000). Speech Parameter Generation Algorithms for
  HMM-based Speech Synthesis. *ICASSP 2000*.
- Zen, H., Tokuda, K. & Black, A. (2009). Statistical Parametric Speech
  Synthesis. *Speech Communication*, 51(11).

### Dataset (for future training)
- Hawthorne, C. et al. (2019). Enabling Factorized Piano Music Modeling
  and Generation with the MAESTRO Dataset. *ICLR 2019*. [arXiv:1810.12247]

### Python implementation
- Labbe, R. Kalman and Bayesian Filters in Python.
  **[github.com/rlabbe — free Jupyter book, best practical start]**
- filterpy library: github.com/rlabbe/filterpy
