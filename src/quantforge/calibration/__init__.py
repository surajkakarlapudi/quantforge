"""Walk-forward risk-forecast calibration over one sealed evaluation (Phase 26).

The first **risk-model out-of-sample validation** capability strictly above Phase
22: a pure consumer that reads, per window of one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`, the
reserved-but-unconsumed in-sample forecast ``predicted_variance`` (``wᵀΣw`` over the
training covariance, the Phase 20/21 method) and the out-of-sample outcome
``realized_variance`` (population variance of the achieved test returns), and asks
the question the whole ``FactorRiskModel → PortfolioOptimization →
WalkForwardEvaluation`` chain never answers - *does the covariance forecast the GMV
construction rests on actually hold out-of-sample?* It resolves the one walk-forward
from the shared Phase 8 sidecar, classifies each window into the calibratable family
(recording every non-calibratable window as a first-class exclusion, never imputed),
and seals the per-window forecast-vs-outcome ratios plus the aggregate bias /
dispersion statistics. It re-resolves no data, introduces no new PIT surface, adds
no runtime dependency, uses no ``_linalg`` / ``_stats`` primitive, and creates no
new store.

* :class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification` - the
  declarative, content-addressed request: a name and exactly one sealed
  ``source_walk_forward_id`` (no per-request numerical parameter).
* :class:`~quantforge.calibration.engine.RiskForecastCalibrationEngine` - resolves +
  verifies the source walk-forward (present, a ``WalkForwardEvaluation``, id matches),
  classifies the calibratable family + the exclusions (RC-3), calibrates the family
  (:func:`~quantforge.calibration.compute.calibrate`), and seals a
  :class:`~quantforge.calibration.result.RiskForecastCalibration`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.risk_calibration_engine`).
* :class:`~quantforge.calibration.result.RiskForecastCalibration` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source
  walk-forward, per calibratable window the variance / volatility ratios, the
  excluded windows, and the aggregate
  :class:`~quantforge.calibration.result.CalibrationSummary` (mean ratio, pooled
  ``aggregate_bias``, dispersion, under-forecast frequency, min / max, roll-up
  status). Satisfies the :class:`~quantforge.factors.store.ResearchRecord` Protocol
  and round-trips byte-identically. It is **ex-post, not PIT** (RC-6): not a
  ``Pit*`` type and no as-of accessor.
* :class:`~quantforge.calibration.model.CalibrationStatus` /
  :class:`~quantforge.calibration.model.CalibrationExcludedReason` /
  :class:`~quantforge.calibration.model.CalibrationUndefinedReason` /
  :class:`~quantforge.calibration.model.CalibrationStat` - the closed fail-closed
  vocabulary: whether the aggregate is defensible, why a window is excluded, why an
  aggregate is UNDEFINED, and the UNDEFINED-preserving stat cell.

Every identity is content-addressed (:mod:`quantforge.calibration.identity`) and
transitively pins the source walk-forward's ``result_hash``, every value is
deterministically serializable and computed in exact ``Decimal`` arithmetic under a
pinned context (``Decimal.sqrt`` the only transcendental; no RNG, no float, no
iteration), and every failure follows the raise-vs-record split
(:mod:`quantforge.calibration.errors`): a request / consistency defect raises; a
window genuinely non-calibratable in the source is excluded and recorded with its
reason.
"""

from __future__ import annotations

from quantforge.calibration.compute import (
    CalibratableWindow,
    CalibrationComputation,
    CalibrationSummaryComputation,
    WindowRatios,
    calibrate,
)
from quantforge.calibration.engine import RiskForecastCalibrationEngine
from quantforge.calibration.errors import (
    CalibrationConfigurationError,
    CalibrationConsistencyError,
    CalibrationError,
)
from quantforge.calibration.identity import (
    risk_forecast_calibration_id,
    risk_forecast_calibration_result_hash,
)
from quantforge.calibration.model import (
    CalibrationExcludedReason,
    CalibrationStat,
    CalibrationStatus,
    CalibrationUndefinedReason,
    StatStatus,
)
from quantforge.calibration.result import (
    BOUNDARY_PIT,
    CALIBRATION_RESULT_FORMAT_VERSION,
    MIN_CALIBRATABLE_WINDOWS,
    CalibrationCoverage,
    CalibrationSummary,
    ExcludedWindow,
    RiskForecastCalibration,
    WindowCalibrationCell,
)
from quantforge.calibration.spec import RiskForecastCalibrationSpecification
from quantforge.calibration.version import (
    CALIBRATION_ENGINE_VERSION,
    CALIBRATION_METHOD_VERSION,
    CALIBRATION_SPEC_VERSION,
    RiskForecastCalibrationEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "CALIBRATION_ENGINE_VERSION",
    "CALIBRATION_METHOD_VERSION",
    "CALIBRATION_RESULT_FORMAT_VERSION",
    "CALIBRATION_SPEC_VERSION",
    "MIN_CALIBRATABLE_WINDOWS",
    "CalibratableWindow",
    "CalibrationComputation",
    "CalibrationConfigurationError",
    "CalibrationConsistencyError",
    "CalibrationCoverage",
    "CalibrationError",
    "CalibrationExcludedReason",
    "CalibrationStat",
    "CalibrationStatus",
    "CalibrationSummary",
    "CalibrationSummaryComputation",
    "CalibrationUndefinedReason",
    "ExcludedWindow",
    "RiskForecastCalibration",
    "RiskForecastCalibrationEngine",
    "RiskForecastCalibrationEngineVersion",
    "RiskForecastCalibrationSpecification",
    "StatStatus",
    "WindowCalibrationCell",
    "WindowRatios",
    "calibrate",
    "default_decimal_context",
    "risk_forecast_calibration_id",
    "risk_forecast_calibration_result_hash",
]
