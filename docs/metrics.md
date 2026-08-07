# Financial Metrics & Research Layer (Phase 7)

The metrics layer computes **derived financial metrics** — ratios and simple
arithmetic combinations of canonical facts (current ratio, working capital,
debt-to-equity, gross margin, …) — as a deterministic, fail-closed, fully
provenanced function of the point-in-time knowledge state built in Phase 5. It is
the "Factors / computed signals" component that
[ARCHITECTURE.md](../ARCHITECTURE.md) has always listed as planned and that
[docs/data-model.md](data-model.md) §9 anticipates via the `ResearchResult`
`factor_definition_id + factor_version` pins.

Package: `src/quantforge/metrics/`.

This layer follows [docs/data-model.md](data-model.md) exactly — the
knowledge-state semantics (§KS), the point-in-time predicate and selection order
(§6.1, §6.3), the reproducible versioning + `ResearchResult` model (§9), the
provenance chain (§5), and the fail-closed / determinism invariants (§12). It
builds directly on the Phase 5 [`PointInTimeResolver`](point-in-time.md) and the
Phase 4 canonical [`Fact`](canonicalization.md). Section references below point
into the data model unless stated otherwise.

> **This layer computes, it never interprets truth and never invents data.** It
> resolves each formula input to a single canonical fact through the *existing*
> point-in-time resolver, checks units and periods, and applies exact-decimal
> arithmetic. When a required input is missing, nil, non-numeric, unit-mismatched,
> or a denominator is zero, the metric is **`UNDEFINED`** — a first-class result
> carrying *why*, never a guessed number, never `0`, never `NaN`/`Inf`. It never
> mutates a canonical fact, never resolves a restatement (Phase 5 already ordered
> them), and never crosses the PIT/REVISED boundary implicitly.

---

## 1. Contradiction analysis

Before any design, the requested work was checked against every prior invariant,
principle, and phase design. **No hard contradiction exists.** Four apparent
tensions were examined; each *resolves* under an explicit rule rather than
requiring a change to a prior layer. Had any been a true contradiction, this
section would say STOP and stop — it does not.

### 1.1 "Factors are out of scope" (data-model §22; Phase 4/5 docs)

Phases 4 and 5 repeatedly state factor construction / backtesting are "explicitly
out of scope." This is a **phase boundary, not a permanent prohibition.**
ARCHITECTURE.md lists **Factors — "Computed signals/features built strictly on
point-in-time data"** as a planned component, and data-model §9's `ResearchResult`
reserves `factor_definition_id + factor_version` precisely for it. Phase 7 is that
planned layer. What remains deferred and is **not** built here: backtesting,
portfolio construction, and any investment recommendation (§9.19 below). A single
per-period metric is a "computed signal on PIT data," squarely inside the planned
scope and outside the still-deferred set.

### 1.2 Phase 4's "no concept mapping, no synonym table" (canonicalization §4.1)

This is the load-bearing tension and it is resolved, not violated. Phase 4 refuses
concept-to-concept mapping **at the identity/fact layer**, because mapping there
would fabricate identity and destroy information: `Revenues` and
`RevenueFromContractWithCustomerExcludingAssessedTax` must stay distinct *facts*.

Phase 7 does **not** map concepts at the fact layer and **never rewrites a fact**.
It layers an **explicit, ordered, versioned, auditable concept-*selection*** on
top: a formula's input names an ordered candidate list of fully-qualified concepts
(e.g. revenue → `[RevenueFromContractWithCustomerExcludingAssessedTax, Revenues,
SalesRevenueNet]`), and the evaluator selects the **highest-priority candidate that
the company actually reported** for the period. Crucially:

- the candidate list is **declarative data hashed into the `formula_id`** (§6, §7)
  — it is versioned and reproducible, never code-hidden;
- selection **never invents** a concept the filer did not report; it only chooses
  among concepts present in the immutable facts, in a fixed documented order;
- the chosen candidate **and every other present candidate** are recorded in the
  metric's provenance (§9), so a selection is always auditable;
- if no candidate is present → `UNDEFINED` (fail closed), never a substitute.

So Phase 4's rule ("do not establish a concept mapping you cannot defend, and never
lose the original") is preserved: the original facts are untouched and
prefix-independent, and the *selection* is an explicit, defensible, versioned
research decision that lives above them — exactly where §9's `factor_definition`
belongs. See §7 for the full mechanism and §21 Decision D2 for the approval ask.

### 1.3 Invariant 28 — "`REVISED` is not a PIT source" (§KS.4, §KS.5)

A metric consumes fact *values*, which come only from the Phase 5 resolver, which
already enforces the PIT/REVISED type split (`PitValue` vs `RevisedValue`). Phase 7
**extends** invariant 28 to the metric layer with **distinct result types**
`PitMetricValue` and `RevisedMetricValue` (§5): a PIT metric is computed *only*
from `PitValue` inputs at one `as_of`; a REVISED metric *only* from `RevisedValue`
inputs over one pinned `DatasetVersion`. The two metric types are not
interchangeable; the only bridge is an explicit, re-evaluating
`RevisedMetricValue.reinterpret_as_pit(...)` (§5.2). No contradiction — the
guarantee is strengthened, not weakened.

### 1.4 Determinism / no-wall-clock / no-float vs. division

Ratios divide, and division can be non-terminating (`1/3`). Using binary `float`
would break the exact-decimal, byte-reproducible guarantee (canonicalization §4.4).
Resolved by a **single, pinned `decimal` context** (precision + rounding mode)
folded into the `MetricEngineVersion` (§8, §16). All arithmetic is exact `Decimal`;
the only rounding is the versioned division context, so the same inputs + same
engine version always produce byte-identical output. No wall-clock, no RNG, no
input-order dependence enters a metric. No contradiction.

