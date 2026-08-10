"""Offline, obviously-synthetic fixtures for Phase 19 factor-portfolio tests.

A characteristic-sorted long/short factor portfolio needs a cross-section wide enough
to fill both legs at each rebalance date - the leg floor is ``n_members >= 2 * Q`` - and
a realized forward return for every member. The Phase 18 cross-section corpus already
seeds exactly this shape (a configurable number of synthetic filers, each with a
``current_ratio`` signal that is *linear* in the filer index and a per-filer monthly
price history), so this module **reuses it verbatim** rather than duplicating the
XBRL/market seeding: :func:`~tests.crosssection.builders.populate` and its ``Corpus``,
``cik_for``, ``security_for``, ``default_bars``, ``default_schedule``, ``PERIOD``,
``EVAL_1`` / ``EVAL_2`` are imported below.

Filer ``i`` has ``current_ratio = 2 + i`` (a strictly increasing signal across the
members), so the quantile sort is fully determined: with five filers and ``Q = 2`` the
bottom bucket (short leg) is the lowest-``current_ratio`` filers and the top bucket
(long leg) the highest - hand-checkable. Everything is fictional and offline
(Principle 8): made-up CIKs ``9999999901..``, round-number values, no network.
"""

from __future__ import annotations

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.factorportfolio.engine import FactorPortfolioEngine
from quantforge.factorportfolio.spec import FactorPortfolioSpecification
from quantforge.metrics.model import MetricPeriod
from quantforge.universe.specification import UniverseSpecification
from tests.crosssection.builders import (
    DEFAULT_RETRIEVED_AT,
    EVAL_1,
    EVAL_2,
    FY_END,
    PERIOD,
    Corpus,
    cik_for,
    default_bars,
    default_schedule,
    populate,
    security_for,
    universe_spec,
)

__all__ = [
    "DEFAULT_RETRIEVED_AT",
    "EVAL_1",
    "EVAL_2",
    "FY_END",
    "PERIOD",
    "Corpus",
    "cik_for",
    "default_bars",
    "default_schedule",
    "factor_portfolio_engine",
    "make_spec",
    "populate",
    "security_for",
    "universe_spec",
]


def factor_portfolio_engine(corpus: Corpus) -> FactorPortfolioEngine:
    """The workspace's Phase 19 engine, narrowed from the ``object`` property."""
    engine = corpus.workspace.factor_portfolio_engine
    assert isinstance(engine, FactorPortfolioEngine)
    return engine


def make_spec(
    engine: FactorPortfolioEngine,
    *,
    n_filers: int = 5,
    signal: str = "current_ratio",
    period: MetricPeriod | None = None,
    forward_horizon: str = "1d",
    quantiles: int = 2,
    weighting: str = "equal",
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
    schedule: RebalanceSchedule | None = None,
    universe: UniverseSpecification | None = None,
    name: str = "phase19-synthetic",
) -> FactorPortfolioSpecification:
    """Assemble a fully pinned specification for the corpus.

    Pins are re-derived from the engine exactly as a real caller does: a throwaway spec
    with placeholder pins gives the source company ids, from which the true fundamentals
    + market dataset-version ids are computed and folded into the final spec (so
    ``construct`` re-derives them and P19-1 verification passes).
    """
    uni = universe or universe_spec(n_filers=n_filers)
    sched = schedule or default_schedule()
    per = period or PERIOD

    def _spec(fundamentals_id: str, market_id: str) -> FactorPortfolioSpecification:
        return FactorPortfolioSpecification(
            name=name,
            signal=signal,
            period=per,
            universe=uni,
            schedule=sched,
            forward_horizon=forward_horizon,
            quantiles=quantiles,
            dataset_version_id=fundamentals_id,
            market_dataset_version_id=market_id,
            weighting=weighting,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
        )

    placeholder = _spec("pending", "pending")
    fundamentals_id = engine.fundamentals_dataset_version(
        placeholder
    ).dataset_version_id
    market_id = engine.market_dataset_version(placeholder).dataset_version_id
    return _spec(fundamentals_id, market_id)
