# Universe Construction Layer

The **universe-construction layer** (Phase 9.2) turns a *declarative statement of
intent* into a resolved, deterministic [`Universe`](universe.md). Where Phase 9.1
answers "*hold this explicit list of filers*", Phase 9.2 answers "*resolve the
filers that satisfy these ordered selection rules, at this point in time*" — and
records exactly how it did so.

```python
from quantforge import (
    UniverseSpecification,
    UniverseBuilder,
    ExplicitCompanyFilter,
    CompanyMetricFilter,
)
from quantforge.universe import ComparisonOperator
from quantforge.metrics import MetricPeriod

spec = UniverseSpecification(
    name="positive-working-capital",
    filters=(
        ExplicitCompanyFilter(identifiers=["AAPL", "MSFT", "NVDA"]),
        CompanyMetricFilter(
            metric_key="working_capital",
            period=MetricPeriod.instant("2023-09-30"),
            operator=ComparisonOperator.GT,
            threshold="0",
        ),
    ),
)

builder = UniverseBuilder(workspace)
result = builder.build_as_of(spec, as_of=some_utc_datetime)

result.universe  # a Phase 9.1 Universe (ordered, de-duplicated members)
result.construction  # a reproducible UniverseConstruction provenance record
```

Package: `src/quantforge/universe/` (the construction modules `specification.py`,
`filters.py`, `builder.py`, `construction.py`, `identity.py`, `version.py`).

This layer **adds no company-identifier system, no metric arithmetic, and no
storage or external I/O**. It *composes* the existing phases: company resolution is
the same [`CompanyResolver`](company-api.md) that backs `Company.resolve(...)`;
metric evaluation is the existing [Phase 7 metric engine](metrics.md) over the
[Phase 5 point-in-time knowledge state](point-in-time.md); membership is the
existing Phase 9.1 [`Universe`](universe.md). The construction layer contributes
only three things: the *rule vocabulary*, the *ordered narrowing*, and the
*provenance packaging*.

---

## 1. Three types, three responsibilities

The layer is a strict separation of *request*, *evaluation*, and *result* — the
same discipline the metric and factor layers use (a versioned definition, a
fail-closed engine, a content-addressed result):

| | Role | Holds data? | Holds a boundary? |
| --- | --- | --- | --- |
| **`UniverseSpecification`** | the immutable, serializable *request* — a name, a schema version, and an **ordered** list of selection filters | no | no |
| **`UniverseBuilder`** | the fail-closed *engine* — evaluates a specification at one PIT/REVISED boundary, composing the resolver and metric engine | — | it *is* handed the boundary |
| **`Universe` + `UniverseConstruction`** | the *result* — the resolved membership plus a reproducible provenance record | yes | records which one |

The point of the split: a `UniverseSpecification` says *what* to build and can be
serialized, versioned, diffed, and stored on its own — it is deliberately
ignorant of *when* it will be evaluated or *against which snapshot*. Evaluating it
at a point in time (`build_as_of`) is a separate, explicit step from evaluating it
over a pinned revised snapshot (`build_revised`); the two produce distinct results
that are impossible to confuse (invariant 27, "no default mode").

## 2. Filters: the selection vocabulary

A specification's `filters` are applied **left-to-right**. The first filter must be
a *source* — it establishes the initial membership from nothing; later filters only
*narrow* it. There is **no implicit universe**: a construction that begins with a
narrowing rule (or declares no filters at all) is a specification defect and is
raised, never silently interpreted as "everyone".

Three initial filter types are implemented (and nothing more — no ranking, no
weighting, no optimization, no backtesting):

### `ExplicitCompanyFilter` — the source

```python
ExplicitCompanyFilter(identifiers=["AAPL", "MSFT", "NVDA"])
ExplicitCompanyFilter(identifiers=["320193", "789019"], by="cik")
```

Resolves an explicit list of tickers / CIKs / names through the **existing**
identity layer into first-seen-ordered, de-duplicated members. `by` optionally
forces the interpretation for every identifier, exactly like
`Company.resolve(..., by=...)`.

- **As the source** (run first, on empty input) the resolved set *is* the seed
  membership.
- **As a later filter** it acts as an *intersecting whitelist*: candidates not in
  its resolved set are excluded with reason `NOT_IN_EXPLICIT_SET`.

### `CompanyMetricFilter` — a point-in-time threshold

```python
CompanyMetricFilter(
    metric_key="working_capital",
    period=MetricPeriod.instant("2023-09-30"),
    operator=ComparisonOperator.GT,
    threshold="0",  # exact decimal string, matching the metric layer
)
```

Keeps candidates whose **registered Phase 7 metric** satisfies the threshold at the
build's boundary, evaluated through the **existing** metric engine:

