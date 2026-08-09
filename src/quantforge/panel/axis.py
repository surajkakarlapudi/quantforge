"""The explicit, ordered, content-addressed period axis (locked §4).

A panel is *one metric evaluated over a time axis*. That axis is **part of the
request** and never "all periods that happen to be ingested locally" (mirrors
Phase 8 F1) — coupling a panel's identity to a machine's ingestion state would be a
reproducibility break and a silent look-ahead-by-ingestion risk.

:class:`PeriodAxis` is therefore an **explicit, ordered, de-duplicated, frozen**
tuple of :class:`~quantforge.metrics.model.MetricPeriod` (each carrying an explicit
``period_type`` + dates, no inferred fiscal labels — D7). It is built two ways,
both hashed into ``axis_id`` (§5):

1. :meth:`of` — an explicit ordered list of periods.
2. :meth:`annual` / :meth:`quarterly` — a **deterministic generator**: a frequency,
   inclusive date bounds, and an explicit ``period_type``. A pure function of its
   declared params — no wall-clock ("last 5 years" is impossible to express), no
   locale, no ambient state.

``axis_id`` is versioned and content-addressed: the domain tag ``period-axis/1``
and the ``axis_kind`` are hashed in, so a **future axis kind hashes distinctly and
leaves every existing** ``axis_id`` **unchanged** (D7 extensibility lock — a new kind
is a new version, never an edit to an existing one). An explicit list hashes its
ordered ``period_key``s; a generator hashes its declared params, so the two identity
forms never collide even when they expand to the same periods.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date

from quantforge.metrics.model import MetricPeriod
from quantforge.panel.errors import PanelConfigurationError
from quantforge.sec.artifacts import sha256_hex
from quantforge.xbrl.contexts import PeriodType

__all__ = ["PeriodAxis"]

# The NUL separator shared across every id space in the project (data-model §11);
# it cannot occur in a period_key, a date, or an enum value, so a joined payload is
# unambiguous.
_SEP = "\x00"

# The axis identity format/version tag. Bumping this (or adding a new axis_kind)
# yields distinct ``axis_id``s without altering any already-computed id — the D7
# extensibility lock (invariant-14 analogue: a new version, never an edit).
_AXIS_DOMAIN = "period-axis/1"

# Canonical axis kinds. Generators encode their frequency in the kind itself, so a
# future kind (e.g. "monthly") hashes distinctly from these.
_KIND_EXPLICIT = "explicit"
_KIND_ANNUAL = "annual"
_KIND_QUARTERLY = "quarterly"

_MONTHS_PER_STEP = {_KIND_ANNUAL: 12, _KIND_QUARTERLY: 3}


@dataclass(frozen=True, slots=True)
class PeriodAxis:
    """An explicit, ordered, de-duplicated sequence of fiscal periods (§4).

    Construct via :meth:`of` (explicit list), :meth:`annual`, or :meth:`quarterly`
    (deterministic generators). Frozen and hashable; ``periods`` is the canonical,
    ordered tuple used for both iteration and cell production. ``axis_id`` binds the
    axis into ``panel_definition_id`` and thence ``panel_id`` (§5).

    The axis is materialized to concrete periods on construction (so a panel always
    has cells to fill), but its **identity** is a pure function of what was declared:
    an explicit axis is identified by its ordered periods; a generator axis by its
    declared params (kind + period_type + bounds), so re-declaring the identical
    request reproduces the same ``axis_id`` on any machine.
    """

    axis_kind: str
    periods: tuple[MetricPeriod, ...]
    # Declared generator params (None for an explicit axis); part of identity.
    period_type: PeriodType | None = None
    lower_bound: str | None = None
    upper_bound: str | None = None

    # -- factories -----------------------------------------------------------

    @classmethod
    def of(cls, periods: Iterable[MetricPeriod]) -> PeriodAxis:
        """Build an axis from an **explicit ordered list** of periods (§4.1).

        Duplicates are rejected (a duplicate period is a configuration bug, not a
        silently-collapsed column — §8); an empty axis fails closed. Order is
        preserved verbatim — the caller's declared order is materialized, but cell
        emission is always by the §2 total order, so identity does not depend on a
        cosmetically different input ordering having been sorted.
        """
        ordered = tuple(periods)
        if not ordered:
            raise PanelConfigurationError(
                "a period axis must contain at least one period; an empty axis is a "
                "configuration bug, not an empty result"
            )
        seen: set[str] = set()
        for period in ordered:
            key = period.period_key
            if key in seen:
                raise PanelConfigurationError(
                    f"period axis contains a duplicate period {period.to_dict()}; "
                    "each period must be distinct"
                )
            seen.add(key)
        return cls(axis_kind=_KIND_EXPLICIT, periods=_sorted_periods(ordered))

    @classmethod
    def annual(cls, start: str, end: str, *, period_type: PeriodType) -> PeriodAxis:
        """A deterministic **annual** axis over inclusive date bounds (§4.2).

        ``start`` and ``end`` are the first and last ``period_end`` dates
        (``YYYY-MM-DD``, inclusive); consecutive periods step one year. For an
        ``INSTANT`` axis each period is a point at a year-end; for a ``DURATION``
        axis each period spans the year ending at that date. A pure function of the
        declared params — no wall-clock, no locale.
        """
        return cls._generate(_KIND_ANNUAL, start, end, period_type)

    @classmethod
    def quarterly(cls, start: str, end: str, *, period_type: PeriodType) -> PeriodAxis:
        """A deterministic **quarterly** axis over inclusive date bounds (§4.2).

        As :meth:`annual` but consecutive periods step one quarter (three months).
        """
        return cls._generate(_KIND_QUARTERLY, start, end, period_type)

    # -- generator -----------------------------------------------------------

    @classmethod
    def _generate(
        cls, kind: str, start: str, end: str, period_type: PeriodType
    ) -> PeriodAxis:
        """Materialize a generator axis; fail closed on any malformed param (§4, §8)."""
        if period_type not in (PeriodType.INSTANT, PeriodType.DURATION):
            raise PanelConfigurationError(
                f"a generated axis requires an INSTANT or DURATION period_type; "
                f"got {period_type!r}"
            )
        lower = _parse_date(start, "start")
        upper = _parse_date(end, "end")
        if lower > upper:
            raise PanelConfigurationError(
                f"axis start {start!r} is after end {end!r}; bounds are inclusive "
                "and must be ordered"
            )
        step = _MONTHS_PER_STEP[kind]
        periods: list[MetricPeriod] = []
        current = lower
        while current <= upper:
            end_str = current.isoformat()
            if period_type is PeriodType.INSTANT:
                periods.append(MetricPeriod.instant(end_str))
            else:
                # DURATION: the span ending here starts one interval + 1 day earlier
                # (e.g. a year ending 2018-12-31 spans 2018-01-01..2018-12-31; a
                # quarter ending 2018-09-30 spans 2018-07-01..2018-09-30). Pure
                # calendar arithmetic — never an inferred fiscal calendar.
                span_start = _add_months(current, -step)
                periods.append(
                    MetricPeriod.duration(_next_day(span_start).isoformat(), end_str)
                )
            current = _add_months(current, step)
        return cls(
            axis_kind=kind,
            periods=tuple(periods),
            period_type=period_type,
            lower_bound=lower.isoformat(),
            upper_bound=upper.isoformat(),
        )

    # -- identity ------------------------------------------------------------

    @property
    def axis_id(self) -> str:
        """Content hash of the period axis (§5): ``sha256(domain, kind, …)``.

        An explicit axis hashes its ordered ``period_key``s; a generator axis hashes
        its declared params (period_type + bounds). The domain tag and ``axis_kind``
        are always included so a future axis kind hashes distinctly and leaves every
        existing ``axis_id`` unchanged (D7 extensibility lock).
        """
        components: list[str] = [_AXIS_DOMAIN, self.axis_kind]
        if self.axis_kind == _KIND_EXPLICIT:
            components.extend(period.period_key for period in self.periods)
        else:
            # A generator is fully identified by its declared params; the expanded
            # period list is a deterministic function of them.
            assert self.period_type is not None  # set for every generator
            components.extend(
                (
                    self.period_type.value,
                    self.lower_bound or "",
                    self.upper_bound or "",
                )
            )
        payload = _SEP.join(components)
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    def to_dict(self) -> dict[str, object]:
        """A serializable, reconstructable description of the axis (§6 provenance)."""
        return {
            "axis_id": self.axis_id,
            "axis_kind": self.axis_kind,
            "period_type": self.period_type.value if self.period_type else None,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "periods": [period.to_dict() for period in self.periods],
        }

    def __len__(self) -> int:
        return len(self.periods)

    def __iter__(self) -> Iterator[MetricPeriod]:
        return iter(self.periods)


def _sorted_periods(periods: tuple[MetricPeriod, ...]) -> tuple[MetricPeriod, ...]:
    """The §2 total order over periods: ``(period_end, period_type, period_start)``.

    Cell emission and axis materialization use one total order so identity never
    depends on set-iteration or a cosmetically different input ordering. ``None``
    dates (an instant has no start) sort before any real date via the empty string.
    """
    return tuple(
        sorted(
            periods,
            key=lambda p: (
                p.period_end or "",
                p.period_type.value,
                p.period_start or "",
            ),
        )
    )


def _parse_date(value: str, label: str) -> date:
    """Parse a ``YYYY-MM-DD`` bound; fail closed on anything else (§8)."""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise PanelConfigurationError(
            f"axis {label} {value!r} is not a valid YYYY-MM-DD date"
        ) from exc


def _is_month_end(d: date) -> bool:
    return _next_day(d).month != d.month


def _next_day(d: date) -> date:
    return date.fromordinal(d.toordinal() + 1)


def _last_day_of_month(year: int, month: int) -> int:
    """The last calendar day of ``month`` in ``year`` (handles leap Februaries)."""
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date.fromordinal(first_of_next.toordinal() - 1).day


def _add_months(d: date, months: int) -> date:
    """Shift ``d`` by ``months`` (may be negative), preserving end-of-month.

    Pure calendar arithmetic. When ``d`` is the last day of its month (every year-
    and quarter-end is), the result snaps to the last day of the target month, so a
    quarter-end walk stays on quarter-ends (``2018-09-30`` + 3 months → ``2018-12-31``,
    not ``2018-12-30``). Otherwise the day is preserved, clamped to the target
    month's length. No fiscal calendar is inferred.
    """
    total = (d.year * 12 + (d.month - 1)) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    if _is_month_end(d):
        day = _last_day_of_month(year, month)
    else:
        day = min(d.day, _last_day_of_month(year, month))
    return date(year, month, day)
