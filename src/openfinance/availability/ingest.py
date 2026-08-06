"""The availability façade — derive, persist, and resolve (Phase 5 entry point).

Composes the existing layers without duplicating any of them (Implementation
Requirement 2):

    Phase 2 FilingRegistry ─(evidence: acceptance/filing/report + form)─┐
    Phase 1 ArtifactStore  ─(retrieved_at upper bound, joined HERE only)┤
                                                                        ▼
                                 derive(evidence, policy) → FilingAvailability
                                                                        │
                              AvailabilityStore (sidecar, by filing_id)
                                                                        │
    Phase 4 CanonicalFactStore ─(immutable Facts)───────────────────────┴─▶ Resolver

Key mandate compliance:

* **``retrieved_at`` joined only at derivation (Decision 1).** It is read from the
  Phase 1 :class:`~openfinance.sec.artifacts.AcquisitionMetadata` here and placed
  on :class:`~openfinance.availability.model.FilingEvidence` — never propagated to
  RawFact/Fact identity. It serves solely as the invariant-11 upper bound.
* **Sidecar store, facts never rewritten (Decision 3).** Availability is persisted
  keyed by ``filing_id``; the Phase 4 fact store is read-only here.
* **Reuses Phase 2 identity & stores.** Company/filing identity comes from the
  registry; no second storage system is created.

The façade is offline: it consumes already-acquired artifacts and already-derived
registry/canonical state. It never touches the network and never mutates raw or
canonical stores.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openfinance.availability.model import (
    AvailabilityStatus,
    FilingAvailability,
    FilingEvidence,
)
from openfinance.availability.policy import derive
from openfinance.availability.resolve import PointInTimeResolver
from openfinance.availability.store import AvailabilityStore
from openfinance.availability.version import (
    AvailabilityPolicy,
    DatasetVersion,
    edgar_std_v1,
)
from openfinance.canonical.model import Fact
from openfinance.canonical.store import CanonicalFactStore
from openfinance.registry.identity import company_id as _company_id
from openfinance.registry.model import FilingRecord
from openfinance.registry.registry import FilingRegistry
from openfinance.sec.storage import ArtifactStore

__all__ = ["AvailabilityIngestor", "CompanyAvailabilityResult"]


@dataclass(frozen=True, slots=True)
class CompanyAvailabilityResult:
    """Outcome of deriving & persisting one filer's filing availability."""

    company_id: str
    records: tuple[FilingAvailability, ...]

    @property
    def derived_count(self) -> int:
        return sum(
            1
            for r in self.records
            if r.availability_status is AvailabilityStatus.DERIVED
        )

    @property
    def verified_count(self) -> int:
        return sum(
            1
            for r in self.records
            if r.availability_status is AvailabilityStatus.VERIFIED
        )

    @property
    def unknown_count(self) -> int:
        return sum(
            1
            for r in self.records
            if r.availability_status is AvailabilityStatus.UNKNOWN
        )


