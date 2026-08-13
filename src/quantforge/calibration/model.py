"""The risk-forecast-calibration vocabulary: statuses, reasons, and the stat cell.

A **risk-forecast calibration** reads, per window of one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`, the in-sample
forecast ``predicted_variance`` (``wᵀΣw`` over the training covariance, Phase 20/21
method) and the out-of-sample outcome ``realized_variance`` (population variance of
the realized test returns), and asks the question the walk itself never answers -
*does the risk model's variance forecast hold out-of-sample?* This module defines
the fail-closed vocabulary those numbers live in:

* :class:`CalibrationStatus` - whether the aggregate calibration is defensible
  (``CALIBRATED``, enough calibratable windows) or genuinely undefined for the data
  (``UNDEFINED``, RC-3).
* :class:`CalibrationExcludedReason` - the closed reason a source window is *not*
  calibratable: the source sealed the whole window UNDEFINED (``WINDOW_UNDEFINED``);
  the window is REALIZED but its ``realized_variance`` is UNDEFINED because the test
  span had one period (``SINGLE_VALID_PERIOD``); the window's ``predicted_variance``
  is non-positive so the ratio is undefined (``ZERO_PREDICTED_VARIANCE``, a
  defensive guard - a REALIZED GMV window's ``wᵀΣw`` over a positive-definite
  covariance is strictly positive); or - defensive, structurally unreachable - a
  REALIZED window whose ``predicted_variance`` is itself UNDEFINED
  (``PREDICTED_VARIANCE_UNDEFINED``).
* :class:`CalibrationUndefinedReason` - why an aggregate statistic (or the roll-up
  status) is UNDEFINED: no calibratable windows at all (``NO_CALIBRATABLE_WINDOWS``), or
  fewer than the ``MIN_CALIBRATABLE_WINDOWS`` floor
  (``INSUFFICIENT_CALIBRATABLE_WINDOWS``).
* :class:`StatStatus` / :class:`CalibrationStat` - the UNDEFINED-preserving aggregate
  cell: a KNOWN decimal string **or** an UNDEFINED reason. Never a bare float, never
  silently omitted.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CalibrationExcludedReason",
    "CalibrationStat",
    "CalibrationStatus",
    "CalibrationUndefinedReason",
    "StatStatus",
]


class CalibrationStatus(StrEnum):
    """Whether the aggregate calibration is defensible or genuinely undefined (RC-3).

    ``CALIBRATED`` when the number of calibratable windows meets the
    :data:`~quantforge.calibration.result.MIN_CALIBRATABLE_WINDOWS` floor; ``UNDEFINED``
    (with a :class:`CalibrationUndefinedReason`) otherwise. A sealed calibration always
    records its status honestly - the record seals either way, never raising below the
    floor.
    """

    CALIBRATED = "calibrated"
    UNDEFINED = "undefined"


class CalibrationExcludedReason(StrEnum):
    """Why a source window is not calibratable - fail-closed, never fabricated (RC-3).

    A closed vocabulary. Each reason preserves information: it records *why* a window
    yields no forecast-vs-outcome ratio rather than inventing one, never a
    divide-by-zero, never a silently dropped window.
    """

    #: The source sealed the whole window as UNDEFINED (no out-of-sample returns were
    #: realized - e.g. a singular training covariance), so there is no realized variance
    #: to compare against. Excluded, recorded, never imputed.
    WINDOW_UNDEFINED = "window_undefined"

    #: The window is REALIZED but its ``realized_variance`` is UNDEFINED: the test span
    #: had a single out-of-sample period, so a dispersion statistic does not exist (the
    #: source ``SINGLE_VALID_PERIOD``, carried forward). The only exclusion reason
    #: reachable for a REALIZED window under the source's own semantics.
    SINGLE_VALID_PERIOD = "single_valid_period"

    #: The window's ``predicted_variance`` is non-positive, so ``realized /
    #: predicted`` does not exist. **Defensive / structurally unreachable**: a
    #: REALIZED window solved a fully-invested GMV over a positive-definite training
    #: covariance, whose ``wᵀΣw`` is strictly positive; retained as a fail-closed
    #: guard, never a divide-by-zero.
    ZERO_PREDICTED_VARIANCE = "zero_predicted_variance"

    #: A REALIZED window whose ``predicted_variance`` is itself UNDEFINED.
    #: **Defensive / structurally unreachable**: a REALIZED window always sealed a
    #: KNOWN in-sample ``wᵀΣw``; retained as a fail-closed guard so a corrupt source
    #: can never be coerced into a ratio.
    PREDICTED_VARIANCE_UNDEFINED = "predicted_variance_undefined"


class CalibrationUndefinedReason(StrEnum):
    """Why an aggregate calibration statistic (or the roll-up status) is UNDEFINED
    (RC-3).

    A closed vocabulary, kept distinct from :class:`CalibrationExcludedReason` (which
    explains a *window*'s exclusion) so a reader can never confuse a missing window with
    a missing aggregate.
    """

    #: No calibratable windows at all (every window was excluded), so every aggregate
    #: statistic is undefined - no sum, no mean, no ratio, never a divide-by-zero.
    NO_CALIBRATABLE_WINDOWS = "no_calibratable_windows"

    #: Fewer calibratable windows than the ``MIN_CALIBRATABLE_WINDOWS`` floor, so the
    #: aggregate calibration is not defensible. Reported on ``calibration_status``; the
    #: (few) per-window ratios still seal.
    INSUFFICIENT_CALIBRATABLE_WINDOWS = "insufficient_calibratable_windows"


class StatStatus(StrEnum):
    """Whether a single :class:`CalibrationStat` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class CalibrationStat:
    """One aggregate statistic: a KNOWN decimal string, or UNDEFINED with a reason
    (RC-3).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``CalibrationStat.known("1.2")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``CalibrationStat.undefined(CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS)``
      - a value genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    calibration analogue of the walk-forward / optimization ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: CalibrationUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is StatStatus.KNOWN:
            if not isinstance(self.value, str) or self.reason is not None:
                raise ValueError(
                    "a KNOWN CalibrationStat must carry a decimal-string value and no "
                    "reason"
                )
        else:  # UNDEFINED
            if self.reason is None or self.value is not None:
                raise ValueError(
                    "an UNDEFINED CalibrationStat must carry a reason and no value"
                )

    @classmethod
    def known(cls, value: str) -> CalibrationStat:
        """A KNOWN cell holding a canonical decimal string."""
        return cls(status=StatStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: CalibrationUndefinedReason) -> CalibrationStat:
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
    def from_dict(cls, raw: dict[str, object]) -> CalibrationStat:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed - the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("CalibrationStat.status must be a string")
        try:
            status = StatStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown CalibrationStat status {status_raw!r}") from exc
        if status is StatStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN CalibrationStat must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED CalibrationStat must carry a reason string")
        try:
            reason = CalibrationUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown CalibrationUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
