"""Exception hierarchy for the performance-analytics layer (Phase 15, §Q).

Rooted at :class:`AnalyticsError` so a caller can catch every failure of this layer with
one type. Phase 15 is a *pure consumer* of Phase 12: it resolves already-sealed
:class:`~quantforge.backtest.result.BacktestResult`s from the shared research sidecar
and computes new risk / benchmark-relative statistics over their sealed
``period_returns``. It resolves no data at any ``T`` and re-derives nothing from source,
so its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§Q):

* A **data / research condition** — a statistic that is genuinely undefined for the
  data (Sortino with no downside, beta with zero benchmark variance, Calmar with no
  drawdown) — is **never** an exception. It is recorded as a first-class UNDEFINED
  :class:`~quantforge.analytics.model.StatValue` carrying *why*, and surfaced — never
  fabricated, never a divide-by-zero, never silently dropped.
* A **configuration / consistency defect** — an empty name, a ``var_confidence``
  outside ``(0, 1)``, a subject/benchmark that is not comparable (different
  ``schedule_id``, unequal return length, incommensurable engine version), a referenced
  id absent from the sidecar, a referenced record whose ``result_hash`` drifted, a
  non-PIT boundary — *is* raised. These are our bugs, surfaced rather than silently
  resolved. A raised error is always preferable to a wrong analytics record.
"""

from __future__ import annotations

__all__ = [
    "AnalyticsConfigurationError",
    "AnalyticsConsistencyError",
    "AnalyticsError",
]


class AnalyticsError(Exception):
    """Base class for all performance-analytics-layer errors."""


class AnalyticsConfigurationError(AnalyticsError):
    """An analytics request is internally inconsistent — our bug.

    Raised for a malformed :class:`~quantforge.analytics.spec.AnalyticsSpecification`
    (an empty ``name`` or ``subject_id``, a ``benchmark_id`` equal to the
    ``subject_id``, a ``var_confidence`` that is not a decimal string strictly in ``(0,
    1)`` or is duplicated, a non-decimal or negative ``risk_free_per_period``, a
    non-decimal or non-positive ``periods_per_year``), or for a subject whose return
    vector is too short for the whole record to be meaningful (``periods < 2`` for any
    variance-based statistic). We refuse to guess an analytics request's intent, exactly
    as Phase 12 refuses a misconfigured backtest.
    """


class AnalyticsConsistencyError(AnalyticsError):
    """A record cannot be honestly computed from the referenced artifacts — surfaced.

    Fail-closed guard for the comparability contract (§Q): a ``subject_id`` or
    ``benchmark_id`` absent from the research sidecar, a referenced record whose
    recomputed ``result_hash`` no longer matches the pinned value (drift), a subject and
    benchmark that do not share a ``schedule_id`` or whose ``period_returns`` differ in
    length (returns not alignable), a subject and benchmark computed under different
    ``backtest_engine_version_id``s (their statistics are not commensurable — mirrors
    Phase 13), or a referenced record whose implied boundary is not ``"pit"``. Each is a
    consistency violation and is raised — never silently computed around. (A corpus-pin
    difference is *not* raised: it is surfaced as
    :attr:`~quantforge.analytics.result.PerformanceAnalytics.pin_mismatch` and the
    record is still computed, exactly as ``UniverseComparison.mode_mismatch`` does.)
    """
