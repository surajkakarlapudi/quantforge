"""The raw-XBRL ingestion façade — locate instances, parse, persist.

This is the public entry point of Phase 3. It composes the pieces without
introducing a second HTTP client or a second storage system (requirement 16):

    Phase 1 ArtifactStore ─(XBRL_INSTANCE blobs)─▶ parse_instance ─▶ RawXbrlStore
             ▲                                                          (derived)
    Phase 2 FilingRegistry ─(filing_id / company_id / accession)─┘

It reads the exact instance bytes from the Phase 1 content-addressed store,
attributes them to a filing via the Phase 2 registry's provenance (accession +
CIK on the artifact metadata), parses them offline (no network I/O), and writes
the deterministic derived representation to the :class:`RawXbrlStore`.

Guarantees preserved end-to-end:

* **Bytes are never rewritten** — the parser receives the exact stored bytes and
  the Phase 1 blob is read-only (requirements 2, 16).
* **Offline** — parsing consumes only already-acquired artifacts (requirement 20
  validation runs against a store populated by Phase 1; acquisition stays in
  Phase 1).
* **Deterministic & fail-closed** — every derived id and file is a pure function
  of the bytes + parser version; malformed instances raise (requirements 12, 13).
"""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.registry.identity import (
    canonical_accession,
)
from openfinance.registry.identity import (
    company_id as _company_id,
)
from openfinance.registry.identity import (
    filing_id as _filing_id,
)
from openfinance.sec.artifacts import AcquisitionMetadata, ArtifactType
from openfinance.sec.storage import ArtifactStore
from openfinance.xbrl.errors import XbrlError
from openfinance.xbrl.parser import ParsedInstance, SourceIdentity, parse_instance
from openfinance.xbrl.store import RawXbrlStore
from openfinance.xbrl.version import XbrlParserVersion

__all__ = ["IngestResult", "XbrlIngestor", "source_identity_from_metadata"]


def source_identity_from_metadata(
    metadata: AcquisitionMetadata,
) -> SourceIdentity:
    """Build a :class:`SourceIdentity` from a Phase 1 artifact's provenance.

    The filing and company identities are derived with the **Phase 2** canonical
    functions (accession → ``filing_id``, CIK → ``company_id``), so Phase 3
    attributes facts to exactly the same identities the registry uses — never a
    second, divergent identity scheme (requirement 16). The artifact must carry
    both a CIK and an accession in its acquisition provenance; without them the
    instance cannot be attributed to a filing offline, and we fail closed rather
    than guess (requirement 7, 12).
    """
    if metadata.accession is None or metadata.accession == "":
        raise XbrlError(
            "cannot attribute XBRL instance to a filing: acquisition metadata "
            f"for {metadata.sha256} has no accession"
        )
    if metadata.cik is None or metadata.cik == "":
        raise XbrlError(
            "cannot attribute XBRL instance to a filing: acquisition metadata "
            f"for {metadata.sha256} has no CIK"
        )
    accession = canonical_accession(metadata.accession)
    source_document_name = _basename(metadata.source_url)
    return SourceIdentity(
        filing_id=_filing_id(accession),
        accession=accession,
        company_id=_company_id(metadata.cik),
        source_artifact_sha256=metadata.sha256,
        source_url=metadata.source_url,
        source_document_name=source_document_name,
        source_artifact_type=metadata.artifact_type,
    )


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of ingesting one XBRL instance artifact."""

    parsed: ParsedInstance
    #: ``raw_document_id`` of the parsed instance (content address of its bytes).
    raw_document_id: str
    #: Number of raw facts extracted.
    fact_count: int


class XbrlIngestor:
    """Parse stored XBRL instances into a deterministic raw-fact store."""

    def __init__(
        self,
        artifact_store: ArtifactStore,
        raw_store: RawXbrlStore,
        *,
        version: XbrlParserVersion | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._raw = raw_store
        self._version = version or XbrlParserVersion()

    @property
    def version(self) -> XbrlParserVersion:
        return self._version

    def ingest_artifact(self, metadata: AcquisitionMetadata) -> IngestResult:
        """Parse one XBRL-instance artifact identified by its Phase 1 metadata.

        Reads the exact bytes from the Phase 1 store (which re-verifies the
        content hash on read), parses them offline, persists the deterministic
        derived representation, and returns the result.
        """
        if metadata.artifact_type is not ArtifactType.XBRL_INSTANCE:
            raise XbrlError(
                f"artifact {metadata.sha256} is {metadata.artifact_type.value}, "
                "not an XBRL instance"
            )
        identity = source_identity_from_metadata(metadata)
        data = self._artifacts.read_blob(metadata.sha256)
        parsed = parse_instance(data, identity, self._version)
        self._raw.write_instance(parsed, self._version.transformation_version_id)
        return IngestResult(
            parsed=parsed,
            raw_document_id=parsed.document.raw_document_id,
            fact_count=len(parsed.facts),
        )

    def ingest_company_from_store(self, cik: str | int) -> list[IngestResult]:
        """Ingest every stored XBRL instance for one filer, offline.

        Iterates the Phase 1 store's metadata (read-only), selects the
        ``XBRL_INSTANCE`` artifacts whose provenance CIK matches ``cik``, parses
        each, and persists it. Results are returned sorted by ``raw_document_id``
        for a deterministic caller-visible order.
        """
        target = _company_id(cik)
        results: list[IngestResult] = []
        for metadata in self._artifacts.iter_metadata():
            if metadata.artifact_type is not ArtifactType.XBRL_INSTANCE:
                continue
            if metadata.cik is None or metadata.cik == "":
                continue
            if _company_id(metadata.cik) != target:
                continue
            results.append(self.ingest_artifact(metadata))
        return sorted(results, key=lambda r: r.raw_document_id)


def _basename(url: str) -> str | None:
    """Return the trailing path segment of a URL (the document filename)."""
    tail = url.rsplit("/", 1)[-1]
    return tail or None
