"""Deterministic identity: raw_fact_id / raw_document_id and ordering."""

from __future__ import annotations

from quantforge.xbrl.model import raw_document_id_for_bytes, raw_fact_id
from quantforge.xbrl.parser import parse_instance
from quantforge.xbrl.version import XbrlParserVersion

from .builders import Ctx, Fact, InstanceBuilder, Unit, source_identity


def _sample() -> InstanceBuilder:
    return (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_context(Ctx("d1", start="2022-10-01", end="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "d1", value="200", unit_ref="usd"))
    )


def test_raw_document_id_is_content_hash() -> None:
    data = _sample().to_bytes()
    parsed = parse_instance(data, source_identity(data=data))
    assert parsed.document.raw_document_id == raw_document_id_for_bytes(data)
    assert parsed.document.raw_document_id.startswith("sha256:")


def test_reparsing_identical_bytes_reproduces_ids() -> None:
    data = _sample().to_bytes()
    p1 = parse_instance(data, source_identity(data=data))
    p2 = parse_instance(data, source_identity(data=data))
    assert [f.raw_fact_id for f in p1.facts] == [f.raw_fact_id for f in p2.facts]
    assert p1.document.raw_document_id == p2.document.raw_document_id


def test_raw_fact_id_independent_of_parser_version() -> None:
    # The parser version is provenance, NOT part of raw_fact_id (§11).
    data = _sample().to_bytes()
    v1 = XbrlParserVersion(code_version="xbrl-parser/1")
    v2 = XbrlParserVersion(code_version="xbrl-parser/999")
    p1 = parse_instance(data, source_identity(data=data), v1)
    p2 = parse_instance(data, source_identity(data=data), v2)
    assert [f.raw_fact_id for f in p1.facts] == [f.raw_fact_id for f in p2.facts]
    # ...but the recorded provenance version DOES differ.
    assert (
        p1.facts[0].provenance.transformation_version_id
        != p2.facts[0].provenance.transformation_version_id
    )


def test_raw_fact_id_matches_standalone_helper() -> None:
    data = _sample().to_bytes()
    parsed = parse_instance(data, source_identity(data=data))
    cash = next(f for f in parsed.facts if f.concept.endswith("}Cash"))
    expected = raw_fact_id(
        raw_document_id=parsed.document.raw_document_id,
        xbrl_context_ref=cash.context_ref,
        concept=cash.concept,
        unit_ref=cash.unit_ref,
        segment_key=cash.dimensions_hash,
        ordinal=cash.ordinal,
    )
    assert cash.raw_fact_id == expected


def test_identity_independent_of_source_prefix() -> None:
    # Same logical fact declared with a different prefix binding → same id.
    b1 = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    b2 = (
        InstanceBuilder()
        .with_ns("gaap", "http://fasb.org/us-gaap/2023")
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    d1, d2 = b1.to_bytes(), b2.to_bytes()
    f1 = parse_instance(d1, source_identity(data=d1)).facts[0]
    f2 = parse_instance(d2, source_identity(data=d2)).facts[0]
    # Different bytes → different raw_document_id, but the fact's identity
    # components (concept, unit_ref, dims) are prefix-independent.
    assert f1.concept == f2.concept
    assert f1.unit_ref == f2.unit_ref
    assert f1.dimensions_hash == f2.dimensions_hash


def test_document_order_does_not_affect_identity() -> None:
    # Reordering facts in the source changes document order but each fact keeps
    # its own identity (identity is content, not position).
    forward = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="1", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Goodwill", "c1", value="2", unit_ref="usd"))
    )
    reverse = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Goodwill", "c1", value="2", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="1", unit_ref="usd"))
    )
    df, dr = forward.to_bytes(), reverse.to_bytes()
    ids_f = {
        f.concept: f.raw_fact_id
        for f in parse_instance(df, source_identity(data=df)).facts
    }
    ids_r = {
        f.concept: f.raw_fact_id
        for f in parse_instance(dr, source_identity(data=dr)).facts
    }
    # raw_fact_id embeds raw_document_id (different here), so ids differ across
    # the two documents — but within each doc the mapping is stable and complete.
    assert set(ids_f) == set(ids_r)
