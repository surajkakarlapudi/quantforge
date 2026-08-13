"""The declarative calibration request (§14): validation + canonicalization."""

from __future__ import annotations

import pytest

from quantforge.calibration.errors import CalibrationConfigurationError
from quantforge.calibration.spec import RiskForecastCalibrationSpecification
from quantforge.calibration.version import CALIBRATION_SPEC_VERSION


def _spec(**overrides: object) -> RiskForecastCalibrationSpecification:
    base: dict[str, object] = {
        "name": "calib",
        "source_walk_forward_id": "sha256:src",
    }
    base.update(overrides)
    return RiskForecastCalibrationSpecification(**base)  # type: ignore[arg-type]


def test_default_spec_version() -> None:
    assert _spec().spec_version == CALIBRATION_SPEC_VERSION


def test_to_dict_is_the_canonical_request() -> None:
    assert _spec().to_dict() == {
        "spec_version": CALIBRATION_SPEC_VERSION,
        "name": "calib",
        "source_walk_forward_id": "sha256:src",
    }


def test_empty_name_is_rejected() -> None:
    with pytest.raises(CalibrationConfigurationError):
        _spec(name="")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(CalibrationConfigurationError):
        _spec(source_walk_forward_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(CalibrationConfigurationError):
        _spec(spec_version="")


def test_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(AttributeError):
        spec.name = "other"  # type: ignore[misc]
