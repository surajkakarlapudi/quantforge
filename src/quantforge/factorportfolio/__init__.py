"""Characteristic-sorted long/short factor-portfolio construction (Phase 19).

The first member of a new **portfolio-construction** capability class - a constructive
sibling strictly above Phases 9/10/11, distinct from the Phase 16 diagnostic scalar and
the Phase 12 execution simulator. At each scheduled rebalance date ``T`` it resolves the
survivorship-free universe PIT as-of ``T``, reads the signal cross-section via
``panel_across(as_of=T)``, pairs each member with a realized *forward* return over ``[T,
T+h]`` trading days, sorts the members into ``Q`` quantiles by the PIT signal, forms a
long (top bucket) and short (bottom bucket) equal-weight leg, and takes the
long-minus-short spread as that period's factor return; chaining the valid per-period
spreads yields a factor return series with a performance summary. It re-resolves no
data, introduces no new PIT surface, adds no runtime dependency, and creates no new
store; it consumes **no** ``BacktestResult`` and produces none (P19-5).

* :class:`~quantforge.factorportfolio.spec.FactorPortfolioSpecification` - the
  declarative, content-addressed request: a name, a signal ``metric_key`` + its explicit
  :class:`~quantforge.metrics.model.MetricPeriod`, a Phase 9 universe, a Phase 12
  evaluation schedule, a forward-return horizon, a quantile count ``Q``, a leg-weighting
  scheme, an annualization convention, and the two corpus pins.
* :class:`~quantforge.factorportfolio.engine.FactorPortfolioEngine` - resolves, verifies
  both corpus pins (P19-1, fail closed), forms the legs per date under the pinned
  decimal context, aggregates the return-series summary, and seals a
  :class:`~quantforge.factorportfolio.result.FactorPortfolio`, persisting it write-once
  to the same Phase 8 sidecar (reached via
  :attr:`~quantforge.workspace.Workspace.factor_portfolio_engine`).
* :class:`~quantforge.factorportfolio.result.FactorPortfolio` - the sealed,
  content-addressed record: the per-period factor-return panel with leg holdings, the
  aggregated summary, a coverage summary, and the carried corpus pins. Satisfies the
  :class:`~quantforge.factors.store.ResearchRecord` Protocol and round-trips
  byte-identically. It is **ex-post, not PIT** (P19-2): not a ``Pit*`` type, no as-of
  accessor, and not a ``BacktestResult`` (P19-5).
* :class:`~quantforge.factorportfolio.model.StatValue` - the UNDEFINED-preserving
  statistic cell: a KNOWN decimal string **or** an UNDEFINED
  :class:`~quantforge.factorportfolio.model.FactorPortfolioUndefinedReason`, never a
  fabricated ``0`` / ``NaN`` / divide-by-zero, never a silently dropped member or leg
  (P19-4).

Every identity is content-addressed (:mod:`quantforge.factorportfolio.identity`), every
value deterministically serializable, and every failure follows the raise-vs-record
split (:mod:`quantforge.factorportfolio.errors`): a request / consistency defect raises;
a statistic genuinely undefined for the data is recorded with its reason.
"""

from __future__ import annotations

from quantforge.factorportfolio.engine import FactorPortfolioEngine
from quantforge.factorportfolio.errors import (
    FactorPortfolioConfigurationError,
    FactorPortfolioConsistencyError,
    FactorPortfolioError,
)
from quantforge.factorportfolio.identity import (
    factor_portfolio_id,
    factor_portfolio_result_hash,
)
from quantforge.factorportfolio.model import (
    CoverageSummary,
    DateCoverage,
    FactorPortfolioStatus,
    FactorPortfolioUndefinedReason,
    FactorReturnSummary,
    LegKind,
    LegMembership,
    PerPeriodReturn,
    StatValue,
)
from quantforge.factorportfolio.result import (
    BOUNDARY_PIT,
    FACTORPORTFOLIO_RESULT_FORMAT_VERSION,
    FactorPortfolio,
)
from quantforge.factorportfolio.spec import (
    WEIGHTING_EQUAL,
    FactorPortfolioSpecification,
)
from quantforge.factorportfolio.version import (
    FACTORPORTFOLIO_ENGINE_VERSION,
    FACTORPORTFOLIO_FORMULA_VERSION,
    FACTORPORTFOLIO_SPEC_VERSION,
    FactorPortfolioEngineVersion,
    default_decimal_context,
)

__all__ = [
    "BOUNDARY_PIT",
    "FACTORPORTFOLIO_ENGINE_VERSION",
    "FACTORPORTFOLIO_FORMULA_VERSION",
    "FACTORPORTFOLIO_RESULT_FORMAT_VERSION",
    "FACTORPORTFOLIO_SPEC_VERSION",
    "WEIGHTING_EQUAL",
    "CoverageSummary",
    "DateCoverage",
    "FactorPortfolio",
    "FactorPortfolioConfigurationError",
    "FactorPortfolioConsistencyError",
    "FactorPortfolioEngine",
    "FactorPortfolioEngineVersion",
    "FactorPortfolioError",
    "FactorPortfolioSpecification",
    "FactorPortfolioStatus",
    "FactorPortfolioUndefinedReason",
    "FactorReturnSummary",
    "LegKind",
    "LegMembership",
    "PerPeriodReturn",
    "StatValue",
    "default_decimal_context",
    "factor_portfolio_id",
    "factor_portfolio_result_hash",
]
