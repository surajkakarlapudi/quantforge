"""Exception hierarchy for the strategy-comparison layer (Phase 24, §15).

Rooted at :class:`ComparisonError` so a caller can catch every failure of this layer
with one type. Phase 24 is a *pure consumer* strictly above Phase 22: it resolves an
ordered set of already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records (the "strategies"
of one head-to-head comparison) from the shared research sidecar, reconstructs each
strategy's realized out-of-sample (OOS) return series on its own reconstructed
calendar-date axis, aligns each pair on their shared dates, and seals the
upper-triangle matrix of paired-difference statistics (the mean OOS return difference,
its standard error, the paired ``t`` statistic, the two-sided ``p`` value, and a
descriptive Sharpe difference). It resolves no data at any ``T`` and re-derives nothing
from source, so its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the walk-forward /
campaign layers in particular:

* A **data / evaluation condition** - a pair whose reconstructed date axes overlap in
  fewer than :data:`~quantforge.comparison.compute.MIN_OVERLAP_PERIODS` periods (so no
  paired difference exists), a pair whose paired-difference series has exactly zero
  population variance (so no ``t`` statistic exists), or a strategy whose sealed OOS
  Sharpe is itself undefined (so no Sharpe difference exists) - is **never** an
  exception. It is recorded as a first-class UNDEFINED cell carrying *why*
  (:class:`~quantforge.comparison.model.ComparisonUndefinedReason`, SC-4), never
  fabricated, never a divide-by-zero, never a silently dropped pair.
* A **configuration / consistency defect** - an empty name / spec version / strategy id,
  a duplicated strategy id, fewer than two or more than ``N_MAX`` strategies, a
  referenced id absent from the sidecar, a referenced record whose
  ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.walkforward.result.WalkForwardEvaluation`, a non-REALIZED
  strategy, strategies that are incommensurable (they do not share one rebalance
  schedule, one producing factor-portfolio engine version, one annualization convention,
  and one risk-free convention), or a strategy whose transitive chain cannot be
  reconstructed into an axis matching the sealed record - *is* raised. These are our
  bugs, surfaced rather than silently resolved. A raised error is always preferable to a
  wrong pairwise comparison.
"""

from __future__ import annotations

__all__ = [
    "ComparisonConfigurationError",
    "ComparisonConsistencyError",
    "ComparisonError",
]


class ComparisonError(Exception):
    """Base class for all strategy-comparison-layer errors."""


class ComparisonConfigurationError(ComparisonError):
    """A strategy-comparison request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.comparison.spec.StrategyComparisonSpecification` (an empty
    ``name`` / ``spec_version``; fewer than two or more than
    :data:`~quantforge.comparison.spec.N_MAX` walk-forward ids; an empty or duplicated
    id) or for a
    non-:class:`~quantforge.comparison.spec.StrategyComparisonSpecification` argument to
    the engine. We refuse to guess a request's intent, exactly as the walk-forward and
    campaign layers refuse a misconfigured request."""


class ComparisonConsistencyError(ComparisonError):
    """A comparison cannot be honestly evaluated from the references - surfaced.

    Fail-closed guard for the reference contract (§15, SC-1/SC-2): a strategy id absent
    from the research sidecar; a referenced record whose ``research_result_id``
    disagrees with the requested id or that is not a
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation`; a strategy whose
    roll-up ``status`` is not REALIZED (it sealed no defensible OOS series); strategies
    that are incommensurable - they do not share one ``schedule_id``, one
    ``factor_portfolio_engine_version_id``, one ``periods_per_year``, and one
    ``risk_free_per_period``, so their out-of-sample returns are not drawn from one
    comparable frame and a head-to-head difference would be meaningless; or a strategy
    whose transitive chain (optimization -> risk model -> factor portfolios) is absent,
    drifted, or reconstructs to a date axis that disagrees with the sealed record's
    ``common_periods`` or per-window ranges. Each is a consistency violation and is
    raised - never silently computed around. (A pair with too little overlap, a
    zero-variance paired difference, or a strategy with an undefined sealed Sharpe is
    *not* raised: the statistic is genuinely undefined for the data, so it is recorded
    as a first-class UNDEFINED cell, SC-4.)"""
