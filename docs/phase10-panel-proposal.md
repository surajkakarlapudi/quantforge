# Phase 10 — Point-in-Time Fundamental Panel (design proposal)

> **Status: PROPOSAL ONLY.** This document proposes the next layer, performs the
> mandated contradiction analysis first, and specifies a design. **No
> implementation code is written and nothing is committed** until the §11
> decisions are approved. It follows the same discipline as the Phase 7/8
> proposals (contradiction analysis → principles → model → identity/versioning →
> PIT/REVISED → determinism → deferred scope → decisions).

---

## 0. What this layer is, in one sentence

Phase 10 adds the **time axis** to QuantForge's research primitives: *one metric,
for one filer (or an explicit universe), evaluated across many fiscal periods
and/or many point-in-time `as_of` instants* — a deterministic, fail-closed,
fully-provenanced **panel** — and the small set of **multi-period derivations**
(growth, trailing-twelve-month, average-balance, level-vs-history) that Phases 7
and 8 explicitly deferred because they require more than one period.

It is the missing third axis. The existing primitives cover two:

```
Phase 7 metric     one metric · one filer   · one period · one boundary → scalar
Phase 8 factor     one metric · many filers · one period · one boundary → cross-section (vector)
Phase 10 panel     one metric · filer(s)    · MANY periods / MANY as_of  → time series / panel (matrix)
```

---

## 1. Contradiction analysis

The mandated first step: the proposed work was checked against every prior
invariant, principle, and phase design **before** any design was written. **No
hard contradiction exists** for the layer proposed. One candidate next layer —
the literal next box in `ARCHITECTURE.md`, *Backtesting* — **is** blocked, and
§1.1 explains why and why the panel is proposed instead. The remaining tensions
each resolve under an explicit rule rather than requiring a change to a prior
layer. Had any been a true contradiction, this section would say STOP and stop.

### 1.1 The literal next box is *Backtesting* — and it is blocked on absent price data (the load-bearing finding)

