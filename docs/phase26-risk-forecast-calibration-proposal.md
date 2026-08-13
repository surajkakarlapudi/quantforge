# Phase 26 Proposal — Walk-Forward Risk-Forecast Calibration

> **Status: PROPOSAL / DESIGN-ONLY.** Nothing in this document is implemented. No source
> files, tests, locked specification, workspace wiring, or version bumps have been created.
> The only repository artifact produced for Phase 26 is this file. Every decision marked
> **★ LOAD-BEARING** requires explicit approval before any implementation begins.
>
> **Verified repository state (not assumed):** `HEAD = 042d5a9` "Release Phase 25:
> Multiple-Comparison Correction"; latest tag `v0.22.0` (`git describe --tags` → `v0.22.0`).
> Phases 1–25 are implemented and released. This investigation read the live tree, not prior
> summaries or memory (memory claimed Phase 25 was "not committed"; the repository is
> authoritative and shows it committed + tagged — memory was stale).

---

## 0. Executive recommendation (one line)

Recommend **Phase 26 = Walk-Forward Risk-Forecast Calibration** — a pure ex-post consumer of
**one** sealed `WalkForwardEvaluation` that reads its already-sealed but **entirely
unconsumed** per-window `predicted_variance` (in-sample `wᵀΣw`) and `realized_variance` (OOS
variance of the achieved returns), and seals a new write-once `RiskForecastCalibration`
`ResearchRecord` answering: *"Does the Phase-20 covariance estimate that drives the Phase-21
GMV weights actually predict realized risk out-of-sample, or is the entire construction stack
resting on a covariance forecast that does not hold OOS?"* This validates the foundational
assumption beneath the whole `FactorRiskModel → PortfolioOptimization → WalkForwardEvaluation`
chain, consumes a payload the Phase 22 architecture visibly **reserved** (it even seals a
`predicted_vs_realized` roll-up property with no consumer), needs **no** new numerical
primitive, **no** `_linalg`/`_stats` change, **no** prior-phase edit, and is exact-Decimal,
deterministic, and ex-post-honest.

---

## 1. Current capability map (verified)

Every research layer P13–P25 is a **pure consumer** that writes a content-addressed,
write-once `ResearchRecord` to the **one** shared Phase-8 `ResearchResultStore`
(`research/sha256-<hex>.json`), folding engine/method version + full request + referenced
`result_hash`es + a `result_hash` over the computed cells. No later phase has added a new
store. Two invariant spines run through all of them: the **ex-post/PIT firewall** (global
inv. 28 → the SD-2/XS-2/…/MC-6 analogs: a realized-forward measurement is never a `Pit*`
type and never a forward input) and the **fail-closed-`UNDEFINED`** posture (inv. 9/15 →
XS-4/P19-4/FR-4/PO-4/WF-4/CE-4/SC-4/MC-3: degenerate inputs are recorded, never imputed or
raised).

### 1.1 Data / PIT foundation (Phases 1–11)
SEC acquisition (1) → filing registry (2) → raw XBRL (3) → canonicalization (4) → **public
availability & PIT** (5, the `PitValue`/`RevisedValue` firewall) → Company façade (6) →
metrics (7) → cross-sectional factors (8) → universe (9) → PIT panel (10) → PIT market data
(11). All are PIT engines/inputs; each is consumed upward.

### 1.2 Research / analytics layers (Phases 12–18) — all ex-post `ResearchRecord`s
| # | Artifact | Consumes | PIT? | Terminal today? |
|---|---|---|---|---|
| 12 | `BacktestResult` | PIT panel + prices | PIT sim | consumed by 13–15,17 |
| 13 | `ExperimentResult` / `BacktestComparison` | backtests | ex-post | consumed by 14 |
| 14 | `ResearchReport` | any refs | ex-post | terminal (renders) |
| 15 | `PerformanceAnalytics` | a backtest + benchmark | ex-post | **terminal leaf** |
| 16 | `SignalDiagnostics` | panel/universe/prices | ex-post (signal PIT) | **terminal leaf** |
| 17 | `FactorAttribution` | ≤K factor backtests | ex-post | **terminal leaf** |
| 18 | `CrossSectionalRegression` | panel/universe/prices | ex-post (signal PIT) | **terminal leaf** |

### 1.3 Factor-construction + validation spine (Phases 19–25) — the frontier
For each: **inputs → sealed numeric payload → identity fold → PIT → consumer → unused payload.**

- **`FactorPortfolio` (19).** In: signal + universe + schedule + corpus pins (by value). Out:
  per-period `factor_return` (long−short spread) + a `FactorReturnSummary`. Id folds domain
  `factorportfolio/1` + spec + both corpus pins + `result_hash`. Ex-post. Consumed by 20 & 22
  (they read only `per_period.factor_return`). **Unused:** the entire `summary`
  (cum/mean/vol/Sharpe/t/hit-rate), `long_return`/`short_return`, leg membership, coverage.
- **`FactorRiskModel` (20).** In: ordered 2..16 sealed `factor_portfolio_id`s. Out: per-factor
  moments; **upper-triangle covariance** (per-period + annualized); **upper-triangle
  correlation**. Id folds domain `factorrisk/1` + ordered factor `result_hash`es (FR-1) +
  `result_hash`. Ex-post. Consumed by 21 (reads **only** per-period covariance). **Unused:**
  the **entire correlation matrix**, all factor moments (esp. the ex-post `mean`, deliberately
  never used as μ), annualized covariance.
