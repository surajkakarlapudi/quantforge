# Phase 13 — Comparative Research: Experiment Sweeps & Backtest Comparison (LOCKED)

> **Status:** Locked normative specification. Decisions **D1–D8** were approved as
> recommended; this document is the source of truth for the implementation and
> supersedes the recommendations in
> [phase13-comparative-research-proposal.md](phase13-comparative-research-proposal.md).
> Every conditional reference in the proposal ("recommended", "if the user wants…")
> is resolved here to a committed decision.
>
> **One-line thesis:** Phase 13 closes the loop from *one* reproducible backtest to
> *comparative, reproducible research* — a declarative **Experiment** (a content-addressed
> family of `BacktestSpecification`s produced by a parameter sweep) and a **BacktestComparison**
> (a deterministic, PIT-aware diff/ranking over sealed `BacktestResult`s) — reusing every
> existing store, identity, and PIT invariant, adding no new source, no database, and no
> runtime dependency.

---

## 1. Locked decisions

| # | Decision (locked) |
|---|---|
| **D1** | Phase 13 **is** Comparative Research: parameter **sweep** + backtest **comparison** as one capability. Python-callback strategies are rejected outright (they break the content-addressed `backtest_id`). |
| **D2** | Corpus pins are **not** sweepable within one `ExperimentSpecification`. Every expanded child inherits `base.dataset_version_id` and `base.market_dataset_version_id` **verbatim**. One experiment ranges over exactly one pinned corpus pair. Cross-corpus comparison is the job of `BacktestComparison.pin_mismatch`, never of mixing corpora inside an experiment. |
| **D3** | **D3-A is adopted.** `BacktestResult.from_dict` and `from_dict` on every nested value type (`TargetWeights`, `SignalRef`, `Fill`, `AppliedAction`, `RebalanceRecord`, `PerformanceStatistics`, `PerformanceSummary`, `Position`) are added additively. Round-trip is byte-identical: `from_dict(to_dict(r))` re-emits an identical `to_dict()` and an identical `result_hash`. This is the **only** edit to existing Phase 12 source. |
| **D4** | `ExperimentResult` and `BacktestComparison` are `ResearchRecord`s persisted write-once to the existing `<root>/research/sha256-<hex>.json` sidecar. No new store, no database. |
| **D5** | Annualization (`periods_per_year`, `risk_free_per_period`) is a **run argument** threaded unchanged to every child, **not** a sweep axis. `ExperimentEngine.run(spec, *, risk_free_per_period="0", periods_per_year="1")` mirrors `BacktestEngine.run`. It is folded into each child's `backtest_id` and into `experiment_id`, but not into `result_hash`. |
| **D6** | `Company` gains **no** Phase 13 method. Experiments and comparisons are engine-/standalone-only, exactly as the backtester and the universe matrix are. |
| **D7** | The closed v1 sweepable-parameter vocabulary is exactly: `select_n`, `rank`, `signal`, `period`, `cost_model.proportional_bps`, `cost_model.fixed_per_order`, `schedule`, `initial_capital`, `universe`. Anything outside it fails closed with `ExperimentConfigurationError`. Extending the set is an explicit future edit, never an implicit fallback. |
| **D8** | This `-locked` normative document exists (matching the Phase 10/11 precedent) and the `ARCHITECTURE.md` "Reproducible Research" row flips to ✅ only once the full suite is green. |

---

## 2. Architecture (locked)

Phase 13 is a thin orchestration + analysis layer strictly *above* Phase 12, a **pure
consumer** of sealed, PIT-correct `BacktestResult`s. It follows the extension recipe every
prior phase uses: versioned immutable request object → fail-closed engine reached from
`Workspace` via a lazy, cycle-free `@property` → distinct result types → content-addressed
identity with fresh domain tags → data conditions recorded as first-class values, defects
raised → compute-on-demand with the shared write-once sidecar.

```
                 ExperimentSpecification            (declarative sweep, content-addressed)
                          |
                          v
   Workspace.experiment_engine  --->  ExperimentEngine
                          |                 |
       (expands, pure Cartesian product)    | for each child spec:
                          v                 v
        [ BacktestSpecification x N ]   BacktestEngine.run(spec, ...)   (Phase 12, unchanged)
                          |                 |
                          |                 v
                          |          BacktestResult (sealed) --> ResearchResultStore  (existing sidecar)
                          v                 |
                  ExperimentResult  <-------+   (records every child backtest_id + coordinate)
                          |
                          v
     BacktestComparison.of_* ([...], read via store.read_as(id, BacktestResult.from_dict))
                          |
                          v
             to_dict() / to_records()  (dependency-free export; itself a ResearchRecord)
```

**New package `src/quantforge/experiment/`:**

- `errors.py` — `ExperimentError` → `ExperimentConfigurationError`, `ExperimentConsistencyError`.
- `identity.py` — `experiment_id`, `sweep_axis_id`, `experiment_result_hash`, `comparison_id`,
  plus `experiment_engine_version_id` / `comparison_version_id`. Domain tags `experiment/1`,
  `sweep-axis/1`, `experiment-engine/1`, `backtest-comparison/1`.
