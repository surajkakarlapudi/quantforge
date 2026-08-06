"""Provenance (requirement 13): unbroken chain Fact → RawFact → source."""

from __future__ import annotations

from tests.xbrl.builders import Ctx, Fact, InstanceBuilder, Unit, source_identity

from .builders import canonicalize

USD = Unit("usd", measures=["iso4217:USD"])


def test_fact_carries_complete_lineage() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    data = b.to_bytes()
    identity = source_identity(data=data)
    fact = canonicalize(b).facts[0]
    prov = fact.provenance

    # Chain: Fact → raw_fact_id → raw_document_id → source artifact hash → SEC.
    assert prov.raw_fact_id in prov.raw_fact_ids
    assert prov.raw_document_id.startswith("sha256:")
    assert prov.source_artifact_sha256 == identity.source_artifact_sha256
    assert prov.source_url == identity.source_url
    assert prov.source_document_name == identity.source_document_name
    # Phase 2 identity is preserved verbatim.
    assert prov.filing_id == identity.filing_id
    assert prov.accession == identity.accession
    assert prov.company_id == identity.company_id
    # The normalizer version that produced the Fact is recorded.
    assert prov.transformation_version_id.startswith("sha256:")
    assert fact.transformation_version_id == prov.transformation_version_id


def test_fact_fields_mirror_provenance_identity() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
    )
    fact = canonicalize(b).facts[0]
    assert fact.filing_id == fact.provenance.filing_id
    assert fact.company_id == fact.provenance.company_id


def test_raw_lexical_value_survives_on_fact() -> None:
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
    fact = canonicalize(b).facts[0]
    # Canonical value is folded; raw is retained verbatim (invariant 26).
    assert fact.value_numeric_str == "123000"
    assert fact.raw_value == "123"
    assert fact.raw_scale == "3"
    assert fact.raw_decimals == "-3"
