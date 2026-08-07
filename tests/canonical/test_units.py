"""Conservative unit canonicalization: explicit mappings only, else UNKNOWN."""

from __future__ import annotations

from quantforge.canonical.units import (
    CANONICAL_UNIT_UNKNOWN,
    canonicalize_unit,
)
from quantforge.xbrl.units import RawUnit

ISO = "http://www.xbrl.org/2003/iso4217"
XBRLI = "http://www.xbrl.org/2003/instance"


def _simple(*measures: str) -> RawUnit:
    return RawUnit(unit_id="u", numerator=tuple(measures))


def _divide(numerator: str, denominator: str) -> RawUnit:
    return RawUnit(
        unit_id="u",
        numerator=(numerator,),
        denominator=(denominator,),
        is_divide=True,
    )


def test_currency_measure_maps_to_code_and_currency() -> None:
    u = canonicalize_unit(_simple(f"{{{ISO}}}USD"))
    assert u.token == "USD"
    assert u.currency == "USD"
    assert u.is_known


def test_foreign_currency_preserved() -> None:
    u = canonicalize_unit(_simple(f"{{{ISO}}}JPY"))
    assert u.token == "JPY"
    assert u.currency == "JPY"


def test_shares_measure() -> None:
    u = canonicalize_unit(_simple(f"{{{XBRLI}}}shares"))
    assert u.token == "shares"
    assert u.currency is None


def test_pure_measure_is_not_percent() -> None:
    u = canonicalize_unit(_simple(f"{{{XBRLI}}}pure"))
    assert u.token == "pure"
    assert u.currency is None


def test_currency_per_share_divide() -> None:
    u = canonicalize_unit(_divide(f"{{{ISO}}}USD", f"{{{XBRLI}}}shares"))
    assert u.token == "USD/shares"
    assert u.currency == "USD"


def test_none_unit_is_unknown() -> None:
    u = canonicalize_unit(None)
    assert u.token == CANONICAL_UNIT_UNKNOWN
    assert u.currency is None
    assert not u.is_known


def test_custom_measure_is_unknown_never_coerced() -> None:
    u = canonicalize_unit(_simple("{http://example.com/units}Widgets"))
    assert u.token == CANONICAL_UNIT_UNKNOWN
    assert u.currency is None


def test_utr_days_unit_is_unknown() -> None:
    # utr:D (days) is a real unit-registry measure we do not canonicalize yet.
    u = canonicalize_unit(_simple("{http://www.xbrl.org/2009/utr}D"))
    assert u.token == CANONICAL_UNIT_UNKNOWN


def test_multi_measure_unit_is_unknown() -> None:
    u = canonicalize_unit(_simple(f"{{{ISO}}}USD", f"{{{XBRLI}}}shares"))
    assert u.token == CANONICAL_UNIT_UNKNOWN


def test_unrecognized_divide_shape_is_unknown() -> None:
    # shares / shares is not the one recognized ratio.
    u = canonicalize_unit(_divide(f"{{{XBRLI}}}shares", f"{{{XBRLI}}}shares"))
    assert u.token == CANONICAL_UNIT_UNKNOWN
