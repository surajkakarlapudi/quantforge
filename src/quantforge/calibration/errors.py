"""Exception hierarchy for the risk-forecast-calibration layer (Phase 26, §15).

Rooted at :class:`CalibrationError` so a caller can catch every failure of this layer
with one type. Phase 26 is a *pure consumer* strictly above Phase 22: it resolves
exactly one already-sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation`
from the shared research sidecar, reads its per-window sealed ``predicted_variance``
(in-sample ``wᵀΣw``) and ``realized_variance`` (out-of-sample population variance), and
seals the per-window forecast-vs-outcome ratios plus the aggregate calibration
statistics. It resolves no data at any ``T`` and re-derives nothing from source - it
never re-solves a window or recomputes a variance from ``oos_returns`` (RC-4) - so its
only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the multiplicity /
walk-forward layers in particular:

* A **data / evaluation condition** - a window the source sealed as UNDEFINED, a
  window whose ``realized_variance`` is UNDEFINED (a single out-of-sample period,
  ``SINGLE_VALID_PERIOD``), or a window whose ``predicted_variance`` is non-positive
  - is **never** an exception. It is excluded from the calibratable family and
  recorded as a first-class :class:`~quantforge.calibration.result.ExcludedWindow`
  carrying *why* (RC-3), never imputed, never coerced to a ratio, never silently
  dropped. Too few calibratable windows likewise is not an exception: the record
  still seals with ``calibration_status`` UNDEFINED
  (``INSUFFICIENT_CALIBRATABLE_WINDOWS``).
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_walk_forward_id``, the source id absent from the sidecar, or a resolved
  record whose ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.walkforward.result.WalkForwardEvaluation` - *is* raised. These
  are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong calibration.
"""

from __future__ import annotations

__all__ = [
    "CalibrationConfigurationError",
    "CalibrationConsistencyError",
    "CalibrationError",
]


class CalibrationError(Exception):
    """Base class for all risk-forecast-calibration-layer errors."""


class CalibrationConfigurationError(CalibrationError):
    """A risk-forecast-calibration request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification` (an empty
    ``name`` / ``spec_version`` / ``source_walk_forward_id``) or for a
    non-:class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification`
    argument to the engine. We refuse to guess a request's intent, exactly as the
    walk-forward and multiplicity layers refuse a misconfigured request."""


class CalibrationConsistencyError(CalibrationError):
    """A calibration cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, RC-1): the
    ``source_walk_forward_id`` is absent from the research sidecar; the resolved record
    does not decode as a :class:`~quantforge.walkforward.result.WalkForwardEvaluation`;
    or the resolved record's ``research_result_id`` disagrees with the requested id (the
    sidecar is inconsistent). Each is a consistency violation and is raised - never
    silently computed around. (A window the source sealed as UNDEFINED, or whose
    ``realized_variance`` / ``predicted_variance`` is not calibratable, is *not* raised:
    it is genuinely undefined for the data, so it is excluded from the family and
    recorded as a first-class :class:`~quantforge.calibration.result.ExcludedWindow`,
    RC-3.)"""