- metric `UNDEFINED` at the boundary (input not yet public, missing data, …) →
  excluded, reason `METRIC_UNDEFINED` (detail = the undefined reason);
- metric `KNOWN` but the comparison is false → excluded, reason
  `METRIC_THRESHOLD_NOT_MET` (detail = the value);
- metric `KNOWN` and the comparison holds → kept.

`threshold` is an exact decimal *string*, matching the metric layer's
`value_numeric_str` discipline — no float ever enters a comparison.

> **On `market_cap`.** A common request is "market cap > \$X". QuantForge derives
> its metrics **only** from SEC filings, which carry no share prices, so no
> `market_cap` formula exists in the registry. `CompanyMetricFilter` works over
> *any registered metric* and validates `metric_key` against the live
> `FormulaRegistry` at build time — so a specification naming `market_cap` (or any
> not-yet-modeled metric) **fails closed** with a clear error rather than silently
> excluding everyone. This is the fabricated-data guard (Principle 8) surfacing at
> the construction boundary. The eight built-in metrics
> (`current_ratio`, `quick_ratio`, `working_capital`, `gross_margin`,
> `operating_margin`, `net_margin`, `debt_to_equity`, `asset_turnover`) are all
> available; see [metrics.md](metrics.md).

### `SectorFilter` — a caller-supplied classification

```python
from quantforge.universe import SectorClassification, SectorFilter

classification = SectorClassification(
    scheme="gics",
    assignments={"cik:0000320193": "Technology", "cik:0000789019": "Technology"},
)

SectorFilter(scheme="gics", sector="Technology")  # operator defaults to ==
```

QuantForge stores **no** sector / SIC / industry data, and this layer never
fabricates it or reaches for an external API. A `SectorFilter` therefore matches
against a **caller-supplied**, content-addressed `SectorClassification` — an
explicit `company_id → sector` mapping under a named `scheme`, passed to the build
via `classifications=(...)`. This mirrors the Phase 9.1 doctrine that membership is
always explicit and caller-supplied.

- no classification supplied for the referenced `scheme` → a **specification
  defect** (raised): the caller asked for a sector rule but supplied no data source;
- company absent from the classification → excluded, reason
  `SECTOR_UNCLASSIFIED` — a data condition, never guessed;
- classified but the comparison (`==` / `!=`) is false → excluded, reason
  `SECTOR_MISMATCH` (detail = the actual sector).

## 3. The two build modes

The builder exposes exactly two evaluation methods — never a default:

```python
builder.build_as_of(spec, as_of=aware_utc_datetime)  # point-in-time
builder.build_revised(spec)  # over a pinned snapshot
builder.build_revised(spec, dataset_version=explicit)  # ... or a supplied one
```

- **`build_as_of`** evaluates every metric filter at a single point-in-time
  `as_of` (timezone-aware; a naive instant is rejected by the Phase 5 choke point).
  A company whose metric is not yet public at `as_of` is *excluded and recorded*,
  never raised.
- **`build_revised`** evaluates over one universe-wide
  [`DatasetVersion`](point-in-time.md). If none is supplied, the builder derives it
  from the specification's explicit *source* members as the union of their per-filer
  snapshots (the same construction the [factor engine](metrics.md) uses), so the
  whole construction is pinned to one reproducible state. Members normalized under
  differing transformation versions fail closed — a single universe-wide snapshot
  requires one normalizer.

A PIT construction and a REVISED construction of the same specification carry
**distinct** `construction_id`s (the boundary is part of the identity) even when
they happen to resolve to the same membership.

## 4. Data conditions vs. specification defects

The layer keeps two failure kinds sharply separate — the same discipline as
Phases 7–8:

- A **data condition** — a metric `UNDEFINED`, a threshold not met, a company with
  no sector under the supplied classification — is **never** an exception. The
  company is dropped and recorded as an `ExcludedCompany` with a machine-readable
  `ExclusionReason`, so *who was dropped, by which filter, and why* is always
  answerable (zero information loss).
- A **specification defect** — a narrowing filter before any source, an unknown
  `metric_key`, a sector rule with no classification, a malformed serialized filter,
  a non-numeric threshold — *is* raised, as `UniverseSpecificationError`.

There is one further fail-closed case at the boundary between the two: if *every*
candidate is filtered out, the **final universe is empty**, which fails closed with
`UniverseConfigurationError` — exactly as Phase 9.1 (a universe over nobody is a
configuration bug, not an empty result). Every drop that led there is still
preserved in the exclusions, so the failure is fully explained.

## 5. Determinism & content-addressing

Every identity in the layer is a `sha256:`-prefixed content hash, computed with the
same canonical, NUL-separated scheme used across the project (`quantforge.sec.
artifacts.sha256_hex`), with a domain tag so id spaces cannot collide:

