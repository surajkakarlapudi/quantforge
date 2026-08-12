"""Walk-forward out-of-sample evaluation - the walk-forward layer (Phase 22).

The first **evaluation** capability strictly above Phase 21: a pure consumer that takes
one sealed :class:`~quantforge.optimization.result.PortfolioOptimization` GMV recipe and
asks the honest out-of-sample question the in-sample optimization cannot - *does the
recipe's predicted variance hold up on data it never saw?* It resolves the recipe (and,
transitively, the :class:`~quantforge.factorrisk.result.FactorRiskModel` and its
:class:`~quantforge.factorportfolio.result.FactorPortfolio` factors) from the shared
Phase 8 sidecar, aligns the factors' KNOWN return series on a common complete-case time
axis, partitions that axis into ordered train->test windows (strict train-before-test,
WF-2), re-estimates the covariance (Phase 20 method) and re-solves the fully-invested
GMV weights (Phase 21 method) on each training span, realizes those weights against the
strictly-subsequent test returns, chains the out-of-sample (OOS) returns, and summarizes
them (Phase 19 method). It re-resolves no data, introduces no new PIT surface, adds no
runtime dependency, and creates no new store; it consumes **no** ``BacktestResult`` and
is not one.

* :class:`~quantforge.walkforward.spec.WalkForwardEvaluationSpecification` - the
  declarative, content-addressed request: a name, exactly one sealed
  ``optimization_id``, and a :class:`~quantforge.walkforward.spec.TrainingPolicy`
  (expanding / rolling window, ``min_train_periods``, ``test_periods`` cadence, optional
  ``rolling_length``).
* :class:`~quantforge.walkforward.engine.WalkForwardEvaluationEngine` - resolves,
  verifies the walkable-recipe contract (OPTIMAL, GMV, fully-invested, WF-1/WF-5),
  resolves + verifies the transitively referenced risk model and factors, aligns the
  return axis (complete-case, WF-6), partitions it into windows, evaluates each
  (composing the Phase 20 / 21 / 19 pinned methods), and seals a
  :class:`~quantforge.walkforward.result.WalkForwardEvaluation`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.walk_forward_engine`).
* :class:`~quantforge.walkforward.result.WalkForwardEvaluation` - the sealed,
  content-addressed record: the ``(optimization_id, result_hash)`` reference, the shared
  schedule and producing engine version, the factor count + labels + inherited
  conventions, the ordered per-window results (train/test bounds, GMV weights, predicted
  / realized variance), the chained OOS return series, the aggregated summary, and the
  aggregate realized variance. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT**: not a ``Pit*`` type, no as-of accessor,
  and not a ``BacktestResult``.
* :class:`~quantforge.walkforward.model.StatValue` - the UNDEFINED-preserving cell: a
  KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.walkforward.model.WalkForwardUndefinedReason` (a
  non-positive-definite training covariance, ``SINGULAR_TRAINING_COVARIANCE``, or a
  mapped Phase 19 summary reason), never a fabricated ``0`` / ``NaN`` / divide-by-zero
  (WF-4).

Every identity is content-addressed (:mod:`quantforge.walkforward.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split (:mod:`quantforge.walkforward.errors`): a request / consistency defect raises; a
window genuinely undefined for the data (a singular training covariance) is recorded
with its reason.
"""

from __future__ import annotations

from quantforge.walkforward.engine import WalkForwardEvaluationEngine
from quantforge.walkforward.errors import (
    WalkForwardConfigurationError,
    WalkForwardConsistencyError,
    WalkForwardError,
)
from quantforge.walkforward.identity import (
    walk_forward_id,
    walk_forward_result_hash,
)
from quantforge.walkforward.model import (
    StatStatus,
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
    factor_label,
)
from quantforge.walkforward.result import (
    BOUNDARY_PIT,
    MIN_VALID_WINDOWS,
    WALKFORWARD_RESULT_FORMAT_VERSION,
    WalkForwardEvaluation,
    WindowResult,
)
from quantforge.walkforward.spec import (
    WINDOW_EXPANDING,
    WINDOW_ROLLING,
    TrainingPolicy,
    WalkForwardEvaluationSpecification,
)
from quantforge.walkforward.version import (
    WALKFORWARD_ENGINE_VERSION,
    WALKFORWARD_METHOD_VERSION,
    WALKFORWARD_SPEC_VERSION,
    WalkForwardEngineVersion,
    default_decimal_context,
)
from quantforge.walkforward.windows import WindowSpec, build_windows

__all__ = [
    "BOUNDARY_PIT",
    "MIN_VALID_WINDOWS",
    "WALKFORWARD_ENGINE_VERSION",
    "WALKFORWARD_METHOD_VERSION",
    "WALKFORWARD_RESULT_FORMAT_VERSION",
    "WALKFORWARD_SPEC_VERSION",
    "WINDOW_EXPANDING",
    "WINDOW_ROLLING",
    "StatStatus",
    "StatValue",
    "TrainingPolicy",
    "WalkForwardConfigurationError",
    "WalkForwardConsistencyError",
    "WalkForwardEngineVersion",
    "WalkForwardError",
    "WalkForwardEvaluation",
    "WalkForwardEvaluationEngine",
    "WalkForwardEvaluationSpecification",
    "WalkForwardSummary",
    "WalkForwardUndefinedReason",
    "WindowResult",
    "WindowSpec",
    "WindowStatus",
    "build_windows",
    "default_decimal_context",
    "factor_label",
    "walk_forward_id",
    "walk_forward_result_hash",
]
