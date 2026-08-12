"""The walk-forward-evaluation orchestration engine (§6, §12, WF-1..WF-6).

:class:`WalkForwardEvaluationEngine` sits strictly **above** Phase 21: it is a pure
consumer that turns a declarative
:class:`~quantforge.walkforward.spec.WalkForwardEvaluationSpecification` into a sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` by *resolving* the one
already-sealed :class:`~quantforge.optimization.result.PortfolioOptimization` recipe a
request names, *verifying* it (and, through it, the referenced
:class:`~quantforge.factorrisk.result.FactorRiskModel` and its
:class:`~quantforge.factorportfolio.result.FactorPortfolio` factors), *aligning* the
factors' KNOWN ``(as_of, factor_return)`` series on a common complete-case time axis,
*partitioning* that axis into ordered train->test windows, *re-estimating* the
covariance (Phase 20 method) and *re-solving* the GMV weights (Phase 21 method) on each
training span, *realizing* those weights against the strictly-subsequent test returns
(WF-2, no look-ahead), *chaining* the out-of-sample (OOS) returns, *summarizing* them
(Phase 19 method), and sealing the answer. It introduces no new data-resolution logic,
no new PIT surface, and no new store; it composes three pinned pure functions from the
layers below and persists write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``optimization_id`` from the shared sidecar via ``store.read_as(id,
   PortfolioOptimization.from_dict)``. A missing id (or a payload that does not decode
   as a ``PortfolioOptimization``) is a consistency defect and raises
   :class:`~quantforge.walkforward.errors.WalkForwardConsistencyError` (fail closed).
2. **Verify the recipe** (WF-1/WF-5): its ``research_result_id`` equals the requested
   id; its ``status`` is ``OPTIMAL`` (a singular in-sample recipe is not walkable); its
   objective is ``minimum_variance`` and its constraint is exactly the v1
   ``{"fully_invested": true}``. Each violation raises.
3. **Resolve + verify the risk model** the recipe references (its ``factor_risk_id``),
   checking its ``result_hash`` matches the recipe's pinned pointer (WF-1, transitive),
   then **resolve each factor** it references, verifying ids and inheriting one shared
   ``risk_free_per_period`` (a disagreement raises).
4. **Align** (complete-case, WF-6): the common axis is the intersection of the ``as_of``
   instants where **every** factor carries a KNOWN return, ascending; the aligned matrix
   is those dates' returns in shared order (the Phase 20 alignment idiom, reused).
5. **Partition + evaluate**: derive the ordered train->test windows from the aligned
   axis + the :class:`~quantforge.walkforward.spec.TrainingPolicy`; per window
   re-estimate, re-solve, and realize the OOS returns (WF-2). A non-positive-definite
   training covariance is a first-class UNDEFINED ``SINGULAR_TRAINING_COVARIANCE``
   window, never raised (WF-4). Fewer than
   :data:`~quantforge.walkforward.result.MIN_VALID_WINDOWS` REALIZED windows (or a
   common axis too short to form them) is a consistency defect and raises - no
   defensible OOS summary exists (WF-4).
6. **Summarize + seal**: chain the OOS returns, summarize them (Phase 19 method) and
   compute the aggregate realized OOS variance, then seal a
   :class:`~quantforge.walkforward.result.WalkForwardEvaluation` (its ``result_hash``
   folds the answer) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Context, Decimal, localcontext

from quantforge.factorportfolio.model import (
    FactorPortfolioStatus,
)
from quantforge.factorportfolio.model import (
    StatValue as FactorPortfolioStatValue,
)
from quantforge.factorportfolio.result import FactorPortfolio
from quantforge.factorportfolio.stats import SeriesSummary, series_summary
from quantforge.factorrisk.result import FactorRiskModel
from quantforge.factorrisk.spec import N_MAX
from quantforge.factors.store import ResearchResultStore
from quantforge.optimization.model import OptimizationStatus
from quantforge.optimization.result import PortfolioOptimization
from quantforge.optimization.spec import OBJECTIVE_MINIMUM_VARIANCE
from quantforge.walkforward.errors import (
    WalkForwardConfigurationError,
    WalkForwardConsistencyError,
)
from quantforge.walkforward.evaluate import evaluate_window
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    factor_label,
)
from quantforge.walkforward.result import (
    BOUNDARY_PIT,
    MIN_VALID_WINDOWS,
    WalkForwardEvaluation,
    WindowResult,
)
from quantforge.walkforward.spec import WalkForwardEvaluationSpecification
from quantforge.walkforward.version import WalkForwardEngineVersion
from quantforge.walkforward.windows import build_windows
from quantforge.workspace import Workspace

__all__ = ["WalkForwardEvaluationEngine"]

_ZERO = Decimal(0)

#: The minimum number of factors the walk accepts - the same lower bound Phase 20/21
#: enforce. Re-checked here fail-closed (WF-1).
_MIN_FACTORS = 2


class WalkForwardEvaluationEngine:
    """Resolve, verify, align, partition, evaluate, summarize, and seal a request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    optimization / factor-risk / factor-portfolio engines sealed their artifacts to - so
    a request walks exactly the optimization already present. The sidecar may be
    overridden (for tests). The engine pins its orchestration logic + composed methods +
    decimal context via :class:`WalkForwardEngineVersion`, and computes every value
    under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: WalkForwardEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else WalkForwardEngineVersion()

    @property
    def walk_forward_engine_version_id(self) -> str:
        """The orchestration + composed-method + decimal-context version, folded in."""
        return self._version.walk_forward_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the evaluation resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(
        self, spec: WalkForwardEvaluationSpecification
    ) -> WalkForwardEvaluation:
        """Resolve, verify, align, partition, evaluate, summarize, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same optimization, rebuilds the same aligned axis and windows,
        recomputes byte-identical statistics under the pinned decimal context, and seals
        a byte-identical :class:`~quantforge.walkforward.result.WalkForwardEvaluation`
        on any machine (whose sidecar write is an idempotent no-op). Fails closed on a
        missing / drifted reference, a non-OPTIMAL or non-GMV recipe, incommensurable
        factors, a disagreeing inherited risk-free convention, or too few valid windows;
        a non-positive-definite training covariance is recorded as a first-class
        UNDEFINED ``SINGULAR_TRAINING_COVARIANCE`` window (WF-4), never raised.
        """
        if not isinstance(spec, WalkForwardEvaluationSpecification):
            raise WalkForwardConfigurationError(
                "evaluate() requires a WalkForwardEvaluationSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the optimization recipe (WF-1/WF-5) -------------
        optimization = self._resolve_optimization(spec.optimization_id, store)
        self._verify_recipe(optimization)

        # -- resolve + verify the risk model and its factors (WF-1/WF-6) ------
        model = self._resolve_risk_model(optimization, store)
        factor_ids = model.factor_portfolio_ids
        n = len(factor_ids)
        if not (_MIN_FACTORS <= n <= N_MAX):
            raise WalkForwardConsistencyError(
                f"the referenced risk model declares {n} factor(s), outside the "
                f"supported range {_MIN_FACTORS}..{N_MAX} (fail closed)"
            )
        factors = [self._resolve_factor(factor_id, store) for factor_id in factor_ids]
        risk_free_per_period = self._inherit_risk_free(factors)

        # -- complete-case alignment on the common KNOWN date axis (WF-6) -----
        known_by_factor = [self._known_returns(factor) for factor in factors]
        common_dates = self._common_dates(known_by_factor)
        m = len(common_dates)
        series = [[known[as_of] for as_of in common_dates] for known in known_by_factor]

        # -- partition into ordered train->test windows (§12, WF-2) -----------
        window_specs = build_windows(m, spec.training_policy)
        if len(window_specs) < MIN_VALID_WINDOWS:
            raise WalkForwardConsistencyError(
                f"the referenced factors share only {m} complete-case period(s), "
                f"which forms {len(window_specs)} train->test window(s) under the "
                f"training policy, fewer than the {MIN_VALID_WINDOWS} required; fail "
                "closed rather than seal a degenerate walk (WF-4)"
            )

        # -- evaluate each window (compose Phase 20 + Phase 21; WF-2/WF-4) ----
        evaluations = [
            evaluate_window(
                series,
                window,
                n=n,
                periods_per_year=model.periods_per_year,
                context=context,
            )
            for window in window_specs
        ]
        windows = tuple(
            WindowResult(
                index=ev.window.index,
                train_start=ev.window.train_start,
                train_end=ev.window.train_end,
                test_start=ev.window.test_start,
                test_end=ev.window.test_end,
                status=ev.status,
                reason=ev.reason,
                weights=ev.weights,
                predicted_variance=ev.predicted_variance,
                realized_variance=ev.realized_variance,
                oos_returns=ev.oos_returns,
            )
            for ev in evaluations
        )
        realized_count = sum(1 for ev in evaluations if ev.oos_returns)
        if realized_count < MIN_VALID_WINDOWS:
            raise WalkForwardConsistencyError(
                f"only {realized_count} of {len(windows)} window(s) realized OOS "
                f"returns (the rest had a non-positive-definite training covariance), "
                f"fewer than the {MIN_VALID_WINDOWS} required for a defensible OOS "
                "summary; fail closed (WF-4)"
            )

        # -- chain the OOS returns, summarize (Phase 19 method), aggregate ----
        chained: list[str] = []
        for ev in evaluations:
            chained.extend(ev.oos_returns)
        summary = self._summarize(
            chained,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=model.periods_per_year,
            context=context,
        )
        realized_variance = self._aggregate_realized_variance(chained, context)

        # -- seal + persist ---------------------------------------------------
        labels = tuple(factor_label(i) for i in range(n))
        evaluation = WalkForwardEvaluation.seal(
            walk_forward_engine_version_id=(
                self._version.walk_forward_engine_version_id
            ),
            walk_forward_spec=spec.to_dict(),
            optimization_ref=(
                optimization.research_result_id,
                optimization.result_hash,
            ),
            boundary_kind=BOUNDARY_PIT,
            schedule_id=model.schedule_id,
            factor_portfolio_engine_version_id=(
                model.factor_portfolio_engine_version_id
            ),
            n_factors=n,
            factor_labels=labels,
            periods_per_year=model.periods_per_year,
            risk_free_per_period=risk_free_per_period,
            common_periods=m,
            windows=windows,
            oos_returns=tuple(chained),
            summary=summary,
            realized_variance=realized_variance,
            dataset_version_ids=model.dataset_version_ids,
            market_dataset_version_ids=model.market_dataset_version_ids,
            formula_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(evaluation)
        return evaluation

    # -- resolution & verification -------------------------------------------

    def _resolve_optimization(
        self, optimization_id: str, store: ResearchResultStore
    ) -> PortfolioOptimization:
        """Read + verify the referenced optimization recipe (fail closed, WF-1)."""
        try:
            result = store.read_as(optimization_id, PortfolioOptimization.from_dict)
        except (KeyError, ValueError) as exc:
            raise WalkForwardConsistencyError(
                f"optimization {optimization_id!r} could not be decoded as a "
                "PortfolioOptimization; the referenced artifact is absent or not an "
                "optimization (fail closed)"
            ) from exc
        if result is None:
            raise WalkForwardConsistencyError(
                f"optimization {optimization_id!r} is not present in the research "
                "sidecar; cannot walk a recipe that was never sealed (fail closed)"
            )
        if result.research_result_id != optimization_id:
            raise WalkForwardConsistencyError(
                f"optimization {optimization_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    def _verify_recipe(self, optimization: PortfolioOptimization) -> None:
        """Enforce walkable-recipe contract: OPTIMAL, GMV, fully-invested (WF-1/WF-5).

        A non-OPTIMAL recipe has no weight vector to walk (its in-sample covariance was
        singular); a non-``minimum_variance`` objective or a constraint other than the
        v1 ``{"fully_invested": true}`` is outside the scope Phase 22 can walk
        PIT-honestly. Each is a consistency defect and raises rather than being silently
        reinterpreted.
        """
        if optimization.status is not OptimizationStatus.OPTIMAL:
            raise WalkForwardConsistencyError(
                f"optimization {optimization.research_result_id!r} has status "
                f"{optimization.status.value!r}, not OPTIMAL; its in-sample covariance "
                "was singular, so there is no GMV recipe to walk (fail closed, WF-1)"
            )
        if optimization.objective != OBJECTIVE_MINIMUM_VARIANCE:
            raise WalkForwardConsistencyError(
                f"optimization {optimization.research_result_id!r} has objective "
                f"{optimization.objective!r}, not {OBJECTIVE_MINIMUM_VARIANCE!r}; "
                "the v1 walk supports only the GMV recipe (fail closed, WF-5)"
            )
        if optimization.constraint_spec != {"fully_invested": True}:
            raise WalkForwardConsistencyError(
                f"optimization {optimization.research_result_id!r} carries constraint "
                f"{optimization.constraint_spec!r}, not the v1 fully-invested GMV "
                "constraint {'fully_invested': True}; fail closed (WF-5)"
            )

    def _resolve_risk_model(
        self, optimization: PortfolioOptimization, store: ResearchResultStore
    ) -> FactorRiskModel:
        """Resolve + verify the risk model the recipe references (fail closed, WF-1).

        Checks the id is present, decodes as a
        :class:`~quantforge.factorrisk.result.FactorRiskModel`, its
        ``research_result_id`` equals the recipe's referenced id, and its sealed
        ``result_hash`` equals the recipe's pinned pointer - so the walk is transitively
        bound to the exact risk model the recipe optimized (and, through it, the factors
        and corpus). Any drift raises.
        """
        risk_id, risk_hash = optimization.risk_model_ref
        try:
            model = store.read_as(risk_id, FactorRiskModel.from_dict)
        except (KeyError, ValueError) as exc:
            raise WalkForwardConsistencyError(
                f"risk model {risk_id!r} (referenced by the optimization) could not be "
                "decoded as a FactorRiskModel (fail closed)"
            ) from exc
        if model is None:
            raise WalkForwardConsistencyError(
                f"risk model {risk_id!r} (referenced by the optimization) is not "
                "present in the research sidecar (fail closed)"
            )
        if model.research_result_id != risk_id:
            raise WalkForwardConsistencyError(
                f"risk model {risk_id!r} resolved to a record whose id "
                f"{model.research_result_id!r} disagrees with the reference "
                "(fail closed)"
            )
        if model.result_hash != risk_hash:
            raise WalkForwardConsistencyError(
                f"risk model {risk_id!r} has result_hash {model.result_hash!r} but the "
                f"optimization pinned {risk_hash!r}; the referenced risk model has "
                "drifted since the recipe was sealed (fail closed, WF-1)"
            )
        return model

    def _resolve_factor(
        self, factor_portfolio_id: str, store: ResearchResultStore
    ) -> FactorPortfolio:
        """Read + verify a referenced factor portfolio (fail closed)."""
        try:
            result = store.read_as(factor_portfolio_id, FactorPortfolio.from_dict)
        except (KeyError, ValueError) as exc:
            raise WalkForwardConsistencyError(
                f"factor portfolio {factor_portfolio_id!r} could not be decoded as a "
                "FactorPortfolio (fail closed)"
            ) from exc
        if result is None:
            raise WalkForwardConsistencyError(
                f"factor portfolio {factor_portfolio_id!r} is not present in the "
                "research sidecar; cannot walk a factor that was never sealed (fail "
                "closed)"
            )
        if result.research_result_id != factor_portfolio_id:
            raise WalkForwardConsistencyError(
                f"factor portfolio {factor_portfolio_id!r} resolved to a record "
                f"whose id {result.research_result_id!r} disagrees with the "
                "request (fail closed)"
            )
        return result

    def _inherit_risk_free(self, factors: list[FactorPortfolio]) -> str:
        """The shared risk-free-per-period convention across factors (fail closed).

        The Phase 19 summary needs the per-period risk-free rate; every factor carries
        its own, and the Phase 20 commensurability contract already guaranteed one
        shared rebalance schedule and producing engine version. A risk-free disagreement
        is a consistency defect (the factors were built under different conventions and
        their OOS Sharpe would not be comparable), raised rather than silently picking
        one.
        """
        risk_free = factors[0].risk_free_per_period
        for factor in factors[1:]:
            if factor.risk_free_per_period != risk_free:
                raise WalkForwardConsistencyError(
                    f"factor {factor.research_result_id!r} uses risk-free-per-period "
                    f"{factor.risk_free_per_period!r} but the first factor uses "
                    f"{risk_free!r}; the OOS summary requires one shared risk-free "
                    "convention (fail closed)"
                )
        return risk_free

    def _known_returns(self, factor: FactorPortfolio) -> dict[str, str]:
        """The factor's KNOWN ``as_of -> factor_return`` map (fail closed on dup date).

        Only KNOWN per-period cells contribute (an UNDEFINED period carries no return);
        the value is the already-canonical decimal string the factor portfolio sealed. A
        duplicate ``as_of`` among the KNOWN cells is a corrupt input (a schedule's dates
        are unique) and raises rather than being silently overwritten. The Phase 20
        alignment idiom, reused (WF-6).
        """
        known: dict[str, str] = {}
        for period in factor.per_period:
            cell = period.factor_return
            if cell.status is not FactorPortfolioStatus.KNOWN:
                continue
            assert cell.value is not None  # guaranteed by a KNOWN StatValue
            if period.as_of in known:
                raise WalkForwardConsistencyError(
                    f"factor {factor.research_result_id!r} carries a duplicate KNOWN "
                    f"return for as_of {period.as_of!r}; a schedule's dates must be "
                    "unique (fail closed)"
                )
            known[period.as_of] = cell.value
        return known

    def _common_dates(self, known_by_factor: list[dict[str, str]]) -> list[str]:
        """The complete-case common dates, ascending (§6, WF-6).

        The intersection of the ``as_of`` instants where **every** factor carries a
        KNOWN return, sorted ascending (lexicographic over the ISO-like instant strings
        the schedule emits). A date where any factor is UNDEFINED is excluded
        (complete-case), never filled or interpolated. The Phase 20 alignment idiom,
        reused.
        """
        if not known_by_factor:
            return []
        common: set[str] = set(known_by_factor[0])
        for known in known_by_factor[1:]:
            common &= known.keys()
        return sorted(common)

    # -- summary + aggregate variance (compose Phase 19) ----------------------

    def _summarize(
        self,
        chained: list[str],
        *,
        risk_free_per_period: str,
        periods_per_year: str,
        context: Context,
    ) -> WalkForwardSummary:
        """Summarize the chained OOS series via the Phase 19 method, mapped (§12).

        Composes :func:`~quantforge.factorportfolio.stats.series_summary` over the
        chained OOS returns, then maps its factor-portfolio :class:`StatValue` cells
        into walk-forward cells (a KNOWN value passes through; an UNDEFINED reason maps
        by its stable string value into the walk-forward reason vocabulary, fail-closed
        on an unexpected reason).
        """
        result = series_summary(
            chained,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            context=context,
        )
        return _map_summary(result)

    def _aggregate_realized_variance(
        self, chained: list[str], context: Context
    ) -> StatValue:
        """The population variance of the whole chained OOS return series (§5.1).

        The realized OOS variance the walk exists to compare against the recipe's
        in-sample predicted variance. KNOWN when at least two OOS periods; a single
        period has no dispersion (``SINGLE_VALID_PERIOD``); an empty series is
        ``NO_VALID_PERIODS`` (both unreachable for a sealed record, which has at least
        :data:`~quantforge.walkforward.result.MIN_VALID_WINDOWS` REALIZED windows).
        """
        m = len(chained)
        if m == 0:
            return StatValue.undefined(WalkForwardUndefinedReason.NO_VALID_PERIODS)
        if m == 1:
            return StatValue.undefined(WalkForwardUndefinedReason.SINGLE_VALID_PERIOD)
        with localcontext(context):
            values = [+Decimal(v) for v in chained]
            mean = sum(values, _ZERO) / Decimal(m)
            variance = sum(((v - mean) * (v - mean) for v in values), _ZERO) / Decimal(
                m
            )
            return StatValue.known(str(+variance))


def _map_cell(cell: FactorPortfolioStatValue) -> StatValue:
    """Map a factor-portfolio summary cell into a walk-forward cell (fail closed).

    A KNOWN value passes through unchanged; an UNDEFINED reason maps by its stable
    ``.value`` string into the walk-forward reason vocabulary (the three summary reasons
    are shared by construction). An unrecognized reason string is a corrupt input and
    raises rather than being guessed.
    """
    if cell.status is FactorPortfolioStatus.KNOWN:
        assert cell.value is not None  # guaranteed by a KNOWN StatValue
        return StatValue.known(cell.value)
    assert cell.reason is not None  # guaranteed by an UNDEFINED StatValue
    try:
        reason = WalkForwardUndefinedReason(cell.reason.value)
    except ValueError as exc:
        raise WalkForwardConsistencyError(
            f"the Phase 19 series summary produced an unexpected reason "
            f"{cell.reason.value!r} for a walk-forward OOS series (fail closed)"
        ) from exc
    return StatValue.undefined(reason)


def _map_summary(result: SeriesSummary) -> WalkForwardSummary:
    """Map a Phase 19 :class:`SeriesSummary` into a :class:`WalkForwardSummary`."""
    return WalkForwardSummary(
        cumulative_return=_map_cell(result.cumulative_return),
        mean_period_return=_map_cell(result.mean_period_return),
        volatility=_map_cell(result.volatility),
        annualized_sharpe=_map_cell(result.annualized_sharpe),
        mean_t_stat=_map_cell(result.mean_t_stat),
        hit_rate=_map_cell(result.hit_rate),
        n_valid_periods=result.n_valid_periods,
    )
