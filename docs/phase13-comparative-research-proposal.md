# Phase 13 — Comparative Research: Experiment Sweeps & Backtest Comparison (DESIGN ONLY)

> **Status:** Proposal. No implementation code exists. This document is design-only and
> must be approved (see §22, *Decisions requiring approval*) before any source is written.
>
> **One-line thesis:** Phase 13 closes the loop from *one* reproducible backtest to
> *comparative, reproducible research* — a declarative **Experiment** (a content-addressed
> family of `BacktestSpecification`s produced by a parameter sweep) and a **BacktestComparison**
> (a deterministic, PIT-aware diff/ranking over sealed `BacktestResult`s) — reusing every
> existing store, identity, and PIT invariant and adding no new source, no database, and no
> runtime dependency.

---

## 0. How this proposal was produced

Per the directive, the entire current repository and architecture were inspected before
proposing anything. Phases 1–12 are treated as implemented and stable. Nothing below assumes
a capability that is not actually present. Concretely, the following were read in full or in
relevant part: `README.md`, `ARCHITECTURE.md`, `docs/index.md`, `docs/data-model.md`, the
Phase 5+ design/locked docs (`metrics.md`, `factors`, `phase9-research-layer.md`, `universe.md`,
`universe-construction.md`, `panel.md`, `phase10-panel-locked.md`, `phase11-market-data-locked.md`,
`phase12-backtesting-proposal.md`), the public APIs of Phases 7–12 (`metrics/`, `factors/`,
`universe/`, `panel/`, `market/`, `backtest/`), `src/quantforge/workspace.py`,
`src/quantforge/company.py`, `src/quantforge/__init__.py`, and the test suite conventions
across every completed phase (`tests/**`, especially `tests/backtest/`).

Key structural facts this design is built on (verified in-repo, not assumed):

- **The reuse seam exists.** `factors/store.py` defines a `@runtime_checkable ResearchRecord`
  Protocol (`research_result_id: str` + `to_dict() -> dict`) and a write-once, fail-closed,
  atomic `ResearchResultStore` (`<root>/research/sha256-<hex>.json`). Phase 8 `ResearchResult`,
  Phase 10 `PanelResearchResult`, and Phase 12 `BacktestResult` all implement it. `read_as(id, from_dict)`
  is a generic decode hook.
- **The comparison pattern exists.** `universe/analysis.py` `UniverseComparison` is the exact
  shape to mirror: a frozen, slotted, deterministic diff by canonical id with an explicit
  `mode_mismatch` guard that refuses to silently treat PIT and REVISED as equivalent (invariant 27).
- **A concrete gap exists.** `BacktestResult` has `to_dict()` but **no `from_dict`** — unlike
  `ResearchResult`/`PanelResearchResult`, it cannot yet be read back generically. Any layer that
  consumes *sealed* results by id must close this gap (see §7, §D3).
- **The spec is a declarative tree.** `backtest/spec.py` `StrategySpecification.rank_select_weight(...)`
  emits an ordered step tuple hashed into `strategy_version`. `BacktestSpecification` pins **both**
  corpora (`dataset_version_id` + `market_dataset_version_id`, BT-1) and folds every result-changing
  input into `backtest_id` (D6). `BacktestEngine.run(spec, *, risk_free_per_period="0", periods_per_year="1")`
  — the annualization convention is folded into `backtest_id` but **not** into `result_hash`.
- **The end goal is named.** `ARCHITECTURE.md`'s single remaining `🔜 Planned` row is
  **"Reproducible Research."** Phase 12's Q40 hand-off explicitly names three Phase 13 candidates:
  (a) research/reporting & comparison; (b) strategy-optimization/parameter-sweep; (c) Python-callback
  strategy escape hatch.

---

## 1. Problem being solved

A researcher can today run a single backtest and get a sealed, reproducible `BacktestResult`.
What they cannot do — and what real quantitative research requires — is answer the questions that
only exist *across* backtests:

1. **"Which parameterization is best, and is the difference real or noise?"** Sweep `top_n ∈ {1,5,10}`,
   costs ∈ {0, 10bps}, rebalance monthly vs quarterly — and rank the family by a chosen statistic.
2. **"Did these two runs differ because of the *strategy* or because of the *corpus*?"** Compare two
   `BacktestResult`s and attribute the difference to specific pinned inputs (strategy_version vs
   dataset pins vs cost model vs annualization).
3. **"Is this experiment reproducible and honest?"** Re-run the whole family on another machine and
   get identical ids; prove no run silently crossed the PIT/REVISED boundary or unpinned a corpus.

Today each of these requires ad-hoc caller glue: hand-building N specifications, calling `run` N times,
manually diffing `to_dict()` blobs, and hand-rolling the "are these even comparable?" safety checks —
exactly the error-prone, non-reproducible work the project exists to eliminate. There is no
content-addressed identity for "the experiment," so an experiment cannot itself be reproduced or cited.

**Phase 13 makes the experiment a first-class, content-addressed, fail-closed object**, and makes
comparison a deterministic engine operation rather than caller glue.

---

## 2. Why this is the correct next phase (and why not the others)

