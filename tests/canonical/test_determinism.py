"""Determinism (requirement 14): same raw records + version → identical output."""

from __future__ import annotations

from openfinance.canonical.canonicalize import Canonicalizer
from tests.xbrl.builders import Ctx, ExplicitDim, Fact, InstanceBuilder, Unit

from .builders import parse

USD = Unit("usd", measures=["iso4217:USD"])


def _sample() -> InstanceBuilder:
    return (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
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
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "seg", value="200", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
    )


def test_repeated_canonicalization_is_identical() -> None:
    parsed = parse(_sample())
    r1 = Canonicalizer().canonicalize(parsed)
    r2 = Canonicalizer().canonicalize(parsed)
    assert [f.to_dict() for f in r1.facts] == [f.to_dict() for f in r2.facts]


def test_facts_returned_sorted_by_fact_id() -> None:
    result = Canonicalizer().canonicalize(parse(_sample()))
    ids = [f.fact_id for f in result.facts]
    assert ids == sorted(ids)


def test_source_fact_order_does_not_change_identity() -> None:
    # Reordering the facts in the source must not change any fact_id.
    forward = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Assets", "c1", value="900", unit_ref="usd"))
    )
    reverse = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Assets", "c1", value="900", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    # Same accession so filing_id matches; only fact order differs. The two
    # documents differ in bytes (raw_document_id), but the per-observation
    # fact_id — which excludes raw_document_id — must be identical.
    a = {
        f.concept.local_name: f.fact_id
        for f in Canonicalizer().canonicalize(parse(forward)).facts
    }
    b = {
        f.concept.local_name: f.fact_id
        for f in Canonicalizer().canonicalize(parse(reverse)).facts
    }
    assert a == b


def test_no_silent_drops_every_raw_fact_accounted_for() -> None:
    result = Canonicalizer().canonicalize(parse(_sample()))
    # 3 raw facts, all distinct obs_keys → 3 facts, 0 collapsed.
    assert result.raw_fact_count == 3
    assert result.fact_count == 3
    assert result.collapsed_duplicate_count == 0
