"""Financial metrics & research layer (Phase 7) — see ``docs/metrics.md``.

Computes derived financial metrics (ratios and simple arithmetic combinations of
canonical facts) as a **deterministic, fail-closed, fully provenanced** function of
the Phase 5 point-in-time knowledge state. It never mutates a fact, never invents
data, and keeps PIT and REVISED impossible to confuse.

Curated public surface (§10). Internal modules (``evaluate``, ``resolve_input``,
``identity``, ``version``) stay private; author/inspect formulas through
:class:`FormulaRegistry` / :class:`FormulaDefinition`, and compute through
:class:`MetricEngine` (or the :class:`~quantforge.company.Company` façade).
"""

from __future__ import annotations

from quantforge.metrics.engine import MetricEngine
from quantforge.metrics.errors import (
    FormulaConfigurationError,
    MetricConsistencyError,
    MetricError,
)
from quantforge.metrics.formula import (
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
from quantforge.metrics.model import (
    MetricPeriod,
    MetricProvenance,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
    UndefinedReason,
)
from quantforge.metrics.registry import FormulaRegistry
from quantforge.metrics.resolve_input import MetricBoundary
from quantforge.metrics.units import UnitExpectation
from quantforge.metrics.version import MetricEngineVersion

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
