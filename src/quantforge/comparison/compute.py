"""The pure paired-difference statistics of one strategy pair (§11, §12).

Given two strategies' reconstructed ``(as_of -> OOS return)`` maps
(:mod:`quantforge.comparison.align`) and their sealed annualized OOS Sharpe strings,
:func:`compare_pair` computes the pair's paired-difference statistics over their shared
calendar dates, under an explicit :class:`decimal.Context`:

* **Overlap.** ``common`` is the ascending intersection of the two date sets;
  ``overlap = |common|``. Fewer than :data:`MIN_OVERLAP_PERIODS` shared dates and the
  whole pair is UNDEFINED ``INSUFFICIENT_OVERLAP`` (SC-4) - no paired difference exists.
* **Paired difference.** ``d_t = r_t^i - r_t^j`` over the shared dates; the mean
  ``d̄ = Σd/T``; the **population** variance ``s²_d = Σ(d-d̄)²/T`` (divisor ``T``, the
  project's population-moment convention); the standard error
  ``se = sqrt(s²_d / T)`` (one ``Decimal.sqrt``); and the paired ``t`` statistic
  ``t = d̄ / se``. When ``s²_d`` is exactly zero the standard error is zero and ``t`` /
  ``p`` are UNDEFINED ``ZERO_DIFFERENCE_VARIANCE`` (the mean difference stays KNOWN),
  never a divide-by-zero (SC-4).
* **Two-sided p-value.** ``p = 2·(1 - Φ(|t|))`` via the shared exact-``Decimal`` normal
  CDF (:func:`quantforge._stats.normal.standard_normal_cdf`), clamped to ``[0, 1]`` -
  the large-sample paired-difference test, deferring a finite-sample ``t``-distribution
  to a later phase (★, disclosed).
* **Descriptive Sharpe difference.** ``sharpe_diff = Sharpe_i - Sharpe_j``, differencing
  the two strategies' **sealed annualized OOS Sharpe** (a pure descriptive passthrough,
  no significance - ★). It is KNOWN when both legs sealed a KNOWN Sharpe (and the pair
  overlaps); UNDEFINED ``UNDEFINED_STRATEGY_SHARPE`` when either leg's sealed Sharpe is
  undefined.

Antisymmetry (SC-8) lives at the engine/record layer: only the ``i < j`` upper triangle
is sealed, and reading ``(j, i)`` sign-flips ``mean_diff`` / ``t_stat`` /
``sharpe_diff`` while preserving ``p_value`` / ``overlap_periods``. This module always
computes the ``i < j`` orientation. Pure: a function of the two maps, the two Sharpe
strings, and the context - no wall clock, no RNG, no iteration-order dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge._stats.normal import standard_normal_cdf
from quantforge.comparison.model import ComparisonStatus, ComparisonUndefinedReason

__all__ = [
    "MIN_OVERLAP_PERIODS",
    "PairComputation",
    "compare_pair",
]

#: The minimum number of shared calendar dates a pair needs for a defined paired
#: difference. Below this the standard error has no dispersion to estimate; the pair is
#: recorded as UNDEFINED ``INSUFFICIENT_OVERLAP`` (SC-4), never fabricated.
MIN_OVERLAP_PERIODS = 2

_ZERO = Decimal(0)
_ONE = Decimal(1)
_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class PairComputation:
    """The computed paired-difference statistics of one ``i < j`` pair.

    ``status`` is ``UNDEFINED`` (with ``reason = INSUFFICIENT_OVERLAP``) when the pair
    shares too few dates - then every value is ``None``. Otherwise ``status`` is
    ``KNOWN``: ``mean_diff`` / ``stderr_diff`` are always populated; ``t_stat`` /
    ``p_value`` are ``None`` with ``t_reason = ZERO_DIFFERENCE_VARIANCE`` when the
    paired difference has zero variance; ``sharpe_diff`` is ``None`` with
    ``sharpe_reason = UNDEFINED_STRATEGY_SHARPE`` when a leg's sealed Sharpe is
    undefined. The engine maps these into UNDEFINED-preserving
    :class:`~quantforge.comparison.model.StatValue` cells.
    """

    i: int
    j: int
    overlap: int
    status: ComparisonStatus
    reason: ComparisonUndefinedReason | None
    mean_diff: Decimal | None
    stderr_diff: Decimal | None
    t_stat: Decimal | None
    p_value: Decimal | None
    sharpe_diff: Decimal | None
    t_reason: ComparisonUndefinedReason | None
    sharpe_reason: ComparisonUndefinedReason | None


def compare_pair(
    i: int,
    j: int,
    returns_i: dict[str, str],
    returns_j: dict[str, str],
    sharpe_i: str | None,
    sharpe_j: str | None,
    *,
    context: Context,
) -> PairComputation:
    """Compute the ``i < j`` pair's paired-difference statistics (§11, §12).

    ``returns_i`` / ``returns_j`` are the reconstructed ``(as_of -> OOS return)`` maps;
    ``sharpe_i`` / ``sharpe_j`` are the strategies' sealed annualized OOS Sharpe strings
    (``None`` when that strategy's sealed Sharpe was UNDEFINED). Deterministic:
    identical inputs yield identical decimal strings on any machine.
    """
    common = sorted(returns_i.keys() & returns_j.keys())
    overlap = len(common)
    if overlap < MIN_OVERLAP_PERIODS:
        return PairComputation(
            i=i,
            j=j,
            overlap=overlap,
            status=ComparisonStatus.UNDEFINED,
            reason=ComparisonUndefinedReason.INSUFFICIENT_OVERLAP,
            mean_diff=None,
            stderr_diff=None,
            t_stat=None,
            p_value=None,
            sharpe_diff=None,
            t_reason=ComparisonUndefinedReason.INSUFFICIENT_OVERLAP,
            sharpe_reason=ComparisonUndefinedReason.INSUFFICIENT_OVERLAP,
        )

    with localcontext(context):
        diffs = [Decimal(returns_i[d]) - Decimal(returns_j[d]) for d in common]
        n = Decimal(overlap)
        mean_diff = sum(diffs, _ZERO) / n
        variance = sum(((d - mean_diff) * (d - mean_diff) for d in diffs), _ZERO) / n

        t_stat: Decimal | None
        p_value: Decimal | None
        t_reason: ComparisonUndefinedReason | None
        if variance == _ZERO:
            stderr_diff = _ZERO
            t_stat = None
            p_value = None
            t_reason = ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE
        else:
            stderr_diff = (variance / n).sqrt()
            t_stat = mean_diff / stderr_diff
            abs_t = -t_stat if t_stat < _ZERO else t_stat
            cdf = standard_normal_cdf(abs_t, context=context)
            p_value = _TWO * (_ONE - cdf)
            if p_value < _ZERO:
                p_value = _ZERO
            elif p_value > _ONE:
                p_value = _ONE
            t_reason = None

        sharpe_diff: Decimal | None
        sharpe_reason: ComparisonUndefinedReason | None
        if sharpe_i is None or sharpe_j is None:
            sharpe_diff = None
            sharpe_reason = ComparisonUndefinedReason.UNDEFINED_STRATEGY_SHARPE
        else:
            sharpe_diff = Decimal(sharpe_i) - Decimal(sharpe_j)
            sharpe_reason = None

    return PairComputation(
        i=i,
        j=j,
        overlap=overlap,
        status=ComparisonStatus.KNOWN,
        reason=None,
        mean_diff=mean_diff,
        stderr_diff=stderr_diff,
        t_stat=t_stat,
        p_value=p_value,
        sharpe_diff=sharpe_diff,
        t_reason=t_reason,
        sharpe_reason=sharpe_reason,
    )
