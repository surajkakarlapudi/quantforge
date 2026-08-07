"""Associate acquired artifacts with the filings they belong to.

The registry records *which acquired documents belong to which filing* — the
filing index, the primary document, and any XBRL package components (instance,
schema, cal/def/lab/pre) — **without parsing any of them**. Association is by
**provenance**, not by guessing from filenames: every non-submissions artifact
carries acquisition metadata with the ``cik`` and ``accession`` it was fetched
for (Phase 1 records these), so a document attaches to a filing iff their
canonical accession numbers match *and* their CIKs agree.

Fail-closed rules (Phase-2 spec):

* An artifact whose accession matches a filing but whose CIK **contradicts** it
  is a :class:`DocumentAssociationError` — we never attach across a CIK
  mismatch.
* An artifact with no accession in its provenance is **not** associated with
  any filing (we do not infer a filing from bytes we cannot attribute).
* The ``primary_document`` flag is set only when a document's source URL
  basename exactly equals the filing's SEC-declared ``primary_document`` — no
  fuzzy matching.
* Submissions artifacts are inputs to the registry, not filing-package
  documents, so they are never associated as documents.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from quantforge.registry.errors import (
    AccessionFormatError,
    DocumentAssociationError,
)
from quantforge.registry.identity import canonical_accession, company_id
from quantforge.registry.model import DocumentReference, FilingRecord
from quantforge.sec.artifacts import AcquisitionMetadata, ArtifactType

__all__ = ["associate_documents"]

# Artifact types that are filing-package documents (everything except the
# submissions history, which is the registry's *input*, not a package member).
_DOCUMENT_TYPES = frozenset(
    t for t in ArtifactType if t is not ArtifactType.SUBMISSIONS
)


def associate_documents(
    records: Iterable[FilingRecord],
    artifact_metadata: Iterable[AcquisitionMetadata],
) -> list[FilingRecord]:
    """Attach document references to each filing from acquired artifacts.

    Parameters
    ----------
    records:
        The filing records to enrich (typically one filer's filings).
    artifact_metadata:
        Provenance records for artifacts already in the store (e.g. from
        :meth:`ArtifactStore.iter_metadata`). Each is matched to a filing by
        canonical accession + CIK.

    Returns the records with a stable, de-duplicated set of
    :class:`DocumentReference` attached. Records are returned in input order.
    """
    by_accession: dict[str, FilingRecord] = {r.accession_number: r for r in records}
    # Collect references per filing, keyed by content hash to dedupe repeat
    # acquisitions of the same bytes.
    collected: dict[str, dict[str, DocumentReference]] = {
        acc: {} for acc in by_accession
    }

    for meta in artifact_metadata:
        if meta.artifact_type not in _DOCUMENT_TYPES:
            continue
        if meta.accession is None or meta.accession == "":
            continue  # Unattributable to a filing; do not guess.
        try:
            accession = canonical_accession(meta.accession)
        except AccessionFormatError:
            # Provenance carries a malformed accession; skip rather than
            # attach to the wrong filing.
            continue
        record = by_accession.get(accession)
        if record is None:
            continue  # Artifact for a filing not in this cohort.
        _guard_cik(meta, record, accession)

        reference = DocumentReference(
            artifact_sha256=meta.sha256,
            artifact_type=meta.artifact_type,
            source_url=meta.source_url,
            is_primary_document=_is_primary(meta, record),
        )
        collected[accession][meta.sha256] = reference

    result: list[FilingRecord] = []
    for record in records:
        refs = collected.get(record.accession_number, {})
        if not refs:
            result.append(record)
            continue
        ordered = tuple(
            sorted(
                refs.values(),
                key=lambda d: (d.artifact_type.value, d.artifact_sha256),
            )
        )
        result.append(record.with_documents(ordered))
    return result


def _guard_cik(meta: AcquisitionMetadata, record: FilingRecord, accession: str) -> None:
    if meta.cik is None or meta.cik == "":
        return  # No CIK to contradict; accession match stands.
    if company_id(meta.cik) != record.company_id:
        raise DocumentAssociationError(
            f"artifact {meta.sha256} claims accession {accession} but its CIK "
            f"({meta.cik}) does not match the filing's company "
            f"({record.company_id}); refusing to associate across a CIK "
            "mismatch"
        )


def _is_primary(meta: AcquisitionMetadata, record: FilingRecord) -> bool:
    if record.primary_document is None:
        return False
    basename = _url_basename(meta.source_url)
    return basename == record.primary_document


def _url_basename(url: str) -> str:
    path = urlsplit(url).path
    return path.rsplit("/", 1)[-1] if path else ""
