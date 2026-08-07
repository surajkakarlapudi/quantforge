# Cross-Sectional Factor & Research-Result Layer (Phase 8)

The factor layer evaluates **one Phase 7 metric across an explicit universe of
filers at a single shared knowledge-state boundary**, producing a
**cross-sectional factor** — a deterministic, fail-closed, fully-provenanced
vector of per-filer values — and packaging it as the reproducible
[`ResearchResult`](data-model.md) that [docs/data-model.md](data-model.md) §9 has
reserved from the start (`factor_definition_id + factor_version`, `query_params`,
`result_hash`). It is the research primitive that sits between the per-company
metric ([Phase 7](metrics.md)) and the still-deferred backtester in
[ARCHITECTURE.md](../ARCHITECTURE.md)'s `Factors → Backtesting → Reproducible
Research` flow.

Package: `src/quantforge/factors/`.

This layer follows [docs/data-model.md](data-model.md) exactly — the
knowledge-state semantics (§KS), the point-in-time predicate and selection order
(§6.1, §6.3), the reproducible `ResearchResult` / versioning model (§9), the
provenance chain (§5), and the fail-closed / determinism invariants (§12). It
builds directly on the Phase 7 [`MetricEngine`](metrics.md) and the two distinct
metric result types, and through them on the Phase 5
[`PointInTimeResolver`](point-in-time.md) and Phase 4 canonical
[`Fact`](canonicalization.md). Section references point into the data model unless
stated otherwise.

> **This layer composes existing per-filer metrics across a universe; it never
> re-implements resolution, never invents membership, and never crosses the
> PIT/REVISED boundary implicitly.** A factor is computed by calling the *existing*
> Phase 7 engine once per filer in a **caller-supplied** universe, at **one**
> shared `as_of` (PIT) or **one** pinned `DatasetVersion` (REVISED), and
> collecting the results. A filer whose metric is `UNDEFINED` contributes a
> first-class `UNDEFINED` cell carrying *why* — never a guessed number, never
> dropped silently, never `0`. It never mutates a fact or a metric, and it adds no
> new resolution logic.

---

## 1. Contradiction analysis

Before any design, the requested work was checked against every prior invariant,
principle, and phase design — the mandated first step, exactly as Phase 7 §1 did.
**No hard contradiction exists.** Five tensions were examined; each *resolves*
under an explicit rule rather than requiring a change to a prior layer. Had any
been a true contradiction, this section would say STOP and stop — it does not.

### 1.1 The "Factors" box is already Phase 7 (ARCHITECTURE.md)

ARCHITECTURE.md's data flow is `Point-in-Time → Factors → Backtesting →
Reproducible Research`, and the **Factors** row is already marked *Exists (Phase
7)* and mapped to [metrics.md](metrics.md). At first glance a "Phase 8 factor
layer" collides with it.

**Resolved by refining the mapping, not overloading the box.** Phase 7 built the
*per-company building block*: one formula, one filer, one period, one boundary →
one value. What ARCHITECTURE's Factors box and data-model §9 actually anticipate
is broader — a **cross-sectional signal over a universe** whose reproducibility is
captured by a `ResearchResult` (`query_params` = *universe/concepts/dates*, plus a
`result_hash`). data-model §9 explicitly reserves `factor_definition_id +
factor_version` for this and it is **not yet realized**. Phase 8 realizes it. The
two layers are complementary and this document proposes ARCHITECTURE.md be
clarified to read: **Phase 7 = per-company metric (building block); Phase 8 =
cross-sectional factor / ResearchResult (research primitive).** No prior code or
guarantee changes; only the doc's Factors row gains a second, more precise line.

### 1.2 "Backtesting / portfolio construction is out of scope" (data-model §9.19; metrics §19)

Phase 7 §19 and data-model §9.19 defer *backtesting, portfolio construction,
trading strategies, and any investment recommendation*. A cross-sectional factor
is upstream of all of those: it is the **input** a backtester would consume, not
the backtester. data-model §9 lists `factor_definition_id + factor_version`
*separately* from `strategy_version` precisely to draw this line — the factor
exists independently of any strategy. Phase 8 stops at the factor vector +
`ResearchResult`; it constructs **no** portfolio, ranks into **no** trades, and
emits **no** recommendation. Those remain deferred (§13).

### 1.3 There is no "universe" / company enumeration, and inventing one would break determinism

The codebase has **no** `list_companies()` / all-filers enumeration — only
`CanonicalFactStore.read_company(company_id)` and per-filer Phase 5/7 methods. A
factor needs a universe. Two options were considered; the fail-closed,
deterministic one is **locked** (Decision F1):

- **Enumerate all locally-ingested filers** — convenient, but it couples a
  factor's *identity and value* to whatever happens to be ingested on this machine
  at this moment. The "same" factor would differ across machines and across
  backfills — a reproducibility break and a silent look-ahead-by-ingestion risk.
- **Caller-supplied explicit universe (LOCKED, F1).** The universe is an
  **explicit, ordered, resolved set of `company_id`s the caller passes in.** It is
  part of the factor request, hashed into the `ResearchResult` (§7), and therefore
  reproducible by construction. A filer in the universe with no facts is a
  first-class `UNDEFINED` cell (§9), never a silent omission. This matches the
  project's determinism (Principle 5) and fail-closed (§PA.3) posture exactly, and
  mirrors how Phase 7 requires an explicit `cik` rather than guessing one.

### 1.4 Cross-sectional aggregation vs. determinism / no-look-ahead

A cross-sectional factor invites *ranks, z-scores, percentiles* — order- and
population-dependent statistics. Two hazards: (a) non-determinism from unstable
ordering or float, and (b) look-ahead if a normalization peeks at values that
weren't knowable at `as_of`.

**Resolved (Decision F3 — transforms included).** Phase 8 ships the **raw
cross-sectional vector** as the primitive *and* a small set of *cross-sectional
transforms* (rank, z-score, min-max, winsorize) that are **pure, deterministic
functions of the KNOWN cells of that same one-`as_of` vector** — they introduce no
new data and no new boundary, so they cannot add look-ahead (every input was
already `as_of`-eligible). They are computed under the **same pinned `Decimal`
context** Phase 7 already versions (§6), with a **fixed tie/ordering rule** (by
`company_id`) so a rank is a total order. `UNDEFINED` cells are **excluded from
the statistic's population and remain `UNDEFINED`** in the output (never imputed to
the mean/median — that would fabricate data, Principle 8).

### 1.5 Other invariants (immutability, no-DB, no-network, PIT/REVISED types)

- **Immutability / no mutation of prior layers.** A factor is pure derived state
  computed by calling Phase 7. No fact, metric, availability record, or store is
  edited. The only wiring is an **additive** `Company`/`Workspace`-level entry
  point (§10) — no prior store changes.
- **No database / file-based.** Factor *values* are computed on demand (Decision
  F2, mirroring Phase 7 D1); a write-once, content-addressed `ResearchResult` file
  sidecar (never a DB) materializes the provenance record for audit (Decision F4).
- **No network, no AI, no web UI, no FX.** The engine is pure and offline; it
  inherits Phase 7's no-conversion rule (a unit mismatch was already `UNDEFINED`
  upstream).
- **PIT/REVISED impossible to confuse.** Phase 8 introduces **distinct**
  `PitFactor` / `RevisedFactor` result types (Decision F5), extending invariant 28
  one level up: a factor is built *only* from same-typed metric cells at one
  boundary, and the only bridge is an explicit, re-evaluating
  `RevisedFactor.reinterpret_as_pit` (§5.2).

**Conclusion: proceed.** The design below realizes the reserved §9 `ResearchResult`
as a cross-sectional factor without altering §12 or any prior phase; the tensions
(§1.1, §1.3, §1.4) are resolved by explicit, versioned, auditable mechanisms
surfaced for approval in §14.

## 2. Guiding principles

1. **Compose, never re-resolve.** Phase 8 calls the Phase 7 `MetricEngine` once
   per filer; Phase 5 already decided eligibility and restatement order, Phase 7
   already did the arithmetic. Phase 8 only fans out and collects.
2. **The universe is explicit and part of the request.** No hidden "all
   companies"; membership is caller-supplied, ordered, and hashed into identity
   (F1).
3. **Every cell is a first-class metric result.** A filer's contribution is a full
   `PitMetricValue` / `RevisedMetricValue` — `KNOWN` with provenance, or
   `UNDEFINED` with a reason. No cell is ever dropped, imputed, or coerced to `0`.
4. **PIT and REVISED are impossible to confuse** — distinct factor types, no
   default mode, one shared boundary for the whole vector (invariants 27, 28).
5. **Exact, deterministic, reproducible.** `Decimal` only (inherited context), no
   `float`, no wall-clock, no RNG; cells are ordered by `company_id`; the same
   request reproduces the same `research_result_id` **and** the same values.
6. **Zero information loss.** The factor records every universe member, its cell
   (value or undefined reason), the shared boundary, and the full pin-set — the §9
   closed loop from raw bytes to result.
7. **Reuse, don't reimplement.** Metric evaluation from Phase 7; PIT/REVISED and
   `DatasetVersion` from Phase 5; decimal context + serialization from Phase 7;
   identity hashing from the §11 conventions. Phase 8 adds only the fan-out, the
   `ResearchResult` shape, and the optional pure transforms.
8. **A factor definition is declarative data.** `metric_key` + optional transform
   + universe + period + boundary, hashed into identity — a change is a new
   `research_result_id`, never a silent edit (mirrors `FormulaDefinition`).

## 3. Package layout

Each concern is a separate module with a single responsibility, matching the
Phase 4/5/7 discipline.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `FactorError` → `FactorConfigurationError` (empty/duplicate universe, unknown transform, boundary/type misuse). Data conditions remain `UNDEFINED` metric cells, **not** exceptions. |
| `model.py` | `FactorCell` (a universe member + its metric result), `FactorStatus` summary counts, the `ResearchResult` provenance record, and the distinct `PitFactor` / `RevisedFactor` result types (§5). |
| `universe.py` | `Universe` — an explicit, ordered, de-duplicated, frozen set of `company_id`s with a content hash (§7.1). Fail-closed on empty. No enumeration of "all filers". |
| `transform.py` | Pure cross-sectional transforms (`rank`, `zscore`, `minmax`, `winsorize`) over the KNOWN cells, under the inherited decimal context, deterministic tie-order (§6.2). Included per Decision F3. |
| `identity.py` | The content-addressed `factor_definition_id` and `research_result_id` (§7). |
| `engine.py` | `FactorEngine` — the façade: fan out the Phase 7 `MetricEngine` across the universe at one boundary, assemble the typed factor + `ResearchResult`. The only I/O boundary; composes, never resolves. |
| `store.py` | `ResearchResultStore` — a file sidecar (never a DB) materializing computed `ResearchResult`s keyed by `research_result_id`, mirroring the Phase 5 `AvailabilityStore` layout. Write-once, content-addressed, for audit/reuse (Decision F4). |
| `__init__.py` | Curated public exports (§10). |

Per Decision F4 a `ResearchResultStore` file sidecar materializes each computed
`ResearchResult` (write-once, content-addressed by `research_result_id`); the
factor *values* remain compute-on-demand (F2) — the sidecar records the reproducible
provenance record, not a second copy of the metric arithmetic.

## 4. Architecture and data flow

No second HTTP client, no second storage system. Phase 8 sits directly on Phase 7:

```
… → CANONICAL → AVAILABILITY/PIT → METRICS → FACTORS
    (Phase 4)     (Phase 5)        (Phase 7)  (Phase 8)
