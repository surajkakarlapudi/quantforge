"""Per-trial OOS excess-return moment estimation (§12)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.campaign.errors import CampaignConsistencyError
from quantforge.campaign.model import CampaignUndefinedReason
from quantforge.campaign.moments import trial_moments
from quantforge.campaign.version import default_decimal_context

CTX = default_decimal_context()


def test_hand_computed_moments() -> None:
    # Series [1,2,3], rf=0: mean=2, pop var=2/3, sigma=sqrt(2/3),
    # sharpe=2/sigma=sqrt(6), skew=0 (symmetric), non-excess kurtosis=1.5.
    m = trial_moments(("1", "2", "3"), risk_free_per_period="0", context=CTX)
    assert m.reason is None
    assert m.n == 3
    assert m.sharpe is not None and abs(m.sharpe - Decimal(6).sqrt(CTX)) < Decimal(
        "1e-30"
    )
    assert m.skew is not None and m.skew == Decimal(0)
    assert m.kurtosis is not None and abs(m.kurtosis - Decimal("1.5")) < Decimal(
        "1e-30"
    )


def test_risk_free_shifts_the_mean() -> None:
    # Subtracting a constant rf shifts excess-return mean but not the dispersion.
    base = trial_moments(
        ("0.05", "0.05", "0.10"), risk_free_per_period="0", context=CTX
    )
    shifted = trial_moments(
        ("0.05", "0.05", "0.10"), risk_free_per_period="0.05", context=CTX
    )
    assert base.sharpe is not None and shifted.sharpe is not None
    # Excess mean drops, so the Sharpe drops.
    assert shifted.sharpe < base.sharpe


def test_single_period_is_insufficient() -> None:
    m = trial_moments(("0.01",), risk_free_per_period="0", context=CTX)
    assert m.reason is CampaignUndefinedReason.INSUFFICIENT_OOS_PERIODS
    assert m.sharpe is None and m.skew is None and m.kurtosis is None


def test_empty_series_is_insufficient() -> None:
    m = trial_moments((), risk_free_per_period="0", context=CTX)
    assert m.reason is CampaignUndefinedReason.INSUFFICIENT_OOS_PERIODS


def test_zero_variance_series_is_undefined() -> None:
    m = trial_moments(("0.03", "0.03", "0.03"), risk_free_per_period="0", context=CTX)
    assert m.reason is CampaignUndefinedReason.ZERO_OOS_VARIANCE
    assert m.sharpe is None


def test_deterministic() -> None:
    a = trial_moments(("0.01", "-0.02", "0.03"), risk_free_per_period="0", context=CTX)
    b = trial_moments(("0.01", "-0.02", "0.03"), risk_free_per_period="0", context=CTX)
    assert a == b


def test_non_decimal_return_fails_closed() -> None:
    with pytest.raises(CampaignConsistencyError):
        trial_moments(("0.01", "oops"), risk_free_per_period="0", context=CTX)


def test_non_finite_return_fails_closed() -> None:
    with pytest.raises(CampaignConsistencyError):
        trial_moments(("0.01", "Infinity"), risk_free_per_period="0", context=CTX)
