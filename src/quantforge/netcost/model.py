"""The net-of-cost vocabulary: statuses, reasons, stat cell.

A **net-of-cost performance** reads, from one sealed
:class:`~quantforge.stability.result.WalkForwardStability`, its per-REALIZED-window
one-way ``turnover_from_prev``, and - transitively, from the one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability pins - the
chained gross out-of-sample return series and its sealed gross performance summary. It
applies a *declared* linear transaction-cost rate ``c`` and asks the question neither
source answers - *what does this strategy earn after paying to trade, and at what cost
rate does its gross edge vanish?* This module defines the fail-closed vocabulary those
numbers live in:

* :class:`NetCostStatus` - whether a net-of-cost Sharpe was formed (``MEASURED``, a
  KNOWN net Sharpe) or is genuinely undefined for the data (``UNDEFINED``, NC-5).
* :class:`NetCostExcludedReason` - the closed reason a source window contributes no
  gross returns and no turnover to the net series: the walk-forward sealed the whole
  window UNDEFINED (``WINDOW_UNDEFINED``, carried through Phase 27's exclusion).
* :class:`NetCostUndefinedReason` - why a cell / the roll-up status is UNDEFINED: a
  realized window with no adjacent realized predecessor has no turnover to charge
  (``NO_PRIOR_REALIZED_WINDOW``, carried from Phase 27 - the window bears **zero** cost,
  no fabricated entry cost); the strategy never trades so the break-even cost rate does
  not exist (``DEGENERATE_NO_TURNOVER``); or the net series has no / one /
  zero-dispersion valid periods so a moment is undefined (``NO_VALID_PERIODS`` /
  ``SINGLE_VALID_PERIOD`` / ``ZERO_RETURN_VARIANCE``, carried verbatim from the reused
  Phase 19 summary).
* :class:`StatStatus` / :class:`NetCostStat` - the UNDEFINED-preserving cell: a KNOWN
  decimal string **or** an UNDEFINED reason. Never a bare float, never silently omitted.

The three series-moment reason strings (``no_valid_periods`` / ``single_valid_period`` /
``zero_return_variance``) are **identical** to
:class:`~quantforge.factorportfolio.model.FactorPortfolioUndefinedReason`'s, so the
reused Phase 19 summary's UNDEFINED cells map straight across by value (NC-5), never
re-interpreted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "NetCostExcludedReason",
    "NetCostStat",
    "NetCostStatus",
    "NetCostUndefinedReason",
    "StatStatus",
]


class NetCostStatus(StrEnum):
    """Whether a net-of-cost Sharpe was formed or is genuinely undefined (NC-5).

    ``MEASURED`` when the net return series has a KNOWN annualized Sharpe (the headline
    net-of-cost verdict is defensible); ``UNDEFINED`` (with a
    :class:`NetCostUndefinedReason`) when it does not - a net series with zero
    population dispersion (``ZERO_RETURN_VARIANCE``) or, defensively, too few valid
    periods. A
    sealed net-of-cost record always records its status honestly - the record seals
    either way, never raising for a data condition.
    """

    MEASURED = "measured"
    UNDEFINED = "undefined"


class NetCostExcludedReason(StrEnum):
    """Why a source window contributes nothing to the net series - fail-closed (NC-5).

    A closed vocabulary. Each reason preserves information: it records *why* a window
    yields no gross returns and no turnover rather than inventing them.
    """

    #: The walk-forward sealed the whole window UNDEFINED (no out-of-sample returns were
    #: realized), so Phase 27 excluded it and it carries no gross returns to charge cost
    #: against. Carried through here verbatim from the stability record's exclusion.
    WINDOW_UNDEFINED = "window_undefined"


class NetCostUndefinedReason(StrEnum):
    """Why a net-of-cost cell / the roll-up status is UNDEFINED (NC-5).

    A closed vocabulary, kept distinct from :class:`NetCostExcludedReason` (which
    explains a *window*'s exclusion) so a reader can never confuse a missing window with
    a missing statistic.
    """

    #: A REALIZED window whose immediately-preceding window is not REALIZED (the first
    #: window, or one following an UNDEFINED gap), so Phase 27 sealed its
    #: ``turnover_from_prev`` UNDEFINED: there is no adjacent book to trade from. The
    #: window bears **zero** transaction cost (no fabricated entry cost - a documented
    #: deviation from the proposal's ``entry_cost_convention``), its turnover / cost
    #: cells are UNDEFINED, and its gross returns pass through to the net series
    #: unchanged. Carried from Phase 27, never fabricated.
    NO_PRIOR_REALIZED_WINDOW = "no_prior_realized_window"

    #: Total one-way turnover over all realized-adjacent transitions is exactly zero
    #: (the strategy never trades), so the break-even cost rate ``Σ gross / Σ turnover``
    #: does not exist - there is no cost that would erase a gross edge. Recorded on the
    #: break-even cell, never a divide-by-zero (NC-5). The net series equals the gross
    #: series (cost is exactly zero everywhere), honestly reported.
    DEGENERATE_NO_TURNOVER = "degenerate_no_turnover"

    #: The net return series was KNOWN on no valid period - there is no series to
    #: summarize (the reused Phase 19 ``NO_VALID_PERIODS``, mapped). **Defensive /
    #: structurally unreachable**: a sealed walk has at least two realized periods.
    NO_VALID_PERIODS = "no_valid_periods"

    #: A single valid net period, so a dispersion statistic (volatility / Sharpe) is
    #: undefined (the reused Phase 19 ``SINGLE_VALID_PERIOD``, mapped). **Defensive /
    #: structurally unreachable** for the same reason.
    SINGLE_VALID_PERIOD = "single_valid_period"

    #: A zero population dispersion over the net series, so the net Sharpe is undefined
    #: (the reused Phase 19 ``ZERO_RETURN_VARIANCE``, mapped). The net mean and (zero)
    #: net volatility stay KNOWN; only the Sharpe is undefined, never a divide-by-zero
    #: (NC-5). Reachable when a cost path makes every net period identical.
    ZERO_RETURN_VARIANCE = "zero_return_variance"


class StatStatus(StrEnum):
    """Whether a single :class:`NetCostStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class NetCostStat:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (NC-5).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``NetCostStat.known("0.041")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``NetCostStat.undefined(NetCostUndefinedReason.DEGENERATE_NO_TURNOVER)`` - a value
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    net-of-cost analogue of the walk-forward / stability ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: NetCostUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN NetCostStat must carry a decimal-string value and no "
                    "reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED NetCostStat must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> NetCostStat:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: NetCostUndefinedReason) -> NetCostStat:
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
    def from_dict(cls, raw: dict[str, object]) -> NetCostStat:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("NetCostStat.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown NetCostStat status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN NetCostStat must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED NetCostStat must carry a reason string")
        try:
            reason = NetCostUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(f"unknown NetCostUndefinedReason {reason_raw!r}") from exc
        return cls.undefined(reason)
