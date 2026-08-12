"""Pairwise out-of-sample strategy comparison (Phase 24).

The first **comparison** capability strictly above Phase 22: a pure consumer that treats
an ordered set of ``N`` sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records as competing
strategies and asks the question a single out-of-sample walk cannot - *for each pair of
strategies, is the difference in their out-of-sample returns distinguishable from noise
on the dates they were both live?* It resolves the strategies from the shared Phase 8
sidecar, verifies they are commensurable (one shared rebalance schedule, one producing
factor-portfolio engine version, one annualization convention, one per-period risk-free
rate), reconstructs each strategy's realized OOS return series by calendar date (its one
deliberate deviation from the axis-index alignment of the approved proposal - a sealed
walk-forward record stores no dates, so Phase 24 rebuilds each strategy's complete-case
axis and maps its realized windows back onto calendar dates), and for each
upper-triangle ``(i < j)`` pair computes the paired-difference statistics over the two
strategies' shared dates: the mean OOS-return difference, its standard error, the paired
``t`` statistic, the two-sided ``p`` value, and a descriptive Sharpe difference. It
re-resolves no data, introduces no new PIT surface, adds no runtime dependency, and
creates no new store.

* :class:`~quantforge.comparison.spec.StrategyComparisonSpecification` - the
  declarative, content-addressed request: a name and an ordered tuple of 2..``N_MAX``
  distinct sealed ``walk_forward_ids``. Strategy order is semantic (it fixes the
  ``strategy_1..N`` labels and the upper-triangle pair order).
* :class:`~quantforge.comparison.engine.StrategyComparisonEngine` - resolves, verifies
  each strategy (present, a ``WalkForwardEvaluation``, REALIZED), enforces
  commensurability (SC-2), reconstructs each strategy's ``(as_of -> OOS return)`` map,
  computes every pair's paired-difference statistics, and seals a
  :class:`~quantforge.comparison.result.StrategyComparison`, persisting it write-once to
  the same sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.comparison_engine`).
* :class:`~quantforge.comparison.result.StrategyComparison` - the sealed,
  content-addressed record: the ordered strategy references, the shared schedule /
  producing engine version / annualization / risk-free convention, the per-strategy
  summary block (sealed annualized OOS Sharpe, valid-period count, reconstructed axis
  length), the upper-triangle pairwise matrix, and a coverage block. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (SC-6): not a ``Pit*`` type and no as-of
  accessor. Reading a ``(j, i)`` pair sign-flips the antisymmetric statistics (SC-8).
* :class:`~quantforge.comparison.model.StatValue` - the UNDEFINED-preserving cell: a
  KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.comparison.model.ComparisonUndefinedReason` (too little date
  overlap, a zero-variance paired difference, or an undefined leg Sharpe), never a
  fabricated ``0`` / ``NaN`` / divide-by-zero (SC-4).
* :class:`~quantforge.comparison.align.ReconstructedStrategy` /
  :func:`~quantforge.comparison.align.reconstruct_strategy` - the date reconstruction:
  re-resolve each strategy's transitive factor chain (fail closed on drift), recompute
  the complete-case date axis with the walk-forward engine's logic, and map the realized
  windows onto the axis dates (guarded against the sealed ``common_periods`` and chained
  ``oos_returns``).

Every identity is content-addressed (:mod:`quantforge.comparison.identity`), every value
deterministically serializable, and every failure follows the raise-vs-record split
(:mod:`quantforge.comparison.errors`): a request / consistency / reconstruction-drift
defect raises; a pair genuinely undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.comparison.align import ReconstructedStrategy, reconstruct_strategy
from quantforge.comparison.compute import MIN_OVERLAP_PERIODS
from quantforge.comparison.engine import StrategyComparisonEngine
from quantforge.comparison.errors import (
    ComparisonConfigurationError,
    ComparisonConsistencyError,
    ComparisonError,
)
from quantforge.comparison.identity import (
    strategy_comparison_id,
    strategy_comparison_result_hash,
)
from quantforge.comparison.model import (
    ComparisonStatus,
    ComparisonUndefinedReason,
    StatStatus,
    StatValue,
    strategy_label,
)
from quantforge.comparison.result import (
    BOUNDARY_PIT,
    COMPARISON_RESULT_FORMAT_VERSION,
    ComparisonCell,
    Coverage,
    StrategyComparison,
    TrialSummary,
)
from quantforge.comparison.spec import N_MAX, StrategyComparisonSpecification
from quantforge.comparison.version import (
    COMPARISON_ENGINE_VERSION,
    COMPARISON_METHOD_VERSION,
    COMPARISON_NORMAL_VERSION,
    COMPARISON_SPEC_VERSION,
    StrategyComparisonEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "COMPARISON_ENGINE_VERSION",
    "COMPARISON_METHOD_VERSION",
    "COMPARISON_NORMAL_VERSION",
    "COMPARISON_RESULT_FORMAT_VERSION",
    "COMPARISON_SPEC_VERSION",
    "MIN_OVERLAP_PERIODS",
    "N_MAX",
    "ComparisonCell",
    "ComparisonConfigurationError",
    "ComparisonConsistencyError",
    "ComparisonError",
    "ComparisonStatus",
    "ComparisonUndefinedReason",
    "Coverage",
    "ReconstructedStrategy",
    "StatStatus",
    "StatValue",
    "StrategyComparison",
    "StrategyComparisonEngine",
    "StrategyComparisonEngineVersion",
    "StrategyComparisonSpecification",
    "TrialSummary",
    "default_decimal_context",
    "reconstruct_strategy",
    "strategy_comparison_id",
    "strategy_comparison_result_hash",
    "strategy_label",
]
