# Live Visualization Reference

> This document catalogues all proposed live visualizations for the V2
> engine, organized by what they show, which timescale they operate at,
> and which screen they belong to.
>
> Two screens are assumed:
> - **Interpreter screen** — technically literate audience, shows the
>   probabilistic model directly. Precision over aesthetics.
> - **Concerto screen** — exhibition visitors and musicians, shows the
>   model as a living visual artifact. Aesthetics and precision coexist.
>
> Three timescales:
> - **Event-level** — updates at each score event (every few seconds)
> - **Rendering-level** — updates continuously during playback (~60fps)
> - **Session-level** — accumulates over the full duration of a piece

---

## 1. Marginal Gaussians — Prior vs Posterior

**What it shows:** The five marginal distributions N(μᵢ, Σᵢᵢ) drawn as
density curves for each expressive dimension. The prior (μ̄, Σ̄) is shown
as a ghost curve behind the solid posterior. The correction step is
visible as the ghost shifting toward the solid.

**Extension:** Draw the actual sample x(t) as a vertical tick on each
curve at the moment it is drawn. Over multiple events, ticks accumulate
on the curve — showing the empirical sampling history against the
theoretical density. A heavy-tailed regime produces ticks scattered far
into the margins; a conservative regime clusters them near the mean.

**Live behavior:** At each score event both curves update simultaneously.
The posterior narrows after update; the prior widens after prediction.

**Timescale:** Event-level.

**Screen:** Interpreter (primary). Concerto (as a painterly layer).

**Complexity:** Low — already prototyped in the interpreter screen.

**What it tells you:** Where the filter believes each parameter is, how
uncertain it is, and whether the current sample was typical or an outlier.

---

## 2. Kalman Gain Heatmap — K(t)

**What it shows:** The 5×5 Kalman gain matrix K(t) rendered as a color
grid. High values mean the observation is dominating that dimension; low
values mean the prior is dominating. The diagonal shows per-dimension
trust; off-diagonal entries would show cross-dimension influence once
non-diagonal Q or R are supported.

**Extension:** Animate the cell transitions — fade from the previous
value to the new one over ~300ms rather than snapping. Makes the filter's
decision-making visible as a process rather than a state.

**Live behavior:** Updates at each score event.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low — already prototyped.

**What it tells you:** At this event, did the filter trust the score
marking or its own momentum? Which dimensions were most affected by the
observation?

---

## 3. Innovation Trace — ν(t)

**What it shows:** The innovation vector ν(t) = y(t) − Hμ̄(t) per
dimension as a scrolling time series. A well-calibrated filter produces
ν that oscillates around zero with no autocorrelation — white noise.
A drifting filter shows systematic trends.

**Extension:** Add a running autocorrelation indicator per dimension — a
single scalar measuring whether recent innovations are correlated. If it
drifts from zero the filter is miscalibrated. This is the Mehra
diagnostic made visible in real time.

**Live behavior:** Scrolls rightward at each score event.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low — already prototyped. Autocorrelation indicator is
easy to add.

**What it tells you:** Is the filter surprised? Is it systematically
wrong in one direction? Is the observation model well-calibrated?

---

## 4. AR(2) Phase Portrait

**What it shows:** x(t) on the horizontal axis against x(t-1) on the
vertical axis, for one or more dimensions. Each event is a point
connected to the previous by a line. The trajectory traces a path in
this 2D phase space.

The attractor geometry of the AR(2) process becomes visible directly:
a stable regime with high A₁ produces smooth inward-curling trajectories;
a turbulent regime produces jagged, wide paths; a bipolar regime produces
figure-eight loops.

**Extension:** Show three panels simultaneously, one per natural dimension
pair: (gain_db × brightness), (timing × attack), (reverb × brightness).
Color the trail by age — recent points bright, older points fading.

**Live behavior:** A new point is added and connected at each score event.
The trail fades over time.

**Timescale:** Event-level with session-level accumulation.

**Screen:** Interpreter and Concerto. On the Concerto screen the trail
can be rendered as ink on wet paper — the trajectory as a calligraphic
stroke that fades slowly.

**Complexity:** Low.

**What it tells you:** The momentum character of the current regime.
Whether the state is converging, diverging, or cycling. The geometry
of the piece-regime interaction over time.

---

## 5. State Trajectory — 5D Projected to 2D

**What it shows:** The full 5D posterior mean μ(t) projected onto two
chosen dimensions as a moving point. The covariance ellipse (1σ and 2σ)
is drawn around it. A trail shows recent history.

