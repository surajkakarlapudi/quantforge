"""Content-addressed identity is deterministic and sensitive to every fold (§10)."""

from __future__ import annotations

from quantforge.calsig.identity import (
    calibration_significance_id,
    calibration_significance_result_hash,
)
from quantforge.calsig.version import CalibrationSignificanceEngineVersion


def _id(**overrides: str) -> str:
    base: dict[str, str] = {
        "calibration_significance_engine_version_id": "sha256:engine",
        "name": "phase29",
        "spec_version": "calsig/1",
        "source_calibration_id": "sha256:cal",
        "source_result_hash": "sha256:cal-hash",
        "null_mean_ratio": "1",
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return calibration_significance_id(**base)


def test_result_hash_is_deterministic_and_sha256() -> None:
    cells: list[dict[str, object]] = [
        {"block": "summary", "t_statistic": {"status": "known", "value": "2"}}
    ]
    first = calibration_significance_result_hash(cells)
    second = calibration_significance_result_hash(cells)
    assert first == second
    assert first.startswith("sha256:")


def test_result_hash_changes_with_a_differing_cell() -> None:
    a_cells: list[dict[str, object]] = [{"block": "summary", "t": "2"}]
    b_cells: list[dict[str, object]] = [{"block": "summary", "t": "3"}]
    a = calibration_significance_result_hash(a_cells)
    b = calibration_significance_result_hash(b_cells)
    assert a != b


def test_id_is_deterministic() -> None:
    assert _id() == _id()
    assert _id().startswith("sha256:")


def test_id_is_sensitive_to_every_fold() -> None:
    base = _id()
    assert _id(name="other") != base
    assert _id(source_calibration_id="sha256:other") != base
    assert _id(source_result_hash="sha256:other-hash") != base
    assert _id(null_mean_ratio="2") != base
    assert _id(result_hash="sha256:other-answer") != base
    assert _id(calibration_significance_engine_version_id="sha256:v2") != base


def test_engine_version_id_folds_context_and_method() -> None:
    base = CalibrationSignificanceEngineVersion()
    other_prec = CalibrationSignificanceEngineVersion(decimal_precision=28)
    other_method = CalibrationSignificanceEngineVersion(
        method_version="calsig-method/2"
    )
    assert (
        base.calibration_significance_engine_version_id
        != other_prec.calibration_significance_engine_version_id
    )
    assert (
        base.calibration_significance_engine_version_id
        != other_method.calibration_significance_engine_version_id
    )
