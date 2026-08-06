"""Tests for retry/backoff behaviour."""

from __future__ import annotations

import pytest

from openfinance.sec.errors import HttpStatusError, TransportError
from openfinance.sec.retry import RetryingHttpClient
from openfinance.sec.throttle import RateLimiter
from openfinance.sec.transport import HttpRequest

from .fakes import NoopSleep, ProgrammedTransport, ok, status

REQ = HttpRequest("https://data.sec.gov/x")


def _limiter() -> RateLimiter:
    # A limiter that never actually blocks (injected no-op sleep/clock).
    return RateLimiter(10, monotonic=lambda: 0.0, sleep=lambda _s: None)


def _client(
    transport: ProgrammedTransport, *, max_retries: int, sleep: NoopSleep
) -> RetryingHttpClient:
    return RetryingHttpClient(
        transport,
        _limiter(),
        max_retries=max_retries,
        sleep=sleep,
        jitter=lambda window: window,  # deterministic: full window
    )


def test_success_on_first_try() -> None:
    transport = ProgrammedTransport([ok(b"data")])
    sleep = NoopSleep()
    resp = _client(transport, max_retries=3, sleep=sleep).send(REQ)
    assert resp.body == b"data"
    assert transport.call_count == 1
    assert sleep.calls == []


def test_retries_on_429_then_succeeds() -> None:
    transport = ProgrammedTransport([status(429), ok(b"data")])
    sleep = NoopSleep()
    resp = _client(transport, max_retries=3, sleep=sleep).send(REQ)
    assert resp.body == b"data"
    assert transport.call_count == 2
    assert len(sleep.calls) == 1


def test_retries_on_500_then_succeeds() -> None:
    transport = ProgrammedTransport([status(500), status(503), ok(b"ok")])
    sleep = NoopSleep()
    resp = _client(transport, max_retries=3, sleep=sleep).send(REQ)
    assert resp.status == 200
    assert transport.call_count == 3


def test_gives_up_after_max_retries_on_retryable_status() -> None:
    transport = ProgrammedTransport([status(503)] * 4)
    sleep = NoopSleep()
    with pytest.raises(HttpStatusError) as exc:
        _client(transport, max_retries=2, sleep=sleep).send(REQ)
    assert exc.value.status == 503
    assert exc.value.attempts == 3  # 1 initial + 2 retries
    assert transport.call_count == 3


def test_403_is_not_retried() -> None:
    transport = ProgrammedTransport([status(403)])
    sleep = NoopSleep()
    # 403 is a permanent client error; the client returns it for the caller to
    # interpret rather than retrying.
    resp = _client(transport, max_retries=3, sleep=sleep).send(REQ)
    assert resp.status == 403
    assert transport.call_count == 1
    assert sleep.calls == []


def test_transport_error_is_retried_then_reraised() -> None:
    transport = ProgrammedTransport(
        [TransportError("reset"), TransportError("reset"), TransportError("reset")]
    )
    sleep = NoopSleep()
    with pytest.raises(TransportError):
        _client(transport, max_retries=2, sleep=sleep).send(REQ)
    assert transport.call_count == 3


def test_transport_error_recovers() -> None:
    transport = ProgrammedTransport([TransportError("reset"), ok(b"back")])
    sleep = NoopSleep()
    resp = _client(transport, max_retries=2, sleep=sleep).send(REQ)
    assert resp.body == b"back"


def test_retry_after_header_is_honoured() -> None:
    transport = ProgrammedTransport([status(429, {"Retry-After": "7"}), ok(b"ok")])
    sleep = NoopSleep()
    _client(transport, max_retries=3, sleep=sleep).send(REQ)
    assert sleep.calls == [7.0]


def test_backoff_is_exponential() -> None:
    transport = ProgrammedTransport([status(500), status(500), ok(b"ok")])
    sleep = NoopSleep()
    # jitter returns the full window, base=1 -> windows 1, 2.
    RetryingHttpClient(
        transport,
        _limiter(),
        max_retries=3,
        base_backoff_seconds=1.0,
        sleep=sleep,
        jitter=lambda window: window,
    ).send(REQ)
    assert sleep.calls == [1.0, 2.0]
