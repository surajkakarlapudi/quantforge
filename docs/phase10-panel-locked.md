# Phase 10 — Point-in-Time Fundamental Panel (LOCKED architecture)

> **Status: LOCKED, implemented.** The Phase 10 proposal
> ([phase10-panel-proposal.md](phase10-panel-proposal.md)) was approved in
> principle and decisions D1–D7 are settled (§1). This document is the normative
> locked architecture; the implementation lives in `src/quantforge/panel/` and is
> documented for readers in [panel.md](panel.md). Changes to the panel data model,
> PIT/REVISED behavior, period-axis semantics, identity rules, or the D5/D7 locks
> require updating this document first.

---

## 1. Decisions D1–D7 — final choices

| # | Decision | Final choice | Status |
| --- | --- | --- | --- |
| **D1** | Scope | Build the **PIT fundamental panel** (time axis over Phase 7 metrics). Do **not** build a return-based backtester — it is blocked on absent price data. | LOCKED (reversible sequencing) |
| **D2** | Panel values | **Compute-on-demand** (mirrors Phase 7 D1 / Phase 8 F2). No cached arithmetic; reproducibility from the pins. | LOCKED (reversible) |
| **D3** | Multi-period derivations | **Included** — `growth`, `ttm`, `average_balance`, `level_vs_history`, pure over KNOWN cells of one series, `UNDEFINED`-preserving, pinned decimal context. | LOCKED (set extensible; each semantics immutable) |
| **D4** | `ResearchResult` sidecar | **Reuse Phase 8's**, provenance-only, write-once, content-addressed, optional. | LOCKED (reversible) |
| **D5** | Panel result types | **Distinct `PitPanel` / `RevisedPanel`** (see §1.1 explicit lock). | LOCKED — architectural commitment |
| **D6** | `Company` convenience | Thin `Company.panel_as_of(...)` + REVISED/vintage siblings delegating to `PanelEngine`; the cross-sectional matrix stays engine-only. | LOCKED (reversible/additive) |
| **D7** | Period-axis model | Explicit list **or** deterministic generator, versioned/content-addressed into panel identity (see §1.2 explicit lock + vocabulary). | LOCKED — identity is a commitment; vocabulary extensible |

### 1.1 D5 — explicit lock (as approved)

- Use **distinct `PitPanel` and `RevisedPanel` types**.
- Preserve the existing PIT/REVISED type separation used by `PitValue`/
  `RevisedValue` (Phase 5) and the Phase 8 factor layer (`PitFactor`/
  `RevisedFactor`).
- A `RevisedPanel` **must never** be accepted where a `PitPanel` is required —
  enforced at the type boundary, not by convention (invariant 28).
- Any revised → PIT conversion must **explicitly re-resolve at the requested
  `as_of`** (`RevisedPanel.reinterpret_as_pit(engine, as_of)` re-runs the whole
  panel; it never rescales or reuses revised cells).

### 1.2 D7 — explicit lock (as approved)

Initial period-axis vocabulary:

- **Annual** periods.
- **Quarterly** periods.
- **Explicit `period_start` and `period_end`** dates.
- **Explicit `period_type`** (`INSTANT` / `DURATION`).
- **No inferred fiscal-year / fiscal-quarter labels** — the axis carries dates and
  type only; it never guesses a fiscal calendar or a "FY2023 Q3" label.
- The period-axis specification is **versioned / content-addressed** and included
  in panel identity (`axis_id` → `panel_definition_id` → `panel_id`).
- The vocabulary is **extensible in future versions without changing the meaning
  of an existing panel ID**: a new axis kind hashes distinctly and never alters
  the hash of an already-defined axis (a new axis kind is a new version, never an
  edit — invariant-14 analogue).

---

## 2. Final panel data model

A **panel** is *one metric evaluated over a time axis*, in one of three shapes,
implemented as one model with the unused axis degenerate.

**Shapes.**
- **4.1 Period-series** — one filer, many periods, one `as_of` (or one snapshot).
  The basis for every multi-period derivation.
- **4.2 Vintage / knowledge-evolution** — one filer, one period, many `as_of`s.
  **PIT-only** (REVISED has no `as_of` axis — §3.1). Makes restatement/vintage
  effects first-class, auditable data.
- **4.3 Cross-sectional matrix** — many filers, many periods, one `as_of`. Reuses
  the Phase 8 `Universe` and `FactorEngine` per period; Phase 10 stacks columns.
  **Engine-only** entry (D6).

