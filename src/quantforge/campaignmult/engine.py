"""The campaign-multiplicity-correction orchestration engine (§6, §11, §12, CM-1..CM-6).

:class:`CampaignMultiplicityEngine` sits strictly **above** Phase 23: it is a pure
consumer that turns a declarative
:class:`~quantforge.campaignmult.spec.CampaignMultiplicitySpecification` into a sealed
:class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` by *resolving*
the one already-sealed :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`
the request names, *verifying* it, *collecting* the family of its per-trial one-sided
p-values ``p_i = 1 - PSR_i`` over the trials whose ``psr`` is KNOWN (and recording each
UNDEFINED-``psr`` trial as a first-class exclusion, never imputed), *correcting* that
family by each requested :class:`~quantforge.campaignmult.model.CorrectionMethod`
(:func:`quantforge.multiplicity.compute.correct_family`, **reused verbatim**), and
sealing the answer. It introduces no new data-resolution logic, no new PIT surface, and
no new store; it composes the pinned pure correction core under the version's decimal
context and persists write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_campaign_id`` from the shared sidecar via
   ``store.read_as(id, ResearchCampaignEvaluation.from_dict)``. A missing id (or a
   payload that does not decode as a ``ResearchCampaignEvaluation``) is a consistency
   defect and raises
   :class:`~quantforge.campaignmult.errors.CampaignMultiplicityConsistencyError` (fail
   closed, CM-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (CM-1).
3. **Collect the family** (CM-3/CM-4): walk the source campaign's trials in their sealed
   request order; a trial whose ``psr`` is KNOWN joins the corrected family (its ``psr``
   consumed verbatim, its ``p = 1 - PSR`` derived once under the pinned context), a
   trial whose ``psr`` is UNDEFINED becomes a first-class
   :class:`~quantforge.campaignmult.result.ExcludedTrialCell` carrying the source's own
   reason - never imputed, never coerced to a number.
4. **Correct** the family by each requested method
   (:func:`~quantforge.multiplicity.compute.correct_family`) under the version's decimal
   context: the adjusted ``p`` value + rejection flag (``p_adj ≤ alpha``) of every
   family member, plus each method's honest error-rate / dependence labels (CM-5/CM-6).
   An empty family yields empty per-method cell lists, never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` (its
   ``result_hash`` folds the answer, its id transitively pins the source campaign's
   ``result_hash``) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Context, Decimal, localcontext

from quantforge.campaign.model import StatStatus
from quantforge.campaign.result import ResearchCampaignEvaluation, TrialStat
from quantforge.campaignmult.errors import (
    CampaignMultiplicityConfigurationError,
    CampaignMultiplicityConsistencyError,
)
from quantforge.campaignmult.result import (
    CampaignMultiplicityCorrection,
    CampaignMultiplicityCoverage,
    ExcludedTrialCell,
    MethodResult,
    TrialFamilyCell,
    TrialMethodCell,
)
from quantforge.campaignmult.spec import CampaignMultiplicitySpecification
from quantforge.campaignmult.version import CampaignMultiplicityEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.multiplicity.compute import MethodComputation, correct_family
from quantforge.multiplicity.model import method_dependence, method_error_rate
from quantforge.workspace import Workspace

__all__ = ["CampaignMultiplicityEngine"]

_ONE = Decimal(1)


class CampaignMultiplicityEngine:
    """Resolve, verify, collect, correct, and seal a correction request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    campaign engine sealed its evaluations to - so a request corrects exactly the
    campaign already present. The sidecar may be overridden (for tests). The engine pins
    its orchestration logic + own method + reused correction core + decimal context via
    :class:`~quantforge.campaignmult.version.CampaignMultiplicityEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: CampaignMultiplicityEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else CampaignMultiplicityEngineVersion()
        )

    @property
    def campaign_multiplicity_engine_version_id(self) -> str:
        """The orchestration + method + correction + decimal-context version, folded
        into every id."""
        return self._version.campaign_multiplicity_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the correction resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def correct(
        self, spec: CampaignMultiplicitySpecification
    ) -> CampaignMultiplicityCorrection:
        """Resolve, verify, collect, correct, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source campaign, recomputes byte-identical ``p = 1 - PSR``
        transforms and adjusted ``p`` values under the pinned decimal context, and seals
        a byte-identical
        :class:`~quantforge.campaignmult.result.CampaignMultiplicityCorrection` on any
        machine (whose sidecar write is an idempotent no-op). Fails closed on a missing
        / drifted reference or a non-``ResearchCampaignEvaluation`` record (CM-1);
        a trial whose ``psr`` the source sealed as UNDEFINED is excluded from the family
        and recorded as a first-class
        :class:`~quantforge.campaignmult.result.ExcludedTrialCell` (CM-3), never raised.
        """
        if not isinstance(spec, CampaignMultiplicitySpecification):
            raise CampaignMultiplicityConfigurationError(
                "correct() requires a CampaignMultiplicitySpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source campaign (CM-1) ------------------
        source = self._resolve_campaign(spec.source_campaign_id, store)

        # -- collect the KNOWN-psr family + the UNDEFINED exclusions (CM-3/4) --
        family, family_p, excluded = self._collect_family(source.trials, context)

        # -- correct the family by each requested method (CM-5/CM-6) ----------
        alpha = Decimal(spec.alpha)
        computations = correct_family(family_p, spec.methods, alpha, context=context)
        corrections = tuple(
            self._method_result(computation, family) for computation in computations
        )

        coverage = CampaignMultiplicityCoverage(
            n_trials_total=len(source.trials),
            family_size=len(family),
            n_excluded=len(excluded),
        )

        # -- seal + persist ---------------------------------------------------
        correction = CampaignMultiplicityCorrection.seal(
            campaign_multiplicity_engine_version_id=(
                self._version.campaign_multiplicity_engine_version_id
            ),
            correction_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source campaign's boundary through unchanged: it documents that
            # the underlying trials were PIT walks. The correction output is ex-post and
            # is not a PIT value (CM-6).
            boundary_kind=source.boundary_kind,
            family=family,
            excluded=excluded,
            corrections=corrections,
            coverage=coverage,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(correction)
        return correction

    # -- resolution & verification -------------------------------------------

    def _resolve_campaign(
        self, source_id: str, store: ResearchResultStore
    ) -> ResearchCampaignEvaluation:
        """Read + verify the one referenced source campaign (fail closed, CM-1)."""
        try:
            result = store.read_as(source_id, ResearchCampaignEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise CampaignMultiplicityConsistencyError(
                f"source campaign {source_id!r} could not be decoded as a "
                "ResearchCampaignEvaluation; the referenced artifact is absent or not "
                "a research-campaign evaluation (fail closed)"
            ) from exc
        if result is None:
            raise CampaignMultiplicityConsistencyError(
                f"source campaign {source_id!r} is not present in the research "
                "sidecar; cannot correct a campaign that was never sealed (fail closed)"
            )
        if result.research_result_id != source_id:
            raise CampaignMultiplicityConsistencyError(
                f"source campaign {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- family collection ----------------------------------------------------

    def _collect_family(
        self, trials: tuple[TrialStat, ...], context: Context
    ) -> tuple[
        tuple[TrialFamilyCell, ...], list[Decimal], tuple[ExcludedTrialCell, ...]
    ]:
        """Split the source's trials into family + exclusions (CM-3/CM-4).

        Walks the source campaign's trials in their sealed request order. A trial whose
        ``psr`` is KNOWN joins the corrected family: its ``psr`` is preserved verbatim,
        and its one-sided p-value ``p = 1 - PSR`` is derived once under the pinned
        decimal context (the only added arithmetic; ``PSR`` is a ``Phi`` value in
        ``[0, 1]``, so ``p`` is in ``[0, 1]`` by construction - no clamp, no repair). A
        trial whose ``psr`` is UNDEFINED becomes a first-class
        :class:`~quantforge.campaignmult.result.ExcludedTrialCell` carrying the source's
        own reason - never imputed, never coerced to a number, never silently dropped.
        Family order is the source order, so every downstream adjusted value maps
        straight back to its trial ``index``.
        """
        family: list[TrialFamilyCell] = []
        family_p: list[Decimal] = []
        excluded: list[ExcludedTrialCell] = []
        with localcontext(context):
            for index, trial in enumerate(trials):
                psr = trial.psr
                if psr.status is StatStatus.KNOWN:
                    assert psr.value is not None  # KNOWN => decimal string present
                    # p = 1 - PSR: the one-sided p-value of H0: true Sharpe <=
                    # benchmark.
                    p_value = _ONE - Decimal(psr.value)
                    p_str = str(+p_value)
                    family.append(
                        TrialFamilyCell(
                            index=index,
                            label=trial.label,
                            psr=psr.value,
                            p_value=p_str,
                        )
                    )
                    # Parse the canonical string back so the value corrected is exactly
                    # the value sealed.
                    family_p.append(Decimal(p_str))
                else:  # UNDEFINED psr => excluded, recorded with why
                    assert psr.reason is not None  # UNDEFINED => reason present
                    excluded.append(
                        ExcludedTrialCell(
                            index=index,
                            label=trial.label,
                            reason=psr.reason,
                        )
                    )
        return tuple(family), family_p, tuple(excluded)

    # -- assembly -------------------------------------------------------------

    def _method_result(
        self, computation: MethodComputation, family: tuple[TrialFamilyCell, ...]
    ) -> MethodResult:
        """Map one method's family-order computation into its sealed block (CM-5/CM-6).

        The adjusted ``p`` values and rejection flags arrive aligned index-for-index to
        the family order, so each maps straight onto its trial ``index``. ``p_adjusted``
        is the canonical decimal string of the computed value (already carrying the
        pinned context's precision). The honest error-rate / dependence labels come from
        the single source of truth in :mod:`quantforge.multiplicity.model`, so
        Benjamini-Hochberg's independence assumption can never be mislabeled as
        dependence-robust (CM-6).
        """
        cells = tuple(
            TrialMethodCell(
                index=member.index,
                p_adjusted=str(adjusted),
                rejected=rejected,
            )
            for member, adjusted, rejected in zip(
                family, computation.adjusted, computation.rejected, strict=True
            )
        )
        n_rejected = sum(1 for cell in cells if cell.rejected)
        return MethodResult(
            method=computation.method,
            error_rate=method_error_rate(computation.method),
            dependence=method_dependence(computation.method),
            cells=cells,
            n_rejected=n_rejected,
        )
