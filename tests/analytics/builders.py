"""Fixtures for Phase 15 analytics tests, reusing the Phase 12 combined corpus.

Phase 15 is a pure consumer of Phase 12: its tests need already-sealed
:class:`~quantforge.backtest.result.BacktestResult` artifacts to analyse, plus the
combined fundamentals + market corpus that produces them. This module re-exports the
Phase 12 ``populate`` / ``make_spec`` machinery and adds the small analytics-layer
helpers: a typed :class:`AnalyticsEngine` accessor over the populated workspace, a
multi-period corpus (the default corpus rebalances only twice, giving a single return —
below the two-observation floor every dispersion statistic needs), and seal helpers that
run + persist a subject / benchmark backtest and hand back a matching
:class:`AnalyticsSpecification`.

Everything stays fictional and offline (Principle 8) — the identities and bars come
straight from ``tests/backtest/builders`` (two made-up CIKs ``9999999991`` /
``9999999992``, round-number OHLC values, no network).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.analytics.engine import AnalyticsEngine
from quantforge.analytics.spec import AnalyticsSpecification
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
    "FOUR_INSTANTS",
    "Corpus",
    "analytics_engine",
    "analytics_spec",
    "make_spec",
    "multi_period_corpus",
    "populate",
    "seal_backtest",
    "seal_benchmark",
    "seal_subject",
]

# Four rebalance instants → three return observations, comfortably above the
# two-observation floor the analytics engine enforces.
_I1 = "2024-01-15T00:00:00Z"
_I2 = "2024-02-15T00:00:00Z"
_I3 = "2024-03-15T00:00:00Z"
_I4 = "2024-04-15T00:00:00Z"
FOUR_INSTANTS = RebalanceSchedule.of([_I1, _I2, _I3, _I4])

# Bars chosen so the two filers move differently period-to-period (so a strategy holding
# B is a genuinely distinct return series from one holding A — a real relative block):
# A closes 10 → 11 → 9 → 12; B closes 20 → 24 → 21 → 27.
_BARS_A = [
    bar("2024-01-10", close="10"),
    bar("2024-02-10", close="11"),
    bar("2024-03-10", close="9"),
    bar("2024-04-10", close="12"),
]
_BARS_B = [
    bar("2024-01-10", close="20"),
    bar("2024-02-10", close="24"),
    bar("2024-03-10", close="21"),
    bar("2024-04-10", close="27"),
]


def multi_period_corpus(root: Path) -> Corpus:
    """A populated corpus whose default four-instant schedule yields three returns."""
    return populate(root, bars_a=_BARS_A, bars_b=_BARS_B)


def analytics_engine(corpus: Corpus) -> AnalyticsEngine:
    """The workspace's Phase 15 engine, narrowed from the ``object`` property.

    :attr:`Workspace.analytics_engine` is typed ``object`` (to keep the engine import
    lazy and cycle-free); this asserts the concrete type once so every test reads a
    fully typed :class:`AnalyticsEngine`.
    """
    engine = corpus.workspace.analytics_engine
    assert isinstance(engine, AnalyticsEngine)
    return engine


def seal_backtest(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Run + seal one Phase 12 backtest into the shared sidecar, returning it.

    Uses the multi-period four-instant schedule by default so the sealed result carries
    three return observations. Any keyword overrides pass through to ``make_spec``.
    """
    kwargs.setdefault("schedule", FOUR_INSTANTS)
    return corpus.backtest_engine.run(make_spec(corpus.backtest_engine, **kwargs))  # type: ignore[arg-type]


def seal_subject(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Seal the subject backtest: a top-1 *descending* strategy (holds filer B)."""
    kwargs.setdefault("rank", "descending")
    return seal_backtest(corpus, **kwargs)


def seal_benchmark(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Seal the benchmark backtest: a top-1 *ascending* strategy (holds filer A).

    A genuinely distinct return series from :func:`seal_subject` over the same schedule,
    so the relative block is non-trivial while staying commensurable.
    """
    kwargs.setdefault("rank", "ascending")
    return seal_backtest(corpus, **kwargs)


def analytics_spec(
    subject_id: str,
    *,
    benchmark_id: str | None = None,
    name: str = "phase15-analytics",
    var_confidences: tuple[str, ...] = ("0.95",),
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
) -> AnalyticsSpecification:
    """An analytics request over a sealed ``subject_id`` (± ``benchmark_id``)."""
    return AnalyticsSpecification(
        name=name,
        subject_id=subject_id,
        benchmark_id=benchmark_id,
        var_confidences=var_confidences,
        risk_free_per_period=risk_free_per_period,
        periods_per_year=periods_per_year,
    )