- **`PortfolioOptimization` (21).** In: one sealed `factor_risk_id`; `objective =
  minimum_variance`; `fully_invested = True` (the only constraint; weights may be negative).
  Out: GMV `weights`, `portfolio_variance`, `portfolio_volatility`. Id folds domain
  `optimization/1` + `factor_risk_id` + its `result_hash` (PO-1). Ex-post. Consumed by 22
  **as a recipe pointer only** — 22 re-solves per window and **ignores the sealed weights**.
  **Unused:** the sealed `weights`/`variance`/`volatility` (effectively terminal numerically).
- **`WalkForwardEvaluation` (22).** In: one `optimization_id` + `TrainingPolicy`
  (expanding/rolling). Out: `windows: tuple[WindowResult]`, each with axis-index bounds,
  `status`, per-factor training `weights`, **`predicted_variance` (`wᵀΣ_train w`)**,
  **`realized_variance` (population variance of that window's OOS test returns;
  `SINGLE_VALID_PERIOD` when the test window has one period)**, and audit `oos_returns`; plus
  chained `oos_returns`, a six-cell `summary`, and aggregate `realized_variance`. Id folds
  domain `walkforward/1` + `optimization_id` + its `result_hash` (WF-1) + a `result_hash` that
  **includes** per-window weights/predicted/realized variance but **excludes** per-window
  `oos_returns`. Ex-post; windows carry axis **indices**, not dates. Consumed by 23 (reads only
  chained `oos_returns` + `risk_free_per_period`) and 24 (reconstructs dates from windows;
  reads `summary.annualized_sharpe`). **Unused by everything:** all per-window `weights`; **all
  per-window and aggregate `predicted_variance`/`realized_variance` and the
  `predicted_vs_realized` roll-up property**; five of six `summary` cells.
- **`ResearchCampaignEvaluation` (23).** In: ordered 2..64 sealed `WalkForwardEvaluation`s.
  Out: per-trial Sharpe/skew/kurtosis/PSR + campaign `expected_max_sharpe (SR₀)` +
  `deflated_sharpe (DSR)` selection-bias correction. Id folds domain `campaign/1` + ordered
  trial `result_hash`es (CE-1). Ex-post. **Terminal leaf** (no consumer). Uses `_stats` Φ/Z⁻¹.
- **`StrategyComparison` (24).** In: ordered 2..32 sealed `WalkForwardEvaluation`s. Out:
  upper-triangle pairwise cells: `mean_diff`, `stderr_diff`, `t_stat`, `p_value`,
  `sharpe_diff`. Id folds domain `comparison/1` + ordered walk-forward `result_hash`es (SC-1).
  Ex-post. Consumed by 25 — which reads **only `p_value`** (+ i/j/labels). **Unused:**
  `mean_diff`, `stderr_diff`, `t_stat`, `sharpe_diff`, all `TrialSummary`. **No CI, no effect
  size computed at all** (Sharpe-difference significance / Jobson–Korkie explicitly deferred).
- **`MultipleComparisonCorrection` (25).** In: exactly one sealed `StrategyComparison`. Out:
  per-method (Holm/BY default; Bonferroni/BH available) adjusted p-values + `rejected` flags +
  coverage + first-class `ExcludedCell`s. Id folds domain `multiplicity/1` + source
  `result_hash` (MC-1). Ex-post; uses **no** `_stats` (consumes p-values). **Terminal leaf** —
  the per-method rejection set (which pairs survive at `alpha`) has no consumer.

### 1.4 Shared infrastructure a new phase may reuse without adding primitives
- **`_linalg`** (`quantforge._linalg`): exact-`Decimal`, closed-form, no iteration — `ldl`
  (LDLᵀ, returns `None` on any non-positive pivot ⇒ **positive-definite only**), `ldl_solve`
  (`Ax=b`), `inverse_diagonal`. **No** matmul/transpose/dot helper, **no** general inverse,
  **no** eigendecomposition, **no** size cap.
- **`_stats`** (`quantforge._stats.normal`): `standard_normal_cdf` (Φ via all-positive-term
  `erf` series), `standard_normal_ppf` (Z⁻¹ via fixed 240-step bisection), `EULER_MASCHERONI`.
  **No** PDF, **no** Student-t, **no** harmonic numbers. `Decimal.sqrt`/`Decimal.exp` are used.
- **Identity:** `sha256_hex` (`quantforge.sec.artifacts`); per-phase `identity.py` re-declares
  `_SEP="\x00"`, canonical JSON `sort_keys=True, ensure_ascii=False, separators=(",",":")`,
  `sha256:` prefix; fold a fresh `"<domain>/1"` tag first; pin upstream by id **and**
  `result_hash`; engine version = `sha256(code_version, config_hash)` with `config_hash` over
  the pinned decimal context (prec 34, `ROUND_HALF_EVEN`).
- **Persistence:** `ResearchResultStore` (implement the `ResearchRecord` protocol:
  `research_result_id` + `to_dict`) — write-once, atomic, idempotent byte-identical rewrite,
  `FactorConsistencyError` on conflict, generic fail-closed `read_as`.
- **Wiring:** one lazy cached `*_engine` `@property` on `Workspace` (18 exist today).

---

## 2. The capability frontier

