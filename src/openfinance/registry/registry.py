"""The Filing Registry — build derived filing records and query them.

This is the public façade of Phase 2. It composes the pieces:

    submissions artifacts ──parse──▶ filing records
                                     │
                    document metadata├──associate──▶ records + documents
                                     │
                                     └──infer──────▶ records + amendment links
                                            │
                                     RegistryStore (deterministic derived state)

The registry answers *what filings a company has* and their SEC-supplied
attributes, with full provenance back to the immutable raw artifacts. It never
interprets financial content and never mutates raw artifacts.

Two ways in:

* :meth:`FilingRegistry.build_company_from_store` — build from artifacts
  already acquired into a Phase 1 :class:`ArtifactStore` (offline, no network).
* :meth:`FilingRegistry.build_company_from_artifacts` — build from an explicit
  list of submissions artifacts + document metadata (used by tests and callers
  that manage acquisition themselves).

Determinism: given the same acquisition artifacts and the same
:class:`TransformationVersion`, both paths produce byte-identical derived
records, independent of artifact iteration order.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from openfinance.registry.amendments import infer_amendments
from openfinance.registry.documents import associate_documents
from openfinance.registry.errors import SourceValidationError
from openfinance.registry.identity import company_id as _company_id
from openfinance.registry.model import FilingRecord
from openfinance.registry.store import RegistryStore
from openfinance.registry.submissions import (
    SubmissionsArtifact,
    parse_submissions_artifact,
)
from openfinance.registry.version import TransformationVersion
from openfinance.sec.artifacts import AcquisitionMetadata, ArtifactType
from openfinance.sec.storage import ArtifactStore

__all__ = ["FilingRegistry"]


class FilingRegistry:
    """Build and query a deterministic registry of SEC filings."""

    def __init__(
        self,
        registry_store: RegistryStore,
        *,
        artifact_store: ArtifactStore | None = None,
        transformation_version: TransformationVersion | None = None,
    ) -> None:
        self._store = registry_store
        self._artifacts = artifact_store
        self._version = transformation_version or TransformationVersion()

    @property
    def transformation_version(self) -> TransformationVersion:
        return self._version

    # -- build ---------------------------------------------------------------

    def build_company_from_artifacts(
        self,
        submissions: Iterable[SubmissionsArtifact],
        *,
        documents: Iterable[AcquisitionMetadata] = (),
    ) -> list[FilingRecord]:
        """Derive and persist one filer's records from explicit artifacts.

        ``submissions`` are the acquired submissions pages (primary + overflow)
        for exactly one filer. ``documents`` are provenance records for any
        acquired filing-package artifacts to associate. Returns the derived
        records (as persisted, sorted by accession).
        """
        records = self._derive(submissions, documents)
        if not records:
            return []
        company_id = _single_company_id(records)
        self._store.write_company(
            company_id, self._version.transformation_version_id, records
        )
        return self._store.read_company(company_id)

    def build_company_from_store(self, cik: str | int) -> list[FilingRecord]:
        """Build one filer's registry from artifacts already in the store.

        Reads every stored submissions artifact for ``cik`` and every stored
        filing-package artifact, deriving records entirely offline. Requires
        an ``artifact_store`` to have been supplied at construction.
        """
        if self._artifacts is None:
            raise ValueError("build_company_from_store requires an artifact_store")
        target = _company_id(cik)
        submissions: list[SubmissionsArtifact] = []
        documents: list[AcquisitionMetadata] = []
        for meta in self._artifacts.iter_metadata():
            if meta.artifact_type is ArtifactType.SUBMISSIONS:
                if _submissions_belongs_to(meta, target):
                    submissions.append(
                        SubmissionsArtifact(
                            self._artifacts.read_blob(meta.sha256), meta
                        )
                    )
            else:
                documents.append(meta)
        return self.build_company_from_artifacts(submissions, documents=documents)

    def _derive(
        self,
        submissions: Iterable[SubmissionsArtifact],
        documents: Iterable[AcquisitionMetadata],
    ) -> list[FilingRecord]:
        # 1) Parse every submissions artifact into records, deduping by
        #    accession (the same filing appears in overflow pages / re-fetches).
        by_accession: dict[str, FilingRecord] = {}
        for artifact in submissions:
            for record in parse_submissions_artifact(artifact, self._version):
                existing = by_accession.get(record.accession_number)
                if existing is None:
                    by_accession[record.accession_number] = record
                else:
                    _check_consistent(existing, record)
                    # Keep the first-seen record deterministically: identity and
                    # attributes are identical, so which object we keep is
                    # irrelevant to the logical result.
        # Deterministic working order (identity-independent): by accession.
        records = [by_accession[a] for a in sorted(by_accession)]
        if not records:
            return []
        # 2) Associate acquired documents (provenance-based, fail-closed).
        records = associate_documents(records, documents)
        # 3) Derive amendment linkage with explicit confidence (never guess).
        records = infer_amendments(records)
        return records

    # -- query ---------------------------------------------------------------

    def list_filings(self, cik: str | int) -> list[FilingRecord]:
        """All filings for a filer, sorted by canonical accession number."""
        return self._store.read_company(_company_id(cik))

    def get_filing(self, cik: str | int, accession: str) -> FilingRecord | None:
        """Retrieve one filing by accession, or ``None`` if not present."""
        from openfinance.registry.identity import canonical_accession

        canonical = canonical_accession(accession)
        for record in self.list_filings(cik):
            if record.accession_number == canonical:
                return record
        return None

    def filings_by_form(self, cik: str | int, form: str) -> list[FilingRecord]:
        """All filings of an exact form (e.g. ``10-K``), sorted by accession.

        Matches the SEC form label exactly and case-sensitively: ``10-K`` does
        **not** match ``10-K/A`` (an amendment is a distinct form).
        """
        return [r for r in self.list_filings(cik) if r.form == form]

    def filing_provenance(self, cik: str | int, accession: str) -> FilingRecord | None:
        """Return the filing whose ``.provenance`` traces to source artifacts.

        Convenience alias for :meth:`get_filing` — the returned record already
        carries its :class:`FilingProvenance` and document references.
        """
        return self.get_filing(cik, accession)

    def list_company_ids(self) -> list[str]:
        """Every filer present in the derived registry, sorted."""
        return self._store.list_company_ids()


def _single_company_id(records: Sequence[FilingRecord]) -> str:
    ids = {r.company_id for r in records}
    if len(ids) != 1:
        raise SourceValidationError(
            f"expected records for exactly one company, got company_ids {sorted(ids)}"
        )
    return next(iter(ids))


def _submissions_belongs_to(meta: AcquisitionMetadata, target_company_id: str) -> bool:
    if meta.cik is None or meta.cik == "":
        # Overflow pages are acquired with the CIK recorded; if a submissions
        # artifact lacks a CIK we cannot attribute it to a filer offline.
        return False
    return _company_id(meta.cik) == target_company_id


def _check_consistent(a: FilingRecord, b: FilingRecord) -> None:
    """Ensure two records for the same accession agree on core attributes.

    The same filing legitimately reappears across overflow pages and
    re-fetches; the columns must match. A genuine disagreement means the source
    artifacts are inconsistent — fail closed rather than silently pick one.
    """
    for attr in ("form", "filing_date", "report_date", "acceptance_timestamp_utc"):
        if getattr(a, attr) != getattr(b, attr):
            raise SourceValidationError(
                f"inconsistent duplicate for accession {a.accession_number}: "
                f"{attr} differs ({getattr(a, attr)!r} vs {getattr(b, attr)!r})"
            )
