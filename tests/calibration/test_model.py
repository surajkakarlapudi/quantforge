"""The calibration vocabulary + the UNDEFINED-preserving stat cell (RC-3)."""

from __future__ import annotations

import pytest

from quantforge.calibration.model import (
    CalibrationExcludedReason,
    CalibrationStat,
    CalibrationStatus,
    CalibrationUndefinedReason,
    StatStatus,
)


def test_known_cell_carries_value_only() -> None:
    cell = CalibrationStat.known("1.25")
    assert cell.status is StatStatus.KNOWN
    assert cell.value == "1.25"
    assert cell.reason is None
    assert cell.to_dict() == {"status": "known", "value": "1.25"}


def test_undefined_cell_carries_reason_only() -> None:
    cell = CalibrationStat.undefined(CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS)
    assert cell.status is StatStatus.UNDEFINED
    assert cell.value is None
    assert cell.to_dict() == {
        "status": "undefined",
        "reason": "no_calibratable_windows",
    }


def test_known_cell_rejects_missing_value() -> None:
    with pytest.raises(ValueError):
        CalibrationStat(status=StatStatus.KNOWN, value=None)


def test_undefined_cell_rejects_a_value() -> None:
    with pytest.raises(ValueError):
        CalibrationStat(
            status=StatStatus.UNDEFINED,
            value="1.0",
            reason=CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS,
        )


def test_stat_round_trips_through_from_dict() -> None:
    for cell in (
        CalibrationStat.known("0.5"),
        CalibrationStat.undefined(
            CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
        ),
    ):
        assert CalibrationStat.from_dict(cell.to_dict()) == cell


def test_from_dict_rejects_corrupt_cells() -> None:
    with pytest.raises(ValueError):
        CalibrationStat.from_dict({"status": "bogus"})
    with pytest.raises(ValueError):
        CalibrationStat.from_dict({"status": "known"})  # no value
    with pytest.raises(ValueError):
        CalibrationStat.from_dict({"status": "undefined", "reason": "not_a_reason"})


def test_status_and_reason_vocabularies_are_closed() -> None:
    assert {s.value for s in CalibrationStatus} == {"calibrated", "undefined"}
    assert {r.value for r in CalibrationUndefinedReason} == {
        "no_calibratable_windows",
        "insufficient_calibratable_windows",
    }
    assert {r.value for r in CalibrationExcludedReason} == {
        "window_undefined",
        "single_valid_period",
        "zero_predicted_variance",
        "predicted_variance_undefined",
    }