**What QuantForge can do end-to-end today:** ingest PIT fundamentals + prices → build
cross-sectional factors → construct long/short factor-return series → estimate their
covariance → optimize a fully-invested GMV factor allocation → evaluate it out-of-sample
via walk-forward → correct a *population* of strategies for selection bias (DSR/PSR) →
compare strategies pairwise (paired-difference t) → correct that pairwise family for
multiplicity (Holm/BY).

**Where the workflow terminates:** three terminal leaves — `ResearchCampaignEvaluation` (23),
`StrategyComparison`→`MultipleComparisonCorrection` (25), and (numerically)
`PortfolioOptimization` (21). The *statistical-validation* branch (does the result survive
selection bias / multiplicity?) is now well-developed.

**The important research question still unanswered:** the entire construction stack rests on
one estimate — the **Phase-20 sample covariance** — used by Phase 21 to pick GMV weights and
by Phase 22 to predict each window's risk (`predicted_variance = wᵀΣ_train w`). **Nothing in
the platform ever checks whether that covariance forecast is any good out-of-sample.** Phase
22 seals, per window, both the forecast (`predicted_variance`) and the outcome
(`realized_variance`) and even exposes a `predicted_vs_realized` convenience property — yet
**no phase consumes any of it.** The single most valuable unlocked-but-unbuilt capability is
therefore **risk-forecast calibration**: turning that reserved, sealed, unconsumed
predicted-vs-realized data into a first-class validation artifact.

**Which artifact holds information with no consumer:** `WalkForwardEvaluation` — its
per-window `predicted_variance`, `realized_variance`, `predicted_vs_realized`, and `weights`
are all sealed and read by nothing. (Secondary: `FactorRiskModel`'s correlation matrix;
`StrategyComparison`'s `mean_diff`/`stderr_diff`/`t_stat`/`sharpe_diff`; `MultipleComparison`'s
rejection set.)

**Unlocked by Phases 22–25:** Phase 22's per-window predicted/realized variance made risk
calibration possible for the first time (Phase 20/21 alone have no OOS outcome to compare
against). Phase 25 established the precedent that a **single-source, closed-form, ex-post
diagnostic that consumes exactly one sealed artifact** is a legitimate, correctly-sized phase.

**Blocked by missing prerequisites:** mean-variance / max-Sharpe (no PIT-safe μ);
asset-level construction (no asset covariance); eigen-based analysis (no eigensolver);
constrained optimization requiring iterative QP (incompatible with exact-Decimal, no float
tolerance); any bootstrap/Reality-Check/SPA (needs RNG — forbidden by inv. 21).

---

## 3. Candidate catalogue (12 candidates)

Attributes per candidate: **Class · Question · Inputs · Output · Consumes · New type? · Numerics ·
Determinism · PIT · Identity · Storage · `_linalg`? · New primitive? · Downstream · Complexity.**

### C1 — Walk-Forward Risk-Forecast Calibration ★ RECOMMENDED
- **Class:** risk-model out-of-sample validation (new). **Question:** does the Phase-20
  covariance predict realized risk OOS (is the GMV built on a valid forecast)?
- **Inputs:** exactly one sealed `WalkForwardEvaluation`. **Output:** `RiskForecastCalibration`.
- **Consumes:** P22 (per-window `predicted_variance` + `realized_variance`). **New type:** yes.
- **Numerics:** per-window ratio `realized/predicted`, `Decimal.sqrt` for vol ratios, pooled
  bias `Σr/Σp`, population dispersion of ratios, under-forecast frequency — all closed-form.
- **Determinism:** exact-Decimal, prec 34 / ROUND_HALF_EVEN; no RNG/float/iteration.
- **PIT:** ex-post; `boundary_kind="pit"` carried; not a `Pit*` type; no as-of.
- **Identity:** domain `calibration/1`; folds source id + `result_hash` (transitive pin).
- **Storage:** shared `ResearchResultStore`, write-once. **`_linalg`?** none. **New primitive?**
  none. **`_stats`?** none. **Downstream:** reporting; a future risk-model-quality gate.
- **Complexity:** LOW (comparable to Phase 25). **No prior-phase edit.**

### C2 — Walk-Forward Portfolio Stability & Turnover (strongest runner-up)
- **Class:** portfolio implementability (new). **Question:** is the GMV allocation stable /
  implementable, or does sample-covariance estimation error make it churn window-to-window?
- **Inputs:** one `WalkForwardEvaluation` (per-window `weights`). **Output:**
  `PortfolioStabilityDiagnostics`. **Consumes:** P22 (weights path). **New type:** yes.
- **Numerics:** one-way turnover `½·Σ|Δw|` between consecutive REALIZED windows; per-factor
  weight-path population std; concentration HHI `Σw²`, effective-N `1/HHI`, gross leverage
  `Σ|w|`; sign-flip counts. `Decimal.sqrt` for std. Closed-form. **Determinism/PIT/Identity/
  Storage:** same clean profile as C1 (domain `stability/1`). **`_linalg`/primitive/`_stats`:**
  none. **Downstream:** transaction-cost feasibility, reporting. **Complexity:** LOW–MEDIUM.
- **Blocking tension:** the Phase 22 proposal **explicitly REJECTED** "exposure analytics" over
  the factor-weight vector as *"near-tautological and thin"* (and deferred turnover *penalties*
  and MCTR/CCTR risk attribution). Reframable (temporal turnover of the decision **path** ≠
  cross-sectional exposure **levels**; measurement ≠ penalty), but it revisits a decision the
  maintainers closed in a locked proposal — a real approval risk C1 does not carry.

