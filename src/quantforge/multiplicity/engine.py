"""The multiple-comparison-correction orchestration engine (§6, §11, §12, MC-1..MC-6).

:class:`MultipleComparisonEngine` sits strictly **above** Phase 24: it is a pure
consumer that turns a declarative
:class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification` into a sealed
:class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` by *resolving* the
one already-sealed :class:`~quantforge.comparison.result.StrategyComparison` the request
names, *verifying* it, *collecting* the family of its KNOWN pairwise ``p`` values (and
recording each UNDEFINED pair as a first-class exclusion, never imputed), *correcting*
that family by each requested :class:`~quantforge.multiplicity.model.CorrectionMethod`
(:mod:`quantforge.multiplicity.compute`), and sealing the answer. It introduces no new
data-resolution logic, no new PIT surface, and no new store; it composes the pinned pure
:func:`~quantforge.multiplicity.compute.correct_family` under the version's decimal
context and persists write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_strategy_comparison_id`` from the shared sidecar via
   ``store.read_as(id, StrategyComparison.from_dict)``. A missing id (or a payload that
   does not decode as a ``StrategyComparison``) is a consistency defect and raises
   :class:`~quantforge.multiplicity.errors.MultiplicityConsistencyError` (fail closed,
   MC-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (MC-1).
3. **Collect the family** (MC-3): walk the source comparison's upper-triangle cells in
   their sealed order; a cell whose ``p_value`` is KNOWN joins the corrected family, a
   cell whose ``p_value`` is UNDEFINED becomes a first-class
   :class:`~quantforge.multiplicity.result.ExcludedCell` carrying the source's reason -
   never imputed, never coerced to a number.
4. **Correct** the family by each requested method
   (:func:`~quantforge.multiplicity.compute.correct_family`) under the version's decimal
   context: the adjusted ``p`` value + rejection flag (``p_adj ≤ alpha``) of every
   family member, plus each method's honest error-rate / dependence labels (MC-5/MC-6).
   An empty family yields empty per-method cell lists, never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` (its
   ``result_hash`` folds the answer, its id transitively pins the source comparison's
   ``result_hash``) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.comparison.model import StatStatus
from quantforge.comparison.result import ComparisonCell, StrategyComparison
from quantforge.factors.store import ResearchResultStore
from quantforge.multiplicity.compute import MethodComputation, correct_family
from quantforge.multiplicity.errors import (
    MultiplicityConfigurationError,
    MultiplicityConsistencyError,
)
from quantforge.multiplicity.model import method_dependence, method_error_rate
from quantforge.multiplicity.result import (
    ExcludedCell,
    FamilyCell,
    MethodCell,
    MethodResult,
    MultipleComparisonCorrection,
    MultiplicityCoverage,
)
from quantforge.multiplicity.spec import MultipleComparisonSpecification
from quantforge.multiplicity.version import MultipleComparisonEngineVersion
from quantforge.workspace import Workspace

__all__ = ["MultipleComparisonEngine"]


class MultipleComparisonEngine:
    """Resolve, verify, collect, correct, and seal a correction request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    comparison engine sealed its comparisons to - so a request corrects exactly the
    comparison already present. The sidecar may be overridden (for tests). The engine
    pins its orchestration logic + statistical method + decimal context via
    :class:`~quantforge.multiplicity.version.MultipleComparisonEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: MultipleComparisonEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else MultipleComparisonEngineVersion()
        )

    @property
    def multiplicity_engine_version_id(self) -> str:
        """The orchestration + method + decimal-context version, folded into every
        id."""
        return self._version.multiplicity_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the correction resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def correct(
        self, spec: MultipleComparisonSpecification
    ) -> MultipleComparisonCorrection:
        """Resolve, verify, collect, correct, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source comparison, recomputes byte-identical adjusted ``p``
        values under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.multiplicity.result.MultipleComparisonCorrection` on any
        machine (whose sidecar write is an idempotent no-op). Fails closed on a missing
        / drifted reference or a non-``StrategyComparison`` record (MC-1); a pairwise
        cell whose ``p`` value the source sealed as UNDEFINED is excluded from the
        family and recorded as a first-class
        :class:`~quantforge.multiplicity.result.ExcludedCell` (MC-3), never raised.
        """
        if not isinstance(spec, MultipleComparisonSpecification):
            raise MultiplicityConfigurationError(
                "correct() requires a MultipleComparisonSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source comparison (MC-1) ----------------
        source = self._resolve_comparison(spec.source_strategy_comparison_id, store)

        # -- collect the KNOWN-p family + the UNDEFINED exclusions (MC-3) ------
        family, family_p, excluded = self._collect_family(source.comparisons)

        # -- correct the family by each requested method (MC-5/MC-6) ----------
        alpha = Decimal(spec.alpha)
        computations = correct_family(family_p, spec.methods, alpha, context=context)
        corrections = tuple(
            self._method_result(computation, family) for computation in computations
        )

        coverage = MultiplicityCoverage(
            n_pairs_total=len(source.comparisons),
            family_size=len(family),
            n_excluded=len(excluded),
        )

        # -- seal + persist ---------------------------------------------------
        correction = MultipleComparisonCorrection.seal(
            multiplicity_engine_version_id=(
                self._version.multiplicity_engine_version_id
            ),
            correction_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source comparison's boundary through unchanged: it documents
            # that the underlying strategies were PIT walks. The correction output is
            # ex-post and is not a PIT value (MC-6).
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

    def _resolve_comparison(
        self, source_id: str, store: ResearchResultStore
    ) -> StrategyComparison:
        """Read + verify the one referenced source comparison (fail closed, MC-1)."""
        try:
            result = store.read_as(source_id, StrategyComparison.from_dict)
        except (KeyError, ValueError) as exc:
            raise MultiplicityConsistencyError(
                f"source comparison {source_id!r} could not be decoded as a "
                "StrategyComparison; the referenced artifact is absent or not a "
                "strategy "
                "comparison (fail closed)"
            ) from exc
        if result is None:
            raise MultiplicityConsistencyError(
                f"source comparison {source_id!r} is not present in the research "
                "sidecar; cannot correct a comparison that was never sealed (fail "
                "closed)"
            )
        if result.research_result_id != source_id:
            raise MultiplicityConsistencyError(
                f"source comparison {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar "
                "is inconsistent (fail closed)"
            )
        return result

    # -- family collection ----------------------------------------------------

    def _collect_family(
        self, cells: tuple[ComparisonCell, ...]
    ) -> tuple[tuple[FamilyCell, ...], list[Decimal], tuple[ExcludedCell, ...]]:
        """Split the source's upper-triangle cells into family + exclusions (MC-3).

        Walks the source comparison's cells in their sealed upper-triangle order. A cell
        whose ``p_value`` is KNOWN joins the corrected family (its canonical decimal
        string preserved verbatim, and parsed once to a ``Decimal`` for the correction
        math); a cell whose ``p_value`` is UNDEFINED becomes a first-class
        :class:`~quantforge.multiplicity.result.ExcludedCell` carrying the source's own
        reason - never imputed, never coerced to a number, never silently dropped.
        Family order is the source order, so every downstream adjusted value maps
        straight back to its ``(i, j)`` cell.
        """
        family: list[FamilyCell] = []
        family_p: list[Decimal] = []
        excluded: list[ExcludedCell] = []
        for cell in cells:
            p_value = cell.p_value
            if p_value.status is StatStatus.KNOWN:
                assert p_value.value is not None  # KNOWN ⇒ decimal string present
                family.append(
                    FamilyCell(
                        i=cell.i,
                        j=cell.j,
                        label_i=cell.label_i,
                        label_j=cell.label_j,
                        p_value=p_value.value,
                    )
                )
                family_p.append(Decimal(p_value.value))
            else:  # UNDEFINED p value ⇒ excluded, recorded with why
                assert p_value.reason is not None  # UNDEFINED ⇒ reason present
                excluded.append(
                    ExcludedCell(
                        i=cell.i,
                        j=cell.j,
                        label_i=cell.label_i,
                        label_j=cell.label_j,
                        reason=p_value.reason,
                    )
                )
        return tuple(family), family_p, tuple(excluded)

    # -- assembly -------------------------------------------------------------

    def _method_result(
        self, computation: MethodComputation, family: tuple[FamilyCell, ...]
    ) -> MethodResult:
        """Map one method's family-order computation into its sealed block (MC-5/MC-6).

        The adjusted ``p`` values and rejection flags arrive aligned index-for-index to
        the family order, so each maps straight onto its ``(i, j)`` cell. ``p_adjusted``
        is the canonical decimal string of the computed value (already carrying the
        pinned context's precision). The honest error-rate / dependence labels come from
        the single source of truth in :mod:`quantforge.multiplicity.model`, so
        Benjamini-Hochberg's independence assumption can never be mislabeled as
        dependence-robust (MC-6).
        """
        cells = tuple(
            MethodCell(
                i=member.i,
                j=member.j,
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
