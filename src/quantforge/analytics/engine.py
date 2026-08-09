"""The performance-analytics orchestration engine (proposal §I, §Q, D1).

:class:`AnalyticsEngine` sits strictly **above** Phase 12: it is a pure consumer that
turns a declarative :class:`~quantforge.analytics.spec.AnalyticsSpecification` into a
sealed :class:`~quantforge.analytics.result.PerformanceAnalytics` by *resolving* the
already-sealed backtest(s) a request is about, *verifying* them, *computing* the risk /
benchmark-relative statistics Phase 12 deferred, and sealing the answer. It introduces
no new data-resolution logic, no new PIT surface, and no new store: the subject and
benchmark were sealed PIT-correctly by Phase 12, and the analytics record persists
write-once to the shared research sidecar (proposal §I, §P, D1).

The build (proposal §I):

1. **Resolve** the ``subject_id`` (and optional ``benchmark_id``) from the shared
   sidecar
   via ``store.read_as(id, BacktestResult.from_dict)``. A missing id is a consistency
   defect (we refuse to analyse an artifact we cannot materialize) and raises
   :class:`~quantforge.analytics.errors.AnalyticsConsistencyError` (fail closed, §Q).
2. **Verify** each resolved record: its ``research_result_id`` equals the requested id;
   its recomputed ``result_hash`` still matches the sealed value (drift detection, §R);
   its implied boundary is ``"pit"`` (v1 PIT-only, §M) — each disagreement raises.
3. **Verify commensurability** (only when a benchmark is present, §Q, D3): subject and
   benchmark must share the exact ``schedule_id`` and equal ``period_returns`` length
   and be computed under the same ``backtest_engine_version_id`` — strict, fail-closed;
   a corpus ``pin_mismatch`` is *surfaced* on the record, never raised.
4. **Compute** the absolute (+ relative) + VaR statistics under the pinned decimal
   context, UNDEFINED-preserving (no float, no RNG, no wall-clock).
5. **Seal** the computed blocks into a :class:`PerformanceAnalytics` (its
   ``result_hash``
   folds the answer) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard (§P, Phase 14 D8).

The engine holds no mutable per-run state — a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical (§O).
"""

from __future__ import annotations

from quantforge.analytics.compute import (
    absolute_statistics,
    relative_statistics,
    var_statistics,
)
from quantforge.analytics.errors import (
    AnalyticsConfigurationError,
    AnalyticsConsistencyError,
)
from quantforge.analytics.model import StatValue
from quantforge.analytics.result import (
    BOUNDARY_PIT,
    PerformanceAnalytics,
)
from quantforge.analytics.spec import AnalyticsSpecification
from quantforge.analytics.version import AnalyticsEngineVersion
from quantforge.backtest.identity import result_hash as _recompute_result_hash
from quantforge.backtest.result import BacktestResult
from quantforge.factors.store import ResearchResultStore
from quantforge.workspace import Workspace

__all__ = ["AnalyticsEngine"]

#: The minimum return observations for the whole record to be meaningful (proposal §Q):
#: every dispersion-based statistic (volatility, skewness, beta, tracking error) needs
#: at least two. Below this the record would be all-UNDEFINED, so we raise a
#: configuration defect rather than seal a meaningless record.
_MIN_PERIODS = 2


