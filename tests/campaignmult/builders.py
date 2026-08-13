"""Offline, obviously-synthetic fixtures for Phase 30 campaign-multiplicity tests.

Phase 30 is a pure consumer of exactly **one** already-sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation`: the engine reads only
each trial's ``label`` and its sealed ``psr`` cell, never the walk-forward /
optimization / risk-model / factor chain beneath it. So - like the MinTRL / calibration
builders, and unlike the campaign layer that must reconstruct a real chain - these
builders synthesize a ``ResearchCampaignEvaluation`` **directly** with hand-chosen
per-trial ``psr`` cells, seal it, and persist it to the shared sidecar. Every id / hash
the synthetic record pins is an obviously-fictional placeholder (Principle 8): Phase 30
pins the campaign by ``(id, result_hash)`` and never resolves anything beneath it, so
the placeholders are load-bearing for identity only, never dereferenced.

The per-trial helpers cover both classification branches (CM-3): a trial with a KNOWN
``psr`` (:func:`psr_trial`, joins the family) and a trial with an UNDEFINED ``psr``
(:func:`undefined_psr_trial`, a first-class exclusion). The other moment cells are inert
placeholders - Phase 30 reads none of them.
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
from quantforge.campaignmult.engine import CampaignMultiplicityEngine
from quantforge.campaignmult.model import CorrectionMethod
from quantforge.campaignmult.spec import CampaignMultiplicitySpecification
from quantforge.workspace import Workspace

__all__ = [
    "campaign_multiplicity_engine",
    "make_campaign",
    "make_spec",
    "psr_trial",
    "undefined_psr_trial",
    "workspace",
]


def workspace(root: Path) -> Workspace:
    """A fully-offline workspace rooted at ``root`` (no network, no seeded filers)."""
    return Workspace.open(root)


def campaign_multiplicity_engine(ws: Workspace) -> CampaignMultiplicityEngine:
    """The workspace's Phase 30 engine, narrowed from the ``object`` property."""
    engine = ws.campaign_multiplicity_engine
    assert isinstance(engine, CampaignMultiplicityEngine)
    return engine


def psr_trial(label: str, *, psr: str, n: int = 10) -> TrialStat:
    """A trial with a KNOWN ``psr`` cell (joins the family). Other moments inert."""
    return TrialStat(
        label=label,
        status=TrialStatus.VALID,
        n=n,
        sharpe=StatValue.known("0.5"),
        skew=StatValue.known("0"),
        kurtosis=StatValue.known("3"),
        psr=StatValue.known(psr),
    )


def undefined_psr_trial(
    label: str,
    *,
    reason: _Reason = _Reason.ZERO_OOS_VARIANCE,
    n: int = 5,
) -> TrialStat:
    """A trial whose ``psr`` cell is UNDEFINED (a first-class exclusion, CM-3)."""
    undefined = StatValue.undefined(reason)
    return TrialStat(
        label=label,
        status=TrialStatus.UNDEFINED,
        n=n,
        sharpe=undefined,
        skew=undefined,
        kurtosis=undefined,
        psr=undefined,
    )


def _summary() -> CampaignSummary:
    """An inert campaign summary; Phase 30 reads none of these cells."""
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
    sealed record (its ``research_result_id`` is what a Phase 30 request points at).
    Every reference the record pins is a fictional placeholder that Phase 30 never
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
    name: str = "phase30-campaignmult",
    alpha: str = "0.05",
    methods: tuple[CorrectionMethod, ...] | None = None,
) -> CampaignMultiplicitySpecification:
    """A campaign-multiplicity request over one sealed campaign id."""
    if methods is None:
        return CampaignMultiplicitySpecification(
            name=name, source_campaign_id=source_id, alpha=alpha
        )
    return CampaignMultiplicitySpecification(
        name=name, source_campaign_id=source_id, alpha=alpha, methods=methods
    )
