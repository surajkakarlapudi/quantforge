"""The explicit, ordered, content-addressed rebalance schedule (proposal §D3, D3).

A backtest is a walk over an ordered sequence of **decision instants**. Neither a
:class:`~quantforge.panel.axis.PeriodAxis` (accounting periods) nor a
:class:`~quantforge.market.axis.PriceAxis` (trading dates) models that: a rebalance
is a *calendar ``as_of`` instant* at which the strategy is allowed to see everything
PIT-eligible and nothing later (analysis row 11). :class:`RebalanceSchedule` is that
third axis — the exact analogue of :class:`PriceAxis`, built to the same discipline:

* an **explicit, ordered, de-duplicated, frozen** tuple of timezone-aware UTC
  ``as_of`` instants — part of the *request*, never "all dates ingested locally"
  (a look-ahead-by-ingestion / reproducibility risk); and
* a versioned, content-addressed ``schedule_id`` (domain ``backtest-schedule/1``,
  the same NUL + ``sha256:`` construction as ``axis_id``): an explicit schedule
  hashes its ordered instants, a generator hashes its declared bounds + parameters,
  so a future schedule kind hashes distinctly and leaves every existing id unchanged.

Every instant is aware UTC (the Phase 5 ``as_of`` contract — invariant 15; a naive
instant is a look-ahead ambiguity and is rejected). The one calendar generator,
:meth:`month_end_closes`, emits the **availability instant of each month-end session
close** under the standard market policy (16:00 ET session close + a publication lag),
so the month-end close a strategy trades on is guaranteed PIT-eligible at its own
rebalance — never a not-yet-knowable price (§B, §D; ``market_eod_std_v1``). Everything
here is a pure function of its declared parameters: no wall-clock, no locale, no
ambient state (invariants 13, 21).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from quantforge.availability.calendar import (
    is_us_business_day,
    utc_from_eastern_naive,
)
from quantforge.availability.timestamps import ensure_aware_utc, format_utc_z, parse_utc
from quantforge.backtest.errors import BacktestConfigurationError
from quantforge.backtest.identity import schedule_id as _schedule_id

__all__ = ["RebalanceSchedule"]

_KIND_EXPLICIT = "explicit"
_KIND_MONTH_END_CLOSE = "month-end-close"

# The standard EOD availability convention this generator assumes, mirroring
# ``market.policy.market_eod_std_v1`` (session close 16:00 ET + a 240-minute
# publication lag → the bar is knowable at 20:00 ET). A month-end rebalance ``as_of``
# is placed at that availability instant so the session's own close is PIT-eligible at
# the rebalance (§B); a decision earlier than this could not defend using the close.
# These are folded into ``schedule_id`` so a different convention hashes distinctly.
_SESSION_CLOSE_HOUR = 16
_SESSION_CLOSE_MINUTE = 0
_PUBLICATION_LAG_MINUTES = 240


@dataclass(frozen=True, slots=True)
class RebalanceSchedule:
    """An explicit, ordered, de-duplicated sequence of ``as_of`` instants (§D3).

    Construct via :meth:`of` (an explicit list of instants) or :meth:`month_end_closes`
    (a deterministic month-end-session-close generator). Frozen and hashable;
    ``instants`` is the canonical, ordered tuple of ISO-8601 ``…Z`` strings used for
    both iteration and identity. ``schedule_id`` binds the schedule into a
    :class:`~quantforge.backtest.result.BacktestResult` identity.

    The schedule is materialized on construction, but its **identity** is a pure
    function of what was declared: an explicit schedule by its ordered instants, a
    generator by its declared bounds and convention — so re-declaring the identical
    request reproduces the same ``schedule_id`` on any machine.
    """

    schedule_kind: str
    instants: tuple[str, ...]
    lower_bound: str | None = None
    upper_bound: str | None = None

    # -- factories -----------------------------------------------------------

    @classmethod
    def of(cls, instants: Iterable[datetime | str]) -> RebalanceSchedule:
        """Build a schedule from an **explicit list** of aware-UTC ``as_of`` instants.

        Each item is a timezone-aware :class:`datetime` or an ISO-8601 string with a
        zone designator (``Z`` or an explicit offset); a naive instant is rejected (an
        ambiguous ``as_of`` is a look-ahead risk — invariant 15). Duplicates are
        rejected (a duplicate rebalance is a configuration bug, not a silently-collapsed
        one); an empty schedule fails closed. Instants are canonicalized to UTC ``…Z``
        form and materialized in a single total order (ascending), so identity never
        depends on a cosmetically different input ordering.
        """
        parsed: list[datetime] = [_coerce_instant(item) for item in instants]
        if not parsed:
            raise BacktestConfigurationError(
                "a rebalance schedule must contain at least one instant; an empty "
                "schedule is a configuration bug, not an empty backtest"
            )
        canonical = [format_utc_z(dt) for dt in parsed]
        seen: set[str] = set()
        for raw in canonical:
            if raw in seen:
                raise BacktestConfigurationError(
                    f"rebalance schedule contains a duplicate instant {raw!r}; each "
                    "rebalance instant must be distinct"
                )
            seen.add(raw)
        ordered = tuple(sorted(canonical, key=parse_utc))
        return cls(schedule_kind=_KIND_EXPLICIT, instants=ordered)

    @classmethod
    def month_end_closes(cls, start: str, end: str) -> RebalanceSchedule:
        """A month-end **session-close** schedule over inclusive ``YYYY-MM-DD`` bounds.

        For each calendar month that intersects ``[start, end]``, the last US business
        day (weekday, not a federal holiday — reusing the Phase 5
        :mod:`~quantforge.availability.calendar`) whose date falls within the bounds is
        selected, and the rebalance ``as_of`` is the **availability instant of that
        session's close** under the standard EOD convention (16:00 ET + a 240-minute
        publication lag → 20:00 ET, converted to UTC DST-correctly). Placing the
        ``as_of`` at the close's availability instant guarantees the month-end close a
        strategy trades on is PIT-eligible at its own rebalance (§B, §D).

        A pure function of the declared bounds — no wall-clock, no exchange-specific
        half-days (a finer calendar is a future schedule kind, not an edit).
        """
        lower = _parse_date(start, "start")
        upper = _parse_date(end, "end")
        if lower > upper:
            raise BacktestConfigurationError(
                f"schedule start {start!r} is after end {end!r}; bounds are inclusive "
                "and must be ordered"
            )
        instants: list[str] = []
        for session in _month_end_business_days(lower, upper):
            instants.append(format_utc_z(_session_close_availability(session)))
        if not instants:
            raise BacktestConfigurationError(
                f"month-end-close schedule [{start}, {end}] contains no month-end US "
                "business day"
            )
        return cls(
            schedule_kind=_KIND_MONTH_END_CLOSE,
            instants=tuple(instants),
            lower_bound=lower.isoformat(),
            upper_bound=upper.isoformat(),
        )

    # -- identity ------------------------------------------------------------

    @property
    def schedule_id(self) -> str:
        """Content hash of the schedule: ``sha256(domain, kind, …)`` (§D3).

        An explicit schedule hashes its ordered instants; a generator schedule hashes
        its declared bounds and the availability convention. The domain tag and
        ``schedule_kind`` are always included so a future schedule kind hashes
        distinctly and leaves every existing ``schedule_id`` unchanged.
        """
        if self.schedule_kind == _KIND_EXPLICIT:
            components = list(self.instants)
        else:
            components = [
                self.lower_bound or "",
                self.upper_bound or "",
                f"close={_SESSION_CLOSE_HOUR:02d}:{_SESSION_CLOSE_MINUTE:02d}",
                f"lag={_PUBLICATION_LAG_MINUTES}",
            ]
        return _schedule_id(kind=self.schedule_kind, components=components)

    def as_of_instants(self) -> tuple[datetime, ...]:
        """The schedule's instants as aware-UTC :class:`datetime`\\ s, in order."""
        return tuple(parse_utc(raw) for raw in self.instants)

    def to_dict(self) -> dict[str, object]:
        return {
            "schedule_id": self.schedule_id,
            "schedule_kind": self.schedule_kind,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "instants": list(self.instants),
        }

    def __len__(self) -> int:
        return len(self.instants)

    def __iter__(self) -> Iterator[datetime]:
        """Iterate the schedule as aware-UTC instants, in ascending order."""
        return iter(self.as_of_instants())


