"""HTTP transport for SEC acquisition.

This module owns the mechanics of a *single* HTTP round trip: building a
request, sending it, decoding the body, and reporting the outcome. It does not
know about SEC endpoints, retries, throttling, or storage — those live in
higher layers.

The transport is defined as a :class:`Protocol` (:class:`HttpTransport`) so the
SEC client depends on an interface rather than a concrete networking library.
The production implementation, :class:`UrllibTransport`, uses only the standard
library (``urllib``) to keep the project dependency-free. Tests inject a fake
transport and therefore never touch the network.
"""

from __future__ import annotations

import gzip
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from quantforge.sec.errors import TransportError

__all__ = [
    "HttpRequest",
    "HttpResponse",
    "HttpTransport",
    "UrllibTransport",
]


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """An immutable description of one HTTP request.

    ``headers`` carries request identity (User-Agent) and conditional-request
    validators (``If-None-Match`` / ``If-Modified-Since``). The transport is
    responsible only for sending exactly what it is given.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """The result of a completed HTTP exchange.

    ``body`` holds the fully-decoded response bytes (gzip already inflated).
    For a ``304 Not Modified`` response ``body`` is empty and the caller is
    expected to reuse a previously stored artifact.
    """

    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup."""
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class HttpTransport(Protocol):
    """The minimal transport contract the SEC client depends on."""

    def send(self, request: HttpRequest) -> HttpResponse:
        """Perform one round trip.

        Implementations must return an :class:`HttpResponse` for any completed
        exchange — *including* error statuses such as 403/429/500 — and raise
        :class:`~quantforge.sec.errors.TransportError` only for failures where
        no HTTP status was obtained (timeouts, connection resets, DNS errors).
        """
        ...


class UrllibTransport:
    """Standard-library HTTP transport built on :mod:`urllib`.

    Requests advertise ``Accept-Encoding: gzip``; the body is transparently
    inflated when the server responds with ``Content-Encoding: gzip``. HTTP
    error statuses are captured and returned rather than raised, so the retry
    layer above can decide what is retryable.
    """

    def send(self, request: HttpRequest) -> HttpResponse:
        headers = dict(request.headers)
        headers.setdefault("Accept-Encoding", "gzip")
        req = urllib.request.Request(request.url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                return self._to_response(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as exc:
            # A completed exchange that returned an error status. Read the body
            # (may be empty) and surface it as a normal response.
            body = exc.read() if exc.fp is not None else b""
            return self._to_response(exc.code, exc.headers, body)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No HTTP status was obtained: DNS failure, connection reset,
            # socket timeout, etc. This is retryable at a higher layer.
            raise TransportError(f"transport failure for {request.url}: {exc}") from exc

    @staticmethod
    def _to_response(status: int, raw_headers: object, body: bytes) -> HttpResponse:
        # ``raw_headers`` is an ``email.message.Message`` in both the success
        # and HTTPError paths; ``.items()`` yields (name, value) pairs.
        headers = {k: v for k, v in raw_headers.items()}  # type: ignore[attr-defined]
        encoding = None
        for key, value in headers.items():
            if key.lower() == "content-encoding":
                encoding = value.lower()
                break
        if encoding == "gzip" and body:
            body = gzip.decompress(body)
        return HttpResponse(status=status, headers=headers, body=body)