- `spec.py` — `SweepAxis`, `ExperimentSpecification`, the closed vocabulary, typed
  substitution and `expand()`, full construction-time validation.
- `result.py` — `ExperimentRun`, `ExperimentResult` (a `ResearchRecord` with `from_dict`).
- `engine.py` — `ExperimentEngine` (constructed from `Workspace`, composes `backtest_engine`
  and `research_result_store`): expand → run/reuse-by-id → seal.
- `analysis.py` — `BacktestComparison`, `ComparisonEntry`, ranking/attribution, `pin_mismatch`.
- `__init__.py` — package exports.

The **only** edit to existing source is `BacktestResult.from_dict` (+ nested `from_dict`s) in
`backtest/result.py` and `Position.from_dict` in `backtest/portfolio.py` (D3), plus the lazy
`Workspace.experiment_engine` property and the top-level re-exports in `__init__.py`.

---

## 3. Data model (locked)

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only for numeric fields
(no float), no wall-clock, no RNG — consistent with every prior phase.

### 3.1 `SweepAxis`

```
SweepAxis(parameter: str, values: tuple[object, ...])
```

- `parameter` must be a member of the D7 closed vocabulary; anything else raises
  `ExperimentConfigurationError` at construction.
- `values` is ordered and load-bearing for enumeration order. The identity `sweep_axis_id`
  sorts the canonicalized values, so `(1, 5)` and `(5, 1)` yield the same axis id (an axis is a
  *set* of values). Enumeration order for display is a separate deterministic sort over the
  canonical form.
- Empty `values`, a duplicate value (by canonical form), or a value of the wrong type for the
  parameter raises at construction.

### 3.2 `ExperimentSpecification`

```
ExperimentSpecification(
    name: str,                         # non-empty
    base: BacktestSpecification,       # fully pinned; every child starts here
    axes: tuple[SweepAxis, ...],       # >= 1 axis; distinct parameters (no collision)
    spec_version: str = "experiment/1",
)
```

- **Corpus pins are inherited unchanged (D2):** every child carries `base.dataset_version_id`
  and `base.market_dataset_version_id` verbatim.
- `expand() -> tuple[tuple[Coordinate, BacktestSpecification], ...]` is a pure, total Cartesian
  product; family size is `∏ len(axis.values)`. Each coordinate is a sorted tuple of
  `(parameter, canonical-value)` pairs; the child spec is `base` rebuilt with those parameters
  substituted (a fresh `StrategySpecification.rank_select_weight(...)` / `CostModel(...)` /
  `UniverseSpecification` / `RebalanceSchedule` / scalar) — never a mutation.
- `experiment_id` folds `name`, `spec_version`, the base spec identity (`base.to_dict()`
  canonicalized), the sorted `sweep_axis_id`s, and the annualization run convention passed to
  `run` (folded at seal time, see §3.3).

### 3.3 `ExperimentRun` / `ExperimentResult`

```
ExperimentRun(coordinate: tuple[tuple[str, str], ...], backtest_id: str)

ExperimentResult(  # implements ResearchRecord
    experiment_id, experiment_engine_version_id,
    base_backtest_request: dict,           # base.to_dict() — full reproducibility
    axis_ids: tuple[str, ...],             # sorted sweep_axis_ids
    runs: tuple[ExperimentRun, ...],       # one per coordinate, ordered by canonical coordinate
    risk_free_per_period: str, periods_per_year: str,   # the run convention (D5)
    dataset_version_id, market_dataset_version_id,      # inherited pins, recorded for provenance
    result_hash,                           # canonical JSON over ordered (coordinate, backtest_id)
)
```

- `research_result_id` aliases the experiment result id (`sha256` over `experiment_id` +
  `experiment_engine_version_id` + `result_hash`), so it persists to the sidecar with no new
  store. The `strategy_version` §9 slot carries the experiment's identity contribution, exactly
  as `PanelResearchResult` maps its own id there.
- The result records **only child `backtest_id`s** — the children are already sealed in the
  same sidecar and read on demand by id.
- `from_dict` decodes it back fail-closed (`_req_str`/`_req_int` idioms from `factors/model.py`).

### 3.4 `BacktestComparison` / `ComparisonEntry`

```
ComparisonEntry(
    backtest_id: str,
    coordinate: tuple[tuple[str, str], ...] | None,   # set when sourced from an experiment
    statistic_value: str | None,                       # decimal string, or None if UNDEFINED
    rank: int | None,                                  # 1-based; None when excluded
)

BacktestComparison(  # implements ResearchRecord; mirrors UniverseComparison
    comparison_id, comparison_version_id,
    statistic_key: str,                    # a real PerformanceStatistics field
    order: str,                            # "descending" | "ascending" (no default guess)
    entries: tuple[ComparisonEntry, ...],  # sorted by rank then backtest_id
    excluded: tuple[tuple[str, str], ...], # (backtest_id, reason) for UNDEFINED members
    pin_mismatch: bool | None,             # None if <2 comparable; True iff pins disagree
    dataset_version_ids, market_dataset_version_ids,   # the distinct pins compared (sorted)
)
```

