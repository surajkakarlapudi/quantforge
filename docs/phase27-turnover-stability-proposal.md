# Phase 27 — Walk-Forward Portfolio Turnover & Stability (proposal)

> Status: PROPOSAL. This document is the design put forward for review. The
> normative description of what was actually built is
> `docs/phase27-turnover-stability-locked.md`.

## 1. Thesis

Phase 22 seals, per walk-forward window, the re-estimated global-minimum-variance
(GMV) training weights — `WindowResult.weights`, a per-factor `StatValue` vector in
factor order, KNOWN when the window REALIZED and empty when it was UNDEFINED. Every
downstream consumer to date (Phases 23, 26) has read the walk's *variance* payload;
**no consumer has ever read the weight vectors**. They are the single richest
reserved-but-unconsumed artifact in the research spine.

A weight *path* — the ordered sequence of GMV solutions the walk re-solves window
after window — answers a question none of the existing analytics touch: **how stable
and how implementable is the decision the strategy actually makes over time?** A GMV
recipe can post an attractive out-of-sample Sharpe (Phase 22/23) yet churn its book
violently from window to window, or concentrate into a handful of factors, or lever
up through offsetting long/short positions. Those are first-order obstacles to ever
running the strategy, and they are invisible in a return series. Phase 27 seals them.

## 2. Capability

A **walk-forward turnover & stability analysis** consumes exactly one sealed
`WalkForwardEvaluation` and seals, per REALIZED window, the stability of that window's
GMV weight vector plus its one-way turnover against the immediately-preceding REALIZED
window; and over the walk, the aggregate turnover and concentration profile.

Per REALIZED window (weight vector `w` of length `N`, in factor order):

* `gross_leverage = Σ_i |w_i|` — the gross book (`1` when long-only fully-invested,
  `> 1` once offsetting shorts appear).
* `concentration_hhi = Σ_i w_i²` — the Herfindahl–Hirschman concentration of the book.
* `effective_breadth = 1 / concentration_hhi` — the effective number of positions
  (UNDEFINED, `ZERO_CONCENTRATION`, if `HHI = 0` — defensive; a fully-invested vector
  has `Σ w = 1` so `HHI ≥ 1/N > 0`).
* `max_abs_weight = max_i |w_i|` — the single largest absolute position.
* `turnover_from_prev = ½ Σ_i |w_i − w'_i|` — the one-way turnover against the
  immediately-preceding window's weights `w'`, KNOWN iff that adjacent window is also
  REALIZED, else UNDEFINED (`NO_PRIOR_REALIZED_WINDOW`).

Over the walk:

* Turnover family (the `T` windows whose `turnover_from_prev` is KNOWN):
  `mean_turnover`, `turnover_dispersion` (population), `max_turnover`, `min_turnover`.
  Every cell UNDEFINED (`NO_TRANSITIONS`) when `T = 0`.
* Concentration family (the `W` REALIZED windows): `mean_gross_leverage`,
  `max_gross_leverage`, `mean_concentration_hhi`, `mean_effective_breadth`. Every cell
  UNDEFINED (`NO_REALIZED_WINDOWS`) when `W = 0` (defensive).

`stability_status` is `STABLE` iff `T ≥ MIN_STABILITY_TRANSITIONS = 2`, else
`UNDEFINED` (`INSUFFICIENT_TRANSITIONS`) — a single transition carries no
cross-transition structure, exactly as Phase 26 requires two calibratable windows. The
per-window cells and the turnover aggregates still seal below the floor.

## 3. Why now

* **First consumer of `WindowResult.weights`.** It converts a reserved payload into a
  sealed research artifact — the batch's selection criterion (a first consumer of an
  unused sealed artifact), the same role Phase 26 played for the variance payload.
* **A distinct scientific dimension.** Turnover / stability is orthogonal to the
  return-level (Phase 22/23) and risk-forecast (Phase 26) questions. It is the
  implementability lens, not another performance statistic.
* **Uses only existing primitives.** Exact `Decimal`, `abs`, and `Decimal.sqrt` (for
  the population dispersion) — the transcendental Phases 19/20/22/26 already use. No
  new `_stats`/`_linalg` surface, no RNG, no float, no new store, no new dependency.

## 4. Alternatives considered / rejected

* **Cross-sectional exposure analytics (per-factor average weight, tilts).** Rejected:
  near-tautological restatement of the GMV solution the walk already seals — the
  "exposure-level" analytics Phase 22 §7 H explicitly warned against. Phase 27 is
  deliberately **temporal** (turnover, path dispersion), the implementability angle a
  weight *level* cannot express.
* **Transaction-cost / net-of-cost return series.** Rejected: fabricating a cost model
  (bps per unit turnover) would invent a forward-looking input the platform does not
  own, and would produce a return-series artifact competing with Phase 22. Turnover is
  the honest cost-free precursor: a cost model, if ever added, consumes it.
* **Turnover between *all* consecutive windows (imputing across UNDEFINED gaps).**
  Rejected: violates fail-closed. A window with no realized weights has no book to
  trade from; a turnover across it would be fabricated. Such transitions are omitted
  and the count of realized-adjacent pairs (`n_transitions`) is sealed honestly.
* **Two-way turnover / netting conventions.** Rejected as the primary metric: one-way
  turnover `½ Σ|Δw|` is the standard, convention-free definition; a two-way variant is
  a trivial `×2` a reader can derive, so it is not sealed separately.

## 5. Data flow

```
WalkForwardStabilitySpecification(name, source_walk_forward_id)
   │  ws.stability_engine.analyze(spec)
   ▼
