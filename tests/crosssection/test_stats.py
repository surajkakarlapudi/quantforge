"""Exact-value tests for the pure per-date OLS + Fama-MacBeth aggregation (§6).

Every case here is small enough to solve by hand, so the assertions pin the *exact*
canonical decimal strings the compute layer must emit under the pinned context - not
approximate floats. This is where the arithmetic is proven; the engine test proves the
orchestration around it. No store, no I/O, no float, no RNG.
"""

from __future__ import annotations

from decimal import Context

import pytest

from quantforge.crosssection.errors import CrossSectionConsistencyError
from quantforge.crosssection.model import (
    CrossSectionStatus,
    CrossSectionUndefinedReason,
)
from quantforge.crosssection.stats import (
    coefficient_labels,
    cross_section_ols,
    premium_estimate,
)
from quantforge.crosssection.version import default_decimal_context


def _ctx() -> Context:
    return default_decimal_context()


# -- coefficient labelling ---------------------------------------------------


def test_coefficient_labels_with_intercept() -> None:
    assert coefficient_labels(2, include_intercept=True) == (
        "alpha",
        "factor_1",
        "factor_2",
    )


def test_coefficient_labels_without_intercept() -> None:
    assert coefficient_labels(2, include_intercept=False) == ("factor_1", "factor_2")


def test_coefficient_labels_no_factors_intercept_only() -> None:
    assert coefficient_labels(0, include_intercept=True) == ("alpha",)


# -- per-date OLS: exact solves ----------------------------------------------


def test_ols_no_intercept_single_factor_exact() -> None:
    # x=[2,4], y=[0.1,0.05]; no intercept -> beta = sum(xy)/sum(x^2)
    #   = (0.2 + 0.2) / (4 + 16) = 0.4/20 = 0.02.
    estimate = cross_section_ols(
        [["2", "4"]], ["0.1", "0.05"], include_intercept=False, context=_ctx()
    )
    assert not estimate.singular
    labels = [label for label, _ in estimate.coefficients]
    assert labels == ["factor_1"]
    ((_, cell),) = estimate.coefficients
    assert cell.status is CrossSectionStatus.KNOWN
    assert cell.value == "0.02"
    # R^2 = 1 - SSR/SST is negative for this (no-intercept) fit: exactly -2.6.
    assert estimate.r_squared.value == "-2.6"


def test_ols_exact_line_with_intercept_r2_one() -> None:
    # y = 1 + 2x exactly through (0,1),(1,3),(2,5): alpha=1, factor_1=2, R^2=1.
    estimate = cross_section_ols(
        [["0", "1", "2"]], ["1", "3", "5"], include_intercept=True, context=_ctx()
    )
    assert not estimate.singular
    assert dict((label, cell.value) for label, cell in estimate.coefficients) == {
        "alpha": "1",
        "factor_1": "2",
    }
    assert estimate.r_squared.value == "1"


def test_ols_constant_signal_with_intercept_is_singular() -> None:
    # A constant signal column duplicates the intercept -> X^T X not positive-definite.
    estimate = cross_section_ols(
        [["5", "5", "5"]], ["1", "2", "3"], include_intercept=True, context=_ctx()
    )
    assert estimate.singular
    for _, cell in estimate.coefficients:
        assert cell.status is CrossSectionStatus.UNDEFINED
        assert cell.reason is CrossSectionUndefinedReason.SINGULAR_DESIGN
    assert estimate.r_squared.reason is CrossSectionUndefinedReason.SINGULAR_DESIGN


def test_ols_zero_variance_regressand_keeps_coefficients_known() -> None:
    # Constant y with a varying signal: SST = 0 -> R^2 is ZERO_VARIANCE, but the
    # coefficients are still KNOWN (alpha=4, factor_1=0 - the exact best fit).
    estimate = cross_section_ols(
        [["1", "2", "3"]], ["4", "4", "4"], include_intercept=True, context=_ctx()
    )
    assert not estimate.singular
    assert dict((label, cell.value) for label, cell in estimate.coefficients) == {
        "alpha": "4",
        "factor_1": "0",
    }
    assert estimate.r_squared.status is CrossSectionStatus.UNDEFINED
    assert estimate.r_squared.reason is CrossSectionUndefinedReason.ZERO_VARIANCE


