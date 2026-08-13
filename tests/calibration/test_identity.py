"""Content-addressed identity for the calibration layer (§10, §11)."""

from __future__ import annotations

from quantforge.calibration.identity import (
    risk_forecast_calibration_id,
    risk_forecast_calibration_result_hash,
)


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "calibration_engine_version_id": "sha256:engine",
        "name": "calib",
        "spec_version": "calibration/1",
        "source_walk_forward_id": "sha256:src",
        "source_result_hash": "sha256:srchash",
        "min_calibratable_windows": 2,
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return risk_forecast_calibration_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert risk_forecast_calibration_result_hash([{"block": "x"}]).startswith("sha256:")


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_each_fold_changes_the_id() -> None:
    base = _id()
    assert _id(calibration_engine_version_id="sha256:other") != base
    assert _id(name="other") != base
    assert _id(spec_version="calibration/2") != base
    assert _id(source_walk_forward_id="sha256:other") != base
    assert _id(source_result_hash="sha256:other") != base
    assert _id(min_calibratable_windows=3) != base
    assert _id(result_hash="sha256:other") != base


def test_result_hash_is_sensitive_to_a_single_cell() -> None:
    a = risk_forecast_calibration_result_hash(
        [{"block": "window", "variance_ratio": "0.25"}]
    )
    b = risk_forecast_calibration_result_hash(
        [{"block": "window", "variance_ratio": "0.26"}]
    )
    assert a != b


def test_result_hash_is_order_sensitive() -> None:
    a = risk_forecast_calibration_result_hash(
        [{"block": "window", "index": 0}, {"block": "window", "index": 1}]
    )
    b = risk_forecast_calibration_result_hash(
        [{"block": "window", "index": 1}, {"block": "window", "index": 0}]
    )
    assert a != b
