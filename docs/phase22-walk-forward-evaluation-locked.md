# Phase 22 — Walk-Forward Out-of-Sample Evaluation (LOCKED)

> **Status:** Locked normative specification. The Phase 22 proposal was **approved as
> recommended** ("yep approved go ahead") — the sealed `PortfolioOptimization` as the walked
> recipe (Q19.1), **compose** the Phase 20 covariance estimator + Phase 21 GMV solver as
> imported pure functions and fold their versions (Q19.2), objective/constraint inherited
> (GMV / fully-invested only, Q19.3), the `TrainingPolicy` vocabulary with **both**
> expanding and rolling windows shipping in v1 (Q19.4), weights held constant over each test
> window (Q19.5), the `r_t = Σ_i w_{k,i}·f_{i,t}` realization + `∏(1+r_t)−1` chaining
> (Q19.6), composed cov/solve/summary versions folded into engine identity (Q19.7), the
> `_MIN_TRAIN`/`_MIN_VALID_WINDOWS (≥2)`/`N_MAX = 16` floors (Q19.8), predicted-vs-realized
> variance sealed per window and in aggregate (Q19.9), the Phase 19 summary vocabulary reused
> (Q19.10), the closed UNDEFINED-reason vocabulary (Q19.11), the names (Q19.12), `v0.19.0`
> (Q19.13), and inherited annualization (Q19.14). This document reflects the **actual
> implementation** and is the source of truth; it supersedes the recommendations in
> [phase22-walk-forward-evaluation-proposal.md](phase22-walk-forward-evaluation-proposal.md).
> Every conditional reference in the proposal ("recommended", "approval-gated") is resolved
> here to a committed decision, and the proposal's open questions (§24) are resolved in §1.1.
>
> **One-line thesis:** Phase 22 adds a deterministic, content-addressed **walk-forward
> out-of-sample (OOS) evaluation** — the first genuine *consumer* of the Phase 21 optimizer
> and the project's first *train-before-test* temporal discipline. Given a declarative
> `WalkForwardEvaluationSpecification` naming exactly one sealed `PortfolioOptimization` (the
> GMV *recipe*) and a `TrainingPolicy`, `WalkForwardEvaluationEngine.evaluate(...)` resolves
> that recipe from the shared Phase 8 research sidecar, re-verifies it (and, transitively,
> its `FactorRiskModel` and every `FactorPortfolio`), complete-case aligns the factors'
> KNOWN `(as_of, factor_return)` series on a common time axis, partitions that axis into
> ordered `train → test` windows, and — per window — **re-estimates** the covariance (Phase
> 20 method) on the training span, **re-solves** the fully-invested GMV weights (Phase 21
> method), and **realizes** those weights against the *strictly subsequent* test returns
> (WF-2, no look-ahead). It chains the OOS returns, summarizes them (Phase 19 method), seals
> the per-window predicted-vs-realized variance, and writes a `WalkForwardEvaluation`
> `ResearchRecord` write-once to the existing sidecar. It introduces **no** new numerical
> formula (it composes three pinned pure functions), **no** new data source, **no** new
> store, **no** runtime dependency, **no** new PIT surface, **no** `_linalg` change, and
> **no** modification to any prior phase's vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **The one non-tautological evaluation of the GMV optimizer: out-of-sample walk-forward.** Given a sealed recipe, re-estimate + re-solve on each training window and realize the weights on the strictly-subsequent test window; seal the chained OOS series, its performance summary, and per-window predicted-vs-realized variance. **No** constrained optimization, mean-variance/max-Sharpe, risk attribution/budgeting, shrinkage/EWMA/robust covariance, regime-conditioning, transaction costs, turnover, or execution — each deferred or rejected with a grounded repository reason (§9 of the proposal). It performs **no execution** and is **not** a `BacktestResult` (WF-3). |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 21.** It resolves exactly one already-sealed `PortfolioOptimization` (the recipe) from the shared sidecar, and transitively its `FactorRiskModel` and `FactorPortfolio`s. It reads **no** raw corpus, creates **no** second covariance estimator, fabricates **no** expected-return / `μ`, and **modifies no** prior-phase vocabulary, engine, or identity. It is the first functional consumer of the Phase 21 terminal leaf. |
| **D-WINDOWS** | **Windows are derived from the complete-case-aligned `as_of` axis + a `TrainingPolicy` cadence — not a separate `RebalanceSchedule` input** (deviation, §1.1). Rebalance cuts `c_k = min_train_periods + k·test_periods` while `c_k < M`; **expanding** train span `[0, c_k)`, **rolling** train span `[max(0, c_k − rolling_length), c_k)`; test span `[c_k, min(c_k + test_periods, M))`. Every emitted window satisfies **WF-2** `train_end == test_start`, has a training span ≥ `min_train_periods`, and a non-empty test span. Both window kinds ship in v1. |
| **D-COMPOSE** | **Compose, do not promote (Q19.2).** The per-window covariance is `factorrisk.stats.estimate_moments` (Phase 20, `factorrisk-stats/1`); the per-window weights are `optimization.solve.solve_min_variance` (Phase 21, `optimization-solve/1`); the OOS summary is `factorportfolio.stats.series_summary` (Phase 19, `factorportfolio-stats/1`). No prior package is edited; each composed method version is folded into the engine identity (**WF-5**, §5), so a bump in any lower layer yields a new, distinguishable engine id. Phase 22's own window-partition + realization method is `walkforward-method/1`. |
| **D-OBJ** | **Objective + constraint are inherited from the recipe; GMV / fully-invested only (Q19.3).** The engine verifies the recipe's `objective == minimum_variance` and `constraint_spec == {"fully_invested": True}` and fails closed otherwise (WF-5) — a future constrained recipe can never be silently walked forward under GMV. No new objective is introduced in v1. |
| **D-REALIZE** | **Weights held constant over each test window (Q19.5); `r_t = Σ_i w_{k,i}·f_{i,t}` per period (Q19.6).** The training-window GMV weights `w_k` are applied unchanged to every period in the test span; each period's OOS return is the weighted sum of the per-period factor returns. The chained series is summarized with the Phase 19 method (whose cumulative uses `∏(1+r_t)−1`). No intra-window drift/compounding of weights. |
| **D-ALIGN** | **Complete-case alignment, deterministic and shared across factors (WF-6).** The evaluated axis is the intersection of `as_of` instants where **every** factor carries a KNOWN return, ascending; a date where any factor is UNDEFINED is excluded — never filled, imputed, or interpolated. Reuses the Phase 20 alignment idiom. A duplicate KNOWN `as_of` within a factor is a corrupt input and raises. |
| **D-SINGULAR** | **A non-positive-definite training covariance is a first-class `UNDEFINED` `SINGULAR_TRAINING_COVARIANCE` window (WF-4)** — the exact Phase 21 `ldl` zero-pivot test, no float tolerance; never a divide-by-zero, pseudo-inverse, dropped/filled window, or regularized matrix. An UNDEFINED window contributes **no** weights and **no** OOS returns but is retained in `windows` with its reason; the evaluation still seals. |
| **D-FLOORS** | **`_MIN_TRAIN_PERIODS = 2`, `MIN_VALID_WINDOWS = 2`, `_MIN_FACTORS = 2`, `N_MAX = 16` (Q19.8).** `min_train_periods` must be ≥ 2 (a covariance needs ≥ 2 observations); a run producing fewer than 2 candidate windows, or fewer than 2 **REALIZED** windows, is a consistency defect and raises — no defensible OOS summary exists (WF-4). The factor count must be in `2..N_MAX` (inherited from the risk model, re-checked fail-closed). |
| **D-EXPOST** | **The output is ex-post, never PIT (WF-3).** A function of ex-post factor return series is itself ex-post. `WalkForwardEvaluation` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` documents only that the *underlying factor portfolios were PIT walks*; it never claims the OOS series is a PIT value. Set unconditionally, so **no new PIT resolution** is introduced. |
| **D-VARIANCE** | **Predicted-vs-realized variance is sealed per window and in aggregate (Q19.9).** Per window: `predicted_variance` = in-sample `wᵀΣw` over the training covariance; `realized_variance` = population variance of that window's OOS test returns (`SINGLE_VALID_PERIOD` when the test span is one period). Aggregate: `realized_variance` = population variance of the whole chained OOS series. This is the non-tautological comparison the phase exists to produce (§5.1 of the proposal). |
| **D-INVARIANTS** | **WF-1..WF-6 are documented both as phase-local invariants here and as a small additive `data-model.md §12` block** mirroring the SD-/XS-/P19-/FR-/PO- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.19.0`** (Phase 21 = v0.18.0, confirmed by git tags). Domain tag `walkforward/1`; engine-version string `walkforward-engine/1`; method string `walkforward-method/1`; record-format string `walkforward-result/1`. The package `__version__` string is unchanged (versioning is by content-addressed ids, not a semver string). Any pre-existing README version-label drift is **not** fixed here. |

