"""Retry with exponential backoff for transient SEC failures.

:class:`RetryingHttpClient` wraps any :class:`~quantforge.sec.transport.HttpTransport`
and, together with a :class:`~quantforge.sec.throttle.RateLimiter`, turns a
best-effort transport into one that survives transient failures:

* ``429 Too Many Requests`` and ``5xx`` responses are retried.
* Transport-level failures (timeouts, resets) are retried.
* Permanent client errors (``403``, ``404``, other ``4xx``) are *not* retried;
  they are surfaced immediately.
* ``Retry-After`` is honoured when the server provides it.

Backoff is exponential with full jitter. The sleep function and the jitter
source are injected so tests are deterministic and never sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from quantforge.sec.errors import HttpStatusError, TransportError
from quantforge.sec.throttle import RateLimiter
from quantforge.sec.transport import HttpRequest, HttpResponse, HttpTransport

__all__ = ["RetryingHttpClient"]

# Statuses that indicate a transient server-side condition worth retrying.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RetryingHttpClient:
    """Add throttling and bounded exponential-backoff retries to a transport."""

    def __init__(
        self,
        transport: HttpTransport,
        rate_limiter: RateLimiter,
        *,
        max_retries: int,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._transport = transport
        self._rate_limiter = rate_limiter
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._sleep = sleep
        # Full jitter in [0, window). Injectable for determinism; the default
        # multiplies the window by a pseudo-random fraction.
        self._jitter = jitter if jitter is not None else _default_jitter

    def send(self, request: HttpRequest) -> HttpResponse:
        """Send ``request``, retrying transient failures up to the limit.

        Returns the first acceptable :class:`HttpResponse` (a 2xx or 304, or a
        non-retryable status the caller asked to see). Raises
        :class:`HttpStatusError` when a retryable status is still failing after
        the retry budget is spent, or :class:`TransportError` when transport
        failures persist.
        """
        attempt = 0
        last_transport_error: TransportError | None = None

        while True:
            attempt += 1
            self._rate_limiter.acquire()
            try:
                response = self._transport.send(request)
            except TransportError as exc:
                last_transport_error = exc
                if attempt > self._max_retries:
                    raise
                self._sleep(self._backoff(attempt))
                continue

            if response.status in _RETRYABLE_STATUSES:
                if attempt > self._max_retries:
                    raise HttpStatusError(
                        response.status, request.url, attempts=attempt
                    )
                self._sleep(self._retry_delay(response, attempt))
                continue

            return response

        # Unreachable, but keeps type checkers happy about ``last_transport_error``.
        raise last_transport_error or TransportError(request.url)

    def _retry_delay(self, response: HttpResponse, attempt: int) -> float:
        """Prefer a server-provided ``Retry-After`` over computed backoff."""
        retry_after = response.header("Retry-After")
        if retry_after is not None:
            try:
                return min(float(retry_after), self._max_backoff)
            except ValueError:
                # HTTP-date form of Retry-After is not parsed; fall back to
                # exponential backoff rather than guessing.
                pass
        return self._backoff(attempt)

    def _backoff(self, attempt: int) -> float:
        """Exponential window with full jitter, capped at the maximum."""
        window = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
        return self._jitter(window)


def _default_jitter(window: float) -> float:
    # Local import keeps the module import graph free of ``random`` unless the
    # production jitter is actually used (tests inject their own).
    import random

    return random.uniform(0, window)
