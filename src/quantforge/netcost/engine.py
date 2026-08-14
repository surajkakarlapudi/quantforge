"""The net-of-cost orchestration engine (§6, §11, §12, NC-1..NC-6).

:class:`NetOfCostEngine` sits strictly **above** Phase 27: it is a pure consumer that
turns a declarative :class:`~quantforge.netcost.spec.NetOfCostSpecification` into a
sealed :class:`~quantforge.netcost.result.NetOfCostPerformance` by *resolving* the one
already-sealed :class:`~quantforge.stability.result.WalkForwardStability` the request
names, *resolving + verifying* the one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability record pins
(so the gross return series is consumed from an artifact whose ``result_hash`` the
stability record already committed to - NC-1), *aligning* the per-window turnover to the
per-period gross returns (the load-bearing decision - the two are **not** zippable),
*reading the sealed gross summary verbatim* (NC-4), *charging* the declared linear cost,
*summarizing* the net series with the reused Phase 19 method, and sealing the answer. It
introduces no new data resolution, no new PIT surface, and no new store; it composes the
pinned pure accounting under the version's decimal context and persists write-once to
the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_stability_id`` from the shared sidecar via
   ``store.read_as(id, WalkForwardStability.from_dict)``. A missing id (or a payload
   that does not decode as a ``WalkForwardStability``) is a consistency defect and
   raises :class:`~quantforge.netcost.errors.NetOfCostConsistencyError` (fail closed,
   NC-1), and the resolved record's ``research_result_id`` must equal the request
   (NC-1).
2. **Resolve + verify the pinned walk-forward transitively** (NC-1): read the
   ``WalkForwardEvaluation`` the stability record pins by
   ``source_ref = (walk_forward_id, walk_forward_result_hash)``, and verify **both** its
   ``research_result_id`` equals that id **and** its ``result_hash`` equals the pinned
   hash - so the gross returns come from exactly the artifact the stability record
   committed to, never a drifted one.
3. **Align** the per-window one-way turnover (Phase 27, per REALIZED window) to the
   per-period chained gross returns (Phase 22): verify the stability record's realized
   window indices equal the walk's REALIZED window indices (in order) and its excluded
   indices equal the walk's UNDEFINED window indices (in order), and verify the
   concatenation of the walk's per-realized-window ``oos_returns`` reproduces the
   walk's chained ``oos_returns`` exactly - so the per-window gross slices are provably
   the same
   numbers as the sealed chained series. Any mismatch fails closed (NC-1).
4. **Read the gross summary verbatim** (NC-4): carry the walk's KNOWN (or UNDEFINED)
   ``mean_period_return`` / ``volatility`` / ``annualized_sharpe`` across as the gross
   moments, never recomputed - so at ``cost_rate == 0`` the net moments equal the gross
   moments exactly (the zero-cost identity).
5. **Compute** the net-of-cost accounting
   (:func:`~quantforge.netcost.compute.compute_net_of_cost`) under the version's decimal
   context: the declared ``cost_rate · turnover_w`` charged at each realized window's
   first OOS period, the net series summarized with the reused Phase 19 method, the cost
   drag, and the parameter-free break-even ``Σ gross / Σ turnover`` (UNDEFINED
   ``DEGENERATE_NO_TURNOVER`` when the strategy never trades, NC-5), never a
   divide-by-zero.
6. **Seal + persist**: seal a
   :class:`~quantforge.netcost.result.NetOfCostPerformance` (its ``result_hash`` folds
   the answer, its id transitively pins the stability record's ``result_hash`` and the
   declared ``cost_rate``) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.factors.store import ResearchResultStore
from quantforge.netcost.compute import (
    RealizedWindowInput,
    compute_net_of_cost,
)
from quantforge.netcost.errors import (
    NetOfCostConfigurationError,
    NetOfCostConsistencyError,
)
from quantforge.netcost.model import (
    NetCostExcludedReason,
    NetCostStat,
    NetCostUndefinedReason,
)
from quantforge.netcost.result import (
    ExcludedWindow,
    NetOfCostCoverage,
    NetOfCostPerformance,
    NetOfCostSummary,
    WindowNetCostCell,
)
from quantforge.netcost.spec import NetOfCostSpecification
from quantforge.netcost.version import NetOfCostEngineVersion
from quantforge.stability.model import StabilityStat
from quantforge.stability.model import StatStatus as StabilityStatStatus
from quantforge.stability.result import WalkForwardStability
from quantforge.walkforward.model import StatStatus as WalkForwardStatStatus
from quantforge.walkforward.model import StatValue as WalkForwardStatValue
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation
from quantforge.workspace import Workspace

__all__ = ["NetOfCostEngine"]


class NetOfCostEngine:
    """Resolve, verify, align, charge, and seal a net-of-cost request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    stability engine sealed its stability records to (and, transitively, the
    walk-forward engine its walks) - so a request evaluates exactly the records already
    present. The sidecar may be overridden (for tests). The engine pins its
    orchestration logic + cost-accounting method + reused-summary method + decimal
    context via :class:`~quantforge.netcost.version.NetOfCostEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: NetOfCostEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else NetOfCostEngineVersion()

    @property
    def net_of_cost_engine_version_id(self) -> str:
        """The orchestration + method + reused-summary + decimal-context version, folded
        into every id."""
        return self._version.net_of_cost_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the net-of-cost resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(self, spec: NetOfCostSpecification) -> NetOfCostPerformance:
        """Resolve, verify, align, charge, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same stability record and its pinned walk, recomputes
        byte-identical statistics under the pinned decimal context, and seals a
        byte-identical :class:`~quantforge.netcost.result.NetOfCostPerformance` on any
        machine (whose sidecar write is an idempotent no-op). Fails closed on a missing
        / drifted reference, a non-matching record type, or any window/gross-series
        misalignment (NC-1); a strategy that never trades seals a break-even that is
        UNDEFINED ``DEGENERATE_NO_TURNOVER`` (NC-5), never raised; a net series with
        zero dispersion seals the net Sharpe UNDEFINED ``ZERO_RETURN_VARIANCE`` (NC-5).
        """
        if not isinstance(spec, NetOfCostSpecification):
            raise NetOfCostConfigurationError(
                "evaluate() requires a NetOfCostSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve the source stability record + its pinned walk (NC-1) -----
        stability = self._resolve_stability(spec.source_stability_id, store)
        walk = self._resolve_walk_forward(stability, store)

        # -- align turnover (per window) to gross returns (per period) (NC-1) -
        realized, excluded_cells = self._align(stability, walk)

        # -- read the gross summary verbatim (NC-4) ---------------------------
        gross_mean = self._gross_cell(walk.summary.mean_period_return)
        gross_volatility = self._gross_cell(walk.summary.volatility)
        gross_sharpe = self._gross_cell(walk.summary.annualized_sharpe)

        # -- compute the net-of-cost accounting (NC-2/NC-3/NC-5) --------------
        computation = compute_net_of_cost(
            realized,
            gross_mean=gross_mean,
            gross_volatility=gross_volatility,
            gross_sharpe=gross_sharpe,
            cost_rate=Decimal(spec.cost_rate),
            risk_free_per_period=walk.risk_free_per_period,
            periods_per_year=walk.periods_per_year,
            context=context,
        )

        window_cells = tuple(
            WindowNetCostCell(
                index=cell.index,
                n_periods=cell.n_periods,
                gross_return=cell.gross_return,
                turnover=cell.turnover,
                cost=cell.cost,
                net_return=cell.net_return,
            )
            for cell in computation.windows
        )
        summary = NetOfCostSummary(
            gross_mean=computation.gross_mean,
            gross_volatility=computation.gross_volatility,
            gross_sharpe=computation.gross_sharpe,
            net_mean=computation.net_mean,
            net_volatility=computation.net_volatility,
            net_sharpe=computation.net_sharpe,
            cost_drag_mean=computation.cost_drag_mean,
            sharpe_drag=computation.sharpe_drag,
            break_even_cost_rate=computation.break_even_cost_rate,
            total_gross_return=computation.total_gross_return,
            total_turnover=computation.total_turnover,
            total_cost=computation.total_cost,
            net_status=computation.net_status,
            status_reason=computation.status_reason,
        )
        coverage = NetOfCostCoverage(
            n_windows=stability.coverage.n_windows,
            n_realized=len(window_cells),
            n_excluded=len(excluded_cells),
            n_charged=computation.n_charged,
            n_periods=computation.n_periods,
        )

        # -- seal + persist ---------------------------------------------------
        performance = NetOfCostPerformance.seal(
            net_of_cost_engine_version_id=self._version.net_of_cost_engine_version_id,
            net_of_cost_spec=spec.to_dict(),
            source_ref=(stability.research_result_id, stability.result_hash),
            # Carry the source stability record's boundary through unchanged: it
            # documents that the underlying factor portfolios were PIT walks. The
            # net-of-cost output is ex-post and counterfactual and is not a PIT value
            # (NC-6).
            boundary_kind=stability.boundary_kind,
            periods_per_year=walk.periods_per_year,
            risk_free_per_period=walk.risk_free_per_period,
            windows=window_cells,
            excluded=excluded_cells,
            summary=summary,
            coverage=coverage,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(performance)
        return performance

    # -- resolution & verification -------------------------------------------

    def _resolve_stability(
        self, source_id: str, store: ResearchResultStore
    ) -> WalkForwardStability:
        """Read + verify the one referenced source stability record (fail closed,
        NC-1)."""
        try:
            result = store.read_as(source_id, WalkForwardStability.from_dict)
        except (KeyError, ValueError) as exc:
            raise NetOfCostConsistencyError(
                f"source stability record {source_id!r} could not be decoded as a "
                "WalkForwardStability; the referenced artifact is absent or not a "
                "walk-forward-stability record (fail closed)"
            ) from exc
        if result is None:
            raise NetOfCostConsistencyError(
                f"source stability record {source_id!r} is not present in the research "
                "sidecar; cannot charge a strategy that was never sealed (fail closed)"
            )
        if result.research_result_id != source_id:
            raise NetOfCostConsistencyError(
                f"source stability record {source_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    def _resolve_walk_forward(
        self, stability: WalkForwardStability, store: ResearchResultStore
    ) -> WalkForwardEvaluation:
        """Read + verify the walk the stability record pins, transitively (NC-1).

        Resolves the ``WalkForwardEvaluation`` by the stability record's pinned
        ``source_walk_forward_id`` and verifies **both** its ``research_result_id`` and
        its ``result_hash`` equal the values the stability record committed to - so the
        gross return series is provably read from the exact artifact the stability
        record was built over, never a drifted one. Any disagreement fails closed.
        """
        walk_id = stability.source_walk_forward_id
        expected_hash = stability.source_result_hash
        try:
            walk = store.read_as(walk_id, WalkForwardEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise NetOfCostConsistencyError(
                f"pinned walk-forward {walk_id!r} could not be decoded as a "
                "WalkForwardEvaluation; the transitively-referenced artifact is absent "
                "or not a walk-forward evaluation (fail closed)"
            ) from exc
        if walk is None:
            raise NetOfCostConsistencyError(
                f"pinned walk-forward {walk_id!r} is not present in the research "
                "sidecar; the stability record references a walk that was never sealed "
                "(fail closed)"
            )
        if walk.research_result_id != walk_id:
            raise NetOfCostConsistencyError(
                f"pinned walk-forward {walk_id!r} resolved to a record whose id "
                f"{walk.research_result_id!r} disagrees with the stability record's "
                "reference; the sidecar is inconsistent (fail closed)"
            )
        if walk.result_hash != expected_hash:
            raise NetOfCostConsistencyError(
                f"pinned walk-forward {walk_id!r} has result_hash {walk.result_hash!r} "
                f"but the stability record pinned {expected_hash!r}; the walk has "
                "drifted from the sealed reference (fail closed)"
            )
        return walk

    # -- alignment ------------------------------------------------------------

    def _align(
        self, stability: WalkForwardStability, walk: WalkForwardEvaluation
    ) -> tuple[tuple[RealizedWindowInput, ...], tuple[ExcludedWindow, ...]]:
        """Align per-window turnover to per-period gross returns (fail closed, NC-1).

        The load-bearing join. Verifies the stability record's realized window indices
        equal the walk's REALIZED window indices (in order) and its excluded indices
        equal the walk's UNDEFINED window indices (in order); verifies the
        concatenation of the walk's per-realized-window ``oos_returns`` reproduces the
        walk's chained ``oos_returns`` exactly (so the per-window gross slices are
        provably the same numbers as the sealed chained series). Then pairs each
        stability window cell with its walk window to build the per-window inputs (the
        KNOWN one-way turnover parsed to a ``Decimal``, or ``None`` when the source
        sealed it UNDEFINED ``NO_PRIOR_REALIZED_WINDOW`` - no adjacent book to trade
        from). Any mismatch is a structural inconsistency and raises.
        """
        realized_windows = tuple(
            w for w in walk.windows if w.status is WindowStatus.REALIZED
        )
        undefined_windows = tuple(
            w for w in walk.windows if w.status is WindowStatus.UNDEFINED
        )

        stability_indices = [cell.index for cell in stability.windows]
        realized_indices = [w.index for w in realized_windows]
        if stability_indices != realized_indices:
            raise NetOfCostConsistencyError(
                "the stability record's realized window indices "
                f"{stability_indices!r} do not match the walk's REALIZED window "
                f"indices {realized_indices!r}; the records are misaligned (fail "
                "closed)"
            )

        excluded_indices = [gap.index for gap in stability.excluded]
        walk_undefined_indices = [w.index for w in undefined_windows]
        if excluded_indices != walk_undefined_indices:
            raise NetOfCostConsistencyError(
                "the stability record's excluded window indices "
                f"{excluded_indices!r} do not match the walk's UNDEFINED window "
                f"indices {walk_undefined_indices!r}; the records are misaligned (fail "
                "closed)"
            )

        # Verify the per-window gross slices reproduce the sealed chained series
        # exactly.
        reconstructed: list[str] = []
        for window in realized_windows:
            reconstructed.extend(window.oos_returns)
        if tuple(reconstructed) != walk.oos_returns:
            raise NetOfCostConsistencyError(
                "the concatenation of the walk's per-window OOS returns does not "
                "reproduce its chained OOS return series; the walk is internally "
                "inconsistent (fail closed)"
            )

        inputs = tuple(
            RealizedWindowInput(
                index=cell.index,
                oos_returns=window.oos_returns,
                turnover=self._turnover(cell.turnover_from_prev, cell.index),
            )
            for cell, window in zip(stability.windows, realized_windows, strict=True)
        )
        excluded_cells = tuple(
            ExcludedWindow(
                index=gap.index,
                reason=self._excluded_reason(gap.reason.value, gap.index),
            )
            for gap in stability.excluded
        )
        return inputs, excluded_cells

    # -- verbatim gross-cell mapping ------------------------------------------

    def _gross_cell(self, cell: WalkForwardStatValue) -> NetCostStat:
        """Carry a sealed walk-forward gross summary cell across verbatim (NC-4).

        A KNOWN cell carries its canonical decimal string across unchanged (never
        recomputed - so at ``cost_rate == 0`` the net moment equals the gross moment
        exactly); an UNDEFINED cell carries its reason across by value. A gross moment
        can only be UNDEFINED for one of the three reused-summary reasons
        (``no_valid_periods`` / ``single_valid_period`` / ``zero_return_variance``), all
        shared verbatim with :class:`~quantforge.netcost.model.NetCostUndefinedReason`;
        any other reason on an aggregate summary cell is a corrupt source and fails
        closed.
        """
        if cell.status is WalkForwardStatStatus.KNOWN:
            assert cell.value is not None  # guaranteed by StatValue.__post_init__
            return NetCostStat.known(cell.value)
        assert cell.reason is not None  # guaranteed by StatValue.__post_init__
        try:
            return NetCostStat.undefined(NetCostUndefinedReason(cell.reason.value))
        except ValueError as exc:
            raise NetOfCostConsistencyError(
                f"gross summary cell is UNDEFINED for reason {cell.reason.value!r}, "
                "which is not a net-of-cost summary reason; the source walk is "
                "inconsistent (fail closed)"
            ) from exc

    def _turnover(self, cell: StabilityStat, index: int) -> Decimal | None:
        """Parse a stability window's ``turnover_from_prev`` cell to a ``Decimal`` /
        None.

        A KNOWN cell yields its one-way turnover parsed once to a ``Decimal``; an
        UNDEFINED ``NO_PRIOR_REALIZED_WINDOW`` cell (no adjacent realized predecessor)
        yields ``None`` (no trade to charge). Per-window turnover has a closed
        vocabulary of exactly those two states; any other UNDEFINED reason on a
        per-window turnover cell is a corrupt source and fails closed - never silently
        treated as zero cost.
        """
        if cell.status is StabilityStatStatus.KNOWN:
            assert cell.value is not None  # guaranteed by StabilityStat.__post_init__
            return Decimal(cell.value)
        reason = cell.reason
        no_prior = NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW.value
        if reason is None or reason.value != no_prior:
            reason_repr = None if reason is None else reason.value
            raise NetOfCostConsistencyError(
                f"realized window {index} has an UNDEFINED turnover for reason "
                f"{reason_repr!r}, which is not a per-window turnover reason; the "
                "stability record is inconsistent (fail closed)"
            )
        return None

    def _excluded_reason(self, reason_value: str, index: int) -> NetCostExcludedReason:
        """Carry a stability exclusion reason across to the net-of-cost vocabulary
        (NC-5).

        The one stability exclusion reason (``window_undefined``) is shared verbatim
        with :class:`~quantforge.netcost.model.NetCostExcludedReason`; any other value
        is a corrupt source and fails closed rather than being relabelled.
        """
        try:
            return NetCostExcludedReason(reason_value)
        except ValueError as exc:
            raise NetOfCostConsistencyError(
                f"excluded window {index} has reason {reason_value!r}, which is not a "
                "net-of-cost exclusion reason; the stability record is inconsistent "
                "(fail closed)"
            ) from exc