**`PanelCell`** — one `(period, as_of, member)` coordinate's contribution:

| Field | Meaning |
| --- | --- |
| `company_id` | Universe/filer member (canonical `cik:`-form). |
| `period` | The `MetricPeriod` for this coordinate. |
| `as_of` | The PIT instant for this coordinate (vintage axis); one shared value for shapes 4.1/4.3. |
| `metric` | The full `PitMetricValue` / `RevisedMetricValue` — `KNOWN` (value + provenance) or `UNDEFINED` (reason + provenance). **Never `None`, never dropped.** |
| `derived_value_numeric_str` | The multi-period derivation output for this coordinate (D3), exact `Decimal` serialized; `None` when the cell/derivation is `UNDEFINED` or no derivation applied. |

**`PitPanel` / `RevisedPanel`** — frozen, slotted dataclasses sharing:

| Field | Meaning |
| --- | --- |
| `panel_id` | Deterministic identity of the whole request + output (§5). |
| `panel_definition_id` | Content hash of metric + formula + derivation + axis + shape. |
| `metric_key`, `formula_id`, `metric_engine_version_id` | The Phase 7 pins (identical for every cell). |
| `axis_id` | Content hash of the period axis (§4). |
| `derivation` | Applied derivation id, or `"none"`. |
| `shape` | `period_series` \| `vintage` \| `cross_section`. |
| `cells` | Ordered tuple of `PanelCell`, one per coordinate, in axis order. |
| `summary` | `PanelStatus`: counts of `KNOWN` vs each `UndefinedReason`. |
| `research_result` | The `ResearchResult` provenance record (§6). |

Distinguishing field: `PitPanel.as_of` (period-series/matrix) or `PitPanel.as_of_axis`
(vintage) — timezone-aware; `RevisedPanel.dataset_version_id` — the pinned snapshot.

**Cell ordering:** by `(period_end, period_type, period_start)` then, for the
matrix, by `company_id`; for the vintage panel, by `as_of` ascending. Ties are
fully resolved by this total order — no set-iteration dependence.

---

## 3. PIT vs REVISED behavior

- **Two methods, no default (invariant 27).** `panel_as_of` / `vintage_as_of` /
  `panel_across` (PIT) require a timezone-aware `as_of`/`as_of_axis` (a naive
  instant is rejected by the Phase 5 timestamp choke point); `revised_panel`
  (REVISED) requires a `DatasetVersion`.
- **Two result types (invariant 28, D5).** `PitPanel` ≠ `RevisedPanel`; a
  `RevisedPanel` can never be passed where a `PitPanel` is required.
- **One shared boundary.** Every cell of a PIT period-series/matrix is resolved at
  the **same** `as_of`; every cell of a REVISED panel over the **same**
  universe-wide `DatasetVersion` (built via the Phase 8 §8.1 union when the panel
  spans filers). Never mixed within one panel.
- **Past-closed & monotonic (invariant 29), inherited per cell.** As `as_of`
  advances, cells go `UNDEFINED → KNOWN` (or a value changes when a restatement
  becomes public). The vintage panel makes this evolution its content.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** Resolved at the
  Phase 5 frontier over the pinned snapshot.
- **Explicit crossing only.** `RevisedPanel.reinterpret_as_pit(engine, as_of)`
  re-runs the whole panel at `as_of`; never an implicit cast (§1.1).

### 3.1 REVISED has no vintage shape

The vintage panel is defined by its `as_of` axis. REVISED has no `as_of` (it is
the single limit as `T → now`). A "revised vintage" is a category error →
`PanelConfigurationError`, never a silent empty panel. REVISED supports only the
period-series (4.1) and cross-sectional (4.3) shapes.

---

## 4. Period-axis semantics

- The axis is **explicit and part of the request** (mirrors Phase 8 F1) — never
  "all periods that happen to be ingested locally."
- Two forms, both hashed into `axis_id`:
  1. **Explicit ordered list** of `MetricPeriod` (each carrying explicit
     `period_type`, `period_start`, `period_end`).
  2. **Deterministic generator** — frequency (`annual` | `quarterly`) + inclusive
     date bounds + explicit `period_type`. A **pure function of its declared
     params** — no wall-clock ("last 5 years" is forbidden), no locale, no ambient
     state.
- **No inferred fiscal labels** (D7): the axis is dates + type only.
- A requested period the filer never reported → a first-class `UNDEFINED` cell,
  never a silently missing column.
