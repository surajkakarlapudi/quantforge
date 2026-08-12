"""The deterministic exact-``Decimal`` standard-normal primitive (★1)."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from quantforge.campaign.normal import (
    EULER_MASCHERONI,
    standard_normal_cdf,
    standard_normal_ppf,
)
from quantforge.campaign.version import default_decimal_context

CTX = default_decimal_context()


def _cdf(x: str) -> Decimal:
    return standard_normal_cdf(Decimal(x), context=CTX)


def _ppf(p: str) -> Decimal:
    return standard_normal_ppf(Decimal(p), context=CTX)


def test_cdf_at_zero_is_one_half() -> None:
    assert _cdf("0") == Decimal("0.5")


def test_cdf_known_values() -> None:
    # Reference values of Phi to a generous tolerance.
    assert abs(_cdf("1") - Decimal("0.8413447460685429")) < Decimal("1e-15")
    assert abs(_cdf("1.96") - Decimal("0.9750021048517796")) < Decimal("1e-15")
    assert abs(_cdf("-2") - Decimal("0.0227501319481792")) < Decimal("1e-15")


def test_cdf_symmetry() -> None:
    # Phi(-x) = 1 - Phi(x).
    for x in ("0.3", "1.1", "2.5", "4"):
        assert abs(_cdf("-" + x) - (Decimal(1) - _cdf(x))) < Decimal("1e-28")


def test_cdf_is_monotone_increasing() -> None:
    xs = ["-3", "-1", "-0.5", "0", "0.5", "1", "3"]
    values = [_cdf(x) for x in xs]
    assert all(a < b for a, b in itertools.pairwise(values))


def test_cdf_is_clamped_to_unit_interval() -> None:
    assert Decimal(0) <= _cdf("-60") <= Decimal(1)
    assert Decimal(0) <= _cdf("60") <= Decimal(1)
    assert _cdf("60") == Decimal(1)


def test_ppf_round_trips_through_cdf() -> None:
    for p in ("0.025", "0.5", "0.9", "0.975", "0.999"):
        x = _ppf(p)
        assert abs(_cdf(str(x)) - Decimal(p)) < Decimal("1e-25")


def test_ppf_known_quantile() -> None:
    assert abs(_ppf("0.975") - Decimal("1.959963984540054")) < Decimal("1e-14")


def test_ppf_rejects_p_outside_open_unit_interval() -> None:
    with pytest.raises(ValueError):
        _ppf("0")
    with pytest.raises(ValueError):
        _ppf("1")
    with pytest.raises(ValueError):
        standard_normal_ppf(Decimal("-0.1"), context=CTX)


def test_cdf_is_deterministic() -> None:
    assert _cdf("1.234567") == _cdf("1.234567")


def test_euler_mascheroni_literal() -> None:
    # A documented high-precision literal, not a truncated series.
    assert str(EULER_MASCHERONI).startswith("0.5772156649")
