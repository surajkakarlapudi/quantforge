"""Resolve user-facing identifiers (ticker / CIK / name) to a filer identity.

:class:`CompanyResolver` turns ``"AAPL"``, ``320193``, ``"CIK0000320193"``, or an
exact company title into a :class:`CompanyIdentity` carrying the canonical
``company_id`` used across Phases 2-5.

Design commitments:

* **Official data only.** Ticker/name resolution uses SEC's
  ``company_tickers.json`` (via the Phase 1 content-addressed store), never a
  hardcoded table. The mapping is fetched at most once and then served offline
  from the cache; repeated lookups touch no network.
* **Cache-first, offline-capable.** The resolver reads the cached mapping from
  the artifact store; only if it is absent *and* a network client was supplied
  does it acquire it. With no client and no cache, ticker/name resolution fails
  closed (:class:`TickerMapUnavailableError`) — CIK resolution still works,
  because it needs no mapping.
* **Fail closed.** An unknown or ambiguous symbol raises; a CIK is never
  fabricated or guessed.
"""

from __future__ import annotations

from typing import Protocol

from openfinance.identity.errors import TickerMapUnavailableError
from openfinance.identity.model import CompanyIdentity, ResolutionSource
from openfinance.identity.tickers import TickerMap
from openfinance.sec.artifacts import ArtifactType
from openfinance.sec.endpoints import canonical_cik
from openfinance.sec.storage import ArtifactStore, StoreResult

__all__ = ["CompanyResolver", "TickerClient", "looks_like_cik"]


class TickerClient(Protocol):
    """The one acquisition capability the resolver needs from a network client.

    :class:`~openfinance.sec.client.SecClient` satisfies this structurally. It is
    narrowed to a Protocol so the resolver depends only on the single method it
    uses (cache-filling), never the whole client — and tests can substitute a
    trivial double.
    """

    def acquire_company_tickers(self) -> StoreResult: ...


def looks_like_cik(identifier: str) -> bool:
    """True if ``identifier`` is unambiguously a CIK (digits or ``CIK`` prefix).

    A bare integer string (``"320193"``, ``"0000320193"``) or a ``CIK``-prefixed
    string is treated as a CIK; anything containing a non-digit after optional
    ``CIK`` stripping is treated as a ticker/name. Tickers are never all-digits,
    so this split is unambiguous.
    """
    value = identifier.strip()
    if value.upper().startswith("CIK"):
        value = value[3:]
    return value.isdigit() and value != ""