def test_ols_two_collinear_signals_with_intercept_is_singular() -> None:
    # factor_2 = 2 * factor_1 exactly -> the two signal columns are collinear.
    estimate = cross_section_ols(
        [["1", "2", "3"], ["2", "4", "6"]],
        ["1", "2", "1"],
        include_intercept=True,
        context=_ctx(),
    )
    assert estimate.singular


def test_ols_rejects_non_decimal_signal() -> None:
    with pytest.raises(CrossSectionConsistencyError):
        cross_section_ols(
            [["1", "oops"]], ["0.1", "0.2"], include_intercept=False, context=_ctx()
        )


def test_ols_rejects_non_finite_return() -> None:
    with pytest.raises(CrossSectionConsistencyError):
        cross_section_ols(
            [["1", "2"]], ["0.1", "NaN"], include_intercept=False, context=_ctx()
        )


# -- Fama-MacBeth aggregation ------------------------------------------------


def test_premium_two_dates_exact() -> None:
    # mean of [0.02, 0.04] = 0.03; population std = 0.01; se = 0.01/sqrt(2);
    # t = 0.03 / se = 3 * sqrt(2) = 4.2426406871...
    mean, se, t, n = premium_estimate("factor_1", ["0.02", "0.04"], context=_ctx())
    assert n == 2
    assert mean.value == "0.03"
    assert se.value == "0.007071067811865475244008443621048491"
    assert t.value == "4.242640687119285146405066172629094"


def test_premium_single_date_mean_known_dispersion_undefined() -> None:
    mean, se, t, n = premium_estimate("factor_1", ["0.02"], context=_ctx())
    assert n == 1
    assert mean.value == "0.02"
    assert se.reason is CrossSectionUndefinedReason.SINGLE_VALID_DATE
    assert t.reason is CrossSectionUndefinedReason.SINGLE_VALID_DATE


def test_premium_no_dates_all_undefined() -> None:
    mean, se, t, n = premium_estimate("factor_1", [], context=_ctx())
    assert n == 0
    for cell in (mean, se, t):
        assert cell.status is CrossSectionStatus.UNDEFINED
        assert cell.reason is CrossSectionUndefinedReason.NO_VALID_DATES


def test_premium_zero_dispersion_t_stat_undefined() -> None:
    # Identical per-date coefficients -> zero population dispersion: se is a KNOWN 0,
    # t is ZERO_COEFFICIENT_VARIANCE (never a divide-by-zero).
    mean, se, t, n = premium_estimate("factor_1", ["0.03", "0.03"], context=_ctx())
    assert n == 2
    assert mean.value == "0.03"
    assert se.status is CrossSectionStatus.KNOWN
    assert se.value == "0E+31"
    assert t.status is CrossSectionStatus.UNDEFINED
    assert t.reason is CrossSectionUndefinedReason.ZERO_COEFFICIENT_VARIANCE


def test_premium_negative_mean_t_sign_follows_mean() -> None:
    mean, _se, t, n = premium_estimate("factor_1", ["-0.02", "-0.04"], context=_ctx())
    assert n == 2
    assert mean.value == "-0.03"
    assert t.value is not None
    assert t.value.startswith("-")


def test_stats_are_deterministic_across_repeated_calls() -> None:
    first = premium_estimate("factor_1", ["0.02", "0.04", "0.05"], context=_ctx())
    second = premium_estimate("factor_1", ["0.02", "0.04", "0.05"], context=_ctx())
    assert [c.to_dict() for c in first[:3]] == [c.to_dict() for c in second[:3]]