WalkForwardStabilityEngine
   1. resolve  source_walk_forward_id  via store.read_as(id, WalkForwardEvaluation.from_dict)
   2. verify   research_result_id == request  (fail closed → StabilityConsistencyError)
   3. classify each source window → REALIZED (parse KNOWN weight vector to Decimal)
              or UNDEFINED (first-class ExcludedWindow, WINDOW_UNDEFINED)
   4. analyze  the ordered windows (stability.compute.analyze_stability) under the
              pinned Decimal context
   5. seal     WalkForwardStability (result_hash folds the answer; id folds the source
              result_hash → transitive pin) and persist write-once to the same sidecar
   ▼
WalkForwardStability  (ResearchRecord; ex-post, not Pit*)
```

## 6. Boundaries

Strictly above Phase 22: a pure consumer. No new data resolution, no `as_of`, no PIT
surface, no new store, no new numerical primitive, no runtime dependency. It reuses the
workspace's shared Phase 8 research sidecar — the same store the walk-forward engine
sealed to.

## 7. Identity

`stability/1` domain tag. `walk_forward_stability_result_hash = sha256(` canonical JSON
over the ordered output cells: coverage descriptor → per-window cells (source order) →
excluded cells → summary `)`. `walk_forward_stability_id = sha256(` domain,
`stability_engine_version_id`, `name`, `spec_version`, `source_walk_forward_id`,
`source_result_hash`, `MIN_STABILITY_TRANSITIONS`, `result_hash` `)`. Folding the
source walk's `result_hash` makes the id **transitively** sensitive to any change in
the walk or anything beneath it. `research_result_id` aliases
`walk_forward_stability_id`. The `stability_engine_version_id = sha256(code_version,
config_hash)` with `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=
stability-method/1")`.

## 8. Persistence / determinism / PIT

* **Persistence:** write-once to the shared sidecar, byte-identical idempotent re-build,
  `FactorConsistencyError` on a conflicting payload under the same id. No new store.
* **Determinism:** all arithmetic under an explicit `Context(prec=34,
  ROUND_HALF_EVEN)`; `abs`/comparison/`Decimal.sqrt` only; no float, RNG, wall-clock,
  `id()`, or iteration-order dependence. Same spec + same sidecar → byte-identical
  record on any machine.
* **PIT:** the output is ex-post. `WalkForwardStability` is **not** a `Pit*` type, has
  **no** as-of accessor, is **not** a `BacktestResult`. `boundary_kind = "pit"` is
  carried unchanged from the source and documents only the input side.