| id | hashes over | properties |
| --- | --- | --- |
| `filter_id` | the filter's canonical declaration (`to_dict()`) | pure function of the declared parameters |
| `classification_id` | `scheme` + the **sorted** `company_id → sector` pairs | order-independent in the mapping |
| `specification_id` | `name` + `spec_version` + the **ordered** `filter_id`s | order-*sensitive* in the filters, independent of any data/boundary |
| `construction_id` | `specification_id` + `construction_version_id` + boundary key + `universe_id` | binds request + engine + boundary + output |
| `universe_id` | the ordered members (Phase 9.1, unchanged) | order- and membership-sensitive |

The guarantee: **same specification + same builder version + same underlying data
⇒ same `universe_id` and same `construction_id`**, independent of execution order,
wall-clock time, or resolution-cache state. The filter framework contains no RNG
and no wall-clock reads; ordering is first-seen throughout; hashing is over
canonical JSON with sorted keys. Rebuilding a specification produces a
byte-identical construction record.

Note the deliberate independence: `specification_id` pins *only the request*, so
two teams authoring the identical specification share it before either has run
anything. `construction_id` additionally pins the boundary and the resolved
output, so it is the reproducible identity of *one concrete construction*.

## 6. Provenance: the `UniverseConstruction` record

Every build returns a `ConstructionResult` — the resolved `Universe` and a frozen,
serializable `UniverseConstruction` that answers *how this exact membership was
derived*:

```python
result.construction.to_dict()
# {
#   "construction_id": "sha256:…",
#   "specification_id": "sha256:…",
#   "specification_name": "positive-working-capital",
#   "spec_version": "universe-spec/1",
#   "construction_version_id": "sha256:…",
#   "construction_code_version": "universe-construction/1",
#   "boundary_kind": "pit",            # or "rev"
#   "boundary_value": "2024-06-01T00:00:00Z",   # or a dataset_version_id
#   "universe_id": "sha256:…",
#   "filter_ids": ["sha256:…", "sha256:…"],
#   "classification_ids": ["sha256:…"],
#   "applied_filters": [               # per-filter tally, in application order
#     {"filter_id": "sha256:…", "filter_kind": "explicit",
#      "received": 0, "kept": 3, "excluded": 0},
#     {"filter_id": "sha256:…", "filter_kind": "metric",
#      "received": 3, "kept": 2, "excluded": 1},
#   ],
#   "excluded": [                      # every drop, with reason and detail
#     {"company_id": "cik:0001045810", "filter_id": "sha256:…",
#      "filter_kind": "metric", "reason": "metric_threshold_not_met",
#      "detail": "-40000000"},
#   ],
# }
```

The record pins the specification identity, the builder version, the boundary, the
ordered source identities (`filter_ids` / `classification_ids`), a per-filter
`applied_filters` tally, and every `ExcludedCompany` with its reason and detail —
everything needed to *audit and reproduce* the construction.

Keeping the `UniverseConstruction` alongside the `Universe` (rather than mutating
the universe with build metadata) preserves the Phase 9.1 `Universe` as a pure
membership value.

## 7. Relationship to Phase 9.1 and the factor layer

- **Phase 9.1 `Universe`** is the *output* of a construction and remains usable
  directly (`Universe.from_companies([...])`) when membership is already known. A
  `UniverseSpecification` whose only filter is an `ExplicitCompanyFilter` is
  equivalent to `Universe.from_companies(...)`, but carries a construction record.
- **The [factor layer](metrics.md)** consumes a `Universe`; a universe *constructed*
  here is an ordinary Phase 9.1 universe and composes with the factor engine with no
  adaptation. The two share the `universe_id` scheme, so a constructed universe and
  a factor universe over the same ordered members share one id.

## 8. Design commitments

- **Composes, never duplicates** (ARCHITECTURE.md principles 3, 5). Resolution,
  metric arithmetic, and PIT/REVISED eligibility are delegated wholesale to the
  existing layers; the builder adds only rule evaluation, ordered narrowing, and
  provenance packaging. No second resolver, identifier system, formula, or store.
- **Immutable & serializable.** Specifications, filters, classifications, and
  construction records are frozen dataclasses with `to_dict()` / `from_dict()`
  round trips.
- **Deterministic & content-addressed.** All ids are `sha256:` hashes; no RNG, no
  wall-clock, no iteration-order dependence.
- **No fabricated data** (Principle 8). No sector data is invented; no metric is
  synthesized; an unknown metric or missing classification fails closed rather than
  guessing.
- **Fail closed on defects, record data conditions.** Specification defects raise;
  excluded companies are first-class recorded values, never exceptions.
- **No default mode** (invariant 27). PIT and REVISED are separate methods with
  distinct results and distinct ids.
- **Provenance first.** Every construction is fully auditable and reproducible.
