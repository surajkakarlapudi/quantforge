"""Period canonicalization: instant/duration/forever; no fiscal inference."""

from __future__ import annotations

import pytest

from quantforge.canonical.errors import CanonicalError
from quantforge.canonical.period import canonicalize_period
from quantforge.xbrl.contexts import PeriodType, RawContext


def _ctx(**kwargs: object) -> RawContext:
    base: dict[str, object] = {
        "context_ref": "c1",
        "entity_identifier": "0000320193",
        "entity_scheme": "http://www.sec.gov/CIK",
    }
    base.update(kwargs)
    return RawContext(**base)  # type: ignore[arg-type]


def test_instant_maps_to_period_end_only() -> None:
    p = canonicalize_period(_ctx(period_type=PeriodType.INSTANT, instant="2023-09-30"))
    assert p.period_type is PeriodType.INSTANT
    assert p.period_start is None
    assert p.period_end == "2023-09-30"


def test_duration_maps_to_start_and_end() -> None:
    p = canonicalize_period(
        _ctx(period_type=PeriodType.DURATION, start="2022-10-01", end="2023-09-30")
    )
    assert p.period_type is PeriodType.DURATION
    assert p.period_start == "2022-10-01"
    assert p.period_end == "2023-09-30"


def test_forever_preserved_with_no_dates() -> None:
    p = canonicalize_period(_ctx(period_type=PeriodType.FOREVER))
    assert p.period_type is PeriodType.FOREVER
    assert p.period_start is None
    assert p.period_end is None


def test_dates_are_not_reformatted() -> None:
    # The lexical date is preserved verbatim — no timezone shift, no reparse.
    p = canonicalize_period(_ctx(period_type=PeriodType.INSTANT, instant="2023-01-01"))
    assert p.period_end == "2023-01-01"


def test_instant_without_date_fails_closed() -> None:
    with pytest.raises(CanonicalError, match="no instant date"):
        canonicalize_period(_ctx(period_type=PeriodType.INSTANT))


def test_duration_missing_end_fails_closed() -> None:
    with pytest.raises(CanonicalError, match="missing start or end"):
        canonicalize_period(_ctx(period_type=PeriodType.DURATION, start="2022-10-01"))
