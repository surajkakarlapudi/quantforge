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
| Next | Long/short factor-portfolio construction / richer execution & cost models |

## Status

QuantForge is an active research/infrastructure project.
Some components are provisional and explicitly versioned as such.
The project prioritizes correctness, reproducibility, and auditability
over breadth.
