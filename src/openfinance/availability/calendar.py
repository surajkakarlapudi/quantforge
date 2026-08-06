"""Deterministic US-Eastern time & business calendar for availability policies.

Data-model §6.4 is explicit: ``acceptance_timestamp`` is stored as-supplied UTC,
and **any** daily-cutoff / business-calendar reasoning happens *inside* an
:class:`~openfinance.availability.version.AvailabilityPolicy`, converting the UTC
instant **to ET** — because the SEC dissemination convention (~17:30 ET cutoff →
next business day, recon §15) is defined in ET and the ET↔UTC offset shifts with
daylight saving. This module is that calendar core.

**Why it is self-contained (no ``zoneinfo``/``tzdata``).** Determinism and
reproducibility (invariants 13, 21) forbid depending on a value that varies by
machine. The IANA tz database is *not* present on every platform (notably a bare
Windows install — no ``tzdata`` wheel is a runtime dependency of this project),
and even where present its version drifts. So we encode the **post-2005 Energy
Policy Act** US-Eastern DST rule directly (DST from the 2nd Sunday of March to
the 1st Sunday of November, EDT = UTC-4, EST = UTC-5) and the US **federal
holiday** rules EDGAR observes. This is safe precisely because the initial policy
(``edgar-std/v1``) is era-bounded with ``effective_from`` in the XBRL era (2009+),
well after the 2007 DST regime change — the rule is only ever applied where it is
exactly correct. A pre-2007 era would require a *different* policy version with a
*different* calendar (invariant 14), never a mutation of this one.

Everything here is a pure function of its inputs: no wall-clock read, no RNG, no
system-locale or system-tz dependency (invariant 13).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

__all__ = [
    "EASTERN_DST_REGIME_FROM",
    "eastern_utc_offset_hours",
    "is_us_business_day",
    "next_us_business_day",
    "to_eastern_naive",
    "utc_from_eastern_naive",
]

#: This module's ET/DST/holiday rules are exactly correct only for acceptance
#: dates on/after this instant (the post-Energy-Policy-Act-2005 DST regime, in
#: force from 2007). A policy using this calendar must set ``effective_from`` no
#: earlier than this; an era before it requires a *different* policy version with
#: its own calendar (invariant 14), never a change here.
EASTERN_DST_REGIME_FROM = "2007-01-01T00:00:00Z"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the ``n``-th ``weekday`` (Mon=0..Sun=6) of ``month`` in ``year``."""
    first = date(year, month, 1)
    # days until the first occurrence of `weekday`, then add whole weeks.
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last ``weekday`` (Mon=0..Sun=6) of ``month`` in ``year``."""
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _us_eastern_dst_active(dt_utc: datetime) -> bool:
    """Whether US-Eastern daylight time is in effect at the given UTC instant.

    Post-2007 rule: DST runs from 02:00 **ET** on the 2nd Sunday of March to
    02:00 **ET** on the 1st Sunday of November. The transition boundaries are
    defined in local (ET) wall-clock; we compare against the UTC instant of each
    boundary. Before the spring transition ET is EST (UTC-5, so 02:00 ET = 07:00
    UTC); before the autumn transition ET is EDT (UTC-4, so 02:00 ET = 06:00
    UTC). Using the correct pre-transition offset at each boundary makes the
    comparison exact.
    """
    year = dt_utc.year
    march = _nth_weekday(year, 3, 6, 2)  # 2nd Sunday of March
    november = _nth_weekday(year, 11, 6, 1)  # 1st Sunday of November
    # Spring-forward: 02:00 EST == 07:00 UTC. Fall-back: 02:00 EDT == 06:00 UTC.
    dst_start = datetime(march.year, march.month, march.day, 7, 0, tzinfo=UTC)
    dst_end = datetime(november.year, november.month, november.day, 6, 0, tzinfo=UTC)
    return dst_start <= dt_utc < dst_end


def eastern_utc_offset_hours(dt_utc: datetime) -> int:
    """Return the ET offset from UTC in hours at ``dt_utc`` (-4 EDT / -5 EST)."""
    return -4 if _us_eastern_dst_active(dt_utc) else -5


def to_eastern_naive(dt_utc: datetime) -> datetime:
    """Convert an aware UTC instant to the equivalent ET **wall-clock** time.

    The result is a naive :class:`datetime` carrying ET wall-clock fields (the
    value a person in New York would read on the wall), suitable for cutoff and
    calendar reasoning. It is deterministic and independent of the host tz
    database. The input must be timezone-aware UTC.
    """
    if dt_utc.tzinfo is None:
        raise ValueError("to_eastern_naive requires an aware UTC datetime")
    dt_utc = dt_utc.astimezone(UTC)
    offset = eastern_utc_offset_hours(dt_utc)
    return (dt_utc + timedelta(hours=offset)).replace(tzinfo=None)


def utc_from_eastern_naive(et_naive: datetime) -> datetime:
    """Convert an ET wall-clock time back to an aware UTC instant.

    Inverse of :func:`to_eastern_naive` for unambiguous times. The offset is
    resolved by trying EST (UTC-5) and EDT (UTC-4) and keeping the candidate that
    round-trips to the same ET wall-clock — deterministic for every instant
    outside the one ambiguous fall-back hour, and even there it resolves to a
    single deterministic choice (EST), which is the *later*/more-conservative UTC
    instant, consistent with §PA.3's "round later on uncertainty."
    """
    # Try standard time first; if the resulting UTC instant is actually in DST,
    # use the daylight offset instead. Preferring EST on ambiguity yields the
    # later UTC instant (conservative).
    for offset in (-5, -4):
        candidate = et_naive.replace(tzinfo=UTC) - timedelta(hours=offset)
        if eastern_utc_offset_hours(candidate) == offset:
            return candidate
    # Ambiguous/nonexistent boundary hour: fall back to EST (conservative-later).
    return et_naive.replace(tzinfo=UTC) + timedelta(hours=5)


def _us_federal_holidays(year: int) -> frozenset[date]:
    """US federal holidays EDGAR observes in ``year`` (observed dates included).

    Fixed-date holidays falling on a weekend are observed on the adjacent
    weekday per federal rule (Saturday → preceding Friday, Sunday → following
    Monday). Juneteenth (2021+) is included only from its first federal
    observance year. Purely rule-driven; no hard-coded per-year table.
    """

    def observed(d: date) -> date:
        if d.weekday() == 5:  # Saturday → Friday
            return d - timedelta(days=1)
        if d.weekday() == 6:  # Sunday → Monday
            return d + timedelta(days=1)
        return d

    days: set[date] = set()
    days.add(observed(date(year, 1, 1)))  # New Year's Day
    days.add(_nth_weekday(year, 1, 0, 3))  # MLK Jr. Day (3rd Mon Jan)
    days.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday (3rd Mon Feb)
    days.add(_last_weekday(year, 5, 0))  # Memorial Day (last Mon May)
    if year >= 2021:
        days.add(observed(date(year, 6, 19)))  # Juneteenth (federal from 2021)
    days.add(observed(date(year, 7, 4)))  # Independence Day
    days.add(_nth_weekday(year, 9, 0, 1))  # Labor Day (1st Mon Sep)
    days.add(_nth_weekday(year, 10, 0, 2))  # Columbus Day (2nd Mon Oct)
    days.add(observed(date(year, 11, 11)))  # Veterans Day
    days.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving (4th Thu Nov)
    days.add(observed(date(year, 12, 25)))  # Christmas Day
    return frozenset(days)


def is_us_business_day(d: date) -> bool:
    """Whether ``d`` is a US business day (not a weekend, not a federal holiday)."""
    if d.weekday() >= 5:  # Saturday/Sunday
        return False
    return d not in _us_federal_holidays(d.year)


def next_us_business_day(d: date) -> date:
    """Return the first US business day strictly after ``d``."""
    nxt = d + timedelta(days=1)
    while not is_us_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt
