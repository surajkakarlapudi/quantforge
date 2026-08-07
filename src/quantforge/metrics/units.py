"""Unit expectations and compatibility checks — no conversion, ever (§14).

A metric input declares a :class:`UnitExpectation` (monetary / shares / pure), and
the operation declares its output unit. This module compares units; it **never**
converts one (no FX, no scaling) — a currency or family mismatch fails closed to
``UNDEFINED(UNIT_MISMATCH)`` rather than fabricating a converted value ("no external
financial APIs", ``docs/metrics.md`` §14).

Unit identity reuses the Phase 4 canonical fields verbatim: a monetary fact carries
a currency token (``"USD"``) with ``currency`` set; a share count carries
``"shares"``; a dimensionless ratio carries ``"pure"``. This module only *reads*
those fields — it never rewrites a unit, mirroring the Phase 4 rule that
canonicalization is pure labelling.
"""

from __future__ import annotations

from enum import StrEnum

from quantforge.canonical.model import Fact

__all__ = [
    "ResolvedUnit",
    "UnitExpectation",
    "add_sub_result_unit",
    "div_result_unit",
    "unit_of_fact",
]


class UnitExpectation(StrEnum):
    """The unit family a metric input is expected to carry (§8, §14).

    ``MONETARY`` — a currency amount (Phase 4 ``currency`` set, token is the ISO
    code). ``SHARES`` — a ``xbrli:shares`` count. ``PURE`` — a dimensionless
    ``xbrli:pure`` ratio. A fact whose canonical unit does not match the expected
    family fails the input closed (``UNIT_MISMATCH``); we never coerce.
    """

    MONETARY = "monetary"
    SHARES = "shares"
    PURE = "pure"


class ResolvedUnit:
    """The concrete unit of a resolved value: a family plus an optional currency.

    Immutable and comparable by value. For a monetary unit ``currency`` is the ISO
    code (e.g. ``"USD"``); otherwise ``currency`` is ``None``. ``token`` is the
    canonical Phase 4 unit string, carried for provenance/display.
    """

    __slots__ = ("currency", "family", "token")

    def __init__(
        self, family: UnitExpectation, currency: str | None, token: str
    ) -> None:
        self.family = family
        self.currency = currency
        self.token = token

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResolvedUnit):
            return NotImplemented
        return (
            self.family == other.family
            and self.currency == other.currency
            and self.token == other.token
        )

    def __hash__(self) -> int:
        return hash((self.family, self.currency, self.token))

    def __repr__(self) -> str:
        return f"ResolvedUnit({self.family.value!r}, currency={self.currency!r})"


def unit_of_fact(fact: Fact, expected: UnitExpectation) -> ResolvedUnit | None:
    """Return the resolved unit of ``fact`` if it matches ``expected``, else ``None``.

    Pure comparison over the Phase 4 canonical ``unit``/``currency`` fields — never
    a conversion. ``None`` means the fact's unit is not in the expected family (the
    caller fails the input closed with ``UNIT_MISMATCH``). A monetary expectation
    requires a set ``currency``; ``shares``/``pure`` require the exact token.
    """
    if expected is UnitExpectation.MONETARY:
        if fact.currency is not None and fact.unit == fact.currency:
            return ResolvedUnit(UnitExpectation.MONETARY, fact.currency, fact.unit)
        return None
    if expected is UnitExpectation.SHARES:
        if fact.unit == "shares":
            return ResolvedUnit(UnitExpectation.SHARES, None, "shares")
        return None
    # PURE
    if fact.unit == "pure":
        return ResolvedUnit(UnitExpectation.PURE, None, "pure")
    return None


def add_sub_result_unit(left: ResolvedUnit, right: ResolvedUnit) -> ResolvedUnit | None:
    """The unit of ``left ± right``, or ``None`` if the operands are incompatible.

    Addition/subtraction require the *same* family and — for monetary operands —
    the *same* currency. A mismatch (``USD`` + ``shares``, or ``USD`` + ``EUR``)
    returns ``None`` → ``UNIT_MISMATCH``. There is no conversion: we never sum
    across currencies or families.
    """
    if left.family is not right.family:
        return None
    if left.family is UnitExpectation.MONETARY and left.currency != right.currency:
        return None
    return left


def div_result_unit(
    numerator: ResolvedUnit, denominator: ResolvedUnit
) -> ResolvedUnit | None:
    """The unit of ``numerator / denominator``, or ``None`` if incompatible.

    A ratio of two same-currency monetary operands (or two operands of the same
    non-monetary family) is dimensionless → ``pure``. A cross-currency or
    cross-family division has no defined dimensionless result here and returns
    ``None`` → ``UNIT_MISMATCH`` (we never convert). This is intentionally narrow:
    Phase 7's ratios are same-family divisions producing ``pure``.
    """
    if numerator.family is not denominator.family:
        return None
    if (
        numerator.family is UnitExpectation.MONETARY
        and numerator.currency != denominator.currency
    ):
        return None
    return ResolvedUnit(UnitExpectation.PURE, None, "pure")
