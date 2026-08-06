"""Tests for the client-side rate limiter."""

from __future__ import annotations

import pytest

from openfinance.sec.throttle import RateLimiter


class FakeClock:
    """A controllable monotonic clock; sleeping advances it."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.t += seconds


def test_first_acquire_does_not_sleep() -> None:
    clock = FakeClock()
    limiter = RateLimiter(10, monotonic=clock.monotonic, sleep=clock.sleep)
    limiter.acquire()
    assert clock.t == 0.0


def test_successive_acquires_are_spaced_by_min_interval() -> None:
    clock = FakeClock()
    # 10 rps -> 0.1s minimum spacing.
    limiter = RateLimiter(10, monotonic=clock.monotonic, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    assert clock.t == pytest.approx(0.1)
    limiter.acquire()
    assert clock.t == pytest.approx(0.2)


def test_no_sleep_when_enough_time_has_passed() -> None:
    clock = FakeClock()
    limiter = RateLimiter(10, monotonic=clock.monotonic, sleep=clock.sleep)
    limiter.acquire()
    clock.t = 5.0  # plenty of time elapses on its own
    limiter.acquire()
    assert clock.t == 5.0  # no additional sleep


def test_invalid_rate_is_rejected() -> None:
    with pytest.raises(ValueError):
        RateLimiter(0)
