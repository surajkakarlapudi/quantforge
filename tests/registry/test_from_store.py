"""Building the registry offline from a populated Phase 1 ArtifactStore."""

from __future__ import annotations

from pathlib import Path

from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from openfinance.sec.artifacts import Artifact, ArtifactType
from openfinance.sec.storage import ArtifactStore

from .builders import FilingRow, SubmissionsBuilder, document_metadata

CIK = 320193
ACCESSION = "0000320193-23-000106"


def test_build_from_store_reads_all_pages(tmp_path: Path) -> None:
    artifact_store = ArtifactStore(tmp_path / "sec")
    b = SubmissionsBuilder(CIK, overflow_files=["p1.json"]).add(
        FilingRow(
            accession=ACCESSION,
            form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            primary_document="aapl-20230930.htm",
        )
    )
    primary = b.primary_artifact()
    overflow = b.overflow_artifact(
        "p1.json", [FilingRow(accession="0000320193-10-000001", form="10-K")]
    )
    for art in (primary, overflow):
        artifact_store.store(Artifact(data=art.data, metadata=art.metadata))

    reg = FilingRegistry(
        RegistryStore(tmp_path / "registry"), artifact_store=artifact_store
    )
    records = reg.build_company_from_store(CIK)
    assert {r.accession_number for r in records} == {
        ACCESSION,
        "0000320193-10-000001",
    }


def test_build_from_store_associates_documents(tmp_path: Path) -> None:
    artifact_store = ArtifactStore(tmp_path / "sec")
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession=ACCESSION,
            form="10-K",
            report_date="2023-09-30",
            primary_document="aapl-20230930.htm",
        )
    )
    primary = b.primary_artifact()
    artifact_store.store(Artifact(data=primary.data, metadata=primary.metadata))

    index_bytes = b"the-index-bytes"
    doc = document_metadata(
        CIK,
        ACCESSION,
        "index.json",
        ArtifactType.FILING_INDEX,
        content=index_bytes,
    )
    artifact_store.store(Artifact(data=index_bytes, metadata=doc))

    reg = FilingRegistry(
        RegistryStore(tmp_path / "registry"), artifact_store=artifact_store
    )
    (record,) = reg.build_company_from_store(CIK)
    assert [d.artifact_type for d in record.documents] == [ArtifactType.FILING_INDEX]


def test_build_from_store_requires_artifact_store(tmp_path: Path) -> None:
    reg = FilingRegistry(RegistryStore(tmp_path / "registry"))
    try:
        reg.build_company_from_store(CIK)
    except ValueError as exc:
        assert "artifact_store" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
