# Phase 22 — Walk-Forward Out-of-Sample Evaluation (PROPOSAL)

> **Status: DESIGN ONLY. Not approved. Nothing implemented.** This document
> proposes the next capability and its architecture for review. No source, tests,
> or locked spec exist. Per the Phase 22 charter it creates exactly one file (this
> proposal) and changes nothing else.
>
> **Recommended capability:** a **walk-forward out-of-sample (OOS) evaluation** of
> the factor risk-model → minimum-variance optimization pipeline. Given a sealed
> `PortfolioOptimization` (Phase 21) as the *recipe*, resolve the underlying factor
> return series transitively through its `FactorRiskModel` (Phase 20) and
> `FactorPortfolio`s (Phase 19), partition the common date axis into ordered
> **train → test** windows on a rebalance schedule, and — for each window — **re-estimate**
> the covariance on the training window and **re-solve** the same objective, then
> apply the resulting weights to the *strictly subsequent* realized factor returns.
> Chain those out-of-sample returns into a series, summarize its realized
> performance, and record the per-window **predicted-vs-realized** variance. The
> result is a new sealed, content-addressed, ex-post `WalkForwardEvaluation` record.
>
> **Version:** **v0.19.0** (Phase 21 = v0.18.0).

---

## 1. Executive Summary

Phases 19–21 built the project's first end-to-end **portfolio-construction stack**:
characteristic-sorted factor return series (`FactorPortfolio`, P19) → their covariance
structure (`FactorRiskModel`, P20) → a fully-invested global minimum-variance (GMV)
weight vector (`PortfolioOptimization`, P21). Repository inspection establishes two facts
that determine the next phase:

1. **`PortfolioOptimization` is a terminal leaf.** Nothing in `src/` consumes it; the GMV
   weights are produced and never evaluated. The entire P19→P20→P21 chain is **in-sample**:
   the covariance is estimated over the full common window, the weights minimize variance
   over *that same* window, and no artifact ever asks whether those weights are any good
   *outside* the window they were fit on.

2. **The only non-tautological evaluation of a minimum-variance optimizer is
   out-of-sample.** By construction the in-sample variance of a GMV portfolio is a lower
   bound, so re-measuring it in-sample is circular (§5.1); and for the *unconstrained*
   fully-invested GMV the per-factor risk contributions collapse to the weights themselves
   (§7, candidate G), so ex-ante "risk attribution" is also tautological. The research
   question that has real content — the one a quant actually asks before trusting an
   optimizer — is **"does re-estimating and re-optimizing on the past actually reduce risk
   / perform when carried forward?"**

Phase 22 answers exactly that. It is a **pure consumer** that references one sealed
`PortfolioOptimization` as the optimization *recipe* (objective + constraint + factor set),
resolves the underlying factor return series through the existing chain, and performs a
deterministic **walk-forward**: on each rebalance date `T_k` it re-estimates the covariance
using **only** returns up to `T_k`, re-solves the same objective to get weights `w_k`, and
realizes those weights against the factor returns in the *strictly subsequent* test window
`(T_k, T_{k+1}]`. The chained OOS return series, its performance summary, and a per-window
predicted-vs-realized variance record are sealed as a new `WalkForwardEvaluation`.

This is the **first genuine consumer of Phase 21's output**, it validates the whole
constructive chain, it introduces the project's first **train-before-test temporal
discipline** (a new invariant family, WF-1..WF-6), and it composes the *existing* Phase 20
covariance estimator and Phase 21 GMV solver as pure library functions over sub-windows —
no new statistical method, no new data source, no new PIT surface, no `_linalg` change, and
no modification to any prior phase. It preserves every existing invariant and is ex-post
throughout.

It is deliberately **not** constrained optimization, mean-variance, or risk attribution —
the repository shows each of those is either premature (tautological for GMV; §7 G),
blocked by determinism (iterative QP; §7 C / §9), or blocked by a missing PIT-safe
expected-return artifact (mean-variance; §7 D / §9).

---

## 2. Repository State

### 2.1 The capability spine as actually implemented (verified from source)

| Phase | Package | Sealed record | Reads | Reached via |
|---|---|---|---|---|
| 9 | `universe` | `Universe` (PIT membership) | corpora | `Workspace` |
| 10 | `panel` | PIT fundamental panels | corpora | `panel_engine` |
| 11 | `market` | PIT market data | corpora | `price_engine` |
| 12 | `backtest` | `BacktestResult` | corpora + strategy | `backtest_engine` |
| 13 | `experiment` | `ExperimentResult` / `BacktestComparison` | sealed backtests | `experiment_engine` |
| 14 | `report` | `ResearchReport` (reference-only) | sealed backtests/experiments | `report_engine` |
| 15 | `analytics` | `PerformanceAnalytics` | sealed `BacktestResult` (store) | `analytics_engine` |
| 16 | `diagnostics` | `SignalDiagnostics` | corpora (P9/10/11) | `signal_diagnostics_engine` |
| 17 | `attribution` | `FactorAttribution` | subject + K factor `BacktestResult`s (store) | `attribution_engine` |
| 18 | `crosssection` | `CrossSectionalRegression` | corpora (P9/10/11) | `crosssection_engine` |
| 19 | `factorportfolio` | `FactorPortfolio` | corpora (P9/10/11) | `factor_portfolio_engine` |
| 20 | `factorrisk` | `FactorRiskModel` | N `FactorPortfolio`s (store) | `factor_risk_engine` |
| 21 | `optimization` | `PortfolioOptimization` | 1 `FactorRiskModel` (store) | `optimization_engine` |

### 2.2 Shared infrastructure (verified)

- **`ResearchRecord` Protocol** (`factors/store.py`): `research_result_id: str` + `to_dict()`.
- **`ResearchResultStore`** (`factors/store.py`): `write` (write-once, atomic, idempotent on
  byte-identical payload; a differing payload under an existing id raises
  `FactorConsistencyError`), `read_as(id, from_dict)` (typed decode), `has`. One JSON file per
  result under `<root>/research/`, `indent=2, sort_keys=True`. Every phase resolves-from and
  seals-to this **one** shared sidecar, reached through `Workspace.research_result_store`.
- **Identity primitive:** `sha256_hex(bytes)` (`sec/artifacts.py`), imported by every phase's
  `identity.py`/`version.py`. No shared `canonical_json`: each identity module inlines
  `json.dumps(..., sort_keys=True, separators=(",",":"))`, NUL-joins components with `"\x00"`,
  prefixes `sha256:`.
- **`_linalg`** (private): exactly `ldl`, `ldl_solve`, `inverse_diagonal` — exact-`Decimal`,
  no float/numpy, run inside the caller's pinned `localcontext`. **No** matrix-multiply,
  full-inverse, eigen/SVD, or quadratic-form helper (P21 does the quadratic form inline).
