"""Derive amendment → base-filing linkage, with explicit confidence.

SEC exposes **no** explicit "this filing amends accession X" field anywhere in
structured metadata (submissions, companyfacts) or the SGML header — confirmed
across all reconnaissance issuers (data-model §7.1, recon §9). Any linkage is
therefore *derived*, and this module records **how defensibly** via
:class:`~openfinance.registry.model.AmendmentLinkConfidence`.

The derivation is deterministic and depends only on the filing cohort's
SEC-supplied attributes (form, CIK, report date, acceptance/filing chronology).
It NEVER guesses: when a base cannot be defensibly identified the linkage is
``UNKNOWN`` with no fabricated ``amends_accession`` (§7.1, invariant 22a).

Confidence rules (verbatim from §7.1):

* ``DERIVED_HIGH_CONFIDENCE`` — form is exactly ``base + "/A"``, **same CIK**,
  **same report date**, exactly **one** candidate base filing, and consistent
  chronology (the amendment was accepted after the base).
* ``DERIVED_LOW_CONFIDENCE`` — ``/A`` + same report date but the base is
  **ambiguous** (several candidates) or chronology matched only approximately
  (e.g. acceptance timestamps unavailable, so only dates could be compared).
* ``UNKNOWN`` — no defensible base (missing report date, no matching base
  filing, orphan ``/A``). Represented standalone.

A crucial non-goal, tested explicitly: a regular filing that merely *contains
prior-period comparative information* (e.g. a 10-K with FY-2 columns) is **not**
an amendment. Only a ``/A`` form is ever considered here, so a comparative-only
filing is never linked to anything (data-model §13 case 11).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from openfinance.registry.model import (
    AmendmentLinkConfidence,
    FilingRecord,
    base_form,
)

__all__ = ["infer_amendments"]


def infer_amendments(
    records: Iterable[FilingRecord],
) -> list[FilingRecord]:
    """Return the records with amendment linkage derived for each ``/A`` filing.

    Non-amendments are returned unchanged. Each amendment is matched against
    candidate base filings drawn from the *same cohort* (same CIK — the input
    is expected to be one filer's filings). Output order mirrors input order;
    the derivation itself is independent of ordering (candidate selection and
    tie-breaking are deterministic functions of the data).
    """
    all_records = list(records)
    result: list[FilingRecord] = []
    for record in all_records:
        if not record.is_amendment:
            result.append(record)
            continue
        amends, confidence = _derive_link(record, all_records)
        result.append(record.with_amendment(amends, confidence))
    return result


def _derive_link(
    amendment: FilingRecord, cohort: Sequence[FilingRecord]
) -> tuple[str | None, AmendmentLinkConfidence]:
    # A base can only be identified with a report date to match on. Absent one,
    # there is no defensible period key → UNKNOWN (never guess).
    if amendment.report_date is None:
        return None, AmendmentLinkConfidence.UNKNOWN

    target_form = base_form(amendment.form)
    candidates = [
        other
        for other in cohort
        if other.accession_number != amendment.accession_number
        and not other.is_amendment
        and other.company_id == amendment.company_id
        and other.form == target_form
        and other.report_date == amendment.report_date
    ]
    if not candidates:
        # No same-period base of the amended form. Could be an amendment of an
        # amendment, an orphan /A, or a base we never acquired. Do not guess.
        return None, AmendmentLinkConfidence.UNKNOWN

    # Chronology filter: the base must precede the amendment. Prefer the
    # millisecond-precision acceptance timestamp; fall back to filing date.
    ordered_before = [c for c in candidates if _strictly_before(c, amendment)]
    chronology_exact = _has_acceptance(amendment) and all(
        _has_acceptance(c) for c in candidates
    )

    if len(candidates) == 1:
        only = candidates[0]
        if _strictly_before(only, amendment) and chronology_exact:
            return only.accession_number, (
                AmendmentLinkConfidence.DERIVED_HIGH_CONFIDENCE
            )
        # Exactly one same-period base, but chronology could only be compared
        # by date (or not at all): defensible link, lower confidence.
        return only.accession_number, (AmendmentLinkConfidence.DERIVED_LOW_CONFIDENCE)

    # Multiple same-period base candidates: the base is ambiguous. We record a
    # low-confidence link to the single best-defined candidate when exactly one
    # precedes the amendment; otherwise the ambiguity is irreducible → UNKNOWN.
    if len(ordered_before) == 1:
        return ordered_before[0].accession_number, (
            AmendmentLinkConfidence.DERIVED_LOW_CONFIDENCE
        )
    return None, AmendmentLinkConfidence.UNKNOWN


def _has_acceptance(record: FilingRecord) -> bool:
    return record.acceptance_timestamp_utc is not None


def _strictly_before(base: FilingRecord, amendment: FilingRecord) -> bool:
    """True if ``base`` demonstrably precedes ``amendment`` in filing time.

    Uses acceptance timestamps when both are present (UTC ISO-8601, so string
    comparison is chronological), else falls back to filing dates. If neither
    pair is comparable, chronology cannot be established and this returns
    ``False`` (fail-closed: an unprovable ordering is not asserted).
    """
    a_acc = base.acceptance_timestamp_utc
    b_acc = amendment.acceptance_timestamp_utc
    if a_acc is not None and b_acc is not None:
        return a_acc < b_acc
    a_date = base.filing_date
    b_date = amendment.filing_date
    if a_date is not None and b_date is not None:
        return a_date < b_date
    return False
