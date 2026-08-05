# Architecture

This document describes the **intended** high-level architecture of OpenFinance
and the **current status** of each component.

> **Important:** Almost everything below is *planned*. The only thing that
> currently exists is the repository, packaging, and development-tooling
> foundation. No ingestion, storage, parsing, provenance, point-in-time layer,
> factors, or backtesting code exists yet.

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
| **Point-in-Time Data Layer** | 🔜 Planned | Serves data *as it was known* at a given date, preventing look-ahead bias. |
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