### 1.1 Deviations from the proposal (disclosed) & open questions resolved

Recorded for auditability; none changes an identity discipline or weakens an invariant.

1. **★ Windows are derived from the aligned `as_of` axis + `TrainingPolicy` cadence, not
   from a separate `RebalanceSchedule` input (resolves proposal open question #3).** The
   proposal §12 sketched a `schedule: RebalanceSchedule` argument plus an instant→axis
   mapping. The implementation drops that input entirely: the factor-return series' `as_of`
   axis *already is* a rebalance calendar (Phase 19 built the factors on a
   `RebalanceSchedule`), so a second schedule + a fragile instant-placement rule is
   redundant. `TrainingPolicy` gained a `test_periods` field (the rebalance cadence in
   aligned periods) to carry the cadence the schedule would have. **The proposal's
   schedule-pinning intent is preserved:** the inherited `schedule_id` (from the resolved
   `FactorRiskModel`) is still folded into `walk_forward_id` (§5). This removes the
   proposal's only fail-closed "schedule instant cannot be placed on the axis" path — the
   axis *is* the calendar — while keeping identity transitively sensitive to it.
2. **★ `WalkForwardUndefinedReason` is the union of the three window reasons and three
   mapped Phase 19 summary reasons; only `SINGULAR_TRAINING_COVARIANCE` is reachable as a
   window reason.** The proposal §10 listed a closed 3-value window vocabulary
   (`INSUFFICIENT_TRAINING`, `SINGULAR_TRAINING_COVARIANCE`, `EMPTY_TEST_WINDOW`). Because
   Phase 22 defines its own self-contained `StatValue` (rather than importing Phase 19's),
   the reason enum also carries the three summary reasons Phase 19 can produce
   (`NO_VALID_PERIODS`, `SINGLE_VALID_PERIOD`, `ZERO_RETURN_VARIANCE`) so the composed
   summary/variance cells map by their stable string value. Of the three **window** reasons,
   only `SINGULAR_TRAINING_COVARIANCE` is reachable given the axis-derived generator;
   `INSUFFICIENT_TRAINING` and `EMPTY_TEST_WINDOW` are retained as **defensive,
   structurally-unreachable** fail-closed guards in `evaluate.py` (the direct analogue of the
   solve layer's non-positive-`s` guard), and are covered by directly-constructed degenerate
   `WindowSpec`s in the tests.
3. **Per-window `realized_variance` added (minor).** The proposal sealed a per-window
   *predicted* variance and an aggregate realized variance. The implementation additionally
   seals a per-window `realized_variance` (the population variance of that window's OOS test
   returns), so `predicted_vs_realized` returns `(index, predicted_variance,
   realized_variance)` per REALIZED window — a strictly richer, still-deterministic
   comparison. It is folded into `result_hash` like every other computed cell.
4. **Compose is confirmed (resolves open question #1).** The Phase 19/20/21 pure functions
   (`series_summary`, `estimate_moments`, `solve_min_variance`) were cleanly importable as
   window-agnostic pure functions; the fallback self-contained method was not needed. Their
   versions are folded (§5).
5. **Both window kinds ship in v1 (resolves open question #2, per Q19.4).**
6. **The recipe's `constraint_spec` is re-validated (resolves open question #6):** the engine
   asserts it is exactly the v1 GMV `{"fully_invested": True}` and fails closed otherwise.
7. **Pure compute types are `WindowEvaluation` (in `evaluate.py`) and `WindowSpec` (in
   `windows.py`).** `evaluate_window(series, window, *, n, periods_per_year, context)`
   returns a `WindowEvaluation`; the engine copies its blocks into the sealed `WindowResult`.
   The split keeps the pure compute layer free of the record/store vocabulary (the analogue
   of Phase 20's `MomentEstimate` / Phase 21's `MinVarianceSolution`).

---

## 2. Architecture

New package **`src/quantforge/walkforward/`**, mirroring the Phase 20/21 layout. Every
module is pure except `engine.py` (which touches the shared store):

```
WalkForwardEvaluationSpecification { name, optimization_id, training_policy }
        │  (frozen, self-validating; reads no store, no wall clock)
        ▼  WalkForwardEvaluationEngine.evaluate(spec)          [engine.py]
1. resolve PortfolioOptimization by optimization_id            — fail closed (WF-1)
2. verify recipe: id match, status OPTIMAL, objective==minimum_variance,
                  constraint_spec=={"fully_invested":True}     — fail closed (WF-1/WF-5)
3. resolve+verify FactorRiskModel (result_hash pin match);
   check 2 <= n <= N_MAX; resolve each FactorPortfolio;
   inherit one shared risk_free_per_period                     — fail closed (WF-1/WF-6)
4. complete-case align on the common KNOWN as_of axis          — never fill (WF-6)
5. build_windows(M, training_policy)  [windows.py]             — WF-2
   require >= MIN_VALID_WINDOWS candidate windows              — fail closed (WF-4)
6. per window: evaluate_window(...)   [evaluate.py]            — WF-2/WF-4
      Σ_k = estimate_moments(train)        [Phase 20 method]
      w_k = solve_min_variance(Σ_k)        [Phase 21 method]   → SINGULAR → UNDEFINED
      r_t = Σ_i w_{k,i}·f_{i,t}  for t in test span
      predicted_var = wᵀΣw ; realized_var = pop-var(OOS)
   require >= MIN_VALID_WINDOWS REALIZED windows               — fail closed (WF-4)
7. chain OOS returns → series_summary(...) [Phase 19 method]
   aggregate realized variance
8. WalkForwardEvaluation.seal(...) → store.write (write-once)  [result.py]
```

Modules: `errors.py` (`WalkForwardError` → `WalkForwardConfigurationError`,
`WalkForwardConsistencyError`); `version.py` (`WalkForwardEngineVersion`, the three version
constants, `default_decimal_context`); `model.py` (`WindowStatus`, `StatStatus`,
`WalkForwardUndefinedReason`, `StatValue`, `WalkForwardSummary`, `factor_label`); `spec.py`
(`TrainingPolicy`, `WalkForwardEvaluationSpecification`, `WINDOW_EXPANDING`,
`WINDOW_ROLLING`); `windows.py` (`WindowSpec`, `build_windows`); `evaluate.py`
(`WindowEvaluation`, `evaluate_window`); `result.py` (`WindowResult`,
`WalkForwardEvaluation`, `MIN_VALID_WINDOWS`, `BOUNDARY_PIT`,
`WALKFORWARD_RESULT_FORMAT_VERSION`); `identity.py` (`walk_forward_result_hash`,
`walk_forward_id`); `engine.py` (`WalkForwardEvaluationEngine`); `__init__.py`.

**Additive edits to existing source (none altering any existing identity):**
`workspace.py` (one lazy, cached `walk_forward_engine` `@property`, typed `-> object` for
import-cycle avoidance, following the `optimization_engine` template);
`src/quantforge/__init__.py` (top-level re-exports of `WalkForwardEvaluationSpecification`
and `WalkForwardEvaluation`); `tests/test_smoke.py` (one additive export assertion). **No
edit** to `_linalg`, `factorrisk`, `optimization`, `factorportfolio`, or any other
prior-phase module.

---

## 3. Data model

**`TrainingPolicy`** (frozen slots): `window` (`"expanding"|"rolling"`), `min_train_periods`
(int ≥ 2), `test_periods` (int ≥ 1), `rolling_length` (int ≥ `min_train_periods`, present
iff rolling). Self-validating at construction (fail closed); `to_dict`/`from_dict` round-trip
(an expanding policy omits `rolling_length`, so the two kinds hash distinctly).

**`WalkForwardEvaluationSpecification`** (frozen slots): `name`, `optimization_id`,
`training_policy`, `spec_version = "walkforward/1"`. Self-validating (non-empty
`name`/`optimization_id`/`spec_version`; a real `TrainingPolicy`). Reads no store.

**`StatValue`** (frozen slots): the UNDEFINED-preserving cell — `status` (`KNOWN`|`UNDEFINED`)
with a canonical decimal-string `value` XOR a `WalkForwardUndefinedReason`. The walk-forward
analogue of the optimization/factor-risk cell.

**`WindowResult`** (frozen slots): `index`, half-open `[train_start, train_end)` /
`[test_start, test_end)` (with `train_end == test_start`), `status`, `reason`, `weights`
(per-factor GMV cells in factor order; empty when UNDEFINED), `predicted_variance`,
`realized_variance`, `oos_returns` (audit metadata — **not** folded into `result_hash`; the
same numbers as the chained series, folded once).

**`WalkForwardSummary`** (frozen slots): six `StatValue` cells (cumulative return, mean period
return, volatility, annualized Sharpe, mean t-stat, hit rate) + `n_valid_periods` — the Phase
22 mapping of the reused Phase 19 `SeriesSummary`.

**`WalkForwardEvaluation`** (frozen slots, `ResearchRecord`): `walk_forward_engine_version_id`,
the full `walk_forward_spec` dict, `optimization_ref = (optimization_id, result_hash)`,
`boundary_kind`, inherited `schedule_id` + `factor_portfolio_engine_version_id`, `n_factors`,
`factor_labels`, inherited `periods_per_year` + `risk_free_per_period`, `common_periods`,
ordered `windows`, chained `oos_returns`, `summary`, aggregate `realized_variance`, carried
`dataset_version_ids` + `market_dataset_version_ids`, `formula_version`, and the sealed
`result_hash`. Derived properties (never stored): `walk_forward_id`, `research_result_id`
(alias), `optimization_id`, `status` (roll-up), `predicted_vs_realized`, `pin_mismatch`.

---

## 4. Method (per window)

No new numerical formula — three composed pinned methods under one pinned `Decimal` context
(precision 34, `ROUND_HALF_EVEN`):

1. **Re-estimate.** `estimate_moments(train_series, periods_per_year, context)` (Phase 20)
   returns the upper triangle of the `N×N` per-period covariance; `_reconstruct` mirrors it
   into a dense symmetric matrix of decimal strings, re-verifying fail-closed (every cell in
   range, `i ≤ j`, none missing/duplicated, all KNOWN) — never repaired or regularized.
2. **Re-solve.** `solve_min_variance(Σ, context)` (Phase 21) returns a `MinVarianceSolution`.
   A non-`OPTIMAL` status (non-positive-definite `Σ`, exact `ldl` zero-pivot) → UNDEFINED
   `SINGULAR_TRAINING_COVARIANCE` window (WF-4). Otherwise the fully-invested GMV weights.
3. **Realize (WF-2).** For each `t` in the test span, `r_t = Σ_i w_{k,i}·Decimal(series[i][t])`
   under `localcontext`. `predicted_variance` = the solution's in-sample `wᵀΣw`;
   `realized_variance` = population variance of the OOS returns (KNOWN with ≥ 2 test periods,
   else `SINGLE_VALID_PERIOD`).

The chained OOS series across all REALIZED windows is summarized by `series_summary` (Phase
19), whose factor-portfolio `StatValue` cells are mapped into walk-forward cells by their
stable string value (fail-closed on an unexpected reason). The aggregate `realized_variance`
is the population variance of the whole chained series.

---

## 5. Identity and determinism

All ids follow the project §11 discipline: `sha256:`-prefixed, `_SEP = "\x00"` NUL-joined,
canonical JSON (`sort_keys=True, ensure_ascii=False, separators=(",",":")`) for structured
payloads; **no** wall-clock, RNG, `id()`, or iteration-order dependence.

- **`walk_forward_engine_version_id = sha256(code_version, config_hash)`** where
  `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=walkforward-method/1\x00cov=<factorrisk-formula>\x00solve=<optimization-solve>\x00summary=<factorportfolio-formula>")`.
  **Folding the three composed lower-layer method versions** (Phase 20 covariance, Phase 21
  solve, Phase 19 summary) makes the evaluation's identity change if *any* composed method
  changes — the discipline that resolves the §9 TENSION (WF-5).
- **`walk_forward_result_hash = sha256(canonical JSON over the ordered computed-output cells)`**:
  each window block in schedule order (`{block:"window", index, bounds, status, reason?,
  weights, predicted_variance, realized_variance}`), then `{block:"oos", returns}`, then
  `{block:"summary", …}`, then `{block:"realized_variance", value}`. Sensitive to every
  computed value and to window order. Per-window `oos_returns` are **excluded** (audit
  metadata; the same numbers as the chained series, folded once).
- **`walk_forward_id = sha256`**, NUL-joined in order: `walkforward/1`,
  `walk_forward_engine_version_id`, `name`, `spec_version`, the canonical-JSON
  `training_policy`, the inherited `schedule_id`, `optimization_id`, the referenced
  `optimization.result_hash` (transitive pin, WF-1), and `walk_forward_result_hash`.
- **`research_result_id` aliases `walk_forward_id`.** Derived ids are re-emitted by their
  properties, never read from stored state — so `from_dict(to_dict(r))` re-emits identical
  bytes and a tampered stored id is ignored.

**Does NOT fold:** the record-format version (container concern); inherited corpus pins
(surfaced via `pin_mismatch`).

Same recipe + same training policy → same `walk_forward_id` and byte-identical payload on
any machine (verified by the two-independent-workspaces test).

---

## 6. PIT / provenance / storage

Zero new store types. `WalkForwardEvaluation` is a `ResearchRecord` written write-once to the
existing `<root>/research/` sidecar via `ResearchResultStore.write` — idempotent for a
byte-identical re-build; a differing payload under the same id fails closed via the store's
guard. `from_dict` is the fail-closed inverse. It stores **no** copy of any covariance matrix
or corpus — only the transitive `(optimization_id, result_hash)` pointer, the per-window
summaries, the chained OOS series, and the realized summary. `boundary_kind = "pit"` documents
the *input* side only; the output is ex-post and is not a PIT value (WF-3). Corpus pins
(`dataset_version_ids`, `market_dataset_version_ids`) are carried transitively from the risk
model; `pin_mismatch` is `True` iff either set is non-singular — surfaced, never raised.

---

## 7. Failure / UNDEFINED semantics

Established split — **defects raise, genuine data conditions are recorded.**

**Raised** (`WalkForwardConfigurationError` / `WalkForwardConsistencyError`):
- Malformed spec / training policy (empty fields; unknown window kind; `min_train_periods < 2`;
  `test_periods < 1`; rolling without `rolling_length`; `rolling_length < min_train_periods`;
  expanding carrying `rolling_length`; a non-`TrainingPolicy`). *(configuration)*
- A non-`WalkForwardEvaluationSpecification` argument. *(configuration)*
- `optimization_id` absent / not decoding as a `PortfolioOptimization` / id-mismatched; a
  recipe whose `status` is not `OPTIMAL`, objective not `minimum_variance`, or constraint not
  `{"fully_invested": True}`. *(consistency, WF-1/WF-5)*
- The transitively-referenced `FactorRiskModel` (missing / not decoding / id-mismatched /
  `result_hash` drift) or any `FactorPortfolio` (missing / not decoding / id-mismatched); a
  factor count outside `2..N_MAX`; a risk-free-per-period disagreement across factors; a
  duplicate KNOWN `as_of` within a factor. *(consistency, WF-1/WF-6)*
- Fewer than `MIN_VALID_WINDOWS (=2)` candidate windows, or fewer than `MIN_VALID_WINDOWS`
  **REALIZED** windows after evaluation. *(consistency, WF-4)*

**Recorded as first-class `UNDEFINED` (never raised, fabricated, or repaired — WF-4):**
- A window whose training covariance is not positive-definite → `WindowStatus.UNDEFINED`,
  reason `SINGULAR_TRAINING_COVARIANCE` (the **only** reachable window reason). No weights, no
  OOS returns; retained in `windows`; the evaluation still seals.
- Defensive, structurally-unreachable guards in `evaluate.py`: `INSUFFICIENT_TRAINING`
  (train span < 2) and `EMPTY_TEST_WINDOW` (empty test span) — the axis-derived generator
  cannot produce a window that trips these.
- Composed-summary / realized-variance cells: `NO_VALID_PERIODS` / `SINGLE_VALID_PERIOD` /
  `ZERO_RETURN_VARIANCE`, mapped from the Phase 19 summary; a single-period per-window test
  span yields `SINGLE_VALID_PERIOD` realized variance.

**Surfaced, never raised:** `pin_mismatch = True` when the carried corpus pins are non-singular.

---

## 8. Public API

```python
from quantforge import (
    Workspace,
    WalkForwardEvaluationSpecification,
    WalkForwardEvaluation,
)
from quantforge.walkforward.spec import TrainingPolicy

ws = Workspace.open(root)

spec = WalkForwardEvaluationSpecification(
    name="gmv-value-momentum-wf",
    optimization_id=optimization_id,  # a sealed PortfolioOptimization (the recipe)
    training_policy=TrainingPolicy(
        window="expanding",  # or "rolling"
        min_train_periods=24,
        test_periods=1,
        rolling_length=None,  # required iff window == "rolling"
    ),
    # objective / constraint are INHERITED from the referenced optimization (WF-5)
)

evaluation = ws.walk_forward_engine.evaluate(spec)  # sealed, write-once

evaluation.status  # WindowStatus roll-up (>= MIN_VALID_WINDOWS realized?)
evaluation.windows  # per-window: bounds, weights, predicted/realized var, status
evaluation.oos_returns  # chained OOS realized factor-combination return series
evaluation.summary  # realized cumulative / mean / vol / Sharpe / t-stat / hit
evaluation.realized_variance  # aggregate realized OOS variance (StatValue)
evaluation.predicted_vs_realized  # per REALIZED window: (index, predicted, realized)
evaluation.pin_mismatch  # inherited corpus-pin flag
evaluation.research_result_id  # == evaluation.walk_forward_id

again = ws.research_result_store.read_as(
    evaluation.research_result_id, WalkForwardEvaluation.from_dict
)
```

`WalkForwardEvaluationEngine` is reached only through `Workspace.walk_forward_engine` (lazy,
cached, `-> object`). `evaluate(spec) -> WalkForwardEvaluation` is the single entry point. No
`Company` method is added.

---

## 9. New invariants (added additively to `data-model.md §12`)

- **WF-1. Reference verification and transitive pinning.** The evaluation resolves the single
  referenced `PortfolioOptimization`, re-verifies its `research_result_id`, requires
  `status = OPTIMAL`, and resolves the transitively-referenced `FactorRiskModel` (with a
  `result_hash` pin match) and every `FactorPortfolio`; any missing / non-decoding /
  id-mismatched / drifted reference fails closed. The recipe's `result_hash` is folded into
  `walk_forward_id`.
- **WF-2. Strict train-before-test split (no look-ahead).** For each window, `train_end ==
  test_start`; the covariance is estimated using only returns strictly before the cut, and
  the weights are applied only to returns at/after the cut. No test return ever enters an
  estimation window.
- **WF-3. Not a PIT value and not a `BacktestResult`.** Ex-post; not a `Pit*` type; no as-of
  accessor; simulates no fills/cash/positions/costs; a distinct record type.
- **WF-4. Fail-closed window degeneracy, never repaired.** A singular training covariance is
  a recorded UNDEFINED window with its reason — never fabricated, dropped, filled, or
  regularized; fewer than `MIN_VALID_WINDOWS` REALIZED windows fails closed.
- **WF-5. Single methodology source; no fabricated inputs.** The per-window covariance and GMV
  weights are the Phase 20 estimator and Phase 21 solver methods only (versions folded into
  identity); objective/constraint inherited from the recipe. No second estimator, no
  shrinkage/regularization, no expected-return / benchmark input.
- **WF-6. Complete-case alignment is deterministic and shared across factors.** The evaluated
  axis is the intersection of `as_of` dates where every factor is KNOWN, ascending; a date
  where any factor is UNDEFINED is excluded, never filled; window bounds are a pure, total
  function of that axis and the `TrainingPolicy`.

---

## 10. Out of scope (strict)

Constrained optimization / iterative QP; mean-variance / max-Sharpe / any expected-return
objective; new objectives or constraints; risk attribution / budgeting; shrinkage / EWMA /
factor-model / robust covariance; regime-conditioning, transaction costs, turnover, execution;
multiple-testing correction; report-scope extension; any modification to Phase 12/19/20/21
vocabulary, engine, or identity; any `_linalg` change; any new store, database, PIT surface,
data source, UI, or runtime dependency; any PIT-eligible / tradable output.

---

## 11. Quality gates

All green at implementation (zero runtime dependencies):

- `ruff check` — All checks passed.
- `ruff format --check` — all files formatted.
- `mypy src tests` — Success (389 source files).
- `pytest -q tests/walkforward/` — 75 passed.
- `pytest -q` — 1648 passed.
- `pytest -q -p no:randomly` — 1648 passed (order-independent).

---

## 12. Test coverage

New `tests/walkforward/` (offline, synthetic; `builders.py` synthesizes a real sealed
factor → risk-model → optimization chain into a workspace sidecar, giving exact control over
the aligned axis and window degeneracy while exercising the true resolve → verify → align →
partition → evaluate → seal → persist path):

- **`test_spec.py`** — `TrainingPolicy` / `WalkForwardEvaluationSpecification` valid,
  round-trip, and every fail-closed path (unknown window kind, `min_train`/`test_periods`
  floors, bool rejection, rolling-length rules, empty fields, non-policy).
- **`test_windows.py`** — expanding/rolling cuts + bounds, dense ordered indices, truncated
  final test block, rolling `train_start` slides and floors at 0, the WF-2 invariant
  (parametrized `M` 0..8), axis-too-short yields none, negative length raises.
- **`test_evaluate.py`** — PD training realizes OOS; weights fully-invested (sum == 1);
  single vs multi test-period realized variance; determinism; 2-obs training and collinear
  factors → `SINGULAR_TRAINING_COVARIANCE`; the defensive `INSUFFICIENT_TRAINING` /
  `EMPTY_TEST_WINDOW` guards via directly-constructed degenerate windows.
- **`test_identity.py`** — `walk_forward_result_hash` sha256/deterministic/cell- &
  order-sensitive; `walk_forward_id` sha256/deterministic, sensitive to every fold, training
  policy folded as key-order-independent canonical JSON.
- **`test_result.py`** — byte-identical round-trip, `research_result_id` alias, tampered
  stored id ignored, `result_hash` value-sensitivity; roll-ups (status threshold,
  `predicted_vs_realized` omits UNDEFINED windows, `pin_mismatch`).
- **`test_engine.py`** — happy path (all windows REALIZED, `common_periods`, references +
  conventions carried, persisted + readable, idempotent rebuild, `predicted_vs_realized`);
  mixed windows (singular first window still seals); complete-case alignment; determinism
  across two workspaces; fail-closed guards (non-spec, missing id, non-optimization record,
  non-OPTIMAL recipe, too-few-windows, all-singular, risk-free disagreement).
- **`tests/test_smoke.py`** — additive export assertion.
