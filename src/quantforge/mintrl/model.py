"""The minimum-track-record-length vocabulary: statuses, reasons, and the stat cell.

A **minimum track-record length** reads, per trial of one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`, that trial's
out-of-sample per-period Sharpe ``SR``, skew ``gamma₃``, non-excess kurtosis
``gamma₄`` and OOS period count ``n``, and asks the question the campaign never
answers directly - *how long a track record would this strategy need before its
Sharpe is significant, at confidence ``alpha``, against a benchmark ``SR*``?*
(Bailey & López de Prado). This module defines the fail-closed vocabulary those
numbers live in:

* :class:`MinTrlStatus` - whether the aggregate MinTRL profile is defensible
  (``EVALUATED``, enough determined trials) or genuinely undefined for the data
  (``UNDEFINED``, MT-3).
* :class:`MinTrlExcludedReason` - the closed reason a source trial is *not*
  evaluable: the source sealed the whole trial UNDEFINED (``TRIAL_UNDEFINED``);
  or - defensive, structurally unreachable - a VALID trial whose Sharpe / skew /
  kurtosis cell is not KNOWN (``MOMENTS_UNDEFINED``).
* :class:`MinTrlUndefinedReason` - why a per-trial MinTRL cell or an aggregate
  statistic (or the roll-up status) is UNDEFINED: the trial's Sharpe does not
  exceed the benchmark so no finite record establishes significance
  (``SHARPE_NOT_ABOVE_BENCHMARK``); the trial's Sharpe-estimator variance is
  non-positive (``DEGENERATE_SHARPE_ESTIMATOR``); no determined trials at all
  (``NO_DETERMINED_TRIALS``); or fewer than the
  :data:`~quantforge.mintrl.result.MIN_DETERMINED_TRIALS` floor
  (``INSUFFICIENT_DETERMINED_TRIALS``).
* :class:`StatStatus` / :class:`MinTrlStat` - the UNDEFINED-preserving cell: a
  KNOWN decimal string **or** an UNDEFINED reason. Never a bare float, never
  silently omitted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "MinTrlExcludedReason",
    "MinTrlStat",
    "MinTrlStatus",
    "MinTrlUndefinedReason",
    "StatStatus",
]


class MinTrlStatus(StrEnum):
    """Whether the aggregate MinTRL profile is defensible or genuinely undefined (MT-3).

    ``EVALUATED`` when the number of determined trials (evaluable trials with a KNOWN
    MinTRL) meets the :data:`~quantforge.mintrl.result.MIN_DETERMINED_TRIALS` floor;
    ``UNDEFINED`` (with a :class:`MinTrlUndefinedReason`) otherwise. A sealed evaluation
    always records its status honestly - the record seals either way, never raising
    below the floor.
    """

    EVALUATED = "evaluated"
    UNDEFINED = "undefined"


class MinTrlExcludedReason(StrEnum):
    """Why a source trial is not evaluable - fail-closed, never fabricated
    (MT-3).

    A closed vocabulary. Each reason preserves information: it records *why* a
    trial yields no MinTRL cell rather than inventing one, never a
    divide-by-zero, never a silently dropped trial.
    """

    #: The source campaign sealed the whole trial as UNDEFINED (its OOS Sharpe did not
    #: exist - e.g. a zero-variance OOS series), so there are no moments to evaluate.
    #: Excluded, recorded, never imputed.
    TRIAL_UNDEFINED = "trial_undefined"

    #: A trial the source marked VALID but whose ``sharpe`` / ``skew`` /
    #: ``kurtosis`` cell is not KNOWN. **Defensive / structurally unreachable**: a
    #: VALID campaign trial always sealed all three moments KNOWN together;
    #: retained as a fail-closed guard so a corrupt source can never be coerced
    #: into a MinTRL.
    MOMENTS_UNDEFINED = "moments_undefined"


class MinTrlUndefinedReason(StrEnum):
    """Why a MinTRL cell / aggregate statistic (or the roll-up status) is
    UNDEFINED (MT-3).

    A closed vocabulary, kept distinct from :class:`MinTrlExcludedReason` (which
    explains a *trial*'s exclusion) so a reader can never confuse a missing trial
    with a missing length or aggregate.
    """

    #: The trial's Sharpe does not exceed the benchmark (``SR ≤ SR*``), so the
    #: required length ``1 + V·(Z_alpha/(SR-SR*))²`` is undefined (no finite
    #: record establishes ``SR > SR*``). Recorded, never a divide-by-zero.
    SHARPE_NOT_ABOVE_BENCHMARK = "sharpe_not_above_benchmark"

    #: The trial's Sharpe-estimator variance ``1 - gamma₃·SR + ((gamma₄-1)/4)·SR²``
    #: is non-positive, so the MinTRL argument is undefined. Mathematically
    #: ``≥ 0`` for any valid moment set (the skew-kurtosis inequality
    #: ``gamma₄ ≥ 1 + gamma₃²``), reachable only in razor-edge degeneracies;
    #: retained as a fail-closed guard rather than a ``√`` of a non-positive
    #: number. (The same guard the Phase-23 PSR applies.)
    DEGENERATE_SHARPE_ESTIMATOR = "degenerate_sharpe_estimator"

    #: No determined trials at all (every evaluable trial had an undefined
    #: MinTRL, or every trial was excluded), so every aggregate statistic is
    #: undefined - no sum, no mean, no dispersion, never a divide-by-zero.
    NO_DETERMINED_TRIALS = "no_determined_trials"

    #: Fewer determined trials than the ``MIN_DETERMINED_TRIALS`` floor, so the
    #: aggregate MinTRL profile is not defensible. Reported on ``mintrl_status``;
    #: the (few) per-trial MinTRL cells still seal.
    INSUFFICIENT_DETERMINED_TRIALS = "insufficient_determined_trials"


class StatStatus(StrEnum):
    """Whether a single :class:`MinTrlStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class MinTrlStat:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (MT-3).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``MinTrlStat.known("12.5")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``MinTrlStat.undefined(MinTrlUndefinedReason.SHARPE_NOT_ABOVE_BENCHMARK)`` -
      a value genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is
    the MinTRL analogue of the calibration / campaign ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: MinTrlUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN MinTrlStat must carry a decimal-string value and no reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED MinTrlStat must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> MinTrlStat:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: MinTrlUndefinedReason) -> MinTrlStat:
        """An UNDEFINED cell recording why the value could not be computed."""
        return cls(status=StatStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason``
        only - so the two are impossible to confuse and the serialized bytes are
        minimal.
        """
        if self.status is StatStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MinTrlStat:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back
        a cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("MinTrlStat.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown MinTrlStat status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN MinTrlStat must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED MinTrlStat must carry a reason string")
        try:
            reason = MinTrlUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(f"unknown MinTrlUndefinedReason {reason_raw!r}") from exc
        return cls.undefined(reason)
