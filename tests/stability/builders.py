"""Offline, obviously-synthetic fixtures for Phase 27 turnover & stability tests.

Phase 27 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation`: the engine reads only
each window's ``status`` and its sealed per-factor GMV ``weights`` vector, never the
optimization / risk-model / factor chain beneath it. So - like the calibration and
multiplicity builders, and unlike the walk-forward layer that must reconstruct a real
chain - these builders synthesize a ``WalkForwardEvaluation`` **directly** with
hand-chosen per-window weight vectors, seal it, and persist it to the shared sidecar.
Every id / hash the synthetic record pins is an obviously-fictional placeholder
(Principle 8): Phase 27 pins the walk by ``(id, result_hash)`` and never resolves
anything beneath it, so the placeholders are load-bearing for identity only, never
dereferenced.

The per-window helpers cover the classification branches (WS-2/WS-3/WS-4): a REALIZED
window carrying a KNOWN weight vector (:func:`realized_window`), a whole-window
exclusion (:func:`undefined_window`, ``WINDOW_UNDEFINED``), and the two corrupt-source
cases the engine must raise on - a REALIZED window whose weight vector is the wrong
length (:func:`wrong_length_window`) or carries a non-KNOWN cell
(:func:`non_known_weight_window`).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.stability.engine import WalkForwardStabilityEngine
from quantforge.stability.spec import WalkForwardStabilitySpecification
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.result import WalkForwardEvaluation, WindowResult
from quantforge.workspace import Workspace

__all__ = [
    "make_spec",
    "make_walk_forward",
    "non_known_weight_window",
    "realized_window",
    "stability_engine",
    "undefined_window",
    "workspace",
    "wrong_length_window",
]

# A placeholder UNDEFINED reason for a whole-window exclusion; Phase 27 never reads it
# (it keys off ``status`` and the weight vector), so any source reason is fine.
_WINDOW_REASON = WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def stability_engine(ws: Workspace) -> WalkForwardStabilityEngine:
    """The workspace's Phase 27 engine, narrowed from the ``object`` property."""
    engine = ws.stability_engine
    assert isinstance(engine, WalkForwardStabilityEngine)
    return engine


def _window(
    index: int,
    *,
    status: WindowStatus,
    weights: tuple[StatValue, ...],
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
        weights=weights,
        predicted_variance=StatValue.known("1"),
        realized_variance=StatValue.known("1"),
        oos_returns=(),
    )


def realized_window(index: int, weights: list[str]) -> WindowResult:
    """A REALIZED window carrying a KNOWN per-factor weight vector, in factor order."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        weights=tuple(StatValue.known(w) for w in weights),
    )


def undefined_window(index: int, n_factors: int) -> WindowResult:
    """A whole-window exclusion: status UNDEFINED, empty weight vector (Phase 22)."""
    return _window(index, status=WindowStatus.UNDEFINED, weights=())


def wrong_length_window(index: int, weights: list[str]) -> WindowResult:
    """A corrupt REALIZED window whose weight vector length is not ``n_factors``."""
    return _window(
        index,
        status=WindowStatus.REALIZED,
        weights=tuple(StatValue.known(w) for w in weights),
    )


def non_known_weight_window(index: int, n_factors: int) -> WindowResult:
    """A corrupt REALIZED window carrying a non-KNOWN cell in its weight vector."""
    cells = [StatValue.known("0.5")] * (n_factors - 1)
    cells.append(StatValue.undefined(_WINDOW_REASON))
    return _window(
        index,
        status=WindowStatus.REALIZED,
        weights=tuple(cells),
    )


def _summary() -> WalkForwardSummary:
    """An inert aggregate summary; Phase 27 reads none of these cells."""
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
    n_factors: int = 2,
    name: str = "synthetic-walk",
    engine_version_id: str = "sha256:synthetic-walk-engine",
) -> WalkForwardEvaluation:
    """Seal a synthetic :class:`WalkForwardEvaluation` and persist it to the sidecar.

    ``windows`` are the sealed windows in source order; ``n_factors`` is the constant
    factor count the walk declares (REALIZED windows must carry a KNOWN weight vector of
    this length). Returns the sealed record (its ``research_result_id`` is what a Phase
    27 request points at). Every reference the record pins is a fictional placeholder
    that Phase 27 never dereferences.
    """
    labels = tuple(f"factor_{i + 1}" for i in range(n_factors))
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
        n_factors=n_factors,
        factor_labels=labels,
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
    name: str = "phase27-stability",
) -> WalkForwardStabilitySpecification:
    """A stability request over one sealed walk-forward id."""
    return WalkForwardStabilitySpecification(
        name=name, source_walk_forward_id=source_id
    )
