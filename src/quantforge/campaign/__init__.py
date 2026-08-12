"""Out-of-sample research-campaign evaluation with selection-bias correction (Phase 23).

The first **campaign** capability strictly above Phase 22: a pure consumer that
treats an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records as the
"trials" of one research campaign and asks the honest question a single
out-of-sample walk cannot - *once you searched over N strategies and kept the
best, how much of its out-of-sample Sharpe is skill rather than the luck of the
search?* It resolves the trials from the shared Phase 8 sidecar, verifies they
are commensurable (one shared rebalance schedule and one producing
factor-portfolio engine version), estimates each trial's OOS excess-return
moments and its Probabilistic Sharpe Ratio against a benchmark, selects the best
OOS Sharpe, estimates the expected-maximum Sharpe under the null, and deflates
the best trial's significance for the size of the search (the Deflated Sharpe
Ratio). It re-resolves no data, introduces no new PIT surface, adds no runtime
dependency, and creates no new store.

* :class:`~quantforge.campaign.spec.ResearchCampaignSpecification` - the declarative,
  content-addressed request: a name, an ordered tuple of 2..``N_MAX`` distinct sealed
  ``trial_ids``, and a benchmark Sharpe ``SR*`` (the per-trial PSR threshold).
* :class:`~quantforge.campaign.engine.ResearchCampaignEngine` - resolves, verifies each
  trial (present, a ``WalkForwardEvaluation``, REALIZED), enforces commensurability
  (CE-3), estimates the per-trial statistics and PSR (Phase 23 method), selects and
  deflates the best trial, and seals a
  :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.campaign_engine`).
* :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` - the sealed,
  content-addressed record: the ordered trial references, the shared schedule and
  producing engine version, the per-trial statistic block (Sharpe, skew, kurtosis, PSR),
  and the campaign summary (valid-trial count, selected trial, expected-maximum Sharpe,
  Deflated Sharpe Ratio). Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (CE-6): not a ``Pit*`` type and no as-of
  accessor.
* :class:`~quantforge.campaign.model.StatValue` - the UNDEFINED-preserving cell: a KNOWN
  decimal string **or** an UNDEFINED
  :class:`~quantforge.campaign.model.CampaignUndefinedReason` (too few OOS periods, a
  zero-variance OOS series, a degenerate Sharpe estimator, or too few valid
  trials), never a fabricated ``0`` / ``NaN`` / divide-by-zero (CE-4).
* :mod:`quantforge.campaign.normal` - the deterministic exact-``Decimal``
  standard-normal CDF ``Φ`` / inverse-CDF ``Z⁻¹`` (and the Euler-Mascheroni constant)
  the PSR/DSR math needs, computed in stdlib ``Decimal`` so a sealed campaign id never
  drifts across platforms.

Every identity is content-addressed (:mod:`quantforge.campaign.identity`), every value
deterministically serializable, and every failure follows the raise-vs-record split
(:mod:`quantforge.campaign.errors`): a request / consistency defect raises; a trial or
campaign genuinely undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.campaign.compute import MIN_VALID_TRIALS
from quantforge.campaign.engine import ResearchCampaignEngine
from quantforge.campaign.errors import (
    CampaignConfigurationError,
    CampaignConsistencyError,
    CampaignError,
)
from quantforge.campaign.identity import campaign_id, campaign_result_hash
from quantforge.campaign.model import (
    CampaignUndefinedReason,
    StatStatus,
    StatValue,
    TrialStatus,
    trial_label,
)
from quantforge.campaign.normal import (
    EULER_MASCHERONI,
    standard_normal_cdf,
    standard_normal_ppf,
)
from quantforge.campaign.result import (
    BOUNDARY_PIT,
    CAMPAIGN_RESULT_FORMAT_VERSION,
    CampaignSummary,
    ResearchCampaignEvaluation,
    TrialStat,
)
from quantforge.campaign.spec import N_MAX, ResearchCampaignSpecification
from quantforge.campaign.version import (
    CAMPAIGN_ENGINE_VERSION,
    CAMPAIGN_METHOD_VERSION,
    CAMPAIGN_NORMAL_VERSION,
    CAMPAIGN_SPEC_VERSION,
    CampaignEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "CAMPAIGN_ENGINE_VERSION",
    "CAMPAIGN_METHOD_VERSION",
    "CAMPAIGN_NORMAL_VERSION",
    "CAMPAIGN_RESULT_FORMAT_VERSION",
    "CAMPAIGN_SPEC_VERSION",
    "EULER_MASCHERONI",
    "MIN_VALID_TRIALS",
    "N_MAX",
    "CampaignConfigurationError",
    "CampaignConsistencyError",
    "CampaignEngineVersion",
    "CampaignError",
    "CampaignSummary",
    "CampaignUndefinedReason",
    "ResearchCampaignEngine",
    "ResearchCampaignEvaluation",
    "ResearchCampaignSpecification",
    "StatStatus",
    "StatValue",
    "TrialStat",
    "TrialStatus",
    "campaign_id",
    "campaign_result_hash",
    "default_decimal_context",
    "standard_normal_cdf",
    "standard_normal_ppf",
    "trial_label",
]
