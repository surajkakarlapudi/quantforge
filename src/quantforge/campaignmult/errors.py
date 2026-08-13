"""Exception hierarchy for the campaign-multiplicity-correction layer (Phase 30, §15).

Rooted at :class:`CampaignMultiplicityError` so a caller can catch every failure of this
layer with one type. Phase 30 is a *pure consumer* strictly above Phase 23: it resolves
exactly one already-sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` from the shared research
sidecar, treats that campaign's KNOWN per-trial Probabilistic-Sharpe-Ratio one-sided
p-values ``p_i = 1 - PSR_i`` as one hypothesis family, and seals the family-wise-error /
false-discovery-rate adjusted ``p`` values plus a rejection set at a declared
``alpha``. It resolves no data at any ``T`` and re-derives nothing from source, so its
only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the multiplicity
layer in particular:

* A **data / evaluation condition** - a trial whose ``psr`` the source sealed as
  UNDEFINED (a zero-variance OOS series, a degenerate Sharpe estimator, or a
  whole-trial exclusion) - is **never** an exception. It is excluded from the corrected
  family and recorded as a first-class
  :class:`~quantforge.campaignmult.result.ExcludedTrialCell` carrying *why* (CM-3/CM-4),
  never imputed, never coerced to a number, never silently dropped.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  source id, an ``alpha`` outside the open interval ``(0, 1)``, an empty or duplicated
  method list, the source id absent from the sidecar, or a resolved record whose
  ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` - *is* raised. These
  are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong multiplicity correction.
"""

from __future__ import annotations

__all__ = [
    "CampaignMultiplicityConfigurationError",
    "CampaignMultiplicityConsistencyError",
    "CampaignMultiplicityError",
]


class CampaignMultiplicityError(Exception):
    """Base class for all campaign-multiplicity-correction-layer errors."""


class CampaignMultiplicityConfigurationError(CampaignMultiplicityError):
    """A campaign-multiplicity-correction request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.campaignmult.spec.CampaignMultiplicitySpecification` (an empty
    ``name`` / ``spec_version`` / ``source_campaign_id``; an ``alpha`` that is not a
    decimal string strictly inside ``(0, 1)``; an empty method tuple or a duplicated
    method) or for a
    non-:class:`~quantforge.campaignmult.spec.CampaignMultiplicitySpecification`
    argument to the engine. We refuse to guess a request's intent, exactly as the
    multiplicity and campaign layers refuse a misconfigured request."""


class CampaignMultiplicityConsistencyError(CampaignMultiplicityError):
    """A correction cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, CM-1): the ``source_campaign_id``
    is absent from the research sidecar; the resolved record does not decode as a
    :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`; or the resolved
    record's ``research_result_id`` disagrees with the requested id (the sidecar is
    inconsistent). Each is a consistency violation and is raised - never silently
    computed around. (A trial whose ``psr`` the source sealed as UNDEFINED is *not*
    raised: it is genuinely undefined for the data, so it is excluded from the family
    and recorded as a first-class
    :class:`~quantforge.campaignmult.result.ExcludedTrialCell`, CM-3/CM-4.)"""
