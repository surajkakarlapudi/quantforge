"""Exception hierarchy for the net-of-cost-significance layer (Phase 32, §15).

Rooted at :class:`NetCostSigError` so a caller can catch every failure of this layer
with one type. Phase 32 is a *pure consumer* strictly above Phase 31: it resolves
exactly one already-sealed :class:`~quantforge.netcost.result.NetOfCostPerformance` from
the shared research sidecar, reads its sealed ``net_mean`` / ``net_volatility`` and its
``coverage.n_periods``, and seals the one-sample significance test of the after-cost
mean return against the null mean ``0``. It resolves no data and re-derives no statistic
from source (NS-4), so its only failures are of the request or of a consistency
invariant.

The governing posture mirrors every prior layer's split (§15), and the calibration-
significance layer (Phase 29) in particular:

* A **data / evaluation condition** - a source whose ``net_status`` is UNDEFINED (its
  net Sharpe was never formed), or a source whose net return series has zero population
  volatility - is **never** an exception. A non-MEASURED source seals a record whose
  ``significance_status`` is UNDEFINED (``SOURCE_NOT_MEASURED``); a zero-volatility
  source seals KNOWN ``net_mean`` / ``edge_direction`` but UNDEFINED ``t_statistic`` /
  ``p_value`` (``ZERO_NET_VOLATILITY``, NS-3), never imputed, never a divide-by-zero.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_net_of_cost_id``, the source id absent from the sidecar, or a resolved record
  whose ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.netcost.result.NetOfCostPerformance` - *is* raised. These are our
  bugs, surfaced rather than silently resolved. A raised error is always preferable to a
  wrong significance verdict.
"""

from __future__ import annotations

__all__ = [
    "NetCostSigConfigurationError",
    "NetCostSigConsistencyError",
    "NetCostSigError",
]


class NetCostSigError(Exception):
    """Base class for all net-of-cost-significance-layer errors."""


class NetCostSigConfigurationError(NetCostSigError):
    """A net-of-cost-significance request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.netcostsig.spec.NetOfCostSignificanceSpecification` (an empty
    ``name`` / ``spec_version`` / ``source_net_of_cost_id``) or for a non-spec argument
    to the engine. We refuse to guess a request's intent, exactly as the calibration-
    significance layer refuses a misconfigured request."""


class NetCostSigConsistencyError(NetCostSigError):
    """A significance test cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, NS-1): the
    ``source_net_of_cost_id`` is absent from the research sidecar; the resolved record
    does not decode as a :class:`~quantforge.netcost.result.NetOfCostPerformance`; or
    the resolved record's ``research_result_id`` disagrees with the requested id (the
    sidecar is inconsistent). Each is a consistency violation and is raised - never
    silently computed around. (A source that is not MEASURED, or a zero-volatility net
    series, is *not* raised: it is genuinely undefined for the data, so the record seals
    with an UNDEFINED status or cell, NS-2/NS-3.)"""
