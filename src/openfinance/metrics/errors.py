"""Exception hierarchy for the financial-metrics layer (Phase 7).

Rooted at :class:`MetricError` so a caller can catch every failure of this layer
with one type. Phase 7 *computes* derived metrics as a deterministic function of
the Phase 4 canonical facts and the Phase 5 point-in-time knowledge state.

The governing posture (data-model §12, ``docs/metrics.md`` §2, §13, §14) is a
sharp split between two failure kinds:

* A **data condition** — a required input is missing, nil, non-numeric, a
  denominator is zero, units disagree, or periods do not align — is **never** an
  exception. It is a first-class ``UNDEFINED`` metric result carrying an
  :class:`~openfinance.metrics.model.UndefinedReason`. A research sweep over many
  filers must record "undefined, because X" without aborting.
* A **configuration/consistency defect** — an unknown ``metric_key``, a formula
  whose operation references an undeclared input, a period request that
  contradicts the formula's own period type, or stored derived state that
  violates an invariant on read — *is* raised. These are our bugs, surfaced
  rather than silently resolved. A raised error is always preferable to a wrong
  metric.
"""

from __future__ import annotations

__all__ = [
    "FormulaConfigurationError",
    "MetricConsistencyError",
    "MetricError",
]


class MetricError(Exception):
    """Base class for all financial-metrics errors."""


class FormulaConfigurationError(MetricError):
    """A formula or metric request is internally inconsistent — our bug, surfaced.

    Raised for an unknown ``metric_key``, a formula whose operation tree
    references an input name it does not declare, a duplicate input name, or a
    metric request whose :class:`~openfinance.metrics.model.MetricPeriod` type
    contradicts the formula's declared primary period type. We refuse to guess a
    formula's intent, exactly as Phase 5 refuses to guess a misconfigured policy.
    """


class MetricConsistencyError(MetricError):
    """A computed or stored metric violates an integrity invariant on read.

    Fail-closed guard for derived state (data-model §12): surfaced rather than
    trusted so a corrupted or contradictory derivation can never silently masquerade
    as a valid metric.
    """
