"""Exact-value tests for the pure leg formation + series aggregation (§12).

Every case here is small enough to solve by hand, so the assertions pin the *exact*
canonical decimal strings the compute layer must emit under the pinned context - not
approximate floats. This is where the arithmetic is proven; the engine test proves the
orchestration around it. No store, no I/O, no float, no RNG.
"""

from __future__ import annotations

from decimal import Context, Decimal

import pytest

from quantforge.factorportfolio.errors import FactorPortfolioConsistencyError
from quantforge.factorportfolio.model import (
    FactorPortfolioStatus,
    FactorPortfolioUndefinedReason,
)
from quantforge.factorportfolio.stats import (
    period_factor_return,
    series_summary,
)
from quantforge.factorportfolio.version import default_decimal_context


def _ctx() -> Context:
    return default_decimal_context()


# -- per-period leg formation: exact solves ----------------------------------


def test_two_quantiles_four_members_exact_spread() -> None:
    # Q=2, n=4: bucket = floor(i*2/4) -> {0,0,1,1}. Short = two lowest signals,
    # long = two highest. Ordered by signal ascending: a,b,c,d.
    members = [
        ("a", "1", "0.10"),
        ("b", "2", "0.20"),
        ("c", "3", "0.30"),
        ("d", "4", "0.40"),
    ]
    leg = period_factor_return(members, 2, context=_ctx())
    assert leg.short_ids == ("a", "b")
    assert leg.long_ids == ("c", "d")
    # short mean = (0.10+0.20)/2 = 0.15; long mean = (0.30+0.40)/2 = 0.35.
    assert leg.short_return.value == "0.15"
    assert leg.long_return.value == "0.35"
    # factor = long - short = 0.35 - 0.15 = 0.20.
    assert leg.factor_return.value == "0.20"


def test_high_signal_is_long_low_signal_is_short() -> None:
    # Deliberately shuffle input order + tie-break: the sort by (signal, company_id)
    # decides legs, not input order. High signal -> long (no sign flip, D-LEG).
    members = [
        ("z", "9", "0.05"),  # highest signal -> long
        ("m", "1", "0.50"),  # lowest signal -> short
        ("k", "5", "0.10"),
        ("a", "5", "0.20"),  # tie on signal with k; company_id "a" < "k"
    ]
    leg = period_factor_return(members, 2, context=_ctx())
    # ordered by (signal, cid): m(1), a(5), k(5), z(9). buckets {0,0,1,1}.
    assert leg.short_ids == ("a", "m")
    assert leg.long_ids == ("k", "z")
    # short = (0.50 + 0.20)/2 = 0.35; long = (0.10 + 0.05)/2 = 0.075.
    assert leg.short_return.value == "0.35"
    assert leg.long_return.value == "0.075"
    assert leg.factor_return.value == "-0.275"


def test_uneven_buckets_five_members_two_quantiles() -> None:
    # Q=2, n=5: bucket = floor(i*2/5) -> {0,0,0,1,1}. Short = three lowest, long = two
    # highest - the exact split the five-filer engine corpus produces.
    members = [
        ("f0", "2", "0.02"),
        ("f1", "3", "0.03"),
        ("f2", "4", "0.04"),
        ("f3", "5", "0.05"),
        ("f4", "6", "0.06"),
    ]
    leg = period_factor_return(members, 2, context=_ctx())
    assert leg.short_ids == ("f0", "f1", "f2")
    assert leg.long_ids == ("f3", "f4")
    # short = (0.02+0.03+0.04)/3 = 0.03; long = (0.05+0.06)/2 = 0.055.
    assert leg.short_return.value == "0.03"
    assert leg.long_return.value == "0.055"
    assert leg.factor_return.value == "0.025"


def test_below_leg_floor_is_insufficient_members() -> None:
    # Q=2 needs n >= 4; three members cannot guarantee both legs -> whole period
    # UNDEFINED,
    # empty membership, never a fabricated leg (P19-4).
    members = [("a", "1", "0.1"), ("b", "2", "0.2"), ("c", "3", "0.3")]
    leg = period_factor_return(members, 2, context=_ctx())
    assert leg.long_ids == ()
    assert leg.short_ids == ()
    for cell in (leg.long_return, leg.short_return, leg.factor_return):
        assert cell.status is FactorPortfolioStatus.UNDEFINED
        assert cell.reason is FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS


def test_rejects_non_decimal_signal() -> None:
    with pytest.raises(FactorPortfolioConsistencyError):
        period_factor_return(
            [
                ("a", "oops", "0.1"),
                ("b", "2", "0.2"),
                ("c", "3", "0.3"),
                ("d", "4", "0.4"),
            ],
            2,
            context=_ctx(),
        )


def test_rejects_non_finite_forward_return() -> None:
    with pytest.raises(FactorPortfolioConsistencyError):
        period_factor_return(
            [
                ("a", "1", "NaN"),
                ("b", "2", "0.2"),
                ("c", "3", "0.3"),
                ("d", "4", "0.4"),
            ],
            2,
            context=_ctx(),
        )


