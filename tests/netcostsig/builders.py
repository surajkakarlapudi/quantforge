"""Offline, obviously-synthetic fixtures for Phase 32 net-of-cost-significance tests.

Phase 32 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.netcost.result.NetOfCostPerformance`: the engine reads only its
``net_status``, its sealed aggregate ``net_mean`` / ``net_volatility`` cells, its
``coverage.n_periods`` and its ``boundary_kind`` - never the stability / walk-forward /
optimization / risk-model / factor chain beneath it, and never the per-window cells
(NS-4). So - like the calibration-significance builders - these builders synthesize a
``NetOfCostPerformance`` **directly** with a hand-chosen aggregate summary, seal it, and
persist it to the shared sidecar. Every id / hash the synthetic record pins is an
obviously-fictional placeholder (Principle 8): Phase 32 pins the net-of-cost record by
``(id, result_hash)`` and never resolves anything beneath it, so the placeholders are
load-bearing for identity only, never dereferenced.

The helpers cover the defensibility branches (NS-2/NS-3): a MEASURED source with a
chosen net mean + volatility (:func:`measured`), a MEASURED source with zero net
volatility (:func:`zero_volatility`), an UNDEFINED source (:func:`undefined_source`),
and - the defensive guard - a MEASURED source whose aggregate net-mean cell is UNDEFINED
(:func:`measured_mean_undefined`).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.netcost.model import (
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
)
from quantforge.netcost.result import (
    NetOfCostCoverage,
    NetOfCostPerformance,
    NetOfCostSummary,
)
from quantforge.netcostsig.engine import NetOfCostSignificanceEngine
from quantforge.netcostsig.spec import NetOfCostSignificanceSpecification
from quantforge.workspace import Workspace

__all__ = [
    "make_net_of_cost",
    "make_spec",
    "measured",
    "measured_mean_undefined",
    "netcostsig_engine",
    "undefined_source",
    "workspace",
    "zero_volatility",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def netcostsig_engine(ws: Workspace) -> NetOfCostSignificanceEngine:
    """The workspace's Phase 32 engine, narrowed from the ``object`` property."""
    engine = ws.net_of_cost_significance_engine
    assert isinstance(engine, NetOfCostSignificanceEngine)
    return engine


def _inert_known() -> NetCostStat:
    """A KNOWN aggregate cell Phase 32 never reads (gross / drag / break-even /
    sharpe)."""
    return NetCostStat.known("0")


def measured(*, net_mean: str, net_volatility: str) -> NetOfCostSummary:
    """A MEASURED summary with a chosen KNOWN net mean + volatility (the tested
    pair)."""
    return NetOfCostSummary(
        gross_mean=_inert_known(),
        gross_volatility=_inert_known(),
        gross_sharpe=_inert_known(),
        net_mean=NetCostStat.known(net_mean),
        net_volatility=NetCostStat.known(net_volatility),
        net_sharpe=_inert_known(),
        cost_drag_mean=_inert_known(),
        sharpe_drag=_inert_known(),
        break_even_cost_rate=_inert_known(),
        total_gross_return="0",
        total_turnover="0",
        total_cost="0",
        net_status=NetCostStatus.MEASURED,
    )


def zero_volatility(*, net_mean: str) -> NetOfCostSummary:
    """A (synthetic) MEASURED summary whose net series has zero population volatility.

    Structurally unreachable from the real Phase 31 engine (a KNOWN net Sharpe implies a
    positive net volatility), synthesized directly to exercise Phase 32's defensive
    ``ZERO_NET_VOLATILITY`` guard (NS-3).
    """
    return measured(net_mean=net_mean, net_volatility="0")


def undefined_source() -> NetOfCostSummary:
    """An UNDEFINED summary (its net Sharpe was never formed): every net cell
    UNDEFINED."""
    reason = NetCostUndefinedReason.ZERO_RETURN_VARIANCE
    undefined = NetCostStat.undefined(reason)
    return NetOfCostSummary(
        gross_mean=_inert_known(),
        gross_volatility=_inert_known(),
        gross_sharpe=_inert_known(),
        net_mean=undefined,
        net_volatility=undefined,
        net_sharpe=undefined,
        cost_drag_mean=_inert_known(),
        sharpe_drag=undefined,
        break_even_cost_rate=_inert_known(),
        total_gross_return="0",
        total_turnover="0",
        total_cost="0",
        net_status=NetCostStatus.UNDEFINED,
        status_reason=reason,
    )


def measured_mean_undefined() -> NetOfCostSummary:
    """Defensive: a MEASURED summary whose net-mean cell is UNDEFINED (unreachable)."""
    reason = NetCostUndefinedReason.ZERO_RETURN_VARIANCE
    return NetOfCostSummary(
        gross_mean=_inert_known(),
        gross_volatility=_inert_known(),
        gross_sharpe=_inert_known(),
        net_mean=NetCostStat.undefined(reason),
        net_volatility=NetCostStat.known("0.05"),
        net_sharpe=_inert_known(),
        cost_drag_mean=_inert_known(),
        sharpe_drag=_inert_known(),
        break_even_cost_rate=_inert_known(),
        total_gross_return="0",
        total_turnover="0",
        total_cost="0",
        net_status=NetCostStatus.MEASURED,
    )


def make_net_of_cost(
    ws: Workspace,
    *,
    summary: NetOfCostSummary,
    n_periods: int = 100,
    name: str = "synthetic-net-of-cost",
    cost_rate: str = "0.001",
    engine_version_id: str = "sha256:synthetic-netcost-engine",
) -> NetOfCostPerformance:
    """Seal a synthetic :class:`NetOfCostPerformance` and persist it to the sidecar.

    ``summary`` is the sealed aggregate block Phase 32 reads; ``n_periods`` the
    net-series period count ``n`` it reads from coverage. Returns the sealed record (its
    ``research_result_id`` is what a Phase 32 request points at). Every reference the
    record pins is a fictional placeholder that Phase 32 never dereferences.
    """
    coverage = NetOfCostCoverage(
        n_windows=1,
        n_realized=1,
        n_excluded=0,
        n_charged=1,
        n_periods=n_periods,
    )
    performance = NetOfCostPerformance.seal(
        net_of_cost_engine_version_id=engine_version_id,
        net_of_cost_spec={
            "spec_version": "netcost/1",
            "name": name,
            "source_stability_id": "sha256:stability",
            "cost_rate": cost_rate,
        },
        source_ref=("sha256:stability", "sha256:stability-hash"),
        boundary_kind="pit",
        periods_per_year="252",
        risk_free_per_period="0",
        windows=(),
        excluded=(),
        summary=summary,
        coverage=coverage,
    )
    ws.research_result_store.write(performance)
    return performance


def make_spec(
    source_id: str,
    *,
    name: str = "phase32-netcostsig",
) -> NetOfCostSignificanceSpecification:
    """A significance request over one sealed net-of-cost id."""
    return NetOfCostSignificanceSpecification(
        name=name, source_net_of_cost_id=source_id
    )
