"""The strategy-comparison result vocabulary: statuses, reasons, cells, labels.

A **strategy comparison** treats an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records as competing
strategies; for each unordered pair ``(i, j)`` with ``i < j`` it reconstructs both
strategies' realized out-of-sample (OOS) return series on their shared calendar dates
and computes the paired-difference statistics (the mean difference, its standard error,
the paired ``t`` statistic, the two-sided ``p`` value, and a descriptive Sharpe
difference). This module defines the fail-closed vocabulary those numbers live in:

* :class:`ComparisonStatus` - whether a pair produced a defined paired-difference
  comparison (``KNOWN``, its dates overlap in at least the minimum number of periods) or
  was genuinely undefined for the data (``UNDEFINED``, SC-4). A ``KNOWN`` pair may still
  carry an individually UNDEFINED ``t``/``p`` cell (zero difference variance) or Sharpe
  cell (an undefined leg Sharpe).
* :class:`ComparisonUndefinedReason` - the closed reason vocabulary: a pair whose
  reconstructed date axes overlap in fewer than
  :data:`~quantforge.comparison.compute.MIN_OVERLAP_PERIODS` periods
  (``INSUFFICIENT_OVERLAP``); a pair whose paired-difference series has exactly zero
  population variance, so no ``t`` statistic / ``p`` value exists
  (``ZERO_DIFFERENCE_VARIANCE``); and a pair one of whose strategies has an undefined
  sealed OOS Sharpe, so no Sharpe difference exists (``UNDEFINED_STRATEGY_SHARPE`` -
  structurally rare, retained as a fail-closed guard, and a disclosed extension of the
  proposal's closed two-reason set, exactly as Phase 23 disclosed its fourth reason).
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :func:`strategy_label` - the deterministic, name-free label keyed to a strategy's
  position in the request order (which also fixes the upper-triangle pair order).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ComparisonStatus",
    "ComparisonUndefinedReason",
    "StatStatus",
    "StatValue",
    "strategy_label",
]


class ComparisonStatus(StrEnum):
    """Whether a pair produced a defined paired-difference comparison or not.

    ``KNOWN`` when the pair's reconstructed date axes overlap in at least
    :data:`~quantforge.comparison.compute.MIN_OVERLAP_PERIODS` periods (a defined mean
    difference exists); ``UNDEFINED`` otherwise. A ``KNOWN`` pair may still carry an
    individually UNDEFINED ``t``/``p`` or Sharpe cell.
    """

    KNOWN = "known"
    UNDEFINED = "undefined"


class StatStatus(StrEnum):
    """Whether a single :class:`StatValue` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class ComparisonUndefinedReason(StrEnum):
    """Why a pair/cell is ``UNDEFINED`` - fail-closed, never fabricated (§15, SC-4).

    A closed vocabulary. Each reason preserves information: it records the *absence* of
    a computable value rather than inventing one, never a divide-by-zero, never a
    fabricated ``0`` / ``NaN``, never a silently dropped pair.
    """

    #: A pair whose two reconstructed OOS return series share fewer than
    #: :data:`~quantforge.comparison.compute.MIN_OVERLAP_PERIODS` calendar dates, so no
    #: paired difference (and hence no mean, standard error, ``t``, ``p``, or Sharpe
    #: difference) can be estimated. The whole pair cell is UNDEFINED with this reason.
    INSUFFICIENT_OVERLAP = "insufficient_overlap"

    #: A pair whose paired-difference series has exactly zero population variance, so
    #: the standard error is zero and the ``t`` statistic (and its ``p`` value) is
    #: undefined. The mean difference and the Sharpe difference remain KNOWN; only
    #: ``t`` / ``p`` carry this reason. Recorded, never a divide-by-zero.
    ZERO_DIFFERENCE_VARIANCE = "zero_difference_variance"

    #: A pair one of whose strategies sealed an UNDEFINED annualized OOS Sharpe (its
    #: chained OOS series had zero return variance), so the descriptive Sharpe
    #: difference cannot be formed. Only the ``sharpe_diff`` cell carries this reason;
    #: the paired-difference ``t`` statistic is unaffected. Structurally rare (a
    #: REALIZED walk-forward almost always has a defined Sharpe), retained as a
    #: fail-closed guard. A disclosed extension of the proposal's closed two-reason set
    #: (Phase 23 precedent).
    UNDEFINED_STRATEGY_SHARPE = "undefined_strategy_sharpe"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (SC-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.5")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(ComparisonUndefinedReason.INSUFFICIENT_OVERLAP)`` - a value
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    comparison analogue of the walk-forward / campaign ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: ComparisonUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN StatValue must carry a decimal-string value and no reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED StatValue must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> StatValue:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: ComparisonUndefinedReason) -> StatValue:
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
    def from_dict(cls, raw: dict[str, object]) -> StatValue:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StatValue.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = ComparisonUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown ComparisonUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def strategy_label(index: int) -> str:
    """The deterministic label of the ``index``-th strategy (0-based).

    ``strategy_1``, ``strategy_2``, ... in the request order - a stable, name-free label
    keyed to the strategy's position (which also fixes the upper-triangle pair order).
    Mirrors :func:`quantforge.campaign.model.trial_label` by construction.
    """
    if index < 0:
        raise ValueError("strategy index must be non-negative")
    return f"strategy_{index + 1}"
