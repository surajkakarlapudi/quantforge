"""The net-of-cost-significance orchestration engine (§6, §11, §12, NS-1..NS-6).

:class:`NetOfCostSignificanceEngine` sits strictly **above** Phase 31: it is a pure
consumer that turns a declarative
:class:`~quantforge.netcostsig.spec.NetOfCostSignificanceSpecification` into a sealed
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` by *resolving* the one
already-sealed :class:`~quantforge.netcost.result.NetOfCostPerformance` the request
names, *verifying* it, *gating* on its defensibility, *reading its sealed aggregate
statistics verbatim* (the after-cost mean return, the population net volatility, and the
net-series period count - never recomputed, NS-4), *computing* the one-sample
large-sample upper-tailed significance test over them
(:func:`~quantforge.netcostsig.compute.test_net_of_cost_significance`), and sealing the
answer. It introduces no new data resolution, no new PIT surface, and no new store; it
composes the pinned pure test under the version's decimal context and persists
write-once to the shared research sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** the ``source_net_of_cost_id`` from the shared sidecar via
   ``store.read_as(id, NetOfCostPerformance.from_dict)``. A missing id (or a payload
   that does not decode as a ``NetOfCostPerformance``) is a consistency defect and
   raises :class:`~quantforge.netcostsig.errors.NetCostSigConsistencyError` (fail
   closed, NS-1).
2. **Verify** the resolved record's ``research_result_id`` equals the requested id (the
   sidecar is otherwise inconsistent); raise on disagreement (NS-1).
3. **Gate on defensibility** (NS-2): build the :class:`MeasuredNetSeries` only when the
   source's ``net_status`` is ``MEASURED`` **and** its sealed ``net_mean`` /
   ``net_volatility`` cells are both KNOWN - reading those decimal strings verbatim
   (NS-4). Otherwise the series is ``None`` and the test is UNDEFINED
   ``SOURCE_NOT_MEASURED`` - recorded, never fabricated.
4. **Compute** the test
   (:func:`~quantforge.netcostsig.compute.test_net_of_cost_significance`) under the
   version's decimal context: ``standard_error = net_volatility / sqrt(n)``,
   ``t = (net_mean - 0) / standard_error``, the one-sided ``p = 1 - Φ(t)`` clamped to
   ``[0, 1]``, and the descriptive edge direction - with the zero-volatility guard
   sealing ``t`` / ``p`` UNDEFINED ``ZERO_NET_VOLATILITY`` while ``net_mean`` and
   direction stay KNOWN (NS-3), never a divide-by-zero.
5. **Seal + persist**: seal a
   :class:`~quantforge.netcostsig.result.NetOfCostSignificance` (its ``result_hash``
   folds the answer, its id transitively pins the source net-of-cost record's
   ``result_hash``) and persist it write-once to the same sidecar. Rebuilding an
   identical request is a byte-identical no-op; a differing payload under the same id
   fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.factors.store import ResearchResultStore
from quantforge.netcost.model import NetCostStatus, StatStatus
from quantforge.netcost.result import NetOfCostPerformance
from quantforge.netcostsig.compute import (
    MeasuredNetSeries,
    test_net_of_cost_significance,
)
from quantforge.netcostsig.errors import (
    NetCostSigConfigurationError,
    NetCostSigConsistencyError,
)
from quantforge.netcostsig.result import (
    NULL_MEAN_RETURN,
    NetOfCostSignificance,
    SignificanceSummary,
)
from quantforge.netcostsig.spec import NetOfCostSignificanceSpecification
from quantforge.netcostsig.version import NetOfCostSignificanceEngineVersion
from quantforge.workspace import Workspace

__all__ = ["NetOfCostSignificanceEngine"]


class NetOfCostSignificanceEngine:
    """Resolve, verify, gate, compute, and seal a significance request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    net-of-cost engine sealed its performances to - so a request evaluates exactly the
    net-of-cost record already present. The sidecar may be overridden (for tests). The
    engine pins its orchestration logic + statistical method + normal primitive +
    decimal context via
    :class:`~quantforge.netcostsig.version.NetOfCostSignificanceEngineVersion`, and
    computes every value under that version's decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: NetOfCostSignificanceEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = (
            version if version is not None else NetOfCostSignificanceEngineVersion()
        )

    @property
    def net_of_cost_significance_engine_version_id(self) -> str:
        """The orchestration + method + normal + decimal-context version, folded into
        every id."""
        return self._version.net_of_cost_significance_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the significance resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(
        self, spec: NetOfCostSignificanceSpecification
    ) -> NetOfCostSignificance:
        """Resolve, verify, gate, compute, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same source net-of-cost record, recomputes byte-identical
        statistics under the pinned decimal context, and seals a byte-identical
        :class:`~quantforge.netcostsig.result.NetOfCostSignificance` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on a missing /
        drifted reference or a non-``NetOfCostPerformance`` record (NS-1); a source that
        is not defensibly MEASURED yields a sealed record whose test is UNDEFINED
        ``SOURCE_NOT_MEASURED`` (NS-2), never raised; a degenerate zero-volatility net
        series seals ``t`` / ``p`` UNDEFINED ``ZERO_NET_VOLATILITY`` (NS-3).
        """
        if not isinstance(spec, NetOfCostSignificanceSpecification):
            raise NetCostSigConfigurationError(
                "evaluate() requires a NetOfCostSignificanceSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify the one source net-of-cost record (NS-1) --------
        source = self._resolve_net_of_cost(spec.source_net_of_cost_id, store)

        # -- gate on defensibility + read sealed statistics verbatim (NS-2/NS-4)
        series = self._series(source)

        # -- compute the one-sample test (NS-3/NS-4/NS-5) ---------------------
        computation = test_net_of_cost_significance(
            series,
            null_mean=Decimal(NULL_MEAN_RETURN),
            context=context,
        )
        summary = SignificanceSummary(
            net_mean=computation.net_mean,
            null_mean_return=NULL_MEAN_RETURN,
            n_periods=computation.n_periods,
            standard_error=computation.standard_error,
            t_statistic=computation.t_statistic,
            p_value=computation.p_value,
            significance_status=computation.significance_status,
            edge_direction=computation.edge_direction,
            status_reason=computation.status_reason,
        )

        # -- seal + persist ---------------------------------------------------
        significance = NetOfCostSignificance.seal(
            net_of_cost_significance_engine_version_id=(
                self._version.net_of_cost_significance_engine_version_id
            ),
            net_of_cost_significance_spec=spec.to_dict(),
            source_ref=(source.research_result_id, source.result_hash),
            # Carry the source net-of-cost record's boundary through unchanged: it
            # documents that the underlying factor portfolios were PIT walks. The
            # significance output is ex-post and is not a PIT value (NS-6).
            boundary_kind=source.boundary_kind,
            summary=summary,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(significance)
        return significance

    # -- resolution & verification -------------------------------------------

    def _resolve_net_of_cost(
        self, source_id: str, store: ResearchResultStore
    ) -> NetOfCostPerformance:
        """Read + verify the one referenced source net-of-cost record (fail closed,
        NS-1)."""
        try:
            result = store.read_as(source_id, NetOfCostPerformance.from_dict)
        except (KeyError, ValueError) as exc:
            raise NetCostSigConsistencyError(
                f"source net-of-cost record {source_id!r} could not be decoded as a "
                "NetOfCostPerformance; the referenced artifact is absent "
                "or not a net-of-cost performance (fail closed)"
            ) from exc
        if result is None:
            raise NetCostSigConsistencyError(
                f"source net-of-cost record {source_id!r} is not present in the "
                "research sidecar; cannot test a net-of-cost performance that was "
                "never sealed (fail closed)"
            )
        if result.research_result_id != source_id:
            raise NetCostSigConsistencyError(
                f"source net-of-cost record {source_id!r} resolved to a record whose "
                f"id {result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        return result

    # -- defensibility gate ---------------------------------------------------

    def _series(self, source: NetOfCostPerformance) -> MeasuredNetSeries | None:
        """The sealed ``(mean, volatility, n)`` bundle, or ``None`` if not defensible.

        Builds a :class:`~quantforge.netcostsig.compute.MeasuredNetSeries` only when the
        source is defensibly MEASURED **and** its sealed ``net_mean`` /
        ``net_volatility`` cells are both KNOWN, reading those canonical decimal strings
        verbatim into ``Decimal`` (NS-4 - never recomputed from the per-window cells).
        Otherwise returns ``None``, so the test is UNDEFINED ``SOURCE_NOT_MEASURED``
        (NS-2). The defensive KNOWN check guards the structurally-unreachable case of a
        MEASURED source whose aggregate cell is not KNOWN - never coerced into a number.
        """
        if source.net_status is not NetCostStatus.MEASURED:
            return None
        summary = source.summary
        mean = summary.net_mean
        volatility = summary.net_volatility
        if mean.status is not StatStatus.KNOWN or mean.value is None:
            return None
        if volatility.status is not StatStatus.KNOWN or volatility.value is None:
            return None
        return MeasuredNetSeries(
            net_mean=Decimal(mean.value),
            net_volatility=Decimal(volatility.value),
            n_periods=source.coverage.n_periods,
        )
