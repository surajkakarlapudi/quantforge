"""Global minimum-variance portfolio optimization - the optimization layer (Phase 21).

The first member of a new **portfolio-construction** capability class - a pure consumer
strictly above Phase 20, distinct from the Phase 20 risk model it consumes. It resolves
exactly one sealed :class:`~quantforge.factorrisk.result.FactorRiskModel`, re-verifies
it, reconstructs the full symmetric ``N x N`` factor covariance matrix from its sealed
upper-triangle cells, and solves the fully-invested global minimum-variance (GMV)
factor-weight problem over that matrix under the pinned decimal context: the closed
form ``w = Σ⁻¹1 / (1ᵀΣ⁻¹1)`` via the shared exact-``Decimal`` LDLᵀ factorization, the
achieved per-period portfolio variance ``wᵀΣw``, and its volatility. It re-resolves no
data, introduces no new PIT surface, adds no runtime dependency, and creates no new
store; it consumes **no** ``BacktestResult`` and is not one (PO-5).

* :class:`~quantforge.optimization.spec.PortfolioOptimizationSpecification` - the
  declarative, content-addressed request: a name, exactly one sealed
  ``factor_risk_id``, the ``minimum_variance`` objective, and the fully-invested
  constraint ``1ᵀw = 1``.
* :class:`~quantforge.optimization.engine.PortfolioOptimizationEngine` - resolves,
  verifies (PO-1), enforces the ``2..N_MAX`` factor bound, reconstructs ``Σ``
  fail-closed (PO-3), solves the GMV under the pinned decimal context, and seals a
  :class:`~quantforge.optimization.result.PortfolioOptimization`, persisting it
  write-once to the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.optimization_engine`).
* :class:`~quantforge.optimization.result.PortfolioOptimization` - the sealed,
  content-addressed record: the objective / constraint spec / covariance basis, the
  ``(factor_risk_id, result_hash)`` reference, the shared schedule and producing engine
  version, the factor count and ordered labels, the per-factor weight cells, and the
  achieved variance / volatility. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (PO-2): not a ``Pit*`` type, no as-of
  accessor, and not a ``BacktestResult`` (PO-5).
* :class:`~quantforge.optimization.model.StatValue` - the UNDEFINED-preserving cell: a
  KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.optimization.model.OptimizationUndefinedReason` (a
  non-positive-definite covariance, ``SINGULAR_COVARIANCE``), never a fabricated ``0`` /
  ``NaN`` / divide-by-zero (PO-4).

Every identity is content-addressed (:mod:`quantforge.optimization.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split (:mod:`quantforge.optimization.errors`): a request / consistency defect raises; a
GMV genuinely undefined for the data (a singular covariance) is recorded with its
reason.
"""

from __future__ import annotations

from quantforge.optimization.engine import PortfolioOptimizationEngine
from quantforge.optimization.errors import (
    PortfolioOptimizationConfigurationError,
    PortfolioOptimizationConsistencyError,
    PortfolioOptimizationError,
)
from quantforge.optimization.identity import (
    optimization_id,
    optimization_result_hash,
)
from quantforge.optimization.model import (
    OptimizationStatus,
    OptimizationUndefinedReason,
    StatValue,
    WeightCell,
    factor_label,
)
from quantforge.optimization.result import (
    BOUNDARY_PIT,
    COVARIANCE_BASIS_PER_PERIOD,
    OPTIMIZATION_RESULT_FORMAT_VERSION,
    PortfolioOptimization,
)
from quantforge.optimization.solve import (
    MinVarianceSolution,
    solve_min_variance,
)
from quantforge.optimization.spec import (
    OBJECTIVE_MINIMUM_VARIANCE,
    PortfolioOptimizationSpecification,
)
from quantforge.optimization.version import (
    OPTIMIZATION_ENGINE_VERSION,
    OPTIMIZATION_SOLVE_VERSION,
    OPTIMIZATION_SPEC_VERSION,
    PortfolioOptimizationEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "COVARIANCE_BASIS_PER_PERIOD",
    "OBJECTIVE_MINIMUM_VARIANCE",
    "OPTIMIZATION_ENGINE_VERSION",
    "OPTIMIZATION_RESULT_FORMAT_VERSION",
    "OPTIMIZATION_SOLVE_VERSION",
    "OPTIMIZATION_SPEC_VERSION",
    "MinVarianceSolution",
    "OptimizationStatus",
    "OptimizationUndefinedReason",
    "PortfolioOptimization",
    "PortfolioOptimizationConfigurationError",
    "PortfolioOptimizationConsistencyError",
    "PortfolioOptimizationEngine",
    "PortfolioOptimizationEngineVersion",
    "PortfolioOptimizationError",
    "PortfolioOptimizationSpecification",
    "StatValue",
    "WeightCell",
    "default_decimal_context",
    "factor_label",
    "optimization_id",
    "optimization_result_hash",
    "solve_min_variance",
]