- **Decimal discipline:** precision 34, `ROUND_HALF_EVEN`, `localcontext` everywhere; no
  float, wall-clock, or RNG in any value or id.
- **`Workspace`**: each engine is a lazy, cached `@property` constructed as `Engine(self)`,
  sharing the one `research_result_store`.

### 2.3 The two facts that drive Phase 22

- **Terminal leaf.** A repo-wide search confirms `PortfolioOptimization` / `optimization_id`
  appear only inside `optimization/`, plus the `Workspace` factory property and the top-level
  re-export. **No functional consumer exists.**
- **Sealed-but-unread upstream data.** `PortfolioOptimizationEngine` reads only
  `FactorRiskModel.covariance[*].value` (per-period cells) + provenance scalars. The full
  `correlation` matrix, `covariance[*].annualized`, and every `FactorMoment` (`mean`,
  `volatility`, `annualized_volatility`) are sealed and never read. And `FactorPortfolio`
  seals a full `per_period` **factor-return series** — the raw material a walk-forward needs —
  currently consumed only by P20's full-window covariance estimate.

---

## 3. Selected Capability

**Walk-forward out-of-sample evaluation of an optimized factor portfolio.**

Input: one sealed `PortfolioOptimization` (the recipe) + a rebalance schedule + a
training-window policy. Computation: transitively resolve the factor return series; partition
the common date axis into ordered train→test windows on the schedule; per window re-estimate
the covariance (Phase 20 method) on the training returns, re-solve the recipe's objective
(Phase 21 method) to obtain weights, and realize those weights against the strictly
subsequent factor returns. Output: a sealed `WalkForwardEvaluation` holding the chained OOS
return series, its realized-performance summary, and the per-window predicted-vs-realized
variance. Ex-post, content-addressed, write-once.

The capability is **constructive-then-evaluative**: it re-runs the construction recipe out of
sample and evaluates what it produced. It performs **no execution** (no fills, cash,
positions, costs) — it is not a `BacktestResult` (WF-3).

---

## 4. Why This Capability Now

1. **It is the missing validation step for everything built in Phases 19–21.** An optimizer
   whose output is only ever measured in-sample is unfalsifiable. Walk-forward is the
   canonical, textbook method for testing whether an estimate→optimize procedure generalizes.
   Until it exists, the P19→P21 chain produces numbers no one can trust.
2. **It is the first genuine consumer of Phase 21.** It turns a terminal leaf into an
   input, and (transitively, WF-1) pins the risk model, the factors, and the corpora.
3. **Every prerequisite already exists.** The factor return series are sealed
   (`FactorPortfolio.per_period`); the covariance estimator and GMV solver exist as pure
   modules (`factorrisk`/`optimization`); the rebalance-schedule primitive exists
   (`RebalanceSchedule`); the exact-`Decimal` discipline and the shared sidecar are in place.
4. **It fills the exact gap both P20 and P21 explicitly deferred** — P20's "Rolling /
   windowed / regime-conditioned covariance" and P21's "Walk-forward / rolling /
   regime-conditioned optimization." Those deferrals both name this phase and confirm it is a
   distinct, recognized future capability rather than a modification of either.
5. **The simpler alternatives are tautological (§5.1, §7).** In-sample realization and ex-ante
   risk attribution add no information about a GMV portfolio; only OOS does.

---

## 5. Research Workflow Gap

Today a researcher can go: *signal → factor portfolio → risk model → GMV weights → **?***.
The arrow after the weights is empty. There is no way to ask the one question that decides
whether the weights matter:

> *If I had actually re-estimated the covariance and re-optimized on data available up to
> each rebalance date, and held those weights forward, what would the portfolio have
> realized — and did minimizing in-sample variance actually reduce realized variance?*

Phase 22 provides that arrow. It closes the constructive loop with an evaluative artifact,
and it establishes the reusable **train/test temporal split** primitive that a later phase
(e.g. constrained or mean-variance optimization, once admissible) can be evaluated through
without re-inventing walk-forward.

### 5.1 Why in-sample evaluation is not enough (the skeptical core)

For a fully-invested unconstrained GMV portfolio with `w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`:

- **In-sample realized variance is the predicted variance.** When `Σ` is the sample
  covariance of exactly the returns being evaluated, the realized `wᵀΣw` over that window
  *is* the optimizer's predicted variance. Re-measuring it in-sample is circular.
- **Ex-ante percent risk contributions equal the weights.** `Σw = (1/s)·1` is constant across
  factors (`s = 1ᵀΣ⁻¹1`), so factor `i`'s component contribution to variance,
  `w_i(Σw)_i / (wᵀΣw)`, reduces to `w_i`. A "risk decomposition" of this specific artifact
  therefore returns the weights we already have (§7, candidate G).

Both collapse **only** in-sample / ex-ante. Out of sample, `Σ_k` (estimated on the training
window) is applied to *different* realized returns, so realized variance ≠ predicted variance
and the comparison is informative. This is precisely why Phase 22 targets OOS.

---

## 6. Capability Matrix (Phases 15–21)

| Phase / record | Research question | Input artifact | Output artifact | Statistical domain | TS / XS | Diagnostic / Constructive | PIT / ex-post | Consumed downstream? | Explicitly deferred |
|---|---|---|---|---|---|---|---|---|---|
| **15** `PerformanceAnalytics` | Risk & benchmark-relative stats of a backtest | `BacktestResult` (store) | `PerformanceAnalytics` | TS risk / distribution / relative stats | TS | Diagnostic | ex-post (`boundary_kind="pit"`) | **No** | multi-factor regression (→P17); batch analytics |
| **16** `SignalDiagnostics` | Does an as-of-`T` signal predict forward returns (IC)? | corpora P9/10/11 | `SignalDiagnostics` | XS predictive (rank/Pearson IC, quantiles) | XS-over-time | Diagnostic | ex-post (signal PIT) | **No** (only `compute.forward_return` reused) | multi-factor / long-short; multi-share-class |
| **17** `FactorAttribution` | How much of a strategy's excess return do K factors explain? | subject + K factor `BacktestResult`s (store) | `FactorAttribution` | TS multi-factor OLS (LDLᵀ) | TS | Diagnostic | ex-post | **No** | robust/HAC/GLS SE; annualized alpha |
| **18** `CrossSectionalRegression` | Do K signals price forward returns (Fama–MacBeth premia)? | corpora P9/10/11 | `CrossSectionalRegression` | per-date XS OLS + FM aggregation | XS-then-TS | Diagnostic | ex-post (signal PIT) | **No** | HAC SE; WLS; standardization/neutralization |
| **19** `FactorPortfolio` | Realized L/S quantile factor-return series? | corpora P9/10/11 | `FactorPortfolio` | construction + return-series summary | XS sort → TS series | **Constructive** | ex-post (signal PIT) | **Yes → P20** | rolling perf; costs; weighting schemes |
| **20** `FactorRiskModel` | Second-moment structure of N factor series? | N `FactorPortfolio`s (store) | `FactorRiskModel` | population covariance / correlation | TS (cross-factor) | Diagnostic | ex-post | **Yes → P21** | **rolling/windowed covariance**; shrinkage; optimization |
| **21** `PortfolioOptimization` | GMV weights over Σ? | 1 `FactorRiskModel` (store) | `PortfolioOptimization` | closed-form convex QP (GMV) | cross-factor static | **Constructive** | ex-post | **No (terminal leaf)** | **walk-forward**; constraints; mean-variance; risk-parity |

