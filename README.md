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
| Next | Factor portfolio optimization / risk-based weighting / richer execution & cost models |

## Status

QuantForge is an active research/infrastructure project.
Some components are provisional and explicitly versioned as such.
The project prioritizes correctness, reproducibility, and auditability
over breadth.