The directive forbids blindly taking the next numbered feature. Evaluating all three Q40 candidates
against the architecture:

| Candidate | Verdict | Reason |
|---|---|---|
| (c) Python-callback strategy escape hatch | **Reject** | Directly contradicts the invariant that makes `backtest_id` honest: a strategy is content-addressed by *what it declares* (`spec.py` §F), not by source bytes. A callback can only be identified by its source text or a pickle — fragile, non-portable, and it destroys D6 reproducibility. This is the *least* architecture-aligned option and would be a regression dressed as a feature. |
| (b) Parameter sweep alone | **Incomplete** | Generating a family of specs is thin without a way to interpret the family. A sweep that returns N unranked results is caller glue with a bow on it. |
| (a) Comparison/reporting alone | **Incomplete** | Comparing results is thin without a reproducible way to *generate* a comparable family. Comparing two hand-built specs is what a researcher already does badly by hand. |
| **(a)+(b) as one capability: Comparative Research** | **Select** | The sweep produces the family; the comparison interprets it. Together they are the single coherent capability that advances QuantForge toward its stated end goal, **"Reproducible Research."** Each half makes the other non-trivial. |

**Why now, specifically:** Phase 12 is the first layer that produces a sealed, comparable artifact
(`BacktestResult`). Before Phase 12 there was nothing to sweep or compare. Phase 13 is therefore the
*first* phase at which comparative research is even possible, and it is the direct on-ramp to the only
remaining architecture milestone. It is not a manufactured phase — it is the capability the stack has
been building toward.

**What it deliberately is not:** it is not multi-factor strategies or richer execution/cost models
(the README "Next" line). Those are *new strategy vocabulary* — a natural Phase 14 that Phase 13's
sweep machinery will immediately be able to explore. Phase 13 adds the research harness first, because
the harness is what turns new vocabulary into knowledge.

---

## 3. Contradiction analysis (against every listed invariant)

Each invariant is checked for whether Phase 13 preserves it. **No contradiction is introduced.** Where
a naïve design *would* contradict an invariant, the mitigation is stated.

| Invariant / property | Preserved? | How / mitigation |
|---|---|---|
| **Point-in-time semantics** | ✅ | Phase 13 never resolves data at a `T`. It orchestrates Phase 12 `run` calls (each of which is PIT-correct by BT-2) and reads *already-sealed* results. It has no `as_of` of its own and touches no resolver. |
| **PIT vs REVISED separation (inv. 27–30)** | ✅ | `BacktestResult` is a PIT-only artifact (BT-2). Phase 13 does not introduce a REVISED backtest. `BacktestComparison` carries a `boundary`/mode guard mirroring `UniverseComparison.mode_mismatch`: comparing results built under materially different corpus pins is surfaced, never silently averaged (see §9, §12). |
| **No look-ahead** | ✅ | Phase 13 adds no data resolution; look-ahead is impossible because it computes nothing at any `T`. A sweep dimension can only vary *declared* spec parameters, never inject future data. |
| **Deterministic / content-addressed identity** | ✅ | `Experiment` and `BacktestComparison` are content-addressed with fresh domain tags (`experiment/1`, `backtest-comparison/1`) over sorted, canonical-JSON payloads via `sha256_hex` + NUL separator — the identical discipline used by every prior phase. Sweep expansion is a pure, order-deterministic Cartesian product. |
| **Immutable source data** | ✅ | Phase 13 reads and writes only the `research/` sidecar. It never touches `sec/`, `market/`, `canonical/`, `registry/`, or `availability/`. It re-derives nothing from source. |
| **Fail-closed behavior** | ✅ | An unranked-by-`UNDEFINED`-statistic result, a comparison across mismatched corpus pins, a missing sealed result, a duplicate sweep point — each is either a first-class recorded outcome or a raised configuration/consistency error, never a guess. Ranking on a statistic that is `UNDEFINED` for a member excludes it and records why (mirrors BT-4 / factor cell semantics). |
| **Provenance** | ✅ | An `ExperimentResult` records the exact `backtest_id` of every child run and the `experiment_id` that generated them; a `BacktestComparison` records the input `backtest_id`s and the pins it compared. Full lineage: comparison → results → specs → corpora → facts → source. |
| **Zero runtime dependencies** | ✅ | Everything is stdlib: `Decimal`, `json`, `hashlib` (via existing `sha256_hex`). No ranking/stats library, no dataframe. |
| **No database requirement** | ✅ | Persistence is the existing write-once `ResearchResultStore` sidecar only. An `ExperimentResult` and `BacktestComparison` are themselves `ResearchRecord`s written to `research/sha256-<hex>.json`. No new store, no DB. |
| **Security / instrument identity** | ✅ | Phase 13 never constructs a `security_id` or `company_id`; it only reads them from sealed results/ledgers. |
| **Phase 9 Universe semantics** | ✅ | A sweep may vary the `UniverseSpecification`, but only by producing distinct specs whose `universe_id` differs honestly. No new universe abstraction. |
| **Phase 10 Panel semantics** | ✅ | Untouched. Phase 13 sits above Phase 12, not beside Phase 10. |
| **Phase 11 Market Data semantics** | ✅ | Untouched. Corpus pins are compared as opaque ids; no price is re-derived. |
| **Phase 12 Backtesting semantics (BT-1..BT-4, D6)** | ✅ | Phase 13 is a *pure consumer* of Phase 12. It calls `run` unchanged (BT-1 verification still fires per child), preserves BT-2/BT-3/BT-4 by not re-implementing the engine, and relies on D6: two identical child specs across two experiments yield the same `backtest_id`, so experiments share/reuse sealed results. |

