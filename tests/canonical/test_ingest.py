"""Offline canonicalization façade: raw store → canonical store (requirement 19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.canonical.ingest import CanonicalizationIngestor
from quantforge.canonical.store import CanonicalFactStore
from quantforge.xbrl.store import RawXbrlStore
from quantforge.xbrl.version import XbrlParserVersion
from tests.xbrl.builders import Ctx, Fact, InstanceBuilder, Unit

from .builders import parse

USD = Unit("usd", measures=["iso4217:USD"])


def _populate_raw(
    store: RawXbrlStore,
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    value: str = "100",
) -> str:
    # The entity identifier and value vary by filer so two filers produce
    # distinct instance bytes (and thus distinct content-addressed documents).
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30", entity=f"{cik:010d}"))
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value=value, unit_ref="usd"))
    )
    parsed = parse(b, cik=cik, accession=accession)
    store.write_instance(parsed, XbrlParserVersion().transformation_version_id)
    return parsed.document.raw_document_id


def test_canonicalize_document_persists_facts(tmp_path: Path) -> None:
    raw = RawXbrlStore(tmp_path / "raw")
    canonical = CanonicalFactStore(tmp_path / "canonical")
    doc_id = _populate_raw(raw)

    ingestor = CanonicalizationIngestor(raw, canonical)
    result = ingestor.canonicalize_document(doc_id)

    assert result.fact_count == 1
    assert result.raw_fact_count == 1
    assert canonical.has_instance(doc_id)
    read = canonical.read_instance(doc_id)
    assert read is not None and len(read) == 1


def test_canonicalize_missing_document_raises(tmp_path: Path) -> None:
    raw = RawXbrlStore(tmp_path / "raw")
    canonical = CanonicalFactStore(tmp_path / "canonical")
    ingestor = CanonicalizationIngestor(raw, canonical)
    with pytest.raises(KeyError):
        ingestor.canonicalize_document("sha256:absent")


def test_canonicalize_all(tmp_path: Path) -> None:
    raw = RawXbrlStore(tmp_path / "raw")
    canonical = CanonicalFactStore(tmp_path / "canonical")
    _populate_raw(raw, cik=320193, accession="0000320193-23-000106", value="100")
    _populate_raw(raw, cik=1318605, accession="0001318605-23-000001", value="200")

    ingestor = CanonicalizationIngestor(raw, canonical)
    results = ingestor.canonicalize_all()
    assert len(results) == 2
    doc_ids = [r.raw_document_id for r in results]
    assert doc_ids == sorted(doc_ids)  # deterministic order


def test_canonicalize_company_filters_by_cik(tmp_path: Path) -> None:
    raw = RawXbrlStore(tmp_path / "raw")
    canonical = CanonicalFactStore(tmp_path / "canonical")
    apple = _populate_raw(
        raw, cik=320193, accession="0000320193-23-000106", value="100"
    )
    _populate_raw(raw, cik=1318605, accession="0001318605-23-000001", value="200")

    ingestor = CanonicalizationIngestor(raw, canonical)
    results = ingestor.canonicalize_company(320193)
    assert len(results) == 1
    assert results[0].raw_document_id == apple


def test_ingest_is_deterministic_across_runs(tmp_path: Path) -> None:
    raw = RawXbrlStore(tmp_path / "raw")
    canonical = CanonicalFactStore(tmp_path / "canonical")
    doc_id = _populate_raw(raw)
    ingestor = CanonicalizationIngestor(raw, canonical)

    ingestor.canonicalize_document(doc_id)
    path = canonical._instance_path(doc_id)
    first = path.read_bytes()
    ingestor.canonicalize_document(doc_id)
    assert path.read_bytes() == first
