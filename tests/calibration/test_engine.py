"""End-to-end risk-forecast calibration through the engine (§6, RC-1..RC-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.calibration.errors import (
    CalibrationConfigurationError,
    CalibrationConsistencyError,
)
from quantforge.calibration.model import (
    CalibrationExcludedReason,
    CalibrationStatus,
    StatStatus,
)
from quantforge.calibration.result import RiskForecastCalibration
from quantforge.factors.errors import FactorConsistencyError
from tests.calibration.builders import (
    calibration_engine,
    make_spec,
    make_walk_forward,
    predicted_undefined_window,
    realized_window,
    single_period_window,
    undefined_window,
    workspace,
    zero_predicted_window,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``WalkForwardEvaluation`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-walk-forward", "id": self.research_result_id}


# -- happy path (RC-2/RC-4/RC-5) ---------------------------------------------


def test_happy_path_calibrates_full_family(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, "4", "1"), realized_window(1, "1", "4")]
    )
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))

    assert isinstance(result, RiskForecastCalibration)
    assert result.calibration_status is CalibrationStatus.CALIBRATED
    assert result.coverage.n_windows == 2
    assert result.coverage.n_calibratable == 2
    assert result.coverage.n_excluded == 0
    assert result.summary.mean_variance_ratio.value == "2.125"
    assert result.summary.aggregate_bias.value == "1"
    assert result.summary.variance_ratio_dispersion.value == "1.875"
    # Per-window ratios map back to source order by index.
    assert [w.index for w in result.windows] == [0, 1]
    assert result.windows[0].variance_ratio == "0.25"


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, "4", "1"), realized_window(1, "1", "4")]
    )
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
    assert result.source_walk_forward_id == wf.research_result_id
    assert result.source_result_hash == wf.result_hash


# -- window classification / exclusion (RC-3) --------------------------------


def test_every_exclusion_reason_is_classified(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[
            realized_window(0, "4", "1"),  # calibratable
            undefined_window(1),  # WINDOW_UNDEFINED
            single_period_window(2, "2"),  # SINGLE_VALID_PERIOD
            zero_predicted_window(3, "1"),  # ZERO_PREDICTED_VARIANCE
            predicted_undefined_window(4, "1"),  # PREDICTED_VARIANCE_UNDEFINED
        ],
    )
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))

    assert result.coverage.n_windows == 5
    assert result.coverage.n_calibratable == 1
    assert result.coverage.n_excluded == 4
    by_index = {e.index: e.reason for e in result.excluded}
    assert by_index == {
        1: CalibrationExcludedReason.WINDOW_UNDEFINED,
        2: CalibrationExcludedReason.SINGLE_VALID_PERIOD,
        3: CalibrationExcludedReason.ZERO_PREDICTED_VARIANCE,
        4: CalibrationExcludedReason.PREDICTED_VARIANCE_UNDEFINED,
    }
    # Below the floor of 2: the record still seals, status UNDEFINED (RC-3/RC-5).
    assert result.calibration_status is CalibrationStatus.UNDEFINED


def test_all_undefined_family_is_empty(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=[undefined_window(0), undefined_window(1)])
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
    assert result.coverage.n_calibratable == 0
    assert result.windows == ()
    assert result.calibration_status is CalibrationStatus.UNDEFINED
    # Every aggregate is UNDEFINED, never a divide-by-zero.
    assert result.summary.mean_variance_ratio.status is StatStatus.UNDEFINED


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, "4", "1"), realized_window(1, "1", "4")]
    )
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
    assert result.boundary_kind == wf.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, "4", "1"), realized_window(1, "1", "4")]
    )
    engine = calibration_engine(ws)
    first = engine.calibrate(make_spec(wf.research_result_id))
    second = engine.calibrate(make_spec(wf.research_result_id))
    assert first.risk_forecast_calibration_id == second.risk_forecast_calibration_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, RiskForecastCalibration.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


def test_write_once_conflict_is_impossible_for_same_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=[realized_window(0, "4", "1")])
    a = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
    b = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
    assert a.to_dict() == b.to_dict()


# -- identity sensitivity ----------------------------------------------------


def test_different_source_answer_changes_calibration_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_walk_forward(ws, windows=[realized_window(0, "4", "1")], name="a")
    b = make_walk_forward(ws, windows=[realized_window(0, "4", "2")], name="b")
    engine = calibration_engine(ws)
    ra = engine.calibrate(make_spec(a.research_result_id))
    rb = engine.calibrate(make_spec(b.research_result_id))
    assert ra.risk_forecast_calibration_id != rb.risk_forecast_calibration_id


def test_request_name_changes_calibration_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=[realized_window(0, "4", "1")])
    engine = calibration_engine(ws)
    one = engine.calibrate(make_spec(wf.research_result_id, name="one"))
    two = engine.calibrate(make_spec(wf.research_result_id, name="two"))
    assert one.risk_forecast_calibration_id != two.risk_forecast_calibration_id


# -- fail-closed guards (RC-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(CalibrationConsistencyError):
        calibration_engine(ws).calibrate(make_spec("sha256:does-not-exist"))


def test_non_walk_forward_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(CalibrationConsistencyError):
        calibration_engine(ws).calibrate(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    # A record stored at a path whose id disagrees with its content is inconsistent.
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=[realized_window(0, "4", "1")])
    store = ws.research_result_store
    real_bytes = store._result_path(wf.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(CalibrationConsistencyError):
        calibration_engine(ws).calibrate(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(CalibrationConfigurationError):
        calibration_engine(ws).calibrate(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    # A differing payload under an existing calibration id fails closed at the store.
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=[realized_window(0, "4", "1")])
    result = calibration_engine(ws).calibrate(make_spec(wf.research_result_id))
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
