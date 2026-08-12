"""The strategy-comparison orchestration engine (§6, §11, §12, SC-1..SC-8).

:class:`StrategyComparisonEngine` sits strictly **above** Phase 22: it is a pure
consumer that turns a declarative
:class:`~quantforge.comparison.spec.StrategyComparisonSpecification` into a sealed
:class:`~quantforge.comparison.result.StrategyComparison` by *resolving* the ordered set
of ``N`` already-sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation`
records a request names (the competing strategies), *verifying* each one, *enforcing*
that the strategies are commensurable (one shared rebalance schedule, one producing
factor-portfolio engine version, one annualization convention, and one per-period
risk-free rate, so their out-of-sample return series are drawn onto one comparable
footing), *reconstructing* each strategy's realized OOS return series by calendar date
(:mod:`quantforge.comparison.align`), *computing* the paired-difference statistics of
every upper-triangle ``(i < j)`` pair over the shared dates
(:mod:`quantforge.comparison.compute`), and sealing the answer. It introduces no new
data-resolution logic, no new PIT surface, and no new store; it composes the pinned pure
functions of :mod:`quantforge.comparison.align` / :mod:`quantforge.comparison.compute` /
:mod:`quantforge._stats.normal` and persists write-once to the shared research sidecar
(§6, §13, §16).

The build (§6):

1. **Resolve** each ``walk_forward_id`` from the shared sidecar via ``store.read_as(id,
   WalkForwardEvaluation.from_dict)``, in request order. A missing id (or a payload that
   does not decode as a ``WalkForwardEvaluation``) is a consistency defect and raises
   :class:`~quantforge.comparison.errors.ComparisonConsistencyError` (fail closed,
   SC-1).
2. **Verify** each strategy: its ``research_result_id`` equals the requested id and its
   roll-up ``status`` is ``REALIZED`` (a walk that sealed no defensible OOS series is
   not a comparison strategy). Each violation raises (SC-1).
3. **Enforce commensurability** (SC-2): every strategy shares one ``schedule_id``, one
   ``factor_portfolio_engine_version_id``, one ``periods_per_year``, and one
   ``risk_free_per_period`` - otherwise the reconstructed return series are not drawn
   onto one comparable footing and a paired-difference comparison is meaningless. A
   disagreement raises.
4. **Reconstruct** each strategy's ``(as_of -> OOS return)`` map by re-resolving its
   transitive factor chain and mapping its realized windows onto the recomputed
   complete-case date axis (:func:`~quantforge.comparison.align.reconstruct_strategy`),
   fail closed on any drift (SC-1).
5. **Compare** every upper-triangle ``(i < j)`` pair over the intersection of the two
   maps' calendar dates (:func:`~quantforge.comparison.compute.compare_pair`): the mean
   OOS-return difference, its standard error, the paired ``t`` statistic, the two-sided
   ``p`` value, and the descriptive Sharpe difference. A pair with too little overlap, a
   zero-variance paired difference, or an undefined leg Sharpe is a first-class
   UNDEFINED cell, never raised (SC-4).
6. **Seal + persist**: seal a
   :class:`~quantforge.comparison.result.StrategyComparison` (its ``result_hash`` folds
   the answer) and persist it write-once to the same sidecar. Rebuilding an identical
   request is a byte-identical no-op; a differing payload under the same id fails closed
   via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Context, Decimal

from quantforge.comparison.align import ReconstructedStrategy, reconstruct_strategy
from quantforge.comparison.compute import PairComputation, compare_pair
from quantforge.comparison.errors import (
    ComparisonConfigurationError,
    ComparisonConsistencyError,
)
from quantforge.comparison.model import (
    ComparisonStatus,
    ComparisonUndefinedReason,
    StatValue,
    strategy_label,
)
from quantforge.comparison.result import (
    BOUNDARY_PIT,
    ComparisonCell,
    Coverage,
    StrategyComparison,
    TrialSummary,
)
from quantforge.comparison.spec import StrategyComparisonSpecification
from quantforge.comparison.version import StrategyComparisonEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation
from quantforge.workspace import Workspace

__all__ = ["StrategyComparisonEngine"]


class StrategyComparisonEngine:
    """Resolve, verify, reconstruct, compare, and seal a comparison request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    walk-forward engine sealed its evaluations to - so a request compares exactly the
    strategies already present. The sidecar may be overridden (for tests). The engine
    pins its orchestration logic + statistical method + normal primitive + decimal
    context via :class:`StrategyComparisonEngineVersion`, and computes every value under
    that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: StrategyComparisonEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else StrategyComparisonEngineVersion()
        )

    @property
    def comparison_engine_version_id(self) -> str:
        """The orchestration + method + normal + decimal-context version, folded in."""
        return self._version.strategy_comparison_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the comparison resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def compare(self, spec: StrategyComparisonSpecification) -> StrategyComparison:
        """Resolve, verify, reconstruct, compare, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same strategies, recomputes byte-identical statistics under the
        pinned decimal context, and seals a byte-identical
        :class:`~quantforge.comparison.result.StrategyComparison` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on a missing / drifted
        reference, a non-``WalkForwardEvaluation`` record, a non-REALIZED strategy,
        incommensurable strategies, or a reconstruction that disagrees with a sealed
        record; a pair with too little overlap, a zero-variance paired difference, or an
        undefined leg Sharpe is recorded as a first-class UNDEFINED cell (SC-4), never
        raised.
        """
        if not isinstance(spec, StrategyComparisonSpecification):
            raise ComparisonConfigurationError(
                "compare() requires a StrategyComparisonSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify each strategy, in request order (SC-1) ----------
        strategies = [
            self._resolve_strategy(walk_forward_id, store)
            for walk_forward_id in spec.walk_forward_ids
        ]
        schedule_id, factor_engine_version_id = self._verify_commensurable(
            spec.walk_forward_ids, strategies
        )

        # -- reconstruct each strategy's (as_of -> OOS return) map (SC-1) -----
        reconstructed = [
            reconstruct_strategy(strategy, store) for strategy in strategies
        ]

        # -- per-strategy summary + upper-triangle pairwise matrix ------------
        trials = tuple(
            self._trial_summary(index, strategy, recon)
            for index, (strategy, recon) in enumerate(
                zip(strategies, reconstructed, strict=True)
            )
        )
        comparisons = self._compare_pairs(strategies, reconstructed, context)
        coverage = self._coverage(len(strategies), comparisons)

        # -- carried corpus pins + shared conventions -------------------------
        trial_refs = tuple(
            (strategy_label(index), strategy.research_result_id, strategy.result_hash)
            for index, strategy in enumerate(strategies)
        )
        dataset_version_ids = self._distinct(
            strategy.dataset_version_ids for strategy in strategies
        )
        market_dataset_version_ids = self._distinct(
            strategy.market_dataset_version_ids for strategy in strategies
        )

        # -- seal + persist ---------------------------------------------------
        comparison = StrategyComparison.seal(
            strategy_comparison_engine_version_id=(
                self._version.strategy_comparison_engine_version_id
            ),
            comparison_spec=spec.to_dict(),
            strategy_refs=trial_refs,
            boundary_kind=BOUNDARY_PIT,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_engine_version_id,
            periods_per_year=strategies[0].periods_per_year,
            risk_free_per_period=strategies[0].risk_free_per_period,
            trials=trials,
            comparisons=comparisons,
            coverage=coverage,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(comparison)
        return comparison

    # -- resolution & verification -------------------------------------------

    def _resolve_strategy(
        self, walk_forward_id: str, store: ResearchResultStore
    ) -> WalkForwardEvaluation:
        """Read + verify one referenced walk-forward strategy (fail closed, SC-1)."""
        try:
            result = store.read_as(walk_forward_id, WalkForwardEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise ComparisonConsistencyError(
                f"strategy {walk_forward_id!r} could not be decoded as a "
                "WalkForwardEvaluation; the referenced artifact is absent or not a "
                "walk-forward evaluation (fail closed)"
            ) from exc
        if result is None:
            raise ComparisonConsistencyError(
                f"strategy {walk_forward_id!r} is not present in the research sidecar; "
                "cannot compare a strategy that was never sealed (fail closed)"
            )
        if result.research_result_id != walk_forward_id:
            raise ComparisonConsistencyError(
                f"strategy {walk_forward_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        if result.status is not WindowStatus.REALIZED:
            raise ComparisonConsistencyError(
                f"strategy {walk_forward_id!r} has roll-up status "
                f"{result.status.value!r}, not REALIZED; it sealed no defensible "
                "out-of-sample series to compare (fail closed)"
            )
        return result

    def _verify_commensurable(
        self,
        walk_forward_ids: tuple[str, ...],
        strategies: list[WalkForwardEvaluation],
    ) -> tuple[str, str]:
        """The shared ``(schedule_id, factor_portfolio_engine_version_id)`` (SC-2).

        Every strategy must share one rebalance schedule, one producing factor-portfolio
        engine version, one annualization convention (``periods_per_year``), and one
        per-period risk-free rate (``risk_free_per_period``) - otherwise the
        reconstructed return series are not drawn onto one comparable footing (their
        calendar axes, the Sharpe annualization behind the descriptive Sharpe
        difference, and the excess basis would differ) and a paired-difference
        comparison would be meaningless. A disagreement is a consistency defect, raised
        rather than silently computed around.
        """
        first = strategies[0]
        schedule_id = first.schedule_id
        factor_engine_version_id = first.factor_portfolio_engine_version_id
        for walk_forward_id, strategy in zip(
            walk_forward_ids[1:], strategies[1:], strict=True
        ):
            if strategy.schedule_id != schedule_id:
                raise ComparisonConsistencyError(
                    f"strategy {walk_forward_id!r} uses rebalance schedule "
                    f"{strategy.schedule_id!r} but the first uses {schedule_id!r}; a "
                    "comparison requires one shared schedule so the strategies are "
                    "comparable (fail closed, SC-2)"
                )
            if strategy.factor_portfolio_engine_version_id != factor_engine_version_id:
                raise ComparisonConsistencyError(
                    f"strategy {walk_forward_id!r} was produced by factor-portfolio "
                    f"engine {strategy.factor_portfolio_engine_version_id!r} but the "
                    f"first by {factor_engine_version_id!r}; a comparison requires one "
                    "producing engine version so the strategies are comparable (fail "
                    "closed, SC-2)"
                )
            if strategy.periods_per_year != first.periods_per_year:
                raise ComparisonConsistencyError(
                    f"strategy {walk_forward_id!r} annualizes at "
                    f"{strategy.periods_per_year!r} periods/year but the first at "
                    f"{first.periods_per_year!r}; a comparison requires one "
                    "annualization convention so the Sharpe differences are comparable "
                    "(fail closed, SC-2)"
                )
            if strategy.risk_free_per_period != first.risk_free_per_period:
                raise ComparisonConsistencyError(
                    f"strategy {walk_forward_id!r} uses per-period risk-free rate "
                    f"{strategy.risk_free_per_period!r} but the first "
                    f"{first.risk_free_per_period!r}; a comparison requires one excess "
                    "basis so the strategies are comparable (fail closed, SC-2)"
                )
        return schedule_id, factor_engine_version_id

    # -- assembly -------------------------------------------------------------

    def _trial_summary(
        self,
        index: int,
        strategy: WalkForwardEvaluation,
        reconstructed: ReconstructedStrategy,
    ) -> TrialSummary:
        """Map one strategy into its sealed :class:`TrialSummary` block.

        The Sharpe is the strategy's **sealed** annualized OOS Sharpe passed through
        (KNOWN when the walk sealed a defined Sharpe, UNDEFINED
        ``UNDEFINED_STRATEGY_SHARPE`` when the walk's own Sharpe was undefined) - never
        recomputed here. ``n_valid_periods`` and ``axis_periods`` are carried as sealed
        / reconstructed counts.
        """
        sealed_sharpe = strategy.summary.annualized_sharpe.value
        if sealed_sharpe is None:
            sharpe = StatValue.undefined(
                ComparisonUndefinedReason.UNDEFINED_STRATEGY_SHARPE
            )
        else:
            sharpe = StatValue.known(sealed_sharpe)
        return TrialSummary(
            label=strategy_label(index),
            sharpe=sharpe,
            n_valid_periods=strategy.summary.n_valid_periods,
            axis_periods=reconstructed.axis_periods,
        )

    def _compare_pairs(
        self,
        strategies: list[WalkForwardEvaluation],
        reconstructed: list[ReconstructedStrategy],
        context: Context,
    ) -> tuple[ComparisonCell, ...]:
        """Compute + map the upper-triangle ``(i < j)`` pairwise cells (SC-4/SC-8).

        Iterates ``i`` then ``j > i`` in ascending order (a stable, deterministic pair
        order), passing each pair's reconstructed maps and sealed Sharpe strings to
        :func:`~quantforge.comparison.compute.compare_pair` and mapping the resulting
        :class:`~quantforge.comparison.compute.PairComputation` into a sealed
        :class:`~quantforge.comparison.result.ComparisonCell`.
        """
        sharpes = [strategy.summary.annualized_sharpe.value for strategy in strategies]
        cells: list[ComparisonCell] = []
        n = len(strategies)
        for i in range(n):
            for j in range(i + 1, n):
                computation = compare_pair(
                    i,
                    j,
                    reconstructed[i].returns,
                    reconstructed[j].returns,
                    sharpes[i],
                    sharpes[j],
                    context=context,
                )
                cells.append(self._comparison_cell(computation))
        return tuple(cells)

    def _comparison_cell(self, computation: PairComputation) -> ComparisonCell:
        """Map a computed pair into its sealed :class:`ComparisonCell` (SC-4).

        An UNDEFINED pair (too little overlap) emits every statistic as an UNDEFINED
        cell carrying the pair reason; a KNOWN pair emits KNOWN ``mean_diff`` /
        ``stderr_diff`` and maps ``t_stat`` / ``p_value`` (KNOWN, or UNDEFINED
        ``ZERO_DIFFERENCE_VARIANCE``) and ``sharpe_diff`` (KNOWN, or UNDEFINED
        ``UNDEFINED_STRATEGY_SHARPE``) through their per-cell reasons.
        """
        label_i = strategy_label(computation.i)
        label_j = strategy_label(computation.j)
        if computation.status is ComparisonStatus.UNDEFINED:
            assert computation.reason is not None  # UNDEFINED ⇒ pair reason present
            cell = StatValue.undefined(computation.reason)
            return ComparisonCell(
                i=computation.i,
                j=computation.j,
                label_i=label_i,
                label_j=label_j,
                status=ComparisonStatus.UNDEFINED,
                overlap_periods=computation.overlap,
                mean_diff=cell,
                stderr_diff=cell,
                t_stat=cell,
                p_value=cell,
                sharpe_diff=cell,
                reason=computation.reason,
            )
        assert computation.mean_diff is not None  # KNOWN pair ⇒ mean/stderr present
        assert computation.stderr_diff is not None
        return ComparisonCell(
            i=computation.i,
            j=computation.j,
            label_i=label_i,
            label_j=label_j,
            status=ComparisonStatus.KNOWN,
            overlap_periods=computation.overlap,
            mean_diff=self._known(computation.mean_diff),
            stderr_diff=self._known(computation.stderr_diff),
            t_stat=self._cell(computation.t_stat, computation.t_reason),
            p_value=self._cell(computation.p_value, computation.t_reason),
            sharpe_diff=self._cell(computation.sharpe_diff, computation.sharpe_reason),
            reason=None,
        )

    def _coverage(
        self, n_strategies: int, comparisons: tuple[ComparisonCell, ...]
    ) -> Coverage:
        """The audit coverage block - a pure function of the sealed cells (§9)."""
        defined = sum(
            1 for cell in comparisons if cell.status is ComparisonStatus.KNOWN
        )
        return Coverage(
            n_strategies=n_strategies,
            n_pairs=len(comparisons),
            n_defined_pairs=defined,
            n_undefined_pairs=len(comparisons) - defined,
        )

    # -- cell helpers ---------------------------------------------------------

    def _known(self, value: Decimal) -> StatValue:
        """A KNOWN cell holding the canonical decimal string of ``value``.

        The value already carries the pinned context's precision from
        :func:`~quantforge.comparison.compute.compare_pair` (computed under
        ``localcontext``); ``str(value)`` re-emits its canonical form without
        re-rounding.
        """
        return StatValue.known(str(value))

    def _cell(
        self,
        value: Decimal | None,
        reason: ComparisonUndefinedReason | None,
    ) -> StatValue:
        """A KNOWN cell for a value, or an UNDEFINED cell carrying ``reason``."""
        if value is not None:
            return self._known(value)
        assert reason is not None  # value is None ⇒ a reason was recorded
        return StatValue.undefined(reason)

    def _distinct(self, groups: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
        """The sorted distinct union of several string tuples (deterministic).

        Strategies may legitimately have been run over different corpus snapshots; the
        record carries the sorted distinct union of their pins so a reader can detect
        (via :attr:`~quantforge.comparison.result.StrategyComparison.pin_mismatch`) that
        the references were not pinned identically. Sorted for a stable,
        order-independent serialization.
        """
        seen: set[str] = set()
        for group in groups:
            seen.update(group)
        return tuple(sorted(seen))
