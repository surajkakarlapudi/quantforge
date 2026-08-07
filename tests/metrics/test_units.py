"""Tests for unit expectations and no-conversion compatibility (metrics.md §14).

The rules under test: a fact's unit is read (never rewritten); a family or
currency mismatch fails to ``None`` (→ ``UNIT_MISMATCH``) rather than converting;
a same-family division yields ``pure``. There is no FX, ever.
"""

from __future__ import annotations

from quantforge.metrics.units import (
    ResolvedUnit,
    UnitExpectation,
    add_sub_result_unit,
    div_result_unit,
    unit_of_fact,
)
from tests.metrics.builders import fact


def _usd() -> ResolvedUnit:
    return ResolvedUnit(UnitExpectation.MONETARY, "USD", "USD")


def _eur() -> ResolvedUnit:
    return ResolvedUnit(UnitExpectation.MONETARY, "EUR", "EUR")


def _pure() -> ResolvedUnit:
    return ResolvedUnit(UnitExpectation.PURE, None, "pure")


def _shares() -> ResolvedUnit:
    return ResolvedUnit(UnitExpectation.SHARES, None, "shares")


class TestUnitOfFact:
    def test_monetary_match(self) -> None:
        f = fact(
            accession="0000320193-23-000106",
            local_name="Assets",
            value="1",
            unit="USD",
            currency="USD",
        )
        u = unit_of_fact(f, UnitExpectation.MONETARY)
        assert u is not None and u.family is UnitExpectation.MONETARY
        assert u.currency == "USD"

    def test_monetary_requires_currency(self) -> None:
        # A "USD"-tokened fact with no currency set is not a monetary match.
        f = fact(
            accession="0000320193-23-000106",
            local_name="Assets",
            value="1",
            unit="USD",
            currency=None,
        )
        assert unit_of_fact(f, UnitExpectation.MONETARY) is None

    def test_shares_match(self) -> None:
        f = fact(
            accession="0000320193-23-000106",
            local_name="Shares",
            value="1",
            unit="shares",
            currency=None,
        )
        assert unit_of_fact(f, UnitExpectation.SHARES) is not None

    def test_pure_match(self) -> None:
        f = fact(
            accession="0000320193-23-000106",
            local_name="Ratio",
            value="1",
            unit="pure",
            currency=None,
        )
        assert unit_of_fact(f, UnitExpectation.PURE) is not None

    def test_family_mismatch_is_none(self) -> None:
        f = fact(
            accession="0000320193-23-000106",
            local_name="Shares",
            value="1",
            unit="shares",
            currency=None,
        )
        assert unit_of_fact(f, UnitExpectation.MONETARY) is None


class TestAddSub:
    def test_same_currency_ok(self) -> None:
        assert add_sub_result_unit(_usd(), _usd()) == _usd()

    def test_cross_currency_is_none(self) -> None:
        assert add_sub_result_unit(_usd(), _eur()) is None

    def test_cross_family_is_none(self) -> None:
        assert add_sub_result_unit(_usd(), _shares()) is None

    def test_same_nonmonetary_family_ok(self) -> None:
        assert add_sub_result_unit(_pure(), _pure()) == _pure()


class TestDiv:
    def test_same_currency_yields_pure(self) -> None:
        assert div_result_unit(_usd(), _usd()) == _pure()

    def test_same_family_shares_yields_pure(self) -> None:
        assert div_result_unit(_shares(), _shares()) == _pure()

    def test_cross_currency_is_none(self) -> None:
        assert div_result_unit(_usd(), _eur()) is None

    def test_cross_family_is_none(self) -> None:
        assert div_result_unit(_usd(), _shares()) is None


def test_resolved_unit_value_equality_and_hash() -> None:
    assert _usd() == _usd()
    assert hash(_usd()) == hash(_usd())
    assert _usd() != _eur()
