"""Offline, obviously-synthetic fixtures for Phase 20 factor-risk tests.

A factor covariance/correlation model needs an ordered set of *N* sealed,
**commensurable** :class:`~quantforge.factorportfolio.result.FactorPortfolio` records -
each a factor whose KNOWN ``(as_of, factor_return)`` series shares one ``schedule_id``
and one ``factor_portfolio_engine_version_id``. The Phase 19 factor-portfolio corpus
(which in turn reuses the Phase 18 cross-section corpus) already produces exactly such
records: the same multi-filer corpus admits **two** distinct non-collinear signals
(``current_ratio`` and ``quick_ratio``), so constructing one factor portfolio per signal
over the same universe + schedule yields two commensurable factor return series with
distinct values. This module seals them via the workspace's Phase 19 engine and returns
their ids, so a factor-risk request references real sealed artifacts. Everything is
fictional and offline (Principle 8): made-up CIKs ``9999999901..``, round-number values,
no network.
"""

from __future__ import annotations

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.factorportfolio.result import FactorPortfolio
from quantforge.factorrisk.engine import FactorRiskEngine
from quantforge.factorrisk.spec import FactorRiskSpecification
from tests.crosssection.builders import (
    EVAL_1,
    EVAL_2,
    Corpus,
    populate,
)
from tests.factorportfolio.builders import factor_portfolio_engine, make_spec

__all__ = [
    "EVAL_1",
    "EVAL_2",
    "Corpus",
    "factor_risk_engine",
    "make_risk_spec",
    "populate",
    "seal_factor",
    "seal_two_factors",
]


def factor_risk_engine(corpus: Corpus) -> FactorRiskEngine:
    """The workspace's Phase 20 engine, narrowed from the ``object`` property."""
    engine = corpus.workspace.factor_risk_engine
    assert isinstance(engine, FactorRiskEngine)
    return engine


def seal_factor(
    corpus: Corpus,
    *,
    signal: str,
    name: str,
    n_filers: int = 5,
    quantiles: int = 2,
    schedule: RebalanceSchedule | None = None,
    periods_per_year: str = "1",
) -> FactorPortfolio:
    """Construct + seal one :class:`FactorPortfolio` over ``corpus`` and return it.

    Reuses the Phase 19 engine and its fully-pinned ``make_spec`` helper (which
    re-derives both corpus pins from the engine), so the sealed record is a real,
    verifiable factor-portfolio artifact in the shared sidecar. Two calls that differ
    only in ``signal`` yield two commensurable factors (one ``schedule_id``, one
    producing engine version) with distinct return series.
    """
    engine = factor_portfolio_engine(corpus)
    spec = make_spec(
        engine,
        n_filers=n_filers,
        signal=signal,
        quantiles=quantiles,
        schedule=schedule,
        periods_per_year=periods_per_year,
        name=name,
    )
    return engine.construct(spec)


def seal_two_factors(
    corpus: Corpus,
    *,
    n_filers: int = 5,
    schedule: RebalanceSchedule | None = None,
    periods_per_year: str = "1",
) -> tuple[FactorPortfolio, FactorPortfolio]:
    """Seal the two default commensurable factors (current_ratio, quick_ratio)."""
    first = seal_factor(
        corpus,
        signal="current_ratio",
        name="phase20-current-ratio",
        n_filers=n_filers,
        schedule=schedule,
        periods_per_year=periods_per_year,
    )
    second = seal_factor(
        corpus,
        signal="quick_ratio",
        name="phase20-quick-ratio",
        n_filers=n_filers,
        schedule=schedule,
        periods_per_year=periods_per_year,
    )
    return first, second


def make_risk_spec(
    *factors: FactorPortfolio,
    name: str = "phase20-synthetic",
    periods_per_year: str = "1",
) -> FactorRiskSpecification:
    """A factor-risk request over the given sealed factors, in the given order."""
    return FactorRiskSpecification(
        name=name,
        factor_portfolio_ids=tuple(f.research_result_id for f in factors),
        periods_per_year=periods_per_year,
    )
