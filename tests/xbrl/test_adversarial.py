"""Adversarial information-loss tests (requirement 19).

Each test constructs two facts that differ in exactly ONE dimension of meaning
and asserts the parser keeps them distinct — never collapsing, deduping, or
coercing away the difference. If any of these ever collapse to a single fact or
share a ``raw_fact_id`` when they shouldn't (or fail to when they should), the
raw layer is silently losing information.
"""

from __future__ import annotations

from collections.abc import Sequence

from quantforge.xbrl.model import RawFact
from quantforge.xbrl.parser import parse_instance

from .builders import (
    Ctx,
    ExplicitDim,
    Fact,
    InstanceBuilder,
    Unit,
    source_identity,
)


def _facts(builder: InstanceBuilder) -> tuple[RawFact, ...]:
    data = builder.to_bytes()
    return parse_instance(data, source_identity(data=data)).facts


def _ids(facts: Sequence[RawFact]) -> set[str]:
    return {f.raw_fact_id for f in facts}


def test_two_facts_differing_only_by_dimension_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(
            Ctx(
                "prod",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
                ],
            )
        )
        .with_context(
            Ctx(
                "svc",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ServiceMember")
                ],
            )
        )
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Revenues", "prod", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "svc", value="100", unit_ref="usd"))
    )
    facts = _facts(b)
    assert len(facts) == 2
    assert len(_ids(facts)) == 2  # distinct identities
    assert facts[0].dimensions_hash != facts[1].dimensions_hash


def test_two_facts_differing_only_by_context_kept_distinct() -> None:
    # Same concept/unit/no-dims, but different (undimensioned) contexts.
    b = (
        InstanceBuilder()
        .with_context(Ctx("y2023", instant="2023-09-30"))
        .with_context(Ctx("y2022", instant="2022-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "y2023", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "y2022", value="100", unit_ref="usd"))
    )
    facts = _facts(b)
    assert len(facts) == 2
    assert len(_ids(facts)) == 2


def test_nil_versus_zero_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_context(Ctx("c2", instant="2022-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
        .with_fact(Fact("us-gaap:Goodwill", "c2", value="0", unit_ref="usd"))
    )
    facts = _facts(b)
    nil_fact = next(f for f in facts if f.context_ref == "c1")
    zero_fact = next(f for f in facts if f.context_ref == "c2")
    assert nil_fact.is_nil is True and nil_fact.value_raw is None
    assert zero_fact.is_nil is False and zero_fact.value_raw == "0"
    assert nil_fact.value_numeric is None
    assert zero_fact.value_numeric is not None  # a real zero, distinct from nil


def test_two_facts_differing_only_by_decimals_both_preserved() -> None:
    # Same concept/context/unit but different `decimals` precision metadata.
    # They share raw identity components (decimals is not part of raw_fact_id),
    # so the ordinal keeps them as two distinct facts — neither is dropped.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-6")
        )
        .with_fact(
            Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd", decimals="-3")
        )
    )
    facts = _facts(b)
    assert len(facts) == 2
    assert {f.decimals for f in facts} == {"-6", "-3"}
    assert len(_ids(facts)) == 2  # ordinal disambiguates; neither dropped


def test_two_facts_differing_only_by_unit_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_unit(Unit("eur", measures=["iso4217:EUR"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="eur"))
    )
    facts = _facts(b)
    assert len(facts) == 2
    assert len(_ids(facts)) == 2
    assert {f.unit_ref for f in facts} != {""}


def test_same_concept_across_periods_kept_distinct() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("q1", start="2022-10-01", end="2022-12-31"))
        .with_context(Ctx("q2", start="2023-01-01", end="2023-03-31"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Revenues", "q1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "q2", value="120", unit_ref="usd"))
    )
    facts = _facts(b)
    assert len(_ids(facts)) == 2


def test_same_period_across_filings_stays_separate() -> None:
    # Identical concept/context/unit/value, but from two different source
    # documents (e.g. an original and a restating filing). They must remain
    # separate raw facts: raw_document_id differs, so raw_fact_id differs.
    shared = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    original = shared.to_bytes()
    # A restatement differs by at least one byte (e.g. a later filing adds a
    # fact); simulate a distinct document.
    restated_builder = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Goodwill", "c1", value="5", unit_ref="usd"))
    )
    restated = restated_builder.to_bytes()

    p1 = parse_instance(
        original, source_identity(accession="0000320193-23-000106", data=original)
    )
    p2 = parse_instance(
        restated, source_identity(accession="0000320193-24-000001", data=restated)
    )
    cash1 = next(f for f in p1.facts if f.concept.endswith("}Cash"))
    cash2 = next(f for f in p2.facts if f.concept.endswith("}Cash"))
    # Same reported value & context, but different source documents.
    assert cash1.value_raw == cash2.value_raw
    assert p1.document.raw_document_id != p2.document.raw_document_id
    assert cash1.raw_fact_id != cash2.raw_fact_id  # never merged across filings


def test_genuine_duplicate_fact_preserved_via_ordinal() -> None:
    # A byte-level duplicate item (same concept/context/unit/dims, same value)
    # must NOT be silently collapsed (data-model §13 case 8).
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    facts = _facts(b)
    assert len(facts) == 2
    assert {f.ordinal for f in facts} == {0, 1}
    assert len(_ids(facts)) == 2  # distinct ids via ordinal
