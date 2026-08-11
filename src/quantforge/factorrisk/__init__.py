"""Factor covariance & correlation estimation - the factor risk model (Phase 20).

The first member of a new **risk-modelling** capability class - a pure consumer strictly
above Phase 19, distinct from the Phase 17 single-subject attribution and the Phase 18
cross-sectional regression. It resolves an ordered set of *N* sealed
:class:`~quantforge.factorportfolio.result.FactorPortfolio` records, re-verifies each,
aligns their KNOWN ``(as_of, factor_return)`` series on a common complete-case time
axis, and estimates their second-moment structure under the pinned decimal context: the
per-factor means and population volatilities, the ``N x N`` population covariance
matrix,
and the companion correlation matrix. It re-resolves no data, introduces no new PIT
surface, adds no runtime dependency, and creates no new store; it consumes **no**
``BacktestResult`` and is not one (FR-5).

* :class:`~quantforge.factorrisk.spec.FactorRiskSpecification` - the declarative,
  content-addressed request: a name, an **ordered** tuple of 2..``N_MAX`` sealed
  factor-portfolio ids (order fixes the matrix row/column order), and an annualization
  convention.
* :class:`~quantforge.factorrisk.engine.FactorRiskEngine` - resolves, verifies (FR-1),
  enforces commensurability (one schedule + one producing engine version; FR-3),
  complete-case aligns the factor return series (FR-4), estimates the moments under the
  pinned decimal context, and seals a
  :class:`~quantforge.factorrisk.result.FactorRiskModel`, persisting it write-once to
  the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.factor_risk_engine`).
* :class:`~quantforge.factorrisk.result.FactorRiskModel` - the sealed, content-addressed
  record: the ordered factor references, the per-factor moments, the upper-triangle
  covariance and correlation matrices, a coverage summary, and the carried corpus pins.
  Satisfies the :class:`~quantforge.factors.store.ResearchRecord` Protocol and
  round-trips byte-identically. It is **ex-post, not PIT** (FR-2): not a ``Pit*`` type,
  no as-of
  accessor, and not a ``BacktestResult`` (FR-5).
* :class:`~quantforge.factorrisk.model.StatValue` - the UNDEFINED-preserving statistic
  cell: a KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.factorrisk.model.FactorRiskUndefinedReason` (a zero-variance
  factor's correlation), never a fabricated ``0`` / ``NaN`` / divide-by-zero (FR-4).

Every identity is content-addressed (:mod:`quantforge.factorrisk.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split
(:mod:`quantforge.factorrisk.errors`): a request / consistency defect raises; a
statistic genuinely undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.factorrisk.engine import FactorRiskEngine
from quantforge.factorrisk.errors import (
    FactorRiskConfigurationError,
    FactorRiskConsistencyError,
    FactorRiskError,
)
from quantforge.factorrisk.identity import (
    factor_risk_id,
    factor_risk_result_hash,
)
from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    CoverageSummary,
    FactorCoverage,
    FactorMoment,
    FactorRiskStatus,
    FactorRiskUndefinedReason,
    StatValue,
    factor_label,
)
from quantforge.factorrisk.result import (
    BOUNDARY_PIT,
    FACTORRISK_RESULT_FORMAT_VERSION,
    FactorRiskModel,
)
from quantforge.factorrisk.spec import (
    N_MAX,
    FactorRiskSpecification,
)
from quantforge.factorrisk.version import (
    FACTORRISK_ENGINE_VERSION,
    FACTORRISK_FORMULA_VERSION,
    FACTORRISK_SPEC_VERSION,
    FactorRiskEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "FACTORRISK_ENGINE_VERSION",
    "FACTORRISK_FORMULA_VERSION",
    "FACTORRISK_RESULT_FORMAT_VERSION",
    "FACTORRISK_SPEC_VERSION",
    "N_MAX",
    "CorrelationCell",
    "CovarianceCell",
    "CoverageSummary",
    "FactorCoverage",
    "FactorMoment",
    "FactorRiskConfigurationError",
    "FactorRiskConsistencyError",
    "FactorRiskEngine",
    "FactorRiskEngineVersion",
    "FactorRiskError",
    "FactorRiskModel",
    "FactorRiskSpecification",
    "FactorRiskStatus",
    "FactorRiskUndefinedReason",
    "StatValue",
    "default_decimal_context",
    "factor_label",
    "factor_risk_id",
    "factor_risk_result_hash",
]
