"""Exception hierarchy for the net-of-cost layer (Phase 31, §15).

Rooted at :class:`NetOfCostError` so a caller can catch every failure of this layer
with one type. Phase 31 is a *pure consumer* strictly above Phase 27: it resolves
exactly one already-sealed
:class:`~quantforge.stability.result.WalkForwardStability` from the shared research
sidecar, re-resolves the one
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability pins (its
transitive source), reads the sealed gross out-of-sample return series and the sealed
per-window one-way turnover, applies a *declared* linear transaction-cost rate, and
seals the net-of-cost performance and the parameter-free break-even cost rate. It
resolves no data and re-derives no gross statistic from a corpus (NC-1), so its only
failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the calibration /
significance / stability layers in particular:

* A **data / evaluation condition** - a strategy whose realized windows never trade
  (total one-way turnover exactly ``0``, so the break-even cost rate does not exist), or
  a net return series with zero population dispersion (so the net Sharpe does not
  exist) - is **never** an exception. A never-trading strategy seals a record whose
  ``break_even_cost_rate`` is UNDEFINED (``DEGENERATE_NO_TURNOVER``) and whose net
  series equals the gross series (cost is exactly zero, honestly reported); a
  zero-net-variance series seals a KNOWN ``net_mean`` / ``net_volatility`` but an
  UNDEFINED ``net_sharpe`` (``ZERO_RETURN_VARIANCE``, NC-5), never imputed, never a
  divide-by-zero.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_stability_id``, a ``cost_rate`` that is not a non-negative finite decimal,
  the source id absent from the sidecar, a resolved record whose ``research_result_id``
  disagrees with the request or that is not the expected type, a transitive
  walk-forward whose ``result_hash`` has drifted from the pin stability sealed, or a
  Phase 27 / Phase 22 pair whose window axes do not agree (a reconstructed gross series
  that disagrees with the sealed chained series, or an index set that does not line
  up) - *is* raised. These are our bugs, surfaced rather than silently resolved. A
  raised error is always preferable to a wrong net-of-cost verdict.
"""

from __future__ import annotations

__all__ = [
    "NetOfCostConfigurationError",
    "NetOfCostConsistencyError",
    "NetOfCostError",
]


class NetOfCostError(Exception):
    """Base class for all net-of-cost-layer errors."""


class NetOfCostConfigurationError(NetOfCostError):
    """A net-of-cost request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.netcost.spec.NetOfCostSpecification` (an empty ``name`` /
    ``spec_version`` / ``source_stability_id``, or a ``cost_rate`` that is not a
    non-negative finite decimal string) or for a non-spec argument to the engine. We
    refuse to guess a request's intent, and above all we refuse to default a cost rate:
    the cost rate is a *declared* modeling assumption (NC-3), never inferred from data
    and never assumed."""


class NetOfCostConsistencyError(NetOfCostError):
    """A net-of-cost record cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, NC-1): the
    ``source_stability_id`` is absent from the research sidecar; the resolved record
    does not decode as a
    :class:`~quantforge.stability.result.WalkForwardStability`; the resolved record's
    ``research_result_id`` disagrees with the requested id; the transitive
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability pins is
    absent, decodes as the wrong type, or has a ``result_hash`` that has drifted from
    the pin stability sealed; or the two sources' window axes are non-commensurable (the
    per-realized-window turnover cells do not line up one-to-one with the walk's
    REALIZED windows, the excluded set disagrees, or the gross series reconstructed from
    the walk's realized windows disagrees with its sealed chained series). Each is a
    consistency violation and is raised - never silently intersected or computed around.
    (A never-trading strategy, or a zero-net-variance series, is *not* raised: it is
    genuinely undefined for the data, so the record seals with an UNDEFINED cell,
    NC-5.)"""