### C3 — Surviving-Strategy Dominance / Selection under Multiplicity
- **Class:** research-campaign culmination (new). **Question:** after honest multiplicity
  control, which strategies are statistically dominated, and what is the survivor set / partial
  order? **Inputs:** one `MultipleComparisonCorrection` + its source `StrategyComparison`.
  **Output:** `StrategyDominance`. **Consumes:** P25 rejection set (terminal leaf) + P24
  `sharpe_diff`/`mean_diff` sign for direction. **New type:** yes. **Numerics:** sign checks +
  graph construction — trivial exact-Decimal comparisons; no sqrt. **Determinism/PIT:** clean,
  ex-post. **`_linalg`/primitive:** none. **Downstream:** selection, reporting. **Complexity:**
  LOW. **Weakness:** borderline **report-like** (boolean/graph over already-sealed decisions);
  little new *quantitative* content.

### C4 — Strategy-Comparison Confidence Intervals & Effect Sizes
- **Class:** inference reporting (extension). **Question:** what is the CI / standardized effect
  size of each pairwise mean difference? **Inputs:** one `StrategyComparison`. **Output:**
  `ComparisonIntervals`. **Consumes:** P24 unused `mean_diff`/`stderr_diff`. **Numerics:**
  `mean_diff ± z·stderr` via `_stats` Z⁻¹; effect size `mean_diff/σ`. **Weakness:** repackages
  statistics already sealed **without a new research question**; arguably a P24 extension.

### C5 — Minimum Track Record Length (MinTRL)
- **Class:** selection-bias adjunct. **Question:** how long must the track record be for a
  Sharpe to be significant at `alpha`? **Inputs:** `WalkForwardEvaluation` (or campaign) Sharpe
  + moments. **Output:** `MinimumTrackRecord`. **Numerics:** closed-form with `_stats` Z⁻¹.
  **Weakness:** overlaps Phase 23 PSR/DSR machinery; scalar-per-strategy — thin; deferred by
  P25 as C3.

### C6 — Rolling / EWMA Factor Risk Model
- **Class:** time-varying covariance. **Inputs:** factor portfolios. **Output:** sequence of
  covariance matrices. **Weakness:** a **Phase-20 extension/variant** (P20 explicitly defers
  "rolling/windowed/regime covariance" as a future *estimator*), and "rolling-series artifact"
  was itself deferred/rejected in P15/P18. Redundant-variant risk.

### C7 — Factor Covariance/Correlation Stability Diagnostics
- **Class:** model diagnostics (new-ish). **Question:** how much does the factor covariance/
  correlation structure drift across models/time? **Inputs:** N sealed `FactorRiskModel`s.
  **Output:** `CovarianceStability`. **Consumes:** the unused correlation matrices. **Weakness:**
  requires *many* risk models as input, but no producer emits a rolling family (would need C6
  first); awkward, prerequisite-blocked.

### C8 — Factor Redundancy / Collinearity Diagnostics
- **Class:** model diagnostics (new-ish). **Question:** which factors are near-collinear /
  redundant? **Inputs:** one `FactorRiskModel`. **Output:** `FactorRedundancy`. **Consumes:**
  the unused correlation matrix + LDLᵀ pivots (determinant `Πdᵢ` is available). **Numerics:**
  correlation thresholds + determinant. **Weakness:** somewhat **thin**; the interesting
  spectral measures (condition number) need an eigensolver that does not exist.

### C9 — GMV Risk Attribution (MCTR / CCTR) — REJECT
- **Class:** risk budgeting. **Weakness:** for **unconstrained fully-invested GMV** the
  first-order condition `Σw ∝ 1` makes every asset's marginal contribution to risk equal ⇒ the
  attribution is **mathematically tautological** (`CCTRᵢ ∝ wᵢ`). Explicitly flagged tautological
  in the P22 proposal and by the Phase-26 brief. Non-tautological only *after* constraints (C11).

### C10 — Equality-Constrained GMV (`Aw=b`, factor-neutral / target-exposure)
- **Class:** constrained optimization (deferred, closed-form-compatible). **Inputs:**
  `FactorRiskModel` + a linear equality system. **Output:** `PortfolioOptimization` variant.
  **Numerics:** range-space KKT — solve `Σx=eⱼ` with existing PD `ldl_solve`, then a **new
  small dense matmul + inverse** of `AΣ⁻¹Aᵀ`. **Requires `_linalg` change (matmul).**
  **Weakness:** (a) needs a new primitive; (b) the KKT saddle system is **indefinite** — the
  existing PD-only `ldl` cannot factor it directly; (c) **the output is a downstream dead-end**:
  Phase 22's WF-5 fails closed on anything but `constraint_spec == {"fully_invested": True}`, so
  a constrained recipe **cannot be walked forward** without also editing Phase 22; (d)
  redundant-variant risk vs P21. Genuinely deferred, but a poor *single* phase.

### C11 — Constrained-Portfolio Risk Attribution
- Non-tautological version of C9, but **strictly blocked on C10** (needs constrained weights
  first). Two phases deep; out of reach now.