### 1.5 Other invariants (immutability, no-DB, no-network, fail-closed)

- **Immutability / no mutation of prior layers.** Metrics are pure derived state.
  The only structural change is *additive* Workspace wiring for the already-existing
  Phase 5 availability layer (§11) — no prior store is edited, no fact rewritten.
- **No database / file-based.** Metrics are computed on demand (a deterministic
  function); the optional materialization is a file sidecar mirroring the Phase 5
  store, never a DB (§3, §10, Decision D1).
- **No network, no external financial APIs, no AI, no web UI.** The evaluator is
  pure and offline; there is **no unit/FX conversion** (a currency mismatch fails
  closed, §14). None of these are approached.
- **Fail closed.** `UNDEFINED` mirrors Phase 5's `UNKNOWN`: the safe, information-
  preserving answer whenever a defensible value cannot be computed (§13, §14).

**Conclusion: proceed.** The design below realizes Phase 7 without altering §12 or
any prior phase; the two tensions (§1.2, §1.3) are resolved by explicit, versioned,
auditable mechanisms surfaced for approval in §21.

## 2. Guiding principles

1. **Compute, never interpret truth.** The metric engine selects and combines
   facts; Phase 5 already decided *which* fact was knowable. Phase 7 never
   re-orders restatements or second-guesses availability.
2. **Undefined is a first-class result, never an exception or a fake number.**
   Missing input, nil input, non-numeric input, unit mismatch, and divide-by-zero
   all yield an `UNDEFINED` metric carrying a machine-readable reason — never `0`,
   `None`-that-looks-like-zero, `NaN`, or `Inf`.
3. **PIT and REVISED are impossible to confuse** — distinct metric result types,
   no default mode, inheriting the Phase 5 discipline (invariants 27–30).
4. **Exact, deterministic arithmetic.** `Decimal` only, a single pinned context,
   no `float`, no wall-clock, no RNG, no input-order dependence.
5. **Every metric is reproducible and versioned.** A metric pins its
   `formula_id`, `metric_engine_version_id`, and the `DatasetVersion` /`as_of`
   boundary — the §9 `ResearchResult` closed loop from raw bytes to result.
6. **Zero information loss.** Facts are never mutated or dropped; the result
   records every input fact, the selected concept, the discarded candidates, and
   the reason for any `UNDEFINED`.
7. **Reuse, don't reimplement.** Concept identity comes from Phase 4, PIT/REVISED
   selection from Phase 5, exact-decimal serialization from
   `canonical.numeric`, versioning shapes from `CanonicalFactVersion` /
   `AvailabilityPolicy`. Phase 7 adds only the formula model and the evaluator.
8. **Formulas are declarative data, not code.** A formula is inputs + an operation
   tree + unit/period rules, hashed into its identity — so a change is a new
   version, never a silent edit (mirrors `AvailabilityPolicy`).

## 3. Package layout

Each concern is a separate module with a single responsibility, matching the
Phase 4/5 module discipline.

| Module | Responsibility |
| --- | --- |
| `errors.py` | `MetricError` → `FormulaConfigurationError`, `MetricConsistencyError`. The fail-closed *configuration* vocabulary (data conditions are `UNDEFINED` results, **not** exceptions). |
| `version.py` | `MetricEngineVersion` — the deterministic evaluator version id `sha256(code_version, config_hash)`, folding in the pinned `decimal` context (§8). |
| `model.py` | `MetricStatus` (`KNOWN`/`UNDEFINED`), `UndefinedReason`, `MetricProvenance`, and the distinct result types `PitMetricValue` / `RevisedMetricValue` (§5). |
| `units.py` | `UnitExpectation` + unit-compatibility checks (monetary / shares / pure; currency equality). **No conversion, ever** (§14). Reuses the Phase 4 canonical unit fields. |
| `formula.py` | `FormulaDefinition`, `InputBinding` (ordered concept-candidate list + dimension/period/unit selectors), `Operation` (declarative op tree), and the content-addressed `formula_id` (§6, §7). |
| `registry.py` | `FormulaRegistry` — the built-in, versioned, declarative starter formulas; fail-closed on unknown `metric_key` (§6). |
| `resolve_input.py` | `resolve_input` — turn one `InputBinding` + a Phase 5 resolver + boundary into a single resolved fact value (or an `UNDEFINED` reason). Houses the concept-selection rule (§7). |
| `evaluate.py` | `MetricEvaluator` — the pure core: bind inputs, check units/periods, apply the operation under the pinned `decimal` context, fail closed to `UNDEFINED`. No I/O. |
| `engine.py` | `MetricEngine` — the façade composing Phase 4 canonical + Phase 5 availability into a resolver, then evaluating formulas for one filer. Company delegates here (§11). |
| `__init__.py` | Curated public exports (§10). |

Per Decision D1 (locked), there is **no** `store.py`: metrics are computed on
demand and never materialized in Phase 7. A metric store remains deferred (§19).

## 4. Architecture and data flow

There is no second HTTP client and no second storage system. Phase 7 sits at the
top of the existing chain:

```
SEC → ACQUISITION → REGISTRY → RAW XBRL → CANONICAL → AVAILABILITY/PIT → METRICS
      (Phase 1)     (Phase 2)  (Phase 3)  (Phase 4)     (Phase 5)        (Phase 7)
```

- **Phase 4** owns the immutable canonical `Fact` (with `obs_key`, `filing_id`,
  unit fields). Phase 7 reads facts read-only.
- **Phase 5** owns availability derivation and the `PointInTimeResolver` (the
  §6.1 gate + §6.3 selection, and the `PitValue`/`RevisedValue` split). Phase 7
  obtains a resolver from the Phase 5 façade and consumes its results — it never
  re-implements eligibility or selection.
