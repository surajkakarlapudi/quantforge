"""Offline, obviously-synthetic fixtures for Phase 24 strategy-comparison tests.

Phase 24 is a pure consumer of an ordered set of already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` "strategies" - but unlike
the campaign layer (which reads only each trial's chained out-of-sample series and can
therefore be tested against a *synthesized* walk with a placeholder reference),
Phase 24 **reconstructs** each strategy's realized OOS return series by re-resolving its
transitive ``optimization -> risk model -> factor portfolios`` chain and recomputing the
complete-case date axis. So the whole chain must be present in the sidecar and the
reconstruction must reproduce the sealed record exactly.

These builders therefore run the **real** Phase 22 walk-forward engine over a real
Phase 19/20/21 chain (reusing :mod:`tests.walkforward.builders`) to produce genuine
sealed strategies whose reconstruction succeeds. Two strategies built from the *same*
factor return series (differing only by ``name``) seal distinct records with identical
OOS returns - the walk reads only the factors' return series, never their names - which
is exploited to exercise the zero-difference-variance path; strategies built from
different series overlap on the same dates with a defined paired difference; and a
strategy built over a disjoint date axis shares no OOS date, exercising the
insufficient-overlap path. Everything is fictional and offline (Principle 8).
"""

from __future__ import annotations

from quantforge.comparison.engine import StrategyComparisonEngine
from quantforge.comparison.spec import StrategyComparisonSpecification
from quantforge.walkforward.result import WalkForwardEvaluation
from quantforge.workspace import Workspace
from tests.walkforward.builders import (
    DATES,
    SERIES_A,
    SERIES_B,
    build_chain,
    make_wf_spec,
    wf_engine,
    workspace,
)

__all__ = [
    "DATES",
    "DATES_LATE",
    "SERIES_A",
    "SERIES_B",
    "SERIES_C",
    "SERIES_D",
    "comparison_engine",
    "comparison_spec",
    "make_strategy",
    "workspace",
]

# Two further independent 6-observation return series (no window of >= 3 observations is
# collinear, so every training span of at least three periods yields a positive-definite
# 2x2 covariance - a REALIZED window - exactly as SERIES_A / SERIES_B do). Used to build
# strategies whose OOS returns differ from the SERIES_A / SERIES_B strategy, so the
# paired difference has a defined non-zero variance.
SERIES_C: tuple[str, ...] = ("0.03", "-0.01", "0.02", "-0.02", "0.01", "-0.015")
SERIES_D: tuple[str, ...] = ("-0.01", "0.025", "-0.02", "0.03", "-0.015", "0.02")

# A disjoint six-instant axis (a full year later). Lexicographic order == time order,
# matching the schedule the real engine emits. A strategy built over this axis shares no
# calendar date with a strategy built over DATES, so their reconstructed OOS series
# never overlap (the insufficient-overlap path).
DATES_LATE: tuple[str, ...] = (
    "2021-01-31",
    "2021-02-28",
    "2021-03-31",
    "2021-04-30",
    "2021-05-31",
    "2021-06-30",
)


def comparison_engine(ws: Workspace) -> StrategyComparisonEngine:
    """The workspace's Phase 24 engine, narrowed from the ``object`` property."""
    engine = ws.comparison_engine
    assert isinstance(engine, StrategyComparisonEngine)
    return engine


def make_strategy(
    ws: Workspace,
    *,
    name: str,
    series: tuple[tuple[str | None, ...], ...] = (SERIES_A, SERIES_B),
    dates: tuple[str, ...] = DATES,
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
    schedule_id: str = "schedule-synthetic",
) -> WalkForwardEvaluation:
    """Seal one strategy by walking a real factor chain, persisted to the sidecar.

    Builds the full ``factors -> risk model -> optimization`` chain from ``series`` over
    ``dates`` (:func:`tests.walkforward.builders.build_chain`), then runs the real Phase
    22 walk-forward engine over it and returns the sealed
    :class:`~quantforge.walkforward.result.WalkForwardEvaluation`. Distinct ``name`` s
    yield distinct chains (hence distinct strategy ids); identical ``series`` under
    distinct names yield identical OOS returns (the walk reads only the return series).
    """
    optimization = build_chain(
        ws,
        series=series,
        dates=dates,
        risk_free_per_period=risk_free_per_period,
        periods_per_year=periods_per_year,
        schedule_id=schedule_id,
        name=name,
    )
    return wf_engine(ws).evaluate(
        make_wf_spec(optimization.research_result_id, name=name)
    )


def comparison_spec(
    walk_forward_ids: tuple[str, ...],
    *,
    name: str = "phase24-comparison",
) -> StrategyComparisonSpecification:
    """A strategy-comparison request over the given ordered sealed strategy ids."""
    return StrategyComparisonSpecification(
        name=name,
        walk_forward_ids=walk_forward_ids,
    )
