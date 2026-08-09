"""The explicit, ordered, content-addressed price date axis (§17).

The Phase 12 hand-off asks for a price *series over a declared date axis*, and
[phase10-panel-locked §11](../docs/phase10-panel-locked.md) fixes that "the axis IS
a rebalance schedule." :class:`PriceAxis` is the market analogue of
:class:`~quantforge.panel.axis.PeriodAxis`: an **explicit, ordered, de-duplicated,
frozen** tuple of ``YYYY-MM-DD`` trading dates, part of the request and never "all
dates that happen to be ingested locally" (a reproducibility break / look-ahead-by-
ingestion risk).

``axis_id`` is versioned and content-addressed: the domain tag ``price-axis/1`` and
the ``axis_kind`` are hashed in, so a future axis kind hashes distinctly and leaves
every existing ``axis_id`` unchanged (the Phase 10 D7 extensibility discipline). An
explicit list hashes its ordered dates; a generator hashes its declared params.

Everything here is a pure function of its declared params — no wall-clock ("last 30
trading days" is impossible to express), no locale, no ambient state.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from quantforge.availability.calendar import is_us_business_day
from quantforge.market.errors import MarketPolicyConfigurationError
from quantforge.sec.artifacts import sha256_hex

__all__ = ["PriceAxis"]

# The NUL separator shared across every id space in the project (data-model §11).
_SEP = "\x00"

# The axis identity format/version tag. A new axis_kind or a bump yields distinct
# ``axis_id``s without altering any already-computed id (extensibility lock).
_AXIS_DOMAIN = "price-axis/1"

_KIND_EXPLICIT = "explicit"
_KIND_BUSINESS_DAILY = "business-daily"


@dataclass(frozen=True, slots=True)
class PriceAxis:
    """An explicit, ordered, de-duplicated sequence of trading dates (§17).

    Construct via :meth:`of` (explicit list) or :meth:`business_daily` (a
    deterministic US-business-day generator). Frozen and hashable; ``dates`` is the
    canonical, ordered tuple used for both iteration and cell production. ``axis_id``
    binds the axis into a :class:`~quantforge.market.result.PitPriceSeries` identity.

    The axis is materialized on construction, but its **identity** is a pure function
    of what was declared: an explicit axis by its ordered dates, a generator by its
    declared bounds — so re-declaring the identical request reproduces the same
    ``axis_id`` on any machine.
    """

    axis_kind: str
    dates: tuple[str, ...]
    lower_bound: str | None = None
    upper_bound: str | None = None

    # -- factories -----------------------------------------------------------

    @classmethod
    def of(cls, dates: Iterable[str]) -> PriceAxis:
        """Build an axis from an **explicit ordered list** of ``YYYY-MM-DD`` dates.

        Duplicates are rejected (a duplicate date is a configuration bug, not a
        silently-collapsed cell); an empty axis fails closed. Each date is validated
        and the axis is materialized in a single total order (ascending), so identity
        never depends on a cosmetically different input ordering.
        """
        parsed = [(_parse_date(d, "date"), d) for d in dates]
        if not parsed:
            raise MarketPolicyConfigurationError(
                "a price axis must contain at least one date; an empty axis is a "
                "configuration bug, not an empty result"
            )
        seen: set[str] = set()
        for _, raw in parsed:
            if raw in seen:
                raise MarketPolicyConfigurationError(
                    f"price axis contains a duplicate date {raw!r}; each date must "
                    "be distinct"
                )
            seen.add(raw)
        ordered = tuple(d.isoformat() for d, _ in sorted(parsed, key=lambda p: p[0]))
        return cls(axis_kind=_KIND_EXPLICIT, dates=ordered)

    @classmethod
    def business_daily(cls, start: str, end: str) -> PriceAxis:
        """A deterministic **US-business-day** axis over inclusive bounds (§17).

        Every US business day (weekday, not a federal holiday — reusing the Phase 5
        :mod:`~quantforge.availability.calendar`) in ``[start, end]``. A pure function
        of the declared bounds — no wall-clock, no exchange-specific half-days (a
        finer calendar is a future axis kind, not an edit).
        """
        lower = _parse_date(start, "start")
        upper = _parse_date(end, "end")
        if lower > upper:
            raise MarketPolicyConfigurationError(
                f"axis start {start!r} is after end {end!r}; bounds are inclusive "
                "and must be ordered"
            )
        dates: list[str] = []
        current = lower
        while current <= upper:
            if is_us_business_day(current):
                dates.append(current.isoformat())
            current = current + timedelta(days=1)
        if not dates:
            raise MarketPolicyConfigurationError(
                f"business-daily axis [{start}, {end}] contains no US business day"
            )
        return cls(
            axis_kind=_KIND_BUSINESS_DAILY,
            dates=tuple(dates),
            lower_bound=lower.isoformat(),
            upper_bound=upper.isoformat(),
        )

    # -- identity ------------------------------------------------------------

    @property
    def axis_id(self) -> str:
        """Content hash of the date axis: ``sha256(domain, kind, …)``.

        An explicit axis hashes its ordered dates; a generator axis hashes its
        declared bounds. The domain tag and ``axis_kind`` are always included so a
        future axis kind hashes distinctly and leaves every existing ``axis_id``
        unchanged (extensibility lock).
        """
        components: list[str] = [_AXIS_DOMAIN, self.axis_kind]
        if self.axis_kind == _KIND_EXPLICIT:
            components.extend(self.dates)
        else:
            components.extend((self.lower_bound or "", self.upper_bound or ""))
        payload = _SEP.join(components)
        return f"sha256:{sha256_hex(payload.encode('utf-8'))}"

    def to_dict(self) -> dict[str, object]:
        return {
            "axis_id": self.axis_id,
            "axis_kind": self.axis_kind,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "dates": list(self.dates),
        }

    def __len__(self) -> int:
        return len(self.dates)

    def __iter__(self) -> Iterator[str]:
        return iter(self.dates)


def _parse_date(value: str, label: str) -> date:
    """Parse a ``YYYY-MM-DD`` date; fail closed on anything else."""
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise MarketPolicyConfigurationError(
            f"price axis {label} {value!r} is not a valid YYYY-MM-DD date"
        ) from exc
