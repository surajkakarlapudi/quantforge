"""Deterministic builders for registry tests.

These construct in-memory submissions artifacts and acquisition metadata that
mirror the real EDGAR shapes (columnar ``filings.recent`` on the primary page,
top-level columns on overflow pages) without any network access. Everything is
a pure function of its inputs, so tests are deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from quantforge.registry.submissions import SubmissionsArtifact
from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    ArtifactType,
    sha256_hex,
)
from quantforge.sec.endpoints import (
    cik10,
    filing_document_url,
    filing_index_url,
    submissions_page_url,
    submissions_url,
)

# A fixed retrieval timestamp: provenance must never influence identity, so the
# exact value is irrelevant to the derived records.
FIXED_RETRIEVED_AT = "2026-08-05T00:00:00+00:00"
UA = "QuantForge test@example.com"


@dataclass
class FilingRow:
    """One columnar row of a submissions page."""

    accession: str
    form: str
    filing_date: str = ""
    report_date: str = ""
    acceptance: str = ""
    primary_document: str = ""
    primary_doc_description: str = ""


@dataclass
class SubmissionsBuilder:
    """Assemble a primary submissions page (optionally with overflow pointers)."""

    cik: int
    rows: list[FilingRow] = field(default_factory=list)
    overflow_files: list[str] = field(default_factory=list)

    def add(self, row: FilingRow) -> SubmissionsBuilder:
        self.rows.append(row)
        return self

    def _columns(self, rows: list[FilingRow]) -> dict[str, list[str]]:
        return {
            "accessionNumber": [r.accession for r in rows],
            "form": [r.form for r in rows],
            "filingDate": [r.filing_date for r in rows],
            "reportDate": [r.report_date for r in rows],
            "acceptanceDateTime": [r.acceptance for r in rows],
            "primaryDocument": [r.primary_document for r in rows],
            "primaryDocDescription": [r.primary_doc_description for r in rows],
        }

    def primary_bytes(self) -> bytes:
        body = {
            "cik": str(self.cik),
            "filings": {
                "recent": self._columns(self.rows),
                "files": [{"name": name} for name in self.overflow_files],
            },
        }
        return json.dumps(body).encode("utf-8")

    def overflow_bytes(self, rows: list[FilingRow]) -> bytes:
        # Overflow pages carry the columnar object at the top level.
        return json.dumps(self._columns(rows)).encode("utf-8")

    def primary_artifact(self, *, cik_in_meta: bool = True) -> SubmissionsArtifact:
        data = self.primary_bytes()
        return _submissions_artifact(
            data,
            submissions_url(self.cik),
            self.cik if cik_in_meta else None,
        )

    def overflow_artifact(
        self, page_filename: str, rows: list[FilingRow]
    ) -> SubmissionsArtifact:
        data = self.overflow_bytes(rows)
        return _submissions_artifact(
            data, submissions_page_url(page_filename), self.cik
        )


def _submissions_artifact(
    data: bytes, url: str, cik: int | None
) -> SubmissionsArtifact:
    meta = AcquisitionMetadata(
        source_url=url,
        artifact_type=ArtifactType.SUBMISSIONS,
        sha256=sha256_hex(data),
        retrieved_at=FIXED_RETRIEVED_AT,
        http_status=200,
        user_agent=UA,
        content_type="application/json",
        content_length=len(data),
        cik=str(cik) if cik is not None else None,
    )
    return SubmissionsArtifact(data, meta)


def document_metadata(
    cik: int,
    accession: str,
    filename: str,
    artifact_type: ArtifactType,
    *,
    content: bytes | None = None,
    cik_override: int | None = None,
) -> AcquisitionMetadata:
    """Build acquisition metadata for one filing-package document artifact."""
    if artifact_type is ArtifactType.FILING_INDEX:
        url = filing_index_url(cik, accession)
    else:
        url = filing_document_url(cik, accession, filename)
    payload = content if content is not None else url.encode("utf-8")
    meta_cik = cik_override if cik_override is not None else cik
    return AcquisitionMetadata(
        source_url=url,
        artifact_type=artifact_type,
        sha256=sha256_hex(payload),
        retrieved_at=FIXED_RETRIEVED_AT,
        http_status=200,
        user_agent=UA,
        content_length=len(payload),
        cik=str(meta_cik),
        accession=accession,
    )


def padded_cik(cik: int) -> str:
    return cik10(cik)