**The one real architectural gap** (not an invariant contradiction, but a concrete blocker): `BacktestResult`
lacks `from_dict`, so a comparison layer cannot generically read sealed results back. §7 and decision **D3**
address this. It is additive (a new classmethod), touches no identity, and is the only change to existing
source Phase 13 requires.

---

## 4. Scope

**In scope:**

1. **`ExperimentSpecification`** — a declarative, content-addressed description of a parameter sweep over
   a *base* `BacktestSpecification`: an ordered set of named **axes**, each enumerating allowed values for
   one sweepable parameter, expanded into a deterministic family of concrete `BacktestSpecification`s.
2. **`ExperimentEngine`** (wired lazily on `Workspace`) — expands a spec into its family, runs each child
   through the existing `BacktestEngine.run` (reusing sealed results by `backtest_id` when already present),
   and seals an **`ExperimentResult`** (a `ResearchRecord`) recording every child `backtest_id` + the axis
   coordinate that produced it.
3. **`BacktestComparison`** — a frozen, deterministic diff/ranking over two-or-more sealed `BacktestResult`s
   (read by id from the sidecar), mirroring `UniverseComparison`: pairwise/statistic ranking, per-input
   attribution (which pinned component differs), and a `mode`/pin-mismatch guard. Itself a `ResearchRecord`.
4. **`BacktestResult.from_dict`** — the additive classmethod that makes sealed results readable (D3).
5. **Public exports** and `Workspace`/`Company` integration (§11).

**Sweepable axes in v1** (each is a *declared* parameter that already changes `backtest_id` honestly):
`select_n` (top_n k), `rank` (descending/ascending), `signal` (metric_key), `period` (MetricPeriod),
`cost_model` (proportional_bps / fixed_per_order), `schedule` (RebalanceSchedule), `initial_capital`,
`universe` (UniverseSpecification). Annualization (`periods_per_year`, `risk_free_per_period`) is a
run-time argument, not a spec field — see **D5** for how (and whether) it is sweepable.

---

## 5. Explicit non-goals

- **No Python-callback / arbitrary-code strategies** (rejected in §2; would break D6).
- **No new statistics** beyond what `PerformanceSummary` already exposes. Comparison ranks on *existing*
  statistics (cumulative return, Sharpe, max drawdown, turnover, …). Adding attribution/alpha-beta/IR is a
  separate, later concern (Phase 12 §35 deferral) and would require bumping `formula_version` — out of scope.
- **No optimizer.** Phase 13 *enumerates* a declared grid and *ranks* it. It does not do gradient descent,
  Bayesian optimization, or any search that would introduce nondeterminism or an objective-function callback.
  (A future optimizer would sit above this deterministic sweep.)
- **No new data source, no market/fundamentals re-derivation, no database, no runtime dependency.**
- **No REVISED backtest.** Phase 12 is PIT-only; Phase 13 does not add a revised simulation.
- **No plotting / rendering.** "Reporting" here means deterministic, serializable data structures
  (`to_dict`, `to_records`) — the same dependency-free export discipline as `UniverseSummary`. Charts are a
  downstream, non-core concern.
- **No cross-corpus averaging.** Results under different corpus pins are surfaced as mismatched, never
  blended into a single statistic.
- **No mutation of any existing store or prior artifact.**

---

## 6. Architecture

Phase 13 is a thin orchestration + analysis layer strictly *above* Phase 12, following the extension recipe
every phase uses (versioned immutable request object → fail-closed engine from `Workspace` via a lazy,
cycle-free `@property` → content-addressed identity with a fresh domain tag → data conditions as first-class
recorded values → compute-on-demand with the shared write-once sidecar).

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
     BacktestComparison.of_results([...], read via store.read_as(id, BacktestResult.from_dict))
                          |
                          v
             to_dict() / to_records()  (dependency-free export; itself a ResearchRecord)