class CompanyResolver:
    """Resolve identifiers to :class:`CompanyIdentity` using official SEC data."""

    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        client: TickerClient | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._client = client
        self._ticker_map: TickerMap | None = None

    # -- public resolution ---------------------------------------------------

    def resolve(self, identifier: str, *, by: str | None = None) -> CompanyIdentity:
        """Resolve ``identifier`` to a :class:`CompanyIdentity`.

        ``by`` optionally forces the interpretation: ``"cik"``, ``"ticker"``, or
        ``"name"``. When omitted, an all-digit / ``CIK``-prefixed value is taken
        as a CIK and everything else is looked up as a ticker first, then as an
        exact company title. Fails closed on unknown/ambiguous input.
        """
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("identifier must be a non-empty string")

        if by is not None:
            return self._resolve_by(identifier, by)

        if looks_like_cik(identifier):
            return self._resolve_cik(identifier)
        return self._resolve_symbol(identifier)

    # -- resolution strategies ----------------------------------------------

    def _resolve_by(self, identifier: str, by: str) -> CompanyIdentity:
        strategy = by.strip().lower()
        if strategy == "cik":
            return self._resolve_cik(identifier)
        if strategy == "ticker":
            return self._resolve_ticker(identifier)
        if strategy == "name":
            return self._resolve_name(identifier)
        raise ValueError(f"unknown resolution mode by={by!r}; use cik/ticker/name")

    def _resolve_cik(self, identifier: str) -> CompanyIdentity:
        cik = canonical_cik(identifier)
        # Enrich with ticker/title if the official mapping is available; a CIK
        # absent from the mapping (no assigned ticker) still resolves fine.
        entry = None
        ticker_map = self._maybe_ticker_map()
        if ticker_map is not None:
            entry = ticker_map.entry_for_cik(cik)
        return CompanyIdentity.from_cik(
            cik,
            resolved_from=identifier,
            source=ResolutionSource.CIK,
            ticker=entry.ticker if entry is not None else None,
            name=entry.title if entry is not None else None,
        )

    def _resolve_ticker(self, identifier: str) -> CompanyIdentity:
        ticker_map = self._require_ticker_map()
        cik = ticker_map.cik_for_ticker(identifier)
        entry = ticker_map.entry_for_cik(cik)
        return CompanyIdentity.from_cik(
            cik,
            resolved_from=identifier,
            source=ResolutionSource.TICKER,
            ticker=entry.ticker if entry is not None else None,
            name=entry.title if entry is not None else None,
        )

    def _resolve_name(self, identifier: str) -> CompanyIdentity:
        ticker_map = self._require_ticker_map()
        cik = ticker_map.cik_for_title(identifier)
        entry = ticker_map.entry_for_cik(cik)
        return CompanyIdentity.from_cik(
            cik,
            resolved_from=identifier,
            source=ResolutionSource.NAME,
            ticker=entry.ticker if entry is not None else None,
            name=entry.title if entry is not None else None,
        )

    def _resolve_symbol(self, identifier: str) -> CompanyIdentity:
        # Ticker first (the common case), then fall back to an exact title.
        from openfinance.identity.errors import UnknownSymbolError

        ticker_map = self._require_ticker_map()
        try:
            cik = ticker_map.cik_for_ticker(identifier)
            source = ResolutionSource.TICKER
        except UnknownSymbolError:
            cik = ticker_map.cik_for_title(identifier)
            source = ResolutionSource.NAME
        entry = ticker_map.entry_for_cik(cik)
        return CompanyIdentity.from_cik(
            cik,
            resolved_from=identifier,
            source=source,
            ticker=entry.ticker if entry is not None else None,
            name=entry.title if entry is not None else None,
        )

    # -- ticker map loading (cache-first, offline-capable) -------------------

    def _require_ticker_map(self) -> TickerMap:
        ticker_map = self._maybe_ticker_map()
        if ticker_map is None:
            raise TickerMapUnavailableError()
        return ticker_map

    def _maybe_ticker_map(self) -> TickerMap | None:
        """Load the official mapping cache-first; fetch once if a client exists.

        Returns ``None`` only when the mapping is neither cached nor fetchable
        (no client wired) — callers that need it turn that into a fail-closed
        error, while CIK resolution tolerates its absence.
        """
        if self._ticker_map is not None:
            return self._ticker_map

        cached = self._load_cached_bytes()
        if cached is None and self._client is not None:
            # Not cached yet — acquire it once into the content-addressed store,
            # then read it straight back so all later lookups are offline.
            result = self._client.acquire_company_tickers()
            cached = self._artifacts.read_blob(result.sha256)
        if cached is None:
            return None

        self._ticker_map = TickerMap.from_bytes(cached)
        return self._ticker_map

    def _load_cached_bytes(self) -> bytes | None:
        """Read the newest cached ``company_tickers.json`` bytes, or ``None``.

        Chooses the most recently retrieved tickers artifact (by provenance
        ``retrieved_at``) for freshness; deterministic given a fixed store.
        """
        newest_sha: str | None = None
        newest_retrieved = ""
        for meta in self._artifacts.iter_metadata():
            if meta.artifact_type is not ArtifactType.COMPANY_TICKERS:
                continue
            if newest_sha is None or meta.retrieved_at > newest_retrieved:
                newest_sha = meta.sha256
                newest_retrieved = meta.retrieved_at
        if newest_sha is None:
            return None
        return self._artifacts.read_blob(newest_sha)