**Largest meaningful gap:** the constructive branch (19 → 21) terminates in an **unevaluated,
in-sample-only** weight vector. Both the immediate predecessors (20, 21) explicitly deferred
the *rolling/walk-forward* dimension. Filling it is the highest-value, best-justified next
step; it consumes the terminal leaf and validates the whole branch.

---

## 7. Alternatives Considered

At least six candidates were evaluated. Each row states: what it is, why it matters,
prerequisites present / missing, fit, duplication, prior-phase change, new PIT/data needs,
whether it seals a new artifact, whether it's phase-sized, sequencing, risks, verdict.

### A. Walk-forward OOS evaluation — **RECOMMENDED**
- **Why it matters:** the only non-tautological validation of the optimizer; closes the chain.
- **Prereqs present:** sealed `FactorPortfolio.per_period` series; `factorrisk` covariance
  estimator + `optimization` GMV solver as pure modules; `RebalanceSchedule`; exact-`Decimal`
  stack; shared sidecar. **Missing:** none that require new data — only a *windowing* driver
  (this phase) and a decision to compose the estimator/solver as libraries (§19, ★).
- **Fit:** clean additive consumer layer; references the sealed `PortfolioOptimization`
  (first consumer) and resolves the chain transitively.
- **Duplicates a phase?** No — it *composes* P20/P21 methods over sub-windows; it does not
  re-seal per-window risk models or optimizations and introduces no new estimator.
- **Requires changing a prior phase?** No. It does not modify P20/P21 specs or vocabularies;
  it imports their pure compute functions (or, if not cleanly importable, re-declares its own
  method version — §19 ★). No `_linalg` change.
- **New PIT / data requirements?** None. Inputs are ex-post factor return series; output is
  ex-post. Introduces a *train-before-test* discipline (WF-2) internal to the ex-post series.
- **New sealed artifact?** Yes — `WalkForwardEvaluation`.
- **Phase-sized?** Yes — bounded single-artifact capability with a coherent new discipline.
- **Sequencing:** enables later evaluation of *any* future optimizer (constrained,
  mean-variance) through the same split. Should precede those.
- **Risks:** re-estimation-per-window could be *seen* as re-opening P20 (rebutted: it is the
  deferred rolling-covariance use, done by composition, versions folded into identity, §13);
  determinism of mapping schedule instants onto factor `as_of` dates (handled fail-closed,
  §15); scope creep into performance analytics (bounded: reuse P19's summary vocabulary, do
  not re-derive P15).
- **Verdict: SELECT.**

### B. In-sample optimized-portfolio realization
- Realize `r_t = Σ w_i f_{i,t}` over the risk model's own window; summarize.
- **Why weak:** in-sample variance is the predicted variance (§5.1) — the risk side is
  tautological; evaluating on the fit window is poor practice. It *would* consume the sealed
  weights, but yields little research value. **Verdict: REJECT** (subsumed as the degenerate
  one-window case of A).

### C. Constrained optimization (long-only / box / gross-exposure)
- **Why it matters:** realistic mandates. **Blocker:** requires an iterative QP / active-set /
  interior-point solver — **incompatible with the exact-`Decimal`, no-iteration, no-float
  determinism rule** (invariant 21; P21 D-SOLVE). Would either introduce float/iteration
  (contradiction) or a bespoke exact-rational active-set method (a research project of its
  own). **Verdict: REJECT / SEQUENCE LATER** — the task's explicit warning ("do not assume
  constrained optimization") aligns with this. (General linear **equality** `Aw=b` is
  closed-form-compatible but is an *optimizer extension*, not an evaluation gap; deferred with
  P21's Q1.)

### D. Mean-variance / maximum-Sharpe
- **Blocker:** needs an expected-return vector `μ`. No PIT-safe expected-return artifact
  exists; using ex-post factor means as forward `μ` is look-ahead fabrication (invariant 8;
  P21 D-OBJ; PO-3). **Verdict: REJECT** until a PIT-safe expected-return artifact is built.

### E. Portfolio risk attribution / risk budgeting (MCTR / CCTR)
- **Blocker:** tautological for the current GMV artifact (§5.1: percent contribution = weight).
  Becomes meaningful only once *constrained / non-GMV* portfolios exist (Σw not constant).
  **Verdict: REJECT as premature** — depends on candidate C first.

### F. Multiple-testing / data-mining correction (Bonferroni / BH-FDR / deflated Sharpe)
- **Why it matters:** the platform can generate many `SignalDiagnostics` / `CrossSectionalRegression`
  / `FactorPortfolio` t-stats; naïve significance is inflated. **Concerns:** the input is a
  *heterogeneous set* of previously-sealed records with no natural single-artifact container;
  it does not consume Phase 21; it is a meta-analysis layer better sequenced once a "research
  campaign" grouping artifact exists. **Verdict: DEFER** — genuine future phase, weaker fit now.

### G. Report-scope extension (make P15–21 artifacts reportable)
- **Why it matters:** today `ResearchReport` can reference only backtests/experiments; none of
  the P15–21 artifacts is reportable. **Concern:** this is a presentation/convenience layer
  ("does not merely add convenience APIs"). Real, but not a *research* capability.
  **Verdict: DEFER** (note it as a small future reporting bump).

### H. Factor / portfolio exposure analytics
- The weights *are* the factor exposures; "exposure analytics" over a factor-weight vector is
  near-tautological and thin. **Verdict: REJECT.**

### I. Factor-model extensions (shrinkage, PCA, EWMA covariance)
- Modifies/extends P20's estimator vocabulary — **prematurely expands an earlier phase**
  (charter constraint 6); P20 explicitly excludes shrinkage. **Verdict: REJECT.**

---

## 8. Prerequisite Analysis

