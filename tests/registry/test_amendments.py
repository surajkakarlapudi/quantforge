"""Amendment linkage derivation with explicit confidence (data-model §7.1).

The system NEVER guesses. These tests pin each confidence level and, critically,
prove that a filing merely *containing prior-period comparative information* is
not mistaken for an amendment.
"""

from __future__ import annotations

from quantforge.registry.amendments import infer_amendments
from quantforge.registry.model import (
    AmendmentLinkConfidence,
    FilingProvenance,
    FilingRecord,
    make_filing_record,
)
from quantforge.sec.artifacts import ArtifactType

CIK = 320193
_PROV = FilingProvenance(
    source_artifact_sha256="deadbeef",
    source_artifact_type=ArtifactType.SUBMISSIONS,
    source_url="https://data.sec.gov/submissions/CIK0000320193.json",
    transformation_version_id="sha256:tv",
)


def _rec(
    accession: str,
    form: str,
    *,
    report_date: str | None = None,
    filing_date: str | None = None,
    acceptance: str | None = None,
) -> FilingRecord:
    return make_filing_record(
        cik=CIK,
        accession_original=accession,
        form=form,
        filing_date=filing_date,
        report_date=report_date,
        acceptance_timestamp_utc=acceptance,
        primary_document=None,
        primary_document_description=None,
        provenance=_PROV,
    )


def _by_accession(records: list[FilingRecord]) -> dict[str, FilingRecord]:
    return {r.accession_number: r for r in records}


def test_high_confidence_single_base_same_period() -> None:
    base = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-09-30",
        acceptance="2023-11-03T18:00:00.000Z",
    )
    amendment = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date="2023-09-30",
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([base, amendment]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession == "0000320193-23-000106"
    assert amended.amendment_link_confidence == (
        AmendmentLinkConfidence.DERIVED_HIGH_CONFIDENCE
    )
    # The base filing itself is untouched.
    assert out["0000320193-23-000106"].amends_accession is None


def test_low_confidence_when_chronology_only_by_date() -> None:
    # No acceptance timestamps: chronology can only be compared by filing date.
    base = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-09-30",
        filing_date="2023-11-03",
    )
    amendment = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date="2023-09-30",
        filing_date="2024-02-01",
    )
    out = _by_accession(infer_amendments([base, amendment]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession == "0000320193-23-000106"
    assert amended.amendment_link_confidence == (
        AmendmentLinkConfidence.DERIVED_LOW_CONFIDENCE
    )


def test_low_confidence_ambiguous_multiple_bases() -> None:
    # Two same-period base 10-Ks (e.g. re-reported) → ambiguous base.
    base1 = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-09-30",
        acceptance="2023-11-03T18:00:00.000Z",
    )
    base2 = _rec(
        "0000320193-23-000200",
        "10-K",
        report_date="2023-09-30",
        acceptance="2023-12-01T18:00:00.000Z",
    )
    amendment = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date="2023-09-30",
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([base1, base2, amendment]))
    amended = out["0000320193-24-000005"]
    # Both bases precede the amendment → irreducibly ambiguous → UNKNOWN.
    assert amended.amends_accession is None
    assert amended.amendment_link_confidence == AmendmentLinkConfidence.UNKNOWN


def test_unknown_when_no_base_present() -> None:
    orphan = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date="2023-09-30",
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([orphan]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession is None
    assert amended.amendment_link_confidence == AmendmentLinkConfidence.UNKNOWN


def test_unknown_when_amendment_has_no_report_date() -> None:
    base = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-09-30",
        acceptance="2023-11-03T18:00:00.000Z",
    )
    amendment = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date=None,
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([base, amendment]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession is None
    assert amended.amendment_link_confidence == AmendmentLinkConfidence.UNKNOWN


def test_comparative_period_filing_is_not_an_amendment() -> None:
    """A later 10-K carrying prior-year comparatives is NOT an amendment.

    This is the case the system must never get wrong: containing historical
    comparative information is not the same as *being* an amendment. Only a
    ``/A`` form is ever linked; a subsequent regular 10-K for a later period is
    a standalone filing with no amendment linkage — even though it reports on
    the prior period in its comparative columns.
    """
    fy2022 = _rec(
        "0000320193-22-000108",
        "10-K",
        report_date="2022-09-24",
        acceptance="2022-10-27T18:00:00.000Z",
    )
    fy2023 = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-09-30",
        acceptance="2023-11-03T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([fy2022, fy2023]))
    for record in out.values():
        assert record.is_amendment is False
        assert record.amends_accession is None
        assert record.amendment_link_confidence is None


def test_amendment_not_linked_to_different_period_base() -> None:
    # A 10-K/A for FY2023 must not link to a FY2022 10-K.
    fy2022 = _rec(
        "0000320193-22-000108",
        "10-K",
        report_date="2022-09-24",
        acceptance="2022-10-27T18:00:00.000Z",
    )
    amendment = _rec(
        "0000320193-24-000005",
        "10-K/A",
        report_date="2023-09-30",
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([fy2022, amendment]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession is None
    assert amended.amendment_link_confidence == AmendmentLinkConfidence.UNKNOWN


def test_amendment_not_linked_across_form_type() -> None:
    # A 10-Q/A must not link to a same-period 10-K.
    ten_k = _rec(
        "0000320193-23-000106",
        "10-K",
        report_date="2023-06-30",
        acceptance="2023-07-01T18:00:00.000Z",
    )
    q_amend = _rec(
        "0000320193-24-000005",
        "10-Q/A",
        report_date="2023-06-30",
        acceptance="2024-02-01T18:00:00.000Z",
    )
    out = _by_accession(infer_amendments([ten_k, q_amend]))
    amended = out["0000320193-24-000005"]
    assert amended.amends_accession is None
    assert amended.amendment_link_confidence == AmendmentLinkConfidence.UNKNOWN
