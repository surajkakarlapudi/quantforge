"""QuantForge: reproducible, point-in-time financial research infrastructure.

The public API is intentionally small. The front door is :class:`Company`::

    from quantforge import Company

    apple = Company.resolve("AAPL")
    for filing in apple.filings():
        print(filing.form, filing.filing_date)
    facts = apple.facts()

``Company`` is a thin façade over the deterministic, provenance-first layers
(acquisition → registry → raw XBRL → canonical facts → point-in-time → metrics →
cross-sectional factors); it adds no data model of its own. The point-in-time
result types (:class:`PitValue` / :class:`RevisedValue`), the derived-metric result
types (:class:`PitMetricValue` / :class:`RevisedMetricValue`), and the
cross-sectional factor types (:class:`PitFactor` / :class:`RevisedFactor`), and the
fundamental-panel result types (:class:`PitPanel` / :class:`RevisedPanel`) are
re-exported so the PIT-vs-revised distinction is visible at the import site; they
remain defined in the availability, metrics, factors, and panel layers respectively.
The Phase 10 panel front door is :class:`~quantforge.panel.PanelEngine` (evaluate one
metric over a :class:`~quantforge.panel.PeriodAxis`), reached via
``Workspace.panel_engine`` or the thin per-filer :meth:`Company.panel_as_of`.
:class:`FormulaRegistry` / :class:`FormulaDefinition` are exported so callers can
enumerate and inspect the available metrics without reaching into internals. The
factor layer's front door is :class:`FactorEngine` (evaluate one metric across a
universe, optionally under a :class:`Transform`).

The Phase 9 Universe Research Layer is re-exported as its front doors.
:class:`Universe` assembles a deterministic, point-in-time collection of filers from
tickers/CIKs/names —
``Universe.from_companies(["AAPL", "MSFT", "NVDA"])`` — resolved through the same
company identity layer as :class:`Company`, so it introduces no new identifier system.
:class:`UniverseSpecification` (the declarative, content-addressed request) and
:class:`UniverseBuilder` (the fail-closed engine that evaluates it at a PIT/REVISED
boundary into a :class:`Universe` plus a reproducible provenance record) construct a
universe from ordered selection rules. A universe then answers researcher-facing
questions on the same object — ``universe.describe()`` and ``universe.compare(other)``
return the serializable :class:`UniverseSummary` / :class:`UniverseComparison` result
types (also re-exported here) — with membership always keyed by the canonical
``company_id`` and the PIT/REVISED distinction preserved, never conflated.
"""

from __future__ import annotations

from quantforge.analytics import (
    AnalyticsSpecification,
    PerformanceAnalytics,
)
from quantforge.attribution import (
    AttributionSpecification,
    FactorAttribution,
)
from quantforge.availability.resolve import PitValue, RevisedValue
from quantforge.backtest import (
    AccountingPolicy,
    BacktestResult,
    BacktestSpecification,
    CostModel,
    RebalanceSchedule,
    StrategySpecification,
    TargetWeights,
)
from quantforge.calibration import (
    RiskForecastCalibration,
    RiskForecastCalibrationSpecification,
)
from quantforge.campaign import (
    ResearchCampaignEvaluation,
    ResearchCampaignSpecification,
)
from quantforge.company import Company
from quantforge.comparison import (
    StrategyComparison,
    StrategyComparisonSpecification,
)
from quantforge.crosssection import (
    CrossSectionalRegression,
    CrossSectionalRegressionSpecification,
    FactorSpec,
)
from quantforge.diagnostics import (
    SignalDiagnostics,
    SignalDiagnosticsSpecification,
)
from quantforge.experiment import (
    BacktestComparison,
    ExperimentResult,
    ExperimentSpecification,
    SweepAxis,
)
from quantforge.factorportfolio import (
    FactorPortfolio,
    FactorPortfolioSpecification,
)
from quantforge.factorrisk import (
    FactorRiskModel,
    FactorRiskSpecification,
)
from quantforge.factors import (
    FactorEngine,
    PitFactor,
    ResearchResult,
    RevisedFactor,
    Transform,
)
from quantforge.identity.model import CompanyIdentity
from quantforge.market import PitPrice, RevisedPrice
from quantforge.metrics import (
    FormulaDefinition,
    FormulaRegistry,
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from quantforge.multiplicity import (
    MultipleComparisonCorrection,
    MultipleComparisonSpecification,
)
from quantforge.optimization import (
    PortfolioOptimization,
    PortfolioOptimizationSpecification,
)
from quantforge.panel import PitPanel, RevisedPanel
from quantforge.report import (
    ReportReference,
    ReportSpecification,
    ResearchReport,
)
from quantforge.universe import (
    CompanyMetricFilter,
    ExplicitCompanyFilter,
    SectorFilter,
    Universe,
    UniverseBuilder,
    UniverseComparison,
    UniverseSpecification,
    UniverseSummary,
)
from quantforge.walkforward import (
    WalkForwardEvaluation,
    WalkForwardEvaluationSpecification,
)
from quantforge.workspace import Workspace

__all__ = [
    "AccountingPolicy",
    "AnalyticsSpecification",
    "AttributionSpecification",
    "BacktestComparison",
    "BacktestResult",
    "BacktestSpecification",
    "Company",
    "CompanyIdentity",
    "CompanyMetricFilter",
    "CostModel",
    "CrossSectionalRegression",
    "CrossSectionalRegressionSpecification",
    "ExperimentResult",
    "ExperimentSpecification",
    "ExplicitCompanyFilter",
    "FactorAttribution",
    "FactorEngine",
    "FactorPortfolio",
    "FactorPortfolioSpecification",
    "FactorRiskModel",
    "FactorRiskSpecification",
    "FactorSpec",
    "FormulaDefinition",
    "FormulaRegistry",
    "MetricPeriod",
    "MetricStatus",
    "MultipleComparisonCorrection",
    "MultipleComparisonSpecification",
    "PerformanceAnalytics",
    "PitFactor",
    "PitMetricValue",
    "PitPanel",
    "PitPrice",
    "PitValue",
    "PortfolioOptimization",
    "PortfolioOptimizationSpecification",
    "RebalanceSchedule",
    "ReportReference",
    "ReportSpecification",
    "ResearchCampaignEvaluation",
    "ResearchCampaignSpecification",
    "ResearchReport",
    "ResearchResult",
    "RevisedFactor",
    "RevisedMetricValue",
    "RevisedPanel",
    "RevisedPrice",
    "RevisedValue",
    "RiskForecastCalibration",
    "RiskForecastCalibrationSpecification",
    "SectorFilter",
    "SignalDiagnostics",
    "SignalDiagnosticsSpecification",
    "StrategyComparison",
    "StrategyComparisonSpecification",
    "StrategySpecification",
    "SweepAxis",
    "TargetWeights",
    "Transform",
    "UndefinedReason",
    "Universe",
    "UniverseBuilder",
    "UniverseComparison",
    "UniverseSpecification",
    "UniverseSummary",
    "WalkForwardEvaluation",
    "WalkForwardEvaluationSpecification",
    "Workspace",
    "__version__",
]

__version__ = "0.0.0"