| Prerequisite | Present? | Evidence / note |
|---|---|---|
| Sealed factor **return series** to walk forward | ✅ | `FactorPortfolio.per_period` (P19) |
| Transitive resolution P21 → P20 → P19 | ✅ | `PortfolioOptimization.risk_model_ref`; `FactorRiskModel.factor_refs` |
| Covariance estimator reusable on a sub-window | ✅ (compose) | `factorrisk` pure moment/covariance compute (`factorrisk/stats.py`) |
| GMV solver reusable on a sub-window | ✅ (compose) | `optimization/solve.py` `solve_min_variance` + `_linalg` `ldl`/`ldl_solve` |
| Rebalance schedule of decision instants | ✅ | `RebalanceSchedule` (P12) — ordered aware-UTC instants, content-addressed |
| Return-series performance summary vocabulary | ✅ (reuse shape) | `FactorPortfolio.summary` (cumulative/mean/vol/Sharpe/t/hit) |
| Exact-`Decimal` + write-once sidecar + identity | ✅ | shared infra (§2.2) |
| Expected-return vector `μ` | ❌ (not needed) | v1 objective inherited from the recipe = GMV, needs only Σ |
| Iterative QP solver | ❌ (not needed / disallowed) | not required for GMV; would break determinism (§9) |
| New `_linalg` primitive | ❌ (not needed) | quadratic form done inline as in P21 |

**Missing prerequisites that are genuinely required: none.** The one load-bearing *decision*
(not a missing capability) is whether to **compose** the P20 estimator and P21 solver as
imported pure functions or **promote** them to a shared module (§19, ★). Recommended:
compose by import and fold their version constants into Phase 22's identity (§13).

---

## 9. Contradiction / Invariant Analysis

Interactions classified as **COMPOSES** (fits cleanly), **CONSTRAINS** (allowed but bounds
the design), **TENSION** (needs explicit handling), **CONTRADICTION** (would force rejection).

| Invariant / rule | Class | Explanation |
|---|---|---|
| **1–7, 21** determinism / no wall-clock / no RNG / reproducibility | COMPOSES | Windowing is schedule-driven and exact-`Decimal`; no float/RNG/clock in any value or id. |
| **8** acceptance≠availability / **no fabricated data** | COMPOSES | No new corpus read; no `μ` fabricated; inputs are sealed ex-post series. |
| **27** mode explicit | COMPOSES | No new resolution query; consumes sealed ex-post artifacts, not `PIT`/`REVISED` values. |
| **28** REVISED is not a PIT source | COMPOSES | Output is ex-post, never offered as a PIT value (WF-3). |
| **29** PIT monotonic / past-closed | COMPOSES (spirit mirrored) | Not a PIT query, but WF-2 mirrors it: the training window for `T_k` uses only returns with `as_of ≤ T_k`; test returns are strictly after `T_k`. |
| **SD-1 / XS-1 / P19-1** corpus pinning | COMPOSES | Corpus pins are inherited (surfaced as `pin_mismatch`) from the referenced chain; not re-derived. |
| **FR-1 / PO-1** reference verification + transitive pinning | COMPOSES → **WF-1** | Resolve + verify the referenced `PortfolioOptimization`; fold its `result_hash`; transitively pin risk model → factors → corpora. |
| **PO-2 / FR-2 / P19-2 / SD-2 / XS-2** "not a PIT value" | COMPOSES → **WF-3** | Ex-post; not a `Pit*` type; no as-of accessor; `boundary_kind="pit"` documents only the underlying PIT walks. |
| **PO-5 / FR-5 / P19-5** "not a `BacktestResult`; no execution" | COMPOSES → **WF-3** | Distinct record type; no fills/cash/positions/costs; not interchangeable with `BacktestResult`. |
| **PO-3** single covariance source / no fabricated inputs | COMPOSES → **WF-5** | Uses the Phase 20 estimator method only; introduces no second estimator, no shrinkage, no `μ`. |
| **PO-4 / FR-4 / XS-4 / P19-4** fail-closed degeneracy, never repaired | COMPOSES → **WF-4** | A window with too-few training periods, singular training covariance, or an empty test window → recorded UNDEFINED window, never fabricated/dropped/regularized. |
| **Identity / content-addressing** (§11) | CONSTRAINS | Must fold engine + composed-method versions + referenced `optimization_id` + its `result_hash` + the answer hash; `research_result_id` aliases the new id. |
| **`ResearchRecord` / write-once store** | COMPOSES | New record implements the Protocol; seals write-once to the shared sidecar; byte-identical idempotent re-seal. |
| **Decimal determinism** | CONSTRAINS | All arithmetic under the pinned context; volatility via `Decimal.sqrt`; no float. |
| **Re-estimating covariance per window vs P20's full-window seal** | **TENSION** | *Not* a contradiction: P20's artifact is full-sample by design and cannot be windowed. Phase 22 does not mutate or re-seal P20; it applies P20's *method* to sub-windows (the deferred "rolling covariance") and folds P20's method version into its own identity. Resolved by composition + version folding (§13, §19 ★). |
| **Ephemeral per-window covariances/weights are not sealed** | **TENSION** | Consistent with existing engines computing intermediates internally (P20 computes moments; P21 reconstructs Σ). The evaluation seals *one* record; the per-window intermediates are provenance-summarized (predicted variance, window bounds, status), not re-sealed as P20/P21 artifacts. |
| **Iterative QP for constraints** | **CONTRADICTION** (for candidate C, not for A) | Documented here to show *why* Phase 22 is evaluation, not constrained optimization: an iterative solver would violate invariant 21 / P21 D-SOLVE. Phase 22's inherited objective is closed-form GMV, so no contradiction arises. |

**No contradiction forces rejection of the recommended capability.** The two TENSIONs are
resolved by composition + identity version-folding and by the established
"intermediates-are-internal" pattern. The one CONTRADICTION is with a *rejected* alternative
(constrained optimization), reinforcing the choice.

---

## 10. Architecture

New package **`src/quantforge/walkforward/`**, mirroring the P20/P21 layout:

- `errors.py` — `WalkForwardError` → `WalkForwardConfigurationError`, `WalkForwardConsistencyError`.
- `version.py` — `WalkForwardEvaluationEngineVersion` (folds the pinned decimal context **and**
  the composed method versions — the walk-forward method version, the reused covariance-estimator
  version, and the reused GMV-solve version — into `config_hash`); constants
  `WALKFORWARD_SPEC_VERSION = "walkforward/1"`, `WALKFORWARD_ENGINE_VERSION = "walkforward-engine/1"`,
  `WALKFORWARD_METHOD_VERSION = "walkforward-method/1"`; `default_decimal_context()`.
- `model.py` — vocabulary: `WindowStatus` (`REALIZED` | `UNDEFINED`), `WalkForwardUndefinedReason`
  (`INSUFFICIENT_TRAINING`, `SINGULAR_TRAINING_COVARIANCE`, `EMPTY_TEST_WINDOW`); `StatValue`
  (KNOWN decimal string | UNDEFINED + reason), reusing the established cell discipline.
