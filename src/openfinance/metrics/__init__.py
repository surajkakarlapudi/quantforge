"""Financial metrics & research layer (Phase 7) — see ``docs/metrics.md``.

Computes derived financial metrics (ratios and simple arithmetic combinations of
canonical facts) as a **deterministic, fail-closed, fully provenanced** function of
the Phase 5 point-in-time knowledge state. It never mutates a fact, never invents
data, and keeps PIT and REVISED impossible to confuse.

Curated public surface (§10). Internal modules (``evaluate``, ``resolve_input``,
``identity``, ``version``) stay private; author/inspect formulas through
:class:`FormulaRegistry` / :class:`FormulaDefinition`, and compute through
:class:`MetricEngine` (or the :class:`~openfinance.company.Company` façade).
"""

from __future__ import annotations

from openfinance.metrics.engine import MetricEngine
from openfinance.metrics.errors import (
    FormulaConfigurationError,
    MetricConsistencyError,
    MetricError,
)
from openfinance.metrics.formula import (
    Add,
    ConceptCandidate,
    Const,
    Div,
    FormulaDefinition,
    InputBinding,
    Mul,
    Operation,
    Ref,
    Sub,
)
from openfinance.metrics.model import (
    MetricPeriod,
    MetricProvenance,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from openfinance.metrics.registry import FormulaRegistry
from openfinance.metrics.resolve_input import MetricBoundary
from openfinance.metrics.units import UnitExpectation
from openfinance.metrics.version import MetricEngineVersion

__all__ = [
    "Add",
    "ConceptCandidate",
    "Const",
    "Div",
    "FormulaConfigurationError",
    "FormulaDefinition",
    "FormulaRegistry",
    "InputBinding",
    "MetricBoundary",
    "MetricConsistencyError",
    "MetricEngine",
    "MetricEngineVersion",
    "MetricError",
    "MetricPeriod",
    "MetricProvenance",
    "MetricStatus",
    "Mul",
    "Operation",
    "PitMetricValue",
    "Ref",
    "RevisedMetricValue",
    "Sub",
    "UndefinedReason",
    "UnitExpectation",
]