## 9. Numerical method

Exact `Decimal` throughout. `gross_leverage`, `concentration_hhi`, `max_abs_weight`,
and `turnover_from_prev` are exact finite sums / max of parsed weight strings.
`effective_breadth = 1/HHI` and the aggregate means are exact `Decimal` divisions.
`turnover_dispersion` is the population standard deviation via `Decimal.sqrt` (the exact,
correctly-rounded method used platform-wide). Weights are parsed **once** from the
source's canonical decimal strings and never re-solved (WS-4).

## 10. Invariant analysis

Phase 27 adds invariants **WS-1 … WS-6** (data-model §12), all additive — they weaken
no existing invariant:

* **WS-1 (reference contract, fail closed).** Exactly one `WalkForwardEvaluation`,
  resolved + id-verified + decoded, its `result_hash` folded (transitive pin). Missing
  / non-`WalkForwardEvaluation` / id-mismatch → `StabilityConsistencyError`.
* **WS-2 (coverage completeness).** Every source window is classified into exactly one
  of {per-window cell (REALIZED), excluded (UNDEFINED)}; `n_realized + n_excluded =
  n_windows`; `n_transitions` counted separately and sealed.
* **WS-3 (undefined preservation).** UNDEFINED source windows are excluded
  (`WINDOW_UNDEFINED`), never imputed; `turnover_from_prev` is UNDEFINED
  (`NO_PRIOR_REALIZED_WINDOW`) with no adjacent REALIZED predecessor; turnover
  aggregates are UNDEFINED (`NO_TRANSITIONS`) when `T = 0`; `effective_breadth` is
  UNDEFINED (`ZERO_CONCENTRATION`) when `HHI = 0`; `stability_status` is UNDEFINED
  (`INSUFFICIENT_TRANSITIONS`) below the floor. Never a divide-by-zero.
* **WS-4 (verbatim consumption).** Weights are parsed once from the sealed source and
  never re-solved / recomputed. A REALIZED window whose weight vector is malformed
  (any non-KNOWN cell, or length ≠ `n_factors`) is a corrupt source →
  `StabilityConsistencyError`.
* **WS-5 (determinism / exact Decimal).** As §8.
* **WS-6 (ex-post, not PIT).** As §8.

## 11. Package / public API

New package `src/quantforge/stability/`: `version.py`, `errors.py`, `model.py`,
`spec.py`, `compute.py`, `identity.py`, `result.py`, `engine.py` — the exact module
shape of `quantforge/calibration/`. Public re-exports from `quantforge/__init__.py`:
`WalkForwardStabilitySpecification`, `WalkForwardStability`. Additive
`Workspace.stability_engine` lazy property. No existing identity changes.

## 12. Tests

Normal (turnover + concentration over a hand-computed 3-window walk); UNDEFINED gap
(`[R, U, R]` → `NO_TRANSITIONS`, status UNDEFINED, concentration KNOWN); single
transition below floor (status UNDEFINED, aggregates KNOWN); malformed-weight consistency
error; identity sensitivity (source change flips the id); transitive pinning; byte-
identical `from_dict(to_dict(r))`; deterministic repeated execution + write-once
idempotency; public exports; Workspace wiring; exact-Decimal boundary values; ex-post
(no `Pit*`, no as-of); upstream-reference verification (missing / wrong-type / id
mismatch).

## 13. Load-bearing decisions

* **Temporal, not cross-sectional.** Turnover / path stability, never exposure levels.
* **Single window family with an UNDEFINED-preserving `turnover_from_prev` cell** (not a
  separate transition family), mirroring Phase 26's single calibratable-window family —
  gaps degrade a per-window cell to UNDEFINED, they never fabricate a trade.
* **`MIN_STABILITY_TRANSITIONS = 2`**, folded into the id — parity with Phase 26's
  `MIN_CALIBRATABLE_WINDOWS = 2`; the status reflects the *turnover* evidence, while
  per-window concentration always seals.
* **Weights verbatim.** Never re-solved; a malformed REALIZED vector fails closed.
