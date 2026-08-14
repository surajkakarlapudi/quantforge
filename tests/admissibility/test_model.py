"""The fail-closed admissibility vocabulary and criterion cell round-trip (§9)."""

from __future__ import annotations

import pytest

from quantforge.admissibility.model import (
    AdmissibilityUndefinedReason,
    AdmissibilityVerdict,
    Criterion,
    CriterionKind,
    CriterionStatus,
)


def test_passed_criterion_round_trips() -> None:
    cell = Criterion.passed(CriterionKind.STABILITY, detail="stable")
    assert cell.status is CriterionStatus.PASS
    assert cell.to_dict() == {
        "kind": "stability",
        "status": "pass",
        "detail": "stable",
    }
    assert Criterion.from_dict(cell.to_dict()) == cell


def test_failed_criterion_round_trips() -> None:
    cell = Criterion.failed(CriterionKind.CALIBRATION, detail="0.001")
    assert cell.status is CriterionStatus.FAIL
    assert cell.to_dict() == {
        "kind": "calibration",
        "status": "fail",
        "detail": "0.001",
    }
    assert Criterion.from_dict(cell.to_dict()) == cell


def test_undefined_criterion_round_trips() -> None:
    cell = Criterion.undefined(
        CriterionKind.NET_OF_COST_EDGE,
        AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED,
    )
    assert cell.status is CriterionStatus.UNDEFINED
    assert cell.to_dict() == {
        "kind": "net_of_cost_edge",
        "status": "undefined",
        "reason": "net_of_cost_undefined",
    }
    assert Criterion.from_dict(cell.to_dict()) == cell


def test_undefined_criterion_requires_a_reason() -> None:
    with pytest.raises(ValueError):
        Criterion(kind=CriterionKind.STABILITY, status=CriterionStatus.UNDEFINED)


def test_pass_criterion_rejects_a_reason() -> None:
    with pytest.raises(ValueError):
        Criterion(
            kind=CriterionKind.STABILITY,
            status=CriterionStatus.PASS,
            reason=AdmissibilityUndefinedReason.STABILITY_UNDEFINED,
        )


def test_from_dict_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        Criterion.from_dict({"kind": "bogus", "status": "pass"})


def test_from_dict_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        Criterion.from_dict({"kind": "stability", "status": "bogus"})


def test_from_dict_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        Criterion.from_dict(
            {"kind": "stability", "status": "undefined", "reason": "bogus"}
        )


def test_closed_vocabularies() -> None:
    assert {v.value for v in AdmissibilityVerdict} == {
        "admissible",
        "inadmissible",
        "undefined",
    }
    assert {k.value for k in CriterionKind} == {
        "stability",
        "calibration",
        "net_of_cost_edge",
    }
    assert {s.value for s in CriterionStatus} == {"pass", "fail", "undefined"}
    assert {r.value for r in AdmissibilityUndefinedReason} == {
        "stability_undefined",
        "calibration_undefined",
        "net_of_cost_undefined",
    }
