# Phase 26 — Walk-Forward Risk-Forecast Calibration (LOCKED)

> **Status:** Locked normative specification. The Phase 26 proposal was **approved as
> recommended** — the recommended capability C1 (§7 / §12 of the proposal, not the deferred
> alternatives C2–C12): consume exactly one sealed `WalkForwardEvaluation`, treat its
> *calibratable* windows as the family, and per window seal the forecast-vs-outcome variance
> and volatility ratios plus the aggregate bias / dispersion / frequency statistics that
> answer whether the Phase-20 covariance the whole GMV chain rests on actually forecasts
> realized out-of-sample risk. This document reflects the **actual implementation** and is the
> source of truth; it supersedes the recommendations in
> [phase26-risk-forecast-calibration-proposal.md](phase26-risk-forecast-calibration-proposal.md).
> Every ★-marked decision in the proposal is resolved here to a committed decision.
>
> **One-line thesis:** Phase 26 adds a deterministic, content-addressed **risk-forecast
> calibration** layer — the platform's first *out-of-sample risk-model validation* capability
> and the first consumer of Phase 22's reserved-but-unconsumed per-window
> `predicted_variance` / `realized_variance` payload. Given a declarative
> `RiskForecastCalibrationSpecification` naming exactly one sealed `WalkForwardEvaluation` id,
> `RiskForecastCalibrationEngine.calibrate(...)` resolves the one walk from the shared Phase 8
> research sidecar, re-verifies it (present, a `WalkForwardEvaluation`, id matches), classifies
> each window into the calibratable family (every non-calibratable window recorded as a
> first-class exclusion, never imputed), computes per window `variance_ratio = realized /
> predicted` and `volatility_ratio = √realized / √predicted` and over the family the pooled
> `aggregate_bias`, the mean ratio, the population dispersion, the under-forecast frequency,
> and the min / max — all under one pinned `Decimal` context — and seals a
> `RiskForecastCalibration` `ResearchRecord` write-once to the existing sidecar. It introduces
> **no** new numerical primitive (`Decimal.sqrt` is the only transcendental, already used by
> Phases 19/20/22), **no** `_linalg`/`_stats` change, **no** RNG, **no** floating point, **no**
> iterative solver, **no** new store, and **no** new PIT surface, and modifies no prior phase's
> vocabulary, engine, or identity.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D-SCOPE** | **OOS risk-forecast calibration over the calibratable-window family of one walk (C1).** The family is exactly the source `WalkForwardEvaluation`'s calibratable windows — `REALIZED`, with a KNOWN, strictly-positive `predicted_variance` and a KNOWN `realized_variance` — in sealed source order. Per window seal `variance_ratio` / `volatility_ratio` (plus the derivable `predicted_volatility` / `realized_volatility` for readability); over the family seal `mean_variance_ratio`, the pooled `aggregate_bias`, `variance_ratio_dispersion`, `underforecast_frequency`, `max_variance_ratio`, `min_variance_ratio`, and `calibration_status`; seal the coverage (`n_windows`, `n_calibratable`, `n_excluded`). **No** cross-walk family (one source only, §20); **no** rolling/blocked recomputation of variances (RC-4); **no** new covariance estimator (C6), risk attribution (C9), or PBO (C12). It performs **no execution**, resolves **no** data at any `T`, and is **not** a `BacktestResult`. |
| **D-INPUT** | **A new pure-consumer layer strictly *above* Phase 22.** It resolves exactly **one** already-sealed `WalkForwardEvaluation` from the shared sidecar by id, reads each window's sealed `status` / `predicted_variance` / `realized_variance` (never re-derives them), and **modifies no** prior-phase vocabulary, engine, or identity. It is the first consumer of the `predicted_vs_realized` payload the Phase 22 architecture explicitly reserved. |
| **D-COMPUTE** | **Closed-form exact-`Decimal` ratios and aggregates, one `Decimal.sqrt` pair per window.** Per calibratable window under the pinned context: `variance_ratio = realized / predicted`, `predicted_volatility = √predicted`, `realized_volatility = √realized`, `volatility_ratio = realized_volatility / predicted_volatility`. Over the `k`-window family: `mean_variance_ratio = (Σ variance_ratio) / k`; the pooled `aggregate_bias = Σrealized / Σpredicted` (a Barra-style bias ratio: `>1` ⇒ the model systematically **under-forecasts** risk, `<1` ⇒ over-forecasts); `variance_ratio_dispersion = √(Σ(ratio − mean)² / k)` (population); `underforecast_frequency = |{realized > predicted}| / k`; `max`/`min_variance_ratio`. |
| **D-STATUS** | **`calibration_status` defensible only at the floor (RC-5).** `CALIBRATED` iff `n_calibratable ≥ MIN_CALIBRATABLE_WINDOWS`, else `UNDEFINED` with `INSUFFICIENT_CALIBRATABLE_WINDOWS`; the per-window ratios still seal either way. An empty family (`k = 0`) seals every aggregate as a first-class UNDEFINED (`NO_CALIBRATABLE_WINDOWS`) — never a divide-by-zero, never a fabricated ratio. |
| **D-EXCLUDE** | **Non-calibratable windows are excluded, never imputed (RC-3).** A source window that is not calibratable is removed from the family and recorded as a first-class `ExcludedWindow` carrying its `CalibrationExcludedReason` — never coerced to a ratio, never imputed, never silently dropped; `n_calibratable + n_excluded = n_windows`. The closed reason set is `WINDOW_UNDEFINED` (whole window UNDEFINED), `SINGLE_VALID_PERIOD` (a `REALIZED` window whose `realized_variance` is UNDEFINED), and the defensive, structurally-unreachable `ZERO_PREDICTED_VARIANCE` (non-positive predicted variance) and `PREDICTED_VARIANCE_UNDEFINED` (UNDEFINED predicted variance in a `REALIZED` window). |
| **D-CONSUME** | **Sealed forecasts and outcomes are consumed verbatim (RC-4).** The engine parses each window's sealed `predicted_variance` / `realized_variance` decimal strings once and never re-solves a window, re-derives a covariance, or recomputes a variance from `oos_returns`. The canonical form `str(+Decimal(source))` is idempotent for an already-canonical source string, so a carried-through value is byte-for-byte the source value. |
| **D-EXPOST** | **The output is ex-post, never PIT (RC-6).** A calibration over an already-ex-post walk is itself ex-post. `RiskForecastCalibration` is **not** a `Pit*` type, exposes **no** as-of accessor, and is not a `BacktestResult`. `boundary_kind = "pit"` is carried unchanged from the source walk and documents only that the *underlying factor portfolios were PIT walks*; it never claims the calibration is a PIT value. No new corpus read, no availability logic, no new PIT resolution. |
| **D-DETERMINISM** | **Exact-`Decimal`, no float / RNG / wall-clock / `id()` / iteration-order (RC-4/RC-5).** All arithmetic runs under an explicit `localcontext` (precision 34, `ROUND_HALF_EVEN`); `Decimal.sqrt` is the only transcendental (the exact method Phases 19/20/22 already use); canonicalization is `str(+value)`. No RNG, no iteration-to-convergence, no `_linalg`/`_stats` change, no new numerical primitive. The engine version folds the decimal context **and** the method version into `config_hash`. |
| **D-IDENTITY** | **Content-addressed, transitively pinned, self-verifying (RC-1).** `risk_forecast_calibration_id` folds the engine version, the request (name, spec version), the source walk's `research_result_id` **and** its `result_hash` (the transitive pin), the `MIN_CALIBRATABLE_WINDOWS` floor, and the `result_hash` over the computed answer. `research_result_id` aliases `risk_forecast_calibration_id`; derived ids are re-emitted by properties, never read from stored state. Domain tag `calibration/1`. |
| **D-STORE** | **One write-once record in the existing `ResearchResultStore`; no new store, no migration.** `RiskForecastCalibration` satisfies the `ResearchRecord` Protocol and persists to `research/sha256-<hex>.json`. An idempotent re-write of a byte-identical payload is a no-op; a conflicting payload under the same id raises `FactorConsistencyError` (the existing store contract). |
| **D-FLOOR** | **`MIN_CALIBRATABLE_WINDOWS = 2`**, a module constant in `result.py` (not a spec field, mirroring walk-forward's `MIN_VALID_WINDOWS`), folded into `risk_forecast_calibration_id` so a change to it is a distinguishable record. A single forecast-vs-outcome ratio carries no cross-window structure. |
| **D-INVARIANTS** | **RC-1..RC-6 are documented both as phase-local invariants here (§7) and as a small additive `data-model.md §12` block** mirroring the WF-/CE-/SC-/MC- blocks (they do not weaken invariants 1–30). |
| **D-VERSION** | This phase releases as **`v0.23.0`** (Phase 25 = v0.22.0). Domain tag `calibration/1`; engine-version string `calibration-engine/1`; method string `calibration-method/1`; spec-version string `calibration/1`; record-format string `calibration-result/1`. The package `__version__` string is unchanged `"0.0.0"` (versioning is by content-addressed ids + the README table, not a semver string). No `pyproject`/packaging change; no new runtime dependency. |

### 1.1 Deviations from the proposal (disclosed)

Recorded for auditability; neither changes an identity discipline or weakens an invariant.

- **`volatility_ratio` is computed as `realized_volatility / predicted_volatility`, not
  `√variance_ratio`.** The proposal (§7) wrote `volatility_ratio = √variance_ratio`. The two are
  mathematically identical (`√(realized/predicted) = √realized / √predicted`); the
  implementation computes it from the two independently-rooted volatilities already needed for
  the `predicted_volatility` / `realized_volatility` cells, which is the more direct expression
  of "the bias on the volatility scale" and avoids a second division-then-root. Under exact
  `Decimal` at prec 34 the sealed strings agree; the choice is folded into the pinned method
  version regardless.
- **A fourth exclusion reason, `PREDICTED_VARIANCE_UNDEFINED`, is added.** The proposal listed
  three reasons (`WINDOW_UNDEFINED`, `SINGLE_VALID_PERIOD`, `ZERO_PREDICTED_VARIANCE`). The
  implementation adds `PREDICTED_VARIANCE_UNDEFINED` — a `REALIZED` window whose
  `predicted_variance` is itself UNDEFINED — as a **defensive, structurally-unreachable**
  fail-closed guard alongside `ZERO_PREDICTED_VARIANCE` (a `REALIZED` GMV window always seals a
  KNOWN in-sample `wᵀΣw`). It closes the classification so a corrupt source can never be coerced
  into a ratio, and is exercised by a synthetic test.

Resolved ★ decisions of note: **★1** capability = C1 (OOS risk-forecast calibration of one
walk); **★2** source is exactly one `WalkForwardEvaluation`, consumed by id; **★3** output
`RiskForecastCalibration`; **★4** package `calibration`, domain tag `calibration/1`; **★5**
public names `RiskForecastCalibrationSpecification` / `RiskForecastCalibration`; **★6**
per-window variance & volatility ratios + pooled bias / dispersion / frequency; **★7**
exact-`Decimal`, no new primitive; **★8** ex-post, not a `Pit*`, boundary carried; **★9**
exclude-never-impute UNDEFINED windows, `MIN_CALIBRATABLE_WINDOWS = 2`; **★10** identity fold as
in §5; **★11** v0.23.0; **★12** no `_linalg`/`_stats` change; **★13** no `N_MAX`; **★14** a
sibling package, no prior-phase edit; **★15** shared write-once `ResearchResultStore`.

---

## 2. What was built

New package **`src/quantforge/calibration/`** (mirrors the P20/P22/P23/P24/P25 layout):

| Module | Responsibility |
|---|---|
| `errors.py` | `CalibrationError` → `CalibrationConfigurationError`, `CalibrationConsistencyError`. |
| `version.py` | `RiskForecastCalibrationEngineVersion` (folds the pinned decimal context + `calibration-method/1` into `config_hash`; **no** normal-primitive version — none is reused); constants `CALIBRATION_SPEC_VERSION` / `CALIBRATION_ENGINE_VERSION` / `CALIBRATION_METHOD_VERSION`; `default_decimal_context()` (prec 34, `ROUND_HALF_EVEN`). |
| `model.py` | The closed `CalibrationStatus` (`calibrated`, `undefined`), `CalibrationExcludedReason` (`window_undefined`, `single_valid_period`, `zero_predicted_variance`, `predicted_variance_undefined`), `CalibrationUndefinedReason` (`no_calibratable_windows`, `insufficient_calibratable_windows`), `StatStatus`, and the UNDEFINED-preserving `CalibrationStat` cell (`known` / `undefined` / `to_dict` / `from_dict`). |
| `spec.py` | `RiskForecastCalibrationSpecification` (declarative request; fail-closed validation; `name`, `source_walk_forward_id`, `spec_version = "calibration/1"`). |
| `compute.py` | The pure exact-`Decimal` procedures: `calibrate(calibratable, *, min_calibratable, context) → CalibrationComputation`; `CalibratableWindow`, `WindowRatios`, `CalibrationSummaryComputation`; per-window ratios and the family aggregates. |
| `result.py` | `RiskForecastCalibration` (`ResearchRecord`; `seal` / `to_dict` / `from_dict`, derived ids, `calibration_status` accessor), `WindowCalibrationCell`, `ExcludedWindow`, `CalibrationSummary`, `CalibrationCoverage`; `MIN_CALIBRATABLE_WINDOWS = 2`, `CALIBRATION_RESULT_FORMAT_VERSION`, `BOUNDARY_PIT = "pit"`. |
| `identity.py` | `risk_forecast_calibration_result_hash`, `risk_forecast_calibration_id`; domain tag `calibration/1`. |
| `engine.py` | `RiskForecastCalibrationEngine.calibrate(spec)`. |
| `__init__.py` | Package exports. |

**Additive edits to existing source (none altering any existing identity):**
1. `workspace.py` — one lazy `risk_calibration_engine` `@property` (+ private
   `_risk_calibration_engine` cache slot), following the `multiplicity_engine` template (typed
   `-> object`, deferred import of `RiskForecastCalibrationEngine` to avoid the module-load
   cycle).
2. `src/quantforge/__init__.py` — top-level re-exports of `RiskForecastCalibrationSpecification`
   and `RiskForecastCalibration`, added to the sorted `__all__`.

**No edit to** `_linalg`, `_stats`, `walkforward`, `comparison`, `multiplicity`, `campaign`,
`optimization`, `factorrisk`, `factorportfolio`, `analytics`, `backtest`, or any other
prior-phase identity/vocabulary. Phase 26 reuses **no** standard-normal primitive (it consumes
already-sealed variances), so `_stats/normal.py` is untouched.

---

## 3. Data flow

```
RiskForecastCalibrationSpecification { name, source_walk_forward_id, spec_version }
        │
        ▼  RiskForecastCalibrationEngine.calibrate(spec)
type-check spec is a RiskForecastCalibrationSpecification                    — CalibrationConfigurationError
        │
        ▼
resolve the ONE source walk-forward by id                                   — fail closed (RC-1)
   store.read_as(id, WalkForwardEvaluation.from_dict)
   present? decodes as a WalkForwardEvaluation? research_result_id == id?    — else CalibrationConsistencyError
        │
        ▼
classify each window in sealed source order                                 — RC-2/RC-3/RC-4
   REALIZED & predicted KNOWN & > 0 & realized KNOWN → CalibratableWindow (parse the two strings)
   else                                              → ExcludedWindow carrying its reason (never imputed)
        │
        ▼  under localcontext(prec 34, ROUND_HALF_EVEN):
   calibrate(calibratable, min_calibratable=MIN_CALIBRATABLE_WINDOWS, context)   — RC-4/RC-5
     per window: variance_ratio = realized/predicted; vol = √predicted, √realized;
                 volatility_ratio = √realized / √predicted
     family (k):  mean ratio; aggregate_bias = Σrealized/Σpredicted;
                  dispersion = √(Σ(r−mean)²/k); underforecast_frequency = |{r>p}|/k; max/min
     calibration_status = CALIBRATED iff k ≥ floor, else UNDEFINED(INSUFFICIENT); k=0 ⇒ all UNDEFINED(NO_CALIBRATABLE)
        │
        ▼
coverage = { n_windows, n_calibratable = k, n_excluded }                    — RC-2
        │
        ▼
RiskForecastCalibration.seal(...)  (result_hash folds the answer;
   boundary_kind carried from source; source_ref = (source id, source result_hash))  — RC-1/RC-6
        │
        ▼
ResearchResultStore.write(calibration)   (write-once, idempotent)           — D-STORE
        │
        ▼
store.read_as(id, RiskForecastCalibration.from_dict)   (byte-identical typed round-trip)
```

---

## 4. Public API

```python
from quantforge import (
    Workspace,
    RiskForecastCalibrationSpecification,
    RiskForecastCalibration,
)

ws = Workspace.open(root)

spec = RiskForecastCalibrationSpecification(
    name="gmv-walk:risk-calibration",
    source_walk_forward_id=walk_forward_id,  # exactly one sealed WalkForwardEvaluation id
)

calibration = ws.risk_calibration_engine.calibrate(spec)  # sealed, write-once

calibration.calibration_status  # CALIBRATED / UNDEFINED (roll-up)
calibration.coverage  # n_windows, n_calibratable, n_excluded
calibration.windows  # tuple[WindowCalibrationCell]: per-window ratios in source order
calibration.excluded  # tuple[ExcludedWindow]: (index, reason) for non-calibratable windows
calibration.summary  # CalibrationSummary: mean ratio, aggregate_bias, dispersion, frequency, max/min
calibration.source_walk_forward_id  # the pinned source walk id
calibration.source_result_hash  # the transitive pin
calibration.research_result_id  # == calibration.risk_forecast_calibration_id

again = ws.research_result_store.read_as(
    calibration.research_result_id, RiskForecastCalibration.from_dict
)
```

`RiskForecastCalibrationEngine` is reached only through `Workspace.risk_calibration_engine`
(lazy, cached, `-> object`). `calibrate(spec) -> RiskForecastCalibration` is the single entry
point.

`RiskForecastCalibrationSpecification` (frozen slots): `name`, `source_walk_forward_id`,
`spec_version = "calibration/1"`. Construction-time validation (fail closed): non-empty `name`
/ `spec_version` / `source_walk_forward_id`. There is **no** per-request numerical parameter —
the calibratable-windows floor is the platform constant `MIN_CALIBRATABLE_WINDOWS` and the
metric set is the single approved methodology.

Each `CalibrationSummary` carries six UNDEFINED-preserving `CalibrationStat` cells
(`mean_variance_ratio`, `aggregate_bias`, `variance_ratio_dispersion`,
`underforecast_frequency`, `max_variance_ratio`, `min_variance_ratio`), the roll-up
`calibration_status`, and an optional `status_reason`.

---

## 5. Identity and hashing

- Domain tags via shared `sha256_hex`, NUL-separated (`_SEP = "\x00"`), canonical JSON
  (`sort_keys=True, ensure_ascii=False, separators=(",",":")`), `sha256:`-prefixed.
- `risk_forecast_calibration_engine_version_id = sha256(code_version "calibration-engine/1",
  config_hash)` where
  `config_hash = sha256("prec=34\x00round=ROUND_HALF_EVEN\x00method=calibration-method/1")`.
  Folding the method version makes the calibration's identity change if the calibratable-window
  selection, the per-window ratios, the pooled bias, the mean, the dispersion, the
  under-forecast frequency, or the min / max changes. **No** normal-primitive version is folded
  — none is reused.
- `risk_forecast_calibration_result_hash = sha256(canonical JSON over the ordered
  computed-output cells: the coverage descriptor
  `{block:"coverage_descriptor", n_windows, n_calibratable, n_excluded}`, then each calibratable
  window `{block:"window", index, predicted_variance, realized_variance, variance_ratio,
  volatility_ratio}` in source order, then each `{block:"excluded", index, reason}`, then
  `{block:"summary", ...}`)`. The derivable per-window volatilities are omitted (the variances
  fold them). Sensitive to every computed ratio and aggregate.
- `risk_forecast_calibration_id = sha256`, NUL-joined, in order: `calibration/1`,
  `risk_forecast_calibration_engine_version_id`, `name`, `spec_version`,
  `source_walk_forward_id`, `source_result_hash` (the transitive pin, RC-1),
  `str(MIN_CALIBRATABLE_WINDOWS)`, and `risk_forecast_calibration_result_hash`.
- `research_result_id` aliases `risk_forecast_calibration_id`. Derived ids are re-emitted by
  properties, never read from stored state — a tampered stored id is ignored and
  `from_dict(to_dict(r))` re-emits identical bytes. The record-format version is **not** folded
  (a container concern). Coverage is **not** folded beyond the descriptor (it is a pure function
  of the sealed window / excluded lists).

---

## 6. Determinism / Decimal rules

- All calibration arithmetic runs under an explicit `localcontext` (precision 34,
  `ROUND_HALF_EVEN`): the per-window `realized / predicted`, the two `Decimal.sqrt` volatilities
  and the volatility ratio, the pooled `Σrealized / Σpredicted`, the mean, the population
  dispersion (a `Decimal.sqrt` of a mean-of-squared-deviations), the under-forecast frequency,
  and the min / max. **No float anywhere**, no RNG, no wall-clock, no `id()`, no
  iteration-to-convergence, no data-dependent iteration order.
- Values are canonicalized as `str(+value)` inside the pinned context; the per-window
  `variance_ratio` is computed once and reused for every aggregate, so a cell's ratio and the
  aggregates over it can never disagree.
- Same source walk + same request → same `risk_forecast_calibration_id` and byte-identical
  payload on any machine. A repeated `calibrate` is a byte-identical no-op (store idempotence).
  Two engines over the same immutable sidecar agree. Because Phase 26 folds the source walk's
  `result_hash`, any upstream change changes this record's id while a byte-identical recompute
  reproduces identical bytes (the Phase 22 audit standard, one layer up).

---

## 7. Invariants (RC-1..RC-6)

Additive to `data-model.md §12`; these do not weaken invariants 1–30.

- **RC-1 — Reference verification and transitive pinning.** The single `source_walk_forward_id`
  is resolved from the shared sidecar via `store.read_as(id, WalkForwardEvaluation.from_dict)`,
  re-verified (`research_result_id == id`, and that it decodes as a `WalkForwardEvaluation`), and
  its `result_hash` folded into `risk_forecast_calibration_id`; through the source walk's own id
  this pins the optimization / risk-model / factor chain beneath it (WF-1). Any missing,
  non-decoding, or id-mismatched reference fails closed with `CalibrationConsistencyError`; the
  source is never copied, only pinned. *(The WF-1 / CE-1 / MC-1 discipline, one layer up.)*
- **RC-2 — The calibrated object is an explicit, sealed family of windows.** The family is
  exactly the calibratable windows of the one source walk, in source order; the coverage
  (`n_windows`, `n_calibratable`, `n_excluded`, with `n_calibratable + n_excluded = n_windows`)
  is sealed so the effective sample the aggregates used is auditable and never inferred. One
  source only (no cross-walk family in v0.23.0).
- **RC-3 — Non-calibratable windows are excluded, never imputed.** A window that is not
  calibratable (`WINDOW_UNDEFINED`, `SINGLE_VALID_PERIOD`, or the defensive
  `ZERO_PREDICTED_VARIANCE` / `PREDICTED_VARIANCE_UNDEFINED`) is removed from the family and
  recorded as a first-class `ExcludedWindow` carrying its `CalibrationExcludedReason` — never
  coerced to a ratio, never imputed, never silently dropped. An empty family (`k = 0`) seals
  every aggregate as a first-class UNDEFINED (`NO_CALIBRATABLE_WINDOWS`) and a
  `calibration_status` of UNDEFINED, never a divide-by-zero. *(The WF-4 / SC-4 / MC-3 posture,
  adapted to windows.)*
- **RC-4 — Sealed forecasts and outcomes are consumed verbatim, never recomputed.** Each
  window's already-sealed `predicted_variance` (in-sample `wᵀΣw`) and `realized_variance`
  (out-of-sample population variance) are read as decimal strings and never re-solved,
  re-derived, or recomputed from `oos_returns`; `str(+Decimal(source))` is idempotent for an
  already-canonical source string, so a carried-through value is byte-for-byte the source value.
  *(The MC-5 posture of operating over already-sealed strings, one layer up.)*
- **RC-5 — Single deterministic methodology.** One exact-`Decimal` method per family — the
  per-window variance / volatility ratios, the mean ratio, the pooled `aggregate_bias`, the
  population dispersion, the under-forecast frequency, and the min / max — all under one pinned
  decimal context (prec 34, `ROUND_HALF_EVEN`) folded into the engine identity, with
  `Decimal.sqrt` the only transcendental. `calibration_status` is `CALIBRATED` iff the family
  meets the platform floor `MIN_CALIBRATABLE_WINDOWS` (folded into the id), else UNDEFINED
  (`INSUFFICIENT_CALIBRATABLE_WINDOWS`); the per-window ratios still seal. No RNG, no float, no
  data-dependent iteration, no `_linalg`/`_stats` change, no new primitive. *(The WF-5 / MC-5
  discipline, reusing exact `Decimal` arithmetic.)*
- **RC-6 — A calibration is not a PIT value and not a `BacktestResult`.** A calibration over an
  already-ex-post walk is itself ex-post: `RiskForecastCalibration` is **not** a `Pit*` type,
  exposes no as-of accessor, is a distinct record type, simulates no fills, and opens no new
  corpus / availability surface. `boundary_kind = "pit"` — carried unchanged from the source
  walk — documents only that the *underlying factor portfolios* were PIT walks. *(The WF-3 /
  SC-6 / MC-6 discipline, one layer up.)*

---

## 8. Failure / UNDEFINED semantics

**Raised** — `CalibrationConfigurationError`: a non-`RiskForecastCalibrationSpecification`
argument to the engine; a malformed spec (empty `name` / `spec_version` /
`source_walk_forward_id`). `CalibrationConsistencyError` (RC-1): the `source_walk_forward_id`
absent from the sidecar; a payload that does not decode as a `WalkForwardEvaluation`; a
resolved-id disagreement.

**Recorded as first-class UNDEFINED** (RC-3, never raised): each non-calibratable window is
excluded and recorded as an `ExcludedWindow` with its reason; a family below the floor still
seals with `calibration_status = UNDEFINED (INSUFFICIENT_CALIBRATABLE_WINDOWS)`; an empty family
seals every aggregate UNDEFINED (`NO_CALIBRATABLE_WINDOWS`).

**Store contract:** a byte-identical re-write is an idempotent no-op; a differing payload under
the same calibration id raises `FactorConsistencyError` (the existing write-once guard).

---

## 9. Testing

`tests/calibration/` (offline, synthetic). Because the engine reads **only** the source
`WalkForwardEvaluation` via `store.read_as`, the builders (`tests/calibration/builders.py`)
construct synthetic `WalkForwardEvaluation` records directly — sealing hand-chosen per-window
`predicted_variance` / `realized_variance` cells (KNOWN decimal strings or UNDEFINED reasons)
via `WalkForwardEvaluation.seal` and writing them to the store — rather than running the full
factor → optimization → walk-forward chain. Per-window helpers cover every classification branch
(`realized_window`, `undefined_window`, `single_period_window`, `zero_predicted_window`,
`predicted_undefined_window`).

Suites (**49 tests** across the package):
- `test_spec` (7) — the default spec version, the canonical `to_dict`, fail-closed rejection of
  empty `name` / `source_walk_forward_id` / `spec_version`, and frozenness.
- `test_model` (7) — the KNOWN/UNDEFINED `CalibrationStat` construction guards, `to_dict` /
  `from_dict` round-trip, fail-closed decode of corrupt cells, and the closed status / reason /
  excluded-reason vocabularies.
- `test_compute` (10) — the pure procedures: the two-window exact hand-calculation
  (`predicted = (4, 1)`, `realized = (1, 4)`: ratios `0.25` / `4`, volatilities `2`/`1`, `1`/`2`,
  vol ratios `0.5` / `2`; mean `2.125`, `aggregate_bias 1`, dispersion `1.875`, frequency `0.5`,
  max `4`, min `0.25`), verbatim consumption (`0.0009 / 0.0016 = 0.5625`, roots `0.04` / `0.03`),
  the below-floor UNDEFINED status with the single ratio still sealed, the at-floor-one
  CALIBRATED case, the empty-family all-UNDEFINED guard, perfect calibration (unit ratios, zero
  dispersion, zero frequency), all-under-forecast frequency `1`, and repeated calls
  byte-identical.
- `test_identity` (5) — `sha256:`-prefixed, deterministic, each-fold-changes-the-id (including
  the `MIN_CALIBRATABLE_WINDOWS` fold), result-hash sensitive to a single cell, and order
  sensitivity.
- `test_result` (9) — seal folds the answer, derived id aliases `research_result_id`,
  byte-identical round-trip, id re-derived not read from state (tampered stored id ignored), the
  accessors, not-a-`Pit*`-and-no-as-of, that the derivable volatilities are excluded from
  `result_hash` while a `variance_ratio` change changes it (both probed by re-sealing), and
  `from_dict` rejects an unknown excluded reason.
- `test_engine` (11) — happy path (full family calibrated, aggregates match the hand-calc,
  per-window ratios map back to source order), source reference pinned, every exclusion reason
  classified (all four in one walk, below-floor status), the all-UNDEFINED empty family, boundary
  carried and the record not PIT; recompute byte-identical and idempotent, write-once no conflict
  for the same id; identity sensitivity to the source answer and the request name; and every RC-1
  fail-closed guard (absent source, non-`WalkForwardEvaluation` record, id-mismatch via a
  path-swapped payload, non-spec argument, and a tampered stored payload →
  `FactorConsistencyError`).

**Gate (all green): `ruff check .` / `ruff format --check .` / `mypy src tests` / `pytest -q` /
`pytest -q -p no:randomly`; 1893 tests pass; zero new runtime dependencies; every prior-phase
id preserved (no prior source touched beyond the additive `workspace.py` / `__init__.py`
re-exports).**
