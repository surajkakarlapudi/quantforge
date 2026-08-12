"""The sealed campaign record round-trips and self-verifies its id (§9, §10)."""

from __future__ import annotations

import pytest

from quantforge.campaign.model import (
    CampaignUndefinedReason,
    StatStatus,
    StatValue,
    TrialStatus,
)
from quantforge.campaign.result import (
    BOUNDARY_PIT,
    CampaignSummary,
    ResearchCampaignEvaluation,
    TrialStat,
)


def _trial(label: str, sharpe: str) -> TrialStat:
    return TrialStat(
        label=label,
        status=TrialStatus.VALID,
        n=24,
        sharpe=StatValue.known(sharpe),
        skew=StatValue.known("0"),
        kurtosis=StatValue.known("3"),
        psr=StatValue.known("0.9"),
    )


def _summary() -> CampaignSummary:
    return CampaignSummary(
        valid_trials=2,
        selected_trial="trial_2",
        selected_sharpe=StatValue.known("0.9"),
        sharpe_dispersion=StatValue.known("0.1"),
        expected_max_sharpe=StatValue.known("0.4"),
        deflated_sharpe=StatValue.known("0.8"),
    )


def _sealed() -> ResearchCampaignEvaluation:
    return ResearchCampaignEvaluation.seal(
        campaign_engine_version_id="sha256:engine",
        campaign_spec={
            "spec_version": "campaign/1",
            "name": "campaign",
            "trial_ids": ["sha256:a", "sha256:b"],
            "benchmark_sharpe": "0",
        },
        trial_refs=(
            ("trial_1", "sha256:a", "sha256:ha"),
            ("trial_2", "sha256:b", "sha256:hb"),
        ),
        boundary_kind=BOUNDARY_PIT,
        schedule_id="schedule",
        factor_portfolio_engine_version_id="fpe/1",
        trials=(_trial("trial_1", "0.3"), _trial("trial_2", "0.9")),
        summary=_summary(),
        dataset_version_ids=("ds",),
        market_dataset_version_ids=("mkt",),
    )


def test_round_trips_byte_identically() -> None:
    record = _sealed()
    restored = ResearchCampaignEvaluation.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.result_hash == record.result_hash
    assert restored.campaign_id == record.campaign_id


def test_research_result_id_aliases_campaign_id() -> None:
    record = _sealed()
    assert record.research_result_id == record.campaign_id


def test_id_is_rederived_ignoring_tampered_stored_value() -> None:
    record = _sealed()
    payload = record.to_dict()
    payload["campaign_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = ResearchCampaignEvaluation.from_dict(payload)
    assert restored.campaign_id == record.campaign_id


def test_trial_ids_property_in_request_order() -> None:
    assert _sealed().trial_ids == ("sha256:a", "sha256:b")


def test_pin_mismatch_flagged_on_multiple_pins() -> None:
    record = _sealed()
    assert record.pin_mismatch is False
    multi = ResearchCampaignEvaluation.from_dict(
        {**record.to_dict(), "dataset_version_ids": ["ds1", "ds2"]}
    )
    assert multi.pin_mismatch is True


def test_undefined_summary_round_trips() -> None:
    reason = CampaignUndefinedReason.INSUFFICIENT_VALID_TRIALS
    cell = StatValue.undefined(reason)
    summary = CampaignSummary(
        valid_trials=1,
        selected_trial=None,
        selected_sharpe=cell,
        sharpe_dispersion=cell,
        expected_max_sharpe=cell,
        deflated_sharpe=cell,
    )
    restored = CampaignSummary.from_dict(summary.to_dict())
    assert restored == summary
    assert restored.selected_trial is None


def test_boundary_is_pit() -> None:
    assert _sealed().boundary_kind == "pit"
    assert BOUNDARY_PIT == "pit"


def test_stat_value_known_requires_value_without_reason() -> None:
    with pytest.raises(ValueError):
        StatValue(status=StatStatus.KNOWN, value=None)


def test_stat_value_undefined_requires_reason_without_value() -> None:
    with pytest.raises(ValueError):
        StatValue(status=StatStatus.UNDEFINED, value="0.1")


def test_stat_value_from_dict_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        StatValue.from_dict({"status": "undefined", "reason": "not_a_reason"})