- **Phase 7** adds the formula model + evaluator. It introduces no persistent
  store in its primary form (metrics are a pure function; §10). The optional
  `MetricStore` (Decision D1) is a file sidecar, never a database.

Data flow for one metric, one filer:

```
FormulaRegistry.get(metric_key)                 → FormulaDefinition (declarative, versioned)
        │
        ▼
MetricEngine.resolver_for(cik)                  → Phase 5 PointInTimeResolver (facts + availability)
        │
        ▼
for each InputBinding:                          resolve_input(binding, resolver, boundary, period)
    concept-select (ordered candidates)  ────────▶  PitValue | RevisedValue  (or UNDEFINED reason)
        │
        ▼
MetricEvaluator                                 unit check → period check → op tree
    (pinned Decimal context)                       ├─ any input UNDEFINED  → UNDEFINED(reason)
        │                                          ├─ unit/currency mismatch → UNDEFINED(UNIT_MISMATCH)
        │                                          ├─ denominator == 0     → UNDEFINED(DIVIDE_BY_ZERO)
        ▼                                          └─ else                 → exact Decimal value
PitMetricValue | RevisedMetricValue             (value or UNDEFINED, + full provenance)
```

The evaluator is a **pure function** of `(FormulaDefinition, resolved inputs,
engine version)`; the engine/façade does the I/O (reading facts + availability via
Phase 5). This mirrors the Phase 4 `Canonicalizer`-vs-`Ingestor` and Phase 5
`derive`-vs-`AvailabilityIngestor` split.

## 5. Financial metric model

A **metric** is *one value of one named formula, for one fiscal period, for one
filer, at one knowledge-state boundary*. Two result types keep PIT and REVISED
unmixable (invariant 28; §1.3).

```
MetricStatus         = KNOWN | UNDEFINED
UndefinedReason      = MISSING_INPUT | NIL_INPUT | NON_NUMERIC_INPUT
                     | UNIT_MISMATCH | DIVIDE_BY_ZERO | AMBIGUOUS_INPUT
                     | PERIOD_UNALIGNED
```

Both result types are frozen, slotted dataclasses sharing this shape:

| Field | Meaning |
| --- | --- |
| `metric_id` | Deterministic identity (§6.2). |
| `metric_key` | The formula name (e.g. `"current_ratio"`). |
| `formula_id` | The content hash of the deciding formula version. |
| `metric_engine_version_id` | The evaluator version (+ pinned decimal context). |
| `company_id` | Canonical filer identity (data-model §11). |
| `period` | The resolved fiscal period key (period_type + dates). |
| `status` | `KNOWN` or `UNDEFINED`. |
| `value_numeric_str` | Exact `Decimal` serialized via `canonical_decimal_str`; `None` when `UNDEFINED`. |
| `unit` | The output unit token (`pure` for a ratio, `USD` for working capital, …); `None` when `UNDEFINED`. |
| `reason` | `UndefinedReason` + a human string when `UNDEFINED`; empty when `KNOWN`. |
| `provenance` | `MetricProvenance` (§9): input fact ids, selected/other concepts, availability of each input, boundary. |

The **distinguishing** field:

- `PitMetricValue.as_of` — the timezone-aware historical instant (invariant 15).
- `RevisedMetricValue.dataset_version_id` — the pinned snapshot (§KS.2).

`UNDEFINED` is a *value*, not an error: a research sweep over many filers must
record "current ratio undefined for filer X at T because `LiabilitiesCurrent` was
not yet public" without aborting the sweep. This mirrors Phase 5's `UNKNOWN`
availability exactly.

### 5.1 A metric inherits its inputs' mode

A `PitMetricValue` is computed **only** from `PitValue` inputs resolved at the same
`as_of`; a `RevisedMetricValue` **only** from `RevisedValue` inputs over the same
`DatasetVersion`. The evaluator never mixes boundaries within one metric. This is
what makes the metric's PIT-ness structurally true rather than hoped-for.

### 5.2 Crossing REVISED → PIT is explicit and re-evaluates

The only bridge from revised to PIT is
`RevisedMetricValue.reinterpret_as_pit(engine, as_of)`, which **re-runs the whole
evaluation** at `as_of` over the same history (it does not rescale or reuse the
revised value). Like Phase 5's `RevisedValue.reinterpret_as_pit`, every crossing is
a visible, intentional, auditable call — never an implicit cast.

## 6. Formula registry

### 6.1 What a formula is (declarative data)

A `FormulaDefinition` is **data, not code** — the evaluator reads it to decide what
to fetch and how to combine:

```
FormulaDefinition {
  metric_key,            # stable public name, e.g. "current_ratio"
  description,           # human doc
  inputs: [InputBinding, ...],   # named operands (§7)
  operation: Operation,          # declarative op tree over input names (§6.3)
  output_unit: UnitExpectation,  # e.g. pure (ratio) or monetary (difference)
  period_model,          # SINGLE_INSTANT | SINGLE_DURATION | INSTANT+INSTANT ... (§6.4)
  confidence,            # verified-against-sec | heuristic | unvalidated  (§18)
  notes
}
```

Because the whole definition (including every concept-candidate list) is hashed
into `formula_id`, any change to a candidate list, an operation, or a unit rule
**necessarily** produces a new formula version — never a silent edit (mirrors
`AvailabilityRule` → `AvailabilityPolicy`, invariant 14).

### 6.2 Identity

```
formula_id                 = sha256(metric_key, definition_hash)
definition_hash            = sha256( canonical JSON of inputs+operation+units+period )
metric_engine_version_id   = sha256(code_version, config_hash)   # config_hash folds in the decimal context (§8)
metric_id                  = sha256( formula_id, metric_engine_version_id,
                                     company_id, period_key, boundary_key )
boundary_key               = "pit:" + as_of_utc      (PIT)
                           | "rev:" + dataset_version_id   (REVISED)
```