- The axis kind and its params are versioned; a future axis kind hashes distinctly
  and leaves existing `panel_id`s unchanged (D7 extensibility lock).

---

## 5. Panel identity / reproducibility rules

All ids `sha256:`-prefixed, NUL-joined, per data-model §11 conventions.

```
axis_id             = sha256( "period-axis" ∥ axis_kind ∥ ordered period_keys | generator_params )
panel_definition_id = sha256( metric_key ∥ formula_id ∥ derivation_id ∥ axis_id ∥ shape )
panel_id            = sha256( panel_definition_id ∥ metric_engine_version_id
                             ∥ (universe_id | company_id) ∥ boundary_key ∥ result_hash )
boundary_key        = "pit:"          + as_of_utc                 (period-series / matrix)
                    | "pit-vintage:"  + sorted as_of_utc list     (vintage)
                    | "rev:"          + dataset_version_id        (REVISED)
result_hash         = sha256( canonical JSON of the ordered cell values + statuses )
```

Guarantee: **same panel definition + same engine version + same member(s) + same
boundary + same underlying data ⇒ same `panel_id` and same values**, on any
machine, independent of execution order, wall-clock, or cache state. No RNG, no
wall-clock reads; ordering is the total order in §2; hashing is canonical JSON
with sorted keys. Maps directly onto data-model §9 `ResearchResult`
(`factor_definition_id ≡ panel_definition_id`, `factor_version ≡
metric_engine_version_id`, `dataset_version_id`, `as_of_timestamp`, `query_params
= {metric_key, axis, derivation, shape, member(s)}`, `result_hash`);
`strategy_version` **absent** — reserved for the deferred backtester.

---

## 6. Provenance rules

- Every panel carries a `ResearchResult` (the §9 record) and a `PanelStatus`
  summary (per-reason cell counts).
- Every `PanelCell.metric` is a complete Phase 7 `MetricProvenance`: selected
  concept, winning `fact_id` → Phase 4 `Fact` → `FactProvenance` → SEC bytes,
  availability policy, discarded candidates, and the boundary.
- Each multi-period derivation records **which input periods it consumed** and, for
  an `UNDEFINED` derivation, **which input made it undefined and why**.
- **Zero information loss:** no coordinate is omitted; an `UNDEFINED` cell records
  its `UndefinedReason`; the axis is reconstructable from `axis_id`.
- Optional write-once, content-addressed `ResearchResult` sidecar (D4) records the
  provenance record only — never the values, never a DB, never in the repo.

---

## 7. Look-ahead prevention

- **PIT panel is point-in-time cell by cell.** Every cell — including the
  historical periods a `growth`/`ttm`/`average_balance` derivation consumes — is
  resolved by the Phase 5 resolver at the panel's single `as_of`. A derivation is
  a **pure function of cells that were already `as_of`-eligible**, so it adds no
  data and no new boundary and **cannot introduce look-ahead** (same argument as
  Phase 8 §1.4 for cross-sectional transforms). Invariant 29 holds: the whole
  column is a function of `≤ as_of` observations.
- **No cross-boundary derivation.** A derivation only ever combines cells of the
  **same** panel (same `as_of`/snapshot). It can never reach across the vintage
  axis to mix knowledge states.
- **Vintage panel** columns are independent `PIT(as_of_i)` evaluations; each is
  closed under `≤ as_of_i`; no column reads another.
- **Type-level enforcement (D5).** A future backtester typed to `PitPanel` cannot
  be handed a `RevisedPanel`; revised → PIT must re-resolve explicitly.
- **Naive `as_of` rejected** at the Phase 5 choke point (invariant 15).

---

## 8. Undefined / missing-cell behavior

- **Every coordinate yields exactly one cell** — never dropped, never reordered by
  value.
- A filer/period with no PIT-eligible fact at the boundary → `UNDEFINED`
  (`MISSING_INPUT`), recorded with reason, not omitted.
- **Derivations are `UNDEFINED`-preserving:** any `UNDEFINED` input period makes
  the derivation `UNDEFINED` (a growth rate needs both endpoints; TTM needs four
  consecutive quarters). Never imputed, never carried-forward, never `0`
  (Principle 8).
- **Divide-by-zero** in a derivation (e.g. `growth` with a zero prior value) →
  `UNDEFINED(DIVIDE_BY_ZERO)`, never `Inf`/`NaN` (exact `Decimal == 0`).
