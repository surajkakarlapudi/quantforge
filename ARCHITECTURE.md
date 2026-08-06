# Architecture

This document describes the **intended** high-level architecture of OpenFinance
and the **current status** of each component.

> **Important:** The acquisition, storage, parsing, provenance, and
> point-in-time layers now exist (Phases 1–5; see "Implemented layers" below).
> Factors and backtesting remain *planned*.

> **Data model.** The canonical financial-fact and provenance model that
> underpins the immutable-raw-data, normalization, provenance, and
> point-in-time components is specified in
> [docs/data-model.md](docs/data-model.md). Point-in-time eligibility is gated
> by a *derived, policy-versioned* public-availability timestamp with an
> explicit `verified`/`derived`/`unknown` status — acceptance alone never
> proves availability, and un-datable facts fail closed (are excluded), never
> guessed. It is design-only; no storage or query code exists yet.

> **Implemented layers.** Five deterministic, provenance-first layers now
> exist, each documented in its own spec: **Phase 1 — SEC acquisition**
> ([docs/sec-acquisition.md](docs/sec-acquisition.md)), the immutable
> content-addressed raw-artifact store; **Phase 2 — filing registry**
> ([docs/filing-registry.md](docs/filing-registry.md)), derived filing identity
> and provenance; **Phase 3 — raw XBRL ingestion**
> ([docs/xbrl-ingestion.md](docs/xbrl-ingestion.md)), immutable loss-preserving
> `RawFact`/`RawContext`/`RawUnit` records parsed from the acquired XBRL
> instances; **Phase 4 — canonicalization**
> ([docs/canonicalization.md](docs/canonicalization.md)), deterministic,
> structured canonical `Fact` observations derived from the raw facts with
> complete lineage back to the source; and **Phase 5 — public availability &
> point-in-time** ([docs/point-in-time.md](docs/point-in-time.md)), a versioned,
> fail-closed derivation of when each filing became public plus point-in-time
> (PIT) and revised knowledge-state queries served as distinct, impossible-to-
> confuse result types over the immutable canonical facts. A thin **company
> identity & public API** layer
> ([docs/company-api.md](docs/company-api.md)) sits above these: it resolves a
> ticker, CIK, or company name to the canonical filer identity via SEC's
> official mapping (cached as a Phase 1 artifact) and exposes
> `from openfinance import Company` as the front door, delegating `filings()`
> and `facts()` to the registry and canonical layers without duplicating them.
> Factors and backtesting remain planned.

## High-level data flow

```
        Public Financial Data
                 |
                 v
            Ingestion
                 |
                 v
        Immutable Raw Data
                 |
                 v
      Parsing / Normalization
                 |
                 v
            Provenance
                 |
                 v
       Point-in-Time Data Layer
                 |
                 v
              Factors
                 |
                 v
            Backtesting
                 |
                 v
        Reproducible Research
```

## Components and status

| Component | Status | Description |
| --- | --- | --- |
| **Public Financial Data** | 🔜 Planned | Public sources (e.g. regulatory filings, public market data). External inputs; no source connectors exist yet. |
| **Ingestion** | 🔜 Planned | Fetches raw data from public sources and records exactly what was retrieved and when. |
| **Immutable Raw Data** | 🔜 Planned | Append-only store of raw source data, never modified after capture. The system of record. |
| **Parsing / Normalization** | 🔜 Planned | Deterministic transformation of raw data into normalized structures, derived only from immutable raw data. |
| **Provenance** | 🔜 Planned | Every normalized/derived value is traceable to the raw record and process that produced it. |
| **Point-in-Time Data Layer** | ✅ Exists (Phase 5) | Serves data *as it was known* at a given date, preventing look-ahead bias. Derives each filing's public-availability timestamp under a versioned, fail-closed policy and answers PIT / revised queries as distinct result types. See [docs/point-in-time.md](docs/point-in-time.md). |
| **Company identity & public API** | ✅ Exists | The `from openfinance import Company` front door: resolves ticker/CIK/name to the canonical filer identity via SEC's official mapping (cached as a Phase 1 artifact), then delegates `filings()`/`facts()` to the registry and canonical layers. Adds no data model or storage of its own. See [docs/company-api.md](docs/company-api.md). |
| **Factors** | 🔜 Planned | Computed signals/features built strictly on point-in-time data. |
| **Backtesting** | 🔜 Planned | Evaluates strategies over point-in-time data with reproducible results. |
| **Reproducible Research** | 🔜 Planned | The end goal: analyses that can be re-run to produce identical results. |
| **Repository & tooling foundation** | ✅ Exists | Packaging (src layout, `pyproject.toml`, `uv.lock`), tests, lint/format, type checking, pre-commit, and docs. |

## Design intent

- The **immutable raw data** store is the system of record. Everything
  downstream is a deterministic function of it.
- **Provenance** links every derived value back to the raw data and the exact
  transformation that produced it.
- The **point-in-time data layer** is what makes research free of look-ahead
  bias: queries are answered as of a specified date using only information that
  was known at that date.
- **Reproducibility** is the end-to-end property that ties the pipeline
  together: the same inputs and code always produce the same outputs.

## Technology notes

- **Python 3.11+**, managed with **uv** (`pyproject.toml` + `uv.lock`).
- **src layout** for the package.
- Runtime dependencies are added only when a component that needs them is
  implemented. There are none yet.
- DuckDB is a likely candidate for local analytical storage, but nothing is
  committed to yet and no database code exists.

## Engineering Principles

These principles are non-negotiable and guide every design decision.

1. **Correctness over convenience.** When the two conflict, correctness wins,
   even if it is slower to build or use.
2. **Immutable raw data.** Raw source data is append-only and never modified
   after capture. It is the system of record.
3. **Provenance.** Every derived value must be traceable to the raw data and the
   transformation that produced it.
4. **Point-in-time integrity.** Data is served as it was known at a given date.
   Look-ahead bias is treated as a correctness bug.
5. **Deterministic transformations.** The same inputs and code must always
   produce the same outputs. No hidden state, no reliance on wall-clock time or
   nondeterministic ordering.
6. **Reproducibility.** Analyses and backtests can be re-run to produce
   identical results, end to end.
7. **Tests for critical behavior.** Anything affecting correctness or
   point-in-time integrity must be covered by tests.
8. **No fabricated financial data.** The project never invents financial data,
   and never ships example data that could be mistaken for real market data.
9. **No secrets in source control.** Credentials and secrets stay out of the
   repository; local secrets live in git-ignored `.env` files.
10. **Minimal dependencies.** A dependency is added only when genuinely needed,
    and its inclusion is justified.
