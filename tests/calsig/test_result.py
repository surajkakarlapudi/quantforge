"""The sealed significance record round-trips byte-identically (§9, §10)."""

from __future__ import annotations

from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStat,
    SignificanceStatus,
    SignificanceUndefinedReason,
)
from quantforge.calsig.result import (
    NULL_MEAN_RATIO,
    CalibrationSignificance,
    SignificanceSummary,
)


def _tested_summary() -> SignificanceSummary:
    return SignificanceSummary(
        mean_variance_ratio=SignificanceStat.known("1.2"),
        null_mean_ratio=NULL_MEAN_RATIO,
        n_calibratable=4,
        standard_error=SignificanceStat.known("0.1"),
        t_statistic=SignificanceStat.known("2"),
        p_value=SignificanceStat.known("0.0455"),
        significance_status=SignificanceStatus.TESTED,
        bias_direction=BiasDirection.UNDER_FORECAST,
    )


def _undefined_summary() -> SignificanceSummary:
    reason = SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED
    undefined = SignificanceStat.undefined(reason)
    return SignificanceSummary(
        mean_variance_ratio=undefined,
        null_mean_ratio=NULL_MEAN_RATIO,
        n_calibratable=0,
        standard_error=undefined,
        t_statistic=undefined,
        p_value=undefined,
        significance_status=SignificanceStatus.UNDEFINED,
        status_reason=reason,
    )


def _seal(summary: SignificanceSummary) -> CalibrationSignificance:
    return CalibrationSignificance.seal(
        calibration_significance_engine_version_id="sha256:engine",
        calibration_significance_spec={
            "spec_version": "calsig/1",
            "name": "phase29",
            "source_calibration_id": "sha256:cal",
        },
        source_ref=("sha256:cal", "sha256:cal-hash"),
        boundary_kind="pit",
        summary=summary,
    )


def test_tested_record_round_trips() -> None:
    record = _seal(_tested_summary())
    restored = CalibrationSignificance.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.calibration_significance_id == record.calibration_significance_id
    assert restored.result_hash == record.result_hash


def test_undefined_record_round_trips() -> None:
    record = _seal(_undefined_summary())
    restored = CalibrationSignificance.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.significance_status is SignificanceStatus.UNDEFINED


def test_research_result_id_aliases_the_significance_id() -> None:
    record = _seal(_tested_summary())
    assert record.research_result_id == record.calibration_significance_id


def test_id_is_derived_not_stored() -> None:
    # A tampered stored id is ignored; the property re-derives from content.
    record = _seal(_tested_summary())
    payload = record.to_dict()
    payload["calibration_significance_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = CalibrationSignificance.from_dict(payload)
    assert restored.calibration_significance_id == record.calibration_significance_id


def test_result_hash_folds_the_answer() -> None:
    a = _seal(_tested_summary())
    changed = _tested_summary()
    changed = SignificanceSummary(
        mean_variance_ratio=changed.mean_variance_ratio,
        null_mean_ratio=changed.null_mean_ratio,
        n_calibratable=changed.n_calibratable,
        standard_error=changed.standard_error,
        t_statistic=SignificanceStat.known("3"),
        p_value=changed.p_value,
        significance_status=changed.significance_status,
        bias_direction=changed.bias_direction,
    )
    b = _seal(changed)
    assert a.result_hash != b.result_hash
    assert a.calibration_significance_id != b.calibration_significance_id


def test_record_is_not_pit() -> None:
    record = _seal(_tested_summary())
    assert record.boundary_kind == "pit"
    assert not hasattr(record, "as_of")
