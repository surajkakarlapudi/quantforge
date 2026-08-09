"""Fixtures for Phase 14 reporting tests, reusing the Phase 12/13 combined corpus.

Phase 14 is a pure consumer of Phases 8-13, so its tests need exactly the Phase 12
combined corpus (fundamentals + market for the two synthetic filers A/B) plus the
already-sealed backtest / experiment artifacts a report is *about*. This module
re-exports the Phase 12/13 ``populate`` / spec machinery and adds the small
report-layer helpers: a typed :class:`ReportEngine` accessor over the populated
workspace, and helpers that seal a backtest / experiment into the shared sidecar and
hand back a matching :class:`ReportSpecification`. Everything stays fictional and
offline (Principle 8) — the identities and bars come straight from
``tests/backtest/builders``.
"""

from __future__ import annotations

from quantforge.backtest.result import BacktestResult
from quantforge.experiment.result import ExperimentResult
from quantforge.report.engine import ReportEngine
from quantforge.report.spec import ComparisonDirective, ReportSpecification
from tests.experiment.builders import (
    Corpus,
    base_spec,
    experiment_engine,
    populate,
    simple_experiment,
)

__all__ = [
    "Corpus",
    "backtest_report_spec",
    "base_spec",
    "experiment_report_spec",
    "populate",
    "report_engine",
    "seal_backtest",
    "seal_experiment",
    "simple_experiment",
]


def report_engine(corpus: Corpus) -> ReportEngine:
    """The workspace's Phase 14 engine, narrowed from the ``object`` property.

    :attr:`Workspace.report_engine` is typed ``object`` (to keep the engine import lazy
    and cycle-free); this asserts the concrete type once so every test reads a fully
    typed :class:`ReportEngine`.
    """
    engine = corpus.workspace.report_engine
    assert isinstance(engine, ReportEngine)
    return engine


def seal_backtest(corpus: Corpus, **kwargs: object) -> BacktestResult:
    """Run + seal one Phase 12 backtest into the shared sidecar, returning it."""
    return corpus.backtest_engine.run(base_spec(corpus, **kwargs))


def seal_experiment(
    corpus: Corpus, *, values: tuple[int, ...] = (1, 2)
) -> ExperimentResult:
    """Run + seal one Phase 13 experiment (and its children) into the sidecar."""
    return experiment_engine(corpus).run(simple_experiment(corpus, values=values))


def backtest_report_spec(
    subject_id: str, *, name: str = "phase14-backtest"
) -> ReportSpecification:
    """A single-backtest report request over an already-sealed ``subject_id``."""
    return ReportSpecification(name=name, scope="backtest", subject_id=subject_id)


def experiment_report_spec(
    subject_id: str,
    *,
    name: str = "phase14-experiment",
    comparisons: tuple[ComparisonDirective, ...] = (
        ComparisonDirective(statistic="final_equity"),
    ),
) -> ReportSpecification:
    """An experiment report request with optional comparison directives."""
    return ReportSpecification(
        name=name,
        scope="experiment",
        subject_id=subject_id,
        comparisons=comparisons,
    )
