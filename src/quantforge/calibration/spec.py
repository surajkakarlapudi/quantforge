"""The declarative, content-addressed risk-forecast-calibration request (§14).

A **risk-forecast-calibration request** names exactly one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` to calibrate. Like every
request in this project it is a frozen value whose identity is a pure content hash of
*what was declared* - the engine resolves and interprets it; it never executes caller
code (mirrors :class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification`).

The spec validates its own shape at construction (fail closed,
:class:`~quantforge.calibration.errors.CalibrationConfigurationError`): an empty
``name`` / ``spec_version`` / ``source_walk_forward_id``. It reads no store and no wall
clock - it cannot know whether the referenced walk-forward exists (that is the engine's
fail-closed resolution step) or how many windows it holds; it validates only the
request's internal shape.

There is **no** per-request numerical parameter: the calibratable-windows floor is
the fixed platform constant
:data:`~quantforge.calibration.result.MIN_CALIBRATABLE_WINDOWS` (folded into the id
by the engine version + identity, not the request), and the metric set is the single
approved methodology. So a calibration request is fully described by the name and
the one source id - the simplest request in the research spine.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.calibration.errors import CalibrationConfigurationError
from quantforge.calibration.version import CALIBRATION_SPEC_VERSION

__all__ = ["RiskForecastCalibrationSpecification"]


@dataclass(frozen=True, slots=True)
class RiskForecastCalibrationSpecification:
    """A declarative, content-addressed risk-forecast-calibration request.

    ``source_walk_forward_id`` is the ``research_result_id`` of exactly one sealed
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation`. Constructing this
    reads no store and no wall clock; it validates its own shape, exactly as the
    multiplicity / comparison layers refuse a misconfigured request.
    """

    name: str
    source_walk_forward_id: str
    spec_version: str = CALIBRATION_SPEC_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CalibrationConfigurationError(
                "a risk-forecast-calibration request must have a non-empty name"
            )
        if (
            not isinstance(self.source_walk_forward_id, str)
            or not self.source_walk_forward_id
        ):
            raise CalibrationConfigurationError(
                "source_walk_forward_id must be a non-empty walk-forward id"
            )
        if not isinstance(self.spec_version, str) or not self.spec_version:
            raise CalibrationConfigurationError(
                "spec_version must be a non-empty string"
            )

    def to_dict(self) -> dict[str, object]:
        """The canonical request payload (deterministic; embedded in the sealed
        record)."""
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "source_walk_forward_id": self.source_walk_forward_id,
        }
