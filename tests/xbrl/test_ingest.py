"""Offline ingestion from stored Phase 1 artifacts (requirement 16, 20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.sec.artifacts import ArtifactType
from openfinance.sec.storage import ArtifactStore
from openfinance.xbrl.errors import XbrlError
from openfinance.xbrl.ingest import (
    XbrlIngestor,
    source_identity_from_metadata,
)
from openfinance.xbrl.store import RawXbrlStore

from .builders import (
    Ctx,
    Fact,
    InstanceBuilder,
    Unit,
    instance_artifact,
)


def _instance_bytes() -> bytes:
    return (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .to_bytes()
    )


def _stores(tmp_path: Path) -> tuple[ArtifactStore, RawXbrlStore]:
    return ArtifactStore(tmp_path / "artifacts"), RawXbrlStore(tmp_path / "raw")


def test_ingest_artifact_offline(tmp_path: Path) -> None:
    data = _instance_bytes()
    artifact = instance_artifact(data)
    artifacts, raw = _stores(tmp_path)
    artifacts.store(artifact)

    ingestor = XbrlIngestor(artifacts, raw)
    result = ingestor.ingest_artifact(artifact.metadata)

    assert result.fact_count == 1
    assert raw.has_instance(result.raw_document_id)
    # The parsed instance is recoverable from the derived store.
    read = raw.read_instance(result.raw_document_id)
    assert read is not None


def test_ingest_reads_exact_bytes_from_store(tmp_path: Path) -> None:
    data = _instance_bytes()
    artifact = instance_artifact(data)
    artifacts, raw = _stores(tmp_path)
    artifacts.store(artifact)
    ingestor = XbrlIngestor(artifacts, raw)
    result = ingestor.ingest_artifact(artifact.metadata)
    # raw_document_id is the content hash of the exact stored bytes.
    from openfinance.xbrl.model import raw_document_id_for_bytes

    assert result.raw_document_id == raw_document_id_for_bytes(data)


def test_ingest_rejects_non_instance_artifact(tmp_path: Path) -> None:
    data = _instance_bytes()
    artifact = instance_artifact(data)
    # Mutate the metadata to a non-instance type.
    from dataclasses import replace

    bad_meta = replace(artifact.metadata, artifact_type=ArtifactType.FILING_DOCUMENT)
    artifacts, raw = _stores(tmp_path)
    ingestor = XbrlIngestor(artifacts, raw)
    with pytest.raises(XbrlError, match="not an XBRL instance"):
        ingestor.ingest_artifact(bad_meta)


def test_source_identity_requires_accession(tmp_path: Path) -> None:
    from dataclasses import replace

    data = _instance_bytes()
    meta = instance_artifact(data).metadata
    with pytest.raises(XbrlError, match="no accession"):
        source_identity_from_metadata(replace(meta, accession=None))


def test_source_identity_requires_cik() -> None:
    from dataclasses import replace

    data = _instance_bytes()
    meta = instance_artifact(data).metadata
    with pytest.raises(XbrlError, match="no CIK"):
        source_identity_from_metadata(replace(meta, cik=None))


def test_ingest_company_from_store_filters_by_cik(tmp_path: Path) -> None:
    artifacts, raw = _stores(tmp_path)
    # Two filers; only 320193 should be ingested.
    data_a = _instance_bytes()
    a = instance_artifact(data_a, cik=320193, accession="0000320193-23-000106")
    data_b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-12-31"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="5", unit_ref="usd"))
        .to_bytes()
    )
    b = instance_artifact(data_b, cik=1318605, accession="0001318605-23-000001")
    artifacts.store(a)
    artifacts.store(b)

    ingestor = XbrlIngestor(artifacts, raw)
    results = ingestor.ingest_company_from_store(320193)
    assert len(results) == 1
    assert results[0].raw_document_id.startswith("sha256:")


def test_ingest_is_deterministic_across_runs(tmp_path: Path) -> None:
    data = _instance_bytes()
    artifact = instance_artifact(data)
    artifacts, raw = _stores(tmp_path)
    artifacts.store(artifact)
    ingestor = XbrlIngestor(artifacts, raw)
    r1 = ingestor.ingest_artifact(artifact.metadata)
    path = raw._document_path(r1.raw_document_id)
    first = path.read_bytes()
    r2 = ingestor.ingest_artifact(artifact.metadata)
    assert r1.raw_document_id == r2.raw_document_id
    assert path.read_bytes() == first
