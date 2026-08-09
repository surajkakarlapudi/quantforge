"""The deterministic backtesting / research-simulation layer (Phase 12).

A declarative, content-addressed backtester that turns a
:class:`~quantforge.backtest.spec.BacktestSpecification` — never a callback or arbitrary
Python — plus a **pinned** PIT corpus into a sealed, reproducible
:class:`~quantforge.backtest.result.BacktestResult`. It composes the Phase 7/8/9/10/11
engines through their public ``*_as_of`` accessors and adds no new data-resolution
logic: Phase 5 already decided availability, Phase 7 the metric arithmetic, Phase 9 the
survivorship-free membership, Phase 11 the prices and corporate actions.

The four Phase 12 invariants (BT-1..BT-4) it enforces:

* **BT-1 corpus pinning** — both corpus snapshots (fundamentals ``dataset_version_id`` +
  market ``market_dataset_version_id``) are re-derived and verified before simulating; a
  mismatch fails closed.
* **BT-2 PIT-only strategy boundary** — the signal at each instant ``T`` is resolved
  through an :class:`~quantforge.backtest.context.AsOfContext` bound to ``T`` that
  exposes only ``Pit*`` results and no settable ``as_of``, so no future/revised
  value can enter a decision.
* **BT-3 engine-owned execution** — the strategy emits only
  :class:`~quantforge.backtest.result.TargetWeights`; the engine diffs them against
  holdings to generate orders, executes at the PIT close, and applies deterministic
  transaction costs.
* **BT-4 fail-closed simulation** — a data/simulation condition (an ``UNDEFINED``
  signal, no tradable security, a price not knowable at ``T``) is recorded in the
  ledger, never raised; only a configuration/consistency defect raises.

Public front door: :class:`~quantforge.backtest.engine.BacktestEngine`, reached via
``Workspace.backtest_engine``. Construct a request from
:class:`~quantforge.backtest.spec.BacktestSpecification` (with
:class:`~quantforge.backtest.spec.StrategySpecification`,
:class:`~quantforge.backtest.spec.CostModel`,
:class:`~quantforge.backtest.spec.AccountingPolicy`, and a
:class:`~quantforge.backtest.schedule.RebalanceSchedule`); the result is a
:class:`~quantforge.backtest.result.BacktestResult` (sealed by ``backtest_id`` /
``result_hash``) that persists write-once to the shared research sidecar.
"""

from __future__ import annotations

from quantforge.backtest.engine import BacktestEngine
from quantforge.backtest.result import (
    AppliedAction,
    BacktestResult,
    Fill,
    PerformanceSummary,
    RebalanceRecord,
    SignalRef,
    TargetWeights,
)
from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import (
    AccountingPolicy,
    BacktestSpecification,
    CostModel,
    StrategySpecification,
)
from quantforge.backtest.stats import PerformanceStatistics

__all__ = [
    "AccountingPolicy",
    "AppliedAction",
    "BacktestEngine",
    "BacktestResult",
    "BacktestSpecification",
    "CostModel",
    "Fill",
    "PerformanceStatistics",
    "PerformanceSummary",
    "RebalanceRecord",
    "RebalanceSchedule",
    "SignalRef",
    "StrategySpecification",
    "TargetWeights",
]
