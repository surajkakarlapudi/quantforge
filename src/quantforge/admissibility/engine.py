"""The strategy-admissibility orchestration engine (§6, §11, §12, AD-1..AD-6).

:class:`AdmissibilityEngine` sits strictly **above** Phases 27/29/32: it is a pure
consumer that turns a declarative
:class:`~quantforge.admissibility.spec.AdmissibilitySpecification` into a sealed
:class:`~quantforge.admissibility.result.StrategyAdmissibility` by *resolving* the three
already-sealed ex-post verdicts the request names, *verifying* each, *reducing* each to
the primitive fact it contributes (its sealed status / p-value / edge direction, read
verbatim - never recomputed, AD-4), *deciding* the joint admissibility verdict
(:func:`~quantforge.admissibility.compute.decide_admissibility`), and sealing the
answer. It introduces no new data resolution, no new PIT surface, and no new store; it
composes the pinned pure decision under the version's decimal context and persists
write-once to the shared research sidecar (§6, §13, §16). It is the first multi-source
consumer in the research spine - it resolves three sealed artifacts rather than one -
but each resolution follows the identical fail-closed contract every prior consumer
uses.

The build (§6):

1. **Resolve** each of ``source_stability_id`` /
   ``source_calibration_significance_id`` / ``source_net_of_cost_significance_id`` from
   the shared sidecar via ``store.read_as(id, <T>.from_dict)``. A missing id (or a
   payload that does not decode as the expected type) is a consistency defect and raises
   :class:`~quantforge.admissibility.errors.AdmissibilityConsistencyError` (fail closed,
   AD-1).
2. **Verify** each resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (AD-1).
3. **Reduce** each verdict to its primitive fact (AD-4): the stability book's STABLE
   flag; the calibration test's TESTED + KNOWN two-sided p-value; the net-of-cost test's
   TESTED + KNOWN one-sided p-value and PROFITABLE edge. A source that is itself
   UNDEFINED yields a not-defined fact - never raised, never fabricated.
4. **Decide** the joint verdict
   (:func:`~quantforge.admissibility.compute.decide_admissibility`) under the version's
   decimal context: the three per-criterion pass tests against the declared ``alpha``
   and the fail-closed roll-up (ADMISSIBLE iff all pass; UNDEFINED iff any criterion
   undefined; else INADMISSIBLE, AD-2/AD-3).
5. **Seal + persist**: seal a
   :class:`~quantforge.admissibility.result.StrategyAdmissibility` (its ``result_hash``
   folds the answer, its id transitively pins all three sources' ``result_hash``) and
   persist it write-once to the same sidecar. Rebuilding an identical request is a
   byte-identical no-op; a differing payload under the same id fails closed via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.admissibility.compute import (
    AdmissibilityInputs,
    decide_admissibility,
)
from quantforge.admissibility.errors import (
    AdmissibilityConfigurationError,
    AdmissibilityConsistencyError,
)
from quantforge.admissibility.result import (
    BOUNDARY_PIT,
    AdmissibilitySummary,
    StrategyAdmissibility,
)
from quantforge.admissibility.spec import AdmissibilitySpecification
from quantforge.admissibility.version import AdmissibilityEngineVersion
from quantforge.calsig.model import SignificanceStatus as CalibrationSignificanceStatus
from quantforge.calsig.model import StatStatus as CalibrationStatStatus
from quantforge.calsig.result import CalibrationSignificance
from quantforge.factors.store import ResearchResultStore
from quantforge.netcostsig.model import EdgeDirection
from quantforge.netcostsig.model import SignificanceStatus as NetSignificanceStatus
from quantforge.netcostsig.model import StatStatus as NetStatStatus
from quantforge.netcostsig.result import NetOfCostSignificance
from quantforge.stability.model import StabilityStatus
from quantforge.stability.result import WalkForwardStability
from quantforge.workspace import Workspace

__all__ = ["AdmissibilityEngine"]


class AdmissibilityEngine:
    """Resolve, verify, reduce, decide, and seal an admissibility request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    stability, calibration-significance, and net-of-cost-significance engines sealed
    their verdicts to - so a request evaluates exactly the three records already
    present. The sidecar may be overridden (for tests). The engine pins its
    orchestration logic + decision method + decimal context via
    :class:`~quantforge.admissibility.version.AdmissibilityEngineVersion`, and decides
    every verdict under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: AdmissibilityEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else AdmissibilityEngineVersion()

    @property
    def admissibility_engine_version_id(self) -> str:
        """The orchestration + method + decimal-context version, folded into every
        id."""
        return self._version.admissibility_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the admissibility resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(self, spec: AdmissibilitySpecification) -> StrategyAdmissibility:
        """Resolve, verify, reduce, decide, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same three verdicts, re-derives byte-identical primitive facts,
        recomputes the same joint verdict under the pinned decimal context, and seals a
        byte-identical
        :class:`~quantforge.admissibility.result.StrategyAdmissibility` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on a missing /
        drifted reference or a wrong-typed record (AD-1); a consumed verdict that is
        itself UNDEFINED yields a sealed record whose criterion - and roll-up - is
        UNDEFINED (AD-2), never raised.
        """
        if not isinstance(spec, AdmissibilitySpecification):
            raise AdmissibilityConfigurationError(
                "evaluate() requires an AdmissibilitySpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the three source verdicts (AD-1) ----------------
        stability = self._resolve_stability(spec.source_stability_id, store)
        calibration = self._resolve_calibration(
            spec.source_calibration_significance_id, store
        )
        net_of_cost = self._resolve_net_of_cost(
            spec.source_net_of_cost_significance_id, store
        )

        # -- reduce each verdict to its primitive fact (AD-4) -----------------
        inputs = _inputs(stability, calibration, net_of_cost)

        # -- decide the joint verdict (AD-2/AD-3) -----------------------------
        computation = decide_admissibility(
            inputs, alpha=Decimal(spec.alpha), context=context
        )
        summary = AdmissibilitySummary(
            verdict=computation.verdict,
            alpha=spec.alpha,
            criteria=computation.criteria,
        )

        # -- seal + persist ---------------------------------------------------
        admissibility = StrategyAdmissibility.seal(
            admissibility_engine_version_id=(
                self._version.admissibility_engine_version_id
            ),
            admissibility_spec=spec.to_dict(),
            stability_ref=(stability.research_result_id, stability.result_hash),
            calibration_ref=(
                calibration.research_result_id,
                calibration.result_hash,
            ),
            net_of_cost_ref=(
                net_of_cost.research_result_id,
                net_of_cost.result_hash,
            ),
            # All three verdicts descend from PIT walks; the admissibility output is
            # ex-post and is not a PIT value (AD-6).
            boundary_kind=BOUNDARY_PIT,
            summary=summary,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(admissibility)
        return admissibility

    # -- resolution & verification -------------------------------------------

    def _resolve_stability(
        self, source_id: str, store: ResearchResultStore
    ) -> WalkForwardStability:
        """Read + verify the referenced source stability record (fail closed, AD-1)."""
        try:
            result = store.read_as(source_id, WalkForwardStability.from_dict)
        except (KeyError, ValueError) as exc:
            raise AdmissibilityConsistencyError(
                f"source stability record {source_id!r} could not be decoded as a "
                "WalkForwardStability; the referenced artifact is absent or not a "
                "walk-forward stability (fail closed)"
            ) from exc
        if result is None:
            raise AdmissibilityConsistencyError(
                f"source stability record {source_id!r} is not present in the research "
                "sidecar; cannot judge a strategy whose stability was never sealed "
                "(fail closed)"
            )
        if result.research_result_id != source_id:
            raise AdmissibilityConsistencyError(
                f"source stability record {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    def _resolve_calibration(
        self, source_id: str, store: ResearchResultStore
    ) -> CalibrationSignificance:
        """Read + verify the referenced source calibration record (fail closed,
        AD-1)."""
        try:
            result = store.read_as(source_id, CalibrationSignificance.from_dict)
        except (KeyError, ValueError) as exc:
            raise AdmissibilityConsistencyError(
                f"source calibration-significance record {source_id!r} could not be "
                "decoded as a CalibrationSignificance; the referenced artifact is "
                "absent or not a calibration significance (fail closed)"
            ) from exc
        if result is None:
            raise AdmissibilityConsistencyError(
                f"source calibration-significance record {source_id!r} is not present "
                "in the research sidecar; cannot judge a strategy whose calibration "
                "significance was never sealed (fail closed)"
            )
        if result.research_result_id != source_id:
            raise AdmissibilityConsistencyError(
                f"source calibration-significance record {source_id!r} resolved to a "
                f"record whose id {result.research_result_id!r} disagrees with the "
                "request; the sidecar is inconsistent (fail closed)"
            )
        return result

    def _resolve_net_of_cost(
        self, source_id: str, store: ResearchResultStore
    ) -> NetOfCostSignificance:
        """Read + verify the referenced source net-of-cost record (fail closed,
        AD-1)."""
        try:
            result = store.read_as(source_id, NetOfCostSignificance.from_dict)
        except (KeyError, ValueError) as exc:
            raise AdmissibilityConsistencyError(
                f"source net-of-cost-significance record {source_id!r} could not be "
                "decoded as a NetOfCostSignificance; the referenced artifact is absent "
                "or not a net-of-cost significance (fail closed)"
            ) from exc
        if result is None:
            raise AdmissibilityConsistencyError(
                f"source net-of-cost-significance record {source_id!r} is not present "
                "in the research sidecar; cannot judge a strategy whose after-cost "
                "significance was never sealed (fail closed)"
            )
        if result.research_result_id != source_id:
            raise AdmissibilityConsistencyError(
                f"source net-of-cost-significance record {source_id!r} resolved to a "
                f"record whose id {result.research_result_id!r} disagrees with the "
                "request; the sidecar is inconsistent (fail closed)"
            )
        return result


# -- verdict reduction (verbatim, AD-4) --------------------------------------


def _inputs(
    stability: WalkForwardStability,
    calibration: CalibrationSignificance,
    net_of_cost: NetOfCostSignificance,
) -> AdmissibilityInputs:
    """Reduce the three sealed verdicts to the primitive facts the rule needs (AD-4).

    Every field is read verbatim from a source record - no statistic is recomputed. A
    source that is itself UNDEFINED (an UNDEFINED stability status, a non-TESTED
    significance, a non-KNOWN p-value cell) yields a not-defined fact, so its criterion
    is UNDEFINED and the roll-up fails closed (AD-2).
    """
    stability_stable = stability.stability_status is StabilityStatus.STABLE

    cal_cell = calibration.summary.p_value
    calibration_defined = (
        calibration.significance_status is CalibrationSignificanceStatus.TESTED
        and cal_cell.status is CalibrationStatStatus.KNOWN
        and cal_cell.value is not None
    )
    calibration_p = (
        Decimal(cal_cell.value)
        if calibration_defined and cal_cell.value is not None
        else None
    )

    net_cell = net_of_cost.summary.p_value
    net_defined = (
        net_of_cost.significance_status is NetSignificanceStatus.TESTED
        and net_cell.status is NetStatStatus.KNOWN
        and net_cell.value is not None
    )
    net_p = (
        Decimal(net_cell.value) if net_defined and net_cell.value is not None else None
    )
    net_profitable = net_of_cost.summary.edge_direction is EdgeDirection.PROFITABLE

    return AdmissibilityInputs(
        stability_stable=stability_stable,
        calibration_defined=calibration_defined,
        calibration_p=calibration_p,
        net_defined=net_defined,
        net_p=net_p,
        net_profitable=net_profitable,
    )