### C12 — PBO / CSCV (Probability of Backtest Overfitting)
- **Class:** overfitting diagnostics. **Question:** probability the selected config is overfit?
  **Inputs:** many strategies' per-sub-period performance. **Numerics:** combinatorially-
  symmetric CV — the combinatorics are **deterministic (no RNG needed)**, so it is *not*
  automatically disqualified. **Weakness:** HIGH complexity + a **data-shape mismatch** (needs an
  N-config × M-subperiod performance matrix the platform does not assemble); deferred by P25 as
  C4. A future phase once a config-grid producer exists.

---

## 4. Capability-family evaluation (brief §5 A–H verdicts)

- **A. Portfolio constraints.** Long-only / box / gross bounds need iterative QP with float
  tolerances — **incompatible** with exact-Decimal / no-float (P21 §9 rejects them). Equality
  `Aw=b` is closed-form-compatible but needs a new `_linalg` matmul and cannot be walked forward
  (C10). **Verdict: defer; not the best single phase now.**
- **B. Portfolio/risk attribution.** GMV risk attribution is **tautological** (C9). Non-
  tautological attribution requires constraints first (C11). **Verdict: reject now.**
- **C. Strategy robustness.** PBO/CSCV is data-shape-blocked (C12); MinTRL overlaps P23 (C5);
  Reality Check / SPA / bootstrap **require RNG** — forbidden (inv. 21). **Risk-forecast
  calibration (C1) is the robustness capability that IS compatible and unlocked.**
- **D. Time-varying risk.** Rolling/EWMA covariance is a **Phase-20 variant** (C6). **Reject.**
- **E. Portfolio stability.** *Yes*, `WalkForwardEvaluation` retains enough (per-window
  `weights`) to compute turnover/stability honestly (C2) — the strongest runner-up — **but** it
  revisits the P22-rejected "exposure analytics." **Verdict: viable, deprioritized vs C1.**
- **F. Statistical inference.** CIs / effect sizes (C4) repackage sealed stats without a new
  question. **Reject as thin/extension.**
- **G. Research-campaign diagnostics.** Dominance/selection under multiplicity (C3) is real but
  **report-like**. **Runner-up, deprioritized.**
- **H. Factor/model diagnostics.** Redundancy (C8) is thin; covariance-stability (C7) is
  prerequisite-blocked. **Reject/defer.**

---

## 5. Terminal-leaf census (and whether each deserves a consumer)

| Terminal / unused | A consumer would… | Honest to build now? |
|---|---|---|
| **P22 per-window `predicted_variance` + `realized_variance`** | validate the covariance forecast OOS (**C1**) | **Yes — reserved (`predicted_vs_realized` exists unconsumed).** |
| P22 per-window `weights` | measure turnover/stability (C2) | Yes, but collides with the P22 "exposure analytics" rejection. |
| P25 rejection set (terminal) | build a survivor set/dominance (C3) | Yes, but report-like. |
| P24 `mean_diff`/`stderr_diff`/`t_stat`/`sharpe_diff` | build CIs/effect sizes (C4) | Weak — repackaging. |
| P20 correlation matrix | redundancy diagnostics (C8) | Thin. |
| P23 `ResearchCampaignEvaluation` (terminal) | feed a report/meta-layer | Acceptable leaf; no honest numeric consumer. |
| P21 sealed `weights` (numerically terminal) | — | Acceptable leaf (P22 re-solves by design). |

A terminal leaf is acceptable when there is no architecturally honest next consumer (P23, P21
weights). The predicted/realized-variance payload is the one case where the architecture
**reserved** a consumer and none was built — the strongest signal for what Phase 26 should be.

---

## 6. Rejected candidates (with the §7 disqualifier each triggers)

- **C6 Rolling/EWMA covariance** — duplicates/extends Phase 20 (redundant variant).
- **C4 CIs/effect sizes** — repackages existing statistics without a new research question.
- **C9 GMV risk attribution** — mathematically **tautological** for unconstrained GMV.
- **Reality Check / SPA / bootstrap CIs / any resampling** — **require RNG**; violate inv. 21.
- **Long-only / box / leverage constraints** — require iterative QP with float tolerances;
  violate exact-Decimal / no-float / finite-termination.
- **Mean-variance / max-Sharpe** — need a PIT-safe expected-return μ that **does not exist**;
  using ex-post factor means as μ is the forbidden look-ahead (inv. 28 / PO-3).
- **Asset-level optimization/attribution** — no asset-level covariance artifact exists.
- **C10/C11 constrained GMV + its attribution** — need a new `_linalg` matmul, hit an indefinite
  KKT the PD-only `ldl` cannot factor, and produce a walk-forward dead-end (WF-5) — a poor
  *single* phase; genuinely deferred.
- **C12 PBO/CSCV** — no config-grid performance matrix producer exists (data-shape mismatch).
- **Any UI / pure report / ingestion-for-its-own-sake** — out of the research-record model.

None of the above, and neither recommended nor runner-up candidates, requires weakening any
invariant or modifying a prior-phase identity.

---

## 7. Recommendation: C1 — Walk-Forward Risk-Forecast Calibration, and why it wins

