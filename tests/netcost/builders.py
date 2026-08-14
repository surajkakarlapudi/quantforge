"""Offline, obviously-synthetic fixtures for Phase 31 net-of-cost tests.

Phase 31 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.stability.result.WalkForwardStability` and, transitively, the one
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` that stability record
pins. It reads only the walk's per-realized-window ``oos_returns`` (the gross series),
the walk's aggregate gross ``summary`` (consumed verbatim), the walk's annualization
conventions, and the stability record's per-window ``turnover_from_prev`` cells - never
the optimization / risk-model / factor chain beneath. So - like the calibration /
stability / multiplicity builders - these builders synthesize both sealed records
**directly** (with hand-chosen per-window gross returns and turnover), seal them, and
persist them to the shared sidecar. The walk's gross ``summary`` is computed with the
**genuine** reused Phase 19
:func:`~quantforge.factorportfolio.stats.series_summary` over the chained gross series,
so it is exactly the summary Phase 22 would have sealed (which
makes the zero-cost identity hold: at ``cost_rate == 0`` the net moments equal the gross
moments). Every id / hash a synthetic record pins is an obviously-fictional placeholder
(Principle 8): Phase 31 pins by ``(id, result_hash)`` and dereferences only the walk it
is handed, so the deeper placeholders are load-bearing for identity only, never
resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantforge.factorportfolio.model import FactorPortfolioStatus
from quantforge.factorportfolio.model import StatValue as FPStatValue
from quantforge.factorportfolio.stats import SeriesSummary, series_summary
from quantforge.netcost.engine import NetOfCostEngine
from quantforge.netcost.spec import NetOfCostSpecification
from quantforge.netcost.version import default_decimal_context
from quantforge.stability.model import (
    StabilityExcludedReason,
    StabilityStat,
    StabilityStatus,
    StabilityUndefinedReason,
)
from quantforge.stability.result import (
    ExcludedWindow,
    StabilityCoverage,
    StabilitySummary,
    WalkForwardStability,
    WindowStabilityCell,
)
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.result import WalkForwardEvaluation, WindowResult
from quantforge.workspace import Workspace

__all__ = [
    "Win",
    "excluded",
    "make_sources",
    "make_spec",
    "net_of_cost_engine",
    "realized",
    "workspace",
]

# A placeholder UNDEFINED reason for a whole-window exclusion in the walk; Phase 31 keys
# off ``status`` and the sealed indices, never this reason.
_WINDOW_REASON = WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE


@dataclass(frozen=True)
class Win:
    """One window of the synthetic schedule (a realized window or an exclusion).

    ``kind`` is ``"realized"`` or ``"excluded"``. A realized window carries its ordered
    per-period gross ``oos_returns`` and its one-way ``turnover`` (a decimal string, or
    ``None`` for no adjacent realized predecessor - ``NO_PRIOR_REALIZED_WINDOW``). An
    excluded window carries neither.
    """

    index: int
    kind: str
    oos_returns: tuple[str, ...] = ()
    turnover: str | None = None


def realized(index: int, oos_returns: list[str], turnover: str | None) -> Win:
    """A realized window: gross OOS returns + one-way turnover (``None`` = no prior)."""
    return Win(
        index=index,
        kind="realized",
        oos_returns=tuple(oos_returns),
        turnover=turnover,
    )


def excluded(index: int) -> Win:
    """A whole-window exclusion (the walk sealed it UNDEFINED)."""
    return Win(index=index, kind="excluded")


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def net_of_cost_engine(ws: Workspace) -> NetOfCostEngine:
    """The workspace's Phase 31 engine, narrowed from the ``object`` property."""
    engine = ws.net_of_cost_engine
    assert isinstance(engine, NetOfCostEngine)
    return engine


def _to_wf(cell: FPStatValue) -> StatValue:
    """Map a Phase 19 summary cell to the walk-forward cell type (same shape)."""
    if cell.status is FactorPortfolioStatus.KNOWN:
        assert cell.value is not None
        return StatValue.known(cell.value)
    assert cell.reason is not None
    return StatValue.undefined(WalkForwardUndefinedReason(cell.reason.value))


def _gross_summary(
    chained: list[str], *, risk_free_per_period: str, periods_per_year: str
) -> WalkForwardSummary:
    """The genuine gross summary Phase 22 would seal over the chained gross series."""
    summary: SeriesSummary = series_summary(
        chained,
        risk_free_per_period=risk_free_per_period,
        periods_per_year=periods_per_year,
        context=default_decimal_context(),
    )
    return WalkForwardSummary(
        cumulative_return=_to_wf(summary.cumulative_return),
        mean_period_return=_to_wf(summary.mean_period_return),
        volatility=_to_wf(summary.volatility),
        annualized_sharpe=_to_wf(summary.annualized_sharpe),
        mean_t_stat=_to_wf(summary.mean_t_stat),
        hit_rate=_to_wf(summary.hit_rate),
        n_valid_periods=summary.n_valid_periods,
    )


