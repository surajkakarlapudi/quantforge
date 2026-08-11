"""Exact-arithmetic tests for the pure second-moment compute layer (§12, FR-4).

These pin the numbers with hand-checkable synthetic series - no corpus, no store, no
engine. Every statistic is computed under the pinned decimal context and asserted
against its closed-form value, and the fail-closed UNDEFINED path (a zero-variance
factor's correlation) is proven to be a recorded reason, never a divide-by-zero.
"""

from __future__ import annotations

from decimal import Context, Decimal

import pytest

from quantforge.factorrisk.errors import FactorRiskConsistencyError
from quantforge.factorrisk.model import (
    FactorRiskStatus,
    FactorRiskUndefinedReason,
    StatValue,
)
from quantforge.factorrisk.stats import MomentEstimate, estimate_moments
from quantforge.factorrisk.version import default_decimal_context


def _ctx() -> Context:
    return default_decimal_context()


def _cov(estimate: MomentEstimate, i: int, j: int) -> str:
    for c in estimate.covariance:
        if c.i == i and c.j == j:
            assert c.value.value is not None
            return c.value.value
    raise AssertionError(f"no covariance cell ({i},{j})")


def _corr(estimate: MomentEstimate, i: int, j: int) -> StatValue:
    for c in estimate.correlation:
        if c.i == i and c.j == j:
            return c.value
    raise AssertionError(f"no correlation cell ({i},{j})")


class TestMoments:
    def test_means_and_population_volatility(self) -> None:
        # factor 0: [1,2,3] -> mean 2, pop var (1+0+1)/3 = 2/3, vol = sqrt(2/3).
        # Expected values are computed under the *same* pinned context the engine uses
        # (division/sqrt round to prec 34), so the strings match exactly.
        ctx = _ctx()
        est = estimate_moments(
            [["1", "2", "3"], ["3", "2", "1"]], periods_per_year="1", context=ctx
        )
        assert est.factors[0].mean.value == "2"
        assert est.factors[1].mean.value == "2"
        expected_vol = ctx.divide(Decimal(2), Decimal(3)).sqrt(ctx)
        assert est.factors[0].volatility.value == str(ctx.plus(expected_vol))

    def test_diagonal_covariance_is_the_population_variance(self) -> None:
        ctx = _ctx()
        est = estimate_moments(
            [["1", "2", "3"], ["3", "2", "1"]], periods_per_year="1", context=ctx
        )
        assert _cov(est, 0, 0) == str(ctx.plus(ctx.divide(Decimal(2), Decimal(3))))
        assert _cov(est, 1, 1) == str(ctx.plus(ctx.divide(Decimal(2), Decimal(3))))

    def test_perfectly_anti_correlated_series(self) -> None:
        # [1,2,3] vs [3,2,1]: covariance -2/3, correlation exactly -1.
        ctx = _ctx()
        est = estimate_moments(
            [["1", "2", "3"], ["3", "2", "1"]], periods_per_year="1", context=ctx
        )
        assert _cov(est, 0, 1) == str(ctx.plus(ctx.divide(Decimal(-2), Decimal(3))))
        assert _corr(est, 0, 1).value == "-1"

    def test_diagonal_correlation_of_positive_variance_is_one(self) -> None:
        est = estimate_moments(
            [["1", "2", "3"], ["3", "2", "1"]], periods_per_year="1", context=_ctx()
        )
        assert _corr(est, 0, 0).value == "1"
        assert _corr(est, 1, 1).value == "1"

    def test_annualization_scales_vol_by_sqrt_and_cov_linearly(self) -> None:
        # Scalings happen under the pinned context, so expected values must too.
        ctx = _ctx()
        est = estimate_moments(
            [["1", "2", "3"], ["3", "2", "1"]], periods_per_year="4", context=ctx
        )
        vol = est.factors[0].volatility.value
        annvol = est.factors[0].annualized_volatility.value
        assert vol is not None and annvol is not None
        # annualized vol = vol * sqrt(4) = 2*vol (sqrt(4) is exactly 2).
        assert Decimal(annvol) == ctx.multiply(Decimal(vol), Decimal(4).sqrt(ctx))
        # annualized covariance = per-period covariance * 4.
        for c in est.covariance:
            if c.i == 0 and c.j == 0:
                assert c.value.value is not None and c.annualized.value is not None
                assert Decimal(c.annualized.value) == ctx.multiply(
                    Decimal(c.value.value), Decimal(4)
                )


class TestZeroVariance:
    def test_constant_factor_has_zero_volatility_but_known(self) -> None:
        est = estimate_moments(
            [["1", "2", "3"], ["5", "5", "5"]], periods_per_year="1", context=_ctx()
        )
        assert est.factors[1].volatility.status is FactorRiskStatus.KNOWN
        assert est.factors[1].volatility.value == "0"

    def test_correlation_with_zero_variance_factor_is_undefined(self) -> None:
        # factor 1 is constant -> every correlation cell touching it is UNDEFINED,
        # including its own diagonal (0/0), never a divide-by-zero.
        est = estimate_moments(
            [["1", "2", "3"], ["5", "5", "5"]], periods_per_year="1", context=_ctx()
        )
        c01 = _corr(est, 0, 1)
        c11 = _corr(est, 1, 1)
        assert c01.status is FactorRiskStatus.UNDEFINED
        assert c01.reason is FactorRiskUndefinedReason.ZERO_VARIANCE
        assert c11.status is FactorRiskStatus.UNDEFINED
        assert c11.reason is FactorRiskUndefinedReason.ZERO_VARIANCE
        # The covariance cells stay KNOWN (a zero covariance is a real number).
        assert _cov(est, 0, 1) == "0"


class TestFailClosed:
    def test_ragged_series_is_refused(self) -> None:
        with pytest.raises(FactorRiskConsistencyError):
            estimate_moments(
                [["1", "2", "3"], ["1", "2"]], periods_per_year="1", context=_ctx()
            )

    def test_single_period_is_refused(self) -> None:
        with pytest.raises(FactorRiskConsistencyError):
            estimate_moments([["1"], ["2"]], periods_per_year="1", context=_ctx())

    def test_non_decimal_cell_is_refused(self) -> None:
        with pytest.raises(FactorRiskConsistencyError):
            estimate_moments(
                [["1", "oops", "3"], ["3", "2", "1"]],
                periods_per_year="1",
                context=_ctx(),
            )
