"""Pure paired-difference statistics of one strategy pair (§11, §12)."""

from __future__ import annotations

from decimal import Decimal

from quantforge.comparison.compute import (
    MIN_OVERLAP_PERIODS,
    PairComputation,
    compare_pair,
)
from quantforge.comparison.model import ComparisonStatus, ComparisonUndefinedReason
from quantforge.comparison.version import default_decimal_context

CTX = default_decimal_context()


def _pair(
    returns_i: dict[str, str],
    returns_j: dict[str, str],
    *,
    sharpe_i: str | None = "0.5",
    sharpe_j: str | None = "0.2",
) -> PairComputation:
    return compare_pair(0, 1, returns_i, returns_j, sharpe_i, sharpe_j, context=CTX)


def test_min_overlap_is_two() -> None:
    assert MIN_OVERLAP_PERIODS == 2


def test_insufficient_overlap_is_undefined() -> None:
    # Share a single date only: no paired difference can be estimated.
    comp = _pair({"d1": "0.02", "d2": "0.03"}, {"d2": "0.01", "d3": "0.04"})
    assert comp.overlap == 1
    assert comp.status is ComparisonStatus.UNDEFINED
    assert comp.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
    assert comp.mean_diff is None
    assert comp.stderr_diff is None
    assert comp.t_stat is None
    assert comp.p_value is None
    assert comp.sharpe_diff is None


def test_disjoint_dates_is_undefined() -> None:
    comp = _pair({"d1": "0.02"}, {"d2": "0.01"})
    assert comp.overlap == 0
    assert comp.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP


def test_known_pair_mean_and_overlap() -> None:
    # diffs over the two shared dates: [0.01, 0.03]; mean 0.02.
    comp = _pair({"d1": "0.03", "d2": "0.05"}, {"d1": "0.02", "d2": "0.02"})
    assert comp.status is ComparisonStatus.KNOWN
    assert comp.overlap == 2
    assert comp.mean_diff == Decimal("0.02")
    assert comp.reason is None
    assert comp.t_reason is None
    assert comp.sharpe_reason is None


def test_population_variance_and_stderr() -> None:
    # diffs [0.01, 0.03]: mean 0.02, pop var = ((-0.01)^2+(0.01)^2)/2 = 0.0001;
    # stderr = sqrt(var/n) = sqrt(0.0001/2) = sqrt(0.00005).
    comp = _pair({"d1": "0.03", "d2": "0.05"}, {"d1": "0.02", "d2": "0.02"})
    assert comp.stderr_diff is not None
    expected = CTX.sqrt(CTX.divide(Decimal("0.0001"), Decimal(2)))
    assert comp.stderr_diff == expected


def test_zero_mean_difference_gives_p_value_one() -> None:
    # diffs [0.01, -0.01]: mean 0 with positive variance ⇒ t = 0 ⇒ p = 2(1-Φ(0)) = 1.
    comp = _pair({"d1": "0.01", "d2": "0"}, {"d1": "0", "d2": "0.01"})
    assert comp.mean_diff == Decimal(0)
    assert comp.t_stat == Decimal(0)
    assert comp.p_value == Decimal(1)


def test_p_value_within_unit_interval() -> None:
    comp = _pair(
        {"d1": "0.02", "d2": "0.04", "d3": "0.06"},
        {"d1": "0.01", "d2": "0.01", "d3": "0.01"},
    )
    assert comp.p_value is not None
    assert Decimal(0) <= comp.p_value <= Decimal(1)


def test_zero_difference_variance_undefines_t_and_p() -> None:
    # A constant paired difference (both series offset by 0.03) has zero variance:
    # the mean stays KNOWN, but t / p are UNDEFINED, never a divide-by-zero.
    comp = _pair({"d1": "0.05", "d2": "0.06"}, {"d1": "0.02", "d2": "0.03"})
    assert comp.status is ComparisonStatus.KNOWN
    assert comp.mean_diff == Decimal("0.03")
    assert comp.stderr_diff == Decimal(0)
    assert comp.t_stat is None
    assert comp.p_value is None
    assert comp.t_reason is ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE
    # The Sharpe difference is unaffected by zero difference variance.
    assert comp.sharpe_diff == Decimal("0.3")
    assert comp.sharpe_reason is None


def test_undefined_leg_sharpe_undefines_only_sharpe_diff() -> None:
    comp = _pair(
        {"d1": "0.03", "d2": "0.05"},
        {"d1": "0.02", "d2": "0.02"},
        sharpe_i=None,
    )
    # The paired-difference t statistic is unaffected by an undefined leg Sharpe.
    assert comp.t_stat is not None
    assert comp.sharpe_diff is None
    assert comp.sharpe_reason is ComparisonUndefinedReason.UNDEFINED_STRATEGY_SHARPE


def test_sharpe_difference_is_directional() -> None:
    comp = _pair(
        {"d1": "0.03", "d2": "0.05"},
        {"d1": "0.02", "d2": "0.02"},
        sharpe_i="1.5",
        sharpe_j="0.4",
    )
    assert comp.sharpe_diff == Decimal("1.1")


def test_deterministic_across_calls() -> None:
    a = _pair({"d1": "0.03", "d2": "0.05"}, {"d1": "0.02", "d2": "0.02"})
    b = _pair({"d1": "0.03", "d2": "0.05"}, {"d1": "0.02", "d2": "0.02"})
    assert a == b
