# Architecture

This document describes the **intended** high-level architecture of QuantForge
and the **current status** of each component.

> **Important:** The acquisition, storage, parsing, provenance, point-in-time,
> derived-metrics, factor, universe, panel, market-data, and backtesting layers
> now exist (Phases 1–12; see "Implemented layers" below).

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
> `from quantforge import Company` as the front door, delegating `filings()`
> and `facts()` to the registry and canonical layers without duplicating them.
> Above them, a **financial metrics & research layer**
> ([docs/metrics.md](docs/metrics.md)) computes deterministic, fail-closed,
> versioned, fully-provenanced derived metrics (ratios and arithmetic
> combinations) on demand over the point-in-time knowledge state — served, like
> Phase 5, as distinct PIT and revised result types so a metric can never
> silently consume revised history. Above the market-data layer, a **backtesting
> / research-simulation layer** ([docs/phase12-backtesting-proposal.md](docs/phase12-backtesting-proposal.md))
> now exists: a deterministic, point-in-time strategy simulator over the pinned
> fundamentals + market corpora, content-addressed end to end.

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
| **Company identity & public API** | ✅ Exists | The `from quantforge import Company` front door: resolves ticker/CIK/name to the canonical filer identity via SEC's official mapping (cached as a Phase 1 artifact), then delegates `filings()`/`facts()` to the registry and canonical layers. Adds no data model or storage of its own. See [docs/company-api.md](docs/company-api.md). |
| **Factors** | ✅ Exists (Phase 7) | Computed signals/features built strictly on point-in-time data. The metrics layer computes deterministic, fail-closed, versioned, fully-provenanced financial metrics (ratios and arithmetic combinations) on demand over the Phase 5 knowledge state, served as distinct PIT / revised result types. See [docs/metrics.md](docs/metrics.md). |
| **Universe management** | ✅ Exists (Phase 9.1) | A deterministic, immutable, point-in-time collection of filers, assembled from tickers/CIKs/names via `Universe.from_companies([...])`. Resolves through the existing company identity layer (no new identifier system), preserves first-seen ordering and per-member provenance, and content-addresses the ordered membership. The foundation for cross-sectional research; ranking, portfolios, and backtesting are not implemented here. See [docs/universe.md](docs/universe.md). |
| **Universe construction** | ✅ Exists (Phase 9.2) | A deterministic construction framework on top of Phase 9.1: `UniverseSpecification` (an immutable, content-addressed, ordered list of selection rules) → `UniverseBuilder` (a fail-closed engine that evaluates it at one PIT/REVISED boundary) → a `Universe` plus a reproducible `UniverseConstruction` provenance record. The three initial filters (`ExplicitCompanyFilter`, `CompanyMetricFilter`, `SectorFilter`) *compose* the existing resolver and metric engine — no new identifier system, no arithmetic, no external I/O. Same specification + same builder + same data ⇒ same `universe_id` and `construction_id`. See [docs/universe-construction.md](docs/universe-construction.md). |
| **Universe research surface** | ✅ Exists (Phase 9) | The researcher-facing completion of Phase 9, on the *same* `Universe` object (no second abstraction): inspection (`members()`, `company_ids`, `contains()`), deterministic serializable description (`describe()` → `UniverseSummary`), membership comparison by canonical `company_id` (`compare()` → `UniverseComparison`, which flags any PIT/REVISED `mode_mismatch`), and dependency-free export (`to_dict()`, `to_records()`). Computes no financial statistic and adds no dependency. `ConstructionResult` exposes the same surface enriched with construction provenance. See [docs/phase9-research-layer.md](docs/phase9-research-layer.md). |
| **Fundamental panel** | ✅ Exists (Phase 10) | One Phase 7 metric evaluated over an explicit, content-addressed period axis, in three shapes — period-series, vintage/knowledge-evolution, and cross-sectional matrix (the last reusing the Phase 9 `Universe`) — with `UNDEFINED`-preserving multi-period derivations (`growth`, `ttm`, `average_balance`, `level_vs_history`). Compute-on-demand and fully provenanced per cell, served as distinct `PitPanel` / `RevisedPanel` types (a `RevisedPanel` can never be passed where a `PitPanel` is required). Adds no market data and no backtester. See [docs/panel.md](docs/panel.md); the [locked architecture](docs/phase10-panel-locked.md) is the normative spec. |
| **Market data** | ✅ Exists (Phase 11) | A provider-neutral, point-in-time market-data layer added as a *new source beneath* the existing stack (never through it). Canonical **unadjusted** daily OHLCV `PriceObservation`s keyed by `(security_id, trading_date, field)`, plus first-class immutable `CorporateAction`s (split / dividend / symbol-change / delisting / merger), each carrying its own fail-closed availability boundary under a versioned market `AvailabilityPolicy`. Instrument identity reuses the designed `security_id` (`cik:<CIK>#class:<...>`; ticker is never identity). Adjusted prices are a derived, versioned, PIT-gated *view* over the immutable actions — never the stored value. Served as distinct `PitPrice` / `RevisedPrice` types (a `RevisedPrice` can never be passed where a `PitPrice` is required). Reuses the Phase 1 content-addressed storage and Phase 5 PIT machinery; edits no prior store, adds no runtime dependency, introduces no database, and builds no backtester. Never rewrites a SEC `Fact`. See the [locked architecture](docs/phase11-market-data-locked.md). |
| **Backtesting** | ✅ Exists (Phase 12) | A deterministic, point-in-time strategy simulator over the pinned fundamentals + market corpora. A strategy is a declarative, content-addressed spec (`signal → rank → select → weight`); the engine owns execution (strategies emit only `TargetWeights`), consuming the Phase 11 PIT-only hand-off (`price_as_of` / `price_series_as_of` returning `PitPrice` / `PitPriceSeries`), applying `CorporateAction`s (split / dividend / delisting / merger / symbol-change) through Phase 11, honoring survivorship through Phase 9, and computing v1 statistics (cumulative/period return, Sharpe, max drawdown, turnover). Every decision at time `T` sees only PIT-eligible-at-`T` data (BT-2); **both** corpus snapshots are pinned and verified (BT-1); missing data is recorded in the ledger, never guessed (BT-4); and the whole run is content-addressed by a `backtest_id` folding every result-changing input (D6) — same inputs reproduce the same id and result on any machine. Reuses the existing stores and PIT machinery; adds no runtime dependency and no database. See [docs/phase12-backtesting-proposal.md](docs/phase12-backtesting-proposal.md). |
| **Reproducible Research** | ✅ Exists (Phase 13) | Comparative research as one capability strictly *above* Phase 12, a pure consumer of already-sealed, PIT-correct backtests. A declarative, content-addressed `ExperimentSpecification` sweeps a closed v1 vocabulary of backtest parameters (D7) — corpus pins are inherited verbatim, never swept (D2) — and `ExperimentEngine.run` deterministically expands the Cartesian product, runs each child through the Phase 12 engine (threading the annualization convention unchanged, D5), and seals a thin `ExperimentResult` ledger of `(coordinate, backtest_id)` pointers to the shared research sidecar (write-once, no new store, D4). `BacktestComparison` ranks a set of sealed backtests (or an experiment's children) by one v1 performance statistic: fail-closed on unknown statistics/orders, absent members, and incommensurable engine versions; corpus `pin_mismatch` is surfaced, never silently compared. `experiment_id` folds every result-changing input, so an identical experiment reproduces the same id, children, and result on any machine — reuse is by determinism + idempotent write-once, never a pre-run guess. Adds no runtime dependency, no database, and no arbitrary-code escape hatch. See the [locked architecture](docs/phase13-comparative-research-locked.md). |
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
