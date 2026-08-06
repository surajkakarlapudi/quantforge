"""Parsing submissions into filing records: dates, forms, fields, errors."""

from __future__ import annotations

import json

import pytest

from openfinance.registry.errors import SourceValidationError
from openfinance.registry.model import AmendmentLinkConfidence, FilingRecord
from openfinance.registry.submissions import (
    SubmissionsArtifact,
    parse_submissions_artifact,
)
from openfinance.registry.version import TransformationVersion
from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    ArtifactType,
    sha256_hex,
)

from .builders import UA, FilingRow, SubmissionsBuilder

CIK = 320193
TV = TransformationVersion()


def _parse(artifact: SubmissionsArtifact) -> list[FilingRecord]:
    return list(parse_submissions_artifact(artifact, TV))


def test_parses_basic_filing_fields() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession="0000320193-23-000106",
            form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            acceptance="2023-11-03T18:01:14.000Z",
            primary_document="aapl-20230930.htm",
            primary_doc_description="10-K",
        )
    )
    (record,) = _parse(b.primary_artifact())
    assert record.filing_id == "accession:0000320193-23-000106"
    assert record.company_id == "cik:0000320193"
    assert record.accession_number == "0000320193-23-000106"
    assert record.form == "10-K"
    assert record.filing_date == "2023-11-03"
    assert record.report_date == "2023-09-30"
    assert record.acceptance_timestamp_utc == "2023-11-03T18:01:14.000Z"
    assert record.primary_document == "aapl-20230930.htm"
    assert record.primary_document_description == "10-K"
    assert record.is_amendment is False


def test_filing_date_and_report_date_stay_distinct() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession="0000320193-23-000106",
            form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
        )
    )
    (record,) = _parse(b.primary_artifact())
    # Neither collapses into the other; both preserved verbatim.
    assert record.filing_date == "2023-11-03"
    assert record.report_date == "2023-09-30"
    assert record.filing_date != record.report_date


def test_acceptance_timestamp_stored_verbatim_utc_no_conversion() -> None:
    # A post-cutoff UTC timestamp must NOT be converted to ET at this layer.
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession="0000320193-23-000106",
            form="10-K",
            acceptance="2023-11-03T22:31:05.000Z",
        )
    )
    (record,) = _parse(b.primary_artifact())
    assert record.acceptance_timestamp_utc == "2023-11-03T22:31:05.000Z"


def test_missing_report_date_preserved_as_none() -> None:
    # Non-periodic forms (e.g. Form 4) carry an empty reportDate in EDGAR.
    b = SubmissionsBuilder(CIK).add(
        FilingRow(accession="0000320193-23-000200", form="4", report_date="")
    )
    (record,) = _parse(b.primary_artifact())
    assert record.report_date is None


def test_missing_acceptance_and_description_preserved_as_none() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession="0000320193-99-000001",
            form="10-K",
            acceptance="",
            primary_doc_description="",
        )
    )
    (record,) = _parse(b.primary_artifact())
    assert record.acceptance_timestamp_utc is None
    assert record.primary_document_description is None


@pytest.mark.parametrize(
    ("form", "is_amendment"),
    [
        ("10-K", False),
        ("10-K/A", True),
        ("10-Q", False),
        ("10-Q/A", True),
        ("8-K", False),
        ("8-K/A", True),
    ],
)
def test_form_amendment_flag(form: str, is_amendment: bool) -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(
            accession="0000320193-23-000106",
            form=form,
            report_date="2023-09-30",
        )
    )
    (record,) = _parse(b.primary_artifact())
    assert record.form == form
    assert record.is_amendment is is_amendment
    # Non-amendments never carry a confidence; amendments start UNKNOWN.
    if is_amendment:
        assert record.amendment_link_confidence == (AmendmentLinkConfidence.UNKNOWN)
    else:
        assert record.amendment_link_confidence is None


def test_provenance_traces_to_source_artifact_hash() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(accession="0000320193-23-000106", form="10-K")
    )
    artifact = b.primary_artifact()
    (record,) = _parse(artifact)
    assert record.provenance.source_artifact_sha256 == artifact.metadata.sha256
    assert record.provenance.source_artifact_type is ArtifactType.SUBMISSIONS
    assert record.provenance.source_url == artifact.metadata.source_url
    assert record.provenance.transformation_version_id == (TV.transformation_version_id)


def test_original_accession_preserved_when_undashed() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(accession="000032019323000106", form="10-K")
    )
    (record,) = _parse(b.primary_artifact())
    assert record.accession_number == "0000320193-23-000106"
    assert record.accession_number_original == "000032019323000106"


def test_cik_resolved_from_body_when_absent_in_metadata() -> None:
    b = SubmissionsBuilder(CIK).add(
        FilingRow(accession="0000320193-23-000106", form="10-K")
    )
    (record,) = _parse(b.primary_artifact(cik_in_meta=False))
    assert record.company_id == "cik:0000320193"


# -- error handling -----------------------------------------------------------


def _artifact(body: bytes, cik: int | None = CIK) -> SubmissionsArtifact:
    meta = AcquisitionMetadata(
        source_url="https://data.sec.gov/submissions/x.json",
        artifact_type=ArtifactType.SUBMISSIONS,
        sha256=sha256_hex(body),
        retrieved_at="2026-08-05T00:00:00+00:00",
        http_status=200,
        user_agent=UA,
        cik=str(cik) if cik is not None else None,
    )
    return SubmissionsArtifact(body, meta)


def test_missing_accession_row_raises() -> None:
    body = json.dumps(
        {"filings": {"recent": {"accessionNumber": [""], "form": ["10-K"]}}}
    ).encode()
    with pytest.raises(SourceValidationError, match="no accession"):
        _parse(_artifact(body))


def test_missing_form_row_raises() -> None:
    body = json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-23-000106"],
                    "form": [""],
                }
            }
        }
    ).encode()
    with pytest.raises(SourceValidationError, match=r"no.*form"):
        _parse(_artifact(body))


def test_misaligned_columns_raise() -> None:
    body = json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-23-000106", "a-2"],
                    "form": ["10-K"],  # shorter than accessionNumber
                }
            }
        }
    ).encode()
    with pytest.raises(SourceValidationError, match=r"must align|length"):
        _parse(_artifact(body))


def test_corrupt_json_raises() -> None:
    with pytest.raises(SourceValidationError, match=r"not valid.*JSON"):
        _parse(_artifact(b"{not json"))


def test_no_resolvable_cik_raises() -> None:
    body = json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-23-000106"],
                    "form": ["10-K"],
                }
            }
        }
    ).encode()
    with pytest.raises(SourceValidationError, match=r"no resolvable.*CIK"):
        _parse(_artifact(body, cik=None))


def test_empty_recent_yields_no_records() -> None:
    body = json.dumps(
        {"filings": {"recent": {"accessionNumber": [], "form": []}}}
    ).encode()
    assert _parse(_artifact(body)) == []


def test_absent_optional_column_treated_as_missing() -> None:
    # reportDate column entirely absent -> every row's report_date is None.
    body = json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-23-000106"],
                    "form": ["10-K"],
                }
            }
        }
    ).encode()
    (record,) = _parse(_artifact(body))
    assert record.report_date is None
    assert record.acceptance_timestamp_utc is None