`metric_id` pins the *request* (formula version, engine, filer, period, boundary);
the value and provenance are the derived output. Re-running the same request
reproduces the same `metric_id` **and** the same value — determinism made
checkable. All ids are `sha256:`-prefixed, NUL-joined, matching §11.

### 6.3 The operation tree

`Operation` is a tiny closed, declarative algebra over input names and literals:

```
Operation = Ref(input_name)
          | Const(decimal_literal_str)
          | Add(Operation, Operation)
          | Sub(Operation, Operation)
          | Mul(Operation, Operation)
          | Div(numerator: Operation, denominator: Operation)
```

The algebra is intentionally minimal (the "computed signal" surface, not a
programming language): no user code, no lambdas, no arbitrary functions — so it is
fully serializable, hashable, and deterministic. Each leaf `Ref` names an
`InputBinding`. Evaluation is post-order under the pinned decimal context; `Div`
with a zero denominator yields `UNDEFINED(DIVIDE_BY_ZERO)` (§14).

### 6.4 Period model

Each formula declares a **primary period type** (`INSTANT` or `DURATION`), and each
`InputBinding` declares its own `period_kind` (`INSTANT` or `DURATION`). Alignment
is therefore explicit and never inferred:

- **`INSTANT` primary** — every input is an `instant` fact at the *same*
  `period_end` (e.g. current ratio, debt-to-equity). An input declared `DURATION`
  under an `INSTANT` primary is a formula-configuration error.
- **`DURATION` primary** — the requested fiscal period is a
  `(period_start, period_end)` span. A `DURATION` input resolves over that exact
  span; an `INSTANT` input resolves at the span's `period_end` — the *ending*
  balance, never an average. This single rule is what lets **asset turnover**
  (`Revenue` over the year ÷ *ending* total `Assets`) compose without any
  cross-period averaging.

If a formula's resolved inputs do not share the required period (a duration input
whose span differs, or an instant input not at `period_end`) → the metric is
`UNDEFINED(PERIOD_UNALIGNED)` — never silently combined across periods.
Cross-period constructs that need *multiple* periods (growth, trailing-twelve-month,
and *average*-balance denominators) are **deferred** (§19); the single-period
ending-balance form above is the only mixed-period shape Phase 7 implements.

### 6.5 The initial set (approved — Decision D6)

The eight metrics below are the approved initial registry. Each ships
`confidence = unvalidated` — the *arithmetic* is exact, but the *concept-selection*
lists are heuristic until validated against real filings (§18, mirroring
`AvailabilityPolicy` shipping `unvalidated`). Named concepts are `us-gaap` unless
noted; a bracketed `[...]` is an **ordered candidate list** (§7); `period` is the
formula's primary period type (§6.4).

| `metric_key` | Formula | Inputs (ordered candidates, consolidated) | period | output unit |
| --- | --- | --- | --- | --- |
| `current_ratio` | `AssetsCurrent / LiabilitiesCurrent` | `AssetsCurrent`; `LiabilitiesCurrent` | INSTANT | `pure` |
| `quick_ratio` | `(AssetsCurrent − Inventory) / LiabilitiesCurrent` | `AssetsCurrent`; `[InventoryNet, InventoryFinishedGoodsNetOfReserves]`; `LiabilitiesCurrent` | INSTANT | `pure` |
| `working_capital` | `AssetsCurrent − LiabilitiesCurrent` | `AssetsCurrent`; `LiabilitiesCurrent` | INSTANT | `USD` |
| `gross_margin` | `(Revenue − CostOfRevenue) / Revenue` | Revenue `[RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet]`; CostOfRevenue `[CostOfRevenue, CostOfGoodsAndServicesSold, CostOfGoodsSold]` | DURATION | `pure` |
| `operating_margin` | `OperatingIncomeLoss / Revenue` | `OperatingIncomeLoss`; Revenue (as above) | DURATION | `pure` |
| `net_margin` | `NetIncomeLoss / Revenue` | `NetIncomeLoss`; Revenue (as above) | DURATION | `pure` |
| `debt_to_equity` | `Liabilities / StockholdersEquity` | `Liabilities`; `StockholdersEquity` | INSTANT | `pure` |
| `asset_turnover` | `Revenue / Assets` | Revenue (as above); `Assets` | DURATION | `pure` |

Notes on the mixed forms:

- `quick_ratio`, `gross_margin`, `operating_margin`, `net_margin`, and
  `asset_turnover` all exercise the ordered candidate mechanism (§7) and its
  ambiguity / fail-closed handling; the plain-concept metrics (`current_ratio`,
  `working_capital`, `debt_to_equity`) exercise the single-candidate path.
- `asset_turnover` is the one **mixed-period** metric: a `DURATION` `Revenue`
  numerator over the fiscal span ÷ an `INSTANT` `Assets` denominator at that span's
  `period_end` (the *ending* balance, §6.4). It deliberately uses ending — not
  average — assets, because an average needs two periods (deferred, §19); the
  choice is documented on the formula so it is auditable, not hidden.

Adding a metric is adding a `FormulaDefinition`; **no company data is ever
hardcoded** and no formula names a CIK/ticker.

## 7. Metric input resolution & the concept-selection rule

An `InputBinding` turns a formula operand into exactly one resolved fact value (or
an `UNDEFINED` reason):

```
InputBinding {
  name,                    # operand name referenced by the Operation
  concept_candidates: [(taxonomy, local_name), ...],  # ORDERED, explicit, versioned (§1.2, §7.0)
  period_kind,             # INSTANT | DURATION — how this input aligns (§6.4)
  dimension_selector,      # CONSOLIDATED (dimensions_hash == "") by default (§7.2)
  unit_expectation,        # monetary | shares | pure  (§8/§14)
}
```