class AvailabilityIngestor:
    """Derive filing availability and build point-in-time resolvers, offline."""

    def __init__(
        self,
        registry: FilingRegistry,
        availability_store: AvailabilityStore,
        *,
        artifact_store: ArtifactStore | None = None,
        canonical_store: CanonicalFactStore | None = None,
        policies: Sequence[AvailabilityPolicy] | None = None,
    ) -> None:
        self._registry = registry
        self._store = availability_store
        self._artifacts = artifact_store
        self._canonical = canonical_store
        # Default to the initial provisional/unvalidated policy (Decision 2).
        self._policies: tuple[AvailabilityPolicy, ...] = (
            tuple(policies) if policies is not None else (edgar_std_v1(),)
        )

    @property
    def policies(self) -> tuple[AvailabilityPolicy, ...]:
        return self._policies

    @property
    def policy_ids(self) -> list[str]:
        return sorted(p.availability_policy_id for p in self._policies)

    # -- evidence assembly ---------------------------------------------------

    def _retrieved_at_by_artifact(self) -> dict[str, str]:
        """Map ``artifact_sha256 → earliest retrieved_at`` from Phase 1 metadata.

        The join key for the invariant-11 upper bound. Multiple retrievals of one
        blob keep the earliest ``retrieved_at`` (the tightest true upper bound on
        availability). Empty when no artifact store is wired.
        """
        earliest: dict[str, str] = {}
        if self._artifacts is None:
            return earliest
        for meta in self._artifacts.iter_metadata():
            prior = earliest.get(meta.sha256)
            if prior is None or meta.retrieved_at < prior:
                earliest[meta.sha256] = meta.retrieved_at
        return earliest

    def _evidence_for(
        self, record: FilingRecord, retrieved_by_artifact: dict[str, str]
    ) -> FilingEvidence:
        """Assemble one filing's derivation evidence (joins retrieved_at here)."""
        # Earliest retrieved_at across the filing's referenced artifacts — the
        # tightest upper bound (invariant 11). None if we have no metadata.
        retrieved_candidates = [
            retrieved_by_artifact[doc.artifact_sha256]
            for doc in record.documents
            if doc.artifact_sha256 in retrieved_by_artifact
        ]
        retrieved_at = min(retrieved_candidates) if retrieved_candidates else None
        return FilingEvidence(
            filing_id=record.filing_id,
            form=record.form,
            acceptance_timestamp_utc=record.acceptance_timestamp_utc,
            filing_date=record.filing_date,
            report_date=record.report_date,
            dissemination_evidence_utc=None,  # no dissemination index ingested yet
            retrieved_at=retrieved_at,
        )

    # -- derive & persist ----------------------------------------------------

    def derive_company(self, cik: str | int) -> CompanyAvailabilityResult:
        """Derive & persist availability for every filing of one filer.

        Reads the filer's filings from the registry, joins each filing's evidence
        (including the Phase 1 ``retrieved_at`` upper bound), derives the
        availability triple under the configured policies, and writes the sidecar
        records keyed by ``filing_id``. Deterministic and offline.
        """
        company = _company_id(cik)
        records = self._registry.list_filings(cik)
        retrieved_by_artifact = self._retrieved_at_by_artifact()
        derived = [
            derive(self._evidence_for(record, retrieved_by_artifact), self._policies)
            for record in records
        ]
        self._store.write_company(company, derived, self.policy_ids)
        stored = self._store.read_company(company)
        return CompanyAvailabilityResult(company_id=company, records=tuple(stored))

    # -- resolver construction ----------------------------------------------

    def resolver_for_company(self, cik: str | int) -> PointInTimeResolver:
        """Build a :class:`PointInTimeResolver` over one filer's facts + availability.

        Joins the persisted sidecar availability (by ``filing_id``) with the
        Phase 4 canonical facts for the same filer, read from the canonical store.
        Requires a ``canonical_store`` to have been supplied.
        """
        if self._canonical is None:
            raise ValueError("resolver_for_company requires a canonical_store")
        company = _company_id(cik)
        availability = self._store.read_company_map(company)
        facts = self._facts_for_company(company)
        return PointInTimeResolver(facts, availability)

    def _facts_for_company(self, company_id: str) -> list[Fact]:
        """Read all canonical facts belonging to ``company_id`` from the store."""
        assert self._canonical is not None
        facts: list[Fact] = []
        for doc_id in self._canonical.list_document_ids():
            instance = self._canonical.read_instance(doc_id)
            if instance is None:
                continue
            facts.extend(f for f in instance if f.company_id == company_id)
        return facts

    def dataset_version_for_company(
        self, cik: str | int, *, transformation_version_id: str
    ) -> DatasetVersion:
        """Build the reproducible snapshot manifest for one filer's REVISED view.

        Pins the transformation version, the applied availability-policy set, and
        the (sorted) raw-document / fact id members for this filer — so a
        ``REVISED`` answer resolved against it is reproducible (§KS.2, invariant
        19). Requires a ``canonical_store``.
        """
        if self._canonical is None:
            raise ValueError("dataset_version_for_company requires a canonical_store")
        company = _company_id(cik)
        raw_document_ids: list[str] = []
        fact_ids: list[str] = []
        for doc_id in self._canonical.list_document_ids():
            instance = self._canonical.read_instance(doc_id)
            if instance is None:
                continue
            company_facts = [f for f in instance if f.company_id == company]
            if not company_facts:
                continue
            raw_document_ids.append(doc_id)
            fact_ids.extend(f.fact_id for f in company_facts)
        return DatasetVersion(
            transformation_version_id=transformation_version_id,
            availability_policy_ids=tuple(self.policy_ids),
            raw_document_ids=tuple(sorted(raw_document_ids)),
            fact_ids=tuple(sorted(fact_ids)),
        )
