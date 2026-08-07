"""Deterministic period canonicalization (requirement 4, data-model §3.1/§6.2).

An XBRL context carries one of three period shapes (Phase 3
:class:`~quantforge.xbrl.contexts.PeriodType`): ``instant``, ``duration``
(``startDate``/``endDate``), or ``forever``. This module maps that raw period to
the canonical period fields on a :class:`~quantforge.canonical.model.Fact`.

The categorical rules:

* **A period is defined solely by its dates** — never inferred from a calendar or
  a fiscal focus (requirement 4; recon §11: the same period-end was tagged
  ``FY2017``/``Q1-2018``/``FY2019`` across filings). We do **not** assume FY2025 =
  calendar 2025, and we do **not** derive fiscal_year/fiscal_quarter here — those
  are the *filing's* document focus, reporting metadata that lives on the Filing,
  not per-observation truth (see the canonicalization spec, "deferred").
* **instant** → ``period_type = INSTANT``, ``period_start = None``,
  ``period_end = <the instant date>`` (the data model represents an instant with
  ``period_end`` as the point; §3.1).
* **duration** → ``period_type = DURATION``, ``period_start = <start>``,
  ``period_end = <end>``.
* **forever** → preserved as its own ``period_type = FOREVER`` with no dates,
  rather than coerced into instant/duration or dropped (loss-preservation). The
  data-model §3.1 core enum lists only ``instant``/``duration``; ``forever`` is
  rare and non-numeric-metadata in practice, but discarding it would lose a
  reported distinction, so we keep it explicitly.

Dates are preserved as the exact lexical strings Phase 3 captured (already
stripped of surrounding whitespace). We do **not** reformat, reparse, or
timezone-shift them — they are ``xsd:date`` calendar dates, not instants, and any
reinterpretation would be a normalization we must not perform here.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.canonical.errors import CanonicalError
from quantforge.xbrl.contexts import PeriodType, RawContext

__all__ = ["CanonicalPeriod", "canonicalize_period"]


@dataclass(frozen=True, slots=True)
class CanonicalPeriod:
    """A canonical period: type plus its defining date(s), nothing inferred.

    ``period_start`` is ``None`` for instants and forever; ``period_end`` carries
    the instant point for instants, the end date for durations, and ``None`` for
    forever. No fiscal-year/quarter meaning is attached (requirement 4).
    """

    period_type: PeriodType
    period_start: str | None
    period_end: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "period_type": self.period_type.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


def canonicalize_period(context: RawContext) -> CanonicalPeriod:
    """Map a raw context's period to a :class:`CanonicalPeriod`, deterministically.

    Preserves the instant/duration/forever distinction and the exact dates; infers
    no fiscal meaning (requirement 4). Fails closed if the raw context is missing
    the date(s) its own period type requires — Phase 3 already guarantees this, so
    a violation here signals corruption, and we never fabricate a date.
    """
    if context.period_type is PeriodType.INSTANT:
        if context.instant is None:
            raise CanonicalError(
                f"instant context {context.context_ref!r} has no instant date"
            )
        return CanonicalPeriod(
            period_type=PeriodType.INSTANT,
            period_start=None,
            period_end=context.instant,
        )

    if context.period_type is PeriodType.DURATION:
        if context.start is None or context.end is None:
            raise CanonicalError(
                f"duration context {context.context_ref!r} is missing start or end"
            )
        return CanonicalPeriod(
            period_type=PeriodType.DURATION,
            period_start=context.start,
            period_end=context.end,
        )

    # forever: preserved explicitly rather than coerced or dropped.
    return CanonicalPeriod(
        period_type=PeriodType.FOREVER,
        period_start=None,
        period_end=None,
    )
