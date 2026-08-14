"""Net-of-cost walk-forward performance over one sealed stability record (Phase 31).

The first **net-of-cost** capability strictly above Phase 27: a pure consumer that
reads, from one sealed :class:`~quantforge.stability.result.WalkForwardStability`, its
per-REALIZED-window one-way ``turnover_from_prev`` and - transitively, from the one
sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability
record pins - the chained gross out-of-sample (OOS) return series and its sealed gross
performance summary, and asks what neither source answers - *what does this strategy
earn after paying a declared cost to trade, and at what cost rate does its gross edge
vanish?* It charges a **declared** linear transaction cost ``cost_rate · turnover_w`` at
each realized window's first OOS period (the per-window turnover and the per-period
gross returns are **not** zippable - the load-bearing alignment), summarizes the net
series with the *reused* Phase 19 series summary (the identical convention Phase 22 used
for gross, so the net Sharpe is comparable), and reports the parameter-free break-even
``Σ gross / Σ turnover``. It re-resolves no data, introduces no new PIT surface, adds no
runtime dependency, uses no ``_linalg`` / ``_stats`` primitive, and creates no new
store.

* :class:`~quantforge.netcost.spec.NetOfCostSpecification` - the declarative,
  content-addressed request: a name, exactly one sealed ``source_stability_id``, and the
  declared non-negative ``cost_rate`` (canonicalized; folded into the id; never inferred
  or defaulted, NC-3).
* :class:`~quantforge.netcost.engine.NetOfCostEngine` - resolves + verifies the source
  stability record and, transitively, the walk it pins (present, right types, id +
  pinned ``result_hash`` match, NC-1), aligns the per-window turnover to the per-period
  gross returns (fail closed on any axis mismatch), reads the gross summary verbatim
  (NC-4), computes the accounting
  (:func:`~quantforge.netcost.compute.compute_net_of_cost`), and seals a
  :class:`~quantforge.netcost.result.NetOfCostPerformance`, persisting it write-once to
  the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.net_of_cost_engine`).
* :class:`~quantforge.netcost.result.NetOfCostPerformance` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source stability
  record, the inherited annualization conventions, the per-realized-window gross /
  turnover / cost / net cells, the excluded windows, the aggregate
  :class:`~quantforge.netcost.result.NetOfCostSummary` (gross moments carried verbatim,
  net moments, cost drag, break-even rate), and a coverage block. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post and counterfactual, not PIT** (NC-6): not a ``Pit*``
  type and no as-of accessor.
* :class:`~quantforge.netcost.model.NetCostStatus` /
  :class:`~quantforge.netcost.model.NetCostExcludedReason` /
  :class:`~quantforge.netcost.model.NetCostUndefinedReason` /
  :class:`~quantforge.netcost.model.NetCostStat` - the closed fail-closed vocabulary:
  whether a net Sharpe was formed, why a window is excluded, why a cell / the roll-up is
  UNDEFINED, and the UNDEFINED-preserving stat cell.

Every identity is content-addressed (:mod:`quantforge.netcost.identity`) and
transitively pins the source stability record's ``result_hash`` (and the declared
``cost_rate``), every value is deterministically serializable and computed in exact
``Decimal`` arithmetic under a pinned context (``Decimal.sqrt`` inside the reused Phase
19 summary the only transcendental; no RNG, no float, no unbounded iteration), and every
failure follows the raise-vs-record split (:mod:`quantforge.netcost.errors`): a request
/ consistency defect raises; a never-trading strategy seals an UNDEFINED
``DEGENERATE_NO_TURNOVER`` break-even and a zero-net-variance series seals an UNDEFINED
``net_sharpe`` (``ZERO_RETURN_VARIANCE``), never imputed, never a divide-by-zero.
"""

from __future__ import annotations

from quantforge.netcost.compute import (
    NetCostComputation,
    RealizedWindowInput,
    WindowNetCost,
    compute_net_of_cost,
)
from quantforge.netcost.engine import NetOfCostEngine
from quantforge.netcost.errors import (
    NetOfCostConfigurationError,
    NetOfCostConsistencyError,
    NetOfCostError,
)
from quantforge.netcost.identity import (
    net_of_cost_id,
    net_of_cost_result_hash,
)
from quantforge.netcost.model import (
    NetCostExcludedReason,
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
    StatStatus,
)
from quantforge.netcost.result import (
    BOUNDARY_PIT,
    NETCOST_RESULT_FORMAT_VERSION,
    ExcludedWindow,
    NetOfCostCoverage,
    NetOfCostPerformance,
    NetOfCostSummary,
    WindowNetCostCell,
)
from quantforge.netcost.spec import NetOfCostSpecification
from quantforge.netcost.version import (
    NETCOST_ENGINE_VERSION,
    NETCOST_METHOD_VERSION,
    NETCOST_SPEC_VERSION,
    NETCOST_SUMMARY_VERSION,
    NetOfCostEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "NETCOST_ENGINE_VERSION",
    "NETCOST_METHOD_VERSION",
    "NETCOST_RESULT_FORMAT_VERSION",
    "NETCOST_SPEC_VERSION",
    "NETCOST_SUMMARY_VERSION",
    "ExcludedWindow",
    "NetCostComputation",
    "NetCostExcludedReason",
    "NetCostStat",
    "NetCostStatus",
    "NetCostUndefinedReason",
    "NetOfCostConfigurationError",
    "NetOfCostConsistencyError",
    "NetOfCostCoverage",
    "NetOfCostEngine",
    "NetOfCostEngineVersion",
    "NetOfCostError",
    "NetOfCostPerformance",
    "NetOfCostSpecification",
    "NetOfCostSummary",
    "RealizedWindowInput",
    "StatStatus",
    "WindowNetCost",
    "WindowNetCostCell",
    "compute_net_of_cost",
    "default_decimal_context",
    "net_of_cost_id",
    "net_of_cost_result_hash",
]
