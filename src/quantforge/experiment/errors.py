"""Exception hierarchy for the comparative-research layer (Phase 13, locked §6).

Rooted at :class:`ExperimentError` so a caller can catch every failure of this layer
with one type. Phase 13 is a *pure consumer* of Phase 12: it orchestrates
:meth:`~quantforge.backtest.engine.BacktestEngine.run` over a declarative sweep and
compares already-sealed :class:`~quantforge.backtest.result.BacktestResult`s. It
resolves no data at any ``T`` and re-derives nothing from source, so its only failures
are of the request or of a consistency invariant.

The governing posture mirrors Phase 12's split (locked §6):

* A **data / research condition** — a member whose ranking statistic is ``UNDEFINED``,
  a family whose members were built under different corpus pins — is **never** an
  exception. It is recorded as a first-class value (an ``excluded`` entry, a
  ``pin_mismatch`` flag) and surfaced, never guessed.
* A **configuration / consistency defect** — an axis parameter outside the closed v1
  vocabulary, an empty or duplicate-valued axis, two axes on one parameter, an unpinned
  base spec, an unknown ranking statistic, an ``order`` that is neither
  ``descending``/``ascending``, a member id absent from the sidecar, or members built
  under mixed engine versions — *is* raised. These are our bugs, surfaced rather than
  silently resolved. A raised error is always preferable to a wrong comparison.
"""

from __future__ import annotations

__all__ = [
    "ExperimentConfigurationError",
    "ExperimentConsistencyError",
    "ExperimentError",
]


class ExperimentError(Exception):
    """Base class for all comparative-research-layer errors."""


class ExperimentConfigurationError(ExperimentError):
    """An experiment or comparison request is internally inconsistent — our bug.

    Raised for a malformed
    :class:`~quantforge.experiment.spec.ExperimentSpecification` (an axis parameter
    outside the closed v1 vocabulary, an empty or duplicate-valued axis, two axes on
    the same parameter, an axis value of the wrong type, a base that is not a fully
    pinned :class:`~quantforge.backtest.spec.BacktestSpecification`) or a malformed
    :class:`~quantforge.experiment.analysis.BacktestComparison` request (a ranking
    statistic that is not a real performance-statistics field, an ``order`` other than
    ``descending``/``ascending``). We refuse to guess an experiment's intent, exactly
    as Phase 12 refuses a misconfigured backtest.
    """


class ExperimentConsistencyError(ExperimentError):
    """A comparison spans artifacts that cannot be honestly compared — surfaced.

    Fail-closed guard for the comparability contract (locked §6): a member
    ``backtest_id`` requested for comparison that is absent from the research sidecar,
    or a set of sealed results computed under *different*
    ``backtest_engine_version_id``s (their statistics are not commensurable), is a
    consistency violation and is raised — never silently compared. (A corpus-pin
    difference is *not* raised: it is surfaced as
    :attr:`~quantforge.experiment.analysis.BacktestComparison.pin_mismatch` and the
    comparison proceeds, exactly as ``UniverseComparison.mode_mismatch`` does.)
    """
