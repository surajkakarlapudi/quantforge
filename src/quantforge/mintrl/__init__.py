"""Minimum track-record length over one sealed research campaign (Phase 28).

The first **required-track-record** capability strictly above Phase 23: a pure
consumer that reads, per trial of one sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`, that trial's
sealed out-of-sample per-period Sharpe ``SR``, skew ``gamma₃``, non-excess
kurtosis ``gamma₄`` and OOS period count ``n``, and asks the question the
campaign never answers directly - *how long a track record would this strategy
need before its Sharpe is significant, at confidence ``alpha``, against a
benchmark ``SR*``?* (Bailey & López de Prado). It is the algebraic inverse of
Phase 23's Probabilistic Sharpe Ratio - it reuses the identical
estimator-variance term ``V = 1 - gamma₃·SR + ((gamma₄-1)/4)·SR²`` and the same
degeneracy guard, and the *reused* deterministic standard-normal quantile
:func:`~quantforge._stats.normal.standard_normal_ppf` for ``Z_alpha`` - so it
adds no new statistical primitive. It resolves the one campaign from the shared
Phase 8 sidecar, classifies each trial into the evaluable family (recording
every non-evaluable trial as a first-class exclusion, never imputed), and seals
the per-trial minimum track-record length plus the aggregate MinTRL profile. It
re-resolves no data, introduces no new PIT surface, adds no runtime dependency,
uses no ``_linalg`` primitive, and creates no new store.

* :class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification` - the
  declarative, content-addressed request: a name, exactly one sealed
  ``source_campaign_id``, a confidence ``alpha`` (``0 < alpha < 1``), and a
  benchmark Sharpe ``SR*``.
* :class:`~quantforge.mintrl.engine.MinimumTrackRecordLengthEngine` - resolves +
  verifies the source campaign (present, a ``ResearchCampaignEvaluation``, id
  matches), classifies the evaluable family + the exclusions (MT-3), computes
  the family (:func:`~quantforge.mintrl.compute.evaluate_mintrl`), and seals a
  :class:`~quantforge.mintrl.result.MinimumTrackRecordLength`, persisting it
  write-once to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.mintrl_engine`).
* :class:`~quantforge.mintrl.result.MinimumTrackRecordLength` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source
  campaign, per evaluable trial the MinTRL and excess length, the excluded
  trials, and the aggregate :class:`~quantforge.mintrl.result.MinTrlSummary` (mean,
  dispersion, min / max, sufficient-frequency, roll-up status). Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (MT-6): not a ``Pit*`` type and
  no as-of accessor.
* :class:`~quantforge.mintrl.model.MinTrlStatus` /
  :class:`~quantforge.mintrl.model.MinTrlExcludedReason` /
  :class:`~quantforge.mintrl.model.MinTrlUndefinedReason` /
  :class:`~quantforge.mintrl.model.MinTrlStat` - the closed fail-closed
  vocabulary: whether the aggregate is defensible, why a trial is excluded, why
  a length / aggregate is UNDEFINED, and the UNDEFINED-preserving stat cell.

Every identity is content-addressed (:mod:`quantforge.mintrl.identity`) and
transitively pins the source campaign's ``result_hash``, every value is
deterministically serializable and computed in exact ``Decimal`` arithmetic under
a pinned context (``Decimal.sqrt`` and the reused ``Z⁻¹`` bisection the only
transcendentals; no RNG, no float, no unbounded iteration), and every failure
follows the raise-vs-record split (:mod:`quantforge.mintrl.errors`): a request /
consistency defect raises; a trial genuinely non-evaluable in the source is
excluded and recorded with its reason, and an evaluable trial whose MinTRL is
undefined for its moments seals an UNDEFINED cell with why.
"""

from __future__ import annotations

from quantforge.mintrl.compute import (
    EvaluableTrial,
    MinTrlComputation,
    MinTrlSummaryComputation,
    TrialMinTrlComputation,
    evaluate_mintrl,
)
from quantforge.mintrl.engine import MinimumTrackRecordLengthEngine
from quantforge.mintrl.errors import (
    MinTrlConfigurationError,
    MinTrlConsistencyError,
    MinTrlError,
)
from quantforge.mintrl.identity import (
    minimum_track_record_length_id,
    minimum_track_record_length_result_hash,
)
from quantforge.mintrl.model import (
    MinTrlExcludedReason,
    MinTrlStat,
    MinTrlStatus,
    MinTrlUndefinedReason,
    StatStatus,
)
from quantforge.mintrl.result import (
    BOUNDARY_PIT,
    MIN_DETERMINED_TRIALS,
    MINTRL_RESULT_FORMAT_VERSION,
    ExcludedTrial,
    MinimumTrackRecordLength,
    MinTrlCoverage,
    MinTrlSummary,
    TrialMinTrlCell,
)
from quantforge.mintrl.spec import MinimumTrackRecordLengthSpecification
from quantforge.mintrl.version import (
    MINTRL_ENGINE_VERSION,
    MINTRL_METHOD_VERSION,
    MINTRL_NORMAL_VERSION,
    MINTRL_SPEC_VERSION,
    MinimumTrackRecordLengthEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "MINTRL_ENGINE_VERSION",
    "MINTRL_METHOD_VERSION",
    "MINTRL_NORMAL_VERSION",
    "MINTRL_RESULT_FORMAT_VERSION",
    "MINTRL_SPEC_VERSION",
    "MIN_DETERMINED_TRIALS",
    "EvaluableTrial",
    "ExcludedTrial",
    "MinTrlComputation",
    "MinTrlConfigurationError",
    "MinTrlConsistencyError",
    "MinTrlCoverage",
    "MinTrlError",
    "MinTrlExcludedReason",
    "MinTrlStat",
    "MinTrlStatus",
    "MinTrlSummary",
    "MinTrlSummaryComputation",
    "MinTrlUndefinedReason",
    "MinimumTrackRecordLength",
    "MinimumTrackRecordLengthEngine",
    "MinimumTrackRecordLengthEngineVersion",
    "MinimumTrackRecordLengthSpecification",
    "StatStatus",
    "TrialMinTrlCell",
    "TrialMinTrlComputation",
    "default_decimal_context",
    "evaluate_mintrl",
    "minimum_track_record_length_id",
    "minimum_track_record_length_result_hash",
]