**Extension:** Let the user choose which two dimensions to project onto
interactively. Provide three fixed panels showing the three natural
pairs simultaneously.

**Live behavior:** The point moves and the ellipse reshapes at each score
event. The ellipse shrinks after the update step and blooms after the
predict step.

**Timescale:** Event-level.

**Screen:** Interpreter (with axis labels and ellipse annotations).
Concerto (as floating organism — the ellipse breathing without labels).

**Complexity:** Medium. The dimension selector requires UI work.

**What it tells you:** Where the full expressive state is, how certain
the filter is, and which direction it is moving.

---

## 6. Structural Salience Score — ω(t) Backdrop

**What it shows:** The full ω curve over the entire score duration,
displayed as a static waveform or bar chart. Since ω is pre-computed
before rendering begins, the entire future is known and can be shown.
A moving playhead indicates the current position.

**Why it is unique:** This is the only visualization where the future
is visible. The viewer can see upcoming ω spikes — structural events —
before the filter reaches them. High spikes signal where Q will increase
and where the most expressive variation will occur.

**Extension:** Color the ω waveform by the dominant ω component at each
event — blue for dynamic_distance, orange for structural_marking, green
for local_contrast, purple for phrase_boundary. The viewer can read which
kind of structural significance is driving each spike.

**Live behavior:** The playhead moves. The waveform is static.

**Timescale:** Session-level backdrop with event-level playhead.

**Screen:** Both. Interpreter with component color coding. Concerto as
a horizon line — the landscape of the piece laid flat.

**Complexity:** Low.

**What it tells you:** The structural shape of the piece. Where the
model expects intensity. How much of the piece remains. What kind of
event is coming next.

---

## 7. Lookahead Prior — φ(t) Horizon

**What it shows:** A bar chart per dimension showing the current φ
vector — the salience-weighted decaying sum of future events pulling
the prior mean. The bars grow as a high-salience event approaches and
collapse after it passes.

**Extension:** Decompose φ into its individual terms — show each upcoming
event as a separate bar, decaying with distance. The viewer can see that
it is event i+2 specifically dominating the pull rather than i+1 or i+3.
This makes the familiarity parameter λ directly legible: high λ produces
many visible bars; low λ shows only the nearest event.

**Live behavior:** Updates at each score event. The bars pulse before
climaxes and collapse after.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low.

**What it tells you:** What the model is anticipating right now. How
much of the prior mean is being pulled by future events vs driven by
momentum. Whether λ is high (far lookahead) or low (sight-reading).

---

## 8. Process Noise Envelope — Q(t)

**What it shows:** A scrolling trace of Q_ii(t) per dimension — the
adaptive process noise level over time. Since Q depends on both ω (score
structure) and ε (filter history), it combines symbolic and statistical
information in one signal.

**Extension:** Overlay ω(t) and ε(t) on the same axis in different
colors. The viewer can read which driver is dominating at any moment —
whether Q is high because the score is structurally intense (ω) or
because the filter has been recently surprised (ε) or both.

**Live behavior:** Scrolls at each score event.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low.

**What it tells you:** How free the state is to move right now. Whether
the filter is in a tight or loose operating mode. The interaction between
symbolic score structure and statistical filter history.

---

## 9. Innovation Energy — ε(t)

**What it shows:** A scrolling trace of ε(t) — the exponentially
weighted squared innovation norm. Shows how surprised the filter has
been recently. Spikes after unexpected markings, decays between them.

**Extension:** Mark the individual innovation events that contributed most
to the current ε as vertical ticks on the trace, so the viewer can see
which specific score events caused the filter to become more uncertain.

**Live behavior:** Scrolls at each score event.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low.

**What it tells you:** The recent statistical history of the filter.
Whether the process has been behaving erratically. Whether Q is being
inflated by genuine surprise or by a structural passage.

---

## 10. Sample Scatter — Empirical vs Theoretical

**What it shows:** For each dimension, a dot is plotted at position
x_i(t) against time t at each event. Over time a cloud of dots
accumulates. The theoretical posterior density N(μᵢ, Σᵢᵢ) is drawn
as a shaded band — the region within 1σ and 2σ of the mean.

**Live behavior:** A new dot appears at each event. The band reshapes
as the posterior evolves.

**Timescale:** Session-level accumulation with event-level updates.

**Screen:** Interpreter.

**Complexity:** Medium.

**What it tells you:** Whether the sampling distribution matches the
posterior. If dots cluster near the mean the regime is conservative.
If they spread into the tails the distribution is heavy-tailed. If
they are systematically offset the filter has a bias. All three are
diagnostically useful over a full session.

---

## 11. Regime Blend Timeline

