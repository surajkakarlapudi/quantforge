"""Campaign-level multiplicity correction over a campaign's PSR family (Phase 30).

The first **campaign-multiplicity** capability strictly above Phase 23: a pure consumer
that treats the per-trial Probabilistic-Sharpe-Ratio one-sided p-values
``p_i = 1 - PSR_i`` of one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` as a single hypothesis
family and asks the question the raw per-trial table cannot - *once we have run a PSR
test per trial, which trials individually beat the benchmark after correcting for the
size of the search?* It resolves the one campaign from the shared Phase 8 sidecar,
collects its KNOWN-``psr`` trials as the family (deriving ``p = 1 - PSR`` per trial,
recording each UNDEFINED-``psr`` trial as a first-class exclusion, never imputed), and
for each requested method seals the adjusted ``p`` value + rejection flag of every
family member at a declared ``alpha``. It re-resolves no data, introduces no new PIT
surface, adds no runtime dependency, and creates no new store.

The correction core (:func:`quantforge.multiplicity.compute.correct_family`) and its
method vocabulary are **reused verbatim** from Phase 25 - the campaign-level analogue of
the pairwise-comparison correction. The only added arithmetic is the exact-``Decimal``
``p = 1 - PSR`` transform.

* :class:`~quantforge.campaignmult.spec.CampaignMultiplicitySpecification` - the
  declarative, content-addressed request: a name, exactly one sealed
  ``source_campaign_id``, a declared ``alpha`` in ``(0, 1)``, and an ordered,
  duplicate-free tuple of :class:`~quantforge.campaignmult.model.CorrectionMethod`\\ s
  (default: Holm + Benjamini-Yekutieli, both valid under arbitrary dependence).
* :class:`~quantforge.campaignmult.engine.CampaignMultiplicityEngine` - resolves +
  verifies the source campaign (present, a ``ResearchCampaignEvaluation``, id matches),
  collects the KNOWN-``psr`` family + the UNDEFINED exclusions (CM-3), corrects the
  family by each method (:func:`~quantforge.multiplicity.compute.correct_family`), and
  seals a :class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection`,
  persisting it write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.campaign_multiplicity_engine`).
* :class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source campaign, the
  declared ``alpha``, the per-trial ``p`` value family (each with its consumed ``psr``
  and derived ``p = 1 - PSR``), the UNDEFINED exclusions, and per method the honest
  error-rate / dependence labels plus each family trial's adjusted ``p`` value +
  rejection flag. Satisfies the :class:`~quantforge.factors.store.ResearchRecord`
  Protocol and round-trips byte-identically. It is **ex-post, not PIT** (CM-6): not a
  ``Pit*`` type and no as-of accessor.
* :class:`~quantforge.campaignmult.model.CorrectionMethod` /
  :class:`~quantforge.campaignmult.model.ErrorRate` /
  :class:`~quantforge.campaignmult.model.DependenceAssumption` - the closed method
  vocabulary and each method's honest labels, re-exported verbatim from Phase 25.

Every identity is content-addressed (:mod:`quantforge.campaignmult.identity`) and
transitively pins the source campaign's ``result_hash``, every value is
deterministically serializable and computed in exact ``Decimal`` arithmetic under a
pinned context (no RNG, no float, no iterative solver), and every failure follows the
raise-vs-record split (:mod:`quantforge.campaignmult.errors`): a request / consistency
defect raises; a trial genuinely UNDEFINED in the source is excluded and recorded with
its reason.
"""

from __future__ import annotations

from quantforge.campaignmult.engine import CampaignMultiplicityEngine
from quantforge.campaignmult.errors import (
    CampaignMultiplicityConfigurationError,
    CampaignMultiplicityConsistencyError,
    CampaignMultiplicityError,
)
from quantforge.campaignmult.identity import (
    campaign_multiplicity_id,
    campaign_multiplicity_result_hash,
)
from quantforge.campaignmult.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
    method_dependence,
    method_error_rate,
)
from quantforge.campaignmult.result import (
    BOUNDARY_PIT,
    CAMPAIGNMULT_RESULT_FORMAT_VERSION,
    CampaignMultiplicityCorrection,
    CampaignMultiplicityCoverage,
    ExcludedTrialCell,
    MethodResult,
    TrialFamilyCell,
    TrialMethodCell,
)
from quantforge.campaignmult.spec import (
    DEFAULT_METHODS,
    CampaignMultiplicitySpecification,
)
from quantforge.campaignmult.version import (
    CAMPAIGNMULT_CORRECTION_VERSION,
    CAMPAIGNMULT_ENGINE_VERSION,
    CAMPAIGNMULT_METHOD_VERSION,
    CAMPAIGNMULT_SPEC_VERSION,
    CampaignMultiplicityEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "CAMPAIGNMULT_CORRECTION_VERSION",
    "CAMPAIGNMULT_ENGINE_VERSION",
    "CAMPAIGNMULT_METHOD_VERSION",
    "CAMPAIGNMULT_RESULT_FORMAT_VERSION",
    "CAMPAIGNMULT_SPEC_VERSION",
    "DEFAULT_METHODS",
    "CampaignMultiplicityConfigurationError",
    "CampaignMultiplicityConsistencyError",
    "CampaignMultiplicityCorrection",
    "CampaignMultiplicityCoverage",
    "CampaignMultiplicityEngine",
    "CampaignMultiplicityEngineVersion",
    "CampaignMultiplicityError",
    "CampaignMultiplicitySpecification",
    "CorrectionMethod",
    "DependenceAssumption",
    "ErrorRate",
    "ExcludedTrialCell",
    "MethodResult",
    "TrialFamilyCell",
    "TrialMethodCell",
    "campaign_multiplicity_id",
    "campaign_multiplicity_result_hash",
    "default_decimal_context",
    "method_dependence",
    "method_error_rate",
]