- `spec.py` — `WalkForwardEvaluationSpecification` (declarative request; §12).
- `windows.py` — pure, deterministic partition of the aligned factor return series into ordered
  `(train, test)` windows given a schedule + training policy (no store, no corpus).
- `evaluate.py` — the pure compute core: per window, compose the covariance estimate and the
  GMV solve (via `factorrisk`/`optimization` pure functions), realize the OOS returns, and
  chain them; returns a `WalkForwardOutcome` (windows + chained series + summary). Pure; reads
  no store.
- `result.py` — `WalkForwardEvaluation` (`ResearchRecord`; `.seal` / `to_dict` / `from_dict`),
  plus `WindowResult`, `OosReturn`, and a realized-performance `summary` block; constants
  `WALKFORWARD_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`.
- `identity.py` — `walkforward_result_hash`, `walk_forward_id`; domain tag `walkforward/1`.
- `engine.py` — `WalkForwardEvaluationEngine`: resolve + verify the referenced
  `PortfolioOptimization` → resolve its `FactorRiskModel` → resolve the N `FactorPortfolio`s →
  extract + complete-case align the return series → partition into windows → per-window
  estimate/solve/realize → chain + summarize → `.seal(...)` → `store.write`.
- `__init__.py` — exports `WalkForwardEvaluationSpecification`, `WalkForwardEvaluation`
  (+ vocabulary/errors).

**Edits to existing source (all additive, none altering any existing identity):**
1. `workspace.py` — one lazy `walk_forward_engine` `@property` (+ cache slot), following the
   `optimization_engine` template.
2. `src/quantforge/__init__.py` — top-level re-exports of `WalkForwardEvaluationSpecification`
   and `WalkForwardEvaluation` (engine reached via `Workspace`).
3. `tests/test_smoke.py` — one additive export assertion.

**No edit to** `_linalg`, `factorrisk`, `optimization`, `backtest`, or any other prior-phase
identity/vocabulary. If the `factorrisk`/`optimization` pure functions are not cleanly
importable as window-agnostic pure functions, the fallback is for Phase 22 to declare its own
`walkforward-method/1` covariance+GMV compute in `evaluate.py` (still exact-`Decimal`, still
`ldl`/`ldl_solve`) rather than modify those packages — a decision surfaced in §19 (★).

---

## 11. Data Flow

```
WalkForwardEvaluationSpecification { optimization_id, schedule, training_policy, name, ... }
        │
        ▼  WalkForwardEvaluationEngine.evaluate(spec)
resolve PortfolioOptimization by optimization_id                        — fail closed (WF-1)
   store.read_as(id, PortfolioOptimization.from_dict); verify research_result_id == id;
   verify status is OPTIMAL (an UNDEFINED/singular recipe cannot be walked forward)  (WF-1)
        │
        ├─ read recipe: objective + constraint_spec + factor set        (inherited, WF-5)
        ▼
resolve FactorRiskModel via risk_model_ref                             — fail closed (WF-1)
        │  read factor_refs (ordered factor_portfolio_ids + hashes)
        ▼
resolve each FactorPortfolio via factor_refs                           — fail closed (WF-1)
        │  extract per_period (as_of, factor_return) KNOWN series
        ▼
complete-case align on the common date axis                            — never fill/impute (WF-4)
   (a date where any factor is UNDEFINED is excluded)
        │
        ▼
partition the aligned axis into ordered (train_k, test_k) windows on the schedule + policy
   train_k = returns with as_of ≤ T_k ;  test_k = returns in (T_k, T_{k+1}]   (WF-2)
        │
        ▼  per window k (deterministic, exact-Decimal, no look-ahead across the split):
   Σ_k = covariance(train_k)         [compose Phase 20 method]         — WF-5
   if |train_k| < min_train  → UNDEFINED window (INSUFFICIENT_TRAINING)  — WF-4
   w_k = solve GMV(Σ_k)              [compose Phase 21 method]
   if Σ_k not PD                     → UNDEFINED window (SINGULAR_TRAINING_COVARIANCE) — WF-4
   if test_k empty                   → UNDEFINED window (EMPTY_TEST_WINDOW)            — WF-4
   for each t in test_k:  r_t = Σ_i w_{k,i} · f_{i,t}    (weights held over the test window)
   predicted_var_k = w_kᵀ Σ_k w_k
        │
        ▼
chain the OOS r_t across all REALIZED windows → OOS return series
compute realized summary (cumulative, mean, population vol, annualized Sharpe, t-stat, hit)
compute realized OOS variance and per-window predicted-vs-realized variance
        │
        ▼
WalkForwardEvaluation.seal(...)  →  ResearchResultStore.write (write-once, idempotent)
        │
        ▼
store.read_as(id, WalkForwardEvaluation.from_dict)   (byte-identical typed round-trip)
```

---

## 12. Public API

```python
from quantforge import (
    Workspace,
    WalkForwardEvaluationSpecification,
    WalkForwardEvaluation,
)

ws = Workspace.open(root)

spec = WalkForwardEvaluationSpecification(
    name="gmv-value-momentum-wf",
    optimization_id=optimization_id,  # a sealed PortfolioOptimization (the recipe)
    schedule=rebalance_schedule,  # RebalanceSchedule of OOS decision instants
    training_policy=TrainingPolicy(  # ★ approval-gated shape (§19)
        window="expanding",  # or "rolling"
        min_train_periods=24,
        rolling_length=None,  # required iff window == "rolling"
    ),
    # objective / constraint are INHERITED from the referenced PortfolioOptimization (WF-5)
)

evaluation = ws.walk_forward_engine.evaluate(spec)  # sealed, write-once

evaluation.status  # WindowStatus roll-up (has ≥ min valid windows?)
evaluation.windows  # per-window: train/test bounds, weights, predicted var, status
evaluation.oos_returns  # chained OOS realized factor-combination return series
evaluation.summary  # realized cumulative / mean / vol / Sharpe / t-stat / hit
evaluation.realized_variance  # realized OOS variance (StatValue)
evaluation.predicted_vs_realized  # per-window predicted vs realized variance
evaluation.pin_mismatch  # inherited corpus-pin flag
evaluation.research_result_id  # == evaluation.walk_forward_id

again = ws.research_result_store.read_as(
    evaluation.research_result_id, WalkForwardEvaluation.from_dict
)
```

`WalkForwardEvaluationEngine` is reached only through `Workspace.walk_forward_engine` (lazy,
cached, `-> object`). `evaluate(spec) -> WalkForwardEvaluation` is the single entry point. No
`Company` method is added.

