"""Exception hierarchy for the walk-forward-evaluation layer (Phase 22, §15).

Rooted at :class:`WalkForwardError` so a caller can catch every failure of this layer
with one type. Phase 22 is a *pure consumer* strictly above Phase 21: it resolves
exactly one already-sealed
:class:`~quantforge.optimization.result.PortfolioOptimization` (the optimization
*recipe*) from the shared research sidecar, resolves the transitively referenced
:class:`~quantforge.factorrisk.result.FactorRiskModel` and its
:class:`~quantforge.factorportfolio.result.FactorPortfolio` factors, partitions their
complete-case-aligned factor return series into ordered train->test windows,
re-estimates the covariance (Phase 20 method) and re-solves the GMV weights (Phase 21
method) on each training window, and realizes those weights against the
strictly-subsequent test returns. It resolves no data at any ``T`` and re-derives
nothing from source, so its only failures are of the request or of a consistency
invariant.

The governing posture mirrors every prior layer's split (§15), and the optimization /
factor-risk layers in particular:

* A **data / evaluation condition** - a window that is genuinely undefined for the data
  (a training covariance that is not positive-definite, so its GMV does not exist; or -
  defensively - a training window shorter than the floor or an empty test span) - is
  **never** an exception. It is recorded as a first-class UNDEFINED window carrying
  *why* (:class:`~quantforge.walkforward.model.WalkForwardUndefinedReason`, WF-4), never
  fabricated, never a divide-by-zero, never a repaired / regularized / pseudo-inverted
  matrix, never a silently dropped window.
* A **configuration / consistency defect** - an empty name / spec version / optimization
  id, a malformed training policy, a referenced id absent from the sidecar, a referenced
  record whose ``research_result_id`` disagrees with the request or that is not the
  expected type, a recipe whose ``status`` is not ``OPTIMAL`` or whose objective /
  constraint is not the v1 GMV / fully-invested recipe, incommensurable factors, a
  disagreeing inherited risk-free convention, a common window too short to form the
  required number of windows, or fewer than the minimum number of REALIZED windows -
  *is* raised. These are our bugs, surfaced rather than silently resolved. A raised
  error is always preferable to a wrong out-of-sample evaluation.
"""

from __future__ import annotations

__all__ = [
    "WalkForwardConfigurationError",
    "WalkForwardConsistencyError",
    "WalkForwardError",
]


class WalkForwardError(Exception):
    """Base class for all walk-forward-evaluation-layer errors."""


class WalkForwardConfigurationError(WalkForwardError):
    """A walk-forward-evaluation request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.walkforward.spec.WalkForwardEvaluationSpecification` (an empty
    ``name`` / ``spec_version`` / ``optimization_id``; a malformed
    :class:`~quantforge.walkforward.spec.TrainingPolicy` - an unknown window kind, a
    ``min_train_periods`` below the floor, a ``test_periods`` below one, a
    ``rolling_length`` absent for a rolling window or present for an expanding one, or a
    ``rolling_length`` below ``min_train_periods``) or for a
    non-:class:`~quantforge.walkforward.spec.WalkForwardEvaluationSpecification`
    argument to the engine. We refuse to guess a request's intent, exactly as the
    optimization layer refuses a misconfigured request.
    """


class WalkForwardConsistencyError(WalkForwardError):
    """A walk-forward evaluation cannot be honestly run from the references - surfaced.

    Fail-closed guard for the reference contract (§15, WF-1/WF-5/WF-6): an
    ``optimization_id`` absent from the research sidecar; a referenced record whose
    ``research_result_id`` disagrees with the requested id or that is not a
    :class:`~quantforge.optimization.result.PortfolioOptimization`; a recipe whose
    ``status`` is not ``OPTIMAL`` (a singular in-sample recipe is not walkable) or whose
    objective / constraint is not the v1 GMV / fully-invested recipe; the transitively
    referenced :class:`~quantforge.factorrisk.result.FactorRiskModel` or any
    :class:`~quantforge.factorportfolio.result.FactorPortfolio` missing, not decoding,
    or id-mismatched; factors that disagree on the inherited risk-free convention; a
    complete-case common window too short to form the required number of train->test
    windows; or fewer than the minimum number of REALIZED windows after evaluation. Each
    is a consistency violation and is raised - never silently computed around. (A
    non-positive-definite training covariance is *not* raised: the window's GMV is
    genuinely undefined for it, so it is recorded as a first-class UNDEFINED window,
    WF-4.)
    """
