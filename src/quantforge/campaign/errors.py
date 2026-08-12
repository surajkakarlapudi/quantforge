"""Exception hierarchy for the research-campaign-evaluation layer (Phase 23, §15).

Rooted at :class:`CampaignError` so a caller can catch every failure of this layer with
one type. Phase 23 is a *pure consumer* strictly above Phase 22: it resolves an ordered
set of already-sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation`
records (the "trials" of one research campaign) from the shared research sidecar, reads
each trial's chained out-of-sample (OOS) return series, and computes the
selection-bias-corrected significance (the Probabilistic and Deflated Sharpe Ratios) of
the best trial. It resolves no data at any ``T`` and re-derives nothing from source, so
its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the walk-forward /
factor-risk layers in particular:

* A **data / evaluation condition** - a trial genuinely undefined for its data (fewer
  than two OOS periods, a zero-variance OOS series so no Sharpe exists, or a degenerate
  Sharpe-estimator variance so no PSR exists), or a whole campaign with fewer than the
  minimum number of valid trials to correct for selection - is **never** an
  exception. It is recorded as a first-class UNDEFINED cell carrying *why*
  (:class:`~quantforge.campaign.model.CampaignUndefinedReason`, CE-4), never fabricated,
  never a divide-by-zero, never a silently dropped trial.
* A **configuration / consistency defect** - an empty name / spec version / trial id, a
  duplicated trial id, fewer than two or more than ``N_MAX`` trials, a non-decimal
  benchmark Sharpe, a referenced id absent from the sidecar, a referenced record whose
  ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.walkforward.result.WalkForwardEvaluation`, a non-REALIZED trial,
  or trials that are incommensurable (they do not share one rebalance schedule and one
  producing factor-portfolio engine version) - *is* raised. These are our bugs, surfaced
  rather than silently resolved. A raised error is always preferable to a wrong
  selection-bias correction.
"""

from __future__ import annotations

__all__ = [
    "CampaignConfigurationError",
    "CampaignConsistencyError",
    "CampaignError",
]


class CampaignError(Exception):
    """Base class for all research-campaign-evaluation-layer errors."""


class CampaignConfigurationError(CampaignError):
    """A research-campaign request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.campaign.spec.ResearchCampaignSpecification` (an empty
    ``name`` / ``spec_version``; fewer than two or more than
    :data:`~quantforge.campaign.spec.N_MAX` trial ids; an empty or duplicated trial
    id; a non-decimal or non-finite ``benchmark_sharpe``) or for a
    non-:class:`~quantforge.campaign.spec.ResearchCampaignSpecification` argument to the
    engine. We refuse to guess a request's intent, exactly as the walk-forward layer
    refuses a misconfigured request.
    """


class CampaignConsistencyError(CampaignError):
    """A campaign cannot be honestly evaluated from the references - surfaced.

    Fail-closed guard for the reference contract (§15, CE-1/CE-3): a trial id absent
    from the research sidecar; a referenced record whose ``research_result_id``
    disagrees with the requested id or that is not a
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation`; a trial whose roll-up
    ``status`` is not REALIZED (it sealed no defensible OOS series); or trials that are
    incommensurable - they do not share one ``schedule_id`` and one
    ``factor_portfolio_engine_version_id``, so their out-of-sample Sharpe ratios are not
    drawn from one comparable search and a selection-bias correction across them
    would be meaningless. Each is a consistency violation and is raised - never
    silently computed around. (A trial with too few OOS periods, a zero-variance OOS
    series, or a campaign with too few valid trials is *not* raised: the statistic is
    genuinely undefined for the data, so it is recorded as a first-class UNDEFINED
    cell, CE-4.)
    """
