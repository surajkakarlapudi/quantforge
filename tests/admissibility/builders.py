"""Offline, obviously-synthetic fixtures for Phase 33 strategy-admissibility tests.

Phase 33 is a pure **multi-source** consumer of exactly three already-sealed ex-post
verdicts of one strategy: a
:class:`~quantforge.stability.result.WalkForwardStability` (the engine reads only its
``stability_status``), a :class:`~quantforge.calsig.result.CalibrationSignificance`
(only its ``significance_status`` + two-sided ``p_value`` cell), and a
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` (only its
``significance_status`` + one-sided ``p_value`` cell + ``edge_direction``) - never the
walk-forward / campaign chain beneath any of them. So - like the single-source consumer
builders - these builders synthesize each source record **directly** with a hand-chosen
summary, seal it, and persist it to the shared sidecar. Every id / hash each synthetic
record pins is an obviously-fictional placeholder (Principle 8): Phase 33 pins each
source by ``(id, result_hash)`` and never resolves anything beneath it, so the
placeholders are load-bearing for identity only, never dereferenced.

The helpers cover the decision branches (AD-2/AD-3): a STABLE / UNDEFINED book
(:func:`make_stability`); a TESTED calibration with a chosen two-sided p-value or an
UNDEFINED one (:func:`make_calibration_significance`); a TESTED net-of-cost edge with a
chosen one-sided p-value + direction or an UNDEFINED one
(:func:`make_net_significance`); and :func:`admissible_sources`, which seals a trio that
rolls up to ADMISSIBLE at the default ``alpha`` of ``0.05``.
"""

from __future__ import annotations

from pathlib import Path

from quantforge.admissibility.engine import AdmissibilityEngine
from quantforge.admissibility.spec import AdmissibilitySpecification
from quantforge.calsig.model import BiasDirection
from quantforge.calsig.model import SignificanceStat as CalStat
from quantforge.calsig.model import SignificanceStatus as CalStatus
from quantforge.calsig.model import SignificanceUndefinedReason as CalReason
from quantforge.calsig.result import (
    NULL_MEAN_RATIO,
    CalibrationSignificance,
)
from quantforge.calsig.result import SignificanceSummary as CalSummary
from quantforge.netcostsig.model import EdgeDirection
from quantforge.netcostsig.model import NetCostSigUndefinedReason as NetReason
from quantforge.netcostsig.model import SignificanceStat as NetStat
from quantforge.netcostsig.model import SignificanceStatus as NetStatus
from quantforge.netcostsig.result import (
    NULL_MEAN_RETURN,
    NetOfCostSignificance,
)
from quantforge.netcostsig.result import SignificanceSummary as NetSummary
from quantforge.stability.model import (
    StabilityStat,
    StabilityStatus,
    StabilityUndefinedReason,
)
from quantforge.stability.result import (
    StabilityCoverage,
    StabilitySummary,
    WalkForwardStability,
)
from quantforge.workspace import Workspace