**`WalkForwardEvaluationSpecification` (frozen slots):** `name`, `optimization_id`,
`schedule` (`RebalanceSchedule`), `training_policy` (`TrainingPolicy`), `spec_version =
"walkforward/1"`. Construction-time validation (fail closed): non-empty `name` /
`optimization_id` / `spec_version`; a valid `training_policy` (`window ∈ {"expanding","rolling"}`;
`min_train_periods ≥ _MIN_TRAIN`; `rolling_length` present iff `rolling`, and `≥ min_train_periods`);
a non-empty schedule. It reads no store — it cannot know whether the recipe exists (engine's
job, WF-1) or whether any window's covariance is PD (needs the resolved data).

---

## 13. Identity and Hashing

- Domain tags via shared `sha256_hex`, NUL-separated, canonical JSON, `sha256:`-prefixed:
  record `walkforward/1`; engine `walkforward-engine/1`; method `walkforward-method/1`.
- `walkforward_engine_version_id = sha256(code_version "walkforward-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=walkforward-method/1
  \x00cov=<factorrisk formula_version>\x00solve=<optimization solve_version>")`. **Folding the
  reused covariance-estimator and GMV-solve versions** makes the evaluation's identity change
  if either composed method changes — the discipline that resolves the §9 TENSION.
- `walkforward_result_hash = sha256(canonical JSON over the ordered computed-output blocks:
  the per-window blocks in schedule order — each `{block:"window", index, train_bounds,
  test_bounds, status, weights?, predicted_variance?}` — then the chained OOS return series,
  then the summary block, then the realized-variance block)`. Sensitive to every computed
  value and to window order.
- `walk_forward_id = sha256`, NUL-joined, in order: `walkforward/1`,
  `walkforward_engine_version_id`, `name`, `spec_version`, the canonical-JSON `schedule_id`,
  the canonical-JSON `training_policy`, `optimization_id`, the referenced
  `optimization.result_hash` (transitive pin, WF-1), and `walkforward_result_hash`.
- `research_result_id` aliases `walk_forward_id`.

**Folds (change identity):** engine + method + decimal-context + **composed cov/solve
versions**; the declared request (name, spec version, schedule id, training policy); the
referenced `optimization_id` **and** its `result_hash` (transitive pin through P21→P20→P19→corpus);
the computed answer. **Does NOT fold:** the record format version (container concern);
inherited corpus pins (surfaced via `pin_mismatch`, per the D-PIN convention); presentation,
wall-clock, RNG, `id()`, or iteration order (windows carry explicit indices).

---

## 14. Determinism / Decimal Rules

- All arithmetic under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); volatility
  via `Decimal.sqrt(context)`. No float anywhere.
- Covariance per window and the GMV solve reuse the exact-`Decimal` P20/P21 methods
  (`ldl`/`ldl_solve`), inheriting their exact zero-pivot singularity test — no float tolerance.
- Window partitioning is a pure function of the schedule instants and the aligned `as_of`
  axis: deterministic, total, order-independent of input enumeration. No wall-clock, no RNG.
- Same recipe + same schedule + same training policy → same `walk_forward_id` and byte-identical
  payload on any machine.

---

## 15. Failure / UNDEFINED Semantics

Follows the established split — **defects raise, data conditions are recorded.**

**Raised** (`WalkForwardConfigurationError` / `WalkForwardConsistencyError`):
- Malformed spec (empty fields; invalid training policy; empty schedule). *(configuration)*
- A non-`WalkForwardEvaluationSpecification` argument. *(configuration)*
- `optimization_id` absent; payload not a `PortfolioOptimization`; resolved id disagreement;
  a recipe whose `status` is not `OPTIMAL` (a singular in-sample recipe is not walkable).
  *(consistency, WF-1)*
- The transitively-referenced `FactorRiskModel` or any `FactorPortfolio` missing / not
  decoding / id-mismatched. *(consistency, WF-1)*
- A schedule instant that cannot be deterministically placed on the aligned `as_of` axis, or a
  schedule producing **zero** candidate windows. *(consistency)*
- Fewer than `_MIN_VALID_WINDOWS` (≥ 2) REALIZED windows after evaluation — no defensible OOS
  summary. *(consistency; mirrors P19 `_MIN_VALID_PERIODS`, P20 `_MIN_PERIODS`)*

**Recorded as first-class `UNDEFINED` (never raised, never fabricated, never repaired — WF-4):**
- A window with fewer than `min_train_periods` training observations → `WindowStatus.UNDEFINED`,
  reason `INSUFFICIENT_TRAINING`.
- A window whose training covariance is not positive-definite → `SINGULAR_TRAINING_COVARIANCE`
  (the exact `ldl` zero-pivot test).
- A window with an empty test span → `EMPTY_TEST_WINDOW`.
An UNDEFINED window contributes **no** OOS returns and **no** weights; it is retained in
`windows` with its reason. The evaluation is still sealed and persisted.

**Surfaced, never raised (inherited D-PIN convention):** a non-singular corpus-pin set carried
from the referenced chain → `pin_mismatch = True`.

---

## 16. Persistence

Zero new store types. `WalkForwardEvaluation` is a `ResearchRecord` written write-once to the
existing `<root>/research/` sidecar via `ResearchResultStore.write`. Idempotent: re-evaluating
an identical spec is a byte-identical no-op; a differing payload under an existing id fails
closed via the store's guard. `from_dict` is the fail-closed inverse; derived ids are
re-computed, never read from state, so `from_dict(to_dict(r))` re-emits identical bytes and a
tampered stored id is ignored. It stores **no** copy of any covariance matrix or corpus — only
the transitive references, the per-window summaries (bounds, weights, predicted variance,
status), the chained OOS series, and the realized summary.

---

## 17. Testing Strategy

New `tests/walkforward/` (`__init__.py`, `builders.py`, `test_spec.py`, `test_windows.py`,
`test_evaluate.py`, `test_identity.py`, `test_result.py`, `test_engine.py`), offline and
synthetic. As in `tests/optimization`, builders **synthesize** a sealed `PortfolioOptimization`
+ its `FactorRiskModel` + the underlying `FactorPortfolio`s directly from hand-chosen factor
return series persisted to a real sidecar, giving exact control over windows and degeneracy
while exercising the true resolve → align → partition → estimate → solve → realize → seal path.

- **Spec validation** — minimal request; canonical payload; every fail-closed path (empty
  fields; bad training policy — rolling without length, length < min, unknown window kind;
  empty schedule).
- **Window partition** (`test_windows`) — deterministic expanding vs rolling partitions;
  strict train-before-test boundary (WF-2, the load-bearing property: assert no test index is
  ≤ its train cutoff); exact window counts; edge cases (single feasible window → fail closed on
  `_MIN_VALID_WINDOWS`).