**What it is.** A new pure-consumer phase above Phase 22. Given a declarative
`RiskForecastCalibrationSpecification` naming exactly one sealed `WalkForwardEvaluation`,
`RiskForecastCalibrationEngine.calibrate(spec)` resolves and re-verifies that walk-forward
(present, decodes as `WalkForwardEvaluation`, `research_result_id == id`, `result_hash`
pinned), walks its sealed `windows` in order, and for every **calibratable** window (status
`REALIZED`, `predicted_variance` KNOWN and `> 0`, `realized_variance` KNOWN — i.e. **not**
`SINGLE_VALID_PERIOD`) seals a calibration cell; then seals aggregate calibration statistics
and coverage into a write-once `RiskForecastCalibration` record. It answers whether the
Phase-20 covariance that the entire GMV chain depends on actually forecasts realized OOS risk.

**Per-window calibration cell (proposed):** `index`, `status`, `predicted_variance`,
`realized_variance`, `predicted_volatility = √predicted`, `realized_volatility = √realized`,
`variance_ratio = realized/predicted`, `volatility_ratio = √variance_ratio`. Windows that are
not calibratable are recorded as first-class **excluded cells** carrying the source reason
(`WINDOW_UNDEFINED`, `SINGLE_VALID_PERIOD`, `ZERO_PREDICTED_VARIANCE`) — never imputed.

**Aggregate calibration summary (proposed):** `n_windows`, `n_calibratable`, `n_excluded`;
`mean_variance_ratio`; **pooled bias** `aggregate_bias = Σrealized / Σpredicted` (a Barra-style
bias-ratio analogue: `>1` ⇒ the model systematically **under-forecasts** risk, `<1` ⇒
over-forecasts); `variance_ratio_dispersion` (population std of the per-window ratios);
`underforecast_frequency = |{realized > predicted}| / n_calibratable`; `max/min_variance_ratio`;
`calibration_status` (`CALIBRATED` when `n_calibratable ≥ MIN_CALIBRATABLE_WINDOWS`, else
`UNDEFINED INSUFFICIENT_CALIBRATABLE_WINDOWS`, still sealed).

**Why it beats every serious alternative:**
- **vs C2 (turnover/stability):** C1 consumes a payload the architecture **reserved**
  (`predicted_vs_realized`), whereas C2 revisits the P22-**rejected** "exposure analytics." On
  *architectural honesty / not re-litigating closed decisions* — a top-weighted criterion — C1
  strictly dominates. C1 also validates the **foundational** covariance the whole 20→21→22 chain
  rests on (higher leverage than an implementability metric).
- **vs C3 (dominance) / C4 (CIs):** those are report-like / repackaging; C1 produces genuinely
  **new quantitative content** (a forecast-vs-outcome comparison that exists nowhere else).
- **vs C10 (constrained GMV):** C1 needs **no** `_linalg` change and is **not** a downstream
  dead-end; C10 needs a new primitive, hits an indefinite KKT, and cannot be walked forward.
- **vs C6 (rolling covariance) / C9 (risk attribution):** C1 is neither a Phase-20 variant nor
  tautological.
- **vs C12 (PBO):** C1 has a clean single-artifact input; PBO has none.

**Scorecard (the ten brief criteria):** genuinely new capability class ✅ (OOS risk-model
validation — absent from P1–25); real quant use ✅ (covariance forecasts are the core input to
every mean-variance/GMV construction; bias-ratio testing is standard practice); consumes sealed
artifacts ✅ (one `WalkForwardEvaluation`); creates a useful downstream artifact ✅
(`RiskForecastCalibration`, a natural future model-quality gate); not merely a report ✅ (new
computed statistics); exact-Decimal determinism ✅; PIT/no-look-ahead preserved ✅ (ex-post,
boundary carried); fits `ResearchRecord`/`ResearchResultStore` ✅; no prior-phase change ✅; one
coherent phase ✅ (Phase-25-sized).

---

## 8. Invariant analysis (COMPOSES / CONSTRAINS / TENSION / CONTRADICTION)

- **Global 1–5, 22–26 (immutability/provenance/amendments):** COMPOSES — untouched; reads only
  sealed, content-addressed inputs; adds append-only records.
- **Global 6–17 (PIT/availability):** COMPOSES — no new corpus read, no `as_of`, no availability
  logic; consumes an already-ex-post artifact.
- **Global 18–21 (determinism/versioning):** COMPOSES — exact-Decimal, no wall-clock/RNG/
  input-order; engine version folds the pinned context; a methodology change hashes distinctly.
- **Global 27–30 + the inv-28 firewall (SD-2/…/MC-6):** COMPOSES — `RiskForecastCalibration` is
  ex-post, **not** a `Pit*` type, exposes **no** as-of accessor; `boundary_kind="pit"` (carried
  from source) documents only the underlying PIT walks. No ex-post field can become a forward
  input (the record is a leaf).
- **WF-1..WF-6 (its direct parent):** COMPOSES / CONSTRAINS — it **inherits** the walk-forward
  train-before-test guarantee (WF-2) and reads only what WF sealed; CONSTRAINS itself to consume
  `predicted_variance`/`realized_variance` exactly as WF defined them (including WF-4's
  `SINGLE_VALID_PERIOD`/degeneracy markers), never recomputing from `oos_returns`.
- **FR/PO (grandparents):** COMPOSES via transitive pinning — folding the walk-forward
  `result_hash` transitively pins the optimization, risk model, and factor chain (the FR-1/PO-1/
  WF-1 pattern, one layer up).
- **CE/SC/MC (sibling meta-analysis layers):** COMPOSES — orthogonal; C1 validates the *risk
  model*, they validate *returns significance*. No shared identity.
