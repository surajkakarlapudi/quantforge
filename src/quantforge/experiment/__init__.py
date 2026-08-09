"""Comparative research: declarative experiment sweeps + backtest comparison (Phase 13).

The layer strictly above Phase 12 (locked D1): it consumes already-sealed, PIT-correct
:class:`~quantforge.backtest.result.BacktestResult`s and never re-resolves data or
introduces new arithmetic or storage. Two capabilities, one package:

* **Experiment sweeps** — :class:`~quantforge.experiment.spec.ExperimentSpecification`
  (a declarative, content-addressed sweep over a base backtest, via
  :class:`~quantforge.experiment.spec.SweepAxis` on the closed v1 parameter vocabulary),
  run by :class:`~quantforge.experiment.engine.ExperimentEngine` into a sealed
  :class:`~quantforge.experiment.result.ExperimentResult` (a thin, reproducible index
  over the child backtests, persisted to the shared sidecar with no new store).
* **Backtest comparison** — :class:`~quantforge.experiment.analysis.BacktestComparison`
  ranks a set of sealed backtests (or an experiment's children) by a chosen performance
  statistic, fail-closed on incommensurable members and surfacing corpus
  ``pin_mismatch``.

Every identity is content-addressed (:mod:`quantforge.experiment.identity`) and every
value deterministically serializable; failures follow Phase 12's split
(:mod:`quantforge.experiment.errors`).
"""

from __future__ import annotations

from quantforge.experiment.analysis import (
    RANKABLE_STATISTICS,
    BacktestComparison,
    ComparisonEntry,
)
from quantforge.experiment.engine import ExperimentEngine
from quantforge.experiment.errors import (
    ExperimentConfigurationError,
    ExperimentConsistencyError,
    ExperimentError,
)
from quantforge.experiment.result import ExperimentResult, ExperimentRun
from quantforge.experiment.spec import (
    SWEEPABLE_PARAMETERS,
    ExperimentSpecification,
    SweepAxis,
)

__all__ = [
    "RANKABLE_STATISTICS",
    "SWEEPABLE_PARAMETERS",
    "BacktestComparison",
    "ComparisonEntry",
    "ExperimentConfigurationError",
    "ExperimentConsistencyError",
    "ExperimentEngine",
    "ExperimentError",
    "ExperimentResult",
    "ExperimentRun",
    "ExperimentSpecification",
    "SweepAxis",
]