def _walk_window(win: Win) -> WindowResult:
    """One synthetic sealed walk window; train/test ranges are inert placeholders."""
    realized_ = win.kind == "realized"
    return WindowResult(
        index=win.index,
        train_start=win.index,
        train_end=win.index + 1,
        test_start=win.index + 1,
        test_end=win.index + 2,
        status=WindowStatus.REALIZED if realized_ else WindowStatus.UNDEFINED,
        reason=None if realized_ else _WINDOW_REASON,
        weights=(),
        predicted_variance=StatValue.known("1"),
        realized_variance=StatValue.known("1"),
        oos_returns=win.oos_returns,
    )


def _stability_cell(win: Win) -> WindowStabilityCell:
    """A realized window's stability cell; only ``turnover_from_prev`` is used."""
    if win.turnover is None:
        turnover = StabilityStat.undefined(
            StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
        )
    else:
        turnover = StabilityStat.known(win.turnover)
    return WindowStabilityCell(
        index=win.index,
        gross_leverage="1",
        concentration_hhi="1",
        effective_breadth=StabilityStat.known("1"),
        max_abs_weight="1",
        turnover_from_prev=turnover,
    )


def _stability_summary() -> StabilitySummary:
    """An inert aggregate stability summary; Phase 31 reads none of these cells."""
    zero = StabilityStat.known("0")
    return StabilitySummary(
        mean_turnover=zero,
        turnover_dispersion=zero,
        max_turnover=zero,
        min_turnover=zero,
        mean_gross_leverage=zero,
        max_gross_leverage=zero,
        mean_concentration_hhi=zero,
        mean_effective_breadth=zero,
        stability_status=StabilityStatus.STABLE,
    )


def make_sources(
    ws: Workspace,
    *,
    windows: list[Win],
    periods_per_year: str = "1",
    risk_free_per_period: str = "0",
    walk_name: str = "synthetic-walk",
    stability_name: str = "synthetic-stability",
    walk_engine_version_id: str = "sha256:synthetic-walk-engine",
    stability_engine_version_id: str = "sha256:synthetic-stability-engine",
) -> tuple[WalkForwardEvaluation, WalkForwardStability]:
    """Seal + persist a matched walk-forward / stability pair, returning both.

    ``windows`` is the full schedule in order (realized + excluded). Builds a genuine
    sealed walk (chained gross = concatenation of the realized windows' OOS returns; the
    gross summary computed with the real Phase 19 summary), then a genuine sealed
    stability record whose realized indices, excluded indices, and ``source_ref`` match
    the walk exactly - so the pair passes every Phase 31 alignment check.
    """
    walk_windows = tuple(_walk_window(w) for w in windows)
    realized_wins = [w for w in windows if w.kind == "realized"]
    excluded_wins = [w for w in windows if w.kind == "excluded"]
    chained: list[str] = []
    for w in realized_wins:
        chained.extend(w.oos_returns)

    walk = WalkForwardEvaluation.seal(
        walk_forward_engine_version_id=walk_engine_version_id,
        walk_forward_spec={
            "spec_version": "walkforward/1",
            "name": walk_name,
            "training_policy": {"kind": "expanding", "min_train": 1},
        },
        optimization_ref=("sha256:opt", "sha256:opt-hash"),
        boundary_kind="pit",
        schedule_id="schedule-synthetic",
        factor_portfolio_engine_version_id="sha256:fpe",
        n_factors=1,
        factor_labels=("factor_1",),
        periods_per_year=periods_per_year,
        risk_free_per_period=risk_free_per_period,
        common_periods=len(windows),
        windows=walk_windows,
        oos_returns=tuple(chained),
        summary=_gross_summary(
            chained,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
        ),
        realized_variance=StatValue.known("0"),
        dataset_version_ids=("sha256:ds",),
        market_dataset_version_ids=("sha256:mkt",),
    )
    ws.research_result_store.write(walk)

    stability = WalkForwardStability.seal(
        stability_engine_version_id=stability_engine_version_id,
        stability_spec={
            "spec_version": "stability/1",
            "name": stability_name,
            "source_walk_forward_id": walk.research_result_id,
        },
        source_ref=(walk.research_result_id, walk.result_hash),
        boundary_kind="pit",
        windows=tuple(_stability_cell(w) for w in realized_wins),
        excluded=tuple(
            ExcludedWindow(
                index=w.index, reason=StabilityExcludedReason.WINDOW_UNDEFINED
            )
            for w in excluded_wins
        ),
        summary=_stability_summary(),
        coverage=StabilityCoverage(
            n_windows=len(windows),
            n_realized=len(realized_wins),
            n_excluded=len(excluded_wins),
            n_transitions=sum(1 for w in realized_wins if w.turnover is not None),
        ),
    )
    ws.research_result_store.write(stability)
    return walk, stability


def make_spec(
    source_stability_id: str,
    *,
    cost_rate: str = "0.1",
    name: str = "phase31-netcost",
) -> NetOfCostSpecification:
    """A net-of-cost request over one sealed stability id at a declared cost rate."""
    return NetOfCostSpecification(
        name=name, source_stability_id=source_stability_id, cost_rate=cost_rate
    )
