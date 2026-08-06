"""Tests for the self-contained US-Eastern time & business calendar.

The calendar is the only piece that reasons about ET/DST/holidays, and it must be
correct *without* a host tz database (deterministic across machines). These tests
pin the DST transition boundaries, the ET offsets, business-day / holiday logic,
and the UTC↔ET round trip.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from openfinance.availability.calendar import (
    eastern_utc_offset_hours,
    is_us_business_day,
    next_us_business_day,
    to_eastern_naive,
    utc_from_eastern_naive,
)


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestEasternOffset:
    def test_winter_is_est_minus_five(self) -> None:
        assert eastern_utc_offset_hours(_utc(2024, 1, 15, 12)) == -5

    def test_summer_is_edt_minus_four(self) -> None:
        assert eastern_utc_offset_hours(_utc(2024, 7, 15, 12)) == -4

    def test_spring_forward_boundary_2024(self) -> None:
        # DST starts 2nd Sunday of March 2024 = Mar 10, 02:00 EST == 07:00 UTC.
        assert eastern_utc_offset_hours(_utc(2024, 3, 10, 6, 59)) == -5
        assert eastern_utc_offset_hours(_utc(2024, 3, 10, 7, 0)) == -4

    def test_fall_back_boundary_2024(self) -> None:
        # DST ends 1st Sunday of November 2024 = Nov 3, 02:00 EDT == 06:00 UTC.
        assert eastern_utc_offset_hours(_utc(2024, 11, 3, 5, 59)) == -4
        assert eastern_utc_offset_hours(_utc(2024, 11, 3, 6, 0)) == -5

    def test_transition_dates_vary_by_year(self) -> None:
        # 2025: 2nd Sunday of March = Mar 9; 1st Sunday of Nov = Nov 2.
        assert eastern_utc_offset_hours(_utc(2025, 3, 9, 7, 0)) == -4
        assert eastern_utc_offset_hours(_utc(2025, 11, 2, 6, 0)) == -5


class TestEasternWallClock:
    def test_utc_to_eastern_summer(self) -> None:
        # 21:30 UTC in summer = 17:30 EDT.
        et = to_eastern_naive(_utc(2024, 8, 1, 21, 30))
        assert (et.hour, et.minute) == (17, 30)

    def test_utc_to_eastern_winter(self) -> None:
        # 22:30 UTC in winter = 17:30 EST.
        et = to_eastern_naive(_utc(2024, 1, 15, 22, 30))
        assert (et.hour, et.minute) == (17, 30)

    def test_round_trip_summer(self) -> None:
        original = _utc(2024, 8, 1, 21, 30)
        et = to_eastern_naive(original)
        assert utc_from_eastern_naive(et) == original

    def test_round_trip_winter(self) -> None:
        original = _utc(2024, 1, 15, 22, 30)
        et = to_eastern_naive(original)
        assert utc_from_eastern_naive(et) == original

    def test_naive_input_rejected(self) -> None:
        with pytest.raises(ValueError, match="aware"):
            to_eastern_naive(datetime(2024, 1, 1, 12, 0))


class TestBusinessCalendar:
    def test_weekday_is_business_day(self) -> None:
        assert is_us_business_day(date(2024, 8, 1))  # Thursday

    def test_weekend_is_not(self) -> None:
        assert not is_us_business_day(date(2024, 8, 3))  # Saturday
        assert not is_us_business_day(date(2024, 8, 4))  # Sunday

    def test_fixed_holiday(self) -> None:
        assert not is_us_business_day(date(2024, 7, 4))  # Independence Day

    def test_floating_holiday_thanksgiving(self) -> None:
        # 4th Thursday of Nov 2024 = Nov 28.
        assert not is_us_business_day(date(2024, 11, 28))

    def test_juneteenth_only_from_2021(self) -> None:
        assert is_us_business_day(date(2020, 6, 19))  # not yet federal
        assert not is_us_business_day(date(2024, 6, 19))  # federal

    def test_weekend_holiday_observed_on_weekday(self) -> None:
        # 2021-07-04 was a Sunday → observed Monday Jul 5.
        assert not is_us_business_day(date(2021, 7, 5))

    def test_next_business_day_skips_weekend(self) -> None:
        # Friday Aug 2, 2024 → next business day is Monday Aug 5.
        assert next_us_business_day(date(2024, 8, 2)) == date(2024, 8, 5)

    def test_next_business_day_skips_holiday(self) -> None:
        # Wednesday Jul 3, 2024 → Jul 4 is a holiday → Friday Jul 5.
        assert next_us_business_day(date(2024, 7, 3)) == date(2024, 7, 5)
