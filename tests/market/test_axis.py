"""The explicit, content-addressed price date axis (section 17)."""

from __future__ import annotations

import pytest

from quantforge.market.axis import PriceAxis
from quantforge.market.errors import MarketPolicyConfigurationError


def test_explicit_axis_sorts_and_dedups_identity() -> None:
    a = PriceAxis.of(["2020-01-03", "2020-01-02"])
    b = PriceAxis.of(["2020-01-02", "2020-01-03"])
    # Cosmetic input order does not change identity.
    assert a.axis_id == b.axis_id
    assert a.dates == ("2020-01-02", "2020-01-03")


def test_empty_axis_fails_closed() -> None:
    with pytest.raises(MarketPolicyConfigurationError):
        PriceAxis.of([])


def test_duplicate_date_fails_closed() -> None:
    with pytest.raises(MarketPolicyConfigurationError):
        PriceAxis.of(["2020-01-02", "2020-01-02"])


def test_invalid_date_fails_closed() -> None:
    with pytest.raises(MarketPolicyConfigurationError):
        PriceAxis.of(["not-a-date"])


def test_business_daily_excludes_weekends_and_holidays() -> None:
    # 2020-01-01 is New Year's Day (holiday); 2020-01-04/05 are the weekend.
    axis = PriceAxis.business_daily("2020-01-01", "2020-01-06")
    assert "2020-01-01" not in axis.dates
    assert "2020-01-04" not in axis.dates
    assert "2020-01-06" in axis.dates


def test_business_daily_bounds_must_be_ordered() -> None:
    with pytest.raises(MarketPolicyConfigurationError):
        PriceAxis.business_daily("2020-01-06", "2020-01-01")


def test_axis_id_differs_by_kind() -> None:
    explicit = PriceAxis.of(["2020-01-02", "2020-01-03"])
    generated = PriceAxis.business_daily("2020-01-02", "2020-01-03")
    assert explicit.axis_id != generated.axis_id
