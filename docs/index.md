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
- [Backtesting / Research Simulation](phase12-backtesting-proposal.md) — Phase 12: a
  deterministic, point-in-time strategy simulator over the pinned fundamentals +
  market corpora. A strategy is a declarative, content-addressed spec (signal → rank
  → select → weight); the engine owns execution (strategies emit only target
  weights), applies corporate actions through Phase 11, honors survivorship through
  Phase 9, and fails closed (missing data is recorded in the ledger, never guessed).
  Every decision at time `T` sees only PIT-eligible-at-`T` data, both corpus snapshots
  are pinned and verified, and the whole run is content-addressed by a `backtest_id`
  folding every result-changing input — same inputs reproduce the same id and result
  on any machine. Adds no runtime dependency and no database.
- [Comparative Research](phase13-comparative-research-locked.md) — Phase 13: reproducible
  research strictly *above* Phase 12, a pure consumer of already-sealed, PIT-correct
  backtests. A declarative, content-addressed `ExperimentSpecification` sweeps a closed
  v1 vocabulary of backtest parameters (corpus pins are inherited verbatim, never swept);
  `ExperimentEngine.run` deterministically expands the Cartesian product, runs each child
  through the Phase 12 engine, and seals a thin `ExperimentResult` ledger of
  `(coordinate, backtest_id)` pointers to the shared research sidecar (write-once, no new
  store). `BacktestComparison` ranks sealed backtests (or an experiment's children) by one
  v1 performance statistic — fail-closed on unknown statistics, absent members, and
  incommensurable engine versions, with corpus `pin_mismatch` surfaced rather than
  silently compared. The [locked architecture](phase13-comparative-research-locked.md) is
  the normative spec.
- [Research Reporting & Explainability](phase14-reporting-locked.md) — Phase 14: a reporting
  layer strictly *above* Phase 13, a pure consumer of already-sealed, PIT-correct artifacts.
  A declarative, content-addressed `ReportSpecification` (scope ∈ `{backtest, experiment}`, a
  `subject_id`, optional comparison directives) drives `ReportEngine.build`, which resolves and
  verifies each referenced artifact from the shared sidecar (fail closed on any missing/drifted
  reference) and seals a `ResearchReport`: a **reference-only** manifest of `(kind, reference_id,
  content_hash, detail)` pointers (never a copy of a financial value) plus the reporting intent
  and an explicit PIT `boundary_kind`. The report is a `ResearchRecord` persisted write-once to
  the existing sidecar (no new store), byte-identically round-tripping; `report_id` folds the
  request + referenced content hashes only — never presentation, schema/format version, or time —
  so it is sensitive to any change in a reported artifact yet invariant under renderer edits. A
  comparison is referenced by intent and recomputed deterministically (never persisted; Phase 13
  analysis untouched). Exactly one pure `render_markdown(report, store)` proves the
  content/presentation split, formatting ten documented sections with zero effect on identity or
  storage. The [locked architecture](phase14-reporting-locked.md) is the normative spec.
- [Performance & Benchmark-Relative Analytics](phase15-analytics-locked.md) — Phase 15: a risk &
  benchmark-relative analytics layer strictly *above* Phase 12, a pure consumer of already-sealed,
  PIT-correct `BacktestResult`s that computes the statistic family Phase 12 explicitly deferred. A
  declarative, content-addressed `AnalyticsSpecification` (a `subject_id`, an optional
  `benchmark_id`, the VaR confidences, and the annualization convention) drives
  `AnalyticsEngine.compute`, which re-verifies each referenced backtest's content hash from the
  shared sidecar (fail closed on any absent/drifted reference) and computes downside/drawdown risk,
  historical **nearest-rank** VaR/CVaR (deterministic, no RNG), return-distribution moments, and —
  only against a **benchmark that is itself a sealed backtest** — tracking error, information ratio,
  capture, and single-factor closed-form OLS alpha/beta (multi-factor deferred). It adds only what
  Phase 12 does not already seal (return/volatility/Sharpe/max-drawdown are never recomputed); every
  undefinable statistic is a first-class `UNDEFINED` cell with a reason — never fabricated, never a
  divide-by-zero. The sealed `PerformanceAnalytics` is a `ResearchRecord` persisted write-once to
  the existing sidecar (no new store), byte-identically round-tripping; `analytics_id` folds the
  engine+formula version, the declared request, both referenced content hashes, and the computed
  answer. All arithmetic runs under the pinned `Decimal` context; no float, wall-clock, or RNG
  enters any value or id. The [locked architecture](phase15-analytics-locked.md) is the normative
  spec.
- [Cross-Sectional Signal Diagnostics](phase16-signal-diagnostics-locked.md) — Phase 16: a
  signal-diagnostics layer *parallel* to Phase 12 (the diagnostic sibling of the backtester),
  strictly *above* the Phase 9 universe, Phase 10 panel, and Phase 11 price layers and composing
  them only — it never consumes a `BacktestResult`. A declarative, content-addressed
  `SignalDiagnosticsSpecification` (one signal `metric_key`, its explicit `MetricPeriod`, a Phase 9
  `UniverseSpecification`, a Phase 12 `RebalanceSchedule` of evaluation `as_of` instants, a `"<n>d"`
  forward horizon, a quantile count, the closed IC-method set, and both corpus pins) drives
  `SignalDiagnosticsEngine.evaluate`, which re-verifies **both** corpora (fundamentals + market) and
  fails closed on any pin mismatch (SD-1 — a changed corpus yields a different `diagnostics_id`). At
  each scheduled `T` it reads the signal as a **PIT-eligible-at-`T`** value (SD-3) and pairs it
  against the realized **forward** return over the horizon; a member lacking a PIT signal or a
  computable forward return is excluded and recorded in coverage, never imputed (SD-4). It computes
  per-date Spearman + Pearson IC, quantile-bucket profiles + a top-minus-bottom spread, and an IC
  summary (mean, population std, information ratio, t-stat, hit-rate). The forward return is a
  diagnostic, **not** a PIT value — no `Pit*` type, no as-of accessor; `boundary_kind="pit"`
  documents only the signal side (SD-2). Every undefinable statistic is a first-class `UNDEFINED`
  cell with its reason — never fabricated, never a divide-by-zero. The sealed `SignalDiagnostics` is
  a `ResearchRecord` persisted write-once to the existing sidecar (no new store), byte-identically
  round-tripping; `diagnostics_id` folds the engine + formula + spec version, the full declared
  request, both corpus pins, and the `result_hash` over the computed answer. All arithmetic runs
  under the pinned `Decimal` context; no float, wall-clock, or RNG enters any value or id. The
  [locked architecture](phase16-signal-diagnostics-locked.md) is the normative spec.
- [Multi-Factor Performance Attribution](phase17-factor-attribution-locked.md) — Phase 17: a
  multi-factor attribution layer strictly *above* Phase 12 — a sibling of the Phase 15 analytics
  layer and the multi-factor generalization Phase 15 explicitly deferred — a pure consumer of
  already-sealed, PIT-correct `BacktestResult`s. A declarative, content-addressed
  `AttributionSpecification` (a `subject_id`, an **ordered** tuple of at most `K_MAX = 8` factor
  `backtest_id`s — each a sealed backtest, generalizing the Phase 15 D3 benchmark convention to *K*
  factors, D1 — and the annualization convention, folded into identity) drives
  `AttributionEngine.attribute`, which re-verifies each referenced backtest's content hash from the
  shared sidecar (fail closed on any absent/drifted reference), enforces commensurability (same
  `schedule_id`, equal return length, same engine version — FA-3) and `n >= K + 2` degrees of
  freedom, and regresses the subject's **excess** return on the *K* factor **excess** returns
  (excess-on-excess) via an exact-`Decimal` LDLᵀ solve with an exact zero-pivot test. It reports
  per-factor betas + alpha, R² / adjusted R² / residual std error, classical coefficient std errors
  / t-statistics (D5), and a sample mean-excess decomposition. Every undefinable statistic (singular
  design, zero-variance regressand, perfect fit) is a first-class `UNDEFINED` cell with its reason —
  never a fabricated coefficient, silently dropped factor, or divide-by-zero (FA-4). The output is
  **ex-post, not PIT** — `FactorAttribution` is not a `Pit*` type and exposes no as-of accessor;
  `boundary_kind="pit"` documents only that the underlying backtests were PIT walks (FA-2). Distinct
  corpus pins are surfaced as `pin_mismatch`, never silently reconciled (FA-1). The sealed
  `FactorAttribution` is a `ResearchRecord` persisted write-once to the existing sidecar (no new
  store), byte-identically round-tripping; `attribution_id` folds the engine + formula version, the
  full declared request, the subject and every ordered factor `result_hash`, and the `result_hash`
  over the computed answer (one id, D2). Only a deterministic residual **digest** is persisted, never
  the series (D4). All arithmetic runs under the pinned `Decimal` context; no float, wall-clock, or
  RNG enters any value or id. The [locked architecture](phase17-factor-attribution-locked.md) is the
  normative spec.
- [Engineering Principles](../ARCHITECTURE.md#engineering-principles) — the
  non-negotiable principles guiding the project.
- [Contributing](../CONTRIBUTING.md) — how to set up a development environment
  and contribute.
- [Security](../SECURITY.md) — how to report vulnerabilities.

## Status

The point-in-time data, metrics, universe, panel, market-data, backtesting,
comparative-research, research-reporting, performance-analytics, signal-diagnostics, and
multi-factor performance-attribution layers are implemented (Phases 1–17). Source ingestion
connectors remain planned; the engine operates over content-addressed corpora it is given.
