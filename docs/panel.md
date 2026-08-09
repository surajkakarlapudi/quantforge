# Point-in-Time Fundamental Panel (Phase 10)

The panel layer evaluates **one Phase 7 metric over a time axis** and returns it
as a deterministic, fully provenanced result. It is the "panel / cross-sectional
research surface" that [ARCHITECTURE.md](../ARCHITECTURE.md) lists as planned and
that [docs/data-model.md](data-model.md) §9 anticipates via the `ResearchResult`
pins — realized one axis wider than the single-period Phase 7 metric.

Package: `src/quantforge/panel/`.

This layer is the **locked Phase 10 architecture**
([phase10-panel-locked.md](phase10-panel-locked.md), decisions D1–D7). It composes
existing layers and adds no new financial logic: every cell is resolved through the
Phase 7 [`MetricEngine`](metrics.md), the cross-sectional matrix reuses the Phase 8
[`Universe`](universe.md) / `FactorEngine`, and the optional provenance sidecar
reuses the Phase 8/9 `ResearchResult` store (D4). Section references below point
into the locked architecture unless stated otherwise.

> **A panel computes, it never interprets truth and never invents data.** Every
> `(period, as_of, member)` coordinate yields exactly one cell — `KNOWN` (value +
> provenance) or a first-class `UNDEFINED` carrying *why*. Missing periods and
> derivation failures are never dropped, imputed, carried-forward, or zeroed
> (Principle 8). It never crosses the PIT/REVISED boundary implicitly and never
> reads across knowledge states.

---

## 1. What a panel is

A panel is *one metric evaluated over a time axis*, in one of three shapes,
implemented as one model with the unused axis degenerate (§2):

- **Period-series** — one filer, many periods, one `as_of`. The basis for every
  multi-period derivation.
- **Vintage / knowledge-evolution** — one filer, one period, many `as_of`s.
  **PIT-only** (REVISED has no `as_of` axis — §4.1). Makes restatement effects
  first-class, auditable data.
- **Cross-sectional matrix** — many filers, many periods, one `as_of`. Reuses the
  Phase 8 `Universe` and `FactorEngine` per period; Phase 10 stacks the columns.
  **Engine-only** (it spans filers, so it is not on `Company`).

---

## 2. The period axis

The axis is **explicit and part of the request** — never "all periods that happen
to be ingested locally." Two forms, both versioned and content-addressed into
`axis_id`:

```python
from quantforge.panel import PeriodAxis
from quantforge.xbrl.contexts import PeriodType

axis = PeriodAxis.annual("2018-12-31", "2023-12-31", period_type=PeriodType.INSTANT)
axis = PeriodAxis.quarterly("2020-03-31", "2023-12-31", period_type=PeriodType.DURATION)
axis = PeriodAxis.of([period_a, period_b, ...])  # explicit ordered MetricPeriods
```

