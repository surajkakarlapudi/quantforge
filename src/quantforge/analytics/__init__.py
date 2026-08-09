"""Performance & benchmark-relative analytics: deterministic, content-addressed risk
statistics (Phase 15).

The layer strictly above Phase 12 (proposal D1): it consumes an already-sealed,
PIT-correct :class:`~quantforge.backtest.result.BacktestResult` (and, optionally,
another as a benchmark — proposal D3), computes the family of risk and
benchmark-relative statistics Phase 12 deferred *by name*, and seals the answer as a new
:class:`~quantforge.factors.store.ResearchRecord`. It re-resolves no data, introduces no
new PIT surface, adds no runtime dependency, and creates no new store.

* :class:`~quantforge.analytics.spec.AnalyticsSpecification` — the declarative,
  content-addressed request: a name, the ``subject_id`` of a sealed backtest, an
  optional benchmark ``backtest_id``, the VaR confidences, and the annualization
  convention (proposal §J.1).
* :class:`~quantforge.analytics.engine.AnalyticsEngine` — resolves the subject (and
  benchmark) from the shared sidecar, verifies them (fail closed on missing / drifted /
  incommensurable — proposal §Q), computes the statistics under the pinned decimal
  context, and seals a :class:`~quantforge.analytics.result.PerformanceAnalytics`,
  persisting it write-once to the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.analytics_engine`).
* :class:`~quantforge.analytics.result.PerformanceAnalytics` — the sealed,
  content-addressed record: the referenced ``(backtest_id, result_hash)`` pointers, the
  three computed statistic blocks (absolute / relative / VaR), the recorded convention,
  and the carried corpus pins. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically (proposal §J.2, D6).
* :class:`~quantforge.analytics.model.StatValue` — the UNDEFINED-preserving statistic
  cell: a KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.analytics.model.AnalyticsUndefinedReason`, never a fabricated
  ``0`` / ``NaN`` / divide-by-zero (proposal D5).

Every identity is content-addressed (:mod:`quantforge.analytics.identity`), every value
deterministically serializable, and every failure follows the raise-vs-record split
(:mod:`quantforge.analytics.errors`): a defect raises; a statistic genuinely undefined
for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.analytics.engine import AnalyticsEngine
from quantforge.analytics.errors import (
    AnalyticsConfigurationError,
    AnalyticsConsistencyError,
    AnalyticsError,
)
from quantforge.analytics.model import (
    ABSOLUTE_KEYS,
    RELATIVE_KEYS,
    VAR_KEYS,
    AnalyticsStatus,
    AnalyticsUndefinedReason,
    StatValue,
)
from quantforge.analytics.result import (
    ANALYTICS_RESULT_FORMAT_VERSION,
    BOUNDARY_PIT,
    PerformanceAnalytics,
)
from quantforge.analytics.spec import (
    ANALYTICS_SPEC_VERSION,
    AnalyticsSpecification,
)
from quantforge.analytics.version import (
    ANALYTICS_ENGINE_VERSION,
    ANALYTICS_FORMULA_VERSION,
    AnalyticsEngineVersion,
    default_decimal_context,
)

__all__ = [
    "ABSOLUTE_KEYS",
    "ANALYTICS_ENGINE_VERSION",
    "ANALYTICS_FORMULA_VERSION",
    "ANALYTICS_RESULT_FORMAT_VERSION",
    "ANALYTICS_SPEC_VERSION",
    "BOUNDARY_PIT",
    "RELATIVE_KEYS",
    "VAR_KEYS",
    "AnalyticsConfigurationError",
    "AnalyticsConsistencyError",
    "AnalyticsEngine",
    "AnalyticsEngineVersion",
    "AnalyticsError",
    "AnalyticsSpecification",
    "AnalyticsStatus",
    "AnalyticsUndefinedReason",
    "PerformanceAnalytics",
    "StatValue",
    "default_decimal_context",
]
