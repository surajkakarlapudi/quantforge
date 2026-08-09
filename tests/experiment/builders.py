"""Fixtures for Phase 13 comparative-research tests, reusing the Phase 12 corpus.

Phase 13 is a pure consumer of Phase 12, so its tests need exactly the Phase 12
combined corpus (fundamentals + market for the two synthetic filers A/B) and nothing
new. This module re-exports the Phase 12 ``populate`` / ``make_spec`` machinery and adds
the small experiment-layer helpers: a typed :class:`ExperimentEngine` accessor over the
populated workspace, and a base-spec + axis builder. Everything stays fictional and
offline (Principle 8) — the identities and bars come straight from
``tests/backtest/builders``.
"""

from __future__ import annotations

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import BacktestSpecification
from quantforge.experiment.engine import ExperimentEngine
from quantforge.experiment.spec import ExperimentSpecification, SweepAxis
from tests.backtest.builders import (
    CIK_A,
    CIK_B,
    INSTANT_1,
    INSTANT_2,
    PERIOD,
    SECURITY_A,
    SECURITY_B,
    Corpus,
    make_spec,
    populate,
)

__all__ = [
    "CIK_A",
    "CIK_B",
    "INSTANT_1",
    "INSTANT_2",
    "PERIOD",
    "SECURITY_A",
    "SECURITY_B",
    "Corpus",
    "alt_schedule",
    "base_spec",
    "experiment_engine",
    "make_spec",
    "populate",
    "select_n_axis",
    "simple_experiment",
]


def experiment_engine(corpus: Corpus) -> ExperimentEngine:
    """The workspace's Phase 13 engine, narrowed from the ``object`` property.

    :attr:`Workspace.experiment_engine` is typed ``object`` (to keep the engine import
    lazy and cycle-free); this asserts the concrete type once so every test reads a
    fully typed :class:`ExperimentEngine`.
    """
    engine = corpus.workspace.experiment_engine
    assert isinstance(engine, ExperimentEngine)
    return engine


def base_spec(corpus: Corpus, **kwargs: object) -> BacktestSpecification:
    """A fully pinned base :class:`BacktestSpecification` over the populated corpus."""
    return make_spec(corpus.backtest_engine, **kwargs)  # type: ignore[arg-type]


def select_n_axis(*values: int) -> SweepAxis:
    """A ``select_n`` sweep axis over the given positive ints (defaults ``1, 2``)."""
    return SweepAxis("select_n", values or (1, 2))


def alt_schedule() -> RebalanceSchedule:
    """A single-instant schedule (distinct id from the default two-instant schedule)."""
    return RebalanceSchedule.of([INSTANT_1])


def simple_experiment(
    corpus: Corpus, *, values: tuple[int, ...] = (1, 2)
) -> ExperimentSpecification:
    """A one-axis ``select_n`` sweep over the default base spec (the common fixture)."""
    return ExperimentSpecification(
        name="phase13-synthetic",
        base=base_spec(corpus),
        axes=(select_n_axis(*values),),
    )