`ARCHITECTURE.md`'s data flow is `… → Point-in-Time → Factors → **Backtesting** →
Reproducible Research`, and `README.md` now lists *Next = "Portfolio /
backtesting infrastructure"*. So the obvious Phase 10 is a backtester.

**It cannot be built honestly today, and this is the most important contradiction
to surface.** A backtest in the conventional sense measures a strategy's realized
**return** over time: it needs, at each rebalance date, a forward price change per
holding. QuantForge **has no prices and no market data by deliberate design**:

- Every metric is derived **only** from SEC filings, which carry **no share
  prices** (`universe-construction.md` §2, `phase9-research-layer.md` scope: "no
  price feeds, market-data ingestion"). There is deliberately **no `market_cap`
  formula** in the registry (`metrics.md` §6.5).
- Engineering Principle 8 forbids fabricating financial data or shipping anything
  mistakable for real market data. Synthesising or importing returns to feed a
  backtester would either violate Principle 8 or introduce a large,
  data-quality-heavy market-data ingestion surface (a new external source, a new
  PIT-availability model for prices, corporate-action adjustment) — an entire
  phase of its own, not a backtester.

Therefore a *performance* backtester is **blocked on a data gap that is a design
choice, not an oversight**. Building it now would force one of two violations:
fabricated returns (breaks Principle 8) or a smuggled-in market-data dependency
(breaks "minimal dependencies" + the SEC-only provenance chain). Neither is
acceptable. **The proposal does not build a return-based backtester.** It instead
builds the primitive that is (a) fully supported by existing data, (b) the
genuine prerequisite for *any* future backtesting or factor-persistence
analytics, and (c) the direct realization of the deferred-scope backlog: the
**point-in-time fundamental panel**. See §2 for why this is the highest-value
buildable layer.

> Backtesting is not being abandoned — it is being *correctly sequenced*. A
> fundamental backtester needs a point-in-time time series of its signal before
> it can rebalance on anything; and even a price-free "signal analytics"
> backtest (factor persistence, universe turnover, rank stability over time)
> needs the panel first. Phase 10 unblocks that future phase without pretending
> the price gap does not exist.

### 1.2 Phase 7 §19 and Phase 8 §13 explicitly *defer* multi-period constructs — is realizing them a scope violation?

Both prior phases list, under **Deferred scope**, exactly the constructs this
layer proposes:

- `metrics.md` §19: "**Cross-period metrics** — growth rates,
  trailing-twelve-month, and averaging metrics (e.g. asset turnover needs
  *average* assets across two instants) … the `period_model` reserves room but
  the constructs are deferred."
- `factors.md` §13: "**Cross-period / time-series factors** — momentum, growth,
  trailing-twelve-month factors need Phase 7's deferred multi-period metrics; a
  factor here is a *single-period cross-section*."

This is a **phase boundary, not a permanent prohibition** — the same reading
`metrics.md` §1.1 applied to "factors are out of scope." Both docs *reserve room*
for exactly this ("the `period_model` reserves room"), and `asset_turnover`
already ships a documented compromise (ending — not average — assets) *because*
the average form "needs two periods (deferred, §19)." Phase 10 is the phase those
deferrals were pointing at. What remains deferred after Phase 10 is named in §10.

### 1.3 Multi-period composition must not smuggle in look-ahead (invariants 28, 29)

This is the load-bearing correctness tension. A growth rate `(x_T − x_{T−1}) /
x_{T−1}` combines two periods; a TTM sums four quarters; a "current ratio vs its
3-year median" compares a level to its own history. Each pulls in **prior
periods' values**, and the danger is using a *later-revised* value of a prior
period, or a value that was not yet public at the panel's `as_of` — precisely the
look-ahead invariant 28/29 forbid.

**Resolved by making the panel itself point-in-time, cell by cell.** A PIT panel
is evaluated at a single `as_of T`; **every** cell in it — including the
historical periods a growth/TTM derivation consumes — is resolved by the existing
Phase 5 resolver *at that same `as_of T`*. So "FY2019 revenue as known on
2021-01-01" and "FY2020 revenue as known on 2021-01-01" are both PIT-eligible at
`T`, and their growth rate is a value that was **genuinely computable on
2021-01-01** using only then-public data. The multi-period derivation is a **pure
function of PIT cells that were already `as_of`-eligible** — it introduces no new
data and no new boundary, so by the same argument `factors.md` §1.4 used for
cross-sectional transforms, **it cannot add look-ahead**. Invariant 29
(as_of-monotonicity) is preserved because the whole panel column is a function of
`≤ T` observations. Any consumed period whose input is not yet public at `T` makes
that derivation `UNDEFINED`, never a guess (§6).

There is a second, subtler axis — a panel *across many `as_of`s* for one period
(the "how did our knowledge of FY2019 revenue evolve?" view). This is the
**vintage** / knowledge-evolution panel (§4.2). It is still fail-closed and PIT
per column: each column is an independent `PIT(as_of_i)` evaluation over the same
immutable history; no column ever reads another column. It cannot leak look-ahead
because each `as_of_i` is closed under `≤ as_of_i` (invariant 29).

### 1.4 A "period range" needs enumerating a filer's periods — is that a hidden non-determinism?

A multi-period panel must know *which* fiscal periods to place on the time axis. A
naive "all periods the filer has" couples the panel's shape to whatever happens to
be ingested — the same reproducibility hazard `factors.md` §1.3 (Decision F1)
rejected for universe membership ("the same factor would differ across machines
and across backfills").

**Resolved by making the period axis explicit and part of the request, mirroring
F1.** The caller supplies the period axis declaratively — either an **explicit
ordered list** of `MetricPeriod`s, or a **deterministic generator** (e.g. "the
fiscal years ending in `[2018-01-01, 2023-12-31]`, annual") whose parameters are
hashed into the panel identity. The panel never enumerates "whatever periods
exist locally." A requested period for which the filer reported nothing is a
first-class `UNDEFINED` cell (§6), never a silently missing column. This keeps the
panel reproducible by construction (Principle 5, 6) exactly as Phase 8 kept the
factor reproducible.

### 1.5 Other invariants (immutability, no-DB, no-network, no-float, PIT/REVISED types)

- **Immutability / no mutation of prior layers.** A panel is pure derived state
  computed by *calling* the Phase 7 `MetricEngine` (and, for the cross-sectional
  panel, the Phase 8 `FactorEngine`) once per cell. No fact, metric, availability
  record, factor, or store is edited. Wiring is **additive** only — a
  lazily-built `PanelEngine` on `Workspace`, exactly as Phase 7/8 added their
  engines (§7).
- **No database / file-based.** Panel *values* are compute-on-demand (mirroring
  Phase 7 D1 and Phase 8 F2). An **optional** write-once content-addressed
  `ResearchResult` sidecar records the provenance record only — never a DB, never
  a second copy of the arithmetic (mirrors Phase 8 F4). Proposed as Decision D4,
  not assumed.
- **No network, no AI, no web UI, no FX.** The engine is pure and offline; it
  inherits Phase 7's no-conversion rule (a cross-currency or unit-mismatched cell
  was already `UNDEFINED` upstream). None of these are approached.
- **Exact decimal, no float.** All multi-period arithmetic (differences, ratios,
  sums, medians) uses the **same pinned `Decimal` context** the Phase 7 engine
  version already fixes (precision 34, `ROUND_HALF_EVEN`) — folded into
  `metric_engine_version_id`, so a panel derivation is byte-reproducible and its
  context is already a version pin. A median of an even-count population uses a
  fixed, documented rule (§6.3) so it is a total, deterministic function.
- **PIT/REVISED impossible to confuse.** Phase 10 introduces **distinct**
  `PitPanel` / `RevisedPanel` result types (Decision D5), extending invariants 27,
  28 one axis further: a PIT panel is built *only* from `PitMetricValue` cells at
  one shared `as_of`; a REVISED panel *only* from `RevisedMetricValue` cells over
  one pinned `DatasetVersion`. The only bridge is an explicit, re-evaluating
  `RevisedPanel.reinterpret_as_pit` (§8.2).

**Conclusion: proceed with the panel, not the backtester.** The design below
realizes the deferred multi-period backlog and the genuine prerequisite for any
future backtesting, without altering §12 or any prior phase. The literal next box
(Backtesting) is deliberately **not** built because it is blocked on absent price
data (§1.1); the tensions (§1.3, §1.4) resolve via explicit, versioned, auditable
mechanisms surfaced for approval in §11.

---

## 2. Why the panel is the single most valuable next layer

Four candidate next layers were weighed; the panel wins on value **and**
coherence.

| Candidate | Value | Blocking problem |
| --- | --- | --- |
| **Return-based backtester** (the literal next box) | High if it existed | **Blocked** — needs prices QuantForge has none of; building it violates Principle 8 or "minimal dependencies" (§1.1). |
| **DuckDB/Parquet storage** (data-model §10) | Scale/infra, not new research | Premature — the project is compute-on-demand by design; "no database code exists yet." No new research question unlocked. |
| **Reproducible-research runner** (re-run a `ResearchResult`, verify `result_hash`) | Real but thin | Phase 8 already persists the `ResearchResult` + `result_hash`; a re-run harness is mostly mechanical and unlocks no new question. |
| **PIT fundamental panel** (this proposal) | **Highest** — unlocks the entire deferred multi-period research class (growth, TTM, momentum, trend, average-balance) and is the true prerequisite for backtesting *and* factor-persistence analytics | None — fully supported by existing data; preserves every invariant. |

The panel is the **only** candidate that is (a) fully buildable on existing data,
(b) directly clears the Phase 7/8 deferred backlog, and (c) is the honest
prerequisite the blocked backtester actually needs. It is the natural third axis
after the Phase 8 cross-section, and it composes the existing engines rather than
introducing any new data, identity, or storage.

---

## 3. Guiding principles

1. **Compose, never re-resolve.** A panel cell is produced by calling the
   *existing* Phase 7 `MetricEngine` (and Phase 8 `FactorEngine` for the
   universe-panel). Phase 10 fans out over the time axis and collects; it adds no
   resolution, no arithmetic on facts, no availability logic.
2. **The period axis is explicit and part of the request** (mirrors Phase 8 F1) —
   no "all periods that happen to exist"; the axis is declared and hashed into
   identity (§1.4).
3. **Every cell is a first-class metric result.** A cell is a full
   `PitMetricValue` / `RevisedMetricValue` — `KNOWN` with provenance, or
   `UNDEFINED` with a reason. No cell is dropped, imputed, or coerced to `0`.
4. **Multi-period derivations are pure functions of KNOWN PIT cells** — they add
   no data and no boundary, so they cannot introduce look-ahead (§1.3); an input
   period that is `UNDEFINED` makes the derivation `UNDEFINED` (§6).
5. **PIT and REVISED are impossible to confuse** — distinct panel types, no
   default mode, one shared boundary for the whole panel (invariants 27, 28).
6. **Exact, deterministic, reproducible.** `Decimal` only (inherited Phase 7
   context), no `float`, no wall-clock, no RNG; cells ordered by (period, then
   `company_id`); the same request reproduces the same `panel_id` **and** the same
   values.
7. **Zero information loss.** The panel records every requested (period × as_of ×
   member) coordinate, its cell (value or undefined reason), the shared boundary,
   and the full pin-set — the §9 closed loop from raw bytes to result.
8. **A panel definition is declarative data.** `metric_key` + period axis +
   optional multi-period derivation + (member or universe) + boundary, hashed into
   identity — a change is a new `panel_id`, never a silent edit (mirrors
   `FormulaDefinition` and the Phase 8 factor definition).

---

## 4. The panel shapes

A **panel** is *one metric evaluated over a time axis*, in one of three shapes.
All three are the same underlying idea (a grid of Phase 7 metric cells at declared
coordinates) with different axes populated; the proposal implements them as one
model with the unused axis degenerate.

### 4.1 Period-series (one filer, many periods, one `as_of`)

The core shape: *"current ratio for Apple across FY2015–FY2023, all as known on
2024-06-01."* Time axis = the requested fiscal periods; every cell resolved at the
**same** PIT `as_of` (or the same REVISED snapshot). This is what a growth rate or
a trend line is computed from (§6). All cells share one boundary, so the series is
internally consistent — no cell knows more than another (§1.3).

### 4.2 Vintage / knowledge-evolution (one filer, one period, many `as_of`s)

*"How did our knowledge of Apple's FY2019 revenue evolve — as known on 2020-01-01,
2021-01-01, 2023-01-01?"* Time axis = the `as_of` instants; the fiscal period is
fixed. Each column is an independent `PIT(as_of_i)` evaluation over the same
immutable history. This is the panel that makes **restatement/vintage effects
visible and auditable** — it directly exhibits the §KS.3 worked example (a value
changing as a restatement becomes public) as first-class data. It is **PIT-only**
(a REVISED "vintage" is a contradiction — REVISED has no `as_of` axis, §8.1).

### 4.3 Cross-sectional panel (many filers, many periods, one `as_of`)

*"current ratio for a 3-filer universe across FY2018–FY2023, all as known on
2024-06-01"* — a full matrix (member × period). This is the composition of Phase 8
(the cross-section, one column per period) and 4.1 (the time series, one row per
member). It is what a future **factor-persistence / turnover analytic** consumes
(§10 notes the analytic itself is deferred). It reuses the Phase 8 `Universe` and
`FactorEngine` per period; Phase 10 stacks the columns.

---

## 5. Package layout (proposed)

A new package `src/quantforge/panel/`, each module single-responsibility, matching
the Phase 4/5/7/8 discipline.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `PanelError` → `PanelConfigurationError` (empty/duplicate period axis, malformed generator, mixed engine version, boundary/type misuse). Data conditions remain `UNDEFINED` cells, **not** exceptions. |
| `axis.py` | `PeriodAxis` — an explicit ordered `MetricPeriod` list **or** a deterministic, hashable generator (frequency + inclusive date bounds); the `AsOfAxis` for the vintage shape. Fail-closed on empty. No "all periods that exist" enumeration (§1.4). |
| `model.py` | `PanelCell` (a (period, as_of, member) coordinate + its metric result), `PanelStatus` summary counts, and the distinct `PitPanel` / `RevisedPanel` result types (§8). |
| `derive.py` | Pure multi-period derivations (`growth`, `ttm`, `average_balance`, `level_vs_history`) over KNOWN cells of one series, under the inherited decimal context, deterministic ordering (§6). Included per Decision D3. |
| `identity.py` | The content-addressed `panel_definition_id` and `panel_id` (§9). |
| `engine.py` | `PanelEngine` — the façade: fan out the Phase 7 `MetricEngine` (or Phase 8 `FactorEngine` for 4.3) across the declared axes at one boundary, assemble the typed panel + `ResearchResult`. The only I/O boundary; composes, never resolves. |
| `store.py` | *(Decision D4, optional)* `ResearchResultStore` reuse — a write-once content-addressed sidecar for the panel's `ResearchResult` provenance record. Never a DB; provenance only, not the values. |
| `__init__.py` | Curated public exports (§7). |

Per Decision D2 (proposed, mirroring Phase 7 D1 / Phase 8 F2) panel **values** are
compute-on-demand; only the optional `ResearchResult` sidecar is persisted.

---

## 6. Multi-period derivations (Decision D3 — proposed, included)

A derivation is a **pure function of the KNOWN cells of one period-series** (§4.1)
that shares one boundary — it adds no data and no new boundary, so it cannot
introduce look-ahead (§1.3). The proposed initial set, each shipping
`confidence = unvalidated` (the *arithmetic* is exact; the *period-selection* is
heuristic until validated on real filings, mirroring `metrics.md` §18):

| Derivation | Definition | Undefined when |
| --- | --- | --- |
| `growth` | `(x_T − x_{T−1}) / x_{T−1}` over adjacent requested periods | either period `UNDEFINED`; or `x_{T−1} == 0` → `UNDEFINED(DIVIDE_BY_ZERO)` (never `Inf`) |
| `ttm` | sum of the four most recent requested `DURATION` quarters ending at `T` | fewer than four consecutive quarters `KNOWN`; a period-kind mismatch → `PanelConfigurationError` |
| `average_balance` | `(x_T + x_{T−1}) / 2` for an `INSTANT` metric (the average `asset_turnover` wanted — `metrics.md` §6.5) | either instant `UNDEFINED` |
| `level_vs_history` | `x_T` vs a statistic (median/min/max) of the prior *n* requested periods — a descriptive position, **not** a z-score-through-time | fewer than *n* prior `KNOWN` periods |

Rules that keep every derivation deterministic and fail-closed:

- **Population = KNOWN cells only.** An `UNDEFINED` input period makes the
  derivation `UNDEFINED` (a growth rate needs both endpoints) — never imputed,
  never carried-forward, never `0` (Principle 8; mirrors `factors.md` §6.2).
- **Exactness** = the pinned Phase 7 `Decimal` context (precision 34,
  `ROUND_HALF_EVEN`), already a version pin. No `float`.
- **Determinism of ordering** = the period axis is ordered by `period_end` (ties
  broken by period_type then start); a median of an even-count population takes
  the **lower-mean** rule — a single documented, total rule (§6.3 spirit).
- **No cross-boundary derivation.** A derivation only ever combines cells of the
  **same** panel (same `as_of`/snapshot); it can never reach across the vintage
  axis (§4.2) to mix knowledge states.

Derivations are **descriptive fundamental time-series statistics**, nothing more:
no returns, no weighting-into-portfolios, no strategy, no recommendation (§10).

---

## 7. Public API & integration (additive only)

```python
# Low-level (engine):
engine = PanelEngine(workspace)  # composes Phase 7 (and Phase 8 for the matrix)

