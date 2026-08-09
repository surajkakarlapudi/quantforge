# QuantForge Documentation

QuantForge is an early-stage project. This documentation is foundational and
will expand as functionality is implemented.

## Contents

- [Architecture](../ARCHITECTURE.md) — intended high-level design and the
  current status of each component.
- [SEC Acquisition Layer](sec-acquisition.md) — Phase 1: retrieving and
  preserving raw SEC EDGAR source material.
- [Filing Registry](filing-registry.md) — Phase 2: the deterministic,
  provenance-tracked registry of SEC filings derived from acquisition artifacts.
- [Raw XBRL Ingestion](xbrl-ingestion.md) — Phase 3: parsing SEC XBRL instance
  artifacts into immutable, fully-provenanced, loss-preserving raw facts.
- [Canonicalization](canonicalization.md) — Phase 4: transforming raw facts into
  deterministic, structured canonical financial observations with complete
  lineage back to the raw source.
- [Public Availability & Point-in-Time](point-in-time.md) — Phase 5: deriving when
  each filing became public under a versioned policy, and serving point-in-time
  (PIT) and revised knowledge-state queries that are impossible to confuse.
- [Company Identity & Public API](company-api.md) — the `from quantforge import
  Company` front door: resolving tickers/CIKs/names to the canonical filer
  identity via the official SEC mapping, then delegating to the existing layers.
- [Financial Metrics & Research Layer](metrics.md) — Phase 7: deterministic,
  fail-closed derived metrics (ratios and arithmetic combinations) computed on
  demand over the point-in-time knowledge state, versioned and fully provenanced,
  served as distinct PIT and revised result types.
- [Universe Research Layer](phase9-research-layer.md) — Phase 9: the cross-sectional
  *universe* primitive, one coherent capability on a single `Universe` abstraction,
  delivered in three parts (management → construction → research surface). Start here
  for the overview; the two documents below cover the parts in depth.
- [Universe Management](universe.md) — a deterministic, immutable,
  point-in-time collection of filers assembled from tickers/CIKs/names via the
  company identity layer — the membership foundation for cross-sectional research
  (ranking, portfolios, backtesting are not implemented). Also documents the
  research surface: inspection, `describe()`, `compare()`, and `to_records()`.
- [Universe Construction](universe-construction.md) — a deterministic
  construction framework (`UniverseSpecification` → `UniverseBuilder` → `Universe`)
  that resolves an eligible membership from ordered, content-addressed selection
  rules (explicit companies, a point-in-time metric threshold, a caller-supplied
  sector classification) and emits a reproducible provenance record — composing the
  existing resolver and metric engine, adding no financial logic of its own.
- [Point-in-Time Fundamental Panel](panel.md) — Phase 10: one Phase 7 metric
  evaluated over an explicit, content-addressed period axis, in three shapes
  (period-series, vintage/knowledge-evolution, cross-sectional matrix) with
  `UNDEFINED`-preserving multi-period derivations, served as distinct `PitPanel` /
  `RevisedPanel` types. The [locked architecture](phase10-panel-locked.md) is the
  normative spec.
- [Point-in-Time Market Data Layer](phase11-market-data-locked.md) — Phase 11: a
  provider-neutral price/market-data foundation built as a new source beneath the
  existing stack. Canonical **unadjusted** daily OHLCV observations plus first-class
  immutable corporate actions (splits, dividends, symbol changes, delistings,
  mergers), served through a market PIT resolver as distinct `PitPrice` /
  `RevisedPrice` types over an own fail-closed availability boundary. Adjusted prices
  are a derived, PIT-gated view; adds no backtester and never rewrites a SEC `Fact`.
  The [locked architecture](phase11-market-data-locked.md) is the normative spec.
- [Engineering Principles](../ARCHITECTURE.md#engineering-principles) — the
  non-negotiable principles guiding the project.
- [Contributing](../CONTRIBUTING.md) — how to set up a development environment
  and contribute.
- [Security](../SECURITY.md) — how to report vulnerabilities.

## Status

No financial functionality is implemented yet. The current release establishes
the repository, packaging, and development-tooling foundation only.
