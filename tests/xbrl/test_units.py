"""Unit extraction: simple measures, divide ratios, custom issuer units."""

from __future__ import annotations

from quantforge.xbrl.parser import ParsedInstance, parse_instance

from .builders import Ctx, Fact, InstanceBuilder, Unit, source_identity


def _parse(builder: InstanceBuilder) -> ParsedInstance:
    data = builder.to_bytes()
    return parse_instance(data, source_identity(data=data))


def test_simple_currency_unit() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    parsed = _parse(b)
    unit = parsed.units["usd"]
    assert unit.is_divide is False
    assert len(unit.numerator) == 1
    assert unit.numerator[0].endswith("}USD")
    assert unit.denominator == ()


def test_shares_unit() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("shares", measures=["xbrli:shares"]))
        .with_fact(
            Fact("us-gaap:SharesOutstanding", "c1", value="1", unit_ref="shares")
        )
    )
    parsed = _parse(b)
    assert parsed.units["shares"].numerator[0].endswith("}shares")


def test_divide_unit_preserves_numerator_and_denominator() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(
            Unit(
                "usdPerShare",
                numerator=["iso4217:USD"],
                denominator=["xbrli:shares"],
            )
        )
        .with_fact(
            Fact("us-gaap:EarningsPerShare", "c1", value="6", unit_ref="usdPerShare")
        )
    )
    parsed = _parse(b)
    unit = parsed.units["usdPerShare"]
    assert unit.is_divide is True
    assert unit.numerator[0].endswith("}USD")
    assert unit.denominator[0].endswith("}shares")
    ref = unit.unit_ref()
    assert ref.startswith("divide")


def test_custom_issuer_unit_passes_through_unknown() -> None:
    # An unknown/custom unit must remain unknown, never coerced (requirement 9).
    b = (
        InstanceBuilder()
        .with_ns("aapl", "http://apple.com/20230930")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("widget", measures=["aapl:Widgets"]))
        .with_fact(Fact("aapl:WidgetCount", "c1", value="5", unit_ref="widget"))
    )
    parsed = _parse(b)
    unit = parsed.units["widget"]
    assert unit.numerator[0] == "{http://apple.com/20230930}Widgets"


def test_unit_ref_is_prefix_independent() -> None:
    # Two builds of the same measure under different prefixes share a unit_ref.
    b1 = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
    )
    b2 = (
        InstanceBuilder()
        .with_ns("cur", "http://www.xbrl.org/2003/iso4217")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["cur:USD"]))
    )
    p1 = _parse(b1)
    p2 = _parse(b2)
    assert p1.units["usd"].unit_ref() == p2.units["usd"].unit_ref()


def test_all_units_retained_even_if_unreferenced() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_unit(Unit("shares", measures=["xbrli:shares"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="1", unit_ref="usd"))
    )
    parsed = _parse(b)
    assert set(parsed.units) == {"usd", "shares"}