axis = PeriodAxis.annual(
    "2018-12-31", "2023-12-31"
)  # explicit/generated, hashed (§1.4)

# 4.1 period-series, PIT:
p = engine.panel_as_of("current_ratio", cik, axis, as_of)  # → PitPanel
# 4.2 vintage, PIT-only:
v = engine.vintage_as_of("current_ratio", cik, period, as_of_axis)  # → PitPanel
# 4.3 cross-sectional matrix, PIT (reuses the Phase 8 Universe):
m = engine.panel_across("current_ratio", universe, axis, as_of)  # → PitPanel
# REVISED (no as_of axis, so no vintage form):
r = engine.revised_panel("current_ratio", cik, axis, dataset_version)  # → RevisedPanel
```

`Workspace` gains a lazily-built, cached `PanelEngine` (exactly as it gained
`MetricEngine` in Phase 7 and `FactorEngine` in Phase 8) — additive wiring only,
no new store, no directory unless Decision D4 (sidecar) is approved. Curated
top-level exports, stable surface only, keeping the PIT/REVISED distinction
visible at the import site:

```python
from quantforge import PitPanel, RevisedPanel  # distinct panel result types
from quantforge.panel import PanelEngine, PeriodAxis  # authoring/inspection
```

There is **no** default-mode `panel()` accessor — the caller must name PIT or
REVISED (invariant 27 at the front door). Because a panel spans many periods (and
possibly many filers), the natural entry point is the engine; a per-filer
`Company.panel_as_of(...)` convenience delegating to the engine is proposed as a
thin façade method (Decision D6), mirroring `Company.metric_as_of`.

---

## 8. PIT vs REVISED behavior

- **Two methods, no default (invariant 27).** `panel_as_of(...)` /
  `vintage_as_of(...)` / `panel_across(...)` (PIT) require a timezone-aware
  `as_of` (a naive instant is rejected by the same Phase 5 timestamp choke point);
  `revised_panel(...)` (REVISED) requires a `DatasetVersion`.
- **Two result types (invariant 28).** `PitPanel` ≠ `RevisedPanel`; a future
  analytic typed to `PitPanel` cannot be handed a revised panel.
- **One shared boundary (§1.3).** Every cell of a PIT period-series is resolved at
  the same `as_of`; every cell of a REVISED panel over the same universe-wide
  `DatasetVersion` (built by the Phase 8 §8.1 union when the panel spans filers).
  Never mixed within one panel.
- **Past-closed & monotonic (invariant 29), inherited per cell.** As `as_of`
  advances, individual cells go `UNDEFINED → KNOWN` (or a value changes on a
  restatement becoming public) exactly as Phase 7 defines; a period-series is the
  time-slice of those per-cell PIT results, so it inherits monotonicity cell by
  cell. The vintage panel (§4.2) makes this evolution the panel's *content*.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** Resolved at the
  Phase 5 frontier over the pinned snapshot.
- **Explicit crossing only (§8.2).** `reinterpret_as_pit` re-evaluates the whole
  panel at `as_of`.

### 8.1 Why REVISED has no vintage shape

The vintage panel (§4.2) is defined by its `as_of` axis — "what did we know at each
of these instants?" REVISED has **no** `as_of`; it is the single limit as
`T → now` (§KS, invariant 29). A "revised vintage" is therefore a category error
and is a `PanelConfigurationError`, not a silent empty panel. REVISED supports only
the period-series (4.1) and cross-sectional (4.3) shapes.

### 8.2 Crossing REVISED → PIT is explicit and re-evaluates

The only bridge is `RevisedPanel.reinterpret_as_pit(engine, as_of)`, which
**re-runs the whole panel evaluation** at `as_of` over the same axes (it does not
reuse the revised cells). Like Phase 5/7/8's `reinterpret_as_pit`, every crossing
is a visible, intentional, auditable call — never an implicit cast.

---

## 9. Identity, versioning & the ResearchResult

Phase 10 closes the same data-model §9 reproducibility loop Phase 8 does, one axis
wider. Content hashes, `sha256:`-prefixed and NUL-joined per §11 conventions:

```
axis_id              = sha256( "period-axis" ∥ ordered period_keys )        # or ∥ generator params
panel_definition_id  = sha256( metric_key ∥ formula_id ∥ derivation_id ∥ axis_id ∥ shape )
panel_id             = sha256( panel_definition_id ∥ metric_engine_version_id
                              ∥ (universe_id | company_id) ∥ boundary_key ∥ result_hash )