__all__ = [
    "admissibility_engine",
    "admissible_sources",
    "make_calibration_significance",
    "make_net_significance",
    "make_spec",
    "make_stability",
    "workspace",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def admissibility_engine(ws: Workspace) -> AdmissibilityEngine:
    """The workspace's Phase 33 engine, narrowed from the ``object`` property."""
    engine = ws.admissibility_engine
    assert isinstance(engine, AdmissibilityEngine)
    return engine


# -- source: walk-forward stability (Phase 27) -------------------------------


def _stability_summary(status: StabilityStatus) -> StabilitySummary:
    """A summary whose ``stability_status`` is the only cell Phase 33 reads.

    The eight turnover / concentration cells are inert placeholders (KNOWN for a STABLE
    book, UNDEFINED for an undefined one); Phase 33 never reads them.
    """
    if status is StabilityStatus.STABLE:
        cell = StabilityStat.known("0")
        return StabilitySummary(
            mean_turnover=cell,
            turnover_dispersion=cell,
            max_turnover=cell,
            min_turnover=cell,
            mean_gross_leverage=cell,
            max_gross_leverage=cell,
            mean_concentration_hhi=cell,
            mean_effective_breadth=cell,
            stability_status=status,
        )
    reason = StabilityUndefinedReason.INSUFFICIENT_TRANSITIONS
    undefined = StabilityStat.undefined(reason)
    return StabilitySummary(
        mean_turnover=undefined,
        turnover_dispersion=undefined,
        max_turnover=undefined,
        min_turnover=undefined,
        mean_gross_leverage=undefined,
        max_gross_leverage=undefined,
        mean_concentration_hhi=undefined,
        mean_effective_breadth=undefined,
        stability_status=status,
        status_reason=reason,
    )


def make_stability(
    ws: Workspace,
    *,
    stable: bool,
    name: str = "synthetic-stability",
    engine_version_id: str = "sha256:synthetic-stability-engine",
) -> WalkForwardStability:
    """Seal a synthetic :class:`WalkForwardStability` and persist it to the sidecar.

    ``stable`` chooses the ``stability_status`` (STABLE vs UNDEFINED) - the only field
    Phase 33 reads. Every reference the record pins is a fictional placeholder that
    Phase 33 never dereferences.
    """
    status = StabilityStatus.STABLE if stable else StabilityStatus.UNDEFINED
    coverage = StabilityCoverage(
        n_windows=3, n_realized=3, n_excluded=0, n_transitions=2
    )
    record = WalkForwardStability.seal(
        stability_engine_version_id=engine_version_id,
        stability_spec={
            "spec_version": "stability/1",
            "name": name,
            "source_walk_forward_id": "sha256:walk",
        },
        source_ref=("sha256:walk", "sha256:walk-hash"),
        boundary_kind="pit",
        windows=(),
        excluded=(),
        summary=_stability_summary(status),
        coverage=coverage,
    )
    ws.research_result_store.write(record)
    return record


# -- source: calibration significance (Phase 29) -----------------------------


def make_calibration_significance(
    ws: Workspace,
    *,
    tested: bool,
    p_value: str = "0.5",
    name: str = "synthetic-calsig",
    engine_version_id: str = "sha256:synthetic-calsig-engine",
) -> CalibrationSignificance:
    """Seal a synthetic :class:`CalibrationSignificance` and persist it to the sidecar.

    A TESTED source carries a KNOWN two-sided ``p_value`` (Phase 33 PASSes calibration
    iff ``p > alpha``); an untested source is UNDEFINED (Phase 33's criterion is
    UNDEFINED). Every reference the record pins is a fictional placeholder.
    """
    if tested:
        summary = CalSummary(
            mean_variance_ratio=CalStat.known("1.1"),
            null_mean_ratio=NULL_MEAN_RATIO,
            n_calibratable=4,
            standard_error=CalStat.known("0.05"),
            t_statistic=CalStat.known("2"),
            p_value=CalStat.known(p_value),
            significance_status=CalStatus.TESTED,
            bias_direction=BiasDirection.UNDER_FORECAST,
        )
    else:
        reason = CalReason.SOURCE_NOT_CALIBRATED
        undefined = CalStat.undefined(reason)
        summary = CalSummary(
            mean_variance_ratio=undefined,
            null_mean_ratio=NULL_MEAN_RATIO,
            n_calibratable=0,
            standard_error=undefined,
            t_statistic=undefined,
            p_value=undefined,
            significance_status=CalStatus.UNDEFINED,
            status_reason=reason,
        )
    record = CalibrationSignificance.seal(
        calibration_significance_engine_version_id=engine_version_id,
        calibration_significance_spec={
            "spec_version": "calsig/1",
            "name": name,
            "source_calibration_id": "sha256:cal",
        },
        source_ref=("sha256:cal", "sha256:cal-hash"),
        boundary_kind="pit",
        summary=summary,
    )
    ws.research_result_store.write(record)
    return record


# -- source: net-of-cost significance (Phase 32) -----------------------------


def make_net_significance(
    ws: Workspace,
    *,
    tested: bool,
    p_value: str = "0.01",
    direction: EdgeDirection = EdgeDirection.PROFITABLE,
    name: str = "synthetic-netsig",
    engine_version_id: str = "sha256:synthetic-netsig-engine",
) -> NetOfCostSignificance:
    """Seal a synthetic :class:`NetOfCostSignificance` and persist it to the sidecar.

    A TESTED source carries a KNOWN one-sided ``p_value`` + ``edge_direction`` (Phase 33
    PASSes the edge iff ``p <= alpha`` **and** PROFITABLE); an untested source is
    UNDEFINED. Every reference the record pins is a fictional placeholder.
    """
    if tested:
        summary = NetSummary(
            net_mean=NetStat.known("0.01"),
            null_mean_return=NULL_MEAN_RETURN,
            n_periods=100,
            standard_error=NetStat.known("0.005"),
            t_statistic=NetStat.known("2"),
            p_value=NetStat.known(p_value),
            significance_status=NetStatus.TESTED,
            edge_direction=direction,
        )
    else:
        reason = NetReason.SOURCE_NOT_MEASURED
        undefined = NetStat.undefined(reason)
        summary = NetSummary(
            net_mean=undefined,
            null_mean_return=NULL_MEAN_RETURN,
            n_periods=0,
            standard_error=undefined,
            t_statistic=undefined,
            p_value=undefined,
            significance_status=NetStatus.UNDEFINED,
            status_reason=reason,
        )
    record = NetOfCostSignificance.seal(
        net_of_cost_significance_engine_version_id=engine_version_id,
        net_of_cost_significance_spec={
            "spec_version": "netcostsig/1",
            "name": name,
            "source_net_of_cost_id": "sha256:nc",
        },
        source_ref=("sha256:nc", "sha256:nc-hash"),
        boundary_kind="pit",
        summary=summary,
    )
    ws.research_result_store.write(record)
    return record


# -- request + convenience trio ----------------------------------------------


def make_spec(
    stability_id: str,
    calibration_id: str,
    net_id: str,
    *,
    name: str = "phase33-admissibility",
    alpha: str = "0.05",
) -> AdmissibilitySpecification:
    """An admissibility request over the three sealed source ids."""
    return AdmissibilitySpecification(
        name=name,
        source_stability_id=stability_id,
        source_calibration_significance_id=calibration_id,
        source_net_of_cost_significance_id=net_id,
        alpha=alpha,
    )


def admissible_sources(ws: Workspace) -> tuple[str, str, str]:
    """Seal a trio that rolls up to ADMISSIBLE at the default ``alpha`` (``0.05``).

    STABLE book; calibration p ``0.5 > 0.05`` (not significantly mis-calibrated); net
    edge p ``0.01 <= 0.05`` and PROFITABLE (significantly positive after costs). Returns
    the three ``research_result_id`` values in (stability, calibration, net) order.
    """
    stability = make_stability(ws, stable=True)
    calibration = make_calibration_significance(ws, tested=True, p_value="0.5")
    net = make_net_significance(
        ws, tested=True, p_value="0.01", direction=EdgeDirection.PROFITABLE
    )
    return (
        stability.research_result_id,
        calibration.research_result_id,
        net.research_result_id,
    )