**What it shows:** A stacked area chart across the full score timeline
showing the normalized effective weight w_eff(t) of each active regime.
When two regimes overlap during a fade transition, the areas blend
smoothly. The current position is marked by a playhead.

**Extension:** Color-code the areas by process model type — one color
family for Kalman regimes, another for Random Walk. The viewer can
immediately see which parts of the piece are score-driven and which are
free. Fade overlaps appear as mixed colors.

**Live behavior:** Playhead moves through a static chart.

**Timescale:** Session-level backdrop with event-level playhead.

**Screen:** Both. Interpreter with labels. Concerto as a color field —
the piece's interpretive landscape laid flat.

**Complexity:** Low.

**What it tells you:** The compositional structure of the interpretation
plan. When transitions occur. How long each regime governs. Where
Kalman and Random Walk overlap.

---

## 12. Full Covariance Matrix — Σ(t)

**What it shows:** The full 5×5 posterior covariance matrix Σ(t) as a
heatmap. The diagonal shows per-dimension uncertainty; off-diagonal
entries show accumulated correlations. The matrix breathes — growing
after prediction, shrinking after update.

**Extension:** Show the matrix at three moments simultaneously:
Σ(t-1) (previous posterior), Σ̄(t) (current prior after predict),
Σ(t) (current posterior after update). The predict–update cycle becomes
visible as a three-panel animation.

**Live behavior:** Updates at each score event. The breathing rhythm
of predict-then-update is the primary visual motion.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low.

**What it tells you:** The full uncertainty structure of the filter,
including dimension correlations. Whether the filter is confident or
uncertain globally. Whether specific dimensions are tightly coupled.

---

## 13. Session Heatmap — State Space Occupancy

**What it shows:** A 2D histogram of where x(t) has been during the
session, for each pair of dimensions. Each time the state passes through
a region, that bin accumulates a count. The heatmap fills slowly over
the session duration.

**Live behavior:** New counts accumulate at each score event. The
heatmap is initially empty and fills gradually — early in the piece it
shows the opening character; late in the piece it shows the full
expressive range explored.

**Timescale:** Session-level accumulation.

**Screen:** Concerto (primary). This is the visualization most suited
to the exhibition context — it accumulates over the entire exhibition
duration if the piece is looped or performed repeatedly, producing an
ever-richer palimpsest.

**Complexity:** Medium.

**What it tells you:** The expressive fingerprint of the piece-regime
combination. A piece with narrow dynamic range produces a concentrated
blob; a turbulent regime spreads heat across the space. Two different
performances of the same piece through the same regime will produce
slightly different heatmaps — the variation is the music.

---

## 14. Pentimento Layer — Historical State Accumulation

**What it shows:** Past state trajectories rendered as translucent
painted layers beneath the current state path. Each pass through a
region of state space leaves a faint trace. The longer the piece runs,
the more layered and complex the visual becomes — earlier passes showing
through later ones, exactly like paint layers in a pentimento.

**Live behavior:** Each event adds a faint mark. The image darkens and
enriches continuously. Nothing is erased.

**Timescale:** Session-level accumulation. Designed for exhibition
contexts where the piece runs for hours or days.

**Screen:** Concerto.

**Complexity:** Medium — requires an off-screen accumulation buffer and
alpha compositing.

**What it tells you:** The full history of the performance visible
simultaneously. Regions visited often are dark and rich; rarely visited
regions remain pale. The visual is a compressed record of all the music
that has been played through it.

---

## 15. Belief State as Organism — Animated Gaussian Ellipse

**What it shows:** A single large animated ellipse representing the 2D
projection of the posterior covariance. The ellipse breathes — blooming
during prediction, snapping tight during update. The center point drifts
as the posterior mean moves. The color encodes the current structural
salience ω — cool at low ω, warm at high ω.

**Live behavior:** Continuous animation at rendering-level (~60fps),
interpolating between the discrete event-level updates with smooth easing.

**Timescale:** Rendering-level (continuous), updated at event-level.

**Screen:** Concerto (as a large central element).

**Complexity:** Medium — requires smooth interpolation between event
states and a rendering loop independent of the event loop.

**What it tells you (for a non-technical viewer):** The model is alive.
It is uncertain or certain. It is calm or agitated. It knows something
is coming.

---

## 16. Dimension Correlation Web

**What it shows:** A radial layout with five nodes — one per expressive
dimension — connected by edges whose thickness and opacity encode the
off-diagonal covariance Σᵢⱼ between each pair. Strong correlations
produce thick edges; near-zero correlations produce invisible ones.

