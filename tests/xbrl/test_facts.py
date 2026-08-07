"""Fact extraction: numeric, non-numeric, nil, decimals, scale, sign, custom."""

from __future__ import annotations

from decimal import Decimal

from quantforge.xbrl.model import RawFact
from quantforge.xbrl.parser import ParsedInstance, parse_instance

from .builders import Ctx, Fact, InstanceBuilder, Unit, source_identity


def _parse(builder: InstanceBuilder) -> ParsedInstance:
    data = builder.to_bytes()
    return parse_instance(data, source_identity(data=data))


def _fact(parsed: ParsedInstance, concept_suffix: str) -> RawFact:
    for f in parsed.facts:
        if f.concept.endswith(concept_suffix):
            return f
    raise AssertionError(f"no fact ending {concept_suffix!r}")


def test_numeric_fact_raw_and_parsed_value() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="29965000000", unit_ref="usd"))
    )
    f = _fact(_parse(b), "}Cash")
    assert f.value_raw == "29965000000"
    assert f.value_numeric == Decimal("29965000000")
    assert f.is_nil is False


def test_non_numeric_fact_has_no_unit() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", forever=True))
        .with_fact(Fact("dei:EntityRegistrantName", "c1", value="Apple Inc."))
    )
    f = _fact(_parse(b), "}EntityRegistrantName")
    assert f.value_raw == "Apple Inc."
    assert f.unit_ref == ""
    # A textual value does not parse as a number: value_numeric is None, raw kept.
    assert f.value_numeric is None


def test_nil_fact_is_not_zero() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
    )
    f = _fact(_parse(b), "}Goodwill")
    assert f.is_nil is True
    assert f.value_raw is None
    assert f.value_numeric is None  # never coerced to Decimal(0)


def test_decimals_preserved_verbatim() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-6")
        )
    )
    assert _fact(_parse(b), "}Cash").decimals == "-6"


def test_decimals_inf_preserved() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("shares", measures=["xbrli:shares"]))
        .with_fact(
            Fact("us-gaap:Shares", "c1", value="100", unit_ref="shares", decimals="INF")
        )
    )
    assert _fact(_parse(b), "}Shares").decimals == "INF"


def test_scale_preserved_and_value_not_prescaled() -> None:
    # scale metadata is retained; value_raw is NOT multiplied out (no normalization).
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", scale="6"))
    )
    f = _fact(_parse(b), "}Cash")
    assert f.scale == "6"
    assert f.value_raw == "100"  # unchanged; scale not applied


def test_sign_attribute_preserved() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", start="2022-10-01", end="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(
            Fact("us-gaap:NetIncomeLoss", "c1", value="99", unit_ref="usd", sign="-")
        )
    )
    f = _fact(_parse(b), "}NetIncomeLoss")
    assert f.sign == "-"
    assert f.value_raw == "99"  # sign not folded into the raw value


def test_custom_issuer_concept_extracted() -> None:
    b = (
        InstanceBuilder()
        .with_ns("aapl", "http://apple.com/20230930")
        .with_context(Ctx("c1", start="2022-10-01", end="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("aapl:CustomMetric", "c1", value="42", unit_ref="usd"))
    )
    f = _fact(_parse(b), "}CustomMetric")
    assert f.concept == "{http://apple.com/20230930}CustomMetric"
    assert f.value_raw == "42"


def test_concept_qname_is_clark_notation() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", forever=True))
        .with_fact(Fact("dei:EntityRegistrantName", "c1", value="Apple Inc."))
    )
    f = _fact(_parse(b), "EntityRegistrantName")
    assert f.concept == "{http://xbrl.sec.gov/dei/2023}EntityRegistrantName"


def test_negative_and_decimal_values_parse_exactly() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", start="2022-10-01", end="2023-09-30"))
        .with_unit(
            Unit(
                "usdPerShare",
                numerator=["iso4217:USD"],
                denominator=["xbrli:shares"],
            )
        )
        .with_fact(Fact("us-gaap:Eps", "c1", value="-6.13", unit_ref="usdPerShare"))
    )
    f = _fact(_parse(b), "}Eps")
    assert f.value_numeric == Decimal("-6.13")
    assert f.value_raw == "-6.13"