def _coerce_instant(item: datetime | str) -> datetime:
    """Coerce one schedule item to an aware-UTC :class:`datetime`; fail closed."""
    if isinstance(item, datetime):
        try:
            return ensure_aware_utc(item)
        except ValueError as exc:
            raise BacktestConfigurationError(
                f"rebalance instant {item!r} is not timezone-aware; a naive as_of is "
                "an ambiguous look-ahead boundary and is rejected (invariant 15)"
            ) from exc
    if isinstance(item, str):
        try:
            return parse_utc(item)
        except ValueError as exc:
            raise BacktestConfigurationError(
                f"rebalance instant {item!r} is not a valid timezone-aware ISO-8601 "
                "instant (needs a 'Z' or explicit offset)"
            ) from exc
    raise BacktestConfigurationError(
        f"rebalance instant {item!r} must be an aware datetime or ISO-8601 string"
    )


def _parse_date(value: str, label: str) -> date:
    """Parse a ``YYYY-MM-DD`` bound; fail closed on anything else."""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise BacktestConfigurationError(
            f"rebalance schedule {label} {value!r} is not a valid YYYY-MM-DD date"
        ) from exc


def _month_end_business_days(lower: date, upper: date) -> list[date]:
    """The last US business day of each month intersecting ``[lower, upper]``.

    Only days within the inclusive bounds are eligible, so the last *in-bounds*
    business day of the first and last months is honored even when the true
    month-end falls outside the bounds. Deterministic and order-stable.
    """
    results: list[date] = []
    year, month = lower.year, lower.month
    while (year, month) <= (upper.year, upper.month):
        chosen = _last_business_day_in_month(year, month, lower, upper)
        if chosen is not None:
            results.append(chosen)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return results


def _last_business_day_in_month(
    year: int, month: int, lower: date, upper: date
) -> date | None:
    """The latest in-bounds US business day of ``year``-``month``, or ``None``."""
    if month == 12:
        month_end = date(year, 12, 31)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    day = min(month_end, upper)
    floor = max(date(year, month, 1), lower)
    while day >= floor:
        if is_us_business_day(day):
            return day
        day = day - timedelta(days=1)
    return None


def _session_close_availability(session: date) -> datetime:
    """The availability instant of ``session``'s EOD close (16:00 ET + lag → UTC)."""
    et_close = datetime(
        session.year,
        session.month,
        session.day,
        _SESSION_CLOSE_HOUR,
        _SESSION_CLOSE_MINUTE,
    )
    et_available = et_close + timedelta(minutes=_PUBLICATION_LAG_MINUTES)
    return utc_from_eastern_naive(et_available)
