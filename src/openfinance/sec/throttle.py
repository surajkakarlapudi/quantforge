"""Client-side request throttling.

SEC's fair-access policy asks automated clients to stay at or below 10
requests per second. :class:`RateLimiter` enforces a minimum interval between
successive acquisitions using a simple monotonic-clock gate.

The clock and sleep functions are injected so that tests are deterministic and
never actually sleep. In production the defaults use :func:`time.monotonic`
(immune to wall-clock adjustments) and :func:`time.sleep`.
"""

from __future__ import annotations

import time
from collections.abc import Callable

__all__ = ["RateLimiter"]


class RateLimiter:
    """Enforce a minimum interval between successive requests.

    This is a single-process, thread-agnostic gate: it spaces calls to
    :meth:`acquire` so that no two are closer together than
    ``1 / max_requests_per_second``. It intentionally does not coordinate
    across processes; cross-process fair-access is handled by keeping the
    default rate comfortably below the SEC ceiling.
    """

    def __init__(
        self,
        max_requests_per_second: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be > 0")
        self._min_interval = 1.0 / max_requests_per_second
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed: float | None = None

    def acquire(self) -> None:
        """Block until the next request is permitted, then reserve the slot."""
        now = self._monotonic()
        if self._next_allowed is not None and now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._min_interval