boundary_key         = "pit:"  + as_of_utc          (PIT period-series / matrix)
                     | "pit-vintage:" + sorted as_of_utc list   (PIT vintage)
                     | "rev:"  + dataset_version_id (REVISED)
result_hash          = sha256( canonical JSON of the ordered cell values+statuses )
```

`panel_id` pins the **request** (definition, engine, member(s), boundary) **and**
the **output** (`result_hash`); re-running the same request reproduces the same
`panel_id` and the same values — determinism made checkable. It maps directly onto
data-model §9 `ResearchResult`: `factor_definition_id ≡ panel_definition_id`,
`factor_version ≡ metric_engine_version_id`, `dataset_version_id` and
`as_of_timestamp` as in Phase 8, `query_params = { metric_key, axis, derivation,
shape, member(s) }`, `result_hash` as above, and `strategy_version` **still
absent** — reserved for the deferred backtester (§1.1, §10).

---

## 10. Deferred scope (surfaced, not silent)

Explicitly **not** built in Phase 10:

- **Return-based backtesting, portfolio construction, weighting, trading
  strategies, investment recommendations** — still out of scope and, for
  performance backtesting specifically, **blocked on absent price/market data**
  (§1.1). `strategy_version` stays unset.
- **Market-data / price ingestion** — no new external source; QuantForge stays
  SEC-only. Any price layer is a separate, explicit phase with its own PIT model.
- **Factor-persistence / universe-turnover analytics** — the *analytics* that
  would consume the §4.3 cross-sectional panel (autocorrelation of ranks, universe
  churn over time) are deferred; Phase 10 delivers the panel they need, not the
  analytic.
- **Through-time normalization that crosses vintages** — e.g. a z-score of a value
  against its own *revised* history; disallowed because it would mix knowledge
  states (§6, §8.1).
- **Per-share / segment / multi-metric composite panels** — inherit Phase 7/8
  deferrals (no security master; consolidated-only; one `metric_key` per panel).
- **DuckDB/Parquet materialization** — panels are compute-on-demand (D2); the
  storage model in data-model §10 remains a separate future decision.

---

## 11. Architectural decisions (proposed — awaiting approval)

Load-bearing choices, surfaced for approval exactly as Phases 7/8 surfaced theirs.
**These are proposals, not locked**; implementation begins only after they are
approved.

- **D1 — Scope: build the PIT fundamental panel, NOT a return-based backtester.**
  The literal next box is blocked on absent price data (§1.1); the panel is the
  highest-value buildable layer and the genuine prerequisite for future
  backtesting (§2).
- **D2 — Panel values: compute-on-demand** (mirrors Phase 7 D1 / Phase 8 F2). No
  cached arithmetic; reproducibility comes from the hashes.
- **D3 — Multi-period derivations: included** — `growth`, `ttm`,
  `average_balance`, `level_vs_history`, all pure over KNOWN cells of one series,
  `UNDEFINED`-preserving, under the pinned decimal context (§6). Alternative:
  ship the raw panel only and defer derivations — offered if a narrower first cut
  is preferred.
- **D4 — `ResearchResult` sidecar: reuse Phase 8's, optional.** Write-once,
  content-addressed, provenance-only. Alternative: no persistence in Phase 10.
- **D5 — Distinct panel result types: `PitPanel` / `RevisedPanel`** — separate
  frozen types, extending invariant 28 to the time axis (look-ahead becomes a type
  error).
- **D6 — `Company` convenience method** — a thin `Company.panel_as_of(...)`
  delegating to the engine, mirroring `Company.metric_as_of`. Alternative:
  engine-only entry point (as Phase 8 chose for factors, since panels can span
  filers).
- **D7 — Period axis model** — explicit list **or** deterministic generator, both
  hashed into `axis_id` (§1.4). Confirm the generator's frequency vocabulary
  (annual / quarterly) and calendar handling before implementation.

---

*This document proposes the Phase 10 point-in-time fundamental panel layer. It
writes no implementation code and commits nothing. Implementation satisfies the
determinism, fail-closed, immutability, provenance, and PIT/REVISED invariants of
data-model §12 (esp. 5, 18, 21, 27–30) and realizes the reserved §9
`ResearchResult` one axis wider. It deliberately does not build a return-based
backtester, which is blocked on the project's intentional absence of price data
(§1.1). Changes to the panel shapes, the derivation rules, the panel result types,
or the `ResearchResult` mapping require updating this document first, and the §11
decisions require approval before any code is written.*
