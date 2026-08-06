"""Document association: index/primary/XBRL attach; ambiguity fails closed."""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.registry.documents import associate_documents
from openfinance.registry.errors import DocumentAssociationError
from openfinance.registry.model import FilingRecord
from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from openfinance.sec.artifacts import ArtifactType

from .builders import FilingRow, SubmissionsBuilder, document_metadata

CIK = 320193
ACCESSION = "0000320193-23-000106"


def _registry(tmp_path: Path) -> FilingRegistry:
    return FilingRegistry(RegistryStore(tmp_path / "registry"))


def _sample_artifact() -> SubmissionsBuilder:
    return SubmissionsBuilder(CIK).add(
        FilingRow(
            accession=ACCESSION,
            form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            primary_document="aapl-20230930.htm",
        )
    )


def test_associates_index_primary_and_xbrl(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    docs = [
        document_metadata(CIK, ACCESSION, "index.json", ArtifactType.FILING_INDEX),
        document_metadata(
            CIK, ACCESSION, "aapl-20230930.htm", ArtifactType.FILING_DOCUMENT
        ),
        document_metadata(
            CIK, ACCESSION, "aapl-20230930_htm.xml", ArtifactType.XBRL_INSTANCE
        ),
    ]
    (record,) = reg.build_company_from_artifacts(
        [_sample_artifact().primary_artifact()], documents=docs
    )
    types = {d.artifact_type for d in record.documents}
    assert types == {
        ArtifactType.FILING_INDEX,
        ArtifactType.FILING_DOCUMENT,
        ArtifactType.XBRL_INSTANCE,
    }


def test_primary_document_flag_set_by_filename(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    docs = [
        document_metadata(
            CIK, ACCESSION, "aapl-20230930.htm", ArtifactType.FILING_DOCUMENT
        ),
        document_metadata(
            CIK, ACCESSION, "exhibit-99.htm", ArtifactType.FILING_DOCUMENT
        ),
    ]
    (record,) = reg.build_company_from_artifacts(
        [_sample_artifact().primary_artifact()], documents=docs
    )
    primary = [d for d in record.documents if d.is_primary_document]
    assert len(primary) == 1
    assert primary[0].source_url.endswith("aapl-20230930.htm")


def test_unrelated_accession_not_associated(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    other = document_metadata(
        CIK, "0000320193-99-999999", "x.htm", ArtifactType.FILING_DOCUMENT
    )
    (record,) = reg.build_company_from_artifacts(
        [_sample_artifact().primary_artifact()], documents=[other]
    )
    assert record.documents == ()


def test_document_without_accession_not_associated() -> None:
    # A submissions artifact (no accession) is never a package document.
    (record,) = associate_documents(
        list(
            _iter_records(),
        ),
        [document_metadata(CIK, ACCESSION, "index.json", ArtifactType.SUBMISSIONS)],
    )
    assert record.documents == ()


def test_cik_mismatch_fails_closed() -> None:
    records = list(_iter_records())
    bad = document_metadata(
        CIK,
        ACCESSION,
        "aapl-20230930.htm",
        ArtifactType.FILING_DOCUMENT,
        cik_override=999999,  # provenance CIK contradicts the filing
    )
    with pytest.raises(DocumentAssociationError, match=r"CIK.*mismatch"):
        associate_documents(records, [bad])


def test_duplicate_document_bytes_deduped(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    doc = document_metadata(CIK, ACCESSION, "index.json", ArtifactType.FILING_INDEX)
    (record,) = reg.build_company_from_artifacts(
        [_sample_artifact().primary_artifact()], documents=[doc, doc]
    )
    assert len(record.documents) == 1


def _iter_records() -> list[FilingRecord]:
    from openfinance.registry.submissions import parse_submissions_artifact
    from openfinance.registry.version import TransformationVersion

    return list(
        parse_submissions_artifact(
            _sample_artifact().primary_artifact(), TransformationVersion()
        )
    )