```

- **Phase 7** owns per-filer metric evaluation and the two metric result types.
  Phase 8 calls `MetricEngine.metric_as_of` / `revised_metric` once per member and
  reads the results — it never touches the resolver, the formula, or the decimal
  context directly.
- **Phase 8** adds the universe fan-out, the cross-sectional assembly, the optional
  transforms, and the `ResearchResult` packaging. Factor values are recomputed on
  demand (Decision F2); only the `ResearchResult` provenance record is persisted, to
  a write-once content-addressed file sidecar (Decision F4).

Data flow for one factor:

```
FactorEngine.factor_as_of(metric_key, universe, period, as_of[, transform])
        │
        ▼
for each company_id in universe (declared order):        ← explicit, caller-supplied (F1)
    MetricEngine.metric_as_of(metric_key, cik, period, as_of)   ← Phase 7, unchanged
        └────────────────▶  PitMetricValue (KNOWN value | UNDEFINED reason)
        │
        ▼
assemble cells (one per member, never dropped)
        │
        ▼
optional transform over KNOWN cells only (pure, same Decimal context, F3)
        │
        ▼
PitFactor { cells, shared as_of, ResearchResult (formula/engine/dataset/universe/params + result_hash) }
```

The engine is the I/O boundary (it drives Phase 7, which reads facts/availability);
the transform and identity are pure. This mirrors the Phase 7 engine-vs-evaluator
and Phase 5 façade-vs-resolver split one level up.

## 5. Factor result model

A **factor** is *one metric, evaluated across one ordered universe, for one fiscal
period, at one knowledge-state boundary.* Two result types keep PIT and REVISED
unmixable (invariant 28), exactly as Phase 5 and Phase 7 do.

A **`FactorCell`** is one universe member's contribution:

| Field | Meaning |
| --- | --- |
| `company_id` | The universe member (canonical `cik:`-form). |
| `metric` | The full `PitMetricValue` / `RevisedMetricValue` for that filer — `KNOWN` (value + provenance) or `UNDEFINED` (reason + provenance). Never `None`, never dropped. |
| `transformed_value_numeric_str` | The transform output for this cell (Decision F3), exact `Decimal` serialized; `None` when the cell is `UNDEFINED` or no transform was applied. |

Both factor result types are frozen, slotted dataclasses sharing this shape:

| Field | Meaning |
| --- | --- |
| `research_result_id` | Deterministic identity of the whole request+output (§7). |
| `metric_key` | The Phase 7 formula name evaluated across the universe. |
| `formula_id` | The formula version used (from Phase 7; identical for every cell). |
| `metric_engine_version_id` | The Phase 7 evaluator version (+ pinned decimal context). |
| `universe_id` | Content hash of the ordered member set (§7.1). |
| `period` | The shared `MetricPeriod`. |
| `transform` | The applied cross-sectional transform id, or `"none"` (§6.2). |
| `cells` | Ordered tuple of `FactorCell`, one per universe member, in universe order. |
| `summary` | `FactorStatus`: counts of `KNOWN` vs each `UndefinedReason` (audit; §9). |
| `research_result` | The `ResearchResult` provenance record (§7). |

The **distinguishing** field (as in Phase 5/7):

- `PitFactor.as_of` — the timezone-aware historical instant shared by all cells.
- `RevisedFactor.dataset_version_id` — the pinned snapshot shared by all cells.

An `UNDEFINED` cell is a *value*, not an error: a factor over 500 filers must
record "current ratio undefined for filer X at T because `LiabilitiesCurrent` was
not yet public" for each X without aborting — exactly Phase 5's `UNKNOWN` and Phase
7's `UNDEFINED` posture, lifted to the vector.

### 5.1 A factor inherits its cells' mode

A `PitFactor` is assembled **only** from `PitMetricValue` cells resolved at the
**same** `as_of`; a `RevisedFactor` **only** from `RevisedMetricValue` cells over
the **same** `DatasetVersion`. The engine never mixes boundaries within one factor
and never mixes filers resolved at different `as_of`s. This is what makes the
factor's PIT-ness structurally true, not hoped-for (invariant 28, extended).

### 5.2 Crossing REVISED → PIT is explicit and re-evaluates

The only bridge is `RevisedFactor.reinterpret_as_pit(engine, as_of)`, which
**re-runs the whole cross-sectional evaluation** at `as_of` over the same universe
(it does not reuse the revised cells). Like Phase 5/7's `reinterpret_as_pit`, every
crossing is a visible, intentional, auditable call — never an implicit cast.

## 6. Cross-sectional evaluation

### 6.1 The fan-out (deterministic, fail-closed)

Given `(metric_key, universe, period, boundary)`:

1. **Validate the universe.** Empty universe → `FactorConfigurationError` (fail
   closed; a factor over nobody is a configuration bug, not an empty result).
   Members are de-duplicated and frozen in caller order (§7.1).
2. **Evaluate per member, in universe order.** For each `company_id`, call the
   Phase 7 engine in the factor's mode — `metric_as_of` (PIT, shared `as_of`) or
   `revised_metric` (REVISED, shared `DatasetVersion`). Phase 7 returns exactly one
   typed metric result per filer, `KNOWN` or `UNDEFINED`.
3. **Assemble one cell per member.** Never drop, never reorder by value. A filer
   with no facts, or whose input is not yet public at `as_of`, yields an
   `UNDEFINED(MISSING_INPUT)` cell — recorded, not omitted.
4. **Summarize.** Count `KNOWN` and each `UndefinedReason` into `FactorStatus`
   (audit; §9), so "how many filers resolved, and why not the rest?" is answerable
   without walking every cell.

The fan-out is a pure function of `(metric_key, ordered universe, period,
boundary, engine version)`: no wall-clock, no RNG, deterministic order.

### 6.2 Cross-sectional transforms (Decision F3 — included)

A transform is a **pure function of the KNOWN cells of the same one-`as_of`
vector** — it adds no data and no boundary, so it cannot introduce look-ahead:

- **Population** = the KNOWN cells only. `UNDEFINED` cells are **excluded** from
  the statistic and stay `UNDEFINED` in the output — never imputed to a
  mean/median (that fabricates data, Principle 8).
- **Exactness** = the **same pinned `Decimal` context** the Phase 7 engine version
  already fixes (precision 34, `ROUND_HALF_EVEN`), folded into
  `metric_engine_version_id`, so a transform result is byte-reproducible and its
  context is already a version pin.
- **Determinism of ordering** = ties broken by `company_id` ascending, so `rank`
  and percentile are a total order (mirrors the §6.3 total-order requirement).
- Candidate transforms: `rank` (ordinal, 1-based, ascending by value with ties
  broken by `company_id` — a total order), `zscore` (population mean/stdev),
  `minmax` (to `[0,1]`), `winsorize` (clip to given percentiles). The applied
  transform id is recorded in `transform` and hashed into `research_result_id`.

`transform="none"` (the raw vector) is always available and is the default.

### 6.3 What Phase 8 deliberately does not compute

No ranking-into-portfolios, no weighting, no returns, no strategy — those are the
backtester (deferred, §13). A transform is a *descriptive cross-sectional
statistic on one date's vector*, nothing more.

## 7. Identity, versioning & the ResearchResult

Phase 8 closes the data-model §9 reproducibility loop. Three content hashes,
composing with the existing pins:

```
universe_id          = sha256( "universe" ∥ ordered, de-duped company_ids )
factor_definition_id = sha256( metric_key ∥ formula_id ∥ transform_id )
research_result_id   = sha256( factor_definition_id ∥ metric_engine_version_id
                               ∥ universe_id ∥ period_key ∥ boundary_key
                               ∥ result_hash )