```

**Module layout** (new package `src/quantforge/experiment/`, mirroring `universe/`, `panel/`, `backtest/`):

- `experiment/spec.py` — `ExperimentSpecification`, `SweepAxis`, the declarative vocabulary + validation.
- `experiment/engine.py` — `ExperimentEngine` (constructed from `Workspace`, composes `backtest_engine`).
- `experiment/result.py` — `ExperimentResult`, `ExperimentRun` (one child: coordinate + `backtest_id`).
- `experiment/analysis.py` — `BacktestComparison`, `ComparisonEntry`, ranking/attribution.
- `experiment/identity.py` — `experiment_id`, `sweep_axis_id`, `experiment_result_hash`, `comparison_id`
  (domain tags `experiment/1`, `sweep-axis/1`, `backtest-comparison/1`).
- `experiment/errors.py` — `ExperimentError` → `ExperimentConfigurationError`, `ExperimentConsistencyError`.

`BacktestResult.from_dict` is added to `backtest/result.py` (the only edit to existing source).

---

## 7. The `BacktestResult.from_dict` gap (concrete blocker)

`BacktestResult` implements `ResearchRecord` via `to_dict()` + `research_result_id` (= `backtest_id`), and
is written write-once to the sidecar today. But it has **no `from_dict`**, so `store.read_as(id, BacktestResult.from_dict)`
is impossible — a comparison layer cannot read a sealed result back into a typed object. Two options
(decision **D3**):

- **D3-A (recommended): add `BacktestResult.from_dict` (and `from_dict` on its nested value types —
  `PerformanceSummary`, `PerformanceStatistics`, `RebalanceRecord`, `Fill`, `AppliedAction`, `SignalRef`,
  `TargetWeights`).** This is additive, symmetric with `ResearchResult.from_dict`/`PanelResearchResult`, and
  makes sealed results first-class readable. It touches no identity (round-trip must be byte-stable: a
  `from_dict(to_dict(r))` reconstruction re-emits the same `to_dict()` and the same `result_hash`), and is
  covered by a `test_result_roundtrip_is_byte_identical` test.
- **D3-B: read raw dicts** via `store.read_as(id, lambda d: d)` and have `BacktestComparison` operate on
  dicts. Avoids editing Phase 12, but pushes untyped dict-spelunking into the comparison code and duplicates
  field knowledge. Rejected as the primary path; acceptable only if the user wants zero edits to Phase 12
  source in this phase.

**Recommendation:** D3-A. It is the honest, symmetric fix and the same pattern the other two `ResearchRecord`s
already follow.

---

## 8. Data model

All types are `@dataclass(frozen=True, slots=True)`, decimal-string-only for any numeric field, no float,
no wall-clock, no RNG — consistent with every prior phase.

### 8.1 `SweepAxis`

```
SweepAxis(
    parameter: str,                 # e.g. "select_n", "cost_model.proportional_bps", "signal"
    values: tuple[object, ...],     # ordered, deduped-by-canonical-form allowed values
)
```

- `parameter` is a member of a **closed v1 vocabulary** (§4). Anything outside it raises
  `ExperimentConfigurationError` (fail-closed — we refuse to sweep a parameter we cannot honestly fold into
  `backtest_id`).
- `values` is ordered and load-bearing for enumeration order, but the *identity* `sweep_axis_id` sorts the
  canonicalized values so that `{1,5}` and `{5,1}` yield the same axis id (an axis is a *set* of values; the
  family it generates is order-independent). Enumeration order for display is a separate, deterministic sort.
- Empty `values`, or a value whose type is wrong for the parameter (e.g. a non-`MetricPeriod` for `period`),
  raises at construction — the same `_req_str`/type-guard discipline as `spec.py`.

### 8.2 `ExperimentSpecification`

```
ExperimentSpecification(
    name: str,                              # non-empty
    base: BacktestSpecification,            # the spec every child starts from
    axes: tuple[SweepAxis, ...],            # >= 1 axis; distinct parameters (no axis collides)
    spec_version: str = "experiment/1",
)
```

- **Corpus pins are NOT sweepable in v1.** `base.dataset_version_id` and `base.market_dataset_version_id`
  are inherited unchanged by every child, so a whole experiment ranges over **one** pinned pair of corpora
  (decision **D2**). This is what makes the family *comparable*: differences are attributable to strategy
  parameters, not to a shifting corpus. (Comparing across corpora is what `BacktestComparison`'s mismatch
  guard is *for* — see §12 — but a single experiment does not straddle corpora.)
- Expansion is a pure Cartesian product across axes, applied to `base`: each coordinate is a mapping
  `{parameter: value}`; the child spec is `base` with those parameters substituted (via typed rebuild, e.g.
  a new `StrategySpecification.rank_select_weight(...)` or a new `CostModel(...)`), never a mutation.
- `expand() -> tuple[tuple[Coordinate, BacktestSpecification], ...]` is deterministic and total: the family
  size is `∏ len(axis.values)`; a coordinate producing an invalid spec (e.g. a `top_n:0`) is impossible
  because axis values are validated against the same rules `spec.py` enforces at construction.
- `experiment_id` folds `name`, `spec_version`, `base.backtest_id`-equivalent request identity, and every
  `sweep_axis_id` (sorted). Two experiments that declare the same base + same axes get the same id (D6-style).

### 8.3 `ExperimentRun` and `ExperimentResult`

```
ExperimentRun(coordinate: tuple[tuple[str, str], ...],   # sorted (parameter, canonical-value) pairs
              backtest_id: str)                            # the sealed child result's id

