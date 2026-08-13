"""The walk-forward turnover & stability orchestration engine (§6, §11, §12, WS-1..6).

:class:`WalkForwardStabilityEngine` sits strictly **above** Phase 22: it is a pure
consumer that turns a declarative
:class:`~quantforge.stability.spec.WalkForwardStabilitySpecification` into a sealed
:class:`~quantforge.stability.result.WalkForwardStability` by *resolving* the one
already-sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation` the request
names, *verifying* it, *classifying* each of its windows into the REALIZED family
(each carrying a KNOWN GMV weight vector parsed once to ``Decimal``) or a first-class
exclusion (never imputed), *analyzing* that family
(:mod:`quantforge.stability.compute`), and
sealing the answer. It introduces no new data-resolution logic, no new PIT surface, and
no new store; it composes the pinned pure
:func:`~quantforge.stability.compute.analyze_stability` under the version's decimal
context and persists write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_walk_forward_id`` from the shared sidecar via
   ``store.read_as(id, WalkForwardEvaluation.from_dict)``. A missing id (or a payload
   that does not decode as a ``WalkForwardEvaluation``) is a consistency defect and
   raises :class:`~quantforge.stability.errors.StabilityConsistencyError` (fail closed,
   WS-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (WS-1).
3. **Classify the windows** (WS-2/WS-4): walk the source's windows in their sealed
   order. A REALIZED window contributes a REALIZED
   :class:`~quantforge.stability.compute.SourceWindow` carrying its weight vector
   parsed once to ``Decimal`` (a malformed vector - any non-KNOWN cell, or a length
   that disagrees with the walk's ``n_factors`` - is a corrupt source and raises,
   :class:`~quantforge.stability.errors.StabilityConsistencyError`, WS-4); every
   UNDEFINED
   window becomes a first-class
   :class:`~quantforge.stability.result.ExcludedWindow` (``WINDOW_UNDEFINED``) *and*
   a non-realized :class:`~quantforge.stability.compute.SourceWindow` (so the analyzer
   sees the gap and never fabricates a turnover across it).
4. **Analyze** the family
   (:func:`~quantforge.stability.compute.analyze_stability`) under the version's
   decimal context: the per-window gross leverage / concentration /
   effective breadth / max-abs weight / one-way turnover and the aggregate turnover /
   concentration statistics, with ``stability_status`` defensible only when the
   realized-adjacent transitions meet
   :data:`~quantforge.stability.result.MIN_STABILITY_TRANSITIONS` (WS-3). No
   transitions yields every turnover aggregate UNDEFINED, never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.stability.result.WalkForwardStability` (its ``result_hash`` folds
   the answer, its id transitively pins the source walk's ``result_hash``) and persist
   it write-once to the same sidecar. Rebuilding an identical request is a
   byte-identical no-op; a differing payload under the same id fails closed via the
   store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.factors.store import ResearchResultStore
from quantforge.stability.compute import SourceWindow, analyze_stability
from quantforge.stability.errors import (
    StabilityConfigurationError,
    StabilityConsistencyError,
)
from quantforge.stability.model import StabilityExcludedReason, StatStatus
from quantforge.stability.result import (
    MIN_STABILITY_TRANSITIONS,
    ExcludedWindow,
    StabilityCoverage,
    StabilitySummary,
    WalkForwardStability,
    WindowStabilityCell,
)
from quantforge.stability.spec import WalkForwardStabilitySpecification
from quantforge.stability.version import WalkForwardStabilityEngineVersion
from quantforge.walkforward.model import StatStatus as WalkStatStatus
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation, WindowResult
from quantforge.workspace import Workspace

__all__ = ["WalkForwardStabilityEngine"]


class WalkForwardStabilityEngine:
    """Resolve, verify, classify, analyze, and seal a stability request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    walk-forward engine sealed its evaluations to - so a request analyzes exactly the
    walk-forward already present. The sidecar may be overridden (for tests). The engine
    pins its orchestration logic + statistical method + decimal context via
    :class:`~quantforge.stability.version.WalkForwardStabilityEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: WalkForwardStabilityEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else WalkForwardStabilityEngineVersion()
        )

    @property
    def stability_engine_version_id(self) -> str:
        """The orchestration + method + decimal-context version, folded into every
        id."""
        return self._version.stability_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the analysis resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def analyze(self, spec: WalkForwardStabilitySpecification) -> WalkForwardStability:
        """Resolve, verify, classify, analyze, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source walk-forward, recomputes byte-identical metrics and
        aggregates under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.stability.result.WalkForwardStability` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on a missing / drifted
        reference, a non-``WalkForwardEvaluation`` record (WS-1), or a REALIZED window
        with a malformed weight vector (WS-4); a window the source sealed UNDEFINED is
        excluded from the family and recorded as a first-class
        :class:`~quantforge.stability.result.ExcludedWindow` (WS-3), never raised.
        """
        if not isinstance(spec, WalkForwardStabilitySpecification):
            raise StabilityConfigurationError(
                "analyze() requires a WalkForwardStabilitySpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source walk-forward (WS-1) --------------
        source = self._resolve_walk_forward(spec.source_walk_forward_id, store)

        # -- classify windows: REALIZED family + exclusions (WS-2/WS-4) -------
        source_windows, excluded = self._classify_windows(
            source.windows, source.n_factors
        )

        # -- analyze the family (WS-3/WS-5) -----------------------------------
        computation = analyze_stability(
            source_windows,
            min_transitions=MIN_STABILITY_TRANSITIONS,
            context=context,
        )
        windows = tuple(
            WindowStabilityCell(
                index=metrics.index,
                gross_leverage=metrics.gross_leverage,
                concentration_hhi=metrics.concentration_hhi,
                effective_breadth=metrics.effective_breadth,
                max_abs_weight=metrics.max_abs_weight,
                turnover_from_prev=metrics.turnover_from_prev,
            )
            for metrics in computation.windows
        )
        summary = StabilitySummary(
            mean_turnover=computation.summary.mean_turnover,
            turnover_dispersion=computation.summary.turnover_dispersion,
            max_turnover=computation.summary.max_turnover,
            min_turnover=computation.summary.min_turnover,
            mean_gross_leverage=computation.summary.mean_gross_leverage,
            max_gross_leverage=computation.summary.max_gross_leverage,
            mean_concentration_hhi=computation.summary.mean_concentration_hhi,
            mean_effective_breadth=computation.summary.mean_effective_breadth,
            stability_status=computation.summary.stability_status,
            status_reason=computation.summary.status_reason,
        )
        n_transitions = sum(
            1
            for metrics in computation.windows
            if metrics.turnover_from_prev.status is StatStatus.KNOWN
        )
        coverage = StabilityCoverage(
            n_windows=len(source.windows),
            n_realized=len(computation.windows),
            n_excluded=len(excluded),
            n_transitions=n_transitions,
        )

        # -- seal + persist ---------------------------------------------------
        stability = WalkForwardStability.seal(
            stability_engine_version_id=self._version.stability_engine_version_id,
            stability_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source walk-forward's boundary through unchanged: it documents
            # that the underlying factor portfolios were PIT walks. The stability output
            # is ex-post and is not a PIT value (WS-6).
            boundary_kind=source.boundary_kind,
            windows=windows,
            excluded=excluded,
            summary=summary,
            coverage=coverage,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(stability)
        return stability

    # -- resolution & verification -------------------------------------------

    def _resolve_walk_forward(
        self, source_id: str, store: ResearchResultStore
    ) -> WalkForwardEvaluation:
        """Read + verify the one referenced source walk-forward (fail closed, WS-1)."""
        try:
            result = store.read_as(source_id, WalkForwardEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise StabilityConsistencyError(
                f"source walk-forward {source_id!r} could not be decoded as a "
                "WalkForwardEvaluation; the referenced artifact is absent or not a "
                "walk-forward evaluation (fail closed)"
            ) from exc
        if result is None:
            raise StabilityConsistencyError(
                f"source walk-forward {source_id!r} is not present in the research "
                "sidecar; cannot analyze a walk-forward that was never sealed (fail "
                "closed)"
            )
        if result.research_result_id != source_id:
            raise StabilityConsistencyError(
                f"source walk-forward {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- window classification ------------------------------------------------

    def _classify_windows(
        self, windows: tuple[WindowResult, ...], n_factors: int
    ) -> tuple[tuple[SourceWindow, ...], tuple[ExcludedWindow, ...]]:
        """Split the source's windows into a REALIZED family + exclusions (WS-2/WS-4).

        Walks the source walk-forward's windows in their sealed order. A REALIZED window
        contributes a REALIZED :class:`~quantforge.stability.compute.SourceWindow`
        carrying its weight vector parsed once to ``Decimal`` (WS-4); every UNDEFINED
        window becomes a first-class
        :class:`~quantforge.stability.result.ExcludedWindow` (``WINDOW_UNDEFINED``)
        *and* a non-realized :class:`~quantforge.stability.compute.SourceWindow` so the
        analyzer sees the gap in the weight path (never fabricating a turnover across
        it, WS-3).
        Order is the source order, so every metric maps straight back to its window
        ``index``. A REALIZED window whose weight vector is malformed (any non-KNOWN
        cell, or a length that disagrees with ``n_factors``) is a corrupt source and
        raises :class:`~quantforge.stability.errors.StabilityConsistencyError` (WS-4),
        never
        silently coerced.
        """
        source_windows: list[SourceWindow] = []
        excluded: list[ExcludedWindow] = []
        for window in windows:
            if window.status is not WindowStatus.REALIZED:
                excluded.append(
                    ExcludedWindow(
                        index=window.index,
                        reason=StabilityExcludedReason.WINDOW_UNDEFINED,
                    )
                )
                source_windows.append(
                    SourceWindow(index=window.index, realized=False, weights=())
                )
                continue
            weights = self._parse_weights(window, n_factors)
            source_windows.append(
                SourceWindow(index=window.index, realized=True, weights=weights)
            )
        return tuple(source_windows), tuple(excluded)

    def _parse_weights(
        self, window: WindowResult, n_factors: int
    ) -> tuple[Decimal, ...]:
        """Parse a REALIZED window's KNOWN weight vector to ``Decimal`` (WS-4).

        A REALIZED GMV window always sealed a full KNOWN weight vector of length
        ``n_factors`` in factor order. A vector of the wrong length, or any non-KNOWN
        cell, is a corrupt source: raise rather than coerce (fail closed, WS-4).
        """
        cells = window.weights
        if len(cells) != n_factors:
            raise StabilityConsistencyError(
                f"REALIZED window {window.index} sealed {len(cells)} weights but the "
                f"walk has {n_factors} factors; the source is inconsistent (fail "
                "closed)"
            )
        parsed: list[Decimal] = []
        for position, cell in enumerate(cells):
            if cell.status is not WalkStatStatus.KNOWN or cell.value is None:
                raise StabilityConsistencyError(
                    f"REALIZED window {window.index} has a non-KNOWN weight at "
                    f"position {position}; a realized GMV window must seal a full "
                    "KNOWN weight vector (fail closed)"
                )
            parsed.append(Decimal(cell.value))
        return tuple(parsed)
