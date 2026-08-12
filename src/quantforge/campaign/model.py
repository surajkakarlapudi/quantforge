"""The research-campaign result vocabulary: statuses, reasons, cells, labels.

A **research-campaign evaluation** treats an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records as the
trials of one research campaign; per trial it re-derives the out-of-sample (OOS)
excess-return moments (mean, population variance, skew, non-excess kurtosis,
per-period Sharpe) and the Probabilistic Sharpe Ratio, then across trials it
selects the best OOS Sharpe and deflates its significance for the size of the
search (the Deflated Sharpe Ratio). This module defines the fail-closed
vocabulary those numbers live in:

* :class:`TrialStatus` - whether a trial produced a defined OOS Sharpe
  (``VALID``) or was genuinely undefined for its data (``UNDEFINED``, CE-4).
* :class:`CampaignUndefinedReason` - the closed reason vocabulary: a trial with
  fewer than two OOS periods (``INSUFFICIENT_OOS_PERIODS``); a trial whose OOS
  series has zero population variance, so no Sharpe / skew / kurtosis exists
  (``ZERO_OOS_VARIANCE``); a trial whose Sharpe-estimator variance is
  non-positive, so no PSR/DSR exists (``DEGENERATE_SHARPE_ESTIMATOR`` -
  structurally rare, retained as a fail-closed guard); and a campaign with fewer
  than the minimum number of valid trials to correct for selection
  (``INSUFFICIENT_VALID_TRIALS``).
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :func:`trial_label` - the deterministic, name-free label keyed to a trial's
  position in the request order.

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CampaignUndefinedReason",
    "StatStatus",
    "StatValue",
    "TrialStatus",
    "trial_label",
]


class TrialStatus(StrEnum):
    """Whether a campaign trial produced a defined OOS Sharpe (``VALID``) or not."""

    VALID = "valid"
    UNDEFINED = "undefined"


class StatStatus(StrEnum):
    """Whether a single :class:`StatValue` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class CampaignUndefinedReason(StrEnum):
    """Why a trial/cell is ``UNDEFINED`` - fail-closed, never fabricated (§15, CE-4).

    A closed vocabulary. Each reason preserves information: it records the
    *absence* of a computable value rather than inventing one, never a
    divide-by-zero, never a fabricated ``0`` / ``NaN``, never a silently dropped
    trial.
    """

    #: A trial with fewer than two OOS periods, so no population dispersion (and
    #: hence no Sharpe, skew, kurtosis, or PSR) can be estimated. Unreachable for
    #: an engine-sealed walk-forward record (which has at least two REALIZED
    #: windows), but a fail-closed guard against a degenerate trial series.
    INSUFFICIENT_OOS_PERIODS = "insufficient_oos_periods"

    #: A trial whose OOS excess-return series has zero population variance, so
    #: the Sharpe ratio (and the skew / kurtosis / PSR that divide by the
    #: volatility) is undefined. Recorded, never a divide-by-zero.
    ZERO_OOS_VARIANCE = "zero_oos_variance"

    #: A trial whose Probabilistic-Sharpe-Ratio estimator variance
    #: ``1 - gamma₃·SR + ((gamma₄-1)/4)·SR²`` is non-positive, so the PSR/DSR
    #: argument is undefined. Mathematically ``≥ 0`` for any valid moment set
    #: (the skew-kurtosis inequality ``gamma₄ ≥ 1 + gamma₃²``), reachable only in
    #: razor-edge degeneracies; retained as a fail-closed guard rather than a
    #: divide-by-zero.
    DEGENERATE_SHARPE_ESTIMATOR = "degenerate_sharpe_estimator"

    #: Fewer than the minimum number of valid trials
    #: (:data:`~quantforge.campaign.compute\
    #: .MIN_VALID_TRIALS`) to estimate the cross-trial Sharpe dispersion, so the
    #: selection, the expected-maximum Sharpe, and the Deflated Sharpe Ratio are
    #: undefined for the campaign. Recorded, never fabricated from a single trial.
    INSUFFICIENT_VALID_TRIALS = "insufficient_valid_trials"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (CE-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.5")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(CampaignUndefinedReason.ZERO_OOS_VARIANCE)`` - a value
      genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    campaign analogue of the walk-forward / factor-risk ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: CampaignUndefinedReason | None = None

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
    def undefined(cls, reason: CampaignUndefinedReason) -> StatValue:
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
        :class:`ValueError` rather than guessed - the sidecar must never read
        back a cell whose meaning changed.
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
            reason = CampaignUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(f"unknown CampaignUndefinedReason {reason_raw!r}") from exc
        return cls.undefined(reason)


def trial_label(index: int) -> str:
    """The deterministic label of the ``index``-th trial (0-based).

    ``trial_1``, ``trial_2``, ... in the request order - a stable, name-free label keyed
    to the trial's position (which also fixes the selection index). Mirrors
    :func:`quantforge.factorrisk.model.factor_label` by construction.
    """
    if index < 0:
        raise ValueError("trial index must be non-negative")
    return f"trial_{index + 1}"