ExperimentResult(  # implements ResearchRecord
    experiment_id: str,
    experiment_version_id: str,      # sha256("experiment-engine/1")
    base_backtest_request: dict,     # base spec.to_dict() minus nothing; full reproducibility
    axis_ids: tuple[str, ...],       # sorted sweep_axis_ids
    runs: tuple[ExperimentRun, ...], # one per coordinate, ordered by canonical coordinate
    result_hash: str,                # canonical JSON over ordered (coordinate, backtest_id) digests
    dataset_version_id: str,         # inherited corpus pins (both), recorded for provenance
    market_dataset_version_id: str,
)
```

- `research_result_id` aliases a `experiment_result_id` (= `sha256` over `experiment_id` +
  `experiment_version_id` + `result_hash`), so it persists to the same sidecar with no new store.
- **`strategy_version` §9 slot:** like `PanelResearchResult`, the §9 record's `strategy_version` field is
  the *experiment's* identity contribution; `to_dict` maps it consistently with the existing schema. (This
  is confirmed against the data-model §9 mapping the factor/panel records already use.)
- The result records **only child `backtest_id`s**, not embedded child results — the children are already
  sealed in the same sidecar and read on demand by id (compute-on-demand; no duplication).

### 8.4 `BacktestComparison`

```
ComparisonEntry(
    backtest_id: str,
    coordinate: tuple[tuple[str, str], ...] | None,   # present when the comparison came from an experiment
    statistic_value: str | None,                       # decimal string, or None if UNDEFINED for this member
    rank: int | None,                                  # 1-based; None when statistic UNDEFINED (excluded)
)

BacktestComparison(  # implements ResearchRecord; mirrors UniverseComparison
    comparison_id: str,
    comparison_version_id: str,       # sha256("backtest-comparison/1")
    statistic_key: str,               # which PerformanceSummary statistic ranked (e.g. "sharpe")
    order: str,                        # "descending" | "ascending" (explicit, no default guess)
    entries: tuple[ComparisonEntry, ...],   # sorted by rank then backtest_id
    excluded: tuple[tuple[str, str], ...],  # (backtest_id, reason) for UNDEFINED-statistic members
    pin_mismatch: bool | None,        # None if <2 comparable; True iff members disagree on corpus pins
    strategy_diff: tuple[...],        # per-input attribution: which pinned component differs across members
)
```

- Constructed via `BacktestComparison.of_results(results)` (from already-read `BacktestResult`s) and
  `of_result_ids(ids, store)` (reads via `store.read_as(id, BacktestResult.from_dict)`), and a convenience
  `of_experiment(experiment_result, store, *, statistic, order)` that ranks a whole sealed experiment.
- **`pin_mismatch`** is the exact analogue of `UniverseComparison.mode_mismatch`: `None` when fewer than two
  comparable members; otherwise `True` iff members do not all share the same `dataset_version_id` +
  `market_dataset_version_id`. It does **not** block comparison (a researcher may legitimately want to see
  two runs on different corpora side by side) but it is surfaced loudly so the difference is never mistaken
  for a strategy effect.
- Ranking on a `statistic_key` that is `UNDEFINED` for a member (e.g. Sharpe when volatility is zero)
  **excludes** that member with a recorded reason — never fabricates a rank (fail-closed, mirrors factor cells).

---

## 9. Public API

```python
from quantforge import Workspace
from quantforge.experiment import (
    ExperimentSpecification,
    SweepAxis,
    ExperimentResult,
    BacktestComparison,
)
from quantforge.backtest.spec import BacktestSpecification, CostModel

ws = Workspace.open(root)

# 1. Declare a sweep over one pinned corpus pair.
exp = ExperimentSpecification(
    name="current-ratio-topn-costs",
    base=base_spec,  # a fully pinned BacktestSpecification
    axes=(
        SweepAxis("select_n", (1, 5, 10)),
        SweepAxis("cost_model.proportional_bps", ("0", "10")),
    ),
)

# 2. Run the family. Children already sealed (same backtest_id) are reused, not re-run.
result = ws.experiment_engine.run(
    exp, periods_per_year="12"
)  # -> ExperimentResult (sealed to sidecar)

# 3. Compare / rank the family by an existing statistic.
cmp = BacktestComparison.of_experiment(
    result,
    ws.research_result_store,
    statistic="sharpe",
    order="descending",
)
cmp.to_records()  # dependency-free tabular export (rank, coordinate, sharpe, backtest_id)
cmp.pin_mismatch  # None here (single-corpus experiment) — a cross-corpus compare would flag True

