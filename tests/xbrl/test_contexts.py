"""Context extraction: instant / duration / forever, explicit + typed dims."""

from __future__ import annotations

from quantforge.xbrl.contexts import PeriodType
from quantforge.xbrl.parser import ParsedInstance, parse_instance

from .builders import Ctx, ExplicitDim, Fact, InstanceBuilder, TypedDim, source_identity


def _parse(builder: InstanceBuilder) -> ParsedInstance:
    data = builder.to_bytes()
    return parse_instance(data, source_identity(data=data))


def test_instant_context_preserved() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_unit_from(("usd", ["iso4217:USD"]))
    )
    parsed = _parse(b)
    ctx = parsed.contexts["c1"]
    assert ctx.period_type is PeriodType.INSTANT
    assert ctx.instant == "2023-09-30"
    assert ctx.start is None and ctx.end is None


def test_duration_context_preserved() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("d1", start="2022-10-01", end="2023-09-30"))
        .with_fact(Fact("us-gaap:Revenues", "d1", value="1", unit_ref="usd"))
        .with_unit_from(("usd", ["iso4217:USD"]))
    )
    parsed = _parse(b)
    ctx = parsed.contexts["d1"]
    assert ctx.period_type is PeriodType.DURATION
    assert ctx.start == "2022-10-01"
    assert ctx.end == "2023-09-30"
    assert ctx.instant is None


def test_forever_context_tolerated() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("f1", forever=True))
        .with_fact(Fact("dei:EntityRegistrantName", "f1", value="Apple Inc."))
    )
    parsed = _parse(b)
    ctx = parsed.contexts["f1"]
    assert ctx.period_type is PeriodType.FOREVER
    assert ctx.instant is None and ctx.start is None and ctx.end is None


def test_entity_identifier_and_scheme_preserved() -> None:
    b = InstanceBuilder().with_context(
        Ctx("c1", instant="2023-09-30", entity="0000320193")
    )
    parsed = _parse(b)
    ctx = parsed.contexts["c1"]
    assert ctx.entity_identifier == "0000320193"
    assert ctx.entity_scheme == "http://www.sec.gov/CIK"


def test_single_explicit_dimension() -> None:
    b = InstanceBuilder().with_context(
        Ctx(
            "seg1",
            instant="2023-09-30",
            segment=[ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember")],
        )
    )
    parsed = _parse(b)
    ctx = parsed.contexts["seg1"]
    assert len(ctx.dimensions) == 1
    dim = ctx.dimensions[0]
    assert dim.is_typed is False
    assert dim.axis.endswith("}ProductOrServiceAxis")
    assert dim.member is not None and dim.member.endswith("}ProductMember")


def test_multiple_dimensions_on_one_context() -> None:
    b = InstanceBuilder().with_context(
        Ctx(
            "seg2",
            instant="2023-09-30",
            segment=[
                ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember"),
                ExplicitDim("us-gaap:StatementGeographicalAxis", "srt:AmericasMember"),
            ],
        )
    )
    parsed = _parse(b)
    ctx = parsed.contexts["seg2"]
    assert len(ctx.dimensions) == 2
    axes = {d.axis for d in ctx.dimensions}
    assert any(a.endswith("}ProductOrServiceAxis") for a in axes)
    assert any(a.endswith("}StatementGeographicalAxis") for a in axes)


def test_typed_dimension_child_and_text() -> None:
    b = InstanceBuilder().with_context(
        Ctx(
            "typed1",
            instant="2023-09-30",
            segment=[TypedDim("us-gaap:ScheduleAxis", "us-gaap:ScheduleItem", "row-7")],
        )
    )
    parsed = _parse(b)
    dim = parsed.contexts["typed1"].dimensions[0]
    assert dim.is_typed is True
    assert dim.member is None
    assert dim.typed_child is not None and dim.typed_child.endswith("}ScheduleItem")
    assert dim.typed_text == "row-7"


def test_scenario_dimensions_also_extracted() -> None:
    b = InstanceBuilder().with_context(
        Ctx(
            "scn1",
            instant="2023-09-30",
            scenario=[ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ServiceMember")],
        )
    )
    parsed = _parse(b)
    ctx = parsed.contexts["scn1"]
    assert len(ctx.dimensions) == 1
    assert ctx.dimensions[0].member is not None
    assert ctx.dimensions[0].member.endswith("}ServiceMember")


def test_undimensioned_context_has_empty_dimensions() -> None:
    b = InstanceBuilder().with_context(Ctx("plain", instant="2023-09-30"))
    parsed = _parse(b)
    assert parsed.contexts["plain"].dimensions == ()


def test_all_contexts_retained_even_if_unreferenced() -> None:
    # A context that no fact references must still be preserved (raw structure
    # is recoverable, not just what a fact happens to point at).
    b = (
        InstanceBuilder()
        .with_context(Ctx("used", instant="2023-09-30"))
        .with_context(Ctx("orphan", instant="2022-09-30"))
        .with_fact(Fact("dei:EntityRegistrantName", "used", value="Apple Inc."))
    )
    parsed = _parse(b)
    assert set(parsed.contexts) == {"used", "orphan"}
