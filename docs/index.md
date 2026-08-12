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
selection-bias correction (Probabilistic & Deflated Sharpe Ratios), and pairwise
out-of-sample strategy comparison (paired-difference t-tests over aligned OOS return series)
layers are implemented (Phases 1–24). Source ingestion
connectors remain planned; the engine operates over content-addressed corpora it is given.
