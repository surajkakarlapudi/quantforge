# Company Identity & Public API

The **company identity layer** is the front door of QuantForge. It resolves a
user-facing identifier — a ticker (`"AAPL"`), a CIK (`320193`), or an exact
company name — to the project's canonical filer identity, and exposes a small,
typed façade for querying the deterministic layers beneath it:

```python
from quantforge import Company

apple = Company.resolve("AAPL")
print(apple)  # Company('AAPL', cik='320193')

for filing in apple.filings():
    print(filing.form, filing.filing_date)

facts = apple.facts()
```

Packages: `src/quantforge/identity/` (resolution) and the top-level
`quantforge.company` / `quantforge.workspace` modules (façade + wiring).

This layer **adds no data model of its own** and **creates no new storage**. It
resolves an identifier to the canonical `company_id` used throughout Phases 2–5
and then delegates every query to the existing layers. It is a thin integration
seam, not a new engine.

---

## 1. What it does, and what it deliberately does not

The identity layer answers exactly one question — *"which SEC filer does this
symbol mean?"* — and then gets out of the way:

- **`Company.resolve(...)`** → resolve ticker / CIK / name to a
  [`CompanyIdentity`](#3-companyresolve) carrying the canonical `company_id`.
- **`Company.filings()`** → delegate to the Phase 2
  [`FilingRegistry`](filing-registry.md).
- **`Company.facts()`** → delegate to the Phase 4
  [`CanonicalFactStore`](canonicalization.md).

It does **not** interpret financial content, build statements, derive
availability, or perform point-in-time selection. Those belong to the layers it
sits on top of (and to later phases). It never fabricates a CIK, never hardcodes
a ticker, and never introduces a second HTTP client or storage system.

## 2. Identity: the canonical `company_id` is the only truth

Every resolution ends at the canonical filer identity defined in
[docs/data-model.md](data-model.md) §11 and produced by
`quantforge.registry.identity.company_id`:

```
company_id = "cik:" + zero-padded-10-digit CIK      # e.g. cik:0000320193
```

A ticker or company name is **descriptive metadata only**. Tickers get
reassigned across issuers over time and names change; neither is stable, so
neither ever participates in identity, storage keys, or provenance. `Company`
stores the resolved ticker/name for display, but everything downstream is keyed
by CIK. This is the same rule the registry, canonical, and availability layers
already follow — the identity layer simply extends the public API up to it
without weakening it.

## 3. `Company.resolve(...)`

```python
Company.resolve(identifier: str, *, by: str | None = None,
                workspace: Workspace | None = None) -> Company
```

Resolution strategy:

- An all-digit or `CIK`-prefixed value (`"320193"`, `"0000320193"`,
  `"CIK0000320193"`) is treated as a **CIK**. CIK resolution needs no mapping
  and always works offline.
- Anything else is looked up as a **ticker** first, then as an **exact company
  name**, against SEC's official mapping.
- `by="cik" | "ticker" | "name"` forces the interpretation.

Resolution is **fail-closed**:

| Situation | Result |
| --- | --- |
| Identifier matches no filer | `UnknownSymbolError` |
| Identifier matches more than one CIK | `AmbiguousSymbolError` (never arbitrated) |
| Ticker/name lookup needed but mapping not cached and no client | `TickerMapUnavailableError` |

A `Company` is a frozen value object exposing `company_id`, `cik`, `ticker`,
`name`, and the underlying `CompanyIdentity` (which additionally records
`resolved_from` — the exact input string — and `source`, for provenance).

## 4. Official SEC ticker → CIK mapping (no hardcoding)

Ticker and name resolution use SEC's authoritative
[`company_tickers.json`](https://www.sec.gov/files/company_tickers.json), never a
hand-written table. The document is retrieved through the Phase 1 client and
stored as an **immutable, content-addressed artifact** like every other SEC
retrieval — so:

- it is fetched **at most once**, then served from the local cache;
- repeated lookups (and a fresh process) are fully **offline**;
- conditional requests reuse the stored bytes when SEC reports no change;
- when several cached copies exist, the newest by retrieval time wins.

`TickerMap` parses those bytes into deterministic lookup indices (by ticker, by
CIK, by title). Every CIK it emits is canonicalized through the Phase 1
`canonical_cik`, so identity never diverges. Incomplete rows are skipped;
a malformed document raises rather than resolving to a guess.

To populate the cache the first time (requires the `QUANTFORGE_SEC_USER_AGENT`
email-format contact SEC's fair-access policy asks for):

```python
from quantforge.sec import build_client

build_client().acquire_company_tickers()  # one network call; cached thereafter
```

## 5. `Workspace` — wiring the phases together

`Company.resolve(...)` needs the existing per-phase stores. A `Workspace` is the
composition root that assembles them from one data root:

```
<root>/sec/          # Phase 1 content-addressed artifacts (authoritative)
<root>/registry/     # Phase 2 derived filing registry
<root>/canonical/    # Phase 4 derived canonical facts
```

```python
from quantforge import Company, Workspace

ws = Workspace.open("/path/to/data")  # explicit root
apple = Company.resolve("AAPL", workspace=ws)
```

With no arguments, `Workspace.open()` reads the root from `QUANTFORGE_DATA_ROOT`
(or derives it from the configured Phase 1 storage dir), and — when a User-Agent
is configured — attaches a network client used *solely* to fetch the ticker
mapping once. With no client and no cached mapping, ticker/name resolution fails
closed while CIK resolution still works. When `workspace` is omitted,
`Company.resolve(...)` opens a default one from the environment.

The `Workspace` constructs only components the phases already define
(`ArtifactStore`, `FilingRegistry`, `CanonicalFactStore`, `CompanyResolver`); it
holds no logic of its own.

## 6. `filings()` and `facts()` — pure delegation

```python
Company.filings() -> list[FilingRecord]        # → FilingRegistry.list_filings(cik)
Company.filings_by_form(form) -> list[FilingRecord]
Company.facts() -> list[Fact]                  # → CanonicalFactStore.read_company(company_id)
```

Both return the existing immutable records with **complete provenance intact** —
the façade copies nothing and loses nothing. `filings()` returns Phase 2
`FilingRecord`s sorted by canonical accession; `facts()` returns Phase 4 `Fact`s
sorted by `fact_id`. A filer with no derived registry/canonical data returns
empty lists (never an error, never fabricated data). `CanonicalFactStore` gained
a `read_company(company_id)` query for this — the same company-scoped scan the
availability façade already needed, now shared rather than duplicated.

## 7. Relationship to the other phases

```
                       ┌───────────────────────────────────────────┐
   "AAPL" / 320193 ───▶│ identity layer (company_tickers.json cache) │──▶ company_id
                       └───────────────────────────────────────────┘
                                          │ delegates
        ┌─────────────────────────────────┼─────────────────────────────────┐
        ▼                                 ▼                                   ▼
  Phase 1 ArtifactStore          Phase 2 FilingRegistry            Phase 4 CanonicalFactStore
  (caches the mapping)              (Company.filings)                   (Company.facts)
```

The identity layer reuses Phase 1 for caching the mapping, Phase 2 for filings,
and Phase 4 for facts. It preserves every architectural guarantee of those
layers — deterministic identity, immutable derived state, full provenance,
rebuildability, byte-identical outputs, and separation of phases — because it
delegates to them rather than reimplementing any of them.

## 8. Determinism & offline behavior

- **Deterministic.** Given a fixed artifact store, resolution and both queries
  are pure functions of stored content. `TickerMap` iteration and every result
  list are sorted; no wall-clock or iteration-order dependence enters identity.
- **Offline after first fetch.** Once `company_tickers.json` is cached, no
  network access occurs. CIK resolution never needs the network at all.
- **Fail-closed everywhere.** Unknown or ambiguous symbols raise; a missing
  mapping raises for ticker/name lookups; nothing is guessed or fabricated.

## 9. Public API surface

Exported from the top-level package:

```python
from quantforge import Company, CompanyIdentity, Workspace, PitValue, RevisedValue
```

`Company` is the primary entry point. `Workspace` wires the backend.
`CompanyIdentity` is the typed resolution result. `PitValue` / `RevisedValue`
are re-exported from the point-in-time layer so the PIT-vs-revised distinction is
visible at the import site (they remain defined in
[`quantforge.availability`](point-in-time.md)). Internal modules
(`quantforge.identity.*`, resolver internals, stores) remain private
implementation detail.
```