A generator is a **pure function of its declared params** — no wall-clock ("last 5
years" is forbidden), no locale, no ambient state. The axis carries dates and
`period_type` only; it **never infers fiscal-year / quarter labels** (D7). A
requested period the filer never reported becomes a first-class `UNDEFINED` cell,
never a silently missing column. Empty, duplicate, or malformed axes raise
`PanelConfigurationError`.

---

## 3. Multi-period derivations

Derivations (D3) are pure functions over the `KNOWN` cells of **one filer's**
series under the pinned Phase 7 decimal context, `UNDEFINED`-preserving:

| Derivation | Meaning | UNDEFINED when |
| --- | --- | --- |
| `growth()` | `(x_T - x_{T-1}) / x_{T-1}` | no prior; either endpoint UNDEFINED; zero prior → `DIVIDE_BY_ZERO` |
| `ttm()` | sum of 4 consecutive `DURATION` quarters | fewer than 4; any quarter UNDEFINED |
| `average_balance()` | `(x_T + x_{T-1}) / 2` | no prior; either endpoint UNDEFINED |
| `level_vs_history(window, stat)` | `x_T - stat(prior window)`, `stat ∈ {median, min, max}` | current UNDEFINED; empty KNOWN population |

Each derivation records **which input periods it consumed** and, when UNDEFINED,
**which input made it undefined**. `level_vs_history` computes its statistic over
the `KNOWN` cells of the window only — UNDEFINED cells are excluded from the
population, never imputed. A period-kind mismatch (e.g. `ttm` over an `INSTANT`
axis) is a configuration defect and raises `PanelConfigurationError`.

Look-ahead is impossible by construction: a derivation is a pure function of cells
that were **already `as_of`-eligible**, so it adds no data and no new boundary
(§7 of the locked spec). In the matrix, a derivation is applied **per filer** over
that filer's own series — never across filers.

---

## 4. PIT vs REVISED

Two methods, no default (invariant 27); two distinct result types (invariant 28,
D5). A `RevisedPanel` can **never** be passed where a `PitPanel` is required —
enforced at the type boundary, not by convention.

```python
from quantforge.panel import PanelEngine

engine = PanelEngine(workspace)  # additive Workspace wiring, lazy + cached

p = engine.panel_as_of("current_ratio", cik, axis, as_of)  # PitPanel (series)
v = engine.vintage_as_of("current_ratio", cik, period, as_ofs)  # PitPanel (vintage)
m = engine.panel_across("current_ratio", universe, axis, as_of)  # PitPanel (matrix)
r = engine.revised_panel("current_ratio", cik, axis)  # RevisedPanel
```

- PIT methods require a **timezone-aware** `as_of` / `as_of_axis`; a naive instant
  is rejected at the Phase 5 timestamp choke point (invariant 15).
- Every cell of a PIT period-series/matrix is resolved at the **same** `as_of`;
  every cell of a REVISED panel over the **same** pinned `DatasetVersion`. Never
  mixed within one panel.
- REVISED is reproducible, not wall-clock: resolved at the Phase 5 frontier over
  the pinned snapshot (invariants 21, 30).

### 4.1 REVISED has no vintage shape

The vintage panel is defined by its `as_of` axis; REVISED has no `as_of`. A
"revised vintage" is a category error → `PanelConfigurationError`, never a silent
empty panel. Crossing is explicit only:

```python
p = r.reinterpret_as_pit(engine, as_of)  # re-runs the whole panel; never a cast
```

---

## 5. Identity & reproducibility

All ids are `sha256:`-prefixed and NUL-joined (data-model §11):

```
axis_id             = sha256("period-axis" ∥ axis_kind ∥ period_keys | generator_params)
panel_definition_id = sha256(metric_key ∥ formula_id ∥ derivation_id ∥ axis_id ∥ shape)
panel_id            = sha256(panel_definition_id ∥ metric_engine_version_id
                            ∥ (universe_id | company_id) ∥ boundary_key ∥ result_hash)
```

Same panel definition + engine version + member(s) + boundary + underlying data ⇒
same `panel_id` and same values, on any machine, independent of execution order,
wall-clock, or cache state. The result maps directly onto the data-model §9
`ResearchResult` (`factor_definition_id ≡ panel_definition_id`, `factor_version ≡
metric_engine_version_id`); `strategy_version` is **absent**, reserved for the
deferred backtester.

Provenance is complete per cell: each `PanelCell.metric` carries the full Phase 7
`MetricProvenance` (concept → winning `fact_id` → Phase 4 `Fact` → SEC bytes,
availability policy, discarded candidates, boundary). The optional write-once,
content-addressed `ResearchResult` sidecar (D4) records the provenance record only
— never the values, never a DB, never in the repo.

---

## 6. Company convenience (D6)

`Company` gains thin, per-filer delegations to the engine. The cross-sectional
matrix stays engine-only (it spans filers):

```python
from quantforge import Company, PitPanel, RevisedPanel

apple = Company.resolve("AAPL")
p = apple.panel_as_of("current_ratio", axis, as_of)  # PitPanel
v = apple.vintage_as_of("current_ratio", period, as_ofs)  # PitPanel (vintage)
r = apple.revised_panel("current_ratio", axis)  # RevisedPanel
```

`filings()` / `facts()` / `metric_as_of` are unchanged. There is no default-mode
`panel()` accessor (invariant 27 at the front door).

---

## 7. What Phase 10 does NOT do

No return-based backtesting, portfolio construction, weighting, or trading
strategies (`strategy_version` stays unset); no market-data / price ingestion
(QuantForge stays SEC-only); no through-time normalization that crosses vintages;
no per-share / segment / multi-metric composite panels (one `metric_key` per
panel); no inferred fiscal labels; no DuckDB/Parquet materialization
(compute-on-demand, D2). See locked §10–§11 for how the deferred market-data layer
and backtester slot in without reopening Phase 10.