- **Evaluate core** (`test_evaluate`) — hand-computed OOS returns on a tiny 2–3 factor series
  under the pinned context; weights-held-over-test-window realization; predicted-vs-realized
  variance where they *differ* OOS (guards against the in-sample tautology, §5.1); UNDEFINED
  windows for insufficient-training / singular-training / empty-test; determinism of a repeated
  evaluation.
- **Identity** — `walk_forward_id` fold + per-input sensitivity (engine version, name, schedule,
  training policy, referenced `optimization_id`, its `result_hash`, result hash); composed
  cov/solve version folding; `walkforward_result_hash` per-block + order sensitivity.
- **Result** — byte-identical `to_dict`/`from_dict`; derived-id survival; `research_result_id`
  alias; `pin_mismatch`; ex-post boundary (no `pit`/`as_of` accessor; not a `BacktestResult`);
  tampered-id ignored; differing-answer id sensitivity.
- **Engine end-to-end** — the multi-window known OOS series; WF-1 reference verification
  (missing / non-`PortfolioOptimization` / id-mismatch / non-OPTIMAL recipe each fail closed);
  transitive resolution failures; identity sensitivity to the referenced recipe; persistence +
  round-trip; idempotent re-eval; two-independent-workspaces agreement; `pin_mismatch` surfaced;
  `walk_forward_engine` wiring cached.
- `tests/test_smoke.py` — additive export assertion.

Quality gate identical to prior phases: `ruff check` / `ruff format --check` / `mypy src tests`
/ `pytest -q` and `pytest -q -p no:randomly`, all green; zero runtime dependencies.

---

## 18. Documentation Impact

*After* implementation and a green gate (never before):
- **New:** `docs/phase22-walk-forward-evaluation-locked.md` (reflecting the actual build +
  disclosed deviations).
- **Update:** `README.md` (capability bullet + v0.19.0 row + Next), `ARCHITECTURE.md` (a
  "Walk-forward evaluation" row), `docs/index.md` (Phase 22 entry + Status → Phases 1–22),
  `docs/data-model.md` §12 (append the **WF-1..WF-6** block; additive, weakening nothing).

This proposal modifies **none** of those files.

---

## 19. Approval-Gated Decisions

Mark ★ = load-bearing (materially shapes identity, semantics, or scope).

1. ★ **Input artifact = the sealed `PortfolioOptimization` (recipe).** Alternative: reference a
   `FactorRiskModel` or the raw `FactorPortfolio`s directly. Recommend the recipe — it is the
   first consumer of Phase 21 and gives maximal transitive pinning (WF-1). *Approve the input
   type.*
2. ★ **Compose vs promote the P20 estimator + P21 solver.** Recommend **compose** by importing
   the pure functions and folding their version constants (§13); fallback is a self-contained
   `walkforward-method/1` compute (no edit to P20/P21). *Approve compose-vs-promote.*
3. ★ **Objective/constraint are inherited from the recipe (GMV / fully-invested only).** No new
   objective is introduced in v1. *Approve inheritance; approve GMV-only v1.*
4. ★ **Training-window policy shape** — `expanding` vs `rolling`; `min_train_periods`;
   `rolling_length`. This is a genuine methodological choice folded into identity. *Approve the
   `TrainingPolicy` vocabulary and whether both window kinds ship in v1.*
5. ★ **Weights held constant over each test window** (a fixed allocation applied to each test
   period's factor returns), re-optimized only at each rebalance `T_k`. Alternative: intra-window
   drift/compounding. Recommend held-constant (the standard rebalance convention). *Approve.*
6. ★ **Test-window return convention** — `r_t = Σ_i w_{k,i} · f_{i,t}` per period (weighted sum
   of per-period factor returns), then chained via `∏(1+r_t)−1` for the cumulative. *Approve the
   realization + chaining formula.*
7. ★ **Fold the composed cov/solve versions into engine identity** (§13). *Approve.*
8. ★ **`_MIN_TRAIN`, `_MIN_VALID_WINDOWS` (≥2), and `N_MAX = 16` inheritance.** *Approve the
   floors.*
9. **Predicted-vs-realized variance is sealed** per window and in aggregate. *Approve inclusion.*
10. **Realized-performance summary reuses P19's vocabulary** (cumulative/mean/population-vol/
    annualized-Sharpe/t-stat/hit), with `periods_per_year` inherited from the chain. Recommend
    reuse-the-shape (do not re-derive Phase 15). *Approve the summary field set.*
11. **UNDEFINED reason vocabulary** = `{INSUFFICIENT_TRAINING, SINGULAR_TRAINING_COVARIANCE,
    EMPTY_TEST_WINDOW}` (closed). *Approve.*
12. **Naming** — package `walkforward`; types `WalkForwardEvaluationSpecification` /
    `WalkForwardEvaluation`; engine `WalkForwardEvaluationEngine.evaluate`; property
    `walk_forward_engine`; domain tags `walkforward/1`, `walkforward-engine/1`,
    `walkforward-method/1`. *Approve names.*
13. ★ **Version = v0.19.0.** *Approve.*
14. **Annualization basis** = the referenced chain's `periods_per_year` (not re-declared).
    *Approve inheritance.*

No decision on this list is silently pre-made; each is surfaced for approval.

---

## 20. New Invariants (proposed, phase-local — not added to the global catalog now)

Naming follows the established convention (SD-/XS-/P19-/FR-/PO-). These would be added to
`docs/data-model.md §12` **only at implementation time**, additively.

- **WF-1. Reference verification and transitive pinning.** The evaluation resolves the single
  referenced `PortfolioOptimization`, re-verifies its `research_result_id`, requires its
  `status = OPTIMAL`, and resolves the transitively-referenced `FactorRiskModel` and every
  `FactorPortfolio`; any missing / non-decoding / id-mismatched reference fails closed. The
  recipe's `result_hash` is folded into `walk_forward_id`, so identity is transitively sensitive
  to any change in the recipe, its risk model, its factors, or their corpora. *Necessary because
  an OOS evaluation is only meaningful relative to a specific, fully-pinned recipe (the PO-1/FR-1
  discipline, one layer up).*
- **WF-2. Strict train-before-test split (no look-ahead across the estimation boundary).** For
  each rebalance `T_k`, the covariance is estimated using only factor returns with `as_of ≤ T_k`,
  and the weights are applied only to realized returns strictly after `T_k`. No test return ever
  enters an estimation window. *Necessary because it is the entire point of the phase: it is the
  ex-post analog of the PIT no-look-ahead rule (invariant 29), applied to the estimation/
  application boundary; violating it silently re-creates the in-sample tautology (§5.1).*
