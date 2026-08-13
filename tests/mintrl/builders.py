"""Offline, obviously-synthetic fixtures for Phase 28 minimum-track-record-length tests.

Phase 28 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`: the engine reads only
each trial's ``status`` and its sealed ``sharpe`` / ``skew`` / ``kurtosis`` cells and
its ``n``, never the walk-forward / optimization / risk-model / factor chain beneath it.
So - like the calibration builders, and unlike the campaign layer that must reconstruct
a real chain - these builders synthesize a ``ResearchCampaignEvaluation`` **directly**
with hand-chosen per-trial statistic blocks, seal it, and persist it to the shared
sidecar. Every id / hash the synthetic record pins is an obviously-fictional placeholder
(Principle 8): Phase 28 pins the campaign by ``(id, result_hash)`` and never resolves
anything beneath it, so the placeholders are load-bearing for identity only, never
dereferenced.

The per-trial helpers cover every classification branch (MT-3): an evaluable trial
(:func:`valid_trial`), a whole-trial exclusion (:func:`undefined_trial`,
``TRIAL_UNDEFINED``), and the defensive guard - a VALID trial with a missing moment
(:func:`moments_undefined_trial`, ``MOMENTS_UNDEFINED``).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.campaign.model import CampaignUndefinedReason as _Reason
from quantforge.campaign.model import StatValue, TrialStatus
from quantforge.campaign.result import (
    CampaignSummary,
    ResearchCampaignEvaluation,
    TrialStat,
)
from quantforge.mintrl.engine import MinimumTrackRecordLengthEngine
from quantforge.mintrl.spec import MinimumTrackRecordLengthSpecification
from quantforge.workspace import Workspace

__all__ = [
    "make_campaign",
    "make_spec",
    "mintrl_engine",
    "moments_undefined_trial",
    "undefined_trial",
    "valid_trial",
    "workspace",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def mintrl_engine(ws: Workspace) -> MinimumTrackRecordLengthEngine:
    """The workspace's Phase 28 engine, narrowed from the ``object`` property."""
    engine = ws.mintrl_engine
    assert isinstance(engine, MinimumTrackRecordLengthEngine)
    return engine


def valid_trial(
    label: str,
    *,
    n: int,
    sharpe: str,
    skew: str,
    kurtosis: str,
    psr: str = "0.5",
) -> TrialStat:
    """An evaluable trial: VALID, all three moments KNOWN. ``psr`` is inert here."""
    return TrialStat(
        label=label,
        status=TrialStatus.VALID,
        n=n,
        sharpe=StatValue.known(sharpe),
        skew=StatValue.known(skew),
        kurtosis=StatValue.known(kurtosis),
        psr=StatValue.known(psr),
    )


def undefined_trial(label: str, *, n: int = 5) -> TrialStat:
    """A whole-trial exclusion: status UNDEFINED, every moment UNDEFINED."""
    undefined = StatValue.undefined(_Reason.ZERO_OOS_VARIANCE)
    return TrialStat(
        label=label,
        status=TrialStatus.UNDEFINED,
        n=n,
        sharpe=undefined,
        skew=undefined,
        kurtosis=undefined,
        psr=undefined,
    )


def moments_undefined_trial(label: str, *, n: int = 5) -> TrialStat:
    """Defensive: a VALID trial whose skew cell is UNDEFINED (structurally
    unreachable)."""
    return TrialStat(
        label=label,
        status=TrialStatus.VALID,
        n=n,
        sharpe=StatValue.known("0.5"),
        skew=StatValue.undefined(_Reason.ZERO_OOS_VARIANCE),
        kurtosis=StatValue.known("3"),
        psr=StatValue.known("0.5"),
    )


def _summary() -> CampaignSummary:
    """An inert campaign summary; Phase 28 reads none of these cells."""
    zero = StatValue.known("0")
    return CampaignSummary(
        valid_trials=0,
        selected_trial=None,
        selected_sharpe=zero,
        sharpe_dispersion=zero,
        expected_max_sharpe=zero,
        deflated_sharpe=zero,
    )


def make_campaign(
    ws: Workspace,
    *,
    trials: list[TrialStat],
    name: str = "synthetic-campaign",
    benchmark_sharpe: str = "0",
    engine_version_id: str = "sha256:synthetic-campaign-engine",
) -> ResearchCampaignEvaluation:
    """Seal a synthetic :class:`ResearchCampaignEvaluation` and persist it to the
    sidecar.

    ``trials`` are the sealed per-trial statistic blocks in source order. Returns the
    sealed record (its ``research_result_id`` is what a Phase 28 request points at).
    Every reference the record pins is a fictional placeholder that Phase 28 never
    dereferences.
    """
    trial_refs = tuple(
        (trial.label, f"sha256:trial-{i}", f"sha256:trial-hash-{i}")
        for i, trial in enumerate(trials)
    )
    evaluation = ResearchCampaignEvaluation.seal(
        campaign_engine_version_id=engine_version_id,
        campaign_spec={
            "spec_version": "campaign/1",
            "name": name,
            "benchmark_sharpe": benchmark_sharpe,
        },
        trial_refs=trial_refs,
        boundary_kind="pit",
        schedule_id="schedule-synthetic",
        factor_portfolio_engine_version_id="sha256:fpe",
        trials=tuple(trials),
        summary=_summary(),
        dataset_version_ids=("sha256:ds",),
        market_dataset_version_ids=("sha256:mkt",),
    )
    ws.research_result_store.write(evaluation)
    return evaluation


def make_spec(
    source_id: str,
    *,
    name: str = "phase28-mintrl",
    confidence: str = "0.95",
    benchmark_sharpe: str = "0",
) -> MinimumTrackRecordLengthSpecification:
    """A MinTRL request over one sealed campaign id."""
    return MinimumTrackRecordLengthSpecification(
        name=name,
        source_campaign_id=source_id,
        confidence=confidence,
        benchmark_sharpe=benchmark_sharpe,
    )
