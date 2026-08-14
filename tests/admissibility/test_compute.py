"""The pure joint admissibility decision rule (§11, AD-2/AD-3/AD-4)."""

from __future__ import annotations

from decimal import Decimal

from quantforge.admissibility.compute import (
    AdmissibilityInputs,
    decide_admissibility,
)
from quantforge.admissibility.model import (
    AdmissibilityUndefinedReason,
    AdmissibilityVerdict,
    CriterionKind,
    CriterionStatus,
)
from quantforge.admissibility.version import default_decimal_context

_CTX = default_decimal_context()
_ALPHA = Decimal("0.05")


def _inputs(
    *,
    stability_stable: bool = True,
    calibration_defined: bool = True,
    calibration_p: str | None = "0.5",
    net_defined: bool = True,
    net_p: str | None = "0.01",
    net_profitable: bool = True,
) -> AdmissibilityInputs:
    return AdmissibilityInputs(
        stability_stable=stability_stable,
        calibration_defined=calibration_defined,
        calibration_p=None if calibration_p is None else Decimal(calibration_p),
        net_defined=net_defined,
        net_p=None if net_p is None else Decimal(net_p),
        net_profitable=net_profitable,
    )


# -- roll-up (AD-2) ----------------------------------------------------------


def test_all_pass_is_admissible() -> None:
    result = decide_admissibility(_inputs(), alpha=_ALPHA, context=_CTX)
    assert result.verdict is AdmissibilityVerdict.ADMISSIBLE
    assert [c.status for c in result.criteria] == [CriterionStatus.PASS] * 3
    assert [c.kind for c in result.criteria] == [
        CriterionKind.STABILITY,
        CriterionKind.CALIBRATION,
        CriterionKind.NET_OF_COST_EDGE,
    ]


def test_a_fail_is_inadmissible() -> None:
    # A calibration p at/below alpha means significantly mis-calibrated -> FAIL.
    result = decide_admissibility(
        _inputs(calibration_p="0.001"), alpha=_ALPHA, context=_CTX
    )
    assert result.verdict is AdmissibilityVerdict.INADMISSIBLE
    assert result.criteria[1].status is CriterionStatus.FAIL


def test_any_undefined_criterion_is_undefined_verdict() -> None:
    # Even with the other two passing, an undefined net edge fails closed to UNDEFINED.
    result = decide_admissibility(
        _inputs(net_defined=False, net_p=None), alpha=_ALPHA, context=_CTX
    )
    assert result.verdict is AdmissibilityVerdict.UNDEFINED
    assert result.criteria[2].status is CriterionStatus.UNDEFINED
    assert result.criteria[2].reason is (
        AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED
    )


def test_undefined_dominates_a_fail() -> None:
    # An undefined criterion outranks a decidable failure: verdict is UNDEFINED.
    result = decide_admissibility(
        _inputs(stability_stable=False, calibration_p="0.001"),
        alpha=_ALPHA,
        context=_CTX,
    )
    assert result.verdict is AdmissibilityVerdict.UNDEFINED


# -- stability criterion (AD-3) ----------------------------------------------


def test_stability_passes_iff_stable() -> None:
    passed = decide_admissibility(_inputs(), alpha=_ALPHA, context=_CTX).criteria[0]
    assert passed.status is CriterionStatus.PASS
    assert passed.detail == "stable"
    undefined = decide_admissibility(
        _inputs(stability_stable=False), alpha=_ALPHA, context=_CTX
    ).criteria[0]
    assert undefined.status is CriterionStatus.UNDEFINED
    assert undefined.reason is AdmissibilityUndefinedReason.STABILITY_UNDEFINED


# -- calibration criterion (AD-3) --------------------------------------------


def test_calibration_passes_strictly_above_alpha() -> None:
    # p == alpha is NOT > alpha, so it FAILs (significantly mis-calibrated).
    at = decide_admissibility(
        _inputs(calibration_p="0.05"), alpha=_ALPHA, context=_CTX
    ).criteria[1]
    assert at.status is CriterionStatus.FAIL
    above = decide_admissibility(
        _inputs(calibration_p="0.0500001"), alpha=_ALPHA, context=_CTX
    ).criteria[1]
    assert above.status is CriterionStatus.PASS


def test_calibration_undefined_when_not_tested() -> None:
    criterion = decide_admissibility(
        _inputs(calibration_defined=False, calibration_p=None),
        alpha=_ALPHA,
        context=_CTX,
    ).criteria[1]
    assert criterion.status is CriterionStatus.UNDEFINED
    assert criterion.reason is AdmissibilityUndefinedReason.CALIBRATION_UNDEFINED


# -- net-of-cost edge criterion (AD-3) ---------------------------------------


def test_net_edge_passes_only_when_significant_and_profitable() -> None:
    # p <= alpha AND profitable -> PASS.
    passed = decide_admissibility(
        _inputs(net_p="0.05", net_profitable=True), alpha=_ALPHA, context=_CTX
    ).criteria[2]
    assert passed.status is CriterionStatus.PASS
    # Significant but NOT profitable -> FAIL.
    not_profit = decide_admissibility(
        _inputs(net_p="0.01", net_profitable=False), alpha=_ALPHA, context=_CTX
    ).criteria[2]
    assert not_profit.status is CriterionStatus.FAIL
    # Profitable but NOT significant (p > alpha) -> FAIL.
    not_sig = decide_admissibility(
        _inputs(net_p="0.5", net_profitable=True), alpha=_ALPHA, context=_CTX
    ).criteria[2]
    assert not_sig.status is CriterionStatus.FAIL


def test_net_edge_undefined_when_not_tested() -> None:
    criterion = decide_admissibility(
        _inputs(net_defined=False, net_p=None), alpha=_ALPHA, context=_CTX
    ).criteria[2]
    assert criterion.status is CriterionStatus.UNDEFINED
    assert criterion.reason is AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED


# -- determinism -------------------------------------------------------------


def test_recompute_is_identical() -> None:
    first = decide_admissibility(
        _inputs(), alpha=_ALPHA, context=default_decimal_context()
    )
    second = decide_admissibility(
        _inputs(), alpha=_ALPHA, context=default_decimal_context()
    )
    assert first == second
