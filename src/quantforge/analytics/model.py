"""The analytics result vocabulary: status, undefined reasons, statistic keys, cells.

A **performance-analytics record** is a set of named statistics computed over one sealed
backtest's ``period_returns`` (plus, optionally, a benchmark backtest's). This
module defines the fail-closed result vocabulary those statistics live in:

* :class:`AnalyticsStatus` / :class:`AnalyticsUndefinedReason` — the fail-closed cell
  vocabulary. ``UNDEFINED`` is a first-class value carrying *why* a statistic could not
  be computed for the data, never an exception, never ``0`` / ``NaN`` / ``Inf`` (§Q,
  D5). This mirrors Phase 7's :class:`~quantforge.metrics.model.MetricStatus` /
  :class:`~quantforge.metrics.model.UndefinedReason` exactly.
* :class:`StatValue` — the UNDEFINED-preserving cell: a KNOWN decimal string **or** an
  UNDEFINED reason. It is never a bare float and never silently omitted — a statistic
  that cannot be computed for the data is present in the record with its reason.
* the **closed v1 statistic key sets** (:data:`ABSOLUTE_KEYS`, :data:`RELATIVE_KEYS`,
  :data:`VAR_KEYS`). Extending any set is an explicit future edit that hashes distinctly
  — never an implicit fallback (mirrors the Phase 13 D7 / Phase 14 D7 discipline).

Every value is deterministically serializable (``to_dict`` / ``from_dict``); no
wall-clock, RNG, or iteration-order dependence enters any value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ABSOLUTE_KEYS",
    "RELATIVE_KEYS",
    "VAR_KEYS",
    "AnalyticsStatus",
    "AnalyticsUndefinedReason",
    "StatValue",
]


class AnalyticsStatus(StrEnum):
    """Whether a statistic resolved to a value (``KNOWN``) or not (``UNDEFINED``)."""

    KNOWN = "known"
    UNDEFINED = "undefined"


class AnalyticsUndefinedReason(StrEnum):
    """Why a statistic is ``UNDEFINED`` — fail-closed, never fabricated (§J.3, §Q).

    Every reason preserves information: it records the *absence* of a computable value
    (a zero denominator, an unmet precondition) rather than inventing one. A zero
    denominator is never a divide-by-zero — it is one of these reasons.
    """

    #: Too few return observations for the statistic to be defined (e.g. a
    #: variance-based statistic with a single period, or recovery with no post-trough
    #: observation).
    INSUFFICIENT_PERIODS = "insufficient_periods"
    #: Sortino / downside deviation with no below-target observations — the downside
    #: denominator is zero, so the ratio is undefined (never divided).
    ZERO_DOWNSIDE = "zero_downside"
    #: A subject-side statistic whose denominator is the subject's own dispersion
    #: (skewness / excess kurtosis / correlation) when the subject return series is
    #: constant — population variance is zero, so the moment ratio is ``0/0`` and
    #: genuinely undefined. Recorded, never fabricated as ``0`` (a constant series has
    #: no shape) and never divided. (A correctness-required companion to the
    #: benchmark-side ``ZERO_BENCHMARK_VARIANCE``; see
    #: ``docs/phase15-analytics-locked.md``.)
    ZERO_VARIANCE = "zero_variance"
    #: Beta / capture / correlation with zero benchmark variance — the benchmark never
    #: moved, so the regression slope and capture ratios are undefined.
    ZERO_BENCHMARK_VARIANCE = "zero_benchmark_variance"
    #: Information ratio with zero tracking error — active return has no dispersion, so
    #: the ratio is undefined (never divided).
    ZERO_TRACKING_ERROR = "zero_tracking_error"
    #: Calmar / max-drawdown duration when the equity curve never falls below its
    #: running peak — there is no drawdown to measure.
    NO_DRAWDOWN = "no_drawdown"
    #: Max-drawdown recovery when the pre-drawdown peak is never regained by series end
    #: — the recovery length is genuinely unknown, not zero.
    UNRECOVERED_DRAWDOWN = "unrecovered_drawdown"


# -- the closed v1 statistic vocabulary (§J.3) -------------------------------
#
# Sorted tuples: the record stores each block sorted by key, so iteration and identity
# are order-independent. Extending a set is an explicit future edit that hashes
# distinctly (a new key changes the result_hash) — never an edit that reinterprets an
# existing record.

#: Absolute statistics over the subject's returns + derived equity curve (benchmark not
#: required). Return / volatility / Sharpe / max-drawdown are **not** here — they are
#: already sealed in the subject's ``PerformanceStatistics`` (D2); Phase 15 adds only
#: what is missing.
ABSOLUTE_KEYS: tuple[str, ...] = (
    "best_period_return",
    "calmar",
    "downside_deviation",
    "excess_kurtosis",
    "max_drawdown_duration_periods",
    "max_drawdown_recovery_periods",
    "positive_period_fraction",
    "skewness",
    "sortino",
    "worst_period_return",
)

#: Relative statistics (subject vs benchmark; both required and aligned). Empty when the
#: request declares no benchmark.
RELATIVE_KEYS: tuple[str, ...] = (
    "active_return",
    "alpha",
    "beta",
    "correlation",
    "cumulative_active_return",
    "down_capture",
    "information_ratio",
    "tracking_error",
    "up_capture",
)

#: The two historical (nearest-rank) tail statistics computed per requested confidence.
VAR_KEYS: tuple[str, ...] = ("var", "cvar")


@dataclass(frozen=True, slots=True)
class StatValue:
    """One statistic cell: a KNOWN decimal string, or UNDEFINED with a reason (D5).

    Exactly one of ``value`` / ``reason`` is populated, enforced at construction:

    * ``StatValue.known("0.1234")`` — a computed decimal string (canonicalized by the
      compute layer via ``str(+Decimal(...))`` before it reaches here);
    * ``StatValue.undefined(AnalyticsUndefinedReason.ZERO_DOWNSIDE)`` — a statistic that
      is genuinely undefined for the data, recorded with why.

    Never a bare float, never ``None``-as-value, never silently omitted. This is the
    analytics analogue of Phase 7's KNOWN/UNDEFINED metric value.
    """

    status: AnalyticsStatus
    value: str | None = None
    reason: AnalyticsUndefinedReason | None = None

    def __post_init__(self) -> None:
        if self.status is AnalyticsStatus.KNOWN:
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
        return cls(status=AnalyticsStatus.KNOWN, value=value)

    @classmethod
    def undefined(cls, reason: AnalyticsUndefinedReason) -> StatValue:
        """An UNDEFINED cell recording why the statistic could not be computed."""
        return cls(status=AnalyticsStatus.UNDEFINED, reason=reason)

    def to_dict(self) -> dict[str, object]:
        """The canonical ``{status, value?, reason?}`` cell (deterministic).

        A KNOWN cell emits ``value`` only; an UNDEFINED cell emits ``reason`` only — so
        the two are impossible to confuse and the serialized bytes are minimal.
        """
        if self.status is AnalyticsStatus.KNOWN:
            return {"status": self.status.value, "value": self.value}
        assert self.reason is not None  # guaranteed by __post_init__
        return {"status": self.status.value, "reason": self.reason.value}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> StatValue:
        """Reconstruct a cell from its :meth:`to_dict` payload; fail closed otherwise.

        A malformed cell (unknown status, missing value/reason, wrong type, or an
        unrecognized reason string) is a corrupt payload, refused with a
        :class:`ValueError` rather than guessed — the sidecar must never read back a
        cell whose meaning changed.
        """
        status_raw = raw.get("status")
        if not isinstance(status_raw, str):
            raise ValueError("StatValue.status must be a string")
        try:
            status = AnalyticsStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown StatValue status {status_raw!r}") from exc
        if status is AnalyticsStatus.KNOWN:
            value = raw.get("value")
            if not isinstance(value, str):
                raise ValueError("a KNOWN StatValue must carry a string value")
            return cls.known(value)
        reason_raw = raw.get("reason")
        if not isinstance(reason_raw, str):
            raise ValueError("an UNDEFINED StatValue must carry a reason string")
        try:
            reason = AnalyticsUndefinedReason(reason_raw)
        except ValueError as exc:
            raise ValueError(
                f"unknown AnalyticsUndefinedReason {reason_raw!r}"
            ) from exc
        return cls.undefined(reason)
