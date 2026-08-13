"""The minimum-track-record-length orchestration engine (§6, §11, §12, MT-1..MT-6).

:class:`MinimumTrackRecordLengthEngine` sits strictly **above** Phase 23: it is a pure
consumer that turns a declarative
:class:`~quantforge.mintrl.spec.MinimumTrackRecordLengthSpecification` into a sealed
:class:`~quantforge.mintrl.result.MinimumTrackRecordLength` by *resolving* the one
already-sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` the
request names, *verifying* it, *classifying* each of its trials into the evaluable
family (or a first-class exclusion, never imputed), *computing* the per-trial minimum
track-record length and aggregate profile over that family
(:mod:`quantforge.mintrl.compute`), and sealing the answer. It introduces no new data
resolution, no new PIT surface, and no new store; it composes the pinned pure
:func:`~quantforge.mintrl.compute.evaluate_mintrl` under the version's decimal context
and persists write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_campaign_id`` from the shared sidecar via
   ``store.read_as(id, ResearchCampaignEvaluation.from_dict)``. A missing id (or a
   payload that does not decode as a ``ResearchCampaignEvaluation``) is a consistency
   defect and raises :class:`~quantforge.mintrl.errors.MinTrlConsistencyError` (fail
   closed, MT-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (MT-1).
3. **Classify the trials** (MT-3): walk the source's trials in their sealed order. A
   VALID trial whose ``sharpe`` / ``skew`` / ``kurtosis`` cells are all KNOWN joins the
   evaluable family (its three moments parsed once to ``Decimal`` for the MinTRL math,
   MT-4); every other trial becomes a first-class
   :class:`~quantforge.mintrl.result.ExcludedTrial` carrying its reason - never imputed,
   never coerced to a length.
4. **Compute** the family (:func:`~quantforge.mintrl.compute.evaluate_mintrl`) under the
   version's decimal context: ``Z_alpha = Φ⁻¹(confidence)`` once, then the per-trial
   MinTRL and excess length and the aggregate mean / dispersion / min / max /
   sufficient-frequency statistics, with ``mintrl_status`` defensible only when the
   determined family meets :data:`~quantforge.mintrl.result.MIN_DETERMINED_TRIALS`
   (MT-3/MT-5). An empty family yields empty per-trial cells and every aggregate
   UNDEFINED, never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.mintrl.result.MinimumTrackRecordLength` (its ``result_hash``
   folds the answer, its id transitively pins the source campaign's ``result_hash``) and
   persist it write-once to the same sidecar. Rebuilding an identical request is a
   byte-identical no-op; a differing payload under the same id fails closed via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.campaign.model import StatStatus, TrialStatus
from quantforge.campaign.result import ResearchCampaignEvaluation, TrialStat
from quantforge.factors.store import ResearchResultStore
from quantforge.mintrl.compute import EvaluableTrial, evaluate_mintrl
from quantforge.mintrl.errors import (
    MinTrlConfigurationError,
    MinTrlConsistencyError,
)
from quantforge.mintrl.model import MinTrlExcludedReason
from quantforge.mintrl.result import (
    MIN_DETERMINED_TRIALS,
    ExcludedTrial,
    MinimumTrackRecordLength,
    MinTrlCoverage,
    MinTrlSummary,
    TrialMinTrlCell,
)
from quantforge.mintrl.spec import MinimumTrackRecordLengthSpecification
from quantforge.mintrl.version import MinimumTrackRecordLengthEngineVersion
from quantforge.workspace import Workspace

__all__ = ["MinimumTrackRecordLengthEngine"]


class MinimumTrackRecordLengthEngine:
    """Resolve, verify, classify, compute, and seal a MinTRL request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    campaign engine sealed its evaluations to - so a request evaluates exactly the
    campaign already present. The sidecar may be overridden (for tests). The engine pins
    its orchestration logic + statistical method + normal primitive + decimal context
    via :class:`~quantforge.mintrl.version.MinimumTrackRecordLengthEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: MinimumTrackRecordLengthEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else MinimumTrackRecordLengthEngineVersion()
        )

    @property
    def minimum_track_record_length_engine_version_id(self) -> str:
        """The orchestration + method + normal + decimal-context version, folded into
        every id."""
        return self._version.minimum_track_record_length_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the evaluation resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(
        self, spec: MinimumTrackRecordLengthSpecification
    ) -> MinimumTrackRecordLength:
        """Resolve, verify, classify, compute, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source campaign, recomputes byte-identical MinTRLs and
        aggregates under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.mintrl.result.MinimumTrackRecordLength` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on a missing /
        drifted reference or a non-``ResearchCampaignEvaluation`` record (MT-1); a trial
        that is not evaluable is excluded from the family and recorded as a first-class
        :class:`~quantforge.mintrl.result.ExcludedTrial` (MT-3), never raised; an
        evaluable trial whose MinTRL is undefined for its moments seals an UNDEFINED
        cell with why.
        """
        if not isinstance(spec, MinimumTrackRecordLengthSpecification):
            raise MinTrlConfigurationError(
                "evaluate() requires a MinimumTrackRecordLengthSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source campaign (MT-1) ------------------
        source = self._resolve_campaign(spec.source_campaign_id, store)

        # -- classify trials: evaluable family + exclusions (MT-3/MT-4) -------
        evaluable, excluded = self._classify_trials(source.trials)

        # -- compute the family (MT-4/MT-5) -----------------------------------
        computation = evaluate_mintrl(
            evaluable,
            confidence=Decimal(spec.confidence),
            benchmark=Decimal(spec.benchmark_sharpe),
            min_determined=MIN_DETERMINED_TRIALS,
            context=context,
        )
        trials = tuple(
            TrialMinTrlCell(
                label=cell.label,
                observed_length=cell.observed_length,
                sharpe=cell.sharpe,
                skew=cell.skew,
                kurtosis=cell.kurtosis,
                min_track_record_length=cell.min_trl,
                excess_length=cell.excess_length,
            )
            for cell in computation.trials
        )
        summary = MinTrlSummary(
            mean_min_trl=computation.summary.mean_min_trl,
            min_trl_dispersion=computation.summary.min_trl_dispersion,
            max_min_trl=computation.summary.max_min_trl,
            min_min_trl=computation.summary.min_min_trl,
            sufficient_frequency=computation.summary.sufficient_frequency,
            n_determined=computation.summary.n_determined,
            mintrl_status=computation.summary.mintrl_status,
            status_reason=computation.summary.status_reason,
        )
        coverage = MinTrlCoverage(
            n_trials=len(source.trials),
            n_evaluable=len(evaluable),
            n_excluded=len(excluded),
        )

        # -- seal + persist ---------------------------------------------------
        evaluation = MinimumTrackRecordLength.seal(
            minimum_track_record_length_engine_version_id=(
                self._version.minimum_track_record_length_engine_version_id
            ),
            mintrl_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source campaign's boundary through unchanged: it documents that
            # the underlying trials were PIT walks. The MinTRL output is ex-post and is
            # not a PIT value (MT-6).
            boundary_kind=source.boundary_kind,
            trials=trials,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(evaluation)
        return evaluation

    # -- resolution & verification -------------------------------------------

    def _resolve_campaign(
        self, source_id: str, store: ResearchResultStore
    ) -> ResearchCampaignEvaluation:
        """Read + verify the one referenced source campaign (fail closed, MT-1)."""
        try:
            result = store.read_as(source_id, ResearchCampaignEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise MinTrlConsistencyError(
                f"source campaign {source_id!r} could not be decoded as a "
                "ResearchCampaignEvaluation; the referenced artifact is absent "
                "or not a research-campaign evaluation (fail closed)"
            ) from exc
        if result is None:
            raise MinTrlConsistencyError(
                f"source campaign {source_id!r} is not present in the research "
                "sidecar; cannot evaluate a campaign that was never sealed "
                "(fail closed)"
            )
        if result.research_result_id != source_id:
            raise MinTrlConsistencyError(
                f"source campaign {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- trial classification -------------------------------------------------

    def _classify_trials(
        self, trials: tuple[TrialStat, ...]
    ) -> tuple[tuple[EvaluableTrial, ...], tuple[ExcludedTrial, ...]]:
        """Split the source's trials into evaluable + exclusions (MT-3/MT-4).

        Walks the source campaign's trials in their sealed order. A VALID trial whose
        ``sharpe`` / ``skew`` / ``kurtosis`` cells are all KNOWN joins the evaluable
        family (its three moments parsed once to ``Decimal`` for the MinTRL math, MT-4);
        every other trial becomes a first-class
        :class:`~quantforge.mintrl.result.ExcludedTrial` carrying its reason - never
        imputed, never coerced to a length, never silently dropped. Family order is the
        source order, so every downstream MinTRL maps straight back to its trial
        ``label``. The classification order is deliberate: a non-VALID trial is
        ``TRIAL_UNDEFINED``; then all three moments must be KNOWN (``MOMENTS_UNDEFINED``
        guards the defensive, structurally-unreachable case of a VALID trial with a
        missing moment).
        """
        evaluable: list[EvaluableTrial] = []
        excluded: list[ExcludedTrial] = []
        for trial in trials:
            reason = self._exclusion_reason(trial)
            if reason is not None:
                excluded.append(ExcludedTrial(label=trial.label, reason=reason))
                continue
            # Evaluable: VALID with all three moments KNOWN (guaranteed by the reason
            # check returning None). Parse the sealed strings verbatim (MT-4).
            assert trial.sharpe.value is not None
            assert trial.skew.value is not None
            assert trial.kurtosis.value is not None
            evaluable.append(
                EvaluableTrial(
                    label=trial.label,
                    n=trial.n,
                    sharpe=Decimal(trial.sharpe.value),
                    skew=Decimal(trial.skew.value),
                    kurtosis=Decimal(trial.kurtosis.value),
                )
            )
        return tuple(evaluable), tuple(excluded)

    def _exclusion_reason(self, trial: TrialStat) -> MinTrlExcludedReason | None:
        """The reason ``trial`` is not evaluable, or ``None`` if it is (MT-3)."""
        if trial.status is not TrialStatus.VALID:
            return MinTrlExcludedReason.TRIAL_UNDEFINED
        for moment in (trial.sharpe, trial.skew, trial.kurtosis):
            if moment.status is not StatStatus.KNOWN or moment.value is None:
                # Defensive / structurally unreachable: a VALID campaign trial always
                # sealed all three moments KNOWN together.
                return MinTrlExcludedReason.MOMENTS_UNDEFINED
        return None
