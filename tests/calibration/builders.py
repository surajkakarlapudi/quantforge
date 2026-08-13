"""Offline, obviously-synthetic fixtures for Phase 26 calibration tests.

Phase 26 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`: the engine reads only
each window's ``status`` and its sealed ``predicted_variance`` / ``realized_variance``
cells, never the optimization / risk-model / factor chain beneath it. So - like the
multiplicity builders, and unlike the walk-forward layer that must reconstruct a real
chain - these builders synthesize a ``WalkForwardEvaluation`` **directly** with
hand-chosen per-window variance cells, seal it, and persist it to the shared sidecar.
Every id / hash the synthetic record pins is an obviously-fictional placeholder
(Principle 8): Phase 26 pins the walk by ``(id, result_hash)`` and never resolves
anything beneath it, so the placeholders are load-bearing for identity only, never
dereferenced.

The per-window helpers cover every classification branch (RC-3): a calibratable window
(:func:`realized_window`), a whole-window exclusion (:func:`undefined_window`,
``WINDOW_UNDEFINED``), a REALIZED window with an UNDEFINED realized variance
(:func:`single_period_window`, ``SINGLE_VALID_PERIOD``), and the two defensive guards -
a non-positive predicted variance (:func:`zero_predicted_window`,
``ZERO_PREDICTED_VARIANCE``) and an UNDEFINED predicted variance
(:func:`predicted_undefined_window`, ``PREDICTED_VARIANCE_UNDEFINED``).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.calibration.engine import RiskForecastCalibrationEngine
from quantforge.calibration.spec import RiskForecastCalibrationSpecification
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.result import WalkForwardEvaluation, WindowResult
from quantforge.workspace import Workspace

__all__ = [
    "calibration_engine",
    "make_spec",
    "make_walk_forward",
    "predicted_undefined_window",
    "realized_window",
    "single_period_window",
    "undefined_window",
    "workspace",
    "zero_predicted_window",
]

# A placeholder UNDEFINED reason for a whole-window exclusion; Phase 26 never reads it
# (it keys off ``status`` and the variance cells), so any source reason is fine.
_WINDOW_REASON = WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def calibration_engine(ws: Workspace) -> RiskForecastCalibrationEngine:
    """The workspace's Phase 26 engine, narrowed from the ``object`` property."""
    engine = ws.risk_calibration_engine
    assert isinstance(engine, RiskForecastCalibrationEngine)
    return engine


def _window(
    index: int,
    *,
    status: WindowStatus,
    predicted: StatValue,
    realized: StatValue,
) -> WindowResult:
    """One synthetic sealed window; the train/test ranges are inert placeholders."""
    return WindowResult(
        index=index,
        train_start=index,
        train_end=index + 1,
        test_start=index + 1,
        test_end=index + 2,
        status=status,
        reason=None if status is WindowStatus.REALIZED else _WINDOW_REASON,
        weights=(),
        predicted_variance=predicted,
        realized_variance=realized,
        oos_returns=(),
    )


def realized_window(index: int, predicted: str, realized: str) -> WindowResult:
    """A calibratable window: REALIZED, KNOWN positive predicted, KNOWN realized."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        predicted=StatValue.known(predicted),
        realized=StatValue.known(realized),
    )


def single_period_window(index: int, predicted: str) -> WindowResult:
    """A REALIZED window whose realized variance is UNDEFINED (SINGLE_VALID_PERIOD)."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        predicted=StatValue.known(predicted),
        realized=StatValue.undefined(WalkForwardUndefinedReason.SINGLE_VALID_PERIOD),
    )


def undefined_window(index: int) -> WindowResult:
    """A whole-window exclusion: status UNDEFINED, both variances UNDEFINED."""
    undefined = StatValue.undefined(_WINDOW_REASON)
    return _window(
        index,
        status=WindowStatus.UNDEFINED,
        predicted=undefined,
        realized=undefined,
    )


def zero_predicted_window(index: int, realized: str) -> WindowResult:
    """Defensive: a REALIZED window whose predicted variance is zero (non-positive)."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        predicted=StatValue.known("0"),
        realized=StatValue.known(realized),
    )


def predicted_undefined_window(index: int, realized: str) -> WindowResult:
    """Defensive: a REALIZED window whose predicted variance is UNDEFINED."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        predicted=StatValue.undefined(_WINDOW_REASON),
        realized=StatValue.known(realized),
    )


def _summary() -> WalkForwardSummary:
    """An inert aggregate summary; Phase 26 reads none of these cells."""
    zero = StatValue.known("0")
    return WalkForwardSummary(
        cumulative_return=zero,
        mean_period_return=zero,
        volatility=zero,
        annualized_sharpe=zero,
        mean_t_stat=zero,
        hit_rate=zero,
        n_valid_periods=0,
    )


def make_walk_forward(
    ws: Workspace,
    *,
    windows: list[WindowResult],
    name: str = "synthetic-walk",
    engine_version_id: str = "sha256:synthetic-walk-engine",
) -> WalkForwardEvaluation:
    """Seal a synthetic :class:`WalkForwardEvaluation` and persist it to the sidecar.

    ``windows`` are the sealed windows in source order. Returns the sealed record (its
    ``research_result_id`` is what a Phase 26 request points at). Every reference the
    record pins is a fictional placeholder that Phase 26 never dereferences.
    """
    evaluation = WalkForwardEvaluation.seal(
        walk_forward_engine_version_id=engine_version_id,
        walk_forward_spec={
            "spec_version": "walkforward/1",
            "name": name,
            "training_policy": {"kind": "expanding", "min_train": 1},
        },
        optimization_ref=("sha256:opt", "sha256:opt-hash"),
        boundary_kind="pit",
        schedule_id="schedule-synthetic",
        factor_portfolio_engine_version_id="sha256:fpe",
        n_factors=1,
        factor_labels=("factor_1",),
        periods_per_year="1",
        risk_free_per_period="0",
        common_periods=len(windows),
        windows=tuple(windows),
        oos_returns=(),
        summary=_summary(),
        realized_variance=StatValue.known("0"),
        dataset_version_ids=("sha256:ds",),
        market_dataset_version_ids=("sha256:mkt",),
    )
    ws.research_result_store.write(evaluation)
    return evaluation


def make_spec(
    source_id: str,
    *,
    name: str = "phase26-calibration",
) -> RiskForecastCalibrationSpecification:
    """A calibration request over one sealed walk-forward id."""
    return RiskForecastCalibrationSpecification(
        name=name, source_walk_forward_id=source_id
    )
