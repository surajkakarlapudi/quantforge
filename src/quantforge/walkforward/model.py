"""The walk-forward result vocabulary: statuses, reasons, cells, summary, labels.

A **walk-forward evaluation** partitions the complete-case-aligned factor-return axis of
a sealed :class:`~quantforge.optimization.result.PortfolioOptimization` recipe into
ordered train->test windows; per window it re-estimates the covariance (Phase 20
method), re-solves the fully-invested global minimum-variance (GMV) weights (Phase 21
method), and realizes those weights against the strictly-subsequent test returns; then
it chains the out-of-sample (OOS) returns and summarizes them (Phase 19 method). This
module defines the fail-closed vocabulary those numbers live in:

* :class:`WindowStatus` - whether a window produced OOS returns (``REALIZED``) or was
  genuinely undefined for the data (``UNDEFINED``, WF-4).
* :class:`WalkForwardUndefinedReason` - the closed reason vocabulary. It is the
  **union** of the three window reasons (only ``SINGULAR_TRAINING_COVARIANCE`` is
  reachable given the axis-derived window generator; ``INSUFFICIENT_TRAINING`` /
  ``EMPTY_TEST_WINDOW`` are retained as defensive guards - structurally unreachable,
  like the solve layer's non-positive-``s`` guard) and the three summary reasons mapped
  from the reused Phase 19 ``series_summary`` (``NO_VALID_PERIODS`` /
  ``SINGLE_VALID_PERIOD`` / ``ZERO_RETURN_VARIANCE``), because Phase 22 defines its own
  self-contained :class:`StatValue`.
* :class:`StatValue` - the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. Never a bare float, never silently omitted.
* :class:`WalkForwardSummary` - the six summary cells + the count of valid OOS periods,
  the Phase 22 mapping of the reused Phase 19 series summary.
* :func:`factor_label` - the deterministic, name-free factor label keyed to a factor's
  position in the referenced risk model (which fixes the weight-vector order).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "StatStatus",
    "StatValue",
    "WalkForwardSummary",
    "WalkForwardUndefinedReason",
    "WindowStatus",
    "factor_label",
]


class WindowStatus(StrEnum):
    """Whether a walk-forward window produced OOS returns (``REALIZED``) or not."""

    REALIZED = "realized"
    UNDEFINED = "undefined"


class StatStatus(StrEnum):
    """Whether a single :class:`StatValue` cell is KNOWN or UNDEFINED."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class WalkForwardUndefinedReason(StrEnum):
    """Why a window/cell is ``UNDEFINED`` - fail-closed, never fabricated (§15, WF-4).

    A closed vocabulary. Each reason preserves information: it records the *absence* of
    a computable value rather than inventing one, never a divide-by-zero, never a
    repaired / regularized / pseudo-inverted matrix, never a silently dropped window.
    """

    #: A training window shorter than the floor of two periods, so no covariance can be
    #: estimated. **Defensive / structurally unreachable**: the axis-derived window
    #: generator only emits windows whose training span is at least
    #: ``min_train_periods`` (>= 2), so this is retained as a fail-closed guard - the
    #: direct analogue of the solve layer's non-positive-``s`` guard - never produced in
    #: normal operation.
    INSUFFICIENT_TRAINING = "insufficient_training"

    #: The re-estimated training covariance ``Σ`` is not positive-definite (collinear
    #: factors / a zero-variance factor / a training window shorter than the factor
    #: count), so its fully-invested GMV does not exist (the Phase 21
    #: ``SINGULAR_COVARIANCE`` condition, surfaced per window). The **only** window
    #: reason reachable under the axis-derived generator. Recorded, never solved around
    #: (WF-4).
    SINGULAR_TRAINING_COVARIANCE = "singular_training_covariance"

    #: A window with an empty test span, so no OOS return can be realized. **Defensive /
    #: structurally unreachable**: the generator only emits windows whose test span is
    #: non-empty; retained as a fail-closed guard.
    EMPTY_TEST_WINDOW = "empty_test_window"

    #: No valid OOS periods to summarize (the reused Phase 19 ``NO_VALID_PERIODS``,
    #: mapped).
    NO_VALID_PERIODS = "no_valid_periods"

    #: A single valid period, so a dispersion statistic (volatility / Sharpe / t-stat,
    #: or a per-window realized variance) is undefined (the reused Phase 19
    #: ``SINGLE_VALID_PERIOD``, mapped).
    SINGLE_VALID_PERIOD = "single_valid_period"

    #: A zero population dispersion over the OOS series, so the Sharpe / t-statistic is
    #: undefined (the reused Phase 19 ``ZERO_RETURN_VARIANCE``, mapped). Never a
    #: divide-by-zero.
    ZERO_RETURN_VARIANCE = "zero_return_variance"


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (WF-4).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.5")`` - a computed decimal string (canonicalized via
      ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE)`` -
      a value genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    walk-forward analogue of the optimization / factor-risk ``StatValue``.
    """

    status: StatStatus
    value: str | None = None
    reason: WalkForwardUndefinedReason | None = None

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
    def undefined(cls, reason: WalkForwardUndefinedReason) -> StatValue:
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
            reason = WalkForwardUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown WalkForwardUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)


def factor_label(index: int) -> str:
    """The deterministic label of the ``index``-th factor (0-based).

    ``factor_1``, ``factor_2``, ... in the referenced risk model's factor order - a
    stable, name-free label keyed to the factor's position (which fixes the
    weight-vector order). Identical to
    :func:`quantforge.optimization.model.factor_label` and
    :func:`quantforge.factorrisk.model.factor_label` by construction, so the labels of a
    risk model, its optimization, and its walk-forward evaluation line up one-to-one.
    """
    if index < 0:
        raise ValueError("factor index must be non-negative")
    return f"factor_{index + 1}"


@dataclass(frozen=True, slots=True)
class WalkForwardSummary:
    """The aggregated OOS performance summary + the count of valid periods (§12).

    Six UNDEFINED-preserving :class:`StatValue` cells (cumulative return, mean period
    return, volatility, annualized Sharpe, mean t-statistic, hit rate) plus
    ``n_valid_periods`` - the Phase 22 mapping of the reused Phase 19
    :class:`~quantforge.factorportfolio.stats.SeriesSummary` over the chained OOS return
    series.
    """

    cumulative_return: StatValue
    mean_period_return: StatValue
    volatility: StatValue
    annualized_sharpe: StatValue
    mean_t_stat: StatValue
    hit_rate: StatValue
    n_valid_periods: int

    def to_dict(self) -> dict[str, object]:
        return {
            "cumulative_return": self.cumulative_return.to_dict(),
            "mean_period_return": self.mean_period_return.to_dict(),
            "volatility": self.volatility.to_dict(),
            "annualized_sharpe": self.annualized_sharpe.to_dict(),
            "mean_t_stat": self.mean_t_stat.to_dict(),
            "hit_rate": self.hit_rate.to_dict(),
            "n_valid_periods": self.n_valid_periods,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> WalkForwardSummary:
        def _cell(key: str) -> StatValue:
            value = raw.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"WalkForwardSummary.{key} must be an object")
            return StatValue.from_dict(value)

        n_valid = raw.get("n_valid_periods")
        if not isinstance(n_valid, int) or isinstance(n_valid, bool):
            raise ValueError("WalkForwardSummary.n_valid_periods must be an int")
        return cls(
            cumulative_return=_cell("cumulative_return"),
            mean_period_return=_cell("mean_period_return"),
            volatility=_cell("volatility"),
            annualized_sharpe=_cell("annualized_sharpe"),
            mean_t_stat=_cell("mean_t_stat"),
            hit_rate=_cell("hit_rate"),
            n_valid_periods=n_valid,
        )