- Constructors: `of_results(results, *, statistic, order)`, `of_result_ids(ids, store, *,
  statistic, order)` (reads via `store.read_as(id, BacktestResult.from_dict)`), and
  `of_experiment(experiment_result, store, *, statistic, order)`.
- **`pin_mismatch`** is the exact analogue of `UniverseComparison.mode_mismatch`: `None` when
  fewer than two comparable members; otherwise `True` iff members do not all share the same
  `(dataset_version_id, market_dataset_version_id)`. It surfaces the difference loudly but does
  **not** block comparison.
- Ranking on a `statistic_key` that is `UNDEFINED` for a member **excludes** that member with a
  recorded reason — never a fabricated rank.
- Fail-closed on: a `statistic_key` that is not a real `PerformanceStatistics` field; an `order`
  other than `descending`/`ascending`; a member id absent from the sidecar; mixed
  `backtest_engine_version_id` across members (`ExperimentConsistencyError`).

---

## 4. Identity / determinism (locked)

- Domain tags via existing `quantforge.sec.artifacts.sha256_hex`, NUL (`\x00`) separated,
  canonical JSON (`sort_keys=True, ensure_ascii=False, separators=(",",":")`): `experiment/1`,
  `sweep-axis/1`, `experiment-engine/1`, `backtest-comparison/1`.
- `sweep_axis_id(parameter, sorted_canonical_values)` — set identity.
- `experiment_id(name, spec_version, base_request, sorted_axis_ids, risk_free_per_period,
  periods_per_year)`.
- `experiment_result_hash(ordered (coordinate, backtest_id) digests)`.
- `comparison_id(comparison_version, statistic_key, order, sorted_member_backtest_ids)`.
- Ranking is a total order: exact `Decimal` compare under the pinned prec-34 ROUND_HALF_EVEN
  context, tie-broken by `backtest_id`. No float, no wall-clock, no RNG, no input-order
  dependence in any identity.
- **D6 reuse:** because a child spec's `backtest_id` folds every result-changing input, two
  experiments sharing a child produce the same `backtest_id`; the engine reuses the sealed
  result via `store.has(id)` and never re-simulates. (Note: the child id folds `result_hash`,
  so it is only knowable *after* running; reuse is therefore keyed on the deterministically
  reproducible child spec producing an identical run whose sealed payload is a byte-identical
  write-once no-op.)

---

## 5. PIT semantics, provenance, storage (inherited)

- Phase 13 has **no `as_of` and performs no resolution.** Each child backtest is PIT-correct by
  BT-2; Phase 13 calls `run` unchanged. There is no REVISED backtest. The only PIT-adjacent risk
  — silently comparing incomparable runs — is mitigated by `pin_mismatch`.
- Provenance: `BacktestComparison` → member `backtest_id`s + compared pins + statistic/order;
  `ExperimentResult` → `experiment_id` + every child `backtest_id` + inherited pins + base
  request; each child → the full Phase 12 lineage down to raw source.
- Storage: zero new store types; write-once sidecar only; re-running an identical experiment is
  a byte-identical no-op write; a differing payload under an existing id fails closed via the
  store's `FactorConsistencyError` guard.

---

## 6. Failure / UNDEFINED behavior (locked)

**Raised** (`ExperimentConfigurationError` / `ExperimentConsistencyError`): axis parameter
outside the D7 vocabulary; empty `values`; duplicate value in an axis; wrong value type for a
parameter; two axes on the same parameter; a `base` that is not a fully pinned
`BacktestSpecification`; a comparison `statistic_key` that is not a real statistic field; an
`order` other than `descending`/`ascending`; a member `backtest_id` absent from the sidecar;
mixed engine versions across compared results.

**Recorded, never raised:** a member whose `statistic_key` is `UNDEFINED` → excluded with a
reason; members disagreeing on corpus pins → `pin_mismatch = True` (comparison proceeds); a
child that itself fails closed internally (BT-4) still seals a `BacktestResult` whose ledger
carries the record, and the experiment references its `backtest_id` normally. An experiment
where every child's statistic is `UNDEFINED` yields an all-excluded, empty ranking — surfaced
honestly, not an error.

---

## 7. Quality gates (locked)

- `uv run pytest` green (all phases; Phase 13 suite added).
- `uv run ruff check .` / `uv run ruff format --check .` clean; `uv run mypy src tests` clean.
- Zero runtime dependencies (stdlib only); no float in any numeric path; no wall-clock/RNG in
  any identity or derivation.
- No new store, no DB; only `<root>/research/` written.
- `BacktestResult` identity unchanged (byte-identical round-trip test proves `from_dict`
  introduces no drift).
- Docs updated; `ARCHITECTURE.md` "Reproducible Research" row flipped to ✅ only when green.