# 4. Ad-hoc comparison of two arbitrary sealed results by id.
cmp2 = BacktestComparison.of_result_ids(
    [id_a, id_b],
    ws.research_result_store,
    statistic="cumulative_return",
    order="descending",
)
```

`ExperimentEngine.run(spec, *, risk_free_per_period="0", periods_per_year="1") -> ExperimentResult`
mirrors `BacktestEngine.run`'s signature so the annualization convention threads through unchanged
(see **D5** for whether annualization is itself a sweep axis).

**Company façade:** `Company` stays thin (it owns no cross-sectional/portfolio logic today, and the matrix
is engine-only). Phase 13 adds **no** `Company` method — experiments and comparisons are inherently
multi-spec / cross-result and belong on the engine and the standalone comparison type, exactly as the
backtester and universe-matrix do (decision **D6**).

---

## 10. Identity / versioning

- New domain tags, all `sha256:`-prefixed, NUL-joined, via existing `sha256_hex`: `experiment/1`,
  `sweep-axis/1`, `experiment-engine/1`, `backtest-comparison/1`.
- `sweep_axis_id(parameter, sorted_canonical_values)` — a set identity (sorted), so axis-value order never
  changes the id.
- `experiment_id(name, spec_version, base_request_identity, sorted_axis_ids)`.
- `experiment_result_hash(ordered (coordinate, backtest_id) digests)` — canonical JSON, order by canonical
  coordinate; sensitive to every child id.
- `comparison_id(comparison_version, statistic_key, order, sorted_member_backtest_ids)` — a comparison's
  identity is the *set* of members + the ranking rule, so re-running the same comparison is reproducible.
- `experiment_version_id`/`comparison_version_id` fold `code_version` (and nothing wall-clock), exactly like
  `metric_engine_version_id`.
- **D6 leverage:** because a child spec's `backtest_id` folds every result-changing input, two experiments
  sharing a child produce the *same* `backtest_id`; the engine detects the sealed result and reuses it
  (`store.has(id)`), so overlapping experiments never re-simulate identical runs.

---

## 11. Workspace / Company integration

- **Workspace:** add one lazy, cached `@property experiment_engine -> object` (typed `object`, imported on
  first use to avoid an import cycle — the identical pattern as `backtest_engine`, `panel_engine`, etc.).
  It composes the existing `self.backtest_engine` and `self.research_result_store`; it constructs **no new
  store** and reads/writes only `<root>/research/`.
- **Company:** no change (see §9, D6).
- **`__init__.py`:** re-export the spec/result/comparison *value* types (`ExperimentSpecification`,
  `SweepAxis`, `ExperimentResult`, `BacktestComparison`) at top level, consistent with the pattern that
  spec/result types are exported but engines are reached via `Workspace`.

---

## 12. PIT semantics

Phase 13 has **no `as_of` and performs no resolution.** Its PIT correctness is entirely inherited:

- Each child backtest is PIT-correct by BT-2 (the engine binds each decision to a single `T` and reads only
  `Pit*` types); Phase 13 calls `run` unchanged.
- A sealed `BacktestResult` is a PIT artifact; there is no REVISED backtest to confuse it with (invariant 28
  holds vacuously — Phase 13 introduces no new REVISED result type).
- The **only** PIT-adjacent risk is *silently comparing incomparable runs*. Mitigated by `pin_mismatch`
  (§8.4), the direct analogue of `UniverseComparison.mode_mismatch` (invariant 27): the guard makes a
  corpus/pin difference impossible to overlook, so PIT and (differently-pinned) results are never treated as
  equivalent. Within a single `ExperimentSpecification`, corpus pins are fixed (D2), so an experiment's
  family is comparable by construction.

---

## 13. Provenance

Full downward lineage at every level:

- `BacktestComparison` → member `backtest_id`s (+ the pins it compared, + the statistic/order rule).
- `ExperimentResult` → `experiment_id` + every child `backtest_id` + the inherited corpus pins + the base
  request dict.
- Each child `backtest_id` → (Phase 12) `BacktestResult` → strategy/schedule/universe/cost/accounting ids +
  both corpus `DatasetVersion`s → (Phases 4/11) canonical facts + price observations → (Phase 1) raw source.

No provenance link is derived from wall-clock or order; everything is content-addressed.

---

## 14. Determinism

- Sweep expansion is a pure Cartesian product; enumeration order is a deterministic sort over canonicalized
  coordinates. No RNG, no wall-clock, no input-order dependence in identity.
- Ranking uses a total order: sort by the decimal statistic value (exact `Decimal` compare under the pinned
  context), tie-broken by `backtest_id`. Ties are therefore resolved deterministically, never by input order.
- All numeric fields are decimal strings; comparisons use `Decimal` under the existing prec-34,
  ROUND_HALF_EVEN context (no float ever enters a comparison).
- Same `ExperimentSpecification` + same corpus + same engine version ⇒ same `experiment_id`,
  same child `backtest_id`s, same `result_hash`, byte-identical sidecar payloads on any machine.

---

## 15. Failure / UNDEFINED behavior (fail-closed)

Consistent with the project-wide split (data conditions → first-class recorded values; configuration/
consistency defects → raised):

**Raised (`ExperimentConfigurationError` / `ExperimentConsistencyError`):**

- an axis parameter outside the closed v1 vocabulary;
- an axis with empty `values`, or a value of the wrong type for its parameter;
- two axes targeting the same parameter (ambiguous product);
- an `ExperimentSpecification` whose `base` is not a fully pinned `BacktestSpecification`;
- a `BacktestComparison` requested on a `statistic_key` that is not a real `PerformanceSummary` field;
- an `order` that is neither `"descending"` nor `"ascending"` (no default guess);
- a member `backtest_id` that is not present in the sidecar (`of_result_ids`);
- mixed engine versions across sealed results being compared (mirrors `_check_shared_version`).

**Recorded, never raised (first-class outcomes):**

- a child run whose `statistic_key` is `UNDEFINED` (e.g. Sharpe with zero volatility) → excluded from the
  ranking with a recorded reason (`excluded` tuple), never assigned a fabricated rank;
- a comparison whose members disagree on corpus pins → `pin_mismatch = True` (surfaced, comparison proceeds);
- a child backtest that itself fails closed internally (BT-4: missing tradable security, undefined signal)
  still produces a sealed `BacktestResult` — its ledger carries the fail-closed record, and the experiment
  records its `backtest_id` normally.

An experiment where *every* child's statistic is `UNDEFINED` produces an `ExperimentResult` with all runs
recorded and a comparison whose `entries` are all excluded — an empty ranking, surfaced honestly, not an error.

---

## 16. Storage implications

- **Zero new store types.** `ExperimentResult` and `BacktestComparison` are `ResearchRecord`s written
  write-once to the existing `<root>/research/sha256-<hex>.json` sidecar (atomic tmp+fsync+os.replace,
  `indent=2, sort_keys=True`), exactly like the Phase 8/10/12 records.
- Child `BacktestResult`s are already in the same sidecar (Phase 12); an experiment references them by id
  and never copies them.
- Re-running an identical experiment is a no-op write (byte-identical payload under the same id); a differing
  payload under an existing id fails closed (`FactorConsistencyError`, the store's existing guard).
- No DB, no Parquet/DuckDB materialization (compute-on-demand, consistent with every prior phase).

---

## 17. Interaction with Phases 1–12

- **Phases 1–5, 7–11:** untouched. Phase 13 re-derives nothing from source, resolves nothing at a `T`, and
  reads no fundamentals/market data directly.
- **Phase 9 (Universe):** a sweep axis may vary the `UniverseSpecification`; each variant's `universe_id`
  differs honestly. No new universe abstraction; `UniverseComparison` is the *pattern* Phase 13 mirrors, not
  a dependency it modifies.
- **Phase 12 (Backtest):** the sole functional dependency. Phase 13 calls `BacktestEngine.run` unchanged
  (all of BT-1..BT-4 + D6 fire per child), reuses `BacktestResult`, and — with **D3-A** — adds one additive
  classmethod (`from_dict`) so sealed results are readable. No Phase 12 semantics change.

---

## 18. Implementation plan (post-approval; not executed in this turn)

1. **`backtest/result.py`:** add `from_dict` to `BacktestResult` and its nested value types (D3-A); add a
   byte-identical round-trip test (`from_dict(to_dict(r))` re-emits identical `to_dict()` and `result_hash`).
2. **`experiment/errors.py`:** the error hierarchy.
3. **`experiment/identity.py`:** the four id builders + two version ids, with the fresh domain tags.
4. **`experiment/spec.py`:** `SweepAxis`, `ExperimentSpecification`, the closed parameter vocabulary, typed
   substitution/`expand()`, full construction-time validation.
5. **`experiment/result.py`:** `ExperimentRun`, `ExperimentResult` (ResearchRecord + `from_dict`).
6. **`experiment/engine.py`:** `ExperimentEngine` from `Workspace`; expand → run/reuse-by-id → seal.
7. **`experiment/analysis.py`:** `BacktestComparison` + `ComparisonEntry`, ranking, attribution, guards.
8. **`workspace.py`:** the lazy `experiment_engine` property.
9. **`__init__.py`:** top-level re-exports.
10. **`tests/experiment/`:** `builders.py` reusing `tests/backtest/builders.py`; test classes per §19.
11. **Docs:** `docs/experiment.md` (or a `phase13-...-locked.md`), plus `README.md`, `ARCHITECTURE.md`
    ("Reproducible Research" row → ✅), `docs/index.md` (and fix the stale "No financial functionality is
    implemented yet" line while there).

---

## 19. Testing strategy

Following the surveyed conventions (per-phase `builders.py`, no `conftest.py`, fictional identities, fixed
timestamps, `TestNoLookAhead` / `TestFailClosed` / `TestIdentitySensitivity` groupings, `test_*_is_deterministic`,
`test_*_id_is_order/membership_sensitive`):

- **`tests/experiment/builders.py`** reuses `tests/backtest/builders.py::populate` to seed one combined
  corpus and build a base spec, then assembles `ExperimentSpecification`s.
- **`TestExpansion`** — Cartesian product size, deterministic enumeration order, typed substitution correctness.
- **`TestDeterminism`** — same spec ⇒ same `experiment_id`, same child `backtest_id`s, same `result_hash`,
  byte-identical sidecar payload; child reuse-by-id (no re-simulation) verified via a run counter.
- **`TestIdentitySensitivity`** — each axis, the base spec, and the statistic/order each change the id;
  axis-value *order* does **not** change `sweep_axis_id`; annualization sensitivity per D5.
- **`TestRanking`** — correct total order + deterministic tie-break by `backtest_id`; `UNDEFINED`-statistic
  member excluded with reason, never ranked.
- **`TestPinMismatch`** — `pin_mismatch` is `None` for a single-corpus experiment, `True` for a cross-corpus
  ad-hoc comparison (built by pointing two `populate`d roots' results at one comparison).
- **`TestFailClosed`** — bad axis parameter, empty values, duplicate-parameter axes, unpinned base, bad
  statistic key, missing member id, mixed engine versions — each raises the right error.
- **`TestRoundTrip`** — `BacktestResult.from_dict(to_dict(r))` is byte-identical (guards D3-A against identity
  drift); `ExperimentResult` / `BacktestComparison` round-trip through the sidecar.
- **`TestAdditiveWiring`** — `Workspace.experiment_engine` composes existing engines, creates no new store,
  and touches only `<root>/research/`.

---

## 20. Quality gates

- `uv run pytest` green (all phases; Phase 13 suite added).
- `uv run ruff check` / format clean; `uv run` type-checking clean.
- Zero runtime dependencies (stdlib only); no float in any numeric path; no wall-clock/RNG in any identity
  or derivation.
- No new store, no DB; only `<root>/research/` written.
- `BacktestResult` identity unchanged (round-trip test proves `from_dict` introduces no drift).
- Docs updated; ARCHITECTURE "Reproducible Research" row flipped to ✅ only when the suite is green.

---

## 21. Future-phase handoff

- **Phase 14 (natural next):** richer strategy vocabulary — multi-factor signals, filters/multi-step
  strategies, non-equal weighting, richer execution/cost models (the README "Next" line). Every new
  *declared* parameter becomes immediately sweepable by Phase 13 with no change to the experiment layer.
- **Optimizer (later):** a deterministic-search or objective-driven layer *above* Phase 13's enumerated grid,
  reusing `ExperimentResult` + `BacktestComparison` as its evaluation substrate.
- **Expanded statistics (Phase 12 §35 deferral):** attribution, alpha/beta, information ratio, bootstrapped
  intervals — a `PerformanceSummary` `formula_version` bump; `BacktestComparison` will rank on them the day
  they exist, with no comparison-layer change.
- **Reporting/rendering:** charts/notebooks are a downstream, non-core concern consuming `to_records()`;
  deliberately out of the deterministic core.

---

## 22. Decision table — decisions requiring your approval before implementation

The following are the decisions where I have made a recommendation but require your explicit approval before
any code is written. **Per the directive, I have written no implementation code, modified no source files,
and committed/pushed nothing. I am stopping here.**

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | **Is Phase 13 "Comparative Research" (sweep + comparison), or a different capability?** | (a) Comparative Research [this proposal]; (b) sweep-only; (c) comparison-only; (d) Python-callback strategies; (e) jump to richer strategy vocabulary (README "Next") | **(a)** — the only option that is non-trivial on both halves and advances the stated "Reproducible Research" end goal; (d) is rejected as it breaks D6. |
| **D2** | **Are corpus pins sweepable within one `ExperimentSpecification`?** | (a) No — one experiment = one pinned corpus pair, children differ only in strategy params; (b) Yes — allow sweeping `dataset_version_id` / `market_dataset_version_id` | **(a)** — keeps a family comparable by construction; cross-corpus comparison is handled by `BacktestComparison.pin_mismatch`, not by mixing corpora inside one experiment. |
| **D3** | **How are sealed `BacktestResult`s read back?** | (a) Add `BacktestResult.from_dict` (+ nested types) [additive edit to Phase 12]; (b) read raw dicts, comparison operates untyped | **(a)** — symmetric with the other two `ResearchRecord`s, guarded by a byte-identical round-trip test; the only edit to existing source. |
| **D4** | **Persistence of `ExperimentResult` / `BacktestComparison`?** | (a) Reuse the existing `ResearchResultStore` sidecar (both are `ResearchRecord`s); (b) a new store type | **(a)** — no new store, no DB; consistent with Phases 8/10/12. |
| **D5** | **Is annualization (`periods_per_year`, `risk_free_per_period`) a sweep axis?** | (a) No — it is a run-arg threaded to every child unchanged (one convention per experiment); (b) Yes — allow sweeping it as an axis | **(a)** — annualization changes `backtest_id` + Sharpe but **not** `result_hash` (verified in Phase 12); making it an axis would produce children with identical `result_hash` but different ids, which is confusing. Keep it a single per-experiment convention; a researcher who wants two annualizations runs two experiments. |
| **D6** | **Does `Company` gain any Phase 13 method?** | (a) No — experiments/comparisons are engine-/standalone-only, `Company` stays thin; (b) add a convenience accessor | **(a)** — consistent with the backtester and universe-matrix staying off the thin façade. |
| **D7** | **v1 sweepable-parameter vocabulary** (§4) | The closed set: `select_n`, `rank`, `signal`, `period`, `cost_model.*`, `schedule`, `initial_capital`, `universe` | Confirm the set. Anything outside it fails closed until explicitly added (a new value hashes distinctly — never an edit). |
| **D8** | **Doc artifact:** proposal-only now, or also a `-locked` normative doc when implemented? | (a) `docs/experiment.md` + flip ARCHITECTURE row on green; (b) also author `phase13-...-locked.md` like Phases 10/11 | **(b)** — match the Phase 10/11 precedent of a locked normative spec once the suite is green. |

**Nothing proceeds to implementation until you approve D1–D8 (or amend them).**
