"""Tests for the aware-UTC timestamp choke point (§6.4, invariant 15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from quantforge.availability.timestamps import (
    ensure_aware_utc,
    format_utc_z,
    parse_utc,
)


class TestParseUtc:
    def test_accepts_z_suffix(self) -> None:
        dt = parse_utc("2024-08-01T22:03:34Z")
        assert dt.tzinfo is UTC
        assert (dt.hour, dt.minute, dt.second) == (22, 3, 34)

    def test_accepts_explicit_offset(self) -> None:
        assert parse_utc("2024-08-01T22:00:00+00:00").hour == 22

    def test_normalizes_non_utc_offset(self) -> None:
        # 18:00-04:00 == 22:00 UTC.
        assert parse_utc("2024-08-01T18:00:00-04:00").hour == 22

    def test_naive_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not timezone-aware"):
            parse_utc("2024-08-01T22:00:00")


class TestEnsureAwareUtc:
    def test_naive_rejected(self) -> None:
        with pytest.raises(ValueError, match="not timezone-aware"):
            ensure_aware_utc(datetime(2024, 1, 1))

    def test_offset_converted_to_utc(self) -> None:
        aware = datetime(2024, 8, 1, 18, 0, tzinfo=timezone(timedelta(hours=-4)))
        assert ensure_aware_utc(aware).hour == 22


class TestFormatUtcZ:
    def test_emits_z_form(self) -> None:
        dt = datetime(2024, 8, 1, 22, 3, 34, tzinfo=UTC)
        assert format_utc_z(dt) == "2024-08-01T22:03:34Z"

    def test_round_trip(self) -> None:
        s = "2024-08-01T22:03:34Z"
        assert format_utc_z(parse_utc(s)) == s