### 7.0 Candidates are matched by `(taxonomy, local_name)`, not a fixed obs_key

A Fact's `obs_key` embeds the *year-versioned* concept URI (e.g.
`{http://fasb.org/us-gaap/2023}Revenues`) and the filing's *raw structural*
`unit_ref` — neither of which a formula can know ahead of time. So a candidate is
declared as a `(taxonomy, local_name)` pair (e.g. `(US_GAAP, "Revenues")`) and
matched against the resolved facts by the Phase 4 `taxonomy` + `concept.local_name`
fields — prefix- and taxonomy-version-independent, exactly the identity discipline
Phase 4 already guarantees. The evaluator never fabricates an `obs_key`; it selects
among the obs_keys the filer actually produced.

Resolution (`resolve_input`) is deterministic:

1. **Find matching obs_keys.** Scan the filer's facts for those matching the
   binding's `period_kind` and the consolidated dimension (`dimensions_hash ==
   sha256("")`), whose period aligns with the request (§6.4), and group the
   *distinct* `obs_key`s by which candidate `(taxonomy, local_name)` they match
   (§7.0). A period-eligible fact carrying a recognizable currency `unit` narrows
   the monetary candidates without ever converting (§14).
2. **Resolve via Phase 5 (mode-consistent).** For each matched obs_key call the
   resolver in the metric's mode — `knowledge_state_as_of(obs_key, as_of)` (PIT) or
   `revised_truth(obs_key, dataset_version)` (REVISED). Phase 5 returns at most one
   known fact per obs_key (its §6.3 total order already handled restatements).
3. **Select first present (fixed order).** Walking the candidate list in order, the
   first candidate that yields a `KNOWN` numeric fact wins. The choice is
   deterministic (list order), never a guess, and only ever selects a concept the
   filer actually reported.
4. **Fail closed on absence.** If no candidate yields a known numeric fact →
   `UNDEFINED(MISSING_INPUT)`. A candidate that resolves to a **nil** fact →
   `UNDEFINED(NIL_INPUT)` (nil ≠ zero, invariant 25). A candidate present only as
   `value_text` → `UNDEFINED(NON_NUMERIC_INPUT)`.
5. **Record everything.** Provenance stores the selected concept, its `fact_id` and
   availability, **and** every other candidate that was also present (§9), so the
   selection and any latent ambiguity are auditable.

### 7.1 Ambiguity handling (Decision D3)

If two or more candidate concepts are simultaneously present for the same period
with **different** values (a possible concept collision, e.g. both `Revenues` and
`RevenueFromContractWithCustomer…` reported), the default is **first-in-list wins,
with all present candidates recorded** in provenance. A stricter alternative —
fail closed with `AMBIGUOUS_INPUT` whenever >1 candidate is present with differing
values — is offered for approval (§21 D3). Identical values across candidates are
never ambiguous.

### 7.2 Dimension selection

By default an input selects the **consolidated** observation (`dimensions_hash ==
""`, the undimensioned context) — the entity-level figure. Segment/dimensioned
metrics require an explicit dimension selector and are **deferred** (§19); the
selector field is reserved now so the model does not change later. `security_id`
stays `None` (Phase 4 defers the security master); per-share metrics are therefore
deferred (§19).

## 8. Versioning strategy

Three version pins, composing with the existing ones, close the §9 reproducibility
loop:

- **`FormulaDefinition` / `formula_id`** — immutable, content-addressed. Changing a
  candidate list, operation, unit rule, or period model yields a new `formula_id`;
  a definition is **never mutated in place** (invariant 14 analogue). Re-declaring
  an identical formula reproduces the same id (invariant 20 analogue).
- **`MetricEngineVersion` / `metric_engine_version_id`** —
  `sha256(code_version, config_hash)`, mirroring `CanonicalFactVersion`. The
  `config_hash` **folds in the pinned `decimal` context** (precision + rounding
  mode, §16), because that context can change a division result. Changing the
  evaluator logic or the context bumps the version, producing new, distinct
  metrics while old ones remain valid.
- **`DatasetVersion` (reused from Phase 5)** pins the exact facts + normalizer +
  availability-policy set a metric was computed over. A REVISED metric cites it
  directly; a PIT metric cites it plus the `as_of`.

A metric therefore reproduces a `ResearchResult` (§9): `factor_definition_id ≡
formula_id`, `factor_version ≡ metric_engine_version_id`, plus
`dataset_version_id`, `as_of_timestamp`, `query_params` (metric_key, period), and a
`result_hash`. Re-running with the same pins reproduces the value.

## 9. Provenance

Every metric — `KNOWN` or `UNDEFINED` — carries a `MetricProvenance` giving the
unbroken chain from the metric back to canonical facts and, through them, to SEC
bytes (§5):

```
MetricProvenance {
  formula_id, metric_engine_version_id,
  boundary: PIT(as_of) | REVISED(dataset_version_id),
  inputs: [ InputResolution {
      name,
      selected_concept_clark,          # or null when UNDEFINED(MISSING_INPUT)
      selected_fact_id,                # → Phase 4 Fact → full FactProvenance → SEC bytes
      selected_availability,           # the FilingAvailability triple used
      present_candidates: [clark, ...],# every candidate that resolved (audit; §7)
      status: KNOWN | UNDEFINED(reason)
  }, ... ],
  result_status, result_reason
}
```

Given a metric you can recover, per input, the exact canonical `Fact` (and hence
its `raw_fact_id` → `raw_document_id` → `source_artifact_sha256` → `source_url`),
the availability record and policy that made it eligible, the selected concept and
the discarded ones, and the formula + engine + dataset that combined them. **Zero
information is lost:** an `UNDEFINED` metric records exactly which input failed and
why (§13, §15).

## 10. Public API

The metric layer keeps the "impossible to confuse" naming discipline of Phase 5 —
no `get_metric()` whose behavior depends on a nullable `as_of`.

```python
# Low-level (engine), one filer:
engine = MetricEngine(workspace)  # composes Phase 4 + Phase 5 (§11)
pit = engine.metric_as_of("current_ratio", cik, period, as_of)  # → PitMetricValue
rev = engine.revised_metric(
    "current_ratio", cik, period, dataset_version
)  # → RevisedMetricValue
```

Curated top-level exports (added to `quantforge/__init__.py`), stable public
surface only — internal modules stay private:

```python
from quantforge import (
    Company,
    PitMetricValue,
    RevisedMetricValue,  # NEW: distinct metric result types
    MetricStatus,  # NEW
)
from quantforge.metrics import (
    FormulaRegistry,
    FormulaDefinition,
)  # for authoring/inspection
```

`PitMetricValue` / `RevisedMetricValue` are re-exported at the top level (like
`PitValue` / `RevisedValue`) so the PIT-vs-revised distinction is visible at the
import site. `FormulaRegistry` is exported so callers can enumerate available
metrics without reaching into internals.

## 11. Company API integration

The metric API composes onto `Company` naturally — and requires only **additive**
wiring, no mutation of any prior layer.

`Workspace` currently wires Phase 1/2/4 + the identity resolver, but **not** the
Phase 5 availability layer. Phase 7 extends `Workspace` to also build the existing
`AvailabilityStore` and `AvailabilityIngestor` under a new `<root>/availability/`
directory (the layout Phase 5 already uses), plus a lazily-constructed
`MetricEngine`:

```
<root>/sec/           # Phase 1 artifacts (authoritative)
<root>/registry/      # Phase 2 filing registry
<root>/canonical/     # Phase 4 canonical facts
<root>/availability/  # Phase 5 derived availability (NEWLY WIRED, not new code)
```

`Company` gains PIT/REVISED-disciplined methods that delegate to the engine:

```python
apple = Company.resolve("AAPL")