# -- series aggregation ------------------------------------------------------


def test_summary_two_periods_exact() -> None:
    # f = [0.02, 0.04]: cumulative = 1.02*1.04 - 1 = 0.0608; mean = 0.03;
    # population vol = sqrt(0.0001) = 0.01; sharpe (rf=0, ppy=1) = 0.03/0.01 = 3;
    # t = mean/(vol/sqrt(2)) = 3*sqrt(2) = 4.2426...; hit rate = 2/2 = 1.
    s = series_summary(
        ["0.02", "0.04"], risk_free_per_period="0", periods_per_year="1", context=_ctx()
    )
    assert s.n_valid_periods == 2
    assert s.cumulative_return.value == "0.0608"
    assert s.mean_period_return.value == "0.03"
    assert s.volatility.value == "0.01"
    assert s.annualized_sharpe.value == "3"
    assert s.mean_t_stat.value == "4.242640687119285146405066172629094"
    assert s.hit_rate.value == "1"


def test_summary_annualization_scales_sharpe() -> None:
    # Same series, periods_per_year=4: sharpe = (mean/vol)*sqrt(4) = 3*2 = 6.
    s = series_summary(
        ["0.02", "0.04"], risk_free_per_period="0", periods_per_year="4", context=_ctx()
    )
    assert s.annualized_sharpe.value == "6"


def test_summary_risk_free_shifts_sharpe() -> None:
    # rf per period = 0.03 = mean -> excess return is 0 -> sharpe is exactly 0.
    s = series_summary(
        ["0.02", "0.04"],
        risk_free_per_period="0.03",
        periods_per_year="1",
        context=_ctx(),
    )
    assert Decimal(s.annualized_sharpe.value or "nan") == 0


def test_summary_negative_mean_t_sign_follows_mean() -> None:
    s = series_summary(
        ["-0.02", "-0.04"],
        risk_free_per_period="0",
        periods_per_year="1",
        context=_ctx(),
    )
    assert s.mean_period_return.value == "-0.03"
    assert s.mean_t_stat.value is not None
    assert s.mean_t_stat.value.startswith("-")
    assert s.hit_rate.value == "0"


def test_summary_single_period_dispersion_undefined() -> None:
    # M=1: cumulative / mean / hit-rate KNOWN; dispersion cells SINGLE_VALID_PERIOD.
    s = series_summary(
        ["0.05"], risk_free_per_period="0", periods_per_year="1", context=_ctx()
    )
    assert s.n_valid_periods == 1
    assert s.cumulative_return.value == "0.05"
    assert s.mean_period_return.value == "0.05"
    assert s.hit_rate.value == "1"
    for cell in (s.volatility, s.annualized_sharpe, s.mean_t_stat):
        assert cell.status is FactorPortfolioStatus.UNDEFINED
        assert cell.reason is FactorPortfolioUndefinedReason.SINGLE_VALID_PERIOD


def test_summary_no_periods_all_undefined() -> None:
    s = series_summary(
        [], risk_free_per_period="0", periods_per_year="1", context=_ctx()
    )
    assert s.n_valid_periods == 0
    for cell in (
        s.cumulative_return,
        s.mean_period_return,
        s.volatility,
        s.annualized_sharpe,
        s.mean_t_stat,
        s.hit_rate,
    ):
        assert cell.status is FactorPortfolioStatus.UNDEFINED
        assert cell.reason is FactorPortfolioUndefinedReason.NO_VALID_PERIODS


def test_summary_zero_variance_sharpe_and_t_undefined() -> None:
    # Identical per-period returns -> zero population dispersion: volatility is a KNOWN
    # 0,
    # sharpe / t are ZERO_RETURN_VARIANCE (never a divide-by-zero).
    s = series_summary(
        ["0.03", "0.03"],
        risk_free_per_period="0",
        periods_per_year="1",
        context=_ctx(),
    )
    assert s.n_valid_periods == 2
    assert s.mean_period_return.value == "0.03"
    assert s.volatility.status is FactorPortfolioStatus.KNOWN
    assert Decimal(s.volatility.value or "nan") == 0
    assert s.hit_rate.value == "1"
    for cell in (s.annualized_sharpe, s.mean_t_stat):
        assert cell.status is FactorPortfolioStatus.UNDEFINED
        assert cell.reason is FactorPortfolioUndefinedReason.ZERO_RETURN_VARIANCE


def test_summary_is_deterministic_across_repeated_calls() -> None:
    a = series_summary(
        ["0.02", "0.04", "0.05"],
        risk_free_per_period="0",
        periods_per_year="1",
        context=_ctx(),
    )
    b = series_summary(
        ["0.02", "0.04", "0.05"],
        risk_free_per_period="0",
        periods_per_year="1",
        context=_ctx(),
    )
    assert a == b
