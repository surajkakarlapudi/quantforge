# Phase 27 — Walk-Forward Portfolio Turnover & Stability (LOCKED)

> **Status:** Locked normative specification. The Phase 27 proposal was **implemented as
> recommended** — the single capability of
> [phase27-turnover-stability-proposal.md](phase27-turnover-stability-proposal.md):
> consume exactly one sealed `WalkForwardEvaluation`, treat its REALIZED windows as the
> family, and per window seal the GMV weight vector's stability (gross leverage,
> concentration, effective breadth, max-abs weight) plus its one-way turnover against the
> immediately-preceding REALIZED window, and over the walk seal the aggregate turnover and
> concentration profile — answering how *stable and implementable* the decision the
> strategy actually makes over time is. This document reflects the **actual
> implementation** and is the source of truth; it supersedes the proposal. Every ★-marked
> decision in the proposal is resolved here.
>
> **One-line thesis:** Phase 27 adds a deterministic, content-addressed **walk-forward
> turnover & stability** layer — the platform's first *implementability* capability and
> the first consumer of Phase 22's reserved-but-unconsumed per-window `weights` payload
> (the GMV training-weight vectors). Given a declarative
> `WalkForwardStabilitySpecification` naming exactly one sealed `WalkForwardEvaluation`
> id, `WalkForwardStabilityEngine.analyze(...)` resolves the one walk from the shared
> Phase 8 research sidecar, re-verifies it (present, a `WalkForwardEvaluation`, id
> matches), classifies each window into the REALIZED family (each carrying a KNOWN weight
> vector parsed once to `Decimal`) or a first-class exclusion (every UNDEFINED window
> recorded, never imputed), computes per REALIZED window `gross_leverage = Σ|w|`,
> `concentration_hhi = Σw²`, `effective_breadth = 1/HHI`, `max_abs_weight = max|w|`, and
> `turnover_from_prev = ½Σ|Δw|`, and over the family the aggregate turnover
> (mean/dispersion/max/min) and concentration (mean gross leverage, max gross leverage,
> mean HHI, mean effective breadth) statistics — all under one pinned `Decimal` context —
> and seals a `WalkForwardStability` `ResearchRecord` write-once to the existing sidecar.
> It introduces **no** new numerical primitive (`Decimal.sqrt` is the only transcendental,
> already used by Phases 19/20/22/26), **no** `_linalg`/`_stats` change, **no** RNG,
> **no** floating point, **no** iterative solver, **no** new store, and **no** new PIT
> surface, and modifies no prior phase's vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **Walk-forward turnover & stability over the REALIZED-window family of one walk.** The family is exactly the source `WalkForwardEvaluation`'s REALIZED windows — each carrying its KNOWN GMV weight vector — in sealed source order. Per REALIZED window seal `gross_leverage`, `concentration_hhi`, `effective_breadth`, `max_abs_weight`, and `turnover_from_prev`; over the family seal `mean_turnover` / `turnover_dispersion` / `max_turnover` / `min_turnover`, `mean_gross_leverage` / `max_gross_leverage` / `mean_concentration_hhi` / `mean_effective_breadth`, and `stability_status`; seal the coverage (`n_windows`, `n_realized`, `n_excluded`, `n_transitions`). **No** cross-walk family (one source only); **no** transaction-cost model or net-of-cost return series (§4); **no** cross-sectional exposure analytics (§4). It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 22.** It resolves exactly **one** already-sealed `WalkForwardEvaluation` from the shared sidecar by id, reads each window's sealed `status` / `weights` (never re-derives them), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of the per-window `weights` payload the Phase 22 architecture reserved but no prior consumer (Phase 23, 26) ever read. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` weight-path metrics and aggregates, one `Decimal.sqrt` for the dispersion.** Per REALIZED window under the pinned context (weight vector `w` of length `N`): `gross_leverage = Σ|w_i|`, `concentration_hhi = Σ w_i²`, `effective_breadth = 1/concentration_hhi`, `max_abs_weight = max|w_i|`, and `turnover_from_prev = ½ Σ|w_i − w'_i|` against the immediately-preceding REALIZED window `w'`. Over the `T`-transition family: `mean_turnover = (Σ turnover)/T`; population `turnover_dispersion = √(Σ(turnover − mean)²/T)`; `max`/`min_turnover`. Over the `W`-REALIZED family: `mean_gross_leverage`, `max_gross_leverage`, `mean_concentration_hhi`, `mean_effective_breadth`. One-way turnover `½Σ|Δw|` is the standard convention-free definition (a two-way variant is a trivial `×2`). |
| **D-STATUS** | **`stability_status` defensible only at the floor.** `STABLE` iff `T ≥ MIN_STABILITY_TRANSITIONS`, else `UNDEFINED` with `INSUFFICIENT_TRANSITIONS`; the per-window cells and the turnover aggregates still seal either way. A walk with no realized-adjacent transitions (`T = 0`) seals every turnover aggregate as a first-class UNDEFINED (`NO_TRANSITIONS`) — never a divide-by-zero, never a fabricated turnover. |
| **D-EXCLUDE** | **UNDEFINED windows are excluded, never imputed.** A source window that is not REALIZED is removed from the concentration family and recorded as a first-class `ExcludedWindow` carrying `WINDOW_UNDEFINED` — never coerced to a metric, never imputed, never silently dropped; `n_realized + n_excluded = n_windows`. An UNDEFINED window also enters the analyzer as a non-realized `SourceWindow`, so it *breaks the weight path*: the next REALIZED window has no adjacent book and its `turnover_from_prev` is UNDEFINED (`NO_PRIOR_REALIZED_WINDOW`), never a turnover fabricated across the gap. |
| **D-CONSUME** | **Sealed weights are consumed verbatim.** The engine parses each REALIZED window's sealed weight-vector decimal strings once and never re-solves a GMV, re-derives a covariance, or recomputes a weight. `str(+Decimal(source))` is idempotent for an already-canonical source string, so a carried-through value is byte-for-byte the source value. A REALIZED window whose weight vector is malformed (length ≠ `n_factors`, or any non-KNOWN cell) is a corrupt source and fails closed. |
| **D-EXPOST** | **The output is ex-post, never PIT.** A stability analysis over an already-ex-post walk is itself ex-post. `WalkForwardStability` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source walk and documents only that the *underlying factor portfolios were PIT walks*; it never claims the stability output is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order.** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); `abs`, comparison, exact sums / divisions, and `Decimal.sqrt` (for the population dispersion) are the only operations — `Decimal.sqrt` the only transcendental (the exact method Phases 19/20/22/26 already use); canonicalization is `str(+value)`. No RNG, no iteration-to-convergence, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context **and** the method version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying.** `walk_forward_stability_id` folds the engine version, the request (name, spec version), the source walk's `research_result_id` **and** its `result_hash` (the transitive pin), the `MIN_STABILITY_TRANSITIONS` floor, and the `result_hash` over the computed answer. `research_result_id` aliases `walk_forward_stability_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `stability/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `WalkForwardStability` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-FLOOR** | **`MIN_STABILITY_TRANSITIONS = 2`**, a module constant in `result.py` (not a spec field, mirroring walk-forward's `MIN_VALID_WINDOWS` and calibration's `MIN_CALIBRATABLE_WINDOWS`), folded into `walk_forward_stability_id` so a change to it is a distinguishable record. A single transition carries no cross-transition structure. |
| **D-INVARIANTS** | **WS-1..WS-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC-/RC- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.24.0`** (Phase 26 = v0.23.0). Domain tag `stability/1`; engine-version string `stability-engine/1`; method string `stability-method/1`; spec-version string `stability/1`; record-format string `stability-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **The record carries a `method_version` field.** The proposal (§7) did not enumerate a
  stored `method_version` on the record (the calibration template omits it). The
  implementation stores `method_version` (default `STABILITY_METHOD_VERSION`) as a
  first-class record field, round-tripped through `to_dict` / `from_dict`. It is **not**
  folded into `walk_forward_stability_id` — the method version already reaches the id
  through `stability_engine_version_id` (whose `config_hash` folds it), so folding it
  twice would be redundant; the stored field is an auditable record of the method that
  produced the answer. `from_dict` requires it (fail closed on absence), so a record's
  stored bytes disclose their producing method without changing identity discipline.
