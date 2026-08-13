"""Exception hierarchy for the calibration-significance layer (Phase 29, §15).

Rooted at :class:`CalSigError` so a caller can catch every failure of this layer with
one type. Phase 29 is a *pure consumer* strictly above Phase 26: it resolves exactly one
already-sealed :class:`~quantforge.calibration.result.RiskForecastCalibration` from the
shared research sidecar, reads its sealed ``mean_variance_ratio`` /
``variance_ratio_dispersion`` / ``n_calibratable``, and seals the one-sample
significance test of the mean variance ratio against the null mean ``1``. It resolves no
data and re-derives no statistic from source (CS-4), so its only failures are of the
request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the calibration /
MinTRL layers in particular:

* A **data / evaluation condition** - a source whose ``calibration_status`` is UNDEFINED
  (below the Phase-26 calibratable-window floor, or no calibratable windows at all), or
  a calibratable family whose per-window variance ratios have zero dispersion - is
  **never** an exception. A non-CALIBRATED source seals a record whose
  ``significance_status`` is UNDEFINED (``SOURCE_NOT_CALIBRATED``); a zero-dispersion
  family seals KNOWN ``mean_variance_ratio`` / ``bias_direction`` but UNDEFINED
  ``t_statistic`` / ``p_value`` (``ZERO_RATIO_DISPERSION``, CS-3), never imputed, never
  a divide-by-zero.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_calibration_id``, the source id absent from the sidecar, or a resolved record
  whose ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.calibration.result.RiskForecastCalibration` - *is* raised. These
  are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong significance verdict.
"""

from __future__ import annotations

__all__ = [
    "CalSigConfigurationError",
    "CalSigConsistencyError",
    "CalSigError",
]


class CalSigError(Exception):
    """Base class for all calibration-significance-layer errors."""


class CalSigConfigurationError(CalSigError):
    """A calibration-significance request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification` (an empty
    ``name`` / ``spec_version`` / ``source_calibration_id``) or for a non-spec argument
    to the engine. We refuse to guess a request's intent, exactly as the calibration and
    MinTRL layers refuse a misconfigured request."""


class CalSigConsistencyError(CalSigError):
    """A significance test cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, CS-1): the
    ``source_calibration_id`` is absent from the research sidecar; the resolved record
    does not decode as a
    :class:`~quantforge.calibration.result.RiskForecastCalibration`; or the resolved
    record's ``research_result_id`` disagrees with the requested id (the sidecar is
    inconsistent). Each is a consistency violation and is raised - never silently
    computed around. (A source that is not CALIBRATED, or a zero-dispersion family, is
    *not* raised: it is genuinely undefined for the data, so the record seals with an
    UNDEFINED status or cell, CS-2/CS-3.)"""
