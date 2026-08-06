"""The canonicalization façade — read raw facts, canonicalize, persist (req. 19).

This is the public entry point of Phase 4. It composes the pieces without
introducing a second HTTP client or an unrelated storage system (requirement 18):

    Phase 3 RawXbrlStore ─(RawDocument + RawFacts)─▶ Canonicalizer ─▶ CanonicalFactStore
                                                                          (derived)

It reads the immutable raw facts back from the Phase 3
:class:`~openfinance.xbrl.store.RawXbrlStore`, canonicalizes them offline (no
network I/O), and writes the deterministic canonical representation to the
:class:`~openfinance.canonical.store.CanonicalFactStore`.

Guarantees preserved end-to-end:

* **Raw facts are never rewritten** — the Phase 3 store is read-only here, and the
  Phase 1 blobs it references are never touched (requirements, invariant 1, 5).
* **Offline** — canonicalization consumes only already-derived raw records
  (requirement 16 validation runs against stores populated by Phases 1-3).
* **Deterministic & fail-closed** — every canonical id and file is a pure function
  of the raw records + normalizer version; contradictory input raises
  (requirements 14, 17).
"""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.canonical.canonicalize import Canonicalizer, CanonicalizeResult
from openfinance.canonical.store import CanonicalFactStore
from openfinance.canonical.version import CanonicalFactVersion
from openfinance.registry.identity import company_id as _company_id
from openfinance.xbrl.store import RawXbrlStore

__all__ = ["CanonicalizationIngestor", "CanonicalizeIngestResult"]


@dataclass(frozen=True, slots=True)
class CanonicalizeIngestResult:
    """Outcome of canonicalizing one raw instance and persisting its facts."""

    result: CanonicalizeResult
    raw_document_id: str

    @property
    def fact_count(self) -> int:
        return self.result.fact_count

    @property
    def raw_fact_count(self) -> int:
        return self.result.raw_fact_count


class CanonicalizationIngestor:
    """Canonicalize stored raw XBRL facts into a deterministic canonical store."""

    def __init__(
        self,
        raw_store: RawXbrlStore,
        canonical_store: CanonicalFactStore,
        *,
        version: CanonicalFactVersion | None = None,
    ) -> None:
        self._raw = raw_store
        self._canonical = canonical_store
        self._canonicalizer = Canonicalizer(version=version)

    @property
    def version(self) -> CanonicalFactVersion:
        return self._canonicalizer.version

    def canonicalize_document(self, raw_document_id: str) -> CanonicalizeIngestResult:
        """Canonicalize one stored raw instance by ``raw_document_id``.

        Reads the raw records from the Phase 3 store, canonicalizes them offline,
        persists the canonical facts, and returns the result. Raises
        ``KeyError`` if the instance is not present in the raw store (we never
        fabricate raw material).
        """
        read = self._raw.read_instance(raw_document_id)
        if read is None:
            raise KeyError(f"no raw instance stored for {raw_document_id!r}")
        document, contexts, units, facts = read
        result = self._canonicalizer.canonicalize_records(
            document=document,
            contexts=contexts,
            units=units,
            facts=tuple(facts),
        )
        self._canonical.write_instance(
            result, self._canonicalizer.version.transformation_version_id
        )
        return CanonicalizeIngestResult(result=result, raw_document_id=raw_document_id)

    def canonicalize_all(self) -> list[CanonicalizeIngestResult]:
        """Canonicalize every raw instance in the raw store, offline.

        Results are returned sorted by ``raw_document_id`` for a deterministic
        caller-visible order.
        """
        results = [
            self.canonicalize_document(doc_id)
            for doc_id in self._raw.list_document_ids()
        ]
        return sorted(results, key=lambda r: r.raw_document_id)

    def canonicalize_company(self, cik: str | int) -> list[CanonicalizeIngestResult]:
        """Canonicalize every stored raw instance belonging to one filer, offline.

        Filters the raw store's instances to those whose ``company_id`` matches
        ``cik`` (via the Phase 2 canonical function), so identity never diverges
        from the registry. Results are sorted by ``raw_document_id``.
        """
        target = _company_id(cik)
        results: list[CanonicalizeIngestResult] = []
        for doc_id in self._raw.list_document_ids():
            read = self._raw.read_instance(doc_id)
            if read is None:
                continue
            document, _, _, _ = read
            if document.company_id != target:
                continue
            results.append(self.canonicalize_document(doc_id))
        return sorted(results, key=lambda r: r.raw_document_id)
