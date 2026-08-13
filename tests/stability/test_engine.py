"""End-to-end walk-forward turnover & stability through the engine (§6, WS-1..6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.factors.errors import FactorConsistencyError
from quantforge.stability.errors import (
    StabilityConfigurationError,
    StabilityConsistencyError,
)
from quantforge.stability.model import (
    StabilityExcludedReason,
    StabilityStatus,
    StabilityUndefinedReason,
    StatStatus,
)
from quantforge.stability.result import WalkForwardStability
from quantforge.walkforward.result import WindowResult
from tests.stability.builders import (
    make_spec,
    make_walk_forward,
    non_known_weight_window,
    realized_window,
    stability_engine,
    undefined_window,
    workspace,
    wrong_length_window,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``WalkForwardEvaluation`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-walk-forward", "id": self.research_result_id}


def _stable_windows() -> list[WindowResult]:
    """Three REALIZED windows: two realized-adjacent transitions (STABLE, WS-3)."""
    return [
        realized_window(0, ["0.5", "0.5"]),
        realized_window(1, ["0.5", "-0.5"]),
        realized_window(2, ["-0.5", "0.5"]),
    ]


# -- happy path (WS-2/WS-4/WS-5) ---------------------------------------------


def test_happy_path_computes_full_family(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))

    assert isinstance(result, WalkForwardStability)
    assert result.stability_status is StabilityStatus.STABLE
    assert result.coverage.to_dict() == {
        "n_windows": 3,
        "n_realized": 3,
        "n_excluded": 0,
        "n_transitions": 2,
    }
    # Per-window metrics map back to source order by index.
    assert [w.index for w in result.windows] == [0, 1, 2]
    w0 = result.windows[0]
    assert w0.gross_leverage == "1.0"
    assert w0.concentration_hhi == "0.50"
    assert w0.max_abs_weight == "0.5"
    assert w0.effective_breadth.value == "2"
    # The first window has no realized predecessor: turnover is UNDEFINED, not zero.
    assert w0.turnover_from_prev.status is StatStatus.UNDEFINED
    assert (
        w0.turnover_from_prev.reason
        is StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
    )
    assert result.windows[1].turnover_from_prev.value == "0.5"
    assert result.windows[2].turnover_from_prev.value == "1.0"


def test_happy_path_aggregates(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    s = stability_engine(ws).analyze(make_spec(wf.research_result_id)).summary
    assert s.mean_turnover.value == "0.75"
    assert s.turnover_dispersion.value == "0.25"
    assert s.max_turnover.value == "1.0"
    assert s.min_turnover.value == "0.5"
    assert s.mean_gross_leverage.value == "1.0"
    assert s.max_gross_leverage.value == "1.0"
    assert s.mean_concentration_hhi.value == "0.50"
    assert s.mean_effective_breadth.value == "2"
    assert s.stability_status is StabilityStatus.STABLE
    assert s.status_reason is None


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))
    assert result.source_walk_forward_id == wf.research_result_id
    assert result.source_result_hash == wf.result_hash


# -- window classification / gaps (WS-2/WS-3) --------------------------------


def test_undefined_window_is_excluded_not_imputed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[
            realized_window(0, ["0.5", "0.5"]),
            undefined_window(1, 2),
            realized_window(2, ["1.0", "0.0"]),
            realized_window(3, ["0.0", "1.0"]),
        ],
        n_factors=2,
    )
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))

    assert result.coverage.n_windows == 4
    assert result.coverage.n_realized == 3
    assert result.coverage.n_excluded == 1
    assert [e.index for e in result.excluded] == [1]
    assert result.excluded[0].reason is StabilityExcludedReason.WINDOW_UNDEFINED
    # The window straddling the gap has no adjacent book: turnover UNDEFINED, never
    # fabricated across the gap (WS-3).
    straddle = next(w for w in result.windows if w.index == 2)
    assert straddle.turnover_from_prev.status is StatStatus.UNDEFINED
    assert (
        straddle.turnover_from_prev.reason
        is StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
    )
    # Only windows 2->3 form a realized-adjacent transition: T=1 < floor 2.
    assert result.coverage.n_transitions == 1
    assert result.stability_status is StabilityStatus.UNDEFINED


def test_no_realized_adjacent_transitions_yields_no_transitions(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[
            realized_window(0, ["0.5", "0.5"]),
            undefined_window(1, 2),
            realized_window(2, ["1.0", "0.0"]),
        ],
        n_factors=2,
    )
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))
    assert result.coverage.n_transitions == 0
    # Every turnover aggregate is UNDEFINED (NO_TRANSITIONS), never a divide-by-zero.
    s = result.summary
    for cell in (
        s.mean_turnover,
        s.turnover_dispersion,
        s.max_turnover,
        s.min_turnover,
    ):
        assert cell.status is StatStatus.UNDEFINED
        assert cell.reason is StabilityUndefinedReason.NO_TRANSITIONS
    # The concentration family is still defined over the two realized windows.
    assert s.mean_gross_leverage.status is StatStatus.KNOWN
    assert s.stability_status is StabilityStatus.UNDEFINED
    assert s.status_reason is StabilityUndefinedReason.INSUFFICIENT_TRANSITIONS


def test_below_floor_still_seals(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[
            realized_window(0, ["0.5", "0.5"]),
            realized_window(1, ["1.0", "0.0"]),
        ],
        n_factors=2,
    )
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))
    # One transition < floor of 2: the record still seals, status UNDEFINED (WS-3).
    assert result.coverage.n_transitions == 1
    assert result.stability_status is StabilityStatus.UNDEFINED
    assert (
        result.summary.status_reason
        is StabilityUndefinedReason.INSUFFICIENT_TRANSITIONS
    )
    # The single turnover value still seals.
    assert result.windows[1].turnover_from_prev.value == "0.5"


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))
    assert result.boundary_kind == wf.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- corrupt-source guards (WS-4) --------------------------------------------


def test_wrong_length_weight_vector_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[realized_window(0, ["0.5", "0.5"]), wrong_length_window(1, ["1.0"])],
        n_factors=2,
    )
    with pytest.raises(StabilityConsistencyError):
        stability_engine(ws).analyze(make_spec(wf.research_result_id))


def test_non_known_weight_cell_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws,
        windows=[realized_window(0, ["0.5", "0.5"]), non_known_weight_window(1, 2)],
        n_factors=2,
    )
    with pytest.raises(StabilityConsistencyError):
        stability_engine(ws).analyze(make_spec(wf.research_result_id))


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    engine = stability_engine(ws)
    first = engine.analyze(make_spec(wf.research_result_id))
    second = engine.analyze(make_spec(wf.research_result_id))
    assert first.walk_forward_stability_id == second.walk_forward_stability_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, WalkForwardStability.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


# -- identity sensitivity ----------------------------------------------------


def test_different_source_answer_changes_stability_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_walk_forward(
        ws, windows=[realized_window(0, ["0.5", "0.5"])], n_factors=2, name="a"
    )
    b = make_walk_forward(
        ws, windows=[realized_window(0, ["0.6", "0.4"])], n_factors=2, name="b"
    )
    engine = stability_engine(ws)
    ra = engine.analyze(make_spec(a.research_result_id))
    rb = engine.analyze(make_spec(b.research_result_id))
    assert ra.walk_forward_stability_id != rb.walk_forward_stability_id


def test_request_name_changes_stability_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    wf = make_walk_forward(ws, windows=_stable_windows(), n_factors=2)
    engine = stability_engine(ws)
    one = engine.analyze(make_spec(wf.research_result_id, name="one"))
    two = engine.analyze(make_spec(wf.research_result_id, name="two"))
    assert one.walk_forward_stability_id != two.walk_forward_stability_id


# -- fail-closed guards (WS-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(StabilityConsistencyError):
        stability_engine(ws).analyze(make_spec("sha256:does-not-exist"))


def test_non_walk_forward_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(StabilityConsistencyError):
        stability_engine(ws).analyze(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    # A record stored at a path whose id disagrees with its content is inconsistent.
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, ["0.5", "0.5"])], n_factors=2
    )
    store = ws.research_result_store
    real_bytes = store._result_path(wf.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(StabilityConsistencyError):
        stability_engine(ws).analyze(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(StabilityConfigurationError):
        stability_engine(ws).analyze(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    # A differing payload under an existing stability id fails closed at the store.
    ws = workspace(tmp_path)
    wf = make_walk_forward(
        ws, windows=[realized_window(0, ["0.5", "0.5"])], n_factors=2
    )
    result = stability_engine(ws).analyze(make_spec(wf.research_result_id))
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
