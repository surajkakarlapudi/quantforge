"""Fact serialization round-trips losslessly and deterministically."""

from __future__ import annotations

from openfinance.canonical.model import Fact as CanonicalFact
from tests.xbrl.builders import Ctx, ExplicitDim, Fact, InstanceBuilder, TypedDim, Unit

from .builders import facts

USD = Unit("usd", measures=["iso4217:USD"])


def _round_trip(fact: CanonicalFact) -> CanonicalFact:
    return CanonicalFact.from_dict(fact.to_dict())


def test_round_trip_simple_fact() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            Fact(
                "us-gaap:Cash",
                "c1",
                value="123",
                unit_ref="usd",
                scale="3",
                decimals="-3",
            )
        )
    )
    fact = facts(b)[0]
    assert _round_trip(fact) == fact


def test_round_trip_dimensional_fact() -> None:
    b = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "seg",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
                ],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Revenues", "seg", value="200", unit_ref="usd"))
    )
    fact = facts(b)[0]
    assert len(fact.dimensions) == 1
    assert _round_trip(fact) == fact


def test_round_trip_typed_dimensional_fact() -> None:
    b = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "d1",
                instant="2023-09-30",
                segment=[TypedDim("us-gaap:ScheduleAxis", "us-gaap:Tranche", "A")],
            )
        )
        .with_unit(USD)
        .with_fact(Fact("us-gaap:DebtInstrument", "d1", value="1", unit_ref="usd"))
    )
    fact = facts(b)[0]
    assert fact.dimensions[0].is_typed
    assert _round_trip(fact) == fact


def test_round_trip_nil_fact() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
    )
    fact = facts(b)[0]
    assert fact.is_nil
    assert fact.value_numeric_str is None
    assert _round_trip(fact) == fact


def test_to_dict_uses_value_numeric_key() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    d = facts(b)[0].to_dict()
    assert d["value_numeric"] == "100"
    assert "value_numeric_str" not in d
