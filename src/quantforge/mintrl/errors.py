"""Exception hierarchy for the minimum-track-record-length layer (Phase 28, §15).

Rooted at :class:`MinTrlError` so a caller can catch every failure of this layer with
one type. Phase 28 is a *pure consumer* strictly above Phase 23: it resolves exactly one
already-sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` from the
shared research sidecar, reads its per-trial sealed ``sharpe`` / ``skew`` /
``kurtosis`` / ``n``, and seals the per-trial minimum track-record length plus the
aggregate MinTRL profile. It resolves no data and re-derives no moment from source
(MT-4), so its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the calibration /
campaign layers in particular:

* A **data / evaluation condition** - a trial the source sealed UNDEFINED, an evaluable
  trial whose Sharpe does not exceed the benchmark (``SHARPE_NOT_ABOVE_BENCHMARK``), or
  an evaluable trial whose Sharpe-estimator variance is non-positive
  (``DEGENERATE_SHARPE_ESTIMATOR``) - is **never** an exception. A source-UNDEFINED
  trial is excluded from the evaluable family and recorded as a first-class
  :class:`~quantforge.mintrl.result.ExcludedTrial`; an evaluable trial with an undefined
  MinTRL seals an UNDEFINED ``min_track_record_length`` cell carrying *why* (MT-3),
  never imputed, never coerced to a length, never silently dropped. Too few determined
  trials likewise is not an exception: the record still seals with ``mintrl_status``
  UNDEFINED (``INSUFFICIENT_DETERMINED_TRIALS``).
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_campaign_id``, a ``confidence`` not in ``(0, 1)`` or a non-finite
  ``benchmark_sharpe``, the source id absent from the sidecar, or a resolved record
  whose ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` - *is* raised. These
  are our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong MinTRL.
"""

from __future__ import annotations

__all__ = [
    "MinTrlConfigurationError",
    "MinTrlConsistencyError",
    "MinTrlError",
]


class MinTrlError(Exception):
    """Base class for all minimum-track-record-length-layer errors."""


class MinTrlConfigurationError(MinTrlError):
    """A minimum-track-record-length request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification` (an empty
    ``name`` / ``spec_version`` / ``source_campaign_id``, a ``confidence`` not strictly
    inside ``(0, 1)``, or a non-decimal / non-finite ``benchmark_sharpe``) or for a
    non-:class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification` argument
    to the engine. We refuse to guess a request's intent, exactly as the campaign and
    calibration layers refuse a misconfigured request."""


class MinTrlConsistencyError(MinTrlError):
    """A MinTRL cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, MT-1): the ``source_campaign_id``
    is absent from the research sidecar; the resolved record does not decode as a
    :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`; or the resolved
    record's ``research_result_id`` disagrees with the requested id (the sidecar is
    inconsistent). Each is a consistency violation and is raised - never silently
    computed around. (A trial the source sealed UNDEFINED, or an evaluable trial whose
    MinTRL is undefined for its moments, is *not* raised: it is genuinely undefined for
    the data, so it is excluded from the family or recorded with an UNDEFINED cell,
    MT-3.)"""
