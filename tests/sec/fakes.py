"""Test doubles for the SEC acquisition layer.

These let the whole subsystem be exercised without touching the network, the
wall clock, or ``time.sleep`` — so tests are fast, deterministic, and never
depend on live SEC availability.
"""

from __future__ import annotations

from collections.abc import Iterable

from openfinance.sec.errors import TransportError
from openfinance.sec.transport import HttpRequest, HttpResponse


class ProgrammedTransport:
    """A transport that returns pre-programmed responses in order.

    Each queued item is either an :class:`HttpResponse` to return or an
    exception to raise (to simulate transport-level failures). Every request is
    recorded on ``requests`` for assertions.
    """

    def __init__(self, responses: Iterable[HttpResponse | Exception]) -> None:
        self._responses = list(responses)
        self.requests: list[HttpRequest] = []
        self._index = 0

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self._index >= len(self._responses):
            raise AssertionError("ProgrammedTransport ran out of responses")
        item = self._responses[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.requests)


class UrlRoutedTransport:
    """A transport that maps each URL to a fixed response.

    Useful for pagination tests where the order of fetches is driven by the
    client, not the test. A URL that is requested but not registered raises
    :class:`TransportError`.
    """

    def __init__(self, routes: dict[str, HttpResponse]) -> None:
        self._routes = routes
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if request.url not in self._routes:
            raise TransportError(f"no route for {request.url}")
        return self._routes[request.url]


def ok(body: bytes, headers: dict[str, str] | None = None) -> HttpResponse:
    """Build a 200 response with sensible defaults."""
    return HttpResponse(status=200, headers=headers or {}, body=body)


def status(code: int, headers: dict[str, str] | None = None) -> HttpResponse:
    """Build an error/other response with an empty body."""
    return HttpResponse(status=code, headers=headers or {}, body=b"")


class NoopSleep:
    """A sleep replacement that records durations instead of sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
