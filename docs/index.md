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
- [Cross-Sectional Factor-Return Regression](phase18-cross-sectional-regression-locked.md) — Phase
  18: a cross-sectional factor-return-regression layer (the Fama–MacBeth method) — the multivariate
  cross-sectional sibling of the Phase 16 signal-diagnostics layer, as Phase 17 is the multivariate
  time-series sibling of Phase 15 — sitting strictly *above* the Phase 9 universe, Phase 10 panel,
  and Phase 11 price layers and composing them only (it never consumes a `BacktestResult`). A
  declarative, content-addressed `CrossSectionalRegressionSpecification` (a name, an **ordered** tuple
  of at most `K_MAX = 8` `FactorSpec` signals — each a `(metric_key, MetricPeriod)`, order semantic
  and never sorted, the display `label` identity-invisible — a Phase 9 `UniverseSpecification`, a
  Phase 12 `RebalanceSchedule` of evaluation `as_of` instants, a `"<n>d"` forward horizon, an
  intercept flag defaulting on, and the two corpus pins — all folded into identity) drives
  `CrossSectionalRegressionEngine.estimate`, which re-verifies **both** corpora and fails closed on
  any pin mismatch or non-unique normalizer (XS-1). At each scheduled `T` it rebuilds membership PIT
  as-of `T` (survivorship-free), reads the *K*-signal cross-section as **PIT-eligible-at-`T`** values
  via `panel_across(as_of=T)` (XS-3), and pairs each member with its realized **forward** return over
  `[T, T+h]` trading days through the Phase 11 PIT-gated adjusted view (the Phase 16 forward-return
  machinery reused verbatim); a member lacking any signal at `T` or a computable forward return is
  excluded and recorded in coverage, never imputed (XS-4). When the eligible-member count clears the
  degrees-of-freedom floor (`n_members >= K + include_intercept + 1`) it runs one exact-`Decimal`
  cross-sectional OLS of the forward returns on the *K* **raw** signals (plus an optional intercept)
  via the shared `quantforge._linalg` LDLᵀ solver with an **exact zero-pivot test** — a below-floor or
  singular date is a recorded `UNDEFINED` block, never raised — then aggregates each coefficient's
  per-date series into a Fama–MacBeth premium (time-series mean, plain **population** standard error
  `popStd/√M`, t-statistic). A run yielding fewer than two valid dates fails closed. The output is
  **ex-post, not PIT** — `CrossSectionalRegression` is not a `Pit*` type and exposes no as-of accessor;
  `boundary_kind="pit"` documents only that the signal side was PIT-eligible (XS-2). Every undefinable
  statistic (a singular/collinear design, insufficient members, a zero-variance regressand, no or a
  single valid date, zero cross-date dispersion) is a first-class `UNDEFINED` cell with its reason —
  never a fabricated `0`, dropped factor, or divide-by-zero. The sealed `CrossSectionalRegression` is a
  `ResearchRecord` persisted write-once to the existing sidecar (no new store), byte-identically
  round-tripping; `crosssection_id` folds the engine + formula + spec version, the full declared
  request, **both** corpus pins, and the `result_hash` over the computed answer (coverage is audit
  metadata and is not folded). All arithmetic runs under the pinned `Decimal` context; no float,
  wall-clock, or RNG enters any value or id. The
  [locked architecture](phase18-cross-sectional-regression-locked.md) is the normative spec.
- [Factor-Portfolio Construction](phase19-factor-portfolio-locked.md) — Phase 19: a
  characteristic-sorted long/short factor-portfolio-construction layer — the first member of a new
  **portfolio-construction** capability class, a *constructive* sibling of the Phase 16
  signal-diagnostics layer — sitting strictly *above* the Phase 9 universe, Phase 10 panel, and Phase
  11 price layers and composing them only (it consumes **no** `BacktestResult` and produces none,
  P19-5). A declarative, content-addressed `FactorPortfolioSpecification` (a name, one signal
  `metric_key` + the explicit `MetricPeriod` it is read for, a Phase 9 `UniverseSpecification`, a
  Phase 12 `RebalanceSchedule` of evaluation `as_of` instants, a `"<n>d"` forward horizon, a quantile
  count `Q >= 2`, a leg-weighting scheme — v1 closed vocabulary `{"equal"}` — the annualization
  convention `risk_free_per_period` / `periods_per_year`, and the two corpus pins — all folded into
  identity) drives `FactorPortfolioEngine.construct`, which re-verifies **both** corpora and fails
  closed on any pin mismatch or non-unique normalizer (P19-1). At each scheduled `T` it rebuilds
  membership PIT as-of `T` (survivorship-free), reads the signal cross-section as
  **PIT-eligible-at-`T`** values via `panel_across(as_of=T)` (P19-3), and pairs each member with its
  realized **forward** return over `[T, T+h]` trading days through the Phase 11 PIT-gated adjusted
  view (the Phase 16 forward-return machinery reused verbatim); a member lacking the PIT signal at
  `T` or a computable forward return is excluded and recorded in coverage, never imputed (P19-4). It
  sorts the surviving members into `Q` quantile buckets by the PIT signal (the Phase 16
  `quantile_buckets` rule reused verbatim), forms the **long** (top bucket) + **short** (bottom
  bucket) legs, equal-weights each leg, and computes the per-period factor return `f_T = mean(long) -
  mean(short)` (high-minus-low on the raw signal, dollar-neutral, gross); a period below the member
  floor (`n_members < 2·Q`) or with an empty long/short leg is a recorded `UNDEFINED` period, never
  raised. It then aggregates the `M` valid per-period returns into a summary — compounded cumulative,
  mean, **population** volatility, annualized Sharpe (via `Decimal.sqrt`), the mean's t-statistic
  `mean/(popStd/√M)`, and hit rate. A run yielding fewer than two valid periods fails closed. The
  output is **ex-post, not PIT** — `FactorPortfolio` is not a `Pit*` type and exposes no as-of
  accessor; `boundary_kind="pit"` documents only that the signal side was PIT-eligible (P19-2), and
  it is not a `BacktestResult` (P19-5). Every undefinable statistic (insufficient members, an empty
  long/short leg, no or a single valid period, zero return variance) is a first-class `UNDEFINED`
  cell with its reason — never a fabricated `0`, `NaN`/`Inf`, or divide-by-zero. The sealed
  `FactorPortfolio` is a `ResearchRecord` persisted write-once to the existing sidecar (no new store),
  byte-identically round-tripping; `factor_portfolio_id` folds the engine + formula + spec version,
  the full declared request, **both** corpus pins, and the `result_hash` over the computed answer
  (per-period leg membership and coverage are audit metadata and are not folded). All arithmetic runs
  under the pinned `Decimal` context; no float, wall-clock, or RNG enters any value or id. The
  [locked architecture](phase19-factor-portfolio-locked.md) is the normative spec.
