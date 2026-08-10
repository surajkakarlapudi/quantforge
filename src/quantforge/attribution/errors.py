"""Exception hierarchy for the factor-attribution layer (Phase 17, §11).

Rooted at :class:`AttributionError` so a caller can catch every failure of this layer
with one type. Phase 17 is a *pure consumer* of Phase 12: it resolves already-sealed
:class:`~quantforge.backtest.result.BacktestResult`s (a subject plus *K* factors) from
the shared research sidecar and regresses the subject's sealed ``period_returns`` on the
factors'. It resolves no data at any ``T`` and re-derives nothing from source, so its
only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§11), and the analytics layer
in particular (Phase 15 §Q):

* A **data / estimation condition** — a coefficient block that is genuinely undefined
  for the data (a singular/collinear design, too few residual degrees of freedom, a
  zero-variance regressand, a perfect in-sample fit) — is **never** an exception. It is
  recorded as a first-class UNDEFINED
  :class:`~quantforge.attribution.model.StatValue` carrying *why* (FA-4), and surfaced —
  never fabricated, never a divide-by-zero, never a silently dropped factor.
* A **configuration / consistency defect** — an empty name, an empty/duplicate factor
  list, a factor id equal to the subject id, too many factors (``> K_MAX``), too few
  periods for the requested factor count, a subject/factor that is not commensurable
  (different ``schedule_id``, unequal return length, incommensurable engine version), a
  referenced id absent from the sidecar, a referenced record whose ``result_hash``
  drifted — *is* raised. These are our bugs, surfaced rather than silently resolved. A
  raised error is always preferable to a wrong attribution record.
"""

from __future__ import annotations

__all__ = [
    "AttributionConfigurationError",
    "AttributionConsistencyError",
    "AttributionError",
]


class AttributionError(Exception):
    """Base class for all factor-attribution-layer errors."""


class AttributionConfigurationError(AttributionError):
    """An attribution request is internally inconsistent — our bug.

    Raised for a malformed
    :class:`~quantforge.attribution.spec.AttributionSpecification` (an empty ``name`` or
    ``subject_id``; an empty ``factor_ids`` tuple, a duplicate factor id, or a factor id
    equal to the ``subject_id``; more than ``K_MAX`` factors; a non-decimal or negative
    ``risk_free_per_period``; a non-decimal or non-positive ``periods_per_year``), or
    for a subject whose return vector is too short for the requested model to be
    estimable (``periods < K + 2`` — *K* factor loadings plus an intercept plus at least
    one residual degree of freedom). We refuse to guess an attribution request's intent,
    exactly as Phase 12 refuses a misconfigured backtest.
    """


class AttributionConsistencyError(AttributionError):
    """A record cannot be honestly computed from the referenced artifacts — surfaced.

    Fail-closed guard for the reference + commensurability contract (§11, FA-1/FA-3): a
    ``subject_id`` or a factor ``backtest_id`` absent from the research sidecar, a
    referenced record whose recomputed ``result_hash`` no longer matches the pinned
    value (drift), or a subject and factor that do not share a ``schedule_id``, whose
    ``period_returns`` differ in length (returns not alignable), or that were computed
    under different ``backtest_engine_version_id``s (their return series are not
    commensurable — mirrors Phase 13/15). Each is a consistency violation and is raised
    — never silently computed around. (A corpus-pin difference is *not* raised: it is
    surfaced as :attr:`~quantforge.attribution.result.FactorAttribution.pin_mismatch`
    and the record is still computed, exactly as ``PerformanceAnalytics.pin_mismatch``
    does.)
    """