- **TENSION (single, resolvable):** the Phase-22 proposal **rejected** "exposure analytics" and
  deferred **MCTR/CCTR risk attribution** as tautological for GMV. *Resolution:* C1 is **neither**
  — it does **not** attribute or decompose risk across factors (no MCTR/CCTR), and it does **not**
  describe exposure levels; it compares a **forecast** (`predicted_variance`) against a realized
  **outcome** (`realized_variance`) — genuinely different quantities whose gap measures
  covariance-estimation quality, which is **not** tautological. No invariant is weakened; the
  rejected capabilities remain rejected.
- **CONTRADICTION:** none identified.

---

## 9. Numerical-method audit

- **Exact formulae:** `variance_ratio = realized/predicted`; `volatility_ratio =
  realized_volatility/predicted_volatility = √(variance_ratio)`; `aggregate_bias = Σr/Σp`;
  `mean_variance_ratio = (Σ VRₖ)/K`; `dispersion = √(Σ(VRₖ − mean)²/K)` (population);
  `underforecast_frequency = count(rₖ>pₖ)/K`.
- **Decimal:** all values are `Decimal` under an explicit `localcontext` (prec 34,
  ROUND_HALF_EVEN). **`Decimal.sqrt` is sufficient** (volatilities, dispersion) — the exact
  method Phases 19/20/22 already use; **no** other transcendental is needed.
- **New deterministic primitive?** **No.** **`_stats` reuse?** **Not needed** (no Φ/Z⁻¹).
  **`_linalg` sufficient / needed?** **Not used** (scalar arithmetic only — no matmul, no
  inversion, no Cholesky, no eigen). **Iteration?** None (finite sums over windows). **Convergence
  criteria?** N/A. **RNG?** None. **Wall-clock?** None.

---

## 10. PIT / ex-post audit

- **PIT or ex-post?** Ex-post — it compares realized OOS variance against an in-sample forecast.
- **Information at the boundary:** none new — every input is already sealed on the source
  `WalkForwardEvaluation`; no corpus, price, or panel is re-read.
- **`as_of` accessor?** No — forbidden by the inv-28 firewall; the record exposes none.
- **Could an ex-post field become forward-looking?** No — the record is a terminal leaf;
  `realized_variance` (post-`T`) is never fed back into any as-of-`T` computation.
- **Consumes only sealed artifacts?** Yes — exactly one `WalkForwardEvaluation`.
- **New PIT resolution surface?** No.

---

## 11. Identity & persistence audit

- **Domain tag:** `calibration/1` (folded first). **Record-format string:**
  `calibration-result/1`. **Engine/method versions:** `calibration-engine/1`,
  `calibration-method/1`.
- **Identity fields folded into `risk_forecast_calibration_id`:** domain,
  `calibration_engine_version_id`, `name`, `spec_version`, `source_walk_forward_id`,
  **`source_result_hash`** (transitive pin), `MIN_CALIBRATABLE_WINDOWS`, and `result_hash`.
- **`result_hash`:** canonical JSON over ordered computed cells — the coverage descriptor, then
  per-window calibration cells (`index`, `predicted_variance`, `realized_variance`,
  `variance_ratio`, `volatility_ratio`) in window order, then excluded cells (`index`, `reason`),
  then the aggregate summary. Derivable fields (`predicted_volatility` = `√predicted`) may be
  omitted from the hash; audit-only coverage counts fold only via the descriptor.
- **Config/decimal context:** `config_hash` over `prec=34\x00round=ROUND_HALF_EVEN\x00
  method=calibration-method/1`, folded into the engine version (identity changes if the
  methodology or context changes).
- **Canonical serialization:** `_SEP="\x00"`; canonical JSON `sort_keys=True,
  ensure_ascii=False, separators=(",",":")`; `sha256:` prefix. Derived ids re-emitted by
  properties, never read from stored state.
- **Write-once behaviour:** shared `ResearchResultStore` under `<root>/research/`; idempotent
  byte-identical rewrite is a no-op; a differing payload under the same id raises
  `FactorConsistencyError`.
- **Store location:** `research/sha256-<hex>.json` (no new store). **Pin-mismatch behaviour:**
  a missing / non-`WalkForwardEvaluation` / id-mismatched / hash-drifted source fails closed with
  `CalibrationConsistencyError`.
- **Identity changes whenever the result can change:** ✅ (folds source `result_hash`, the full
  request, the pinned context, and the computed `result_hash`).

---

## 12. Approval-gated decisions (★ LOAD-BEARING)

1. **★ Capability scope** — OOS risk-forecast calibration of exactly one walk-forward; a
   descriptive validation artifact, no correction/optimization/execution.
2. **★ Input artifact** — exactly one sealed `WalkForwardEvaluation` (by id). *(No multi-source
   family in v1.)*
3. **★ Output artifact** — `RiskForecastCalibration`.
4. **★ Package name** — `src/quantforge/calibration/`. **★ Domain tag** — `calibration/1`.
5. **★ Public type names** — `RiskForecastCalibrationSpecification`, `RiskForecastCalibration`
   (+ nested `WindowCalibrationCell`, `ExcludedWindow`, `CalibrationSummary`,
   `CalibrationCoverage`); engine `RiskForecastCalibrationEngine.calibrate(spec)` reached via
   `Workspace.risk_calibration_engine`.