- [Factor Risk Model](phase20-factor-risk-model-locked.md) — Phase 20: a factor-risk-modelling
  layer strictly *above* Phase 19 — the first member of a new **risk-modelling** capability class,
  a pure-consumer sibling of the Phase 15/17 backtest-consumer layers (it references sealed
  artifacts, not a raw corpus). A declarative, content-addressed `FactorRiskSpecification` (a name,
  an **ordered** tuple of `2..N_MAX = 16` sealed `FactorPortfolio` ids — order semantic, no
  duplicate — and the annualization convention `periods_per_year`, folded into identity) drives
  `FactorRiskEngine.estimate`, which resolves and re-verifies each referenced factor from the shared
  sidecar (folding each factor's `result_hash` for transitive pinning, FR-1), enforces
  commensurability — one shared `schedule_id` **and** one `factor_portfolio_engine_version_id`, else
  fail closed (FR-3; a corpus-pin difference is surfaced as `pin_mismatch`, never raised or
  reconciled) — and complete-case aligns the factors' KNOWN `(as_of, factor_return)` series on the
  intersection of dates where **every** factor is KNOWN (ascending; never filled or interpolated),
  requiring at least `_MIN_PERIODS = 2` common dates or it fails closed (FR-4). Over that window it
  estimates, under the pinned `Decimal` context, the per-factor mean + **population** volatility
  vectors (`√((1/M)Σ(f-mean)²)` via `Decimal.sqrt`), the `N x N` population covariance matrix
  `cov(i,j) = (1/M)Σ(f_i-mean_i)(f_j-mean_j)`, and the companion correlation matrix
  `cov(i,j)/(vol_i·vol_j)` — per-period and annualized (`vol·√ppy`, `cov·ppy`), stored as the
  **upper triangle** only. A zero-variance factor's correlation (its `0/0` diagonal included) is a
  first-class `UNDEFINED` `ZERO_VARIANCE` cell — never a divide-by-zero; means, volatilities, and
  covariances stay KNOWN. The output is **ex-post, not PIT** — `FactorRiskModel` is not a `Pit*`
  type and exposes no as-of accessor; `boundary_kind="pit"` documents only that the underlying
  factor portfolios were PIT walks (FR-2), and it is not a `BacktestResult` (FR-5). The sealed
  `FactorRiskModel` is a `ResearchRecord` persisted write-once to the existing sidecar (no new
  store), byte-identically round-tripping; `factor_risk_id` folds the engine + formula + spec
  version, the declared request, the **ordered** factor `result_hash`es, and the `result_hash` over
  the computed answer (coverage is audit metadata and is not folded). All arithmetic runs under the
  pinned `Decimal` context; no float, wall-clock, or RNG enters any value or id. The
  [locked architecture](phase20-factor-risk-model-locked.md) is the normative spec.
- [Portfolio Optimization](phase21-portfolio-optimization-locked.md) — Phase 21: a
  factor-risk-aware portfolio-optimization layer strictly *above* Phase 20 — the **first
  optimization layer** in the project and the first member of a new **optimization** capability
  class, the pure-consumer sibling of Phase 20 (it references one sealed `FactorRiskModel`, not a
  raw corpus). A declarative, content-addressed `PortfolioOptimizationSpecification` (a name, exactly
  one sealed `factor_risk_id`, the objective `minimum_variance` — the sole v1 vocabulary — and the
  constraint flag `fully_invested`, which must be identically `True`, all folded into identity)
  drives `PortfolioOptimizationEngine.optimize`, which resolves and re-verifies the referenced model
  from the shared sidecar (folding its `result_hash` for transitive pinning, PO-1; a missing / drifted
  / non-`FactorRiskModel` reference fails closed), re-checks the inherited factor-count bound
  `2..N_MAX = 16`, and reconstructs the full symmetric `N x N` factor covariance `Σ` fail-closed from
  the sealed **upper-triangle** cells — consumed as-is, never recomputed, shrunk, or regularized
  (PO-3). Under the pinned `Decimal` context it solves the **fully-invested global minimum-variance**
  problem `min wᵀΣw s.t. 1ᵀw = 1` in **closed form** via the existing exact-`Decimal` `_linalg` LDLᵀ
  primitives (`w = Σ⁻¹1 / 1ᵀΣ⁻¹1`, unchanged `_linalg`): per-factor GMV weights in factor order (a
  weight may be negative), achieved per-period variance `wᵀΣw`, and volatility. A non-positive-definite
  `Σ` — the exact LDLᵀ zero-pivot test — is a first-class `UNDEFINED` `SINGULAR_COVARIANCE` result
  (every weight / variance / volatility UNDEFINED together), never a divide-by-zero, pseudo-inverse,
  dropped factor, or repaired matrix (PO-4). The output is **ex-post, not PIT** — `PortfolioOptimization`
  is not a `Pit*` type and exposes no as-of accessor (PO-2), and it is not a `BacktestResult` and
  performs no execution (PO-5). The sealed `PortfolioOptimization` is a `ResearchRecord` persisted
  write-once to the existing sidecar (no new store), byte-identically round-tripping; `optimization_id`
  folds the engine + solve + spec version, the declared request + canonical constraint spec, the
  covariance basis, the referenced `factor_risk_id` + its `result_hash`, and the `result_hash` over the
  computed answer. All arithmetic runs under the pinned `Decimal` context; no float, iteration,
  wall-clock, or RNG enters any value or id. The
  [locked architecture](phase21-portfolio-optimization-locked.md) is the normative spec.
- [Walk-Forward Out-of-Sample Evaluation](phase22-walk-forward-evaluation-locked.md) — Phase 22:
  a walk-forward out-of-sample-evaluation layer strictly *above* Phase 21 — the **first genuine
  consumer** of the Phase 21 optimizer and the project's first **train-before-test** temporal
  discipline. A declarative, content-addressed `WalkForwardEvaluationSpecification` (a name, exactly
  one sealed `optimization_id` recipe, and a `TrainingPolicy` — `expanding`\|`rolling`,
  `min_train_periods >= 2`, `test_periods >= 1`, `rolling_length` iff rolling — all folded into
  identity) drives `WalkForwardEvaluationEngine.evaluate`, which resolves and re-verifies the recipe
  (id match, `status = OPTIMAL`, objective `minimum_variance`, constraint `{"fully_invested": True}`,
  WF-5) and, transitively, its `FactorRiskModel` (with a `result_hash` pin match) and every
  `FactorPortfolio` (WF-1), inherits one shared `risk_free_per_period`, and complete-case aligns the
  factors' KNOWN `(as_of, factor_return)` series on the common date axis (WF-6). It partitions that
  axis into ordered `train → test` windows with a strict no-look-ahead split `train_end == test_start`
  (WF-2), and per window **re-estimates** the covariance (Phase 20 method), **re-solves** the
  fully-invested GMV weights (Phase 21 method), and **realizes** them held constant against the
  strictly-subsequent test returns `r_t = Σ_i w_{k,i}·f_{i,t}`, sealing per-window and aggregate
  **predicted-vs-realized** variance. A non-positive-definite training covariance is a first-class
  `UNDEFINED` `SINGULAR_TRAINING_COVARIANCE` window, never repaired (WF-4); fewer than 2 REALIZED
  windows fails closed. It chains the OOS returns and summarizes them by composing the Phase 19
  `series_summary` (compounded cumulative, mean, population volatility, annualized Sharpe, t-statistic,
  hit rate). Phase 22 introduces **no new numerical formula** — it composes three pinned pure methods
  (Phase 19/20/21), whose versions are folded into the engine identity (WF-5) — and no `_linalg`
  change. The output is **ex-post — not a PIT value and not a `BacktestResult`** (WF-3). The sealed
  `WalkForwardEvaluation` is a `ResearchRecord` persisted write-once to the existing sidecar (no new
  store), byte-identically round-tripping; `walk_forward_id` folds the engine + composed-method +
  decimal-context version, the declared request + canonical training policy, the inherited
  `schedule_id`, the referenced `optimization_id` + its `result_hash`, and the `result_hash` over the
  computed walk. All arithmetic runs under the pinned `Decimal` context; no float, iteration,
  wall-clock, or RNG enters any value or id. The
  [locked architecture](phase22-walk-forward-evaluation-locked.md) is the normative spec.
- [Out-of-Sample Research-Campaign Evaluation](phase23-research-campaign-evaluation-locked.md) —
  Phase 23: a research-campaign-evaluation layer strictly *above* Phase 22 — the **first genuine
  consumer** of the Phase 22 terminal leaf and the project's first **selection-bias /
  meta-analysis** layer. A declarative, content-addressed `ResearchCampaignSpecification` (a name,
  an **ordered** tuple of `2..N_MAX = 64` sealed `WalkForwardEvaluation` ids — the *trials* of one
  research campaign, order semantic and never sorted — and a per-period benchmark Sharpe `SR*`
  defaulting to `"0"`, all folded into identity) drives `ResearchCampaignEngine.evaluate`, which
  resolves and re-verifies each trial from the shared sidecar (id match, roll-up `status =
  REALIZED`, folding each `result_hash` for transitive pinning, CE-1) and enforces
  commensurability — one shared `schedule_id` **and** one `factor_portfolio_engine_version_id`,
  else fail closed (CE-3; a corpus-pin difference is surfaced as `pin_mismatch`, never reconciled).
  Per trial it re-derives from the sealed `oos_returns` (with the inherited `risk_free_per_period`,
  never the sealed annualized Sharpe) the per-period excess-return **Sharpe**, **skew**, and
  **non-excess kurtosis** and the **Probabilistic Sharpe Ratio** `PSR(SR*)`; across trials it takes
  the search size `N` as the count of **all** submitted trials (CE-2), the **population** variance
  `V` of the valid trials' Sharpe ratios, the **expected-maximum Sharpe under the null** `SR₀ =
  √V·[(1−γ)·Z⁻¹(1−1/N)+γ·Z⁻¹(1−1/(N·e))]`, and the headline **Deflated Sharpe Ratio** `DSR =
  PSR(SR₀)` of the selected (max-Sharpe, ties→lowest index) trial. It introduces exactly **one** new
  numerical primitive — a deterministic exact-`Decimal` standard-normal `Φ` (an all-positive-term
  `erf` series) / `Z⁻¹` (a fixed-iteration bisection), phase-local, **not** an `_linalg` change
  (CE-5) — and composes a self-contained exact-`Decimal` moment computation. Every undefinable
  statistic (a trial with fewer than two OOS periods, zero OOS variance, or a degenerate PSR
  estimator; a campaign with fewer than `MIN_VALID_TRIALS = 2` valid trials) is a first-class
  `UNDEFINED` cell with its reason, excluded from selection and `V` — never a fabricated `0` or
  divide-by-zero (CE-4); the record still seals. The output is **ex-post — not a PIT value and not a
  `BacktestResult`** — `boundary_kind="pit"` documents only that the underlying trials were PIT
  walks (CE-6). The sealed `ResearchCampaignEvaluation` is a `ResearchRecord` persisted write-once to
  the existing sidecar (no new store), byte-identically round-tripping; `campaign_id` folds the
  engine + method + normal-primitive + decimal-context version, the declared request (name, spec
  version, the **ordered** trial ids, the benchmark Sharpe), the **ordered** trial `result_hash`es,
  and the `result_hash` over the computed answer. All arithmetic runs under the pinned `Decimal`
  context; no float, wall-clock, or RNG enters any value or id. The
  [locked architecture](phase23-research-campaign-evaluation-locked.md) is the normative spec.
- [Pairwise Out-of-Sample Strategy Comparison](phase24-strategy-comparison-locked.md) —
  Phase 24: the platform's first **relative / comparative testing** layer and the second
  consumer of the Phase 22 terminal leaf (the first to read `oos_returns` as a *series*). A
  declarative, content-addressed `StrategyComparisonSpecification` (a name and an **ordered**
  tuple of `2..N_MAX = 32` sealed `WalkForwardEvaluation` ids — the *strategies* of one
  comparison, order semantic and never sorted, fixing the `strategy_1..N` labels and the
  upper-triangle pair order) drives `StrategyComparisonEngine.compare`, which resolves and
  re-verifies each strategy (id match, roll-up `status = REALIZED`, folding each `result_hash`
  for transitive pinning, SC-1) and enforces commensurability — one shared `schedule_id`,
  `factor_portfolio_engine_version_id`, `periods_per_year`, **and** `risk_free_per_period`,
  else fail closed (SC-2; a corpus-pin difference is surfaced as `pin_mismatch`). It
  **reconstructs** each strategy's realized OOS series by re-resolving its transitive
  `optimization → risk model → factors` chain and recomputing the deterministic complete-case
  **calendar-date** axis (identical to the walk engine's logic, guarded against the sealed
  `common_periods` / `oos_returns`, SC-3), then over each upper-triangle `(i<j)` pair aligned
  by date intersection seals the mean per-period difference `d̄`, its population-variance
  standard error, the paired `t = d̄/stderr`, the two-sided `p = 2·(1 − Φ(|t|))` (via the
  Phase 23 `Φ`, now extracted byte-identically to a shared `_stats/normal.py`), and the
  descriptive Sharpe point difference. Every undefinable pair (overlap `<
  MIN_OVERLAP_PERIODS = 2` → `INSUFFICIENT_OVERLAP`; zero paired-difference variance →
  `ZERO_DIFFERENCE_VARIANCE` on `t`/`p`; an undefined leg Sharpe → `UNDEFINED_STRATEGY_SHARPE`
  on `sharpe_diff`) is a first-class `UNDEFINED` cell, never a divide-by-zero (SC-4). Only the
  `i<j` triangle is stored; `(j,i)` is an exact sign-flip (SC-8). Measurement-only — no
  family-wise / FDR correction (SC-7). The output is **ex-post — not a PIT value and not a
  `BacktestResult`** (SC-6). The sealed `StrategyComparison` is a `ResearchRecord` persisted
  write-once to the existing sidecar (no new store), byte-identically round-tripping;
  `strategy_comparison_id` folds the engine + method + normal + decimal-context version, the
  declared request, the ordered strategy `result_hash`es, `periods_per_year`, and the
  `result_hash` over the computed answer. Introduces no new numerical primitive, no `_linalg`
  change, no RNG/iteration, and no runtime dependency. The
  [locked architecture](phase24-strategy-comparison-locked.md) is the normative spec.
- [Multiple-Comparison Correction](phase25-multiple-comparison-correction-locked.md) —
  Phase 25: the platform's first consumer of a **meta-analysis** artifact (turning the
  Phase 24 terminal-leaf `StrategyComparison` into an input) and its first **family-wise /
  false-discovery-rate** control — the future consumer SC-7 explicitly deferred to. A
  declarative, content-addressed `MultipleComparisonSpecification` (a name, exactly **one**
  sealed `source_strategy_comparison_id`, a declared `alpha ∈ (0, 1)` canonicalized at
  construction, and an ordered, duplicate-free tuple of `CorrectionMethod`s — default Holm +
  Benjamini–Yekutieli, both valid under arbitrary dependence) drives
  `MultipleComparisonEngine.correct`, which resolves the one comparison from the shared
  sidecar via `store.read_as(id, StrategyComparison.from_dict)`, re-verifies its
  `research_result_id` equals the request, and folds its `result_hash` for transitive pinning
  (fail closed on any missing / non-`StrategyComparison` / id-mismatched reference, MC-1). It
  collects the family `F` = the source's KNOWN pairwise `p` values in upper-triangle order —
  each UNDEFINED pairwise cell (`INSUFFICIENT_OVERLAP`, `ZERO_DIFFERENCE_VARIANCE`) a
  first-class `ExcludedCell` carrying its reason, never imputed (MC-3) — and seals the
  coverage (`n_pairs_total`, family size `m`, `n_excluded`, MC-2). For each method, under the
  pinned `Decimal` context, it computes each family member's adjusted `p` value + rejection
  flag via one ascending sort (ties → family `(i, j)` index) plus the closed-form step
  transforms — Bonferroni `min(1, m·p)`, Holm step-down under a running max, Benjamini–Hochberg
  step-up under a running min, Benjamini–Yekutieli the same scaled by the harmonic constant
  `c(m) = Σ_{k=1}^{m} 1/k` — tied `p` values collapsing to one adjusted value, every value
  capped at `1`, and rejection defined **uniformly** as `p_adj ≤ alpha` (MC-4/MC-5). Each
  method seals its honest `error_rate` / `dependence` label; Benjamini–Hochberg's
  independence / PRDS assumption is sealed alongside its results so it can never be mistaken
  for a dependence-robust guarantee (MC-6). An empty family (`m = 0`) seals empty per-method
  cell lists, never a divide-by-zero. The output is **ex-post — not a PIT value** (MC-6):
  `MultipleComparisonCorrection` is not a `Pit*` type and exposes no as-of accessor;
  `boundary_kind = "pit"` is carried unchanged from the source comparison. The sealed
  `MultipleComparisonCorrection` is a `ResearchRecord` persisted write-once to the existing
  sidecar (no new store), byte-identically round-tripping; `multiple_comparison_id` folds the
  engine + method + decimal-context version, the declared request (name, spec version,
  `alpha`, the ordered method list), the source comparison's id **and** `result_hash`, and the
  `result_hash` over the computed answer. Introduces no new numerical primitive (it reuses no
  standard-normal primitive), no `_linalg` change, no RNG / float / iterative solver, and no
  runtime dependency. The
  [locked architecture](phase25-multiple-comparison-correction-locked.md) is the normative
  spec.
- [Risk-Forecast Calibration](phase26-risk-forecast-calibration-locked.md) —
  Phase 26: the first consumer of the per-window `predicted_variance` / `realized_variance`
  payload the Phase 22 architecture reserved, and the platform's first **out-of-sample
  risk-model validation** layer (does the Phase-20 covariance the whole GMV chain rests on
  actually forecast realized OOS risk?). A declarative, content-addressed
  `RiskForecastCalibrationSpecification` (a name and exactly **one** sealed
  `source_walk_forward_id`; no per-request numerical parameter) drives
  `RiskForecastCalibrationEngine.calibrate`, which resolves the one walk from the shared
  sidecar via `store.read_as(id, WalkForwardEvaluation.from_dict)`, re-verifies its
  `research_result_id` equals the request, and folds its `result_hash` for transitive pinning
  (fail closed on any missing / non-`WalkForwardEvaluation` / id-mismatched reference, RC-1).
  It classifies each window in source order into the *calibratable* family — REALIZED, with a
  KNOWN strictly-positive `predicted_variance` and a KNOWN `realized_variance` — every
  non-calibratable window a first-class `ExcludedWindow` carrying its reason
  (`WINDOW_UNDEFINED`, `SINGLE_VALID_PERIOD`, and the defensive `ZERO_PREDICTED_VARIANCE` /
  `PREDICTED_VARIANCE_UNDEFINED`), never imputed (RC-3), and seals the coverage (`n_windows`,
  `n_calibratable`, `n_excluded`, RC-2). Over the family, under the pinned `Decimal` context,
  it seals per window `variance_ratio = realized / predicted` and `volatility_ratio = √realized
  / √predicted`, and across the `k`-window family the mean `variance_ratio`, the pooled
  `aggregate_bias = Σrealized / Σpredicted` (a Barra-style bias ratio: `>1` under-forecasts
  risk), the population dispersion, the under-forecast frequency, and the min / max
  (RC-4/RC-5). `calibration_status` is `CALIBRATED` iff `n_calibratable ≥
  MIN_CALIBRATABLE_WINDOWS = 2`, else `UNDEFINED` (`INSUFFICIENT_CALIBRATABLE_WINDOWS`) with the
  per-window ratios still sealed; an empty family seals every aggregate UNDEFINED
  (`NO_CALIBRATABLE_WINDOWS`), never a divide-by-zero. Sealed forecasts and outcomes are
  consumed **verbatim**, never recomputed (RC-4). The output is **ex-post — not a PIT value and
  not a `BacktestResult`** (RC-6): `RiskForecastCalibration` is not a `Pit*` type and exposes no
  as-of accessor; `boundary_kind = "pit"` is carried unchanged from the source walk. The sealed
  `RiskForecastCalibration` is a `ResearchRecord` persisted write-once to the existing sidecar
  (no new store), byte-identically round-tripping; `risk_forecast_calibration_id` folds the
  engine + method + decimal-context version, the declared request (name, spec version), the
  source walk's id **and** `result_hash`, the `MIN_CALIBRATABLE_WINDOWS` floor, and the
  `result_hash` over the computed answer. Introduces no new numerical primitive (`Decimal.sqrt`
  the only transcendental; it reuses no standard-normal primitive), no `_linalg` / `_stats`
  change, no RNG / float / iterative solver, and no runtime dependency. The
  [locked architecture](phase26-risk-forecast-calibration-locked.md) is the normative spec.
- [Walk-Forward Turnover & Stability](phase27-turnover-stability-locked.md) —
  Phase 27: the first consumer of the per-window GMV `weights` payload the Phase 22
  architecture reserved (no prior consumer read it), and the platform's first
  **implementability** lens (is the decision the strategy actually makes stable and tradeable
  over time?). A declarative, content-addressed `WalkForwardStabilitySpecification` (a name and
  exactly **one** sealed `source_walk_forward_id`; no per-request numerical parameter) drives
  `WalkForwardStabilityEngine.analyze`, which resolves the one walk from the shared sidecar via
  `store.read_as(id, WalkForwardEvaluation.from_dict)`, re-verifies its `research_result_id`
  equals the request, and folds its `result_hash` for transitive pinning (fail closed on any
  missing / non-`WalkForwardEvaluation` / id-mismatched reference, WS-1). It classifies each
  window in source order — a REALIZED window contributes its KNOWN GMV weight vector parsed once
  to `Decimal` (a malformed vector — length ≠ `n_factors`, or any non-KNOWN cell — is a corrupt
  source and fails closed, WS-4), an UNDEFINED window is a first-class `ExcludedWindow`
  (`WINDOW_UNDEFINED`) that also breaks the weight path, never imputed (WS-3) — and seals the
  coverage (`n_windows`, `n_realized`, `n_excluded`, `n_transitions`, WS-2). Over the family,
  under the pinned `Decimal` context, it seals per REALIZED window `gross_leverage = Σ|w|`,
  `concentration_hhi = Σw²`, `effective_breadth = 1/HHI`, `max_abs_weight = max|w|`, and the
  one-way `turnover_from_prev = ½Σ|Δw|` against the immediately-preceding REALIZED window
  (UNDEFINED `NO_PRIOR_REALIZED_WINDOW` across a gap), and across the walk the turnover mean /
  population dispersion / max / min and the concentration mean gross leverage / max gross
  leverage / mean HHI / mean effective breadth (WS-5). `stability_status` is `STABLE` iff the
  realized-adjacent transitions meet `MIN_STABILITY_TRANSITIONS = 2`, else `UNDEFINED`
  (`INSUFFICIENT_TRANSITIONS`) with the per-window cells and aggregates still sealed; a walk
  with no transitions seals every turnover aggregate UNDEFINED (`NO_TRANSITIONS`), a walk with
  no REALIZED windows every concentration aggregate UNDEFINED (`NO_REALIZED_WINDOWS`), a
  defensive `HHI = 0` an UNDEFINED `ZERO_CONCENTRATION` breadth — never a divide-by-zero, never
  a fabricated trade (WS-3). Sealed weights are consumed **verbatim**, never re-solved (WS-4).
  The output is **ex-post — not a PIT value and not a `BacktestResult`** (WS-6):
  `WalkForwardStability` is not a `Pit*` type and exposes no as-of accessor; `boundary_kind =
  "pit"` is carried unchanged from the source walk. The sealed `WalkForwardStability` is a
  `ResearchRecord` persisted write-once to the existing sidecar (no new store), byte-identically
  round-tripping; `walk_forward_stability_id` folds the engine + method + decimal-context
  version, the declared request (name, spec version), the source walk's id **and**
  `result_hash`, the `MIN_STABILITY_TRANSITIONS` floor, and the `result_hash` over the computed
  answer. Introduces no new numerical primitive (`Decimal.sqrt` the only transcendental; it
  reuses no standard-normal primitive), no `_linalg` / `_stats` change, no RNG / float /
  iterative solver, and no runtime dependency. The
  [locked architecture](phase27-turnover-stability-locked.md) is the normative spec.
- [Minimum Track-Record Length](phase28-minimum-track-record-length-locked.md) —
  Phase 28: the first consumer of the `ResearchCampaignEvaluation` sealed per-trial moment
  block (Phase 23 sealed each trial's `sharpe` / `skew` / `kurtosis` / `n`; Phase 28 reads
  exactly those), and the platform's first **statistical-power / track-record-adequacy** lens
  (how long a track record must a strategy accumulate before its Sharpe is significant?). A
  declarative, content-addressed `MinimumTrackRecordLengthSpecification` (a name, exactly
  **one** sealed `source_campaign_id`, a confidence `alpha ∈ (0, 1)` — default `0.95` — and a
  benchmark Sharpe `SR*` — default `0`) drives `MinimumTrackRecordLengthEngine.evaluate`, which
  resolves the one campaign from the shared sidecar via
  `store.read_as(id, ResearchCampaignEvaluation.from_dict)`, re-verifies its
  `research_result_id` equals the request, and folds its `result_hash` for transitive pinning
  (fail closed on any missing / non-`ResearchCampaignEvaluation` / id-mismatched reference,
  MT-1). It classifies each trial in source order — a VALID trial whose `sharpe` / `skew` /
  `kurtosis` cells are all KNOWN joins the evaluable family (its three moments parsed once to
  `Decimal`, carried verbatim, never recomputed, MT-4), a source-UNDEFINED trial is a
  first-class `ExcludedTrial` (`TRIAL_UNDEFINED`), the defensive VALID-but-missing-moment case
  is `MOMENTS_UNDEFINED` (MT-3) — and seals the coverage (`n_trials`, `n_evaluable`,
  `n_excluded`, MT-2). Over the family, under the pinned `Decimal` context, it computes
  `Z_alpha = Φ⁻¹(alpha)` once via the reused deterministic exact-`Decimal` `Z⁻¹` bisection
  (`quantforge/_stats/normal.py`, shared with Phase 23 — no new primitive) and seals per trial
  the Bailey–López de Prado `MinTRL = 1 + V·(Z_alpha/(SR − SR*))²` with
  `V = 1 − γ₃·SR + ((γ₄−1)/4)·SR²` — the identical Sharpe-estimator variance the Phase-23 PSR
  uses, of which MinTRL is the exact algebraic inverse — plus `excess_length = n − MinTRL` and,
  across the determined family, the mean / population dispersion / max / min MinTRL and the
  `sufficient_frequency` (the fraction of determined trials whose observed length already meets
  its MinTRL, MT-5). An evaluable trial whose Sharpe does not exceed the benchmark
  (`SHARPE_NOT_ABOVE_BENCHMARK`) or whose estimator variance is non-positive
  (`DEGENERATE_SHARPE_ESTIMATOR`) is a first-class `UNDEFINED` cell whose `excess_length`
  inherits the same reason, never a divide-by-zero (MT-3). `mintrl_status` is `EVALUATED` iff
  the determined family meets `MIN_DETERMINED_TRIALS = 2`, else `UNDEFINED`
  (`INSUFFICIENT_DETERMINED_TRIALS`) with the per-trial cells still sealed; an empty family
  seals every aggregate UNDEFINED (`NO_DETERMINED_TRIALS`), never a divide-by-zero. The output
  is **ex-post — not a PIT value and not a `BacktestResult`** (MT-6): `MinimumTrackRecordLength`
  is not a `Pit*` type and exposes no as-of accessor; `boundary_kind = "pit"` is carried
  unchanged from the source campaign. The sealed `MinimumTrackRecordLength` is a
  `ResearchRecord` persisted write-once to the existing sidecar (no new store), byte-identically
  round-tripping; `minimum_track_record_length_id` folds the engine + method + normal-primitive
  + decimal-context version, the declared request (name, spec version, the canonical
  `confidence` and `benchmark_sharpe`), the source campaign's id **and** `result_hash`, the
  `MIN_DETERMINED_TRIALS` floor, and the `result_hash` over the computed answer. Introduces no
  new numerical primitive (`Decimal.sqrt` the only transcendental; it reuses the shared `Z⁻¹`
  bisection verbatim), no `_linalg` / `_stats` change, no RNG / float / iterative solver, and no
  runtime dependency. The
  [locked architecture](phase28-minimum-track-record-length-locked.md) is the normative spec.
- [Risk-Forecast Calibration Significance](phase29-calibration-significance-locked.md) —
  Phase 29: the first consumer of the sealed `RiskForecastCalibration` summary and the
  calibration analogue of the Phase-24 paired-difference strategy comparison, applied as a
  **one-sample** significance test about the null mean `1`. It answers the one question the
  calibration record never tests: is the risk model's mean variance ratio statistically
  distinguishable from perfect calibration? A declarative, content-addressed
  `CalibrationSignificanceSpecification` (a name and exactly **one** sealed
  `source_calibration_id`; no per-request numerical parameter) drives
  `CalibrationSignificanceEngine.evaluate`, which resolves the one calibration from the shared
  sidecar via `store.read_as(id, RiskForecastCalibration.from_dict)`, re-verifies its
  `research_result_id` equals the request, and folds its `result_hash` for transitive pinning
  (fail closed on any missing / non-`RiskForecastCalibration` / id-mismatched reference, CS-1).
  It gates on the source: only a `CALIBRATED` source whose aggregate `mean_variance_ratio` /
  `variance_ratio_dispersion` cells are KNOWN is tested, else every statistic is a first-class
  UNDEFINED `SOURCE_NOT_CALIBRATED` (CS-2). Consuming the sealed mean `m`, population dispersion
  `s`, and window count `K = n_calibratable` verbatim — never recomputed (CS-4) — under the
  pinned `Decimal` context it seals `standard_error = s/√K`, `t = (m − 1)/standard_error`, and
  the two-sided `p = 2·(1 − Φ(|t|))` clamped to `[0, 1]` via the reused exact-`Decimal`
  `standard_normal_cdf` (`quantforge/_stats/normal.py`, shared with Phase 24 — no new primitive;
  the same population-moment convention `√(variance/n)` as Phase 24, CS-5), plus the descriptive
  `bias_direction` (`UNDER_FORECAST` when `m > 1`, `OVER_FORECAST` when `m < 1`, `UNBIASED` at
  `m == 1`). A zero-dispersion source seals `standard_error` a KNOWN `0` but `t` / `p` UNDEFINED
  (`ZERO_RATIO_DISPERSION`) with the mean and bias direction still KNOWN — never a divide-by-zero
  (CS-3); the record always seals (only a request / reference defect raises). There is no
  per-request numerical parameter — the null mean is the fixed platform constant
  `NULL_MEAN_RATIO = "1"`, folded into identity; the finite-sample Student-`t` is deferred (★),
  matching Phase 24. The output is **ex-post — not a PIT value and not a `BacktestResult`**
  (CS-6): `CalibrationSignificance` is not a `Pit*` type and exposes no as-of accessor;
  `boundary_kind = "pit"` is carried unchanged from the source calibration. The sealed
  `CalibrationSignificance` is a `ResearchRecord` persisted write-once to the existing sidecar
  (no new store), byte-identically round-tripping; `calibration_significance_id` folds the
  engine + method + normal-primitive + decimal-context version, the declared request (name, spec
  version, source calibration id), the source calibration's `result_hash`, the `null_mean_ratio`,
  and the `result_hash` over the computed answer. Introduces no new numerical primitive
  (`Decimal.sqrt` the only extra transcendental; it reuses the shared `Φ` verbatim), no
  `_linalg` / `_stats` change, no RNG / float / iterative solver, and no runtime dependency. The
  [locked architecture](phase29-calibration-significance-locked.md) is the normative spec.
- [Campaign-Level Multiplicity](phase30-campaign-multiplicity-locked.md) —
  Phase 30: the campaign analogue of the Phase 25 `StrategyComparison` correction and the
  first consumer of the `ResearchCampaignEvaluation` sealed per-trial `psr` block (Phase 28
  read the trial `sharpe` / `skew` / `kurtosis` moments; Phase 30 reads exactly the `psr`).
  It answers what the raw per-trial PSR table cannot honestly answer by eye: which trials
  individually beat the benchmark once the whole family of PSR tests is accounted for? A
  declarative, content-addressed `CampaignMultiplicitySpecification` (a name, exactly **one**
  sealed `source_campaign_id`, a declared `alpha ∈ (0, 1)`, and an ordered, duplicate-free
  tuple of `CorrectionMethod`s — default `(HOLM, BENJAMINI_YEKUTIELI)`, the reused Phase 25
  vocabulary) drives `CampaignMultiplicityEngine.correct`, which resolves the one campaign
  from the shared sidecar via `store.read_as(id, ResearchCampaignEvaluation.from_dict)`,
  re-verifies its `research_result_id` equals the request, and folds its `result_hash` for
  transitive pinning (fail closed on any missing / non-`ResearchCampaignEvaluation` /
  id-mismatched reference, CM-1). It collects the family = the source's per-trial one-sided
  p-values `p_i = 1 − PSR_i` over trials whose `psr` is KNOWN, in sealed request order (each
  UNDEFINED-`psr` trial a first-class `ExcludedTrialCell` with its `CampaignUndefinedReason`,
  never imputed, CM-3), and seals the coverage (`n_trials_total`, family `size`, `n_excluded`,
  CM-2). The `p = 1 − PSR` transform is the only added arithmetic — exact `Decimal`, in
  `[0, 1]` by construction because `PSR` is a `Φ` value in `[0, 1]`, no clamp / repair (CM-4).
  For each requested method, under the pinned `Decimal` context, it computes each family
  member's adjusted `p` + rejection flag (`p_adj ≤ alpha`) via
  `quantforge.multiplicity.compute.correct_family` **reused verbatim** (Bonferroni / Holm /
  Benjamini–Hochberg / Benjamini–Yekutieli — no new primitive, no `_stats` / `_linalg`
  change, CM-5), each method sealing its honest `error_rate` / `dependence` label from the
  single source of truth in `multiplicity.model`. An empty family seals empty per-method
  cells, never a divide-by-zero. The output is **ex-post — not a PIT value** (CM-6):
  `CampaignMultiplicityCorrection` is not a `Pit*` type and exposes no as-of accessor;
  `boundary_kind = "pit"` is carried unchanged from the source campaign. The sealed
  `CampaignMultiplicityCorrection` is a `ResearchRecord` persisted write-once to the existing
  sidecar (no new store), byte-identically round-tripping; `campaign_multiplicity_id` folds
  the engine + own method + **reused-correction-core** + decimal-context version (the reused
  `MULTIPLICITY_METHOD_VERSION` is folded, so a change to the shared correction core changes
  this record's identity), the declared request (name, spec version, `alpha`, the **ordered**
  method list), the source campaign's `research_result_id` **and** its `result_hash`, and the
  `result_hash` over the computed answer. Introduces no new numerical primitive, no `_linalg`
  / `_stats` change, no RNG / float / iterative solver, and no runtime dependency. The
  [locked architecture](phase30-campaign-multiplicity-locked.md) is the normative spec.
- [Net-of-Cost Walk-Forward Performance](phase31-net-of-cost-performance-locked.md) —
  Phase 31: the platform's first net-of-cost / execution-aware layer and the first consumer
  of the per-REALIZED-window one-way `turnover_from_prev` Phase 27 sealed. It answers what an
  attractive *gross* OOS Sharpe never does: does the strategy still earn its edge after
  paying a declared cost to trade, and at what cost rate does that edge vanish? A declarative,
  content-addressed `NetOfCostSpecification` (a name, exactly **one** sealed
  `source_stability_id`, and a declared linear one-way `cost_rate` — a non-negative finite
  decimal string canonicalized at construction, folded into identity, never inferred or
  defaulted, NC-3) drives `NetOfCostEngine.evaluate`, which resolves the one stability record
  from the shared sidecar via `store.read_as(id, WalkForwardStability.from_dict)` **and** the
  one `WalkForwardEvaluation` it pins, re-verifying each record's `research_result_id`, type,
  and `result_hash` (fail closed on any missing / wrong-type / id- or hash-mismatched
  reference at either level, NC-1). **The alignment is the load-bearing decision** (NC-2):
  gross performance is a *per-period* chained OOS series while turnover is a *per-window*
  quantity — not zippable. The engine verifies the realized-window indices, the excluded
  windows, and the concatenated per-window sub-series all equal the walk's, then charges
  `cost = cost_rate · turnover_w` at each realized window's **first** OOS period only. A
  realized window with no adjacent realized predecessor (`NO_PRIOR_REALIZED_WINDOW`, carried
  from Phase 27) bears **zero** cost — no fabricated entry cost (a disclosed deviation from
  the proposal's `entry_cost_convention`, NC-3) — and its gross returns pass through. The
  gross moments are read **verbatim** from the walk's sealed summary and the net series is
  summarized with the **reused** Phase 19 `series_summary` (the identical convention Phase 22
  used for gross, so net and gross Sharpe are comparable and the `cost_rate = 0` net moments
  equal the gross moments byte-for-byte — the zero-cost identity; no new primitive, NC-4). It
  seals per-window gross / turnover / cost / net cells, the aggregate net moments, the cost
  drag (`gross − net`, UNDEFINED-propagating), and the parameter-free break-even
  `Σ gross / Σ turnover` — UNDEFINED `DEGENERATE_NO_TURNOVER` when the strategy never trades,
  and an UNDEFINED `net_sharpe` (`ZERO_RETURN_VARIANCE`, reused from Phase 19 — a disclosed
  deviation from the proposal's `DEGENERATE_SHARPE_ESTIMATOR` label) when a cost path makes
  the net series constant, never a divide-by-zero (NC-5). The output is **ex-post /
  counterfactual — not a PIT value** (NC-6): `NetOfCostPerformance` is not a `Pit*` type and
  exposes no as-of accessor; `boundary_kind = "pit"` is carried unchanged from the source. The
  sealed `NetOfCostPerformance` is a `ResearchRecord` persisted write-once to the existing
  sidecar (no new store), byte-identically round-tripping; `net_of_cost_id` folds the engine +
  own method + **reused-summary** + decimal-context version (the reused
  `FACTORPORTFOLIO_FORMULA_VERSION` is folded, an honest transitive pin), the declared request
  (name, spec version), the source stability record's `research_result_id` **and** its
  `result_hash` (transitive pin, reaching the gross walk beneath it), the declared `cost_rate`
  (folds the id, not the result hash), and the `result_hash` over the computed answer.
  Introduces no new numerical primitive, no `_linalg` / `_stats` change, no RNG / float /
  iterative solver, and no runtime dependency. The
  [locked architecture](phase31-net-of-cost-performance-locked.md) is the normative spec.
- [Net-of-Cost Significance](phase32-net-of-cost-significance-locked.md) —
  Phase 32: the platform's first significance test applied to an economic (after-cost)
  quantity and the first consumer of the terminal `NetOfCostPerformance` leaf Phase 31
  sealed — the net-of-cost analogue of the Phase 29 calibration significance test, applied as
  a **one-sample, one-sided (upper-tailed)** test about the null mean `0`. It answers the one
  question the net-of-cost record states the magnitude of but never tests: is the after-cost
  edge statistically distinguishable from zero given the realized sample length? A
  declarative, content-addressed `NetOfCostSignificanceSpecification` (a name and exactly
  **one** sealed `source_net_of_cost_id`, both folded into identity; no per-request numerical
  parameter) drives `NetOfCostSignificanceEngine.evaluate`, which resolves the one net-of-cost
  record from the shared sidecar via `store.read_as(id, NetOfCostPerformance.from_dict)` and
  re-verifies that the resolved record's `research_result_id` equals the requested id and that
  it decodes as a `NetOfCostPerformance` (fail closed on any missing / non-`NetOfCostPerformance`
  / id-mismatched reference); the source's `result_hash` is **folded into the significance
  record's identity**, reaching the stability record → walk → optimization → risk model →
  factors → corpora beneath it (NS-1). It gates on the source: only a `MEASURED` source whose
  aggregate `net_mean` / `net_volatility` cells are KNOWN is tested; a non-`MEASURED` or
  non-KNOWN-mean source seals a first-class UNDEFINED record with every statistic
  `SOURCE_NOT_MEASURED`, `n_periods = 0`, and `edge_direction = None`, never imputed (NS-2).
  Consuming the sealed after-cost mean `m`, population volatility `σ`, and OOS-period count
  `n = n_periods` **verbatim** — never recomputed from the per-window cells or the net return
  series (NS-4) — under the pinned `Decimal` context it seals `standard_error = σ/√n`,
  `t = (m − 0)/standard_error`, and the one-sided upper-tailed `p = 1 − Φ(t)` clamped to
  `[0, 1]` via the **reused** exact-`Decimal` `standard_normal_cdf` (`quantforge/_stats/normal.py`,
  shared with Phase 24 / 29 — no new primitive, no `_stats` / `_linalg` change; the same
  population-moment convention `√(variance/n)` as Phase 24 / 29, so `t = (m/σ)·√n` is the
  classic Sharpe `t`-statistic, NS-5), plus the descriptive `edge_direction` (`PROFITABLE`
  when `m > 0`, `UNPROFITABLE` when `m < 0`, `FLAT` at `m == 0`). A zero-volatility source
  (structurally unreachable for a MEASURED source, guarded defensively) seals `standard_error`
  a KNOWN `0` but `t` / `p` UNDEFINED (`ZERO_NET_VOLATILITY`) with the mean and edge direction
  still KNOWN — never a divide-by-zero (NS-3); the record **always seals** (a data condition is
  never an exception, only a request / reference defect raises). There is **no per-request
  numerical parameter** — the null mean is the fixed platform constant `NULL_MEAN_RETURN = "0"`,
  folded into identity (as Phase 29 folds `NULL_MEAN_RATIO = "1"`); the two-sided value is
  derivable from the sealed `t` and is not separately sealed; the finite-sample Student-`t`
  distribution and a declared benchmark net mean are deferred (★), matching Phase 24 / 29. The
  output is **ex-post — not a PIT value and not a `BacktestResult`** (NS-6):
  `NetOfCostSignificance` is not a `Pit*` type and exposes no as-of accessor; `boundary_kind =
  "pit"` is carried unchanged from the source. The sealed `NetOfCostSignificance` is a
  `ResearchRecord` persisted write-once to the existing sidecar (no new store), byte-identically
  round-tripping; `net_of_cost_significance_id` folds the engine + method + normal-primitive +
  decimal-context version, the declared request (name, spec version, source net-of-cost id),
  the source's `result_hash` (transitive pin), the `null_mean_return`, and the `result_hash`
  over the computed answer. Introduces no new numerical primitive, no `_linalg` / `_stats`
  change, no RNG / float / iterative solver, and no runtime dependency. The
  [locked architecture](phase32-net-of-cost-significance-locked.md) is the normative spec.
- [Strategy Admissibility](phase33-strategy-admissibility-locked.md) —
  Phase 33: the platform's **first multi-source consumer** — it resolves and joins **three**
  sealed verdicts rather than one — and the capstone over the ex-post validator battery. It
  answers the one question no single validator answers: taken together — a stable book, a
  well-calibrated risk model, and a statistically significant after-cost edge — is this
  strategy admissible? A declarative, content-addressed `AdmissibilitySpecification` (a name;
  exactly **one** sealed `source_stability_id` (Phase 27), one
  `source_calibration_significance_id` (Phase 29), and one `source_net_of_cost_significance_id`
  (Phase 32), all descending from one `WalkForwardEvaluation` root; plus a declared level
  `alpha`, a decimal string strictly inside `(0, 1)` canonicalized via
  `str(Decimal(alpha).normalize())` — every field folded into identity, AD-5) drives
  `AdmissibilityEngine.evaluate`, which resolves each of the three records from the shared
  sidecar via `store.read_as(id, <T>.from_dict)`, re-verifies each record's `research_result_id`
  equals the requested id and decodes as its expected type, and folds each `result_hash` into
  `admissibility_id` — reaching the calibration / stability / net-of-cost chains and the shared
  walk root beneath them; any missing / wrong-type / id-mismatched reference at **any** of the
  three sources fails closed with `AdmissibilityConsistencyError` (AD-1). It reads each layer's
  sealed answer **verbatim** — the stability book's `stability_status`, the calibration test's
  two-sided `p_value`, the net-of-cost test's one-sided `p_value` + `edge_direction` — and
  re-derives **no** statistic (AD-4); because the standard-normal Φ CDF was applied and sealed
  by the significance layers, Phase 33 introduces **no new numerical primitive** and only
  compares exact `Decimal` p-values against `alpha`. Under the pinned `Decimal` context it
  decides three criteria in the fixed order STABILITY, CALIBRATION, NET_OF_COST_EDGE (AD-3):
  STABILITY PASSes iff STABLE (else UNDEFINED — never FAILs); CALIBRATION PASSes iff the
  two-sided `p > alpha`, FAILs iff `p ≤ alpha`, UNDEFINED if not TESTED / not KNOWN;
  NET_OF_COST_EDGE PASSes iff the one-sided `p ≤ alpha` **and** the edge is PROFITABLE, FAILs
  if decidable-but-not, UNDEFINED if not TESTED / not KNOWN. The fail-closed roll-up (AD-2):
  UNDEFINED if **any** criterion is UNDEFINED (UNDEFINED dominates a FAIL); ADMISSIBLE iff all
  three PASS; else INADMISSIBLE — the record **always seals** (a data condition is never an
  exception). The output is **ex-post — not a PIT value and not a `BacktestResult`** (AD-6):
  `StrategyAdmissibility` is not a `Pit*` type and exposes no as-of accessor; `boundary_kind =
  "pit"` documents only that the underlying factor portfolios were PIT walks. The sealed
  `StrategyAdmissibility` is a `ResearchRecord` persisted write-once to the existing sidecar (no
  new store), storing only pointers to the three sources and byte-identically round-tripping;
  `admissibility_id` folds the engine + method + decimal-context version, the declared request
  (name, spec version), each of the three source verdicts' `research_result_id` **and**
  `result_hash` (transitive pin), the declared `alpha`, and the `result_hash` over the computed
  answer. Introduces no new numerical primitive, no `_linalg` / `_stats` change, no RNG / float
  / iterative solver, and no runtime dependency. The
  [locked architecture](phase33-strategy-admissibility-locked.md) is the normative spec.
- [Engineering Principles](../ARCHITECTURE.md#engineering-principles) — the
  non-negotiable principles guiding the project.
- [Contributing](../CONTRIBUTING.md) — how to set up a development environment
  and contribute.
- [Security](../SECURITY.md) — how to report vulnerabilities.

## Status

The point-in-time data, metrics, universe, panel, market-data, backtesting,
comparative-research, research-reporting, performance-analytics, signal-diagnostics,
multi-factor performance-attribution, cross-sectional factor-return-regression
(Fama–MacBeth premia), characteristic-sorted long/short factor-portfolio-construction,
factor-risk-model (factor covariance & correlation estimation), factor-risk-aware
portfolio-optimization (fully-invested global minimum-variance), walk-forward out-of-sample
evaluation (train-before-test), out-of-sample research-campaign evaluation with
selection-bias correction (Probabilistic & Deflated Sharpe Ratios), pairwise
out-of-sample strategy comparison (paired-difference t-tests over aligned OOS return series),
multiple-comparison correction over a strategy comparison's pairwise `p`-value family
(Holm / Benjamini–Yekutieli family-wise & false-discovery control), walk-forward
risk-forecast calibration over one evaluation's calibratable-window family (forecast-vs-outcome
variance / volatility ratios and a pooled bias ratio — out-of-sample risk-model validation),
walk-forward portfolio turnover & stability over one evaluation's REALIZED-window family
(per-window gross leverage / concentration / effective breadth / max-abs weight + one-way
turnover and their aggregate profile — the first implementability lens), and minimum
track-record length (MinTRL) over one research campaign's evaluable trials (per-trial
Bailey–López de Prado significance-horizon `MinTRL = 1 + V·(Z_alpha/(SR − SR*))²` and the
aggregate MinTRL profile — the first statistical-power / track-record-adequacy lens), and
risk-forecast calibration significance over one calibration's aggregate family (a one-sample
two-sided large-sample test of whether the mean variance ratio differs from perfect calibration
`1` — the calibration analogue of the paired-difference strategy comparison), and
campaign-level multiplicity correction over one research campaign's per-trial PSR family
(the per-trial one-sided p-values `p_i = 1 − PSR_i` corrected for Holm / Benjamini–Yekutieli
family-wise & false-discovery control — the campaign analogue of the strategy-comparison
correction)
layers are implemented (Phases 1–30). Source ingestion
connectors remain planned; the engine operates over content-addressed corpora it is given.