boundary_key         = "pit:" + as_of_utc        (PIT)
                     | "rev:" + dataset_version_id   (REVISED)
result_hash          = sha256( canonical JSON of the ordered cell values+statuses )
```

All ids are `sha256:`-prefixed and NUL-joined, matching data-model §11 and the
Phase 5/7 convention. `research_result_id` pins the **request** (which factor
definition, engine, universe, period, boundary) **and** the **output**
(`result_hash`); re-running the same request reproduces the same
`research_result_id` and the same values — determinism made checkable.

This maps **directly** onto data-model §9's `ResearchResult`:

| data-model §9 `ResearchResult` field | Phase 8 source |
| --- | --- |
| `factor_definition_id` | `factor_definition_id` (metric + formula + transform) |
| `factor_version` | `metric_engine_version_id` (Phase 7 engine + decimal context) |
| `dataset_version_id` | the shared REVISED snapshot, or the PIT snapshot cited alongside `as_of` |
| `availability_policy_ids` | implied by the `DatasetVersion` (reused from Phase 5) |
| `transformation_version_id` | implied by the `DatasetVersion` |
| `as_of_timestamp` | `PitFactor.as_of` (null for a REVISED factor) |
| `query_params` | `metric_key`, `universe_id`, `period`, `transform` |
| `result_hash` | `result_hash` above |
| `strategy_version` | **absent** — reserved for the deferred backtester (§1.2) |

`factor_definition_id ≡ §9 factor_definition_id` and `metric_engine_version_id ≡
§9 factor_version` are not new invention — §9 reserved exactly these names.

### 7.1 The Universe

`Universe` is an **explicit, ordered, de-duplicated, frozen** tuple of
`company_id`s (canonical `cik:`+10-digit form; the constructor canonicalizes bare
CIKs via the existing `registry.identity` helpers). Its `universe_id` is a content
hash over the *ordered* members, so two requests with the same members in the same
order share identity and reproduce. An empty universe fails closed
(`FactorConfigurationError`). Phase 8 provides **no** "all filers" constructor
(Decision F1); a caller assembles a universe from resolved `Company`/CIK values it
already holds.

## 8. Versioning strategy

A factor's reproducibility is the **union** of its cells' pins plus the universe
and transform:

- **`factor_definition_id`** — content-addressed over `metric_key` + the Phase 7
  `formula_id` + the transform id. Changing the metric, its formula version, or the
  transform yields a new definition id; re-declaring the identical factor
  reproduces it (invariant 20 analogue).
- **`metric_engine_version_id`** (reused from Phase 7) — the evaluator + pinned
  decimal context; identical across every cell of a factor (the engine asserts
  this — a mixed engine version across cells is a `FactorConfigurationError`).
- **`DatasetVersion`** — for a REVISED factor, **one** snapshot spanning the whole
  universe pins the exact facts + normalizer + availability-policy set every cell
  was resolved over (§8.1). A PIT factor cites the snapshot plus the shared
  `as_of`.

### 8.1 One DatasetVersion for the whole universe

A REVISED factor must resolve **every** cell over **one** frontier, or filers
would be compared across different ingestion states — a subtle look-ahead. Phase 8
builds a **universe-wide** `DatasetVersion` by unioning each member's facts +
raw-documents + the shared availability-policy set, reusing the Phase 5
`DatasetVersion` Merkle-manifest primitive (which is already fact-set-agnostic —
its id is a Merkle root over sorted members, so a union composes cleanly). Every
cell's `revised_metric` is resolved against this one snapshot. The same
`dataset_version_id` is recorded on the `RevisedFactor` and every cell.

## 9. Provenance

Every factor — and every cell — carries the unbroken chain back to canonical facts
and, through them, to SEC bytes:

```
ResearchResult {
  factor_definition_id, metric_engine_version_id,
  universe_id, period, transform,
  boundary: PIT(as_of) | REVISED(dataset_version_id),
  dataset_version_id,
  query_params: { metric_key, universe_id, period, transform },
  summary: { known: n, missing_input: n, nil_input: n, ... },  # per-reason counts
  result_hash
}
```

Each `FactorCell.metric` is a complete Phase 7 `MetricProvenance` (selected
concept, winning `fact_id` → Phase 4 Fact → `FactProvenance` → SEC bytes,
availability policy, discarded candidates, the boundary). So from a factor you can
recover, per filer, exactly which facts produced its cell and why any cell is
`UNDEFINED`. **Zero information loss:** no member is omitted, and an undefined cell
records its reason (§13 posture, lifted to the vector).

## 10. Public API & integration

Phase 8 composes onto the existing façades **additively** — no mutation of any
prior layer.

```python
# Low-level (engine):
engine = FactorEngine(workspace)  # composes Phase 7 (§4)
uni = Universe.of("AAPL-resolved-id", ...)  # explicit company_ids (F1)
pit = engine.factor_as_of("current_ratio", uni, period, as_of)  # → PitFactor
rev = engine.revised_factor(
    "current_ratio", uni, period, dataset_version
)  # → RevisedFactor
```

The `Workspace` gains a lazily-built, cached `FactorEngine` (exactly as it gained
`MetricEngine` in Phase 7) — additive wiring only, no new store, no directory. A
convenience `Workspace.factor_engine` property mirrors `metric_engine`.

Curated top-level exports (added to `quantforge/__init__.py`), stable surface
only:

```python
from quantforge import (
    Company,
    PitFactor,
    RevisedFactor,  # NEW: distinct cross-sectional factor types
    Universe,  # NEW: the explicit universe
)
from quantforge.factors import FactorEngine  # for authoring/inspection
```

`PitFactor` / `RevisedFactor` are re-exported (like `PitValue`/`PitMetricValue`) so
the PIT-vs-revised distinction is visible at the import site. There is **no**
default-mode `factor()` accessor — the caller must name PIT or REVISED (invariant
27 at the front door). Because a factor spans *many* filers, the natural entry
point is the engine, not a single `Company`; `Company` gains no cross-sectional
method (it stays a per-filer façade).

## 11. PIT vs REVISED behavior

- **Two methods, no default (invariant 27).** `factor_as_of(...)` (PIT) requires a
  timezone-aware `as_of`; `revised_factor(...)` (REVISED) requires a
  `DatasetVersion`. A naive `as_of` raises `ModeError` via the same Phase 5
  timestamp choke point Phase 7 uses.
- **Two result types (invariant 28).** `PitFactor` ≠ `RevisedFactor`; a backtester
  typed to `PitFactor` cannot be handed a revised factor.
- **One shared boundary (§5.1).** Every cell of a PIT factor is resolved at the
  same `as_of`; every cell of a REVISED factor over the same universe-wide
  `DatasetVersion`. Never mixed within a factor.
- **Past-closed & monotonic (invariant 29), inherited per cell.** As `as_of`
  advances, individual cells go `UNDEFINED → KNOWN` (or a value changes on a
  restatement becoming public) exactly as Phase 7 defines; the factor is the
  cross-section of those per-cell PIT results, so it inherits monotonicity cell by
  cell.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** Resolved at the
  Phase 5 frontier over the pinned universe-wide `DatasetVersion`.
- **Explicit crossing only (§5.2).** `reinterpret_as_pit` re-evaluates the whole
  vector at `as_of`.

## 12. Determinism requirements

- **Exact `Decimal` only** — inherited from Phase 7; no `float` anywhere,
  including transforms (§6.2).
- **One pinned decimal context** — the Phase 7 engine's context, unchanged and
  already folded into `metric_engine_version_id`. Phase 8 introduces no new
  context.
- **Deterministic order** — cells are in universe (caller-declared) order;
  transform ties break by `company_id`; `result_hash` serializes cells in that
  fixed order with `sort_keys=True`. No RNG, no wall-clock.
- **Reproducible by construction** — same `(factor_definition_id, engine_version,
  universe_id, period, boundary)` ⇒ same `research_result_id` **and** same values,
  on any machine.

## 13. Deferred scope

Explicitly **not** built in Phase 8 (surfaced, not silent):

- **Backtesting, portfolio construction, trading strategies, investment
  recommendations** — still out of scope (data-model §9.19); Phase 8 stops at the
  factor vector + `ResearchResult`. `strategy_version` is left unset.
- **Universe *enumeration* / screening** — no "all filers" or rule-based screen;
  the universe is always caller-supplied (F1). A future screening layer would be a
  separate, explicit phase.
- **Cross-period / time-series factors** — momentum, growth, trailing-twelve-month
  factors need Phase 7's deferred multi-period metrics (metrics §19); a factor here
  is a *single-period cross-section*.
- **Multi-metric / composite factors** — combining several metrics into one score
  is deferred; Phase 8 evaluates one `metric_key` per factor.
- **Per-share / segment factors** — inherit Phase 7's deferrals (no security
  master, consolidated-only).
- **Persistent factor *value* materialization** — factor values are compute-on-demand
  (F2); only the `ResearchResult` provenance record is persisted, via the write-once
  content-addressed sidecar (F4). No cached metric arithmetic.

## 14. Architectural decisions (all resolved)

These load-bearing choices are recorded as locked Decisions, mirroring how Phases 5
and 7 recorded theirs. All five are now settled by your answers; implementation
follows them exactly.

- **F1 — Universe model: caller-supplied explicit set (LOCKED).** The universe is
  an explicit, ordered, de-duplicated `company_id` set, hashed into identity. No
  enumeration of locally-ingested filers (§1.3, §7.1).
- **F2 — Factor values: compute-on-demand (LOCKED, mirrors Phase 7 D1).** The
  cross-sectional vector is recomputed from Phase 7 on request; no metric arithmetic
  is cached. Reproducibility comes from the hashes, not from stored values.
- **F3 — Cross-sectional transforms: included (LOCKED).** Ship the raw vector plus
  the pure, deterministic transforms `rank`, `zscore`, `minmax`, `winsorize` over
  the KNOWN cells — `UNDEFINED` excluded from the population and never imputed (§6.2).
- **F4 — `ResearchResult` sidecar: included (LOCKED).** A write-once,
  content-addressed file sidecar (`ResearchResultStore`, never a DB) materializes
  each computed `ResearchResult` under the workspace root for audit/reuse (§3, §9).
  It stores the provenance record only, not a second copy of the values (F2).
- **F5 — Distinct factor result types: LOCKED.** `PitFactor` and `RevisedFactor`
  are separate frozen types, extending invariant 28 to the cross-section, making
  look-ahead a type error rather than a runtime check.

## 15. Testing strategy

Per-module unit tests, matching the Phase 4/5/7 rigor; **all existing tests
continue to pass** (Phase 8 is additive).

- **`universe.py`** — ordering preserved; de-duplication; bare-CIK canonicalization;
  empty universe → `FactorConfigurationError`; `universe_id` determinism and
  sensitivity to membership and order.
- **`identity.py`** — `factor_definition_id` / `research_result_id` determinism and
  sha256 prefix; sensitivity to metric_key, formula, transform, universe, period,
  boundary; `result_hash` stability and sensitivity to any cell value/status.
- **`transform.py`** — rank/zscore/minmax/winsorize exact under the pinned
  context; `UNDEFINED` cells excluded from population and stay `UNDEFINED`;
  deterministic tie-order by `company_id`; a single-KNOWN-cell zscore fails closed
  (zero stdev → `UNDEFINED`, never division blowup); an all-`UNDEFINED` population
  yields an all-`UNDEFINED` transformed vector, never an exception.
- **`store.py`** — a `ResearchResult` round-trips (write → read → identical);
  write is content-addressed by `research_result_id`; a re-write of the same id is a
  no-op (write-once, never a silent overwrite); a differing payload under an existing
  id fails closed; the sidecar lives under the workspace root, never in the repo.
- **`engine.py`** — fan-out preserves universe order; every member yields exactly
  one cell (mixed KNOWN/UNDEFINED); a missing filer → `UNDEFINED(MISSING_INPUT)`
  cell, never dropped; PIT uses one shared `as_of`, REVISED one universe-wide
  `DatasetVersion`; distinct result types; naive `as_of` rejected;
  `reinterpret_as_pit` re-evaluates the whole vector; `research_result_id`
  reproducible; the `ResearchResult` maps onto data-model §9 fields.
- **PIT discipline** — cell-wise monotonicity (a cell goes `UNDEFINED → KNOWN` as
  the shared `as_of` crosses a filer's last input's availability); `PitFactor`
  never consumes revised cells.
- **Integration** — over the real backend (Phase 1→7 wired), a small explicit
  universe yields a `PitFactor` whose KNOWN cells match standalone Phase 7 calls;
  additive `Workspace.factor_engine` wiring does not disturb `facts()`/`filings()`
  / metrics.

## 16. Live SEC validation plan

Run **outside the repository**, fully **offline** over already-cached Phase 1
artifacts (standing constraint; live data under the sibling
`quantforge-recon-tmp/live/`). Reusing the Phase 5/7 validation filers — Apple
(320193), Tesla (1318605), Berkshire (1067983) — as an explicit universe,
`live_factor_validation.py`:

1. Builds registry → canonical → availability from stored artifacts (no network).
2. For the three-filer universe and each starter metric, over historical `as_of`
   instants and one universe-wide pinned `DatasetVersion`, computes `PitFactor` /
   `RevisedFactor`.
3. **Confirms on real data:** every KNOWN cell equals the standalone Phase 7 metric
   for that filer; UNDEFINED cells carry correct reasons and are never dropped;
   cell-wise PIT monotonicity holds as `as_of` advances; PIT and REVISED return
   distinct types and `reinterpret_as_pit` re-evaluates; determinism —
   recomputation yields byte-identical `research_result_id` + values; a
   transform's population excludes UNDEFINED cells and is exact; a persisted
   `ResearchResult` round-trips through the sidecar unchanged.
4. Records per-reason cell counts per factor, so universe coverage is auditable.

## 17. Assumptions

- **Explicit universe.** Callers supply resolved `company_id`s; Phase 8 does not
  discover membership (F1).
- **One reporting currency per factor.** Inherited from Phase 7 — a cross-currency
  cell was already `UNDEFINED(UNIT_MISMATCH)` upstream; Phase 8 never converts.
- **Single-period cross-section.** A factor compares one fiscal period across
  filers; multi-period composition is deferred (§13).
- **Phase 7 metrics are computable** for the filers (the metric layer exists; Phase
  8 only fans it out).
- **Starter concept-candidate lists remain `unvalidated`** (Phase 7 §18) — the
  factor's arithmetic and fan-out are exact and validated; the underlying concept
  selection carries Phase 7's confidence, unchanged.

---

*This document specifies the Phase 8 cross-sectional factor layer. Implementation
satisfies the determinism, fail-closed, immutability, provenance, and PIT/REVISED
invariants of data-model §12 (esp. 5, 18, 21, 27–30) and realizes the reserved §9
`ResearchResult`. Changes to the universe model, the factor result types, the
`ResearchResult` mapping, or the transform rules require updating this document
first. No implementation code is written until the §14 decisions are approved.*
