"""The declarative calibration-significance request validates its own shape (§14)."""

from __future__ import annotations

import pytest

from quantforge.calsig.errors import CalSigConfigurationError
from quantforge.calsig.spec import CalibrationSignificanceSpecification
from quantforge.calsig.version import CALSIG_SPEC_VERSION


def test_valid_spec_round_trips_to_dict() -> None:
    spec = CalibrationSignificanceSpecification(
        name="phase29", source_calibration_id="sha256:cal"
    )
    assert spec.spec_version == CALSIG_SPEC_VERSION
    assert spec.to_dict() == {
        "spec_version": CALSIG_SPEC_VERSION,
        "name": "phase29",
        "source_calibration_id": "sha256:cal",
    }


def test_empty_name_is_rejected() -> None:
    with pytest.raises(CalSigConfigurationError):
        CalibrationSignificanceSpecification(name="", source_calibration_id="sha256:c")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(CalSigConfigurationError):
        CalibrationSignificanceSpecification(name="phase29", source_calibration_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(CalSigConfigurationError):
        CalibrationSignificanceSpecification(
            name="phase29", source_calibration_id="sha256:c", spec_version=""
        )
