"""The SEC acquisition client.

:class:`SecClient` composes the lower layers into a single façade that safely
*retrieves and preserves* SEC source material:

    transport  →  retry/backoff + throttle  →  client  →  content-addressed store

Every ``acquire_*`` method fetches one URL, records full provenance, and writes
an immutable content-addressed artifact — returning an
:class:`~openfinance.sec.storage.StoreResult`. Nothing here parses SEC content;
parsing belongs to later phases.

The client also implements submissions filing-history pagination
(:meth:`iter_submissions_pages`), because the first submissions response is not
the complete inventory for prolific filers — older filings spill onto overflow
pages listed in ``filings.files``.

Determinism: artifact identity is the SHA-256 of the bytes. Retrieval
timestamps are provenance only and are supplied by an injected clock so the
identity is never derived from wall-clock time or randomness.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from openfinance.sec.config import SecConfig
from openfinance.sec.endpoints import (
    canonical_cik,
    company_facts_url,
    company_tickers_url,
    filing_document_url,
    filing_index_url,
    submissions_page_url,
    submissions_url,
)
from openfinance.sec.errors import HttpStatusError
from openfinance.sec.retry import RetryingHttpClient
from openfinance.sec.storage import ArtifactStore, StoreResult
from openfinance.sec.transport import HttpRequest

__all__ = ["SecClient", "SubmissionsPage"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SubmissionsPage:
    """One retrieved submissions page plus its parsed pagination pointers.

    ``overflow_pages`` are the filenames listed in ``filings.files`` on the
    *primary* page (empty on overflow pages). Parsing is confined to reading
    those pointers — the artifact itself is stored verbatim.
    """

    __slots__ = ("overflow_pages", "result")

    def __init__(self, result: StoreResult, overflow_pages: list[str]) -> None:
        self.result = result
        self.overflow_pages = overflow_pages


class SecClient:
    """High-level, storage-backed SEC acquisition client."""

    def __init__(
        self,
        config: SecConfig,
        http: RetryingHttpClient,
        store: ArtifactStore,
        *,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._config = config
        self._http = http
        self._store = store
        self._clock = clock

    @property
    def store(self) -> ArtifactStore:
        """The content-addressed store backing this client (read access)."""
        return self._store

    # -- low-level acquisition ------------------------------------------------

    def acquire(
        self,
        url: str,
        artifact_type: ArtifactType,
        *,
        cik: str | None = None,
        accession: str | None = None,
    ) -> StoreResult:
        """Fetch ``url``, capture provenance, and store an immutable artifact.

        Conditional requests are issued automatically when a prior artifact for
        this exact URL is known: a ``304 Not Modified`` reuses the stored
        bytes (recording a fresh provenance record against the same hash)
        rather than downloading again.
        """
        headers = {"User-Agent": self._config.user_agent}
        prior = self._find_prior(url)
        if prior is not None:
            if prior.etag:
                headers["If-None-Match"] = prior.etag
            if prior.last_modified:
                headers["If-Modified-Since"] = prior.last_modified

        request = HttpRequest(
            url=url,
            headers=headers,
            timeout_seconds=self._config.timeout_seconds,
        )
        response = self._http.send(request)

        if response.status == 304 and prior is not None:
            # Server confirms our stored copy is current. Re-record provenance
            # against the unchanged content address.
            return self._store_bytes(
                self._store.read_blob(prior.sha256),
                url,
                artifact_type,
                http_status=304,
                response_headers=response.headers,
                cik=cik,
                accession=accession,
            )

        if response.status != 200:
            raise HttpStatusError(response.status, url)

        return self._store_bytes(
            response.body,
            url,
            artifact_type,
            http_status=response.status,
            response_headers=response.headers,
            cik=cik,
            accession=accession,
        )

    def _store_bytes(
        self,
        data: bytes,
        url: str,
        artifact_type: ArtifactType,
        *,
        http_status: int,
        response_headers: dict[str, str],
        cik: str | None,
        accession: str | None,
    ) -> StoreResult:
        sha = sha256_hex(data)
        metadata = AcquisitionMetadata(
            source_url=url,
            artifact_type=artifact_type,
            sha256=sha,
            retrieved_at=self._clock(),
            http_status=http_status,
            user_agent=self._config.user_agent,
            content_type=_header(response_headers, "Content-Type"),
            content_length=len(data),
            etag=_header(response_headers, "ETag"),
            last_modified=_header(response_headers, "Last-Modified"),
            cik=cik,
            accession=accession,
        )
        return self._store.store(Artifact(data=data, metadata=metadata))

    def _find_prior(self, url: str) -> AcquisitionMetadata | None:
        """Best-effort lookup of the newest prior metadata for ``url``.

        Used only to populate conditional-request validators. Absence simply
        means we fetch unconditionally.
        """
        newest: AcquisitionMetadata | None = None
        meta_root = self._store.root / "meta"
        if not meta_root.exists():
            return None
        for meta_file in meta_root.rglob("*.json"):
            try:
                raw = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("source_url") != url:
                continue
            retrieved = raw.get("retrieved_at", "")
            if newest is None or retrieved > newest.retrieved_at:
                newest = AcquisitionMetadata(
                    source_url=raw["source_url"],
                    artifact_type=ArtifactType(raw["artifact_type"]),
                    sha256=raw["sha256"],
                    retrieved_at=retrieved,
                    http_status=raw.get("http_status", 0),
                    user_agent=raw.get("user_agent", ""),
                    etag=raw.get("etag"),
                    last_modified=raw.get("last_modified"),
                )
        return newest

    # -- typed acquisition helpers -------------------------------------------

    def acquire_submissions(self, cik: str | int) -> StoreResult:
        """Acquire the primary submissions JSON (``filings.recent``)."""
        return self.acquire(
            submissions_url(cik),
            ArtifactType.SUBMISSIONS,
            cik=canonical_cik(cik),
        )

    def acquire_company_facts(self, cik: str | int) -> StoreResult:
        return self.acquire(
            company_facts_url(cik),
            ArtifactType.COMPANY_FACTS,
            cik=canonical_cik(cik),
        )

    def acquire_company_tickers(self) -> StoreResult:
        """Acquire the official SEC ticker → CIK mapping (``company_tickers.json``).

        A single filer-agnostic document; not keyed by CIK. Stored as an
        immutable content-addressed artifact so repeated resolution is served
        offline from the cache (conditional requests reuse the stored bytes).
        """
        return self.acquire(company_tickers_url(), ArtifactType.COMPANY_TICKERS)

    def acquire_filing_index(self, cik: str | int, accession: str) -> StoreResult:
        return self.acquire(
            filing_index_url(cik, accession),
            ArtifactType.FILING_INDEX,
            cik=canonical_cik(cik),
            accession=accession,
        )

    def acquire_filing_document(
        self,
        cik: str | int,
        accession: str,
        filename: str,
        artifact_type: ArtifactType = ArtifactType.FILING_DOCUMENT,
    ) -> StoreResult:
        """Acquire one named file from a filing package.

        ``artifact_type`` lets callers tag XBRL components (instance, schema,
        cal/def/lab/pre) precisely; it defaults to a generic filing document.
        """
        return self.acquire(
            filing_document_url(cik, accession, filename),
            artifact_type,
            cik=canonical_cik(cik),
            accession=accession,
        )

    # -- pagination -----------------------------------------------------------

    def acquire_submissions_page(
        self, page_filename: str, cik: str | int | None = None
    ) -> StoreResult:
        """Acquire one overflow submissions page by filename."""
        return self.acquire(
            submissions_page_url(page_filename),
            ArtifactType.SUBMISSIONS,
            cik=canonical_cik(cik) if cik is not None else None,
        )

    def iter_submissions_pages(self, cik: str | int) -> Iterator[SubmissionsPage]:
        """Yield every submissions page for ``cik``, following overflow.

        The primary page is fetched first; its ``filings.files[*].name`` list
        is then followed page by page. Every page is stored as an immutable
        artifact and yielded so callers can drive their own bookkeeping. This
        makes explicit that the primary response is *not* the complete filing
        history for prolific filers.
        """
        result = self.acquire_submissions(cik)
        overflow = self._parse_overflow_pages(result)
        yield SubmissionsPage(result, overflow)

        # ``filings.files`` only appears on the primary page; overflow pages do
        # not chain further, so a single pass over the discovered list covers
        # the entire history.
        for page_filename in overflow:
            page_result = self.acquire_submissions_page(page_filename, cik)
            yield SubmissionsPage(page_result, [])

    def _parse_overflow_pages(self, result: StoreResult) -> list[str]:
        data = self._store.read_blob(result.sha256)
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return []
        files = parsed.get("filings", {}).get("files", [])
        return [
            entry["name"]
            for entry in files
            if isinstance(entry, dict) and "name" in entry
        ]


def _header(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None
