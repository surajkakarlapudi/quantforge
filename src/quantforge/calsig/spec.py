"""The declarative, content-addressed calibration-significance request (§14).

A **calibration-significance request** names exactly one sealed
:class:`~quantforge.calibration.result.RiskForecastCalibration` to test. Like every
request in this project it is a frozen value whose identity is a pure content hash of
*what was declared* - the engine resolves and interprets it; it never executes caller
code (mirrors :class:`~quantforge.calibration.spec.RiskForecastCalibrationSpecification`
and :class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.calsig.errors.CalSigConfigurationError`): an empty ``name`` /
``spec_version`` / ``source_calibration_id``. It reads no store and no wall clock - it
cannot know whether the referenced calibration exists (that is the engine's fail-closed
resolution step) or whether it is CALIBRATED; it validates only the request's internal
shape.

There is **no** per-request numerical parameter: the null mean tested is the fixed
platform constant :data:`~quantforge.calsig.result.NULL_MEAN_RATIO` (``1``, folded into
the id by the identity, not the request), and the method is the single approved
one-sample large-sample two-sided test. So a significance request is fully described by
the name and the one source id - the simplest request in the research spine, alongside
the calibration request it consumes.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.calsig.errors import CalSigConfigurationError
from quantforge.calsig.version import CALSIG_SPEC_VERSION

__all__ = ["CalibrationSignificanceSpecification"]


@dataclass(frozen=True, slots=True)
class CalibrationSignificanceSpecification:
    """A declarative, content-addressed calibration-significance request.

    ``source_calibration_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.calibration.result.RiskForecastCalibration`. Constructing this
    reads no store and no wall clock; it validates its own shape, exactly as the
    calibration / MinTRL layers refuse a misconfigured request.
    """

    name: str
    source_calibration_id: str
    spec_version: str = CALSIG_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CalSigConfigurationError(
                "a calibration-significance request must have a non-empty name"
            )
        if (
            not isinstance(self.source_calibration_id, str)
            or not self.source_calibration_id
        ):
            raise CalSigConfigurationError(
                "source_calibration_id must be a non-empty calibration id"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise CalSigConfigurationError("spec_version must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_calibration_id": self.source_calibration_id,
        }
