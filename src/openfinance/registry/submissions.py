"""Parse acquired submissions artifacts into filing records.

The submissions JSON is SEC's per-filer filing history. It is **columnar**:
``filings.recent`` is an object of parallel arrays (``accessionNumber``,
``form``, ``filingDate``, ``reportDate``, ``acceptanceDateTime``,
``primaryDocument``, ``primaryDocDescription``, ...), each the same length, one
index per filing. Prolific filers spill older filings onto overflow pages named
in ``filings.recent``/``filings.files``; the overflow *pages* carry the same
columnar object at the top level (no ``filings`` wrapper).

This module turns the **bytes of already-acquired** submissions artifacts into
:class:`~openfinance.registry.model.FilingRecord` objects. It performs no
network I/O and no financial interpretation — only the columnar unpacking
needed to know *what filings exist* and their SEC-supplied attributes.

Fail-closed rules (data-model §12; Phase-2 spec):

* A row with no accession number is a hard error
  (:class:`SourceValidationError`) — we never invent an accession.
* Columnar arrays of mismatched length are a hard error — the shape is corrupt.
* Missing optional fields (report date, acceptance, description) are preserved
  as ``None`` — never fabricated.
* Timestamps are stored **exactly as supplied** — no timezone conversion here.
* Determinism: rows are emitted in encounter order and identity never depends
  on ordering, but the caller (registry build) sorts for a stable result.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from openfinance.registry.errors import SourceValidationError
from openfinance.registry.model import (
    FilingProvenance,
    FilingRecord,
    make_filing_record,
)
from openfinance.registry.version import TransformationVersion
from openfinance.sec.artifacts import AcquisitionMetadata
from openfinance.sec.endpoints import canonical_cik

__all__ = [
    "SubmissionsArtifact",
    "parse_submissions_artifact",
]

# Columns we read out of the columnar `filings.recent` (or an overflow page).
# `accessionNumber` and `form` are required; the rest are preserved when
# present and left as None when absent. We deliberately read only what a
# *registry* needs — no financial columns are interpreted.
_COL_ACCESSION = "accessionNumber"
_COL_FORM = "form"
_COL_FILING_DATE = "filingDate"
_COL_REPORT_DATE = "reportDate"
_COL_ACCEPTANCE = "acceptanceDateTime"
_COL_PRIMARY_DOC = "primaryDocument"
_COL_PRIMARY_DESC = "primaryDocDescription"


class SubmissionsArtifact:
    """An acquired submissions artifact: its raw bytes + acquisition metadata.

    Bundles what the parser needs: the immutable bytes (already read from the
    content-addressed store) and the :class:`AcquisitionMetadata` describing
    where they came from (source URL, artifact type, content hash, CIK). The
    metadata's content hash and URL become each derived record's provenance.
    """

    __slots__ = ("data", "metadata")

    def __init__(self, data: bytes, metadata: AcquisitionMetadata) -> None:
        self.data = data
        self.metadata = metadata


def parse_submissions_artifact(
    artifact: SubmissionsArtifact,
    transformation_version: TransformationVersion,
) -> Iterator[FilingRecord]:
    """Yield a :class:`FilingRecord` per filing in one submissions artifact.

    Handles both the primary page (a ``filings.recent`` object under a
    ``filings`` wrapper) and overflow pages (the columnar object at top level).
    The CIK is taken from the artifact's acquisition metadata when present, and
    otherwise from the JSON body's ``cik`` field; if neither is available the
    artifact is rejected (a filing has no owning company without a CIK).
    """
    try:
        parsed = json.loads(artifact.data)
    except json.JSONDecodeError as exc:
        raise SourceValidationError(
            f"submissions artifact {artifact.metadata.sha256} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise SourceValidationError(
            f"submissions artifact {artifact.metadata.sha256} is not a JSON object"
        )

    cik = _resolve_cik(artifact, parsed)
    columns = _extract_columns(parsed, artifact.metadata.sha256)
    if columns is None:
        return  # No `recent`/columnar block on this artifact: nothing to emit.

    provenance = FilingProvenance(
        source_artifact_sha256=artifact.metadata.sha256,
        source_artifact_type=artifact.metadata.artifact_type,
        source_url=artifact.metadata.source_url,
        transformation_version_id=(transformation_version.transformation_version_id),
    )
    yield from _rows_to_records(columns, cik, provenance, artifact.metadata.sha256)


def _resolve_cik(artifact: SubmissionsArtifact, parsed: dict[str, object]) -> str:
    meta_cik = artifact.metadata.cik
    if meta_cik is not None and meta_cik != "":
        return canonical_cik(meta_cik)
    body_cik = parsed.get("cik")
    if isinstance(body_cik, (str, int)) and not isinstance(body_cik, bool):
        try:
            return canonical_cik(body_cik)
        except ValueError:
            pass
    raise SourceValidationError(
        f"submissions artifact {artifact.metadata.sha256} has no resolvable "
        "CIK (neither acquisition metadata nor the JSON body supplied one)"
    )


def _extract_columns(
    parsed: dict[str, object], sha: str
) -> dict[str, list[object]] | None:
    """Return the columnar block, or None if this artifact has no filings.

    The primary page nests the columns under ``filings.recent``. Overflow
    pages carry the same columns at the top level. We detect which by looking
    for the ``accessionNumber`` column in each candidate location.
    """
    filings = parsed.get("filings")
    if isinstance(filings, dict):
        recent = filings.get("recent")
        if isinstance(recent, dict) and _COL_ACCESSION in recent:
            return _validate_columnar(recent, sha)
        # A `filings` wrapper with no usable `recent` block: nothing to emit
        # from this artifact (e.g. a pointer-only structure).
        return None
    if _COL_ACCESSION in parsed:
        # Overflow page: columns at top level.
        return _validate_columnar(parsed, sha)
    return None


def _validate_columnar(block: dict[str, object], sha: str) -> dict[str, list[object]]:
    """Coerce a columnar block to lists and verify all columns are aligned."""
    accessions = block.get(_COL_ACCESSION)
    if not isinstance(accessions, list):
        raise SourceValidationError(
            f"submissions artifact {sha}: {_COL_ACCESSION} is not an array"
        )
    n = len(accessions)
    columns: dict[str, list[object]] = {}
    for name in (
        _COL_ACCESSION,
        _COL_FORM,
        _COL_FILING_DATE,
        _COL_REPORT_DATE,
        _COL_ACCEPTANCE,
        _COL_PRIMARY_DOC,
        _COL_PRIMARY_DESC,
    ):
        value = block.get(name)
        if value is None:
            # Absent column: treat every row's value as missing. (Older pages
            # occasionally omit a column entirely.)
            columns[name] = [None] * n
            continue
        if not isinstance(value, list):
            raise SourceValidationError(
                f"submissions artifact {sha}: column {name} is not an array"
            )
        if len(value) != n:
            raise SourceValidationError(
                f"submissions artifact {sha}: column {name} has length "
                f"{len(value)}, expected {n} (columnar arrays must align)"
            )
        columns[name] = value
    return columns


def _rows_to_records(
    columns: dict[str, list[object]],
    cik: str,
    provenance: FilingProvenance,
    sha: str,
) -> Iterator[FilingRecord]:
    accessions = columns[_COL_ACCESSION]
    for i in range(len(accessions)):
        accession = _cell_str(accessions[i])
        if accession is None or accession == "":
            raise SourceValidationError(
                f"submissions artifact {sha}: row {i} has no accession number"
            )
        form = _cell_str(columns[_COL_FORM][i])
        if form is None or form == "":
            raise SourceValidationError(
                f"submissions artifact {sha}: row {i} ({accession}) has no form type"
            )
        yield make_filing_record(
            cik=cik,
            accession_original=accession,
            form=form,
            filing_date=_cell_opt(columns[_COL_FILING_DATE][i]),
            report_date=_cell_opt(columns[_COL_REPORT_DATE][i]),
            acceptance_timestamp_utc=_cell_opt(columns[_COL_ACCEPTANCE][i]),
            primary_document=_cell_opt(columns[_COL_PRIMARY_DOC][i]),
            primary_document_description=_cell_opt(columns[_COL_PRIMARY_DESC][i]),
            provenance=provenance,
        )


def _cell_str(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip()
    return None


def _cell_opt(value: object) -> str | None:
    """Preserve a present, non-empty string cell; map absence/empty to None.

    SEC uses the empty string for "not applicable" columns (e.g. ``reportDate``
    for a Form 4). We treat empty as absence and never fabricate a value.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