- **`mean_effective_breadth` degrades to UNDEFINED (`ZERO_CONCENTRATION`) if *any*
  REALIZED window has `HHI = 0`.** The proposal specified the per-window
  `effective_breadth` cell as UNDEFINED on `HHI = 0` (defensive, structurally
  unreachable) but did not spell out the aggregate's behaviour. The implementation makes
  the *aggregate* `mean_effective_breadth` UNDEFINED (`ZERO_CONCENTRATION`) whenever any
  contributing window's breadth was UNDEFINED, so a defined mean is never silently
  computed over a subset that dropped a window (fail-closed, WS-3). The other three
  concentration aggregates (`mean_gross_leverage`, `max_gross_leverage`,
  `mean_concentration_hhi`) are always defined for `W ≥ 1` (they need no reciprocal).

Resolved ★ decisions of note: capability = walk-forward turnover & stability of one walk;
source is exactly one `WalkForwardEvaluation`, consumed by id; output
`WalkForwardStability`; package `stability`, domain tag `stability/1`; public names
`WalkForwardStabilitySpecification` / `WalkForwardStability`; per-window weight-vector
stability + one-way turnover + aggregate turnover / concentration; exact-`Decimal`, no new
primitive; ex-post, not a `Pit*`, boundary carried; exclude-never-impute UNDEFINED
windows, `MIN_STABILITY_TRANSITIONS = 2`; identity fold as in §5; v0.24.0; no
`_linalg`/`_stats` change; a sibling package, no prior-phase edit; shared write-once
`ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/stability/`** (mirrors the P20/P22/P23/P24/P25/P26 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `StabilityError` → `StabilityConfigurationError`, `StabilityConsistencyError`. |
| `version.py` | `WalkForwardStabilityEngineVersion` (folds the pinned decimal context + `stability-method/1` into `config_hash`; **no** normal-primitive version — none is reused); constants `STABILITY_SPEC_VERSION` / `STABILITY_ENGINE_VERSION` / `STABILITY_METHOD_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `StabilityStatus` (`stable`, `undefined`), `StabilityExcludedReason` (`window_undefined`), `StabilityUndefinedReason` (`no_prior_realized_window`, `no_transitions`, `no_realized_windows`, `insufficient_transitions`, `zero_concentration`), `StatStatus`, and the UNDEFINED-preserving `StabilityStat` cell (`known` / `undefined` / `to_dict` / `from_dict`). |
| `spec.py` | `WalkForwardStabilitySpecification` (declarative request; fail-closed validation; `name`, `source_walk_forward_id`, `spec_version = "stability/1"`). |
| `compute.py` | The pure exact-`Decimal` procedures: `analyze_stability(windows, *, min_transitions, context) → StabilityComputation`; `SourceWindow`, `WindowStabilityMetrics`, `StabilitySummaryComputation`; per-window metrics and the family aggregates (`_summarize`, `_turnover_aggregates`, `_concentration_aggregates`). |
| `result.py` | `WalkForwardStability` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `stability_status` accessor), `WindowStabilityCell`, `ExcludedWindow`, `StabilitySummary`, `StabilityCoverage`; `MIN_STABILITY_TRANSITIONS = 2`, `STABILITY_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `walk_forward_stability_result_hash`, `walk_forward_stability_id`; domain tag `stability/1`. |
| `engine.py` | `WalkForwardStabilityEngine.analyze(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `stability_engine` `@property` (+ private `_stability_engine`
   cache slot), following the `risk_calibration_engine` template (typed `-> object`,
   deferred import of `WalkForwardStabilityEngine` to avoid the module-load cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of `WalkForwardStabilitySpecification`
   and `WalkForwardStability`, added to the sorted `__all__`.

**No edit to** `_linalg`, `_stats`, `walkforward`, `calibration`, `comparison`,
`multiplicity`, `campaign`, `optimization`, `factorrisk`, `factorportfolio`, `analytics`,
`backtest`, or any other prior-phase identity/vocabulary. Phase 27 reuses **no**
standard-normal primitive (it consumes already-sealed weights), so `_stats/normal.py` is
untouched.

---

## 3. Data flow

```
WalkForwardStabilitySpecification { name, source_walk_forward_id, spec_version }
        │
        ▼  WalkForwardStabilityEngine.analyze(spec)
type-check spec is a WalkForwardStabilitySpecification                       — StabilityConfigurationError
        │
        ▼
resolve the ONE source walk-forward by id                                   — fail closed (WS-1)
   store.read_as(id, WalkForwardEvaluation.from_dict)
   present? decodes as a WalkForwardEvaluation? research_result_id == id?    — else StabilityConsistencyError
        │
        ▼
classify each window in sealed source order                                 — WS-2/WS-3/WS-4
   REALIZED → parse the KNOWN weight vector (len == n_factors, all KNOWN)    — else StabilityConsistencyError
              → REALIZED SourceWindow
   UNDEFINED → ExcludedWindow(WINDOW_UNDEFINED) AND non-realized SourceWindow (breaks the path)
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   analyze_stability(source_windows, min_transitions=MIN_STABILITY_TRANSITIONS, context)  — WS-3/WS-5
     per REALIZED window: gross_leverage = Σ|w|; concentration_hhi = Σw²; effective_breadth = 1/HHI;
                          max_abs_weight = max|w|; turnover_from_prev = ½Σ|Δw| (UNDEFINED if no prior)
     turnover family (T):  mean; population dispersion = √(Σ(t−mean)²/T); max; min  (UNDEFINED NO_TRANSITIONS if T=0)
     concentration family (W): mean_gross_leverage; max_gross_leverage; mean_hhi; mean_effective_breadth
     stability_status = STABLE iff T ≥ floor, else UNDEFINED(INSUFFICIENT_TRANSITIONS)
        │
        ▼
coverage = { n_windows, n_realized = W, n_excluded, n_transitions = T }      — WS-2
        │
        ▼
WalkForwardStability.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — WS-1/WS-6
        │
        ▼
ResearchResultStore.write(stability)   (write-once, idempotent)             — D-STORE
        │
        ▼
store.read_as(id, WalkForwardStability.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    WalkForwardStabilitySpecification,
    WalkForwardStability,
)

ws = Workspace.open(root)

spec = WalkForwardStabilitySpecification(
    name="gmv-walk:turnover-stability",
    source_walk_forward_id=walk_forward_id,  # exactly one sealed WalkForwardEvaluation id
)

stability = ws.stability_engine.analyze(spec)  # sealed, write-once

stability.stability_status  # STABLE / UNDEFINED (roll-up)
stability.coverage  # n_windows, n_realized, n_excluded, n_transitions
stability.windows  # tuple[WindowStabilityCell]: per-REALIZED-window metrics in source order
stability.excluded  # tuple[ExcludedWindow]: (index, reason) for UNDEFINED windows
stability.summary  # StabilitySummary: turnover + concentration aggregates + status
stability.source_walk_forward_id  # the pinned source walk id
stability.source_result_hash  # the transitive pin
stability.research_result_id  # == stability.walk_forward_stability_id

again = ws.research_result_store.read_as(
    stability.research_result_id, WalkForwardStability.from_dict
)
```

`WalkForwardStabilityEngine` is reached only through `Workspace.stability_engine`
(lazy, cached, `-> object`). `analyze(spec) -> WalkForwardStability` is the single entry
point.

`WalkForwardStabilitySpecification` (frozen slots): `name`, `source_walk_forward_id`,
`spec_version = "stability/1"`. Construction-time validation (fail closed): non-empty
`name` / `spec_version` / `source_walk_forward_id`. There is **no** per-request numerical
parameter — the transitions floor is the platform constant `MIN_STABILITY_TRANSITIONS`
and the metric set is the single approved methodology.

Each `WindowStabilityCell` carries `gross_leverage` / `concentration_hhi` /
`max_abs_weight` (canonical decimal strings), the UNDEFINED-preserving
`effective_breadth` and `turnover_from_prev` cells, and the source `index`. Each
`StabilitySummary` carries eight UNDEFINED-preserving `StabilityStat` cells
(`mean_turnover`, `turnover_dispersion`, `max_turnover`, `min_turnover`,
`mean_gross_leverage`, `max_gross_leverage`, `mean_concentration_hhi`,
`mean_effective_breadth`), the roll-up `stability_status`, and an optional
`status_reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `stability_engine_version_id = sha256(code_version "stability-engine/1", config_hash)`
  where `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=stability-method/1")`.
  Folding the method version makes the stability record's identity change if the
  REALIZED-window selection, the per-window metrics, the one-way turnover, or any
  aggregate changes. **No** normal-primitive version is folded — none is reused.
- `walk_forward_stability_result_hash = sha256(canonical JSON over the ordered
  computed-output cells: the coverage descriptor
  `{block:"coverage_descriptor", n_windows, n_realized, n_excluded, n_transitions}`, then
  each REALIZED window `{block:"window", index, gross_leverage, concentration_hhi,
  max_abs_weight, turnover_from_prev}` in source order, then each
  `{block:"excluded", index, reason}`, then `{block:"summary", ...}`)`. The derivable
  per-window `effective_breadth` is omitted (`concentration_hhi` folds it). Sensitive to
  every computed metric and aggregate.
- `walk_forward_stability_id = sha256`, NUL-joined, in order: `stability/1`,
  `stability_engine_version_id`, `name`, `spec_version`, `source_walk_forward_id`,
  `source_result_hash` (the transitive pin, WS-1), `str(MIN_STABILITY_TRANSITIONS)`, and
  `walk_forward_stability_result_hash`.
- `research_result_id` aliases `walk_forward_stability_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version and the
  stored `method_version` are **not** folded (a container / audit concern; the method
  reaches the id through the engine version). Coverage is **not** folded beyond the
  descriptor (it is a pure function of the sealed window / excluded lists).

---

## 6. Determinism / Decimal rules

- All stability arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the per-window `Σ|w|`, `Σw²`, `1/HHI`, `max|w|`, and one-way
  `½Σ|Δw|`, the aggregate means, the `max`/`min`, and the population dispersion (a
  `Decimal.sqrt` of a mean-of-squared-deviations). **No float anywhere**, no RNG, no
  wall-clock, no `id()`, no iteration-to-convergence, no data-dependent iteration order.
- Values are canonicalized as `str(+value)` inside the pinned context; each per-window
  metric is computed once and reused for every aggregate, so a cell's value and the
  aggregates over it can never disagree.
- Same source walk + same request → same `walk_forward_stability_id` and byte-identical
  payload on any machine. A repeated `analyze` is a byte-identical no-op (store
  idempotence). Two engines over the same immutable sidecar agree. Because Phase 27 folds
  the source walk's `result_hash`, any upstream change changes this record's id while a
  byte-identical recompute reproduces identical bytes (the Phase 22 audit standard, one
  layer up).

---

## 7. Invariants (WS-1..WS-6)

Additive to `data-model.md §12`; these do not weaken invariants 1–30.

- **WS-1 — Reference verification and transitive pinning.** The single
  `source_walk_forward_id` is resolved from the shared sidecar via
  `store.read_as(id, WalkForwardEvaluation.from_dict)`, re-verified
  (`research_result_id == id`, and that it decodes as a `WalkForwardEvaluation`), and its
  `result_hash` folded into `walk_forward_stability_id`; through the source walk's own id
  this pins the optimization / risk-model / factor chain beneath it (WF-1). Any missing,
  non-decoding, or id-mismatched reference fails closed with
  `StabilityConsistencyError`; the source is never copied, only pinned. *(The WF-1 /
  CE-1 / MC-1 / RC-1 discipline, one layer up.)*
- **WS-2 — The analyzed object is an explicit, sealed family of windows.** Every source
  window is classified into exactly one of {a per-window stability cell (REALIZED), an
  `ExcludedWindow` (UNDEFINED)}, in source order; the coverage (`n_windows`,
  `n_realized`, `n_excluded` with `n_realized + n_excluded = n_windows`, and the
  separately-counted `n_transitions`) is sealed so the effective sample each aggregate
  used is auditable and never inferred. One source only (no cross-walk family in
  v0.24.0).
- **WS-3 — UNDEFINED windows are excluded and gaps are never imputed.** A window the
  source sealed UNDEFINED is removed from the concentration family and recorded as a
  first-class `ExcludedWindow` (`WINDOW_UNDEFINED`) — never coerced to a metric, never
  imputed, never silently dropped — *and* it breaks the weight path so the next REALIZED
  window's `turnover_from_prev` is UNDEFINED (`NO_PRIOR_REALIZED_WINDOW`), never a
  turnover fabricated across the gap. A walk with no realized-adjacent transitions
  (`T = 0`) seals every turnover aggregate UNDEFINED (`NO_TRANSITIONS`); a family below
  the floor seals `stability_status = UNDEFINED (INSUFFICIENT_TRANSITIONS)`; a defensive
  `HHI = 0` seals `effective_breadth` UNDEFINED (`ZERO_CONCENTRATION`), and any such
  window makes `mean_effective_breadth` UNDEFINED. Never a divide-by-zero. *(The WF-4 /
  SC-4 / MC-3 / RC-3 posture, adapted to windows.)*
- **WS-4 — Sealed weights are consumed verbatim, never recomputed.** Each REALIZED
  window's already-sealed GMV weight vector is read as decimal strings and parsed once;
  the engine never re-solves a GMV, re-derives a covariance, or recomputes a weight;
  `str(+Decimal(source))` is idempotent for an already-canonical source string, so a
  carried-through value is byte-for-byte the source value. A REALIZED window whose weight
  vector is malformed (length ≠ `n_factors`, or any non-KNOWN cell) is a corrupt source
  and raises `StabilityConsistencyError`, never coerced. *(The RC-4 / MC-5 posture of
  operating over already-sealed strings, one layer up.)*
- **WS-5 — Single deterministic methodology.** One exact-`Decimal` method per family —
  the per-window gross leverage / concentration / effective breadth / max-abs weight /
  one-way turnover, the turnover mean / population dispersion / max / min, and the
  concentration mean gross leverage / max gross leverage / mean HHI / mean effective
  breadth — all under one pinned decimal context (prec 34, `ROUND_HALF_EVEN`) folded into
  the engine identity, with `Decimal.sqrt` the only transcendental. `stability_status` is
  `STABLE` iff the family meets the platform floor `MIN_STABILITY_TRANSITIONS` (folded
  into the id), else UNDEFINED (`INSUFFICIENT_TRANSITIONS`); the per-window cells and the
  aggregates still seal. No RNG, no float, no data-dependent iteration, no
  `_linalg`/`_stats` change, no new primitive. *(The WF-5 / MC-5 / RC-5 discipline,
  reusing exact `Decimal` arithmetic.)*
- **WS-6 — A stability analysis is not a PIT value and not a `BacktestResult`.** A
  stability analysis over an already-ex-post walk is itself ex-post:
  `WalkForwardStability` is **not** a `Pit*` type, exposes no as-of accessor, is a
  distinct record type, simulates no fills, and opens no new corpus / availability
  surface. `boundary_kind = "pit"` — carried unchanged from the source walk — documents
  only that the *underlying factor portfolios* were PIT walks. *(The WF-3 / SC-6 /
  MC-6 / RC-6 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `StabilityConfigurationError`: a non-`WalkForwardStabilitySpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_walk_forward_id`). `StabilityConsistencyError` (WS-1/WS-4): the
`source_walk_forward_id` absent from the sidecar; a payload that does not decode as a
`WalkForwardEvaluation`; a resolved-id disagreement; a REALIZED window whose weight vector
is malformed (length ≠ `n_factors`, or any non-KNOWN cell).

**Recorded as first-class UNDEFINED** (WS-3, never raised): each UNDEFINED window is
excluded and recorded as an `ExcludedWindow` with `WINDOW_UNDEFINED`; a window with no
realized-adjacent predecessor seals `turnover_from_prev` UNDEFINED
(`NO_PRIOR_REALIZED_WINDOW`); a walk with `T = 0` seals every turnover aggregate UNDEFINED
(`NO_TRANSITIONS`); a family below the floor seals `stability_status = UNDEFINED
(INSUFFICIENT_TRANSITIONS)`; a defensive `HHI = 0` seals `effective_breadth` /
`mean_effective_breadth` UNDEFINED (`ZERO_CONCENTRATION`); a walk with no REALIZED windows
seals every concentration aggregate UNDEFINED (`NO_REALIZED_WINDOWS`).

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload
under the same stability id raises `FactorConsistencyError` (the existing write-once
guard).

---

## 9. Testing

`tests/stability/` (offline, synthetic). Because the engine reads **only** the source
`WalkForwardEvaluation` via `store.read_as`, the builders (`tests/stability/builders.py`)
construct synthetic `WalkForwardEvaluation` records directly — sealing hand-chosen
per-window weight vectors (KNOWN decimal strings or UNDEFINED windows) via
`WalkForwardEvaluation.seal` and writing them to the store — rather than running the full
factor → optimization → walk-forward chain. Per-window helpers cover every classification
branch (`realized_window`, `undefined_window`, `wrong_length_window`,
`non_known_weight_window`).

The canonical fixture is three REALIZED windows with weights `[0.5, 0.5]`, `[0.5, −0.5]`,
`[−0.5, 0.5]`: per-window `gross_leverage = "1.0"`, `concentration_hhi = "0.50"`,
`max_abs_weight = "0.5"`, `effective_breadth = "2"`; turnovers `"0.5"` (W1) and `"1.0"`
(W2); aggregates `mean_turnover = "0.75"`, `turnover_dispersion = "0.25"`,
`max_turnover = "1.0"`, `min_turnover = "0.5"`, `mean_gross_leverage = "1.0"`,
`max_gross_leverage = "1.0"`, `mean_concentration_hhi = "0.50"`,
`mean_effective_breadth = "2"`; status STABLE; coverage `{3, 3, 0, 2}`.

Suites (**48 tests** across the package):
- `test_spec` (4) — the default spec version, the canonical `to_dict`, fail-closed
  rejection of empty fields, frozenness.
- `test_model` (7) — the KNOWN/UNDEFINED `StabilityStat` construction guards, `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells.
- `test_compute` (6) — the pure procedures over synthetic `SourceWindow` paths: exact
  per-window metrics, STABLE at floor, first-window / post-gap no-prior turnover, the
  `NO_TRANSITIONS` all-UNDEFINED turnover family, the all-gaps `NO_REALIZED_WINDOWS`
  guard, and repeated computation identical.
- `test_identity` (5) — `sha256:`-prefixed, deterministic, each-fold-changes-the-id
  (including the transitive `source_result_hash` pin and the `MIN_STABILITY_TRANSITIONS`
  fold), result-hash sensitive to a single cell, and order sensitivity.
- `test_result` (7) — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip, id re-derived not read from state (tampered stored id
  ignored), the accessors, that the derivable `effective_breadth` is excluded from
  `result_hash` (two records differing only in it seal identically), and `from_dict`
  rejects a malformed `source_ref`.
- `test_public_api` (2) — public exports and the lazy/cached `Workspace.stability_engine`.
- `test_engine` (17) — happy path (full family, aggregates match the fixture, per-window
  cells map back to source order), source reference pinned, UNDEFINED-window exclusion
  with the straddling window's turnover UNDEFINED across the gap, `NO_TRANSITIONS`,
  below-floor still seals, boundary carried and the record not PIT; wrong-length and
  non-KNOWN weight fail-closed; recompute byte-identical and idempotent; identity
  sensitivity to the source answer and the request name; and every fail-closed guard
  (absent source, non-`WalkForwardEvaluation` record, id-mismatch via a path-swapped
  payload, non-spec argument, and a tampered stored payload → `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` /
`pytest -q` / `pytest -q -p no:randomly`; 1941 tests pass; zero new runtime dependencies;
every prior-phase id preserved (no prior source touched beyond the additive
`workspace.py` / `__init__.py` re-exports).**
