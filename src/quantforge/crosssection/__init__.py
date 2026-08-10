"""Fama-MacBeth cross-sectional factor-return regression (Phase 18).

The layer strictly above Phases 9/10/11 - the multivariate cross-sectional sibling of
the Phase 16 univariate IC diagnostics: at each scheduled date ``T`` it resolves the
survivorship-free universe PIT as-of ``T``, reads the ``K``-signal cross-section via
``panel_across(as_of=T)``, pairs each member with a realized *forward* return over
``[T, T+h]`` trading days, runs one exact-``Decimal`` ordinary-least-squares
cross-section across the members, then aggregates the per-date coefficients over time
into factor **premia** (time-series mean, plain population standard error, t-statistic).
It re-resolves no data, introduces no new PIT surface, adds no runtime dependency, and
creates no new store; it consumes **no** ``BacktestResult``.

* :class:`~quantforge.crosssection.spec.CrossSectionalRegressionSpecification` - the
  declarative, content-addressed request: a name, an **ordered** tuple of
  :class:`~quantforge.crosssection.spec.FactorSpec` (a ``metric_key`` + its explicit
  :class:`~quantforge.metrics.model.MetricPeriod`), a Phase 9 universe, a Phase 12
  evaluation schedule, a forward-return horizon, whether to include an intercept, and
  the two corpus pins.
* :class:`~quantforge.crosssection.engine.CrossSectionalRegressionEngine` - resolves,
  verifies both corpus pins (XS-1, fail closed), regresses per date under the pinned
  decimal context, aggregates Fama-MacBeth premia, and seals a
  :class:`~quantforge.crosssection.result.CrossSectionalRegression`, persisting it
  write-once to the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.crosssection_engine`).
* :class:`~quantforge.crosssection.result.CrossSectionalRegression` - the sealed,
  content-addressed record: the per-date coefficient panel, the aggregated premia, a
  coverage summary, and the carried corpus pins. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (XS-2): not a ``Pit*`` type, no as-of
  accessor.
* :class:`~quantforge.crosssection.model.StatValue` - the UNDEFINED-preserving
  statistic cell: a KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.crosssection.model.CrossSectionUndefinedReason`, never a
  fabricated ``0`` / ``NaN`` / divide-by-zero, never a silently dropped member or factor
  (XS-4).

Every identity is content-addressed (:mod:`quantforge.crosssection.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split (:mod:`quantforge.crosssection.errors`): a request / consistency defect raises; a
statistic genuinely undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.crosssection.engine import CrossSectionalRegressionEngine
from quantforge.crosssection.errors import (
    CrossSectionConfigurationError,
    CrossSectionConsistencyError,
    CrossSectionError,
)
from quantforge.crosssection.identity import (
    crosssection_id,
    crosssection_result_hash,
)
from quantforge.crosssection.model import (
    INTERCEPT_LABEL,
    CoverageSummary,
    CrossSectionStatus,
    CrossSectionUndefinedReason,
    DateCoverage,
    PerDateCoefficients,
    PremiumEstimate,
    StatValue,
    factor_label,
)
from quantforge.crosssection.result import (
    BOUNDARY_PIT,
    CROSSSECTION_RESULT_FORMAT_VERSION,
    CrossSectionalRegression,
)
from quantforge.crosssection.spec import (
    CROSSSECTION_SPEC_VERSION,
    K_MAX,
    CrossSectionalRegressionSpecification,
    FactorSpec,
)
from quantforge.crosssection.version import (
    CROSSSECTION_ENGINE_VERSION,
    CROSSSECTION_FORMULA_VERSION,
    CrossSectionEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "CROSSSECTION_ENGINE_VERSION",
    "CROSSSECTION_FORMULA_VERSION",
    "CROSSSECTION_RESULT_FORMAT_VERSION",
    "CROSSSECTION_SPEC_VERSION",
    "INTERCEPT_LABEL",
    "K_MAX",
    "CoverageSummary",
    "CrossSectionConfigurationError",
    "CrossSectionConsistencyError",
    "CrossSectionEngineVersion",
    "CrossSectionError",
    "CrossSectionStatus",
    "CrossSectionUndefinedReason",
    "CrossSectionalRegression",
    "CrossSectionalRegressionEngine",
    "CrossSectionalRegressionSpecification",
    "DateCoverage",
    "FactorSpec",
    "PerDateCoefficients",
    "PremiumEstimate",
    "StatValue",
    "crosssection_id",
    "crosssection_result_hash",
    "default_decimal_context",
    "factor_label",
]