- **WF-3. A walk-forward evaluation is not a PIT value and not a `BacktestResult`.**
  `WalkForwardEvaluation` is ex-post, not a `Pit*` type, exposes no as-of accessor
  (`boundary_kind="pit"` documents only the underlying PIT walks), is a distinct record type, and
  simulates no fills / cash / positions / costs. *Necessary to preserve the PO-2/PO-5/FR-2/FR-5
  boundaries one layer up and prevent an evaluation from masquerading as a tradable/PIT artifact.*
- **WF-4. Fail-closed window degeneracy, never repaired.** A window with insufficient training
  periods, a non-positive-definite training covariance, or an empty test span is a recorded
  `UNDEFINED` window with its reason — never fabricated, dropped, filled, or regularized; a run
  with fewer than `_MIN_VALID_WINDOWS` REALIZED windows fails closed. *Necessary: the XS-4/P19-4/
  PO-4 posture, adapted to windows; a silently-dropped bad window would bias the OOS series.*
- **WF-5. Single methodology source; no fabricated inputs.** The per-window covariance and GMV
  weights are produced by the Phase 20 estimator and Phase 21 solver methods only (their versions
  folded into identity); the objective/constraint are inherited from the recipe. No second
  covariance estimator, no shrinkage/regularization, no expected-return / risk-free / benchmark
  input is introduced. *Necessary to keep the evaluation a faithful test of the actual recipe (the
  PO-3 discipline) rather than of a silently different method.*
- **WF-6. Complete-case alignment is deterministic and shared across factors.** The evaluated
  return axis is the intersection of `as_of` dates where **every** factor is KNOWN, ascending;
  a date where any factor is UNDEFINED is excluded, never filled or interpolated; window bounds
  are a pure, total function of the schedule and this axis. *Necessary for determinism and to
  avoid mixing differently-covered factors within a window (the FR-4 complete-case rule, reused).*

---

## 21. Proposed Files (implementation stage only — none created now)

```
src/quantforge/walkforward/__init__.py
src/quantforge/walkforward/errors.py
src/quantforge/walkforward/version.py
src/quantforge/walkforward/model.py
src/quantforge/walkforward/spec.py
src/quantforge/walkforward/windows.py
src/quantforge/walkforward/evaluate.py
src/quantforge/walkforward/result.py
src/quantforge/walkforward/identity.py
src/quantforge/walkforward/engine.py

tests/walkforward/__init__.py
tests/walkforward/builders.py
tests/walkforward/test_spec.py
tests/walkforward/test_windows.py
tests/walkforward/test_evaluate.py
tests/walkforward/test_identity.py
tests/walkforward/test_result.py
tests/walkforward/test_engine.py

docs/phase22-walk-forward-evaluation-locked.md   (post-implementation)
```

Additive edits at implementation stage: `src/quantforge/workspace.py` (+`walk_forward_engine`),
`src/quantforge/__init__.py` (2 re-exports), `tests/test_smoke.py` (1 assertion), and the §18
doc updates. **None of these is created or edited by this proposal.**

---

## 22. Out of Scope (strict)

- **Constrained optimization** (long-only/box/gross/leverage/concentration) and any iterative
  QP/active-set/interior-point solver — breaks exact-`Decimal` determinism (§9).
- **Mean-variance / max-Sharpe / any expected-return objective** — no PIT-safe `μ` exists.
- **New objectives or constraints** — v1 inherits the recipe's GMV/fully-invested only.
- **Risk attribution / risk budgeting (MCTR/CCTR)** — tautological for GMV (§5.1); deferred.
- **Shrinkage / EWMA / factor-model / robust covariance** — would expand Phase 20's estimator.
- **Regime-conditioning, transaction costs, turnover penalties, execution** — no fills/cash/
  positions/costs; not a `BacktestResult` (WF-3).
- **Multiple-testing correction, report-scope extension** — separate future phases (§7 F/G).
- **Any modification to Phase 12/19/20/21 vocabulary, engine, or identity; any `_linalg`
  change; any new store, database, PIT surface, data source, UI, or runtime dependency.**
- **Any PIT-eligible / tradable output** — the evaluation is ex-post only.

---

## 23. Version

Phase 20 = v0.17.0, Phase 21 = v0.18.0 (each phase a `+0.01.0` minor bump; confirmed by the
README release table and git tags). **Phase 22 releases as `v0.19.0`.** Domain tags:
`walkforward/1` (record), `walkforward-engine/1` (engine), `walkforward-method/1` (method).

---

## 24. Open Questions

1. **Are `factorrisk`/`optimization` pure functions cleanly importable as window-agnostic
   compute?** If yes → compose (recommended, §19.2). If entangled with their engines → declare a
   self-contained `walkforward-method/1` compute (still `ldl`/`ldl_solve`), no edit to P20/P21.
   *(Resolve during implementation; does not change the public shape.)*
2. **`expanding` vs `rolling` in v1 — one or both?** Both are one small `windows.py` branch;
   shipping both is cheap but each adds an identity-folded knob. *(§19.4 ★)*
3. **Schedule instant → `as_of` axis mapping.** Exact rule for placing a rebalance instant onto
   the factor return dates (nearest prior KNOWN date ≤ instant, fail closed if none). *(§15)*
4. **Predicted-vs-realized reconciliation metric** — seal the raw pair per window (recommended),
   or also a summary tracking-error-style scalar? *(§19.9)*
5. **Minimum floors** — `_MIN_TRAIN`, `_MIN_VALID_WINDOWS` exact values. *(§19.8 ★)*
6. **Does the recipe's `constraint_spec` need to be re-validated each window** (it is trivially
   `{fully_invested: True}` in v1)? Recommended: assert it is the v1 GMV constraint and fail
   closed otherwise, so a future constrained recipe cannot be silently walked forward under GMV.

---

## Final Recommendation

Implement **Phase 22 = Walk-Forward Out-of-Sample Evaluation** as specified above:
a pure-consumer, ex-post, content-addressed `WalkForwardEvaluation` that references one sealed
`PortfolioOptimization`, resolves the factor return series transitively through the existing
chain, re-estimates and re-optimizes the recipe over ordered train→test windows with a strict
no-look-ahead split, and seals the chained out-of-sample return series, its realized-performance
summary, and per-window predicted-vs-realized variance — at **v0.19.0**, composing the existing
Phase 20 covariance estimator and Phase 21 GMV solver, changing no prior phase and no `_linalg`,
and preserving every existing invariant while adding WF-1..WF-6.

It is the **first genuine consumer of Phase 21**, the **highest-value missing step** in the
research workflow (out-of-sample validation of the entire construction chain), and the only
evaluation of a minimum-variance optimizer that is not tautological. It is explicitly **not**
constrained optimization, mean-variance, or risk attribution — each of which the repository
shows to be blocked by determinism, a missing PIT-safe expected-return artifact, or GMV
tautology, respectively.

**Awaiting explicit approval before any implementation.**
