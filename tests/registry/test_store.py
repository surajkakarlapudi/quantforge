"""RegistryStore round-trip and FilingRecord serialization fidelity."""

from __future__ import annotations

from pathlib import Path

from openfinance.registry.model import (
    AmendmentLinkConfidence,
    DocumentReference,
    FilingProvenance,
    FilingRecord,
    make_filing_record,
)
from openfinance.registry.store import RegistryStore
from openfinance.sec.artifacts import ArtifactType

CIK = 320193
_PROV = FilingProvenance(
    source_artifact_sha256="abc123",
    source_artifact_type=ArtifactType.SUBMISSIONS,
    source_url="https://data.sec.gov/submissions/CIK0000320193.json",
    transformation_version_id="sha256:tv",
)


def _record() -> FilingRecord:
    base = make_filing_record(
        cik=CIK,
        accession_original="0000320193-24-000005",
        form="10-K/A",
        filing_date="2024-02-01",
        report_date="2023-09-30",
        acceptance_timestamp_utc="2024-02-01T18:00:00.000Z",
        primary_document="aapl.htm",
        primary_document_description="10-K/A",
        provenance=_PROV,
    )
    with_docs = base.with_documents(
        (
            DocumentReference(
                artifact_sha256="doc1",
                artifact_type=ArtifactType.FILING_INDEX,
                source_url="https://www.sec.gov/…/index.json",
            ),
        )
    )
    return with_docs.with_amendment(
        "0000320193-23-000106",
        AmendmentLinkConfidence.DERIVED_HIGH_CONFIDENCE,
    )


def test_record_dict_roundtrip() -> None:
    record = _record()
    restored = FilingRecord.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.amends_accession == "0000320193-23-000106"
    assert restored.amendment_link_confidence == (
        AmendmentLinkConfidence.DERIVED_HIGH_CONFIDENCE
    )
    assert restored.documents[0].artifact_type is ArtifactType.FILING_INDEX


def test_store_write_read_roundtrip(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path)
    store.write_company("cik:0000320193", "sha256:tv", [_record()])
    read = store.read_company("cik:0000320193")
    assert len(read) == 1
    assert read[0].to_dict() == _record().to_dict()


def test_store_filename_derived_from_cik(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path)
    store.write_company("cik:0000320193", "sha256:tv", [_record()])
    assert (tmp_path / "filings" / "cik-0000320193.json").exists()


def test_missing_company_reads_empty(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path)
    assert store.read_company("cik:0000000001") == []
    assert store.has_company("cik:0000000001") is False