6. **★ Numerical methodology** — per-window `realized/predicted` variance & volatility ratios;
   pooled `aggregate_bias = Σr/Σp`; population `variance_ratio_dispersion`;
   `underforecast_frequency`; min/max ratios. *(Approve the exact metric set; approve
   variance-basis + volatility-basis both, or variance-only.)*
7. **★ Determinism strategy** — exact-Decimal, prec 34 / ROUND_HALF_EVEN; no RNG / float /
   iteration / wall-clock; `Decimal.sqrt` only.
8. **★ PIT / ex-post boundary** — ex-post; not a `Pit*` type; no as-of accessor;
   `boundary_kind="pit"` carried unchanged from the source.
9. **★ UNDEFINED semantics** — exclude (never impute) windows that are `UNDEFINED`, have
   `SINGLE_VALID_PERIOD` realized variance, or zero predicted variance
   (`ZERO_PREDICTED_VARIANCE`); each recorded as a first-class excluded cell. Empty/`< MIN`
   calibratable set ⇒ `calibration_status = UNDEFINED INSUFFICIENT_CALIBRATABLE_WINDOWS`, record
   still seals. **★ `MIN_CALIBRATABLE_WINDOWS`** value (proposed `2`).
10. **★ Identity fold** — as in §11 (domain, engine version, spec, source id + `result_hash`,
    `MIN_CALIBRATABLE_WINDOWS`, `result_hash`); source pinned transitively.
11. **★ Version** — **v0.23.0**.
12. **★ `_linalg` changes** — **NONE.** **★ `_stats` changes** — **NONE.** **★ Shared-infra
    extraction** — **NONE** (no new primitive; no refactor of existing modules).
13. **★ Bounds** — **no `N_MAX`** (single source; window count is bounded by the source).
14. **★ Sibling vs extension** — a **sibling** new package (`calibration/`); **no** edit to
    `walkforward/` vocabulary, engine, or identity. Only additive `Workspace` property +
    top-level exports.
15. **★ Persistence model** — shared `ResearchResultStore`, write-once, idempotent, fail-closed;
    **no** new store/database/migration.

---

## 13. Proposed phase-local invariants (RC-1 .. RC-6)

Additive to `data-model.md §12`; these do **not** weaken invariants 1–30 or any prior family.

- **RC-1 — Reference verification & transitive pinning.** The single `source_walk_forward_id`
  is resolved via `read_as(id, WalkForwardEvaluation.from_dict)`, re-verified
  (`research_result_id == id`; decodes as a `WalkForwardEvaluation`), and its `result_hash`
  folded into `risk_forecast_calibration_id` — transitively pinning the optimization/risk/factor
  chain beneath it. Missing/non-decoding/id-mismatched/hash-drifted ⇒ `CalibrationConsistencyError`.
- **RC-2 — Explicit calibratable family + sealed coverage.** The family is exactly the source's
  calibratable windows; coverage (`n_windows`, `n_calibratable`, `n_excluded`;
  `n_calibratable + n_excluded = n_windows`) is sealed so the effective sample is auditable.
- **RC-3 — Non-calibratable windows excluded, never imputed.** A window that is `UNDEFINED`, has
  `SINGLE_VALID_PERIOD` realized variance, or zero predicted variance is recorded as a
  first-class excluded cell with its reason; an empty family seals empty cell lists (no
  divide-by-zero). *(The WF-4/MC-3 fail-closed posture, adapted to windows.)*
- **RC-4 — Forecast vs outcome, never recomputed.** `predicted_variance` and `realized_variance`
  are consumed **exactly as the source sealed them**; the calibration never re-derives variance
  from `oos_returns` or re-solves any window — it only forms ratios/aggregates.
- **RC-5 — Single deterministic methodology.** One exact-Decimal calibration under one pinned
  context (prec 34, ROUND_HALF_EVEN), `Decimal.sqrt` only; no RNG/float/iteration/`_linalg`/
  `_stats`/new primitive; one uniform definition of each statistic.
- **RC-6 — A calibration is not a PIT value and not a `BacktestResult`.** It is an ex-post
  comparison of a forecast against a realized outcome; not a `Pit*` type, no as-of accessor
  (`boundary_kind="pit"` documents only the underlying PIT walks), a distinct record type, no
  fills/cash/positions/costs. *(The WF-3/PO-2/MC-6 discipline, one layer up.)*

---

## 14. Out of scope (strict, if approved)

Deferred to later, explicitly-labelled phases; Phase 26 absorbs none: multi-source calibration
families; any correction/hypothesis test on the ratios (a future consumer, mirroring how P22
seals and P23/P25 correct); rolling/regime-conditioned calibration; risk **attribution**
(MCTR/CCTR); turnover/stability (C2); dominance/selection (C3); CIs/effect sizes (C4); any
`_linalg`/`_stats` change; any new store, RNG, float, iteration, corpus read, `as_of` surface,
ingestion, UI, or API; any modification to Phase 22 (or any prior phase) vocabulary, engine, or
identity; feeding the calibration into any prior phase.

---

## 15. What this document is NOT

This is design-only. No package, engine, spec, record, identity, tests, workspace wiring,
public export, `data-model.md` invariant block, README/ARCHITECTURE/index edits, version bump,
commit, tag, or release has been made. Implementation begins only after the ★ decisions in §12
are explicitly approved.