- **Population = KNOWN cells only** for any statistic (`level_vs_history`);
  `UNDEFINED` cells are excluded from the population and stay `UNDEFINED`.
- **Fail-closed defects raise:** empty/duplicate axis, malformed generator, a
  period-kind mismatch for a derivation, a "revised vintage", or a mixed engine
  version across cells → `PanelConfigurationError`. Data conditions are cells;
  configuration defects are exceptions.

---

## 9. Public API

```python
# Engine (all shapes):
engine = PanelEngine(workspace)  # additive Workspace wiring, lazy + cached
axis = PeriodAxis.annual(
    "2018-12-31", "2023-12-31", period_type=INSTANT
)  # or .quarterly / .of([...])

p = engine.panel_as_of(
    "current_ratio", cik, axis, as_of
)  # → PitPanel   (period-series)
v = engine.vintage_as_of(
    "current_ratio", cik, period, as_of_axis
)  # → PitPanel   (vintage, PIT-only)
m = engine.panel_across(
    "current_ratio", universe, axis, as_of
)  # → PitPanel   (matrix; reuses Phase 8 Universe)
r = engine.revised_panel("current_ratio", cik, axis, dataset_version)  # → RevisedPanel

# Company convenience (D6) — per-filer shapes only, thin delegation:
p = company.panel_as_of("current_ratio", axis, as_of)  # → PitPanel

# Explicit crossing (never implicit):
p = r.reinterpret_as_pit(engine, as_of)  # re-resolves the whole panel
```

Curated top-level exports (PIT/REVISED distinction visible at the import site):

```python
from quantforge import PitPanel, RevisedPanel
from quantforge.panel import PanelEngine, PeriodAxis
```

No default-mode `panel()` accessor (invariant 27 at the front door). The
cross-sectional matrix is engine-only (it spans filers). `Company` stays a thin
façade; `filings()`/`facts()`/`metric_as_of` are unchanged.

---

## 10. What Phase 10 explicitly does NOT do

- **No return-based backtesting, portfolio construction, weighting, trading
  strategies, or investment recommendations.** `strategy_version` stays unset.
- **No market-data / price ingestion.** QuantForge stays SEC-only; performance
  backtesting remains blocked on absent price data by design.
- **No factor-persistence / turnover *analytics*** — Phase 10 delivers the matrix
  panel those would consume, not the analytic itself.
- **No through-time normalization that crosses vintages** (e.g. z-score against
  one's own *revised* history) — would mix knowledge states.
- **No per-share / segment / multi-metric composite panels** — inherits Phase 7/8
  deferrals (no security master; consolidated-only; one `metric_key` per panel).
- **No inferred fiscal-year/quarter labels** (D7).
- **No DuckDB/Parquet materialization** — compute-on-demand (D2); data-model §10
  storage remains a separate future decision.

---

## 11. Room for a future market-data layer and backtester

The design is deliberately shaped so the deferred phases slot in without reopening
Phase 10:

- **`strategy_version` is reserved, not used.** The `ResearchResult` mapping
  already leaves the field for the backtester (data-model §9), so a strategy layer
  cites the panels it consumed without a schema change.
- **`PitPanel` is the typed hand-off.** Because backtests/factors accept only PIT
  (§KS.5) and D5 makes that a type, a future backtester's signature consumes
  `PitPanel` and structurally refuses revised history — the safety boundary is
  already built.
- **The period axis is a rebalance schedule.** A backtester's rebalance dates map
  directly onto a declared `PeriodAxis`; no new time model is needed.
- **A market-data layer plugs in beneath, not through, Phase 10.** When prices
  arrive they become a *new source* with their **own** PIT-availability model
  (their own `AvailabilityPolicy`, their own `DatasetVersion` contribution) — the
  same immutable-raw → derived → PIT pipeline every existing phase uses. Panels
  and factors then compose price-derived metrics identically to filing-derived
  ones; nothing in Phase 10 assumes SEC-only *at the panel layer*, only that
  today's registry happens to be SEC-only.
- **Compute-on-demand leaves caching open.** If a backtester needs speed, a
  transparent cache keyed by `panel_id` can be added later precisely because
  values are pure functions of the pins (D2).

---

*This document is the locked Phase 10 architecture. The implementation satisfies
the determinism, fail-closed, immutability, provenance, and PIT/REVISED invariants
of data-model §12 (esp. 5, 18, 21, 27–30) and realizes the reserved §9
`ResearchResult` one axis wider.*