# Point-in-time metric — requires a timezone-aware as_of (invariant 15):
cr = apple.metric_as_of("current_ratio", period, as_of)  # → PitMetricValue

# Revised metric — requires an explicit pinned snapshot:
cr_now = apple.revised_metric(
    "current_ratio", period, dataset_version
)  # → RevisedMetricValue
```

`Company` stays a **thin façade** (its current contract): it owns no metric logic,
delegating to `MetricEngine`, exactly as `filings()`/`facts()` delegate to the
registry/canonical stores. The existing `Company.facts()` / `filings()` are
unchanged. There is **no** default-mode `metric()` accessor — the caller must name
PIT or REVISED, preserving invariant 27 at the front door.

## 12. PIT vs REVISED behavior

- **Two methods, no default (invariant 27).** `metric_as_of(...)` (PIT) requires a
  timezone-aware `as_of`; `revised_metric(...)` (REVISED) requires a
  `DatasetVersion`. A naive `as_of` raises `ModeError` via the Phase 5 timestamp
  choke point.
- **Two result types (invariant 28).** `PitMetricValue` ≠ `RevisedMetricValue`; a
  backtest/factor typed to `PitMetricValue` cannot be handed a revised metric.
- **Mode consistency (§5.1).** Every input of a PIT metric is resolved at the same
  `as_of`; every input of a REVISED metric over the same `DatasetVersion`. Never
  mixed within a metric.
- **Past-closed & monotonic (invariant 29).** A PIT metric at `T` depends only on
  facts available `≤ T`. As `T` advances, an `UNDEFINED(MISSING_INPUT)` metric can
  *become* `KNOWN` once its last required input is public, and a `KNOWN` metric can
  *change* when a restatement of an input becomes public — always reflecting what
  was knowable then, never the future.
- **REVISED is reproducible, not wall-clock (invariants 21, 30).** It resolves at
  the Phase 5 ingestion frontier over a pinned `DatasetVersion` — deterministic.
- **Explicit crossing only (§5.2).** `reinterpret_as_pit` re-evaluates at `as_of`.

Worked example (extends point-in-time §5.3). Current ratio for FY2019, with
`AssetsCurrent` and `LiabilitiesCurrent` both first public 2020-03-01, and
`AssetsCurrent` later restated (public 2022-05-01):

| Query | Result |
| --- | --- |
| `metric_as_of(current_ratio, FY2019, 2020-01-01)` | `UNDEFINED(MISSING_INPUT)` — neither input public yet |
| `metric_as_of(current_ratio, FY2019, 2021-01-01)` | ratio from the **original** current assets/liabilities |
| `metric_as_of(current_ratio, FY2019, 2023-01-01)` | ratio using the **restated** current assets |
| `revised_metric(current_ratio, FY2019, snapshot)` | ratio using the latest known inputs at the frontier |

## 13. Missing-data policy

Fail closed, never impute (data-model §PA.3 posture, applied to metrics):

- **Any required input not PIT/REVISED-eligible or absent at the boundary** →
  `UNDEFINED(MISSING_INPUT)`. Never substituted with `0`, a prior period, a peer,
  or a guessed concept.
- **Nil input** (`is_nil = true`) → `UNDEFINED(NIL_INPUT)`. An explicit "reported
  nothing" is information, but it is **not** a number to divide or subtract, and
  **not** zero (invariant 25). We refuse to fabricate arithmetic from it.
- **Non-numeric input** (only `value_text`) → `UNDEFINED(NON_NUMERIC_INPUT)`.
- **Concept absent from the filer's report** → covered by `MISSING_INPUT` after all
  ordered candidates are exhausted (§7).
- **Partial availability.** If some but not all inputs are known at `T`, the metric
  is `UNDEFINED` (a ratio needs both operands) — never computed from a subset.

Every `UNDEFINED` names the offending input(s) and reason in provenance (§9), so
"why is this metric missing?" is always answerable without re-deriving.

## 14. Divide-by-zero & unit policy

**Divide-by-zero.** A `Div` whose denominator resolves to exactly `Decimal(0)`
yields `UNDEFINED(DIVIDE_BY_ZERO)` — **never** `Inf`, `NaN`, or a sentinel number.
The check is exact (`== 0` on a `Decimal`), so a real reported denominator of `0`
(e.g. zero current liabilities) is correctly *undefined*, distinct from a *missing*
denominator (`MISSING_INPUT`). A zero **numerator** with a nonzero denominator is a
legitimate `KNOWN` result of `0`. Because arithmetic is `Decimal`, no floating
`inf`/`nan` can ever arise.

**Units (no conversion, ever).** Each input declares a `UnitExpectation`
(monetary / shares / pure); the operation declares its output unit:

- Operands to `Add`/`Sub` must share the same unit **and** currency; a mismatch
  (e.g. `USD` + `shares`, or `USD` + `EUR`) → `UNDEFINED(UNIT_MISMATCH)`.
- `Div` of two same-currency monetary operands → dimensionless `pure` (a ratio).
- **No FX and no unit conversion exist in this layer** ("no external financial
  APIs"): a cross-currency metric fails closed rather than convert. Unit identity
  reuses the Phase 4 canonical `unit` / `currency` / `unit_ref` fields — Phase 7
  compares, it never rewrites, a unit.

## 15. Zero-information-loss guarantees

- **Facts are never mutated or deleted.** The Phase 4 store is read-only here; the
  Phase 5 sidecar and Phase 1 blobs are untouched. Metrics are pure derived state,
  deletable and rebuildable to byte-identical output.
- **`UNDEFINED` is never a silent null.** It always carries an `UndefinedReason`
  and the failing input(s) — the *absence* of a computable value is itself
  recorded information (parallel to Phase 5 `UNKNOWN`).
- **Concept selection is fully transparent.** The chosen concept **and** every
  other present candidate are recorded (§9), so a selection never hides a
  discarded alternative.
- **The formula is captured, not referenced by name only.** `formula_id` hashes the
  full declarative definition, so the exact candidates/operation/units that
  produced a metric are reconstructable and auditable.
- **No lossy rounding beyond the versioned division context.** Additions and
  subtractions are exact; only division rounds, under a pinned, versioned context
  (§16) — and that context is part of the reproducibility pins.

## 16. Determinism requirements

- **Exact `Decimal` only** — no binary `float` anywhere. Values are read from the
  Phase 4 `value_numeric_str` (already base-unit, scale/sign folded) and serialized
  with `canonical.numeric.canonical_decimal_str`, so equal magnitudes are
  byte-identical.
- **One pinned decimal context.** Division uses a fixed `decimal.Context`
  (proposed: **precision 34 significant digits, `ROUND_HALF_EVEN`** — Decision D5),
  applied via an explicit `localcontext`, never the ambient process context. The
  context is folded into `metric_engine_version_id`, so a change to it is a new,
  distinguishable version.
- **No wall-clock, no RNG, no input-order dependence.** `metric_id`,
  `formula_id`, and every value are pure functions of content. Inputs are processed
  in the formula's declared order; result serialization uses `sort_keys=True`.
- **Reproducible by construction.** Same `(formula_id, engine_version,
  dataset_version, as_of/boundary, period)` ⇒ same `metric_id` **and** same value,
  on any machine. `REVISED` "now" is the Phase 5 ingestion frontier, not a clock.

## 17. Live SEC validation plan

Run **outside the repository**, fully **offline** over already-cached Phase 1
artifacts (per the standing constraint; live data under the sibling
`quantforge-recon-tmp/live/`). Reusing the Phase 5 validation filers — Apple
(320193), Tesla (1318605), Berkshire (1067983) — `live_metric_validation.py`:

1. Builds registry → canonical → availability from stored artifacts (no network).
2. For each filer and each starter metric, over a set of historical `as_of`
   instants and one pinned `DatasetVersion`, computes `PitMetricValue` /
   `RevisedMetricValue`.
3. **Confirms on real data:**
   - every `KNOWN` metric's inputs trace to real PIT-eligible facts, and the
     selected concept is one the filer actually reported;
   - `UNDEFINED` results carry a correct reason (e.g. pre-availability `MISSING_
     INPUT`; a genuinely zero denominator, if any, `DIVIDE_BY_ZERO`);
   - PIT monotonicity: the `KNOWN`-set is non-decreasing as `as_of` advances, and a
     restatement of an input flips the value only after its availability;
   - PIT and REVISED return **distinct types**; `reinterpret_as_pit` re-evaluates;
   - determinism: recomputation yields byte-identical `metric_id` + value; the
     optional store (if built) round-trips byte-identically regardless of order;
   - **spot-check against the raw filings** (hand-computed current ratio for a
     known Apple 10-K), **never** against an external financial API.
4. Records counts (KNOWN vs each UNDEFINED reason per metric per filer) so the
   concept-selection lists can be promoted from `unvalidated` toward
   `verified-against-sec` (§18).

## 18. Testing strategy

Per-module unit tests, matching the Phase 4/5 rigor; **all existing tests continue
to pass** (Phase 7 is additive).

- **`version.py`** — `metric_engine_version_id` determinism and sensitivity to the
  decimal context.
- **`units.py`** — monetary/shares/pure compatibility; same-currency vs
  cross-currency; ratio→`pure`; mismatch → `UNIT_MISMATCH`.
- **`formula.py` / `registry.py`** — `formula_id` determinism and sensitivity to
  every declarative field (candidate list order, operation, units, period);
  unknown `metric_key` → `FormulaConfigurationError`; the op-tree round-trips.
- **`resolve_input.py`** — ordered concept selection (first present wins);
  fail-closed `MISSING_INPUT` when no candidate present; `NIL_INPUT` for a nil fact;
  `NON_NUMERIC_INPUT`; consolidated-dimension selection; present-candidate audit
  recording; the D3 ambiguity behavior.
- **`evaluate.py` (adversarial suite)** — the mandated data conditions each map to
  the right result: missing input, nil input, non-numeric input, unit mismatch,
  currency mismatch, **zero denominator → `DIVIDE_BY_ZERO`** (and zero numerator →
  `KNOWN 0`), period misalignment, exact-`Decimal` division determinism (`1/3`
  under the pinned context), byte-identical re-computation, and full provenance
  completeness (selected + discarded candidates present).
- **PIT/REVISED discipline** — distinct result types; naive `as_of` rejected;
  `metric_as_of` vs `revised_metric` never interchangeable; `reinterpret_as_pit`
  re-resolves rather than reusing the revised value; PIT monotonicity (a metric
  goes `UNDEFINED → KNOWN` as `as_of` crosses the last input's availability; a
  restatement flips the value only after its availability).
- **Company/Workspace integration** — `<root>/availability/` wiring is additive and
  does not disturb `facts()`/`filings()`; `Company.metric_as_of` /
  `revised_metric` delegate to the engine and return the correct types.

## 19. Deferred scope

Explicitly **not** built in Phase 7 (surfaced, not silent):

- **Backtesting, portfolio construction, trading strategies, and any investment
  recommendation** — still out of scope (data-model §9.19); Phase 7 stops at the
  single computed signal.
- **Cross-period metrics** — growth rates, trailing-twelve-month, and averaging
  metrics (e.g. asset turnover needs *average* assets across two instants). These
  require multi-period composition; the `period_model` reserves room but the
  constructs are deferred.
- **Segment / dimensioned metrics** — the `dimension_selector` is reserved but only
  `CONSOLIDATED` is implemented now.
- **Per-share metrics** (EPS-style) — require `security_id`, which Phase 4
  deliberately defers (no external security master).
- **Unit / FX conversion** — never in this layer; cross-currency fails closed.
- **A concept-selection map beyond the starter formulas** — new metrics/candidate
  lists are added as new versioned `FormulaDefinition`s, validated per §18.
- **Persistent metric materialization** — locked to on-demand computation
  (Decision D1); no metric store is built in Phase 7.

## 20. Assumptions

- **XBRL-era filings.** As in Phase 5, the meaningful population is XBRL-era; pre-
  XBRL filers largely lack PIT-eligible facts, so their metrics are `UNDEFINED`.
- **Consolidated = the undimensioned context** (`dimensions_hash == ""`), matching
  the Phase 4/recon finding that the entity-level figure is the default context.
- **Single reporting currency per metric.** The starter formulas assume `USD`
  operands; a cross-currency operand fails closed rather than convert.
- **The starter concept-candidate lists are provisional heuristics.** The
  arithmetic is exact and validated; the *selection* lists are `unvalidated` until
  checked against real filings (§17/§18). They reflect common us-gaap usage
  observed in reconnaissance, not an authoritative taxonomy mapping.
- **Phase 5 availability is already derivable** for the filer (the availability
  layer exists; Phase 7 only wires it into the Workspace/Company path).

## 21. Architectural decisions (approved)

The following load-bearing choices were surfaced for approval and are now **locked**
(mirroring how earlier phases recorded Decisions). Implementation follows them
exactly and does not expand scope beyond them.

- **D1 — Storage model: LOCKED — compute-on-demand; storage deferred.** Metrics are
  a pure function of facts + availability + formula, computed on each query. No
  persistent metric store is built in Phase 7; the `store.py` sidecar is deferred
  (dropped from the delivered package layout, §3). This sidesteps the unbounded-
  `as_of` storage problem and keeps the layer minimal.
- **D2 — Concept selection: LOCKED — versioned candidate lists.** The explicit,
  ordered `(taxonomy, local_name)` candidate list is hashed into `formula_id`
  (§6.2, §7). Any change to a list is a new formula version. This is the mechanism
  that lets Phase 7 name "revenue" without violating Phase 4's no-mapping-at-the-
  fact-layer rule.
- **D3 — Ambiguity handling: LOCKED — deterministic first-valid selection.** The
  first candidate in list order that yields a `KNOWN` numeric fact wins; **all**
  present candidates (selected + discarded) are recorded in provenance (§9). The
  `AMBIGUOUS_INPUT` reason is retained in the model vocabulary for future strict
  policies but is not raised by the default selector.
- **D4 — Distinct metric result types: LOCKED.** `PitMetricValue` and
  `RevisedMetricValue` are separate frozen types (extending invariant 28 to
  metrics), making look-ahead a type error rather than a runtime check.
- **D5 — Decimal context: LOCKED — precision 34, `ROUND_HALF_EVEN`.** The pinned
  division context is folded into `metric_engine_version_id` (§8, §16); changing it
  bumps the engine version.
- **D6 — Initial formula set: LOCKED — eight metrics.** Current ratio, quick ratio,
  working capital, gross margin, operating margin, net margin, debt-to-equity, and
  asset turnover (§6.5), all shipping `confidence = unvalidated`.

---

*This document specifies the Phase 7 metrics layer. Implementation satisfies the
determinism, fail-closed, immutability, provenance, and PIT/REVISED invariants of
data-model §12 (esp. 5, 18, 21, 25, 27–30). Changes to the formula model, the
concept-selection rule, or the metric result types require updating this document
first.*
