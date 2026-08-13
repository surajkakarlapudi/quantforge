"""End-to-end calibration-significance through the engine (§6, CS-1..CS-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.calsig.errors import (
    CalSigConfigurationError,
    CalSigConsistencyError,
)
from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStatus,
    SignificanceUndefinedReason,
    StatStatus,
)
from quantforge.calsig.result import CalibrationSignificance
from quantforge.factors.errors import FactorConsistencyError
from tests.calsig.builders import (
    calibrated,
    calibrated_mean_undefined,
    calsig_engine,
    make_calibration,
    make_spec,
    undefined_source,
    workspace,
    zero_dispersion,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``RiskForecastCalibration`` :class:`ResearchRecord` for fail-closed
    tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-calibration", "id": self.research_result_id}


# -- happy path (CS-4/CS-5) --------------------------------------------------


def test_happy_path_tests_the_family(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(
        ws, summary=calibrated(mean="1.2", dispersion="0.2"), n_calibratable=4
    )
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))

    assert isinstance(result, CalibrationSignificance)
    assert result.significance_status is SignificanceStatus.TESTED
    assert result.summary.n_calibratable == 4
    assert result.summary.null_mean_ratio == "1"
    assert result.summary.bias_direction is BiasDirection.UNDER_FORECAST
    assert result.summary.mean_variance_ratio.value == "1.2"
    assert result.summary.t_statistic.value == "2"
    assert result.summary.p_value.status is StatStatus.KNOWN


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.1", dispersion="0.2"))
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    assert result.source_calibration_id == calibration.research_result_id
    assert result.source_result_hash == calibration.result_hash


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.1", dispersion="0.2"))
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    assert result.boundary_kind == calibration.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- defensibility gate (CS-2/CS-3) ------------------------------------------


def test_undefined_source_seals_undefined_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=undefined_source())
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert (
        result.summary.status_reason
        is SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED
    )
    assert result.summary.mean_variance_ratio.status is StatStatus.UNDEFINED
    assert result.summary.bias_direction is None


def test_calibrated_but_undefined_mean_is_source_not_calibrated(
    tmp_path: Path,
) -> None:
    # Defensive branch: CALIBRATED status but the aggregate mean cell is UNDEFINED.
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated_mean_undefined())
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert (
        result.summary.status_reason
        is SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED
    )


def test_zero_dispersion_seals_partial_undefined(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=zero_dispersion(mean="1.4"))
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert (
        result.summary.status_reason
        is SignificanceUndefinedReason.ZERO_RATIO_DISPERSION
    )
    # Mean + direction survive; t / p are undefined, never a divide-by-zero.
    assert result.summary.mean_variance_ratio.value == "1.4"
    assert result.summary.bias_direction is BiasDirection.UNDER_FORECAST
    assert result.summary.t_statistic.status is StatStatus.UNDEFINED


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.2", dispersion="0.2"))
    engine = calsig_engine(ws)
    first = engine.evaluate(make_spec(calibration.research_result_id))
    second = engine.evaluate(make_spec(calibration.research_result_id))
    assert first.calibration_significance_id == second.calibration_significance_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, CalibrationSignificance.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


# -- identity sensitivity (CS-1) ---------------------------------------------


def test_different_source_answer_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_calibration(ws, summary=calibrated(mean="1.2", dispersion="0.2"), name="a")
    b = make_calibration(ws, summary=calibrated(mean="1.3", dispersion="0.2"), name="b")
    engine = calsig_engine(ws)
    ra = engine.evaluate(make_spec(a.research_result_id))
    rb = engine.evaluate(make_spec(b.research_result_id))
    assert ra.calibration_significance_id != rb.calibration_significance_id


def test_request_name_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.2", dispersion="0.2"))
    engine = calsig_engine(ws)
    one = engine.evaluate(make_spec(calibration.research_result_id, name="one"))
    two = engine.evaluate(make_spec(calibration.research_result_id, name="two"))
    assert one.calibration_significance_id != two.calibration_significance_id


# -- fail-closed guards (CS-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(CalSigConsistencyError):
        calsig_engine(ws).evaluate(make_spec("sha256:does-not-exist"))


def test_non_calibration_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(CalSigConsistencyError):
        calsig_engine(ws).evaluate(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.2", dispersion="0.2"))
    store = ws.research_result_store
    real_bytes = store._result_path(calibration.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(CalSigConsistencyError):
        calsig_engine(ws).evaluate(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(CalSigConfigurationError):
        calsig_engine(ws).evaluate(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    calibration = make_calibration(ws, summary=calibrated(mean="1.2", dispersion="0.2"))
    result = calsig_engine(ws).evaluate(make_spec(calibration.research_result_id))
    store = ws.research_result_store

    @dataclass(frozen=True)
    class _Same:
        research_result_id: str
        payload: dict[str, object]

        def to_dict(self) -> dict[str, object]:
            return self.payload

    tampered = result.to_dict()
    tampered["boundary_kind"] = "tampered"
    with pytest.raises(FactorConsistencyError):
        store.write(
            _Same(
                research_result_id=result.research_result_id,
                payload=tampered,
            )
        )
