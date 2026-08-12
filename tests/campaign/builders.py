"""Offline, obviously-synthetic fixtures for Phase 23 research-campaign tests.

The campaign engine is a pure consumer of an ordered set of already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` "trials" - from which it
reads only each trial's chained out-of-sample (OOS) return series, its inherited
``risk_free_per_period``, its roll-up ``status``, and the shared ``schedule_id`` /
``factor_portfolio_engine_version_id`` that make the trials commensurable. Rather than
run the full walk-forward chain (that path is proven end-to-end in
``tests/walkforward``), these builders **synthesize** a sealed
:class:`WalkForwardEvaluation` directly from a
hand-chosen OOS return series and persist it to a real
:class:`~quantforge.factors.store.ResearchResultStore` sidecar via the workspace. That
gives exact control over each trial's OOS Sharpe while still exercising the true
resolve -> verify -> commensurability -> estimate -> select -> deflate -> seal ->
persist path through the engine and the shared store.

Every synthesized record is a *valid* sealed record (its ``result_hash`` / id are the
real content hashes and it round-trips through its own ``from_dict``), so the engine's
fail-closed reference checks pass exactly as they would for engine-produced records. The
per-window blocks, summary, and realized variance the campaign never reads are honest
KNOWN placeholders (two REALIZED windows, so the roll-up ``status`` is REALIZED).
Everything is fictional and offline (Principle 8).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from quantforge.campaign.engine import ResearchCampaignEngine
from quantforge.campaign.spec import ResearchCampaignSpecification
from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.result import (
    BOUNDARY_PIT,
    WalkForwardEvaluation,
    WindowResult,
)
from quantforge.workspace import Workspace

__all__ = [
    "SERIES_HIGH",
    "SERIES_LOW",
    "SERIES_MID",
    "campaign_engine",
    "campaign_spec",
    "make_trial",
    "workspace",
]

# A synthetic producing-engine version + schedule the trials share (commensurability).
# The campaign carries these through to its sealed record; their exact strings are
# arbitrary but stable so re-builds reproduce identical ids.
_FPE_VERSION = "fpe-synthetic/1"
_SCHEDULE = "schedule-synthetic"

# Three OOS return series with distinctly ordered per-period Sharpe ratios (mean/vol):
# the HIGH series has the greatest Sharpe, LOW the least. Each has >= 2 periods and
# positive dispersion, so all three are VALID trials.
SERIES_HIGH: tuple[str, ...] = ("0.04", "0.05", "0.03", "0.06", "0.04")
SERIES_MID: tuple[str, ...] = ("0.02", "-0.01", "0.03", "0.00", "0.02")
SERIES_LOW: tuple[str, ...] = ("-0.02", "0.03", "-0.04", "0.01", "-0.03")


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def campaign_engine(ws: Workspace) -> ResearchCampaignEngine:
    """The workspace's Phase 23 engine, narrowed from the ``object`` property."""
    engine = ws.campaign_engine
    assert isinstance(engine, ResearchCampaignEngine)
    return engine


def _canonical(value: str) -> str:
    """The canonical decimal string of ``value`` (matches the sealing layers)."""
    return str(+Decimal(value))


def _placeholder_windows(realized: int) -> tuple[WindowResult, ...]:
    """Two placeholder windows, the first ``realized`` of them REALIZED.

    The campaign engine reads only the trial's roll-up ``status`` and top-level chained
    OOS series, not per-window detail; these windows exist solely to control whether the
    synthesized record rolls up to REALIZED (>= 2 REALIZED windows) or UNDEFINED.
    """
    known = StatValue.known("0")
    windows: list[WindowResult] = []
    for index in range(2):
        is_realized = index < realized
        windows.append(
            WindowResult(
                index=index,
                train_start=0,
                train_end=2 + index,
                test_start=2 + index,
                test_end=3 + index,
                status=WindowStatus.REALIZED if is_realized else WindowStatus.UNDEFINED,
                reason=(
                    None
                    if is_realized
                    else WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE
                ),
                weights=(
                    (StatValue.known("0.5"), StatValue.known("0.5"))
                    if is_realized
                    else ()
                ),
                predicted_variance=known,
                realized_variance=known,
                oos_returns=("0",) if is_realized else (),
            )
        )
    return tuple(windows)


def make_trial(
    ws: Workspace,
    *,
    name: str,
    oos_returns: tuple[str, ...],
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
    schedule_id: str = _SCHEDULE,
    factor_engine_version_id: str = _FPE_VERSION,
    dataset_version_ids: tuple[str, ...] = ("ds-synthetic",),
    market_dataset_version_ids: tuple[str, ...] = ("mkt-synthetic",),
    realized_windows: int = 2,
    write: bool = True,
) -> WalkForwardEvaluation:
    """Synthesize a sealed :class:`WalkForwardEvaluation` trial from an OOS return
    series.

    ``oos_returns`` is the chained out-of-sample series the campaign reads and
    summarizes; ``name`` distinguishes the trial (so distinct trials get distinct
    ids). The record carries two REALIZED placeholder windows so its roll-up
    ``status`` is REALIZED. Persisted to the workspace sidecar by default so the
    campaign engine can resolve it.
    """
    chained = tuple(_canonical(v) for v in oos_returns)
    zero = StatValue.known("0")
    summary = WalkForwardSummary(
        cumulative_return=zero,
        mean_period_return=zero,
        volatility=zero,
        annualized_sharpe=zero,
        mean_t_stat=zero,
        hit_rate=zero,
        n_valid_periods=len(chained),
    )
    spec_payload: dict[str, object] = {
        "spec_version": "walkforward/1",
        "name": name,
        "training_policy": {
            "window": "expanding",
            "min_train_periods": 2,
            "test_periods": 1,
        },
    }
    evaluation = WalkForwardEvaluation.seal(
        walk_forward_engine_version_id="wfe-synthetic/1",
        walk_forward_spec=spec_payload,
        optimization_ref=(f"sha256:opt-{name}", f"sha256:opthash-{name}"),
        boundary_kind=BOUNDARY_PIT,
        schedule_id=schedule_id,
        factor_portfolio_engine_version_id=factor_engine_version_id,
        n_factors=2,
        factor_labels=("factor_1", "factor_2"),
        periods_per_year=periods_per_year,
        risk_free_per_period=_canonical(risk_free_per_period),
        common_periods=len(chained) + 2,
        windows=_placeholder_windows(realized_windows),
        oos_returns=chained,
        summary=summary,
        realized_variance=StatValue.known("0"),
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )
    if write:
        ws.research_result_store.write(evaluation)
    return evaluation


def campaign_spec(
    trial_ids: tuple[str, ...],
    *,
    name: str = "phase23-campaign",
    benchmark_sharpe: str = "0",
) -> ResearchCampaignSpecification:
    """A research-campaign request over the given ordered sealed trial ids."""
    return ResearchCampaignSpecification(
        name=name,
        trial_ids=trial_ids,
        benchmark_sharpe=benchmark_sharpe,
    )
