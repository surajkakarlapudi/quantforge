"""Net-of-cost-significance test over one sealed net-of-cost performance (Phase 32).

The first **net-of-cost-significance** capability strictly above Phase 31 - and the
first significance test applied to an *economic* (after-cost) quantity: a pure consumer
that reads, from one sealed :class:`~quantforge.netcost.result.NetOfCostPerformance`,
its sealed aggregate after-cost ``net_mean``, population ``net_volatility`` and its
net-series period count ``n_periods``, and asks what the net-of-cost record never asks -
*is the after-cost mean return significantly greater than ``0`` (a real edge, not noise,
given the realized sample length)?* It runs the one-sample large-sample upper-tailed
test ``t = (net_mean - 0) / (net_volatility / sqrt(n))``, ``p = 1 - Φ(t)``, reusing the
*identical* deterministic standard-normal CDF
:func:`~quantforge._stats.normal.standard_normal_cdf` (shared with Phases 23/24/29) - so
it adds no new statistical primitive. It resolves the one net-of-cost record from the
shared Phase 8 sidecar, gates on its defensibility, consumes its sealed statistics
verbatim (never recomputed, NS-4), and seals the significance verdict. It re-resolves no
data, introduces no new PIT surface, adds no runtime dependency, uses no ``_linalg``
primitive, and creates no new store.

* :class:`~quantforge.netcostsig.spec.NetOfCostSignificanceSpecification` - the
  declarative, content-addressed request: a name and exactly one sealed
  ``source_net_of_cost_id``. There is no per-request numerical parameter: the null mean
  tested is the fixed platform constant
  :data:`~quantforge.netcostsig.result.NULL_MEAN_RETURN` (``0``).
* :class:`~quantforge.netcostsig.engine.NetOfCostSignificanceEngine` - resolves +
  verifies the source net-of-cost record (present, a ``NetOfCostPerformance``, id
  matches), gates on ``net_status == MEASURED`` (NS-2), reads its sealed mean /
  volatility / period count verbatim (NS-4), computes the test
  (:func:`~quantforge.netcostsig.compute.test_net_of_cost_significance`), and seals a
  :class:`~quantforge.netcostsig.result.NetOfCostSignificance`, persisting it write-once
  to the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.net_of_cost_significance_engine`).
* :class:`~quantforge.netcostsig.result.NetOfCostSignificance` - the sealed,
  content-addressed record: the ``(id, result_hash)`` pin to the source net-of-cost
  record and the aggregate :class:`~quantforge.netcostsig.result.SignificanceSummary`
  (the net mean carried verbatim, the null mean, the period count, the standard error,
  the ``t`` statistic, the one-sided ``p`` value, the descriptive edge direction, and
  the roll-up status). Satisfies the :class:`~quantforge.factors.store.ResearchRecord`
  Protocol and round-trips byte-identically. It is **ex-post, not PIT** (NS-6): not a
  ``Pit*`` type and no as-of accessor.
* :class:`~quantforge.netcostsig.model.SignificanceStatus` /
  :class:`~quantforge.netcostsig.model.NetCostSigUndefinedReason` /
  :class:`~quantforge.netcostsig.model.EdgeDirection` /
  :class:`~quantforge.netcostsig.model.SignificanceStat` - the closed fail-closed
  vocabulary: whether the test was run, why it (or a cell) is UNDEFINED, the descriptive
  sign of the after-cost edge, and the UNDEFINED-preserving stat cell.

Every identity is content-addressed (:mod:`quantforge.netcostsig.identity`) and
transitively pins the source net-of-cost record's ``result_hash``, every value is
deterministically serializable and computed in exact ``Decimal`` arithmetic under a
pinned context (``Decimal.sqrt`` and the reused ``Φ`` CDF the only transcendentals; no
RNG, no float, no unbounded iteration), and every failure follows the raise-vs-record
split (:mod:`quantforge.netcostsig.errors`): a request / consistency defect raises; a
source that is not MEASURED seals an UNDEFINED ``SOURCE_NOT_MEASURED`` verdict and a
zero-volatility net series seals UNDEFINED ``t`` / ``p`` (``ZERO_NET_VOLATILITY``),
never imputed, never a divide-by-zero.
"""

from __future__ import annotations

from quantforge.netcostsig.compute import (
    MeasuredNetSeries,
    SignificanceComputation,
    test_net_of_cost_significance,
)
from quantforge.netcostsig.engine import NetOfCostSignificanceEngine
from quantforge.netcostsig.errors import (
    NetCostSigConfigurationError,
    NetCostSigConsistencyError,
    NetCostSigError,
)
from quantforge.netcostsig.identity import (
    net_of_cost_significance_id,
    net_of_cost_significance_result_hash,
)
from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStat,
    SignificanceStatus,
    StatStatus,
)
from quantforge.netcostsig.result import (
    BOUNDARY_PIT,
    NETCOSTSIG_RESULT_FORMAT_VERSION,
    NULL_MEAN_RETURN,
    NetOfCostSignificance,
    SignificanceSummary,
)
from quantforge.netcostsig.spec import NetOfCostSignificanceSpecification
from quantforge.netcostsig.version import (
    NETCOSTSIG_ENGINE_VERSION,
    NETCOSTSIG_METHOD_VERSION,
    NETCOSTSIG_NORMAL_VERSION,
    NETCOSTSIG_SPEC_VERSION,
    NetOfCostSignificanceEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "NETCOSTSIG_ENGINE_VERSION",
    "NETCOSTSIG_METHOD_VERSION",
    "NETCOSTSIG_NORMAL_VERSION",
    "NETCOSTSIG_RESULT_FORMAT_VERSION",
    "NETCOSTSIG_SPEC_VERSION",
    "NULL_MEAN_RETURN",
    "EdgeDirection",
    "MeasuredNetSeries",
    "NetCostSigConfigurationError",
    "NetCostSigConsistencyError",
    "NetCostSigError",
    "NetCostSigUndefinedReason",
    "NetOfCostSignificance",
    "NetOfCostSignificanceEngine",
    "NetOfCostSignificanceEngineVersion",
    "NetOfCostSignificanceSpecification",
    "SignificanceComputation",
    "SignificanceStat",
    "SignificanceStatus",
    "SignificanceSummary",
    "StatStatus",
    "default_decimal_context",
    "net_of_cost_significance_id",
    "net_of_cost_significance_result_hash",
    "test_net_of_cost_significance",
]
