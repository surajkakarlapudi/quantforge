"""The pure one-sample net-of-cost-significance math (§11, NS-3/NS-4/NS-5)."""

from __future__ import annotations

from decimal import Decimal

from quantforge.netcostsig.compute import (
    MeasuredNetSeries,
)
from quantforge.netcostsig.compute import (
    test_net_of_cost_significance as run_significance,
)
from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStatus,
    StatStatus,
)
from quantforge.netcostsig.version import default_decimal_context

_CTX = default_decimal_context()
_NULL = Decimal("0")


def _series(mean: str, volatility: str, n: int) -> MeasuredNetSeries:
    return MeasuredNetSeries(
        net_mean=Decimal(mean),
        net_volatility=Decimal(volatility),
        n_periods=n,
    )


# -- happy path (NS-4/NS-5) --------------------------------------------------


def test_known_statistics_and_direction() -> None:
    # se = 0.05/sqrt(100) = 0.005; t = 0.01/0.005 = 2.0; p = 1-Phi(2) ~ 0.02275.
    result = run_significance(
        _series("0.01", "0.05", 100), null_mean=_NULL, context=_CTX
    )
    assert result.significance_status is SignificanceStatus.TESTED
    assert result.status_reason is None
    assert result.n_periods == 100
    assert result.edge_direction is EdgeDirection.PROFITABLE
    assert result.net_mean.value == "0.01"
    assert result.standard_error.value == "0.005"
    assert result.t_statistic.value == "2"
    p = Decimal(result.p_value.value or "-1")
    assert Decimal("0.022") < p < Decimal("0.023")


def test_sharpe_times_sqrt_n_identity() -> None:
    # t = (m/s) * sqrt(n): here (0.01/0.05)*sqrt(100) = 0.2*10 = 2.
    result = run_significance(
        _series("0.01", "0.05", 100), null_mean=_NULL, context=_CTX
    )
    assert Decimal(result.t_statistic.value or "-1") == Decimal("2")


def test_unprofitable_direction_and_upper_tailed_p() -> None:
    # A negative mean is UNPROFITABLE; the upper-tailed p exceeds 0.5 (edge not real).
    result = run_significance(
        _series("-0.01", "0.05", 100), null_mean=_NULL, context=_CTX
    )
    assert result.edge_direction is EdgeDirection.UNPROFITABLE
    assert result.t_statistic.value == "-2"
    p = Decimal(result.p_value.value or "-1")
    assert p > Decimal("0.97")


def test_flat_direction_when_mean_equals_null() -> None:
    result = run_significance(_series("0", "0.05", 100), null_mean=_NULL, context=_CTX)
    assert result.edge_direction is EdgeDirection.FLAT
    assert Decimal(result.t_statistic.value or "-1") == Decimal("0")
    # p = 1 - Phi(0) = 0.5.
    assert Decimal(result.p_value.value or "-1") == Decimal("0.5")


def test_more_periods_shrink_the_p_value() -> None:
    # Same per-period edge, quadrupled sample: t doubles (2 -> 4), so p falls sharply.
    short = run_significance(
        _series("0.01", "0.05", 100), null_mean=_NULL, context=_CTX
    )
    long = run_significance(_series("0.01", "0.05", 400), null_mean=_NULL, context=_CTX)
    assert long.t_statistic.value == "4"
    assert Decimal(long.p_value.value or "9") < Decimal(short.p_value.value or "-9")


# -- fail-closed: zero volatility (NS-3) -------------------------------------


def test_zero_volatility_leaves_mean_known_but_t_p_undefined() -> None:
    result = run_significance(_series("0.01", "0", 100), null_mean=_NULL, context=_CTX)
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.status_reason is NetCostSigUndefinedReason.ZERO_NET_VOLATILITY
    # Mean + direction stay KNOWN; standard error is a known zero; t / p undefined.
    assert result.net_mean.value == "0.01"
    assert result.edge_direction is EdgeDirection.PROFITABLE
    assert result.standard_error.value == "0"
    assert result.t_statistic.status is StatStatus.UNDEFINED
    assert result.p_value.status is StatStatus.UNDEFINED
    assert result.t_statistic.reason is NetCostSigUndefinedReason.ZERO_NET_VOLATILITY


# -- fail-closed: absent series (NS-2) ---------------------------------------


def test_absent_series_is_all_undefined() -> None:
    result = run_significance(None, null_mean=_NULL, context=_CTX)
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.status_reason is NetCostSigUndefinedReason.SOURCE_NOT_MEASURED
    assert result.n_periods == 0
    assert result.edge_direction is None
    for cell in (
        result.net_mean,
        result.standard_error,
        result.t_statistic,
        result.p_value,
    ):
        assert cell.status is StatStatus.UNDEFINED
        assert cell.reason is NetCostSigUndefinedReason.SOURCE_NOT_MEASURED


# -- p-value clamp & determinism ---------------------------------------------


def test_p_value_stays_within_unit_interval() -> None:
    # A large positive t drives p toward 0; a large negative t toward 1 - never outside.
    high = run_significance(_series("0.05", "0.01", 100), null_mean=_NULL, context=_CTX)
    low = run_significance(_series("-0.05", "0.01", 100), null_mean=_NULL, context=_CTX)
    for result in (high, low):
        p = Decimal(result.p_value.value or "-1")
        assert Decimal("0") <= p <= Decimal("1")


def test_recompute_is_identical() -> None:
    first = run_significance(
        _series("0.01", "0.05", 100),
        null_mean=_NULL,
        context=default_decimal_context(),
    )
    second = run_significance(
        _series("0.01", "0.05", 100),
        null_mean=_NULL,
        context=default_decimal_context(),
    )
    assert first == second