class AnalyticsEngine:
    """Resolve, verify, compute, and seal a declarative analytics request (§I, D1).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar — the same store the
    backtest engine sealed its artifacts to — so a request analyses exactly the
    backtests already present. The sidecar may be overridden (for tests). The engine
    pins its statistics logic + formula + decimal context via
    :class:`AnalyticsEngineVersion`, and computes every statistic under that version's
    decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: AnalyticsEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else AnalyticsEngineVersion()

    @property
    def analytics_engine_version_id(self) -> str:
        """The engine-logic + formula + decimal-context version folded into every id."""
        return self._version.analytics_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared write-once sidecar the analytics resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def compute(self, spec: AnalyticsSpecification) -> PerformanceAnalytics:
        """Resolve, verify, compute, seal, and persist analytics from ``spec`` (§I, §P).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same backtests, recomputes byte-identical statistics under the
        pinned decimal context, and seals a byte-identical
        :class:`~quantforge.analytics.result.PerformanceAnalytics` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on any missing/drifted
        reference, non-PIT boundary, or incommensurable benchmark (§Q).
        """
        if not isinstance(spec, AnalyticsSpecification):
            raise AnalyticsConfigurationError(
                "compute() requires an AnalyticsSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        subject = self._resolve(spec.subject_id, store)
        subject_returns = subject.performance.statistics.period_returns
        periods = len(subject_returns)
        if periods < _MIN_PERIODS:
            raise AnalyticsConfigurationError(
                f"subject backtest {spec.subject_id!r} has {periods} return "
                f"observation(s); at least {_MIN_PERIODS} are required for any "
                "dispersion-based statistic to be meaningful (fail closed rather than "
                "seal an all-UNDEFINED record)"
            )

        benchmark: BacktestResult | None = None
        benchmark_returns: tuple[str, ...] | None = None
        if spec.benchmark_id is not None:
            benchmark = self._resolve(spec.benchmark_id, store)
            benchmark_returns = benchmark.performance.statistics.period_returns
            self._verify_commensurable(subject, benchmark)

        # -- compute (under the pinned decimal context) ----------------------
        absolute = absolute_statistics(
            subject_returns,
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            context=context,
        )
        if benchmark_returns is not None:
            relative = relative_statistics(
                subject_returns,
                benchmark_returns,
                risk_free_per_period=spec.risk_free_per_period,
                periods_per_year=spec.periods_per_year,
                context=context,
            )
        else:
            # No benchmark → the relative block is empty (never fabricated). The
            # absolute block is fully defined without one (proposal §J.3).
            relative = _empty_relative()
        var = var_statistics(
            subject_returns, spec.sorted_var_confidences, context=context
        )

        # -- carried-through corpus pins (distinct, sorted; §N) --------------
        dataset_pins = _distinct(
            subject.dataset_version_id,
            benchmark.dataset_version_id if benchmark is not None else None,
        )
        market_pins = _distinct(
            subject.market_dataset_version_id,
            benchmark.market_dataset_version_id if benchmark is not None else None,
        )

        analytics = PerformanceAnalytics.seal(
            analytics_engine_version_id=self._version.analytics_engine_version_id,
            analytics_spec=spec.to_dict(),
            subject_ref=(subject.backtest_id, subject.result_hash),
            benchmark_ref=(
                (benchmark.backtest_id, benchmark.result_hash)
                if benchmark is not None
                else None
            ),
            boundary_kind=BOUNDARY_PIT,
            schedule_id=subject.schedule_id,
            periods=periods,
            absolute=absolute,
            relative=relative,
            var=var,
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            dataset_version_ids=dataset_pins,
            market_dataset_version_ids=market_pins,
            formula_version=self._version.formula_version,
        )
        # Persist write-once to the shared research sidecar (D1). Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(analytics)
        return analytics

    # -- resolution & verification -------------------------------------------

    def _resolve(self, backtest_id: str, store: ResearchResultStore) -> BacktestResult:
        """Read + verify a referenced backtest from the sidecar (fail closed, §I, §R).

        Verifies three fail-closed consistency guards: the id is present; the resolved
        record's own ``research_result_id`` equals the requested id (a corrupt sidecar
        whose key disagrees with its content); and the record's ``result_hash`` still
        equals the hash recomputed from its ledger (drift — a tampered or replaced
        upstream record can never be silently analysed). The PIT boundary needs no
        runtime check: a :class:`~quantforge.backtest.result.BacktestResult` is PIT-only
        by construction (there is no ``RevisedBacktest``), so the sealed analytics
        record carries the explicit ``boundary_kind = "pit"`` unconditionally (§M). A
        future REVISED-scope backtest would carry a distinct boundary and be handled by
        a distinct analytics scope.
        """
        result = store.read_as(backtest_id, BacktestResult.from_dict)
        if result is None:
            raise AnalyticsConsistencyError(
                f"backtest {backtest_id!r} is not present in the research sidecar; "
                "cannot analyse an artifact that was never sealed (fail closed)"
            )
        if result.research_result_id != backtest_id:
            raise AnalyticsConsistencyError(
                f"backtest {backtest_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        recomputed = _recompute_result_hash(
            [record.outcome_digest() for record in result.ledger]
        )
        if recomputed != result.result_hash:
            raise AnalyticsConsistencyError(
                f"backtest {backtest_id!r} has drifted: its ledger recomputes to "
                f"{recomputed!r} but the sealed result_hash is {result.result_hash!r}; "
                "refusing to analyse a record whose content no longer matches its seal"
            )
        return result

    def _verify_commensurable(
        self, subject: BacktestResult, benchmark: BacktestResult
    ) -> None:
        """Enforce the strict subject/benchmark comparability contract (§Q, D3).

        Fail-closed on any of: a different ``schedule_id`` (the returns do not align on
        a common rebalance calendar), unequal ``period_returns`` length (the vectors are
        not alignable point-for-point), or a different ``backtest_engine_version_id``
        (the two return series were produced by different engine logic and are not
        commensurable — mirrors Phase 13). We never silently align mismatched datasets
        by truncating, filling, or interpolating; a raised error beats a wrong relative
        statistic. A corpus pin difference is *not* raised here — it is surfaced as
        :attr:`~quantforge.analytics.result.PerformanceAnalytics.pin_mismatch`.
        """
        if subject.schedule_id != benchmark.schedule_id:
            raise AnalyticsConsistencyError(
                f"subject schedule {subject.schedule_id!r} and benchmark schedule "
                f"{benchmark.schedule_id!r} differ; relative statistics require both "
                "return series to align on the same rebalance schedule (fail closed)"
            )
        subject_len = len(subject.performance.statistics.period_returns)
        benchmark_len = len(benchmark.performance.statistics.period_returns)
        if subject_len != benchmark_len:
            raise AnalyticsConsistencyError(
                f"subject has {subject_len} period return(s) but benchmark has "
                f"{benchmark_len}; the vectors are not alignable point-for-point "
                "(fail closed rather than truncate or pad)"
            )
        if subject.backtest_engine_version_id != benchmark.backtest_engine_version_id:
            raise AnalyticsConsistencyError(
                f"subject engine version {subject.backtest_engine_version_id!r} and "
                f"benchmark engine version {benchmark.backtest_engine_version_id!r} "
                "differ; their return series are not commensurable (fail closed)"
            )


def _empty_relative() -> tuple[tuple[str, StatValue], ...]:
    """The relative block is absent (not fabricated) when no benchmark is declared.

    An empty tuple, never a block of zeros or UNDEFINEDs: a request without a benchmark
    asks no relative question, so no relative cell exists to answer.
    """
    return ()


def _distinct(*values: str | None) -> tuple[str, ...]:
    """The distinct non-``None`` pins, sorted (§N).

    Sorted so the carried pins are order-independent (they are a set of corpus
    snapshots, not a sequence). A single shared pin collapses to one entry; a
    subject/benchmark disagreement yields two, which
    :attr:`~quantforge.analytics.result.PerformanceAnalytics.pin_mismatch` then
    surfaces.
    """
    seen = {value for value in values if value is not None}
    return tuple(sorted(seen))
