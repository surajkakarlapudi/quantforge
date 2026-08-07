# Universe Management Layer

The **universe layer** (Phase 9.1) represents a *deterministic collection of
securities at a specific point in time* — the set of filers a later
cross-sectional step (ranking, portfolio construction, backtesting) will operate
across. This phase builds **only** that foundation: it resolves and holds
membership. Ranking, portfolios, and backtesting are deliberately **not**
implemented here.

```python
from quantforge.universe import Universe

universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])

for company_id in universe:
    print(company_id)  # cik:0000320193, cik:0000789019, cik:0001045810
```

`Universe` is also re-exported at the top level, so `from quantforge import
Universe` works too.

Package: `src/quantforge/universe/`.

This layer **adds no new company-identifier system** and **creates no new
storage**. It composes the existing [company identity
layer](company-api.md): every member is resolved by the same
`CompanyResolver` that backs `Company.resolve(...)`, and is keyed by the
canonical `company_id` used throughout every phase (see
[data-model.md](data-model.md) §11).

---

## 1. What it does, and what it deliberately does not

The universe layer answers exactly one question — *"which ordered set of SEC
filers am I researching over?"* — and then gets out of the way:

- **`Universe.from_companies([...])`** → resolve a list of tickers / CIKs / names
  through the identity layer into an ordered, de-duplicated collection of
  [`CompanyIdentity`](company-api.md) members.
- **`Universe.from_identities([...])`** → assemble a universe from identities a
  caller already holds (e.g. `company.identity`), without re-resolving.
- **Iteration / `len()` / `company_ids`** → the canonical `company_id`s in
  deterministic order.
- **`universe_id`** → a content hash over the ordered membership.
- **`to_dict()`** → a serializable provenance record.

It does **not** rank, weight, or score members; it does not construct portfolios;
it does not run backtests; and it does not enumerate "all filers" (there is no
implicit universe — membership is always explicit and caller-supplied). Those
belong to later phases.

## 2. Identity: the canonical `company_id` is the only truth

A universe is a set of *filers*, and a filer's identity is the canonical
`company_id` — never a ticker or name:

```
company_id = "cik:" + zero-padded-10-digit CIK      # e.g. cik:0000320193
```

`from_companies` resolves each supplied identifier through the identity layer,
which fails closed on an unknown or ambiguous symbol (it never fabricates a CIK).
De-duplication is by `company_id`, so distinct spellings of one filer — a ticker
and its CIK, or the same ticker twice — collapse to a single member:

```python
Universe.from_companies(["AAPL", "320193"])  # one member: cik:0000320193
```

Each member keeps the exact identifier the caller supplied and which lookup
matched it (`resolved_from`, `source`), so the membership is auditable back to the
caller's input. See [company-api.md](company-api.md) §2 for the full identity
contract, which this layer inherits unchanged.

## 3. Deterministic ordering

Ordering is **first-seen, de-duplicated**: the order in which the caller lists
identifiers is the order of the universe, with later duplicates dropped.

```python
Universe.from_companies(["MSFT", "AAPL", "AAPL", "NVDA"]).company_ids
# ("cik:0000789019", "cik:0000320193", "cik:0001045810")
```

There is no hidden sorting, no dependence on wall-clock time, and no dependence on
resolution-cache state. Identical inputs always produce an identical universe —
the ordering discipline required by [ARCHITECTURE.md](../ARCHITECTURE.md#engineering-principles)
principles 5 (deterministic transformations) and 6 (reproducibility). This matters
downstream: a cross-sectional cell order and any rank tie-break follow the
universe's member order, so a stable order is a correctness property, not a
cosmetic one.

An **empty universe fails closed** with `UniverseConfigurationError` — a universe
over nobody is a configuration bug, not an empty result. A bare string
(`from_companies("AAPL")`) is likewise rejected, because a string is iterable
character-by-character and silently resolving `"A", "A", "P", "L"` would be a nasty
bug; pass a list.

## 4. Provenance

Provenance is preserved at two levels:

- **Per member** — each `CompanyIdentity` records the exact `resolved_from`
  identifier and the `source` lookup (`ticker` / `name` / `cik`).
- **Per universe** — the pinned `UniverseBuilderVersion` records the deterministic
  construction logic (canonicalization + de-duplication + ordering rule) as a
  stable `sha256:` version id, following the same
  [transformation-version](data-model.md) convention as the canonical, metric, and
  availability layers.

`to_dict()` serializes the whole record — the `universe_id`, the builder version,
and every member's provenance — for audit and reproducibility:

```python
universe.to_dict()
# {
#   "universe_id": "sha256:…",
#   "universe_version_id": "sha256:…",
#   "builder_version": "universe-builder/1",
#   "members": [{"company_id": "cik:0000320193", "resolved_from": "AAPL", …}, …],
# }
```

## 5. Content-addressed identity

`universe_id` is a SHA-256 over the **ordered** `company_id` members, with a
domain tag so it cannot collide with any other id space:

```
universe_id = "sha256:" + sha256("universe" ⊹ m0 ⊹ m1 ⊹ …)     # ⊹ = NUL separator
```

It is **order-sensitive** and **membership-sensitive**: re-declaring the identical
ordered universe reproduces the same id, while any change to membership *or* order
yields a new one. This is the *same* scheme used by the cross-sectional factor
universe (`quantforge.factors.Universe`), so a universe assembled here and a factor
universe over the same ordered members share one id — the two compose rather than
diverge.

## 6. Relationship to the factor universe

There are two universe abstractions, at two altitudes:

| | `quantforge.universe.Universe` (Phase 9.1) | `quantforge.factors.Universe` (Phase 8) |
| --- | --- | --- |
| Input | tickers / CIKs / names (human-facing) | CIKs / `company_id`s the caller already holds |
| Resolves through identity layer | **yes** | no (canonicalizes CIKs only) |
| Carries per-member provenance | **yes** (`CompanyIdentity`) | no (bare `company_id` strings) |
| Iterates `company_id`s in order | yes | yes |
| `universe_id` scheme | shared, content-addressed | shared, content-addressed |

The Phase 9.1 universe is the **front door** for building membership from
human-facing symbols; the factor universe is the low-level ordered id set the
factor engine consumes. Because they share the `universe_id` scheme and the
`company_id` iteration contract, the Phase 9.1 universe composes cleanly with the
existing factor engine without duplicating it.

## 7. Design commitments

- **Composes, never duplicates.** Resolution is delegated entirely to the existing
  `CompanyResolver`; no second resolver, identifier system, or storage is
  introduced.
- **Immutable.** `Universe` is a frozen dataclass; its membership cannot change
  after construction.
- **Deterministic.** Ordering and de-duplication are pure functions of the input;
  nothing depends on wall-clock time or nondeterministic iteration.
- **Fail closed.** An empty universe or a mis-typed argument is raised, never
  silently accepted or guessed.
- **Provenance first.** Every member and the builder itself carry an auditable,
  serializable record.
