"""OpenFinance: reproducible, point-in-time financial research infrastructure.

The public API is intentionally small. The front door is :class:`Company`::

    from openfinance import Company

    apple = Company.resolve("AAPL")
    for filing in apple.filings():
        print(filing.form, filing.filing_date)
    facts = apple.facts()

``Company`` is a thin façade over the deterministic, provenance-first layers
(acquisition → registry → raw XBRL → canonical facts → point-in-time → metrics →
cross-sectional factors); it adds no data model of its own. The point-in-time
result types (:class:`PitValue` / :class:`RevisedValue`), the derived-metric result
types (:class:`PitMetricValue` / :class:`RevisedMetricValue`), and the
cross-sectional factor types (:class:`PitFactor` / :class:`RevisedFactor`) are
re-exported so the PIT-vs-revised distinction is visible at the import site; they
remain defined in the availability, metrics, and factors layers respectively.
:class:`FormulaRegistry` / :class:`FormulaDefinition` are exported so callers can
enumerate and inspect the available metrics without reaching into internals. The
factor layer's front door is :class:`FactorEngine` (evaluate one metric across a
:class:`Universe`, optionally under a :class:`Transform`).
"""

from __future__ import annotations

from openfinance.availability.resolve import PitValue, RevisedValue
from openfinance.company import Company
from openfinance.factors import (
    FactorEngine,
    PitFactor,
    ResearchResult,
    RevisedFactor,
    Transform,
    Universe,
)
from openfinance.identity.model import CompanyIdentity
from openfinance.metrics import (
    FormulaDefinition,
    FormulaRegistry,
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from openfinance.workspace import Workspace

__all__ = [
    "Company",
    "CompanyIdentity",
    "FactorEngine",
    "FormulaDefinition",
    "FormulaRegistry",
    "MetricPeriod",
    "MetricStatus",
    "PitFactor",
    "PitMetricValue",
    "PitValue",
    "ResearchResult",
    "RevisedFactor",
    "RevisedMetricValue",
    "RevisedValue",
    "Transform",
    "UndefinedReason",
    "Universe",
    "Workspace",
    "__version__",
]

__version__ = "0.0.0"