**Live behavior:** Edge weights update at each score event as the
posterior covariance evolves.

**Timescale:** Event-level.

**Screen:** Interpreter.

**Complexity:** Low.

**What it tells you:** Which expressive dimensions are currently
coupled. If gain_db and brightness are strongly correlated, a sample
that is loud will also tend to be bright. If timing and attack are
coupled, a rushed note will also tend to be sharp. The correlation
structure of the posterior is musically interpretable.

---

## 17. Distribution Shape Indicator

**What it shows:** For each dimension, a small glyph indicating the
current effective sampling distribution — its family, shape, and
approximate tail weight. The glyph is a miniature density curve, not
a label. When salience-conditioned distributions are active, the glyph
morphs as ω changes.

**Live behavior:** Updates at each score event. Morphs smoothly when
the distribution shifts.

**Timescale:** Event-level.

**Screen:** Interpreter (as an annotation on the marginal Gaussians panel).

**Complexity:** Low if static per regime. Medium if morphing with ω.

**What it tells you:** Which sampling family is governing each dimension
right now. Whether tails are getting heavier as a climax approaches.
The distribution shape as an expressive parameter in its own right.

---

## Summary Table

| # | Visualization | Timescale | Screen | Complexity | Already built |
|---|--------------|-----------|--------|------------|---------------|
| 1 | Marginal Gaussians + sample ticks | event | both | low | yes (partial) |
| 2 | Kalman gain heatmap K(t) | event | interpreter | low | yes |
| 3 | Innovation trace ν(t) + autocorrelation | event | interpreter | low | yes (partial) |
| 4 | AR(2) phase portrait | event + session | both | low | no |
| 5 | State trajectory 5D → 2D | event | both | medium | no |
| 6 | Structural salience ω backdrop + playhead | session + event | both | low | no |
| 7 | Lookahead prior φ horizon bars | event | interpreter | low | no |
| 8 | Process noise envelope Q(t) | event | interpreter | low | no |
| 9 | Innovation energy ε(t) | event | interpreter | low | no |
| 10 | Sample scatter vs posterior | session | interpreter | medium | no |
| 11 | Regime blend timeline | session + event | both | low | no |
| 12 | Full covariance matrix Σ(t) | event | interpreter | low | no |
| 13 | Session heatmap — state space occupancy | session | concerto | medium | no |
| 14 | Pentimento layer — historical accumulation | session | concerto | medium | no |
| 15 | Belief state as organism — animated ellipse | rendering | concerto | medium | no |
| 16 | Dimension correlation web | event | interpreter | low | no |
| 17 | Distribution shape indicator | event | interpreter | low–medium | no |

---

## Screen Assignment Summary

### Interpreter screen — model diagnostics

Visualizations 1, 2, 3, 7, 8, 9, 10, 12, 16, 17.

The interpreter screen shows the complete probabilistic model state with
precision. Every panel is mathematically labeled. The primary question
it answers is: what is the filter doing right now, and is it behaving
correctly?

Suggested layout:
- Full-width top: marginal Gaussians (1) with distribution glyphs (17)
- Left column: innovation trace (3), Q envelope (8), ε trace (9)
- Center column: Kalman gain (2), covariance matrix (12)
- Right column: φ horizon (7), correlation web (16)

### Concerto screen — exhibition artifact

Visualizations 4, 5, 6, 11, 13, 14, 15.

The Concerto screen shows the model as a living visual object. Labels
are minimal or absent. The primary experience is aesthetic — the viewer
reads the model through its visual behavior rather than its numbers.

Suggested composition:
- Large center: belief organism (15) over pentimento accumulation (14)
- Backdrop: ω score landscape (6) and regime blend timeline (11)
- Peripheral: AR(2) phase portrait trails (4), session heatmap (13)

---

## Implementation Order Recommendation

### Phase 1 — Complete the interpreter screen

Items not yet built that are low complexity and high diagnostic value:

1. φ horizon bars (7) — two hours
2. Q(t) envelope with ω and ε overlay (8, 9) — half day
3. Full Σ(t) heatmap (12) — two hours
4. Dimension correlation web (16) — two hours
5. ω score backdrop with playhead (6) — half day

### Phase 2 — Build the Concerto screen foundation

6. AR(2) phase portrait with fading trail (4) — half day
7. Regime blend timeline (11) — half day
8. Belief state organism with interpolation (15) — one day
9. Session heatmap (13) — half day

### Phase 3 — Long-running exhibition features

10. Pentimento accumulation layer (14) — one day
11. Sample scatter vs posterior (10) — half day
12. Distribution shape morphing (17) — one day
