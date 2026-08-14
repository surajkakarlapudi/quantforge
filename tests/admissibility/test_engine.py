"""End-to-end strategy admissibility through the engine (§6, AD-1..AD-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.admissibility.errors import (
    AdmissibilityConfigurationError,
    AdmissibilityConsistencyError,
)
from quantforge.admissibility.model import (
    AdmissibilityVerdict,
    CriterionKind,
    CriterionStatus,
)
from quantforge.admissibility.result import StrategyAdmissibility
from quantforge.factors.errors import FactorConsistencyError
from quantforge.netcostsig.model import EdgeDirection
from tests.admissibility.builders import (
    admissibility_engine,
    admissible_sources,
    make_calibration_significance,
    make_net_significance,
    make_spec,
    make_stability,
    workspace,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-source :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-source", "id": self.research_result_id}


# -- happy path (AD-2/AD-3) --------------------------------------------------


def test_happy_path_is_admissible(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    stab, cal, net = admissible_sources(ws)
    result = admissibility_engine(ws).evaluate(make_spec(stab, cal, net))

    assert isinstance(result, StrategyAdmissibility)
    assert result.verdict is AdmissibilityVerdict.ADMISSIBLE
    assert [c.kind for c in result.summary.criteria] == [
        CriterionKind.STABILITY,
        CriterionKind.CALIBRATION,
        CriterionKind.NET_OF_COST_EDGE,
    ]
    assert [c.status for c in result.summary.criteria] == [CriterionStatus.PASS] * 3


def test_all_three_sources_are_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.source_stability_id == s.research_result_id
    assert result.source_stability_result_hash == s.result_hash
    assert result.source_calibration_significance_id == c.research_result_id
    assert result.source_calibration_result_hash == c.result_hash
    assert result.source_net_of_cost_significance_id == n.research_result_id
    assert result.source_net_of_cost_result_hash == n.result_hash


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    stab, cal, net = admissible_sources(ws)
    result = admissibility_engine(ws).evaluate(make_spec(stab, cal, net))
    assert result.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- inadmissible / undefined verdicts (AD-2) --------------------------------


def test_significant_miscalibration_is_inadmissible(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.001")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.verdict is AdmissibilityVerdict.INADMISSIBLE
    assert result.summary.failed_criteria == (CriterionKind.CALIBRATION,)


def test_unprofitable_edge_is_inadmissible(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(
        ws, tested=True, p_value="0.01", direction=EdgeDirection.UNPROFITABLE
    )
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.verdict is AdmissibilityVerdict.INADMISSIBLE
    assert result.summary.failed_criteria == (CriterionKind.NET_OF_COST_EDGE,)


def test_undefined_stability_seals_undefined_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=False)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.verdict is AdmissibilityVerdict.UNDEFINED
    assert result.summary.undefined_criteria == (CriterionKind.STABILITY,)


def test_undefined_calibration_seals_undefined_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=False)
    n = make_net_significance(ws, tested=True, p_value="0.01")
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.verdict is AdmissibilityVerdict.UNDEFINED
    assert result.summary.undefined_criteria == (CriterionKind.CALIBRATION,)


def test_undefined_net_edge_seals_undefined_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=False)
    result = admissibility_engine(ws).evaluate(
        make_spec(s.research_result_id, c.research_result_id, n.research_result_id)
    )
    assert result.verdict is AdmissibilityVerdict.UNDEFINED
    assert result.summary.undefined_criteria == (CriterionKind.NET_OF_COST_EDGE,)


# -- alpha sensitivity -------------------------------------------------------


def test_alpha_can_flip_the_verdict(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    # Calibration p = 0.03: not significant at alpha 0.01 (PASS), significant at 0.05.
    c = make_calibration_significance(ws, tested=True, p_value="0.03")
    n = make_net_significance(ws, tested=True, p_value="0.005")
    engine = admissibility_engine(ws)
    lenient = engine.evaluate(
        make_spec(
            s.research_result_id,
            c.research_result_id,
            n.research_result_id,
            alpha="0.01",
        )
    )
    strict = engine.evaluate(
        make_spec(
            s.research_result_id,
            c.research_result_id,
            n.research_result_id,
            alpha="0.05",
        )
    )
    assert lenient.verdict is AdmissibilityVerdict.ADMISSIBLE
    assert strict.verdict is AdmissibilityVerdict.INADMISSIBLE
    assert lenient.admissibility_id != strict.admissibility_id


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    stab, cal, net = admissible_sources(ws)
    engine = admissibility_engine(ws)
    first = engine.evaluate(make_spec(stab, cal, net))
    second = engine.evaluate(make_spec(stab, cal, net))
    assert first.admissibility_id == second.admissibility_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, StrategyAdmissibility.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


# -- identity sensitivity (AD-1) ---------------------------------------------


def test_different_source_answer_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    n = make_net_significance(ws, tested=True, p_value="0.01")
    a = make_calibration_significance(ws, tested=True, p_value="0.5", name="a")
    b = make_calibration_significance(ws, tested=True, p_value="0.6", name="b")
    engine = admissibility_engine(ws)
    ra = engine.evaluate(
        make_spec(s.research_result_id, a.research_result_id, n.research_result_id)
    )
    rb = engine.evaluate(
        make_spec(s.research_result_id, b.research_result_id, n.research_result_id)
    )
    assert ra.admissibility_id != rb.admissibility_id


def test_request_name_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    stab, cal, net = admissible_sources(ws)
    engine = admissibility_engine(ws)
    one = engine.evaluate(make_spec(stab, cal, net, name="one"))
    two = engine.evaluate(make_spec(stab, cal, net, name="two"))
    assert one.admissibility_id != two.admissibility_id


# -- fail-closed guards (AD-1) -----------------------------------------------


def test_absent_stability_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec("sha256:missing", c.research_result_id, n.research_result_id)
        )


def test_absent_calibration_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    n = make_net_significance(ws, tested=True, p_value="0.01")
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec(s.research_result_id, "sha256:missing", n.research_result_id)
        )


def test_absent_net_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec(s.research_result_id, c.research_result_id, "sha256:missing")
        )


def test_wrong_typed_source_fails_closed(tmp_path: Path) -> None:
    # A calibration id that actually points at a stability record fails to decode.
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    n = make_net_significance(ws, tested=True, p_value="0.01")
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec(
                s.research_result_id,
                s.research_result_id,  # a stability id where a calibration is required
                n.research_result_id,
            )
        )


def test_non_source_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec(
                dummy.research_result_id, c.research_result_id, n.research_result_id
            )
        )


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    s = make_stability(ws, stable=True)
    c = make_calibration_significance(ws, tested=True, p_value="0.5")
    n = make_net_significance(ws, tested=True, p_value="0.01")
    store = ws.research_result_store
    real_bytes = store._result_path(s.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(AdmissibilityConsistencyError):
        admissibility_engine(ws).evaluate(
            make_spec(fake_id, c.research_result_id, n.research_result_id)
        )


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(AdmissibilityConfigurationError):
        admissibility_engine(ws).evaluate(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    stab, cal, net = admissible_sources(ws)
    result = admissibility_engine(ws).evaluate(make_spec(stab, cal, net))
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
