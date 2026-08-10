"""Fixtures for Phase 17 attribution tests, reusing the Phase 12 combined corpus.

Phase 17 is a pure consumer of Phase 12: its tests need already-sealed
:class:`~quantforge.backtest.result.BacktestResult` artifacts to regress, plus the
combined fundamentals + market corpus that produces them. This module re-exports the
Phase 12 ``populate`` / ``make_spec`` machinery and adds the attribution-layer helpers:
a
typed :class:`AttributionEngine` accessor over the populated workspace, a multi-period
corpus (six rebalance instants → five returns, enough residual degrees of freedom for a
two-factor regression), and seal helpers that run + persist subject / factor backtests.

Everything stays fictional and offline (Principle 8) — the identities and bars come
straight from ``tests/backtest/builders`` (two made-up CIKs ``9999999991`` /
``9999999992``, round-number OHLC values, no network). To obtain genuinely distinct
return series for a subject and *K* factors from only two tradable securities, the
helpers vary the strategy (top-1 ascending vs descending → holds A vs B) and the
rebalance schedule, all over the same pinned corpus so the results stay commensurable.
"""

from __future__ import annotations

from pathlib import Path

from quantforge.attribution.engine import AttributionEngine
from quantforge.attribution.spec import AttributionSpecification
from quantforge.backtest.result import BacktestResult
from quantforge.backtest.schedule import RebalanceSchedule
from tests.backtest.builders import (
    CIK_A,
    CIK_B,
    Corpus,
    make_spec,
    populate,
)
from tests.market.builders import bar

__all__ = [
    "CIK_A",
    "CIK_B",
    "SIX_INSTANTS",
    "Corpus",
    "attribution_engine",
    "attribution_spec",
    "multi_period_corpus",
    "seal_backtest",
    "seal_factor",
    "seal_subject",
]

# Six rebalance instants → five return observations, enough for a two-factor regression
# (n = 5 ≥ K + 2 = 4) to have residual degrees of freedom.
_INSTANTS = [
    "2024-01-15T00:00:00Z",
    "2024-02-15T00:00:00Z",
    "2024-03-15T00:00:00Z",
    "2024-04-15T00:00:00Z",
    "2024-05-15T00:00:00Z",
    "2024-06-15T00:00:00Z",
]
SIX_INSTANTS = RebalanceSchedule.of(_INSTANTS)

# Bars chosen so the two filers move differently period-to-period, giving a subject
# (holds B) and a factor (holds A) that are genuinely distinct commensurable series.
_BARS_A = [
    bar("2024-01-10", close="10"),
    bar("2024-02-10", close="11"),
    bar("2024-03-10", close="9"),
    bar("2024-04-10", close="12"),
    bar("2024-05-10", close="13"),
    bar("2024-06-10", close="10"),
]
_BARS_B = [
    bar("2024-01-10", close="20"),
    bar("2024-02-10", close="24"),
    bar("2024-03-10", close="21"),
    bar("2024-04-10", close="27"),
    bar("2024-05-10", close="25"),
    bar("2024-06-10", close="30"),
]


def multi_period_corpus(root: Path) -> Corpus:
    """A populated corpus whose default six-instant schedule yields five returns."""
    return populate(root, bars_a=_BARS_A, bars_b=_BARS_B)


def attribution_engine(corpus: Corpus) -> AttributionEngine:
    """The workspace's Phase 17 engine, narrowed from the ``object`` property.

    :attr:`Workspace.attribution_engine` is typed ``object`` (to keep the engine import
    lazy and cycle-free); this asserts the concrete type once so every test reads a
    fully typed :class:`AttributionEngine`.
    """
    engine = corpus.workspace.attribution_engine
    assert isinstance(engine, AttributionEngine)
    return engine


def seal_backtest(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Run + seal one Phase 12 backtest into the shared sidecar, returning it.

    Uses the multi-period six-instant schedule by default so the sealed result carries
    five return observations. Any keyword overrides pass through to ``make_spec``.
    """
    kwargs.setdefault("schedule", SIX_INSTANTS)
    return corpus.backtest_engine.run(make_spec(corpus.backtest_engine, **kwargs))  # type: ignore[arg-type]


def seal_subject(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Seal the subject backtest: a top-1 *descending* strategy (holds filer B)."""
    kwargs.setdefault("rank", "descending")
    return seal_backtest(corpus, **kwargs)


def seal_factor(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Seal a factor backtest: a top-1 *ascending* strategy (holds filer A).

    A genuinely distinct return series from :func:`seal_subject` over the same schedule,
    so the regression is non-trivial while staying commensurable.
    """
    kwargs.setdefault("rank", "ascending")
    return seal_backtest(corpus, **kwargs)


def attribution_spec(
    subject_id: str,
    factor_ids: tuple[str, ...],
    *,
    name: str = "phase17-attribution",
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
) -> AttributionSpecification:
    """An attribution request over a sealed subject and ordered ``factor_ids``."""
    return AttributionSpecification(
        name=name,
        subject_id=subject_id,
        factor_ids=factor_ids,
        risk_free_per_period=risk_free_per_period,
        periods_per_year=periods_per_year,
    )
