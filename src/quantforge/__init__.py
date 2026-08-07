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
cross-sectional factor types (:class:`PitFactor` / :class:`RevisedFactor`) are
re-exported so the PIT-vs-revised distinction is visible at the import site; they
remain defined in the availability, metrics, and factors layers respectively.
:class:`FormulaRegistry` / :class:`FormulaDefinition` are exported so callers can
enumerate and inspect the available metrics without reaching into internals. The
factor layer's front door is :class:`FactorEngine` (evaluate one metric across a
universe, optionally under a :class:`Transform`).

The universe-management layer's :class:`Universe` (Phase 9.1) is re-exported as the
front door for assembling a deterministic, point-in-time collection of filers from
tickers/CIKs/names — ``Universe.from_companies(["AAPL", "MSFT", "NVDA"])`` — resolved
through the same company identity layer as :class:`Company`, so it introduces no new
identifier system.
"""

from __future__ import annotations

from quantforge.availability.resolve import PitValue, RevisedValue
from quantforge.company import Company
from quantforge.factors import (
    FactorEngine,
    PitFactor,
    ResearchResult,
    RevisedFactor,
    Transform,
)
from quantforge.identity.model import CompanyIdentity
from quantforge.metrics import (
    FormulaDefinition,
    FormulaRegistry,
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from quantforge.universe import Universe
from quantforge.workspace import Workspace

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
