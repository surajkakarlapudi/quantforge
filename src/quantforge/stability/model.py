"""The walk-forward turnover & stability vocabulary: statuses, reasons, stat cell.

A **walk-forward turnover & stability analysis** reads, per window of one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`, the re-estimated GMV
training ``weights`` (a per-factor vector in factor order, KNOWN when the window
REALIZED), and asks the question the walk itself never answers - *how stable and how
implementable is the weight path the strategy re-solves over time?* This module defines
the fail-closed vocabulary those numbers live in:

* :class:`StabilityStatus` - whether the aggregate turnover profile is defensible
  (``STABLE``, enough realized-adjacent transitions) or genuinely undefined for the data
  (``UNDEFINED``, WS-3).
* :class:`StabilityExcludedReason` - the closed reason a source window yields no
  per-window stability cell: the source sealed the whole window UNDEFINED
  (``WINDOW_UNDEFINED``).
* :class:`StabilityUndefinedReason` - why a per-window cell, an aggregate statistic, or
  the roll-up status is UNDEFINED: no adjacent REALIZED predecessor to trade from
  (``NO_PRIOR_REALIZED_WINDOW``); no realized-adjacent transitions at all
  (``NO_TRANSITIONS``); no realized windows at all (``NO_REALIZED_WINDOWS``, defensive);
  fewer transitions than the ``MIN_STABILITY_TRANSITIONS`` floor
  (``INSUFFICIENT_TRANSITIONS``); or a zero-concentration book so the effective breadth
  is undefined (``ZERO_CONCENTRATION``, defensive - a fully-invested vector has
  ``Σw = 1`` so ``HHI ≥ 1/N > 0``).
* :class:`StatStatus` / :class:`StabilityStat` - the UNDEFINED-preserving cell: a KNOWN
  decimal string **or** an UNDEFINED reason. Never a bare float, never silently omitted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "StabilityExcludedReason",
    "StabilityStat",
    "StabilityStatus",
    "StabilityUndefinedReason",
    "StatStatus",
]


class StabilityStatus(StrEnum):
    """Whether the aggregate turnover profile is defensible or undefined (WS-3).

    ``STABLE`` when the number of realized-adjacent transitions meets the
    :data:`~quantforge.stability.result.MIN_STABILITY_TRANSITIONS` floor; ``UNDEFINED``
    (with a :class:`StabilityUndefinedReason`) otherwise. A sealed analysis always
    records its status honestly - the record seals either way, never raising below the
    floor. The per-window cells and the turnover aggregates still seal below it.
    """

    STABLE = "stable"
    UNDEFINED = "undefined"


class StabilityExcludedReason(StrEnum):
    """Why a source window yields no per-window stability cell - fail-closed (WS-3).

    A closed vocabulary. Each reason preserves information: it records *why* a window
    has no weight vector to analyze rather than inventing one.
    """

    #: The source sealed the whole window as UNDEFINED (no out-of-sample returns were
    #: realized - e.g. a singular training covariance), so it carries no KNOWN weight
    #: vector. Excluded, recorded, never imputed.
    WINDOW_UNDEFINED = "window_undefined"


class StabilityUndefinedReason(StrEnum):
    """Why a per-window cell, an aggregate, or the roll-up status is UNDEFINED (WS-3).

    A closed vocabulary, kept distinct from :class:`StabilityExcludedReason` (which
    explains a *window*'s exclusion) so a reader can never confuse a missing window with
    a missing statistic.
    """

    #: A REALIZED window whose immediately-preceding window is not REALIZED (the first
    #: window, or one following an UNDEFINED gap), so there is no adjacent book to trade
    #: from and ``turnover_from_prev`` does not exist. Recorded, never fabricated.
    NO_PRIOR_REALIZED_WINDOW = "no_prior_realized_window"

    #: No realized-adjacent transitions at all (every REALIZED window either is
    #: the first or follows a gap), so every turnover aggregate is undefined - no
    #: sum, no mean, never a divide-by-zero.
    NO_TRANSITIONS = "no_transitions"

    #: No realized windows at all, so every concentration aggregate is undefined.
    #: **Defensive / structurally unreachable**: the source fails closed below two
    #: realized windows, so a sealed walk always has at least two; retained as a
    #: fail-closed guard, never a divide-by-zero.
    NO_REALIZED_WINDOWS = "no_realized_windows"

    #: Fewer realized-adjacent transitions than the ``MIN_STABILITY_TRANSITIONS`` floor,
    #: so the aggregate turnover profile is not defensible. Reported on
    #: ``stability_status``; the (few) turnover values still seal.
    INSUFFICIENT_TRANSITIONS = "insufficient_transitions"

    #: A window whose ``concentration_hhi`` is zero, so ``effective_breadth = 1/HHI``
    #: does not exist. **Defensive / structurally unreachable**: a fully-invested GMV
    #: vector has ``Σw = 1`` so ``HHI ≥ 1/N > 0``; retained as a fail-closed guard,
    #: never a divide-by-zero.
    ZERO_CONCENTRATION = "zero_concentration"


class StatStatus(StrEnum):
    """Whether a single :class:`StabilityStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class StabilityStat:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (WS-3).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StabilityStat.known("0.5")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``StabilityStat.undefined(StabilityUndefinedReason.NO_TRANSITIONS)`` - a value
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    stability analogue of the walk-forward / calibration ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: StabilityUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN StabilityStat must carry a decimal-string value and no "
                    "reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED StabilityStat must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> StabilityStat:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: StabilityUndefinedReason) -> StabilityStat:
        """An UNDEFINED cell recording why the value could not be computed."""
        return cls(status=StatStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only - so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is StatStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StabilityStat:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StabilityStat.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StabilityStat status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StabilityStat must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StabilityStat must carry a reason string")
        try:
            reason = StabilityUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown StabilityUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
