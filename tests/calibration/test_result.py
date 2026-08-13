"""The sealed calibration record (§9, §10): seal, round-trip, derived ids, accessors."""

from __future__ import annotations

import json

import pytest

from quantforge.calibration.model import (
    CalibrationExcludedReason,
    CalibrationStat,
    CalibrationStatus,
)
from quantforge.calibration.result import (
    CalibrationCoverage,
    CalibrationSummary,
    ExcludedWindow,
    RiskForecastCalibration,
    WindowCalibrationCell,
)


def _record() -> RiskForecastCalibration:
    windows = (
        WindowCalibrationCell(
            index=0,
            predicted_variance="4",
            realized_variance="1",
            predicted_volatility="2",
            realized_volatility="1",
            variance_ratio="0.25",
            volatility_ratio="0.5",
        ),
        WindowCalibrationCell(
            index=1,
            predicted_variance="1",
            realized_variance="4",
            predicted_volatility="1",
            realized_volatility="2",
            variance_ratio="4",
            volatility_ratio="2",
        ),
    )
    excluded = (
        ExcludedWindow(index=2, reason=CalibrationExcludedReason.WINDOW_UNDEFINED),
    )
    summary = CalibrationSummary(
        mean_variance_ratio=CalibrationStat.known("2.125"),
        aggregate_bias=CalibrationStat.known("1"),
        variance_ratio_dispersion=CalibrationStat.known("1.875"),
        underforecast_frequency=CalibrationStat.known("0.5"),
        max_variance_ratio=CalibrationStat.known("4"),
        min_variance_ratio=CalibrationStat.known("0.25"),
        calibration_status=CalibrationStatus.CALIBRATED,
        status_reason=None,
    )
    coverage = CalibrationCoverage(n_windows=3, n_calibratable=2, n_excluded=1)
    return RiskForecastCalibration.seal(
        calibration_engine_version_id="sha256:engine",
        calibration_spec={
            "spec_version": "calibration/1",
            "name": "calib",
            "source_walk_forward_id": "sha256:src",
        },
        source_ref=("sha256:src", "sha256:srchash"),
        boundary_kind="pit",
        windows=windows,
        excluded=excluded,
        summary=summary,
        coverage=coverage,
    )


def test_seal_folds_answer_into_result_hash() -> None:
    assert _record().result_hash.startswith("sha256:")


def test_derived_id_aliases_research_result_id() -> None:
    r = _record()
    assert r.risk_forecast_calibration_id == r.research_result_id
    assert r.risk_forecast_calibration_id.startswith("sha256:")


def test_round_trip_is_byte_identical() -> None:
    r = _record()
    again = RiskForecastCalibration.from_dict(r.to_dict())
    assert json.dumps(r.to_dict(), sort_keys=True) == json.dumps(
        again.to_dict(), sort_keys=True
    )
    assert again.risk_forecast_calibration_id == r.risk_forecast_calibration_id
    assert again.result_hash == r.result_hash


def test_id_is_rederived_not_read_from_state() -> None:
    # A tampered stored id is ignored: the property recomputes from content.
    r = _record()
    raw = r.to_dict()
    raw["risk_forecast_calibration_id"] = "sha256:tampered"
    raw["research_result_id"] = "sha256:tampered"
    again = RiskForecastCalibration.from_dict(raw)
    assert again.risk_forecast_calibration_id == r.risk_forecast_calibration_id


def test_accessors() -> None:
    r = _record()
    assert r.source_walk_forward_id == "sha256:src"
    assert r.source_result_hash == "sha256:srchash"
    assert r.calibration_status is CalibrationStatus.CALIBRATED


def test_not_a_pit_type_and_no_as_of_accessor() -> None:
    # Ex-post record: boundary documents the input side, but there is no as-of surface.
    r = _record()
    assert r.boundary_kind == "pit"
    assert not hasattr(r, "as_of")
    assert type(r).__name__ == "RiskForecastCalibration"
    assert not type(r).__name__.startswith("Pit")


def _resealed(**win0: str) -> RiskForecastCalibration:
    """Re-seal ``_record`` with the first window's fields overridden (to probe seal)."""
    r = _record()
    base = r.windows[0]
    first = WindowCalibrationCell(
        index=base.index,
        predicted_variance=win0.get("predicted_variance", base.predicted_variance),
        realized_variance=win0.get("realized_variance", base.realized_variance),
        predicted_volatility=win0.get(
            "predicted_volatility", base.predicted_volatility
        ),
        realized_volatility=win0.get("realized_volatility", base.realized_volatility),
        variance_ratio=win0.get("variance_ratio", base.variance_ratio),
        volatility_ratio=win0.get("volatility_ratio", base.volatility_ratio),
    )
    return RiskForecastCalibration.seal(
        calibration_engine_version_id=r.calibration_engine_version_id,
        calibration_spec=r.calibration_spec,
        source_ref=r.source_ref,
        boundary_kind=r.boundary_kind,
        windows=(first, r.windows[1]),
        excluded=r.excluded,
        summary=r.summary,
        coverage=r.coverage,
    )


def test_volatilities_are_excluded_from_the_hash() -> None:
    # The derivable per-window volatilities do not enter result_hash; the variances do.
    r = _record()
    resealed = _resealed(predicted_volatility="999", realized_volatility="999")
    assert resealed.result_hash == r.result_hash


def test_variance_ratio_change_changes_the_hash() -> None:
    r = _record()
    resealed = _resealed(variance_ratio="0.26")
    assert resealed.result_hash != r.result_hash


def test_from_dict_rejects_unknown_excluded_reason() -> None:
    r = _record()
    raw = r.to_dict()
    excluded = raw["excluded"]
    assert isinstance(excluded, list)
    first = excluded[0]
    assert isinstance(first, dict)
    first["reason"] = "not_a_reason"
    with pytest.raises(ValueError):
        RiskForecastCalibration.from_dict(raw)
