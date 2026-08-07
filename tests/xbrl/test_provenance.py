"""Provenance completeness: every fact traces back to its filing + artifact."""

from __future__ import annotations

from quantforge.xbrl.parser import ParsedInstance, SourceIdentity, parse_instance

from .builders import Ctx, Fact, InstanceBuilder, Unit, source_identity


def _parse() -> tuple[ParsedInstance, SourceIdentity]:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    data = b.to_bytes()
    identity = source_identity(data=data)
    return parse_instance(data, identity), identity


def test_document_carries_full_provenance() -> None:
    parsed, identity = _parse()
    doc = parsed.document
    assert doc.filing_id == identity.filing_id
    assert doc.accession == identity.accession
    assert doc.company_id == identity.company_id
    assert doc.source_artifact_sha256 == identity.source_artifact_sha256
    assert doc.source_url == identity.source_url
    assert doc.source_document_name == identity.source_document_name


def test_fact_provenance_links_to_filing_and_artifact() -> None:
    parsed, identity = _parse()
    prov = parsed.facts[0].provenance
    assert prov.filing_id == identity.filing_id
    assert prov.accession == identity.accession
    assert prov.company_id == identity.company_id
    assert prov.source_artifact_sha256 == identity.source_artifact_sha256
    assert prov.source_url == identity.source_url
    assert prov.source_document_name == identity.source_document_name
    assert prov.transformation_version_id.startswith("sha256:")


def test_fact_links_to_its_raw_document() -> None:
    parsed, _ = _parse()
    assert parsed.facts[0].raw_document_id == parsed.document.raw_document_id


def test_provenance_roundtrips_through_to_dict() -> None:
    from quantforge.xbrl.model import RawFact

    parsed, _ = _parse()
    fact = parsed.facts[0]
    restored = RawFact.from_dict(fact.to_dict())
    assert restored == fact
