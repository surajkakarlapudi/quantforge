"""PSR/DSR selection-bias arithmetic (§12, López de Prado)."""

from __future__ import annotations

from decimal import Decimal

from quantforge.campaign.compute import (
    MIN_VALID_TRIALS,
    campaign_statistics,
    expected_max_sharpe,
    probabilistic_sharpe,
    sharpe_dispersion,
    trial_statistics,
)
from quantforge.campaign.model import CampaignUndefinedReason, TrialStatus
from quantforge.campaign.moments import TrialMoments
from quantforge.campaign.version import default_decimal_context

CTX = default_decimal_context()


def _valid(
    sharpe: str, *, skew: str = "0", kurtosis: str = "3", n: int = 24
) -> TrialMoments:
    return TrialMoments(
        n=n,
        sharpe=Decimal(sharpe),
        skew=Decimal(skew),
        kurtosis=Decimal(kurtosis),
        reason=None,
    )


def _undef(reason: CampaignUndefinedReason, *, n: int = 1) -> TrialMoments:
    return TrialMoments(n=n, sharpe=None, skew=None, kurtosis=None, reason=reason)


# -- probabilistic_sharpe ----------------------------------------------------


def test_psr_at_own_sharpe_is_one_half() -> None:
    # SR - SR* = 0 => Phi(0) = 0.5.
    psr = probabilistic_sharpe(
        sharpe=Decimal("0.5"),
        benchmark=Decimal("0.5"),
        skew=Decimal(0),
        kurtosis=Decimal(3),
        n=24,
        context=CTX,
    )
    assert psr == Decimal("0.5")


def test_psr_increases_with_sharpe() -> None:
    def psr(sr: str) -> Decimal:
        value = probabilistic_sharpe(
            sharpe=Decimal(sr),
            benchmark=Decimal(0),
            skew=Decimal(0),
            kurtosis=Decimal(3),
            n=24,
            context=CTX,
        )
        assert value is not None
        return value

    assert psr("0.1") < psr("0.5") < psr("1.0")


def test_psr_degenerate_estimator_returns_none() -> None:
    # Synthetic moment set violating the skew-kurtosis inequality so the estimator
    # variance 1 - skew*SR + ((kurt-1)/4)*SR^2 is negative.
    psr = probabilistic_sharpe(
        sharpe=Decimal(10),
        benchmark=Decimal(0),
        skew=Decimal(1),
        kurtosis=Decimal(1),
        n=24,
        context=CTX,
    )
    assert psr is None


# -- sharpe_dispersion / expected_max_sharpe ---------------------------------


def test_sharpe_dispersion_is_population_variance() -> None:
    # [1, 3]: mean 2, pop var = ((1-2)^2 + (3-2)^2)/2 = 1.
    v = sharpe_dispersion([Decimal(1), Decimal(3)], context=CTX)
    assert v == Decimal(1)


def test_expected_max_sharpe_zero_dispersion_is_zero() -> None:
    sr0 = expected_max_sharpe(dispersion=Decimal(0), n_trials=5, context=CTX)
    assert sr0 == Decimal(0)


def test_expected_max_sharpe_grows_with_search_size() -> None:
    small = expected_max_sharpe(dispersion=Decimal(1), n_trials=2, context=CTX)
    large = expected_max_sharpe(dispersion=Decimal(1), n_trials=50, context=CTX)
    assert large > small > Decimal(0)


# -- trial_statistics --------------------------------------------------------


def test_trial_statistics_marks_valid_and_undefined() -> None:
    moments = [
        _valid("0.5"),
        _undef(CampaignUndefinedReason.ZERO_OOS_VARIANCE, n=3),
    ]
    stats = trial_statistics(moments, benchmark=Decimal(0), context=CTX)
    assert stats[0].status is TrialStatus.VALID
    assert stats[0].psr is not None
    assert stats[1].status is TrialStatus.UNDEFINED
    assert stats[1].reason is CampaignUndefinedReason.ZERO_OOS_VARIANCE
    assert stats[1].psr is None
    assert stats[1].psr_reason is CampaignUndefinedReason.ZERO_OOS_VARIANCE
    # Index tracks request order.
    assert stats[0].index == 0 and stats[1].index == 1


# -- campaign_statistics -----------------------------------------------------


def test_campaign_selects_greatest_sharpe() -> None:
    moments = [_valid("0.2"), _valid("0.9"), _valid("0.5")]
    stats = trial_statistics(moments, benchmark=Decimal(0), context=CTX)
    campaign = campaign_statistics(stats, n_trials=3, context=CTX)
    assert campaign.reason is None
    assert campaign.selected_index == 1
    assert campaign.selected_sharpe == Decimal("0.9")
    assert campaign.deflated_sharpe is not None


def test_campaign_tie_breaks_on_lowest_index() -> None:
    moments = [_valid("0.7"), _valid("0.7"), _valid("0.3")]
    stats = trial_statistics(moments, benchmark=Decimal(0), context=CTX)
    campaign = campaign_statistics(stats, n_trials=3, context=CTX)
    assert campaign.selected_index == 0


def test_campaign_too_few_valid_trials_is_undefined() -> None:
    moments = [
        _valid("0.5"),
        _undef(CampaignUndefinedReason.ZERO_OOS_VARIANCE, n=3),
    ]
    stats = trial_statistics(moments, benchmark=Decimal(0), context=CTX)
    campaign = campaign_statistics(stats, n_trials=2, context=CTX)
    assert campaign.reason is CampaignUndefinedReason.INSUFFICIENT_VALID_TRIALS
    assert campaign.selected_index is None
    assert campaign.expected_max_sharpe is None
    assert campaign.deflated_sharpe is None
    assert campaign.valid_count == 1


def test_search_size_counts_all_submitted_trials() -> None:
    # Two valid, one undefined: N (search size) is 3, deflating against a larger search.
    moments = [
        _valid("0.9"),
        _valid("0.5"),
        _undef(CampaignUndefinedReason.INSUFFICIENT_OOS_PERIODS),
    ]
    stats = trial_statistics(moments, benchmark=Decimal(0), context=CTX)
    n2 = campaign_statistics(
        trial_statistics(
            [_valid("0.9"), _valid("0.5")], benchmark=Decimal(0), context=CTX
        ),
        n_trials=2,
        context=CTX,
    )
    n3 = campaign_statistics(stats, n_trials=3, context=CTX)
    assert n3.expected_max_sharpe is not None and n2.expected_max_sharpe is not None
    # A larger search size raises the null threshold, lowering the deflated Sharpe.
    assert n3.expected_max_sharpe > n2.expected_max_sharpe


def test_min_valid_trials_is_two() -> None:
    assert MIN_VALID_TRIALS == 2
