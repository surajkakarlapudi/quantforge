# Phase 9 — Universe Research Layer

Phase 9 gives QuantForge its first **cross-sectional** primitive: the *universe* —
a deterministic, point-in-time collection of SEC filers that a later research step
operates across. It is **one coherent capability**, delivered on a single
`Universe` abstraction in three cooperating parts:

```
Universe management  →  Universe construction  →  Research surface
(hold membership)       (derive membership       (inspect · describe ·
                         from ordered rules)       compare · export)
```

There is deliberately **no second universe type**. Construction produces the same
`Universe`; the research surface is methods *on* that `Universe` (and on the
`ConstructionResult` that carries its provenance).

| Part | Front door | Document |
| --- | --- | --- |
| **Management** | `Universe.from_companies([...])` / `Universe.from_identities([...])` | [universe.md](universe.md) |
| **Construction** | `UniverseSpecification` → `UniverseBuilder` → `ConstructionResult` | [universe-construction.md](universe-construction.md) |
| **Research surface** | `universe.describe()` · `universe.compare(other)` · `universe.to_records()` | [universe.md §8](universe.md#8-research-surface-inspection-description-comparison-export) |

## The through-line

A universe is built once and then interrogated. Every method preserves the two
invariants that make the whole pipeline trustworthy:

- **Canonical identity.** Membership is always keyed by the canonical `company_id`
  (`"cik:" + zero-padded CIK`). A ticker or name is a descriptive label that never
  participates in identity — in construction, in comparison, or in export.
- **PIT/REVISED never conflated** (invariant 27). Construction has no default
  mode: `build_as_of(...)` (point-in-time) and `build_revised(...)` (a pinned
  revised snapshot) are separate, explicit methods producing distinct results with
  distinct ids. The research surface *preserves* that mode: `UniverseSummary.mode`
  records it, and `UniverseComparison.mode_mismatch` flags any attempt to compare
  two universes built at different boundaries.

## The research surface at a glance

```python
from quantforge import Universe

universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])

# inspection
universe.members()  # tuple[CompanyIdentity, …] — full provenance
universe.company_ids  # canonical ids, ordered
len(universe)  # member count
universe.contains("cik:0000320193")  # membership by canonical id

# description — a deterministic, serializable UniverseSummary
summary = universe.describe()
summary.member_count, summary.company_ids, summary.universe_id
summary.to_dict()

# comparison — a deterministic, serializable UniverseComparison
cmp = before.compare(after)
cmp.added, cmp.removed, cmp.retained, cmp.is_identical
cmp.to_dict()

# export — dependency-free interchange
universe.to_dict()  # full provenance record
universe.to_records()  # one flat dict per member (CSV/DataFrame-ready)
```

For a **constructed** universe the `ConstructionResult` exposes the same surface,
enriched with construction provenance:

```python
result = builder.build_as_of(spec, as_of=...)
result.describe().mode  # "pit"  (a REVISED build → "rev")
result.describe().exclusions_by_reason  # {"metric_threshold_not_met": 1}
result.provenance()  # the full UniverseConstruction record
result.construction.excluded_for(cid)  # why a company is not a member
result.compare(other_result).mode_mismatch  # True if boundaries differ
result.to_records()  # rows tagged with construction_id + mode
```

## Result types

Both are frozen, deterministic, serializable value objects — not alternative
universes:

- **`UniverseSummary`** (`universe.describe()`) — member count, ordered
  `company_id`s, `universe_id`, builder version, and (for constructions) name,
  specification id, PIT/REVISED mode, boundary, applied filters, and exclusion
  counts by reason. It is **structural only** — no metric value, price, or
  market-cap field, because QuantForge holds no PIT-safe market data to compute one
  from. Prefer omission over fabrication.
- **`UniverseComparison`** (`universe.compare(other)`) — the members `added`,
  `removed`, and `retained` (diffed by canonical `company_id`), their counts,
  `is_identical`, and `mode_mismatch`. Ordering derives from the source universes'
  member order, never from set iteration.

Both are re-exported at the top level for type annotations:

```python
from quantforge import UniverseSummary, UniverseComparison
```

## Scope boundaries

Phase 9 is research-*universe* infrastructure. It does **not** implement — and
these remain later phases — ranking, weighting, portfolio construction or
optimization, trading, backtesting, performance attribution, price feeds,
market-data ingestion, alpha prediction, ML, or any external financial API. The
research surface computes no financial statistic and reaches no network; it is a
set of deterministic views over membership and existing provenance.
