# QuantForge

> A deterministic, point-in-time financial research engine built from SEC filings.

QuantForge is an open-source quantitative finance infrastructure project for
researchers, developers, and students who need reproducible financial data
without survivorship bias, look-ahead bias, or opaque data transformations.

## What QuantForge Does

QuantForge turns SEC filings into a reproducible research pipeline:

SEC filings
    ↓
Canonical financial facts
    ↓
Point-in-time availability
    ↓
Financial statements
    ↓
Financial metrics
    ↓
Cross-sectional factors
    ↓
Universe research
    ↓
Fundamental panels
    ↓
Point-in-time backtesting
    ↓
Quantitative research

### Core capabilities

- SEC filing acquisition and provenance
- XBRL fact extraction and canonicalization
- Point-in-time financial data
- PIT vs. revised data separation
- Financial statement assembly
- Deterministic financial metrics
- Cross-sectional factor research
- Universe research (deterministic membership, construction, inspection, comparison, export)
- Point-in-time fundamental panels (period-series, vintage, cross-sectional matrix)
- Point-in-time market data (unadjusted daily OHLCV + first-class corporate actions, PIT-gated adjusted views)
- Point-in-time backtesting (declarative content-addressed strategies, pinned dual corpora, engine-owned execution, corporate-action accounting, reproducible results)
- Comparative research (declarative experiment sweeps + deterministic backtest comparison)
- Research reporting & explainability (content-addressed, reference-only research reports with a deterministic Markdown renderer)
- Performance & benchmark-relative analytics (downside/drawdown risk, historical VaR/CVaR, distribution moments, and — against a benchmark that is itself a sealed backtest — tracking error, information ratio, capture, and single-factor OLS alpha/beta, sealed as a content-addressed record)
- Multi-factor performance attribution (exact-`Decimal` OLS of a subject backtest's excess return on *K* factor backtests' excess returns: per-factor betas + alpha, R² / adjusted R², classical coefficient std errors / t-statistics, and a sample mean-excess decomposition; ex-post — not a PIT value; sealed as a content-addressed record)
- Cross-sectional factor-return regression (Fama–MacBeth premia: per evaluation date, one exact-`Decimal` cross-sectional OLS of members' realized forward returns on *K* PIT-eligible signals, then time-series aggregation of the per-date coefficients into factor premia with plain Fama–MacBeth standard errors and t-statistics; a per-date coefficient panel + coverage summary; ex-post — not a PIT value; sealed as a content-addressed record)
- Characteristic-sorted long/short factor-portfolio construction (per rebalance date, sort a Phase 9 universe into `Q` quantiles by a PIT-eligible-at-`T` signal, form a long top-bucket and short bottom-bucket leg, and realize each leg's forward return; the per-period factor return is the long-minus-short spread, chained into a factor return series with per-period leg holdings, coverage, and a performance summary — cumulative / mean / population volatility / annualized Sharpe / t-statistic / hit rate; ex-post — not a PIT value; sealed as a content-addressed record)
- Factor risk model / covariance & correlation estimation (resolve an ordered set of *N* sealed factor portfolios, enforce one shared schedule + producing-engine version, complete-case align their KNOWN return series, and estimate the second-moment structure under a pinned `Decimal` context: the per-factor mean + population volatility vectors, the `N x N` population covariance matrix, and the companion correlation matrix — per-period and annualized, stored as the upper triangle; a zero-variance factor's correlation is a first-class UNDEFINED cell, never a divide-by-zero; each factor's `result_hash` folded for transitive pinning, corpus `pin_mismatch` surfaced; ex-post — not a PIT value and not a `BacktestResult`; sealed as a content-addressed record)
- Factor-risk-aware portfolio optimization (resolve exactly one sealed factor risk model, reconstruct its `N x N` factor covariance, and solve the fully-invested global minimum-variance portfolio `min wᵀΣw s.t. 1ᵀw = 1` in closed form under a pinned `Decimal` context via the exact-`Decimal` LDLᵀ solver — per-factor GMV weights (a weight may be negative), achieved per-period variance and volatility; a non-positive-definite covariance is a first-class UNDEFINED `SINGULAR_COVARIANCE` result, never a divide-by-zero or a repaired matrix; the risk model's `result_hash` folded for transitive pinning; ex-post — not a PIT value and not a `BacktestResult`; sealed as a content-addressed record)
- Walk-forward out-of-sample evaluation (resolve one sealed portfolio-optimization recipe and, transitively, its factor risk model and factor portfolios; partition the common return axis into ordered `train → test` windows with a strict no-look-ahead split, and per window re-estimate the covariance, re-solve the fully-invested GMV weights, and realize them held constant against the strictly-subsequent test returns — sealing per-window and aggregate predicted-vs-realized variance plus a compounded OOS performance summary; a non-positive-definite training covariance is a first-class UNDEFINED `SINGULAR_TRAINING_COVARIANCE` window, never repaired; composes three pinned pure methods with no new numerical formula; ex-post — not a PIT value and not a `BacktestResult`; sealed as a content-addressed record)
- Out-of-sample research-campaign evaluation with selection-bias correction (treat an ordered set of *N* sealed walk-forward evaluations as the trials of one research campaign; re-derive each trial's per-period OOS Sharpe / skew / non-excess kurtosis and its Probabilistic Sharpe Ratio, then across trials take the honest search size *N* = all submitted trials, the population variance of the valid trials' Sharpe ratios, the expected-maximum Sharpe under the null, and the headline Deflated Sharpe Ratio of the selected max-Sharpe trial — via a deterministic exact-`Decimal` standard-normal `Φ` / `Z⁻¹` primitive, no float or RNG; commensurability enforced, each trial's `result_hash` folded for transitive pinning; degenerate trials/campaigns are first-class UNDEFINED cells, never fabricated; ex-post — not a PIT value and not a `BacktestResult`; sealed as a content-addressed record)
- Full fact-to-source provenance
- Content-addressed versioning
- Offline/reproducible research
## Example

from quantforge import Company

apple = Company.resolve("AAPL")

filings = apple.filings()
facts = apple.facts()

# A universe: a deterministic, point-in-time collection of filers
from quantforge import Universe

universe = Universe.from_companies(["AAPL", "MSFT", "NVDA"])
universe.describe()          # a deterministic, serializable UniverseSummary
universe.compare(other)      # a UniverseComparison, diffed by canonical company_id
universe.to_records()        # dependency-free tabular export

# A fundamental panel: one metric over an explicit, content-addressed time axis
from quantforge.panel import PeriodAxis
from quantforge.xbrl.contexts import PeriodType

axis = PeriodAxis.annual("2018-12-31", "2023-12-31", period_type=PeriodType.INSTANT)
panel = apple.panel_as_of("current_ratio", axis, as_of)  # a PitPanel, one cell/period

# A research report: a content-addressed, reference-only manifest over a sealed
# backtest or experiment, rendered to deterministic Markdown
from quantforge import ReportSpecification
from quantforge.report import render_markdown

spec = ReportSpecification(name="momentum-study", scope="experiment", subject_id=experiment_id)
report = workspace.report_engine.build(spec)   # a sealed, write-once ResearchReport
markdown = render_markdown(report, workspace.research_result_store)

# Performance & benchmark-relative analytics: risk and relative statistics over a
# sealed backtest (and, optionally, a benchmark that is itself a sealed backtest)
from quantforge import AnalyticsSpecification

spec = AnalyticsSpecification(
    name="vs-equal-weight",
    subject_id=strategy_backtest_id,
    benchmark_id=equal_weight_backtest_id,   # a sealed BacktestResult, not external data
    var_confidences=("0.95", "0.99"),
    periods_per_year="12",
)
analytics = workspace.analytics_engine.compute(spec)   # a sealed, write-once PerformanceAnalytics
## Design Principles

QuantForge is built around several principles:

- No look-ahead
- No fabricated financial data
- No silent data loss
- Explicit PIT/REVISED separation
- Deterministic computation
- Full provenance
- Versioned transformations
- Fail-closed behavior
- Read-only composition of lower layers
## Project Status

| Version | Capability |
|---|---|
| v0.1.0 | SEC acquisition, XBRL, canonical facts, PIT availability |
| v0.2.0 | Financial statements & public Company API |
| v0.3.0 | Financial metrics |
| v0.4.0 | Cross-sectional factors + QuantForge rebrand |
| v0.5.0 | Universe research layer (management, construction, inspection, comparison, export) |
| v0.6.0 | Point-in-time fundamental panel (period-series, vintage, cross-sectional matrix) |
| v0.7.0 | Point-in-time market data layer (unadjusted OHLCV, first-class corporate actions, PIT-gated adjusted views, `PitPrice` / `RevisedPrice`) |
| v0.8.0 | Deterministic point-in-time backtesting engine (declarative content-addressed strategies, pinned dual corpora, engine-owned execution, corporate-action accounting, fail-closed simulation, reproducible `backtest_id`) |
| v0.9.0 | Comparative research (declarative content-addressed experiment sweeps over a closed parameter vocabulary + deterministic backtest comparison, reusing sealed Phase 12 results) |
| v0.10.0 | Research reporting & explainability (content-addressed, reference-only `ResearchReport` over sealed backtests/experiments + a single deterministic Markdown renderer, write-once to the existing sidecar) |
| v0.11.0 | Performance & benchmark-relative analytics (pure consumer of sealed backtests: downside/drawdown risk, historical nearest-rank VaR/CVaR, distribution moments, tracking error, information ratio, capture, single-factor OLS alpha/beta; UNDEFINED-preserving; sealed as a content-addressed `PerformanceAnalytics` record) |
| v0.12.0 | Cross-sectional signal diagnostics (pure consumer above universe/panel/price layers, diagnostic sibling of the backtester: per-date Spearman + Pearson IC of an as-of-`T` signal against realized forward returns, quantile-bucket profiles + top-minus-bottom spread, IC summary; both corpora pinned & re-verified, fail-closed pairing with auditable coverage, UNDEFINED-preserving; sealed as a content-addressed `SignalDiagnostics` record) |
| v0.14.0 | Multi-factor performance attribution (pure consumer of sealed backtests, sibling of the analytics layer: exact-`Decimal` OLS of a subject's excess return on *K* factor backtests' excess returns via LDLᵀ with an exact zero-pivot test; per-factor betas + alpha, R² / adjusted R² / residual std error, classical coefficient std errors / t-statistics, sample mean-excess decomposition; commensurability + drift verified, corpus pins surfaced, UNDEFINED-preserving; ex-post — not a PIT value; sealed as a content-addressed `FactorAttribution` record) |
| v0.15.0 | Cross-sectional factor-return regression (Fama–MacBeth premia; pure consumer above universe/panel/price layers, multivariate cross-sectional sibling of the signal-diagnostics layer: per evaluation date, one exact-`Decimal` cross-sectional OLS of members' realized forward returns on *K* raw PIT-eligible-at-`T` signals via the shared LDLᵀ solver with an exact zero-pivot test, then time-series aggregation of the per-date coefficients into factor premia with plain population Fama–MacBeth standard errors + t-statistics; a per-date coefficient panel + auditable coverage; both corpora pinned & re-verified, fail-closed pairing, UNDEFINED-preserving; ex-post — not a PIT value; sealed as a content-addressed `CrossSectionalRegression` record) |
| v0.16.0 | Characteristic-sorted long/short factor-portfolio construction (pure consumer above universe/panel/price layers, the first member of a new portfolio-construction capability class, a constructive sibling of the signal-diagnostics layer: per rebalance date `T`, sort the universe into `Q` quantiles by a PIT-eligible-at-`T` signal via the Phase 16 `quantile_buckets` rule, form the long top bucket + short bottom bucket, equal-weight each leg, and realize each leg's forward return over `[T, T+h]` trading days; the per-period factor return is the long-minus-short spread `f_T = mean(long) - mean(short)` (dollar-neutral, gross), chained into a factor return series with per-period leg holdings, coverage, and a summary — compounded cumulative, mean, population volatility, annualized Sharpe, t-statistic, hit rate; both corpora pinned & re-verified, fail-closed pairing, UNDEFINED-preserving; ex-post — not a PIT value and not a `BacktestResult`; sealed as a content-addressed `FactorPortfolio` record) |
| v0.17.0 | Factor risk model — factor covariance & correlation estimation (pure consumer strictly above Phase 19, the first member of a new risk-modelling capability class, the sibling of the Phase 15/17 backtest-consumer layers: a declarative content-addressed `FactorRiskSpecification` names an **ordered** set of 2..`N_MAX = 16` sealed `FactorPortfolio` ids + an annualization convention; `FactorRiskEngine.estimate` resolves and re-verifies each factor from the shared sidecar (folding each factor's `result_hash` for transitive pinning, FR-1), enforces commensurability — one shared `schedule_id` **and** one `factor_portfolio_engine_version_id`, else fail closed (FR-3; corpus `pin_mismatch` surfaced, never reconciled) — complete-case aligns their KNOWN `(as_of, factor_return)` series on the common date axis (FR-4; fewer than 2 common dates fails closed), and estimates the second-moment structure under the pinned `Decimal` context: the per-factor mean + **population** volatility vectors, the `N x N` population covariance matrix `(1/M)Σ(f_i-mean_i)(f_j-mean_j)`, and the companion correlation matrix `cov/(vol_i·vol_j)` — per-period and annualized (`vol·√ppy`, `cov·ppy`), stored as the **upper triangle** only. A zero-variance factor's correlation is a first-class `UNDEFINED` `ZERO_VARIANCE` cell (its `0/0` diagonal included), never a divide-by-zero; means/volatilities/covariances stay KNOWN. The output is **ex-post — not a PIT value** (FR-2; no `Pit*` type, no as-of accessor) and **not a `BacktestResult`** (FR-5). The sealed `FactorRiskModel` is a `ResearchRecord` persisted write-once to the same Phase 8 sidecar (no new store), byte-identically round-tripping; `factor_risk_id` folds the engine + formula + spec version, the declared request, the ordered factor `result_hash`es, and the `result_hash` over the computed answer (coverage is audit metadata and is not folded). All arithmetic runs under the pinned context (prec 34, `ROUND_HALF_EVEN`); no float, wall-clock, or RNG enters any value or id. Adds no runtime dependency, no database, no new data source, and no new PIT resolution) |
| v0.18.0 | Factor-risk-aware portfolio optimization — fully-invested global minimum-variance (pure consumer strictly above Phase 20, the first optimization layer and first member of a new optimization capability class: a declarative content-addressed `PortfolioOptimizationSpecification` names exactly one sealed `FactorRiskModel` + the objective `minimum_variance` + the constraint `fully_invested`; `PortfolioOptimizationEngine.optimize` resolves and re-verifies the referenced model from the shared sidecar (folding its `result_hash` for transitive pinning, PO-1), enforces the inherited factor-count bound `2..N_MAX = 16`, reconstructs the full symmetric `N x N` factor covariance `Σ` fail-closed from the sealed upper-triangle cells (single source, consumed as-is — never recomputed/shrunk/regularized, PO-3), and solves the GMV problem `min wᵀΣw s.t. 1ᵀw = 1` in closed form under the pinned `Decimal` context via the existing exact-`Decimal` LDLᵀ solver (`w = Σ⁻¹1 / 1ᵀΣ⁻¹1`): per-factor GMV weights in factor order (a weight may be negative — an honest long/short across factors), achieved per-period variance `wᵀΣw` and volatility. A non-positive-definite `Σ` (the exact LDLᵀ zero-pivot test) is a first-class `UNDEFINED` `SINGULAR_COVARIANCE` result — every weight/variance/volatility UNDEFINED together — never a divide-by-zero, pseudo-inverse, dropped factor, or repaired matrix (PO-4). The output is **ex-post — not a PIT value** (PO-2; no `Pit*` type, no as-of accessor) and **not a `BacktestResult`** (PO-5; no execution/holdings/cost). The sealed `PortfolioOptimization` is a `ResearchRecord` persisted write-once to the same Phase 8 sidecar (no new store), byte-identically round-tripping; `optimization_id` folds the engine + solve + spec version, the declared request + canonical constraint spec, the covariance basis, the referenced `factor_risk_id` + its `result_hash`, and the `result_hash` over the computed answer. All arithmetic runs under the pinned context (prec 34, `ROUND_HALF_EVEN`); no float, iteration, wall-clock, or RNG enters any value or id, and `_linalg` is unchanged. Adds no runtime dependency, no database, no new data source, and no new PIT resolution) |
| v0.19.0 | Walk-forward out-of-sample evaluation (the first genuine consumer of the Phase 21 optimizer and the project's first *train-before-test* temporal discipline: a declarative content-addressed `WalkForwardEvaluationSpecification` names exactly one sealed `PortfolioOptimization` recipe + a `TrainingPolicy` (expanding or rolling; `min_train_periods`, `test_periods`, `rolling_length`); `WalkForwardEvaluationEngine.evaluate` resolves and re-verifies the recipe from the shared sidecar (`status = OPTIMAL`, objective `minimum_variance`, constraint `fully_invested`) and, transitively, its `FactorRiskModel` (with a `result_hash` pin match) and every `FactorPortfolio` (WF-1), inherits one shared `risk_free_per_period`, complete-case aligns the factors' KNOWN `(as_of, factor_return)` series on the common date axis (WF-6), and partitions that axis into ordered `train → test` windows with a strict no-look-ahead split `train_end == test_start` (WF-2). Per window it **re-estimates** the covariance (Phase 20 method), **re-solves** the fully-invested GMV weights (Phase 21 method), and **realizes** those weights held constant against the strictly-subsequent test returns `r_t = Σ_i w_{k,i}·f_{i,t}`; a non-positive-definite training covariance is a first-class `UNDEFINED` `SINGULAR_TRAINING_COVARIANCE` window, never repaired (WF-4). It chains the OOS returns, summarizes them (Phase 19 method: compounded cumulative, mean, population volatility, annualized Sharpe, t-statistic, hit rate), and seals the per-window and aggregate **predicted-vs-realized** variance — the non-tautological comparison the phase exists to produce. Fewer than 2 REALIZED windows fails closed. It composes three pinned pure methods (Phase 19/20/21) — their versions folded into engine identity (WF-5), no new numerical formula — introduces no new estimator, no expected-return / `μ`, and no `_linalg` change. The output is **ex-post — not a PIT value and not a `BacktestResult`** (WF-3). The sealed `WalkForwardEvaluation` is a `ResearchRecord` persisted write-once to the same Phase 8 sidecar (no new store), byte-identically round-tripping; `walk_forward_id` folds the engine + composed-method + decimal-context version, the declared request + canonical training policy, the inherited `schedule_id`, the referenced `optimization_id` + its `result_hash` (transitive pin), and the `result_hash` over the computed walk. All arithmetic runs under the pinned context (prec 34, `ROUND_HALF_EVEN`); no float, iteration, wall-clock, or RNG enters any value or id. Adds no runtime dependency, no database, no new data source, and no new PIT resolution) |
| v0.20.0 | Out-of-sample research-campaign evaluation with selection-bias correction (the first genuine consumer of the Phase 22 terminal-leaf `WalkForwardEvaluation` and the project's first selection-bias / meta-analysis layer: a declarative content-addressed `ResearchCampaignSpecification` names an **ordered** tuple of `2..N_MAX = 64` sealed `WalkForwardEvaluation` ids — the *trials* of one research campaign — plus a per-period benchmark Sharpe `SR*` (default `"0"`); `ResearchCampaignEngine.evaluate` resolves and re-verifies each trial from the shared sidecar (id match, roll-up `status = REALIZED`, folding each `result_hash` for transitive pinning, CE-1) and enforces commensurability — one shared `schedule_id` **and** one `factor_portfolio_engine_version_id`, else fail closed (CE-3; corpus `pin_mismatch` surfaced, never reconciled). Per trial it re-derives from the sealed `oos_returns` (with the inherited `risk_free_per_period`, never the sealed annualized Sharpe) the per-period excess-return Sharpe, skew, and **non-excess** kurtosis and the Probabilistic Sharpe Ratio `PSR(SR*) = Φ((SR−SR*)·√(n−1)/√(1−γ₃·SR+((γ₄−1)/4)·SR²))`; across trials it takes the search size `N` as the count of **all** submitted trials — valid and UNDEFINED (CE-2) — the **population** variance `V` of the valid trials' Sharpe ratios, the expected-maximum Sharpe under the null `SR₀ = √V·[(1−γ)·Z⁻¹(1−1/N)+γ·Z⁻¹(1−1/(N·e))]` (γ = Euler–Mascheroni), and the headline **Deflated Sharpe Ratio** `DSR = PSR(SR₀)` of the selected (max-Sharpe, ties→lowest index) trial. It introduces exactly one new numerical primitive — a deterministic exact-`Decimal` standard-normal `Φ` (an all-positive-term `erf` series) / `Z⁻¹` (a fixed-iteration bisection), phase-local, **not** an `_linalg` change (CE-5) — and composes a self-contained exact-`Decimal` moment computation. Every undefinable statistic (a trial with fewer than two OOS periods, zero OOS variance, or a degenerate PSR estimator; a campaign with fewer than `MIN_VALID_TRIALS = 2` valid trials) is a first-class UNDEFINED cell with its reason, excluded from selection and `V`, never a fabricated `0` or divide-by-zero (CE-4); the record still seals. The output is **ex-post — not a PIT value and not a `BacktestResult`** (CE-6). The sealed `ResearchCampaignEvaluation` is a `ResearchRecord` persisted write-once to the same Phase 8 sidecar (no new store), byte-identically round-tripping; `campaign_id` folds the engine + method + normal-primitive + decimal-context version, the declared request (name, spec version, the ordered trial ids, the canonical benchmark Sharpe), the ordered trial `result_hash`es, and the `result_hash` over the computed answer. All arithmetic runs under the pinned context (prec 34, `ROUND_HALF_EVEN`); no float, wall-clock, or RNG enters any value or id, and `_linalg` is unchanged. Adds no runtime dependency, no database, no new data source, and no new PIT resolution) |
| Next | Mean-variance / max-Sharpe (needs a PIT-safe expected-return artifact) / constrained (long-only, box) optimization / richer execution & cost models |

## Status

QuantForge is an active research/infrastructure project.
Some components are provisional and explicitly versioned as such.
The project prioritizes correctness, reproducibility, and auditability
over breadth.
