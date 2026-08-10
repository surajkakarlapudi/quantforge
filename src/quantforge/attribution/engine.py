"""The factor-attribution orchestration engine (proposal §6, §11, D1).

:class:`AttributionEngine` sits strictly **above** Phase 12: it is a pure consumer that
turns a declarative :class:`~quantforge.attribution.spec.AttributionSpecification` into
a sealed :class:`~quantforge.attribution.result.FactorAttribution` by *resolving* the
already-sealed backtest(s) a request is about (a subject plus *K* factors), *verifying*
them, *regressing* the subject's excess return on the factors' excess returns, and
sealing the answer. It introduces no new data-resolution logic, no new PIT surface, and
no new store: the subject and factors were sealed PIT-correctly by Phase 12, and the
attribution record persists write-once to the shared research sidecar (§6, §10, D1).

The build (proposal §6):

1. **Resolve** the ``subject_id`` and each ``factor_id`` from the shared sidecar via
   ``store.read_as(id, BacktestResult.from_dict)``. A missing id is a consistency defect
   (we refuse to analyse an artifact we cannot materialize) and raises
   :class:`~quantforge.attribution.errors.AttributionConsistencyError` (fail closed).
2. **Verify** each resolved record: its ``research_result_id`` equals the requested id;
   its recomputed ``result_hash`` still matches the sealed value (drift detection) —
   each
   disagreement raises.
3. **Verify commensurability** (FA-3): every factor must share the subject's exact
   ``schedule_id``, an equal ``period_returns`` length, and the same
   ``backtest_engine_version_id`` — strict, fail-closed; a corpus ``pin_mismatch`` is
   *surfaced* on the record, never raised.
4. **Check degrees of freedom** (§11): ``n >= K + 2`` (K loadings + intercept + ≥1
   residual df); otherwise a configuration defect is raised rather than sealing a record
   with no residual degrees of freedom.
5. **Regress** the excess subject on the excess factors under the pinned decimal
context,
   UNDEFINED-preserving (no float, no RNG, no wall-clock).
6. **Seal** the computed blocks + residual digest into a
   :class:`~quantforge.attribution.result.FactorAttribution` (its ``result_hash`` folds
   the answer) and persist it write-once to the same sidecar. Rebuilding an identical
   request is a byte-identical no-op; a differing payload under the same id fails closed
   via the store's guard.

The engine holds no mutable per-run state — a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from quantforge.attribution.errors import (
    AttributionConfigurationError,
    AttributionConsistencyError,
)
from quantforge.attribution.identity import residual_digest as _residual_digest
from quantforge.attribution.result import BOUNDARY_PIT, FactorAttribution
from quantforge.attribution.spec import AttributionSpecification
from quantforge.attribution.stats import attribute_returns
from quantforge.attribution.version import AttributionEngineVersion
from quantforge.backtest.identity import result_hash as _recompute_result_hash
from quantforge.backtest.result import BacktestResult
from quantforge.factors.store import ResearchResultStore
from quantforge.workspace import Workspace

__all__ = ["AttributionEngine"]

#: The minimum residual degrees of freedom the record requires (proposal §11). With *K*
#: factor loadings plus an intercept, ``n - K - 1`` must be ≥ 1 for the residual
#: variance
#: (and hence every standard error / t-statistic) to be defined — so ``n >= K + 2``.
#: Below this the record would have no residual df, so we raise a configuration defect
#: rather than seal a degenerate record.
_MIN_RESIDUAL_DF = 1


class AttributionEngine:
    """Resolve, verify, regress, and seal a declarative attribution request (§6, D1).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar — the same store the
    backtest engine sealed its artifacts to — so a request analyses exactly the
    backtests already present. The sidecar may be overridden (for tests). The engine
    pins its OLS logic + formula + decimal context via
    :class:`AttributionEngineVersion`, and computes every statistic under that version's
    decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: AttributionEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else AttributionEngineVersion()

    @property
    def attribution_engine_version_id(self) -> str:
        """The engine-logic + formula + decimal-context version folded into every id."""
        return self._version.attribution_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The shared write-once sidecar the attribution resolves from and persists
        to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def attribute(self, spec: AttributionSpecification) -> FactorAttribution:
        """Resolve, verify, regress, seal, and persist attribution from ``spec`` (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same backtests, recomputes byte-identical statistics under the
        pinned decimal context, and seals a byte-identical
        :class:`~quantforge.attribution.result.FactorAttribution` on any machine (whose
        sidecar write is an idempotent no-op). Fails closed on any missing/drifted
        reference, incommensurable factor, or insufficient periods.
        """
        if not isinstance(spec, AttributionSpecification):
            raise AttributionConfigurationError(
                "attribute() requires an AttributionSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        subject = self._resolve(spec.subject_id, store)
        subject_returns = subject.performance.statistics.period_returns
        periods = len(subject_returns)
        k = len(spec.factor_ids)
        if periods < k + 1 + _MIN_RESIDUAL_DF:
            raise AttributionConfigurationError(
                f"subject backtest {spec.subject_id!r} has {periods} return "
                f"observation(s), but a {k}-factor regression needs at least "
                f"{k + 1 + _MIN_RESIDUAL_DF} (K factor loadings + intercept + at least "
                f"{_MIN_RESIDUAL_DF} residual degree(s) of freedom); fail closed "
                "than seal a record with no residual degrees of freedom"
            )

        factors: list[BacktestResult] = []
        factor_returns: list[tuple[str, ...]] = []
        for factor_id in spec.factor_ids:
            factor = self._resolve(factor_id, store)
            self._verify_commensurable(subject, factor)
            factors.append(factor)
            factor_returns.append(factor.performance.statistics.period_returns)

        # -- regress (under the pinned decimal context) ----------------------
        estimate = attribute_returns(
            subject_returns,
            factor_returns,
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            context=context,
        )

        # -- carried-through corpus pins (distinct, sorted; §9, FA-1) --------
        dataset_pins = _distinct(
            subject.dataset_version_id, *(f.dataset_version_id for f in factors)
        )
        market_pins = _distinct(
            subject.market_dataset_version_id,
            *(f.market_dataset_version_id for f in factors),
        )

        factor_refs = tuple(
            (label, factor.backtest_id, factor.result_hash)
            for label, factor in zip(_factor_labels(k), factors, strict=True)
        )

        attribution = FactorAttribution.seal(
            attribution_engine_version_id=self._version.attribution_engine_version_id,
            attribution_spec=spec.to_dict(),
            subject_ref=(subject.backtest_id, subject.result_hash),
            factor_refs=factor_refs,
            boundary_kind=BOUNDARY_PIT,
            schedule_id=subject.schedule_id,
            periods=periods,
            coefficients=estimate.coefficients,
            diagnostics=estimate.diagnostics,
            decomposition=estimate.decomposition,
            residual_digest=_residual_digest(list(estimate.residuals)),
            risk_free_per_period=spec.risk_free_per_period,
            periods_per_year=spec.periods_per_year,
            dataset_version_ids=dataset_pins,
            market_dataset_version_ids=market_pins,
            formula_version=self._version.formula_version,
        )
        # Persist write-once to the shared research sidecar (D1). Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(attribution)
        return attribution

    # -- resolution & verification -------------------------------------------

    def _resolve(self, backtest_id: str, store: ResearchResultStore) -> BacktestResult:
        """Read + verify a referenced backtest from the sidecar (fail closed, §6, §18).

        Verifies three fail-closed consistency guards: the id is present; the resolved
        record's own ``research_result_id`` equals the requested id (a corrupt sidecar
        whose key disagrees with its content); and the record's ``result_hash`` still
        equals the hash recomputed from its ledger (drift — a tampered or replaced
        upstream record can never be silently analysed). The PIT boundary needs no
        runtime check: a :class:`~quantforge.backtest.result.BacktestResult` is PIT-only
        by construction (there is no ``RevisedBacktest``), so the sealed attribution
        record carries the explicit ``boundary_kind = "pit"`` unconditionally,
        documenting the input side; the attribution output remains ex-post and non-PIT
        (FA-2).
        """
        result = store.read_as(backtest_id, BacktestResult.from_dict)
        if result is None:
            raise AttributionConsistencyError(
                f"backtest {backtest_id!r} is not present in the research sidecar; "
                "cannot attribute an artifact that was never sealed (fail closed)"
            )
        if result.research_result_id != backtest_id:
            raise AttributionConsistencyError(
                f"backtest {backtest_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        recomputed = _recompute_result_hash(
            [record.outcome_digest() for record in result.ledger]
        )
        if recomputed != result.result_hash:
            raise AttributionConsistencyError(
                f"backtest {backtest_id!r} has drifted: its ledger recomputes to "
                f"{recomputed!r} but the sealed result_hash is {result.result_hash!r};"
                " refusing to attribute a record whose content no longer matches its "
                "seal"
            )
        return result

    def _verify_commensurable(
        self, subject: BacktestResult, factor: BacktestResult
    ) -> None:
        """Enforce the strict subject/factor comparability contract (§6, FA-3).

        Fail-closed on any of: a different ``schedule_id`` (the returns do not align on
        a common rebalance calendar), unequal ``period_returns`` length (the vectors are
        not alignable point-for-point), or a different ``backtest_engine_version_id``
        (the two return series were produced by different engine logic and are not
        commensurable — mirrors Phase 13/15). We never silently align mismatched
        datasets by truncating, filling, or interpolating; a raised error beats a wrong
        loading. A corpus pin difference is *not* raised here — it is surfaced as
        :attr:`~quantforge.attribution.result.FactorAttribution.pin_mismatch`.
        """
        if subject.schedule_id != factor.schedule_id:
            raise AttributionConsistencyError(
                f"subject schedule {subject.schedule_id!r} and factor schedule "
                f"{factor.schedule_id!r} differ; attribution requires every return "
                "series to align on the same rebalance schedule (fail closed)"
            )
        subject_len = len(subject.performance.statistics.period_returns)
        factor_len = len(factor.performance.statistics.period_returns)
        if subject_len != factor_len:
            raise AttributionConsistencyError(
                f"subject has {subject_len} period return(s) but factor has "
                f"{factor_len}; the vectors are not alignable point-for-point "
                "(fail closed rather than truncate or pad)"
            )
        if subject.backtest_engine_version_id != factor.backtest_engine_version_id:
            raise AttributionConsistencyError(
                f"subject engine version {subject.backtest_engine_version_id!r} and "
                f"factor engine version {factor.backtest_engine_version_id!r} differ; "
                "their return series are not commensurable (fail closed)"
            )


def _factor_labels(k: int) -> tuple[str, ...]:
    """The deterministic factor labels ``factor_1..factor_K`` in request order."""
    from quantforge.attribution.model import factor_label

    return tuple(factor_label(i) for i in range(k))


def _distinct(*values: str | None) -> tuple[str, ...]:
    """The distinct non-``None`` pins, sorted (§9, FA-1).

    Sorted so the carried pins are order-independent (they are a set of corpus
    snapshots, not a sequence). A single shared pin collapses to one entry; a
    subject/factor disagreement yields more than one, which
    :attr:`~quantforge.attribution.result.FactorAttribution.pin_mismatch` then surfaces.
    """
    seen = {value for value in values if value is not None}
    return tuple(sorted(seen))
