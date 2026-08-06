"""End-to-end tests for the SEC client (mocked transport, real storage)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openfinance.sec.artifacts import sha256_hex
from openfinance.sec.client import SecClient
from openfinance.sec.config import SecConfig
from openfinance.sec.endpoints import (
    company_facts_url,
    company_tickers_url,
    submissions_page_url,
    submissions_url,
)
from openfinance.sec.errors import HttpStatusError
from openfinance.sec.retry import RetryingHttpClient
from openfinance.sec.storage import ArtifactStore
from openfinance.sec.throttle import RateLimiter
from openfinance.sec.transport import HttpResponse

from .fakes import UrlRoutedTransport, ok, status

CIK = 320193
UA = "OpenFinance test@example.com"


def _make_client(
    routes: dict[str, HttpResponse], tmp_path: Path
) -> tuple[SecClient, UrlRoutedTransport]:
    transport = UrlRoutedTransport(routes)
    limiter = RateLimiter(10, monotonic=lambda: 0.0, sleep=lambda _s: None)
    http = RetryingHttpClient(
        transport,
        limiter,
        max_retries=2,
        sleep=lambda _s: None,
        jitter=lambda w: w,
    )
    store = ArtifactStore(tmp_path)
    cfg = SecConfig(user_agent=UA, storage_dir=str(tmp_path))
    # Deterministic clock: identity must not depend on it.
    client = SecClient(cfg, http, store, clock=lambda: "2026-08-05T00:00:00+00:00")
    return client, transport


def test_acquire_company_tickers_stores_content_addressed(tmp_path: Path) -> None:
    body = b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}'
    client, transport = _make_client(
        {company_tickers_url(): ok(body, {"ETag": '"t1"'})}, tmp_path
    )
    result = client.acquire_company_tickers()
    assert result.sha256 == sha256_hex(body)
    assert result.blob_path.read_bytes() == body
    # Served from www.sec.gov, which requires the email-format User-Agent.
    assert transport.requests[0].headers["User-Agent"] == UA


def test_acquire_submissions_stores_content_addressed(tmp_path: Path) -> None:
    body = b'{"cik": "0000320193", "filings": {"recent": {}}}'
    client, transport = _make_client(
        {submissions_url(CIK): ok(body, {"ETag": '"abc"'})}, tmp_path
    )
    result = client.acquire_submissions(CIK)
    assert result.sha256 == sha256_hex(body)
    assert result.blob_path.read_bytes() == body
    # User-Agent was sent.
    assert transport.requests[0].headers["User-Agent"] == UA


def test_metadata_captures_provenance(tmp_path: Path) -> None:
    body = b'{"x": 1}'
    client, _ = _make_client(
        {
            company_facts_url(CIK): ok(
                body,
                {"Content-Type": "application/json", "ETag": '"v1"'},
            )
        },
        tmp_path,
    )
    result = client.acquire_company_facts(CIK)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert meta["source_url"] == company_facts_url(CIK)
    assert meta["artifact_type"] == "company_facts"
    assert meta["http_status"] == 200
    assert meta["content_type"] == "application/json"
    assert meta["content_length"] == len(body)
    assert meta["etag"] == '"v1"'
    assert meta["cik"] == str(CIK)
    assert meta["user_agent"] == UA


def test_403_raises_http_status_error(tmp_path: Path) -> None:
    client, _ = _make_client({submissions_url(CIK): status(403)}, tmp_path)
    with pytest.raises(HttpStatusError) as exc:
        client.acquire_submissions(CIK)
    assert exc.value.status == 403


def test_duplicate_acquisition_deduplicates(tmp_path: Path) -> None:
    body = b'{"same": true}'
    client, _ = _make_client({submissions_url(CIK): ok(body)}, tmp_path)
    first = client.acquire_submissions(CIK)
    second = client.acquire_submissions(CIK)
    assert first.sha256 == second.sha256
    assert not first.deduplicated
    assert second.deduplicated


def test_identity_is_independent_of_timestamp(tmp_path: Path) -> None:
    body = b"deterministic"
    transport = UrlRoutedTransport({submissions_url(CIK): ok(body)})
    limiter = RateLimiter(10, monotonic=lambda: 0.0, sleep=lambda _s: None)
    http = RetryingHttpClient(transport, limiter, max_retries=0)
    store = ArtifactStore(tmp_path)
    cfg = SecConfig(user_agent=UA, storage_dir=str(tmp_path))
    # Two different clocks -> same content address.
    c1 = SecClient(cfg, http, store, clock=lambda: "2020-01-01T00:00:00+00:00")
    r1 = c1.acquire_submissions(CIK)

    transport2 = UrlRoutedTransport({submissions_url(CIK): ok(body)})
    http2 = RetryingHttpClient(transport2, limiter, max_retries=0)
    c2 = SecClient(cfg, http2, store, clock=lambda: "2099-12-31T00:00:00+00:00")
    r2 = c2.acquire_submissions(CIK)
    assert r1.sha256 == r2.sha256


# -- pagination ---------------------------------------------------------------


def test_pagination_follows_overflow_pages(tmp_path: Path) -> None:
    # Primary page lists two overflow pages in filings.files.
    primary = json.dumps(
        {
            "cik": "0000320193",
            "filings": {
                "recent": {"accessionNumber": ["a-1"]},
                "files": [
                    {"name": "CIK0000320193-submissions-001.json"},
                    {"name": "CIK0000320193-submissions-002.json"},
                ],
            },
        }
    ).encode("utf-8")
    page1 = b'{"accessionNumber": ["a-2"]}'
    page2 = b'{"accessionNumber": ["a-3"]}'
    routes = {
        submissions_url(CIK): ok(primary),
        submissions_page_url("CIK0000320193-submissions-001.json"): ok(page1),
        submissions_page_url("CIK0000320193-submissions-002.json"): ok(page2),
    }
    client, transport = _make_client(routes, tmp_path)

    pages = list(client.iter_submissions_pages(CIK))
    assert len(pages) == 3  # primary + 2 overflow
    assert pages[0].overflow_pages == [
        "CIK0000320193-submissions-001.json",
        "CIK0000320193-submissions-002.json",
    ]
    # Overflow pages report no further pages.
    assert pages[1].overflow_pages == []
    assert pages[2].overflow_pages == []
    # All three URLs were actually fetched — proving the first response is not
    # assumed to be the complete inventory.
    fetched = {r.url for r in transport.requests}
    assert fetched == set(routes)


def test_pagination_with_no_overflow(tmp_path: Path) -> None:
    primary = json.dumps(
        {"filings": {"recent": {"accessionNumber": []}, "files": []}}
    ).encode("utf-8")
    client, _ = _make_client({submissions_url(CIK): ok(primary)}, tmp_path)
    pages = list(client.iter_submissions_pages(CIK))
    assert len(pages) == 1
    assert pages[0].overflow_pages == []


# -- conditional requests -----------------------------------------------------


def test_conditional_request_reuses_stored_bytes_on_304(tmp_path: Path) -> None:
    body = b'{"v": 1}'
    # First fetch: 200 with an ETag. Second fetch: 304 Not Modified.
    transport = UrlRoutedTransport({})
    limiter = RateLimiter(10, monotonic=lambda: 0.0, sleep=lambda _s: None)
    http = RetryingHttpClient(transport, limiter, max_retries=0)
    store = ArtifactStore(tmp_path)
    cfg = SecConfig(user_agent=UA, storage_dir=str(tmp_path))
    client = SecClient(cfg, http, store, clock=lambda: "2026-08-05T00:00:00+00:00")

    url = submissions_url(CIK)
    transport._routes[url] = ok(body, {"ETag": '"v1"'})
    first = client.acquire_submissions(CIK)

    # Now the server would answer 304; the client should send If-None-Match and
    # reuse the stored blob.
    transport._routes[url] = HttpResponse(status=304, headers={}, body=b"")
    second = client.acquire_submissions(CIK)

    assert second.sha256 == first.sha256
    assert second.deduplicated  # reused existing blob
    # The conditional header was sent on the second request.
    last = transport.requests[-1]
    assert last.headers.get("If-None-Match") == '"v1"'
