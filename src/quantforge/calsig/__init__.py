"""Calibration-significance test over one sealed risk-forecast calibration (Phase 29).

The first **calibration-significance** capability strictly above Phase 26: a pure
consumer that reads, from one sealed
:class:`~quantforge.calibration.result.RiskForecastCalibration`, its sealed aggregate
``mean_variance_ratio``, population ``variance_ratio_dispersion`` and its
calibratable-window count ``n_calibratable``, and asks what the calibration never asks -
*is the mean variance ratio significantly different from ``1`` (perfect calibration on
average)?* It runs the one-sample large-sample two-sided test
``t = (mean - 1) / (dispersion / sqrt(K))``, ``p = 2·(1 - Φ(|t|))``, reusing the
*identical* deterministic standard-normal CDF
:func:`~quantforge._stats.normal.standard_normal_cdf` (shared with Phases 23/24) - so it
adds no new statistical primitive. It resolves the one calibration from the shared
Phase 8 sidecar, gates on its defensibility, consumes its sealed statistics verbatim
(never recomputed, CS-4), and seals the significance verdict. It re-resolves no data,
introduces no new PIT surface, adds no runtime dependency, uses no ``_linalg``
primitive, and creates no new store.

* :class:`~quantforge.calsig.spec.CalibrationSignificanceSpecification` - the
  declarative, content-addressed request: a name and exactly one sealed
  ``source_calibration_id``. There is no per-request numerical parameter: the null mean
  tested is the fixed platform constant
  :data:`~quantforge.calsig.result.NULL_MEAN_RATIO` (``1``).
* :class:`~quantforge.calsig.engine.CalibrationSignificanceEngine` - resolves + verifies
  the source calibration (present, a ``RiskForecastCalibration``, id matches), gates on
  ``calibration_status == CALIBRATED`` (CS-2), reads its sealed mean / dispersion /
  count verbatim (CS-4), computes the test
  (:func:`~quantforge.calsig.compute.test_calibration_significance`), and seals a
  :class:`~quantforge.calsig.result.CalibrationSignificance`, persisting it write-once
  to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.calibration_significance_engine`).
* :class:`~quantforge.calsig.result.CalibrationSignificance` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source calibration and
  the aggregate :class:`~quantforge.calsig.result.SignificanceSummary` (the mean carried
  verbatim, the null mean, the window count, the standard error, the ``t`` statistic,
  the two-sided ``p`` value, the descriptive bias direction, and the roll-up status).
  Satisfies the :class:`~quantforge.factors.store.ResearchRecord` Protocol and
  round-trips byte-identically. It is **ex-post, not PIT** (CS-6): not a ``Pit*`` type
  and no as-of accessor.
* :class:`~quantforge.calsig.model.SignificanceStatus` /
  :class:`~quantforge.calsig.model.SignificanceUndefinedReason` /
  :class:`~quantforge.calsig.model.BiasDirection` /
  :class:`~quantforge.calsig.model.SignificanceStat` - the closed fail-closed
  vocabulary: whether the test was run, why it (or a cell) is UNDEFINED, the descriptive
  sign of the mis-calibration, and the UNDEFINED-preserving stat cell.

Every identity is content-addressed (:mod:`quantforge.calsig.identity`) and transitively
pins the source calibration's ``result_hash``, every value is deterministically
serializable and computed in exact ``Decimal`` arithmetic under a pinned context
(``Decimal.sqrt`` and the reused ``Φ`` CDF the only transcendentals; no RNG, no float,
no unbounded iteration), and every failure follows the raise-vs-record split
(:mod:`quantforge.calsig.errors`): a request / consistency defect raises; a source that
is not CALIBRATED seals an UNDEFINED ``SOURCE_NOT_CALIBRATED`` verdict and a
zero-dispersion family seals UNDEFINED ``t`` / ``p`` (``ZERO_RATIO_DISPERSION``), never
imputed, never a divide-by-zero.
"""

from __future__ import annotations

from quantforge.calsig.compute import (
    CalibratableFamily,
    SignificanceComputation,
    test_calibration_significance,
)
from quantforge.calsig.engine import CalibrationSignificanceEngine
from quantforge.calsig.errors import (
    CalSigConfigurationError,
    CalSigConsistencyError,
    CalSigError,
)
from quantforge.calsig.identity import (
    calibration_significance_id,
    calibration_significance_result_hash,
)
from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStat,
    SignificanceStatus,
    SignificanceUndefinedReason,
    StatStatus,
)
from quantforge.calsig.result import (
    BOUNDARY_PIT,
    CALSIG_RESULT_FORMAT_VERSION,
    NULL_MEAN_RATIO,
    CalibrationSignificance,
    SignificanceSummary,
)
from quantforge.calsig.spec import CalibrationSignificanceSpecification
from quantforge.calsig.version import (
    CALSIG_ENGINE_VERSION,
    CALSIG_METHOD_VERSION,
    CALSIG_NORMAL_VERSION,
    CALSIG_SPEC_VERSION,
    CalibrationSignificanceEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "CALSIG_ENGINE_VERSION",
    "CALSIG_METHOD_VERSION",
    "CALSIG_NORMAL_VERSION",
    "CALSIG_RESULT_FORMAT_VERSION",
    "CALSIG_SPEC_VERSION",
    "NULL_MEAN_RATIO",
    "BiasDirection",
    "CalSigConfigurationError",
    "CalSigConsistencyError",
    "CalSigError",
    "CalibratableFamily",
    "CalibrationSignificance",
    "CalibrationSignificanceEngine",
    "CalibrationSignificanceEngineVersion",
    "CalibrationSignificanceSpecification",
    "SignificanceComputation",
    "SignificanceStat",
    "SignificanceStatus",
    "SignificanceSummary",
    "SignificanceUndefinedReason",
    "StatStatus",
    "calibration_significance_id",
    "calibration_significance_result_hash",
    "default_decimal_context",
    "test_calibration_significance",
]
