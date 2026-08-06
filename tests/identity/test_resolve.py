"""Tests for CompanyResolver: ticker/CIK/name resolution, caching, offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.identity.errors import (
    TickerMapUnavailableError,
    UnknownSymbolError,
)
from openfinance.identity.model import ResolutionSource
from openfinance.identity.resolve import CompanyResolver, looks_like_cik
from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from openfinance.sec.storage import ArtifactStore, StoreResult

TICKERS = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":1318605,"ticker":"TSLA","title":"Tesla, Inc."}}'
)


def _store_tickers(store: ArtifactStore, data: bytes, *, retrieved_at: str) -> str:
    sha = sha256_hex(data)
    meta = AcquisitionMetadata(
        source_url="https://www.sec.gov/files/company_tickers.json",
        artifact_type=ArtifactType.COMPANY_TICKERS,
        sha256=sha,
        retrieved_at=retrieved_at,
        http_status=200,
        user_agent="test test@example.com",
    )
    store.store(Artifact(data=data, metadata=meta))
    return sha


class _CountingClient:
    """A fake SecClient that stores the tickers doc and counts fetches."""

    def __init__(self, store: ArtifactStore, data: bytes) -> None:
        self._store = store
        self._data = data
        self.fetches = 0

    def acquire_company_tickers(self) -> StoreResult:
        self.fetches += 1
        sha = _store_tickers(
            self._store, self._data, retrieved_at="2026-01-01T00:00:00"
        )
        return StoreResult(
            sha,
            self._store.blob_path(sha),
            self._store.blob_path(sha),
            deduplicated=False,
        )


# -- looks_like_cik ---------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("320193", True),
        ("0000320193", True),
        ("CIK0000320193", True),
        ("cik320193", True),
        ("AAPL", False),
        ("BRK-B", False),
        ("Apple Inc.", False),
    ],
)
def test_looks_like_cik(value: str, expected: bool) -> None:
    assert looks_like_cik(value) is expected


# -- resolution from cache (offline) ----------------------------------------


def test_resolve_ticker_from_cache_offline(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)  # no client → offline only

    ident = resolver.resolve("AAPL")
    assert ident.company_id == "cik:0000320193"
    assert ident.cik == "320193"
    assert ident.ticker == "AAPL"
    assert ident.name == "Apple Inc."
    assert ident.source is ResolutionSource.TICKER
    assert ident.resolved_from == "AAPL"


def test_resolve_name_fallback(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)

    ident = resolver.resolve("Tesla, Inc.")
    assert ident.cik == "1318605"
    assert ident.source is ResolutionSource.NAME


def test_resolve_cik_needs_no_mapping(tmp_path: Path) -> None:
    # CIK resolution works with no cache and no client at all.
    resolver = CompanyResolver(ArtifactStore(tmp_path))
    ident = resolver.resolve("320193")
    assert ident.company_id == "cik:0000320193"
    assert ident.cik == "320193"
    assert ident.source is ResolutionSource.CIK
    # No mapping cached → no ticker/name enrichment, but still resolves.
    assert ident.ticker is None


def test_resolve_cik_enriched_when_mapping_present(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)
    ident = resolver.resolve("CIK0000320193")
    assert ident.source is ResolutionSource.CIK
    assert ident.ticker == "AAPL"


def test_ticker_without_cache_or_client_fails_closed(tmp_path: Path) -> None:
    resolver = CompanyResolver(ArtifactStore(tmp_path))
    with pytest.raises(TickerMapUnavailableError):
        resolver.resolve("AAPL")


def test_unknown_ticker_fails_closed(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)
    with pytest.raises(UnknownSymbolError):
        resolver.resolve("NOPE")


def test_empty_identifier_rejected(tmp_path: Path) -> None:
    resolver = CompanyResolver(ArtifactStore(tmp_path))
    with pytest.raises(ValueError, match="non-empty"):
        resolver.resolve("   ")


def test_explicit_by_mode(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)
    # Force name lookup; a value that also isn't a ticker.
    ident = resolver.resolve("Apple Inc.", by="name")
    assert ident.cik == "320193"
    with pytest.raises(ValueError, match="unknown resolution mode"):
        resolver.resolve("AAPL", by="bogus")


# -- caching / fetch-once ---------------------------------------------------


def test_fetches_once_then_serves_offline(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    client = _CountingClient(store, TICKERS)
    resolver = CompanyResolver(store, client=client)

    a = resolver.resolve("AAPL")
    b = resolver.resolve("TSLA")
    assert a.cik == "320193"
    assert b.cik == "1318605"
    # One network fetch total: the map is parsed once and reused in-process.
    assert client.fetches == 1


def test_uses_existing_cache_without_fetching(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    _store_tickers(store, TICKERS, retrieved_at="2026-01-01T00:00:00")
    client = _CountingClient(store, TICKERS)
    resolver = CompanyResolver(store, client=client)

    resolver.resolve("AAPL")
    # Cache present → client never called.
    assert client.fetches == 0


def test_new_resolver_reuses_disk_cache(tmp_path: Path) -> None:
    # First resolver fetches; a fresh resolver over the same store is offline.
    store = ArtifactStore(tmp_path)
    client = _CountingClient(store, TICKERS)
    CompanyResolver(store, client=client).resolve("AAPL")
    assert client.fetches == 1

    offline = CompanyResolver(store)  # no client
    ident = offline.resolve("AAPL")
    assert ident.cik == "320193"


def test_picks_newest_cached_mapping(tmp_path: Path) -> None:
    # If two tickers artifacts exist, the newest retrieved_at wins.
    store = ArtifactStore(tmp_path)
    old = b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Old Name"}}'
    new = b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}'
    _store_tickers(store, old, retrieved_at="2020-01-01T00:00:00")
    _store_tickers(store, new, retrieved_at="2026-01-01T00:00:00")
    resolver = CompanyResolver(store)
    assert resolver.resolve("AAPL").name == "Apple Inc."
