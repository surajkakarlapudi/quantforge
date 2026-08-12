"""End-to-end research-campaign evaluation through the engine (§6, CE-1..CE-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from quantforge.campaign.errors import (
    CampaignConfigurationError,
    CampaignConsistencyError,
)
from quantforge.campaign.model import CampaignUndefinedReason, TrialStatus
from quantforge.campaign.result import ResearchCampaignEvaluation
from tests.campaign.builders import (
    SERIES_HIGH,
    SERIES_LOW,
    SERIES_MID,
    campaign_engine,
    campaign_spec,
    make_trial,
    workspace,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``WalkForwardEvaluation`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-walk", "id": self.research_result_id}


def _three_trials(ws: object) -> tuple[str, str, str]:
    lo = make_trial(ws, name="lo", oos_returns=SERIES_LOW)  # type: ignore[arg-type]
    mid = make_trial(ws, name="mid", oos_returns=SERIES_MID)  # type: ignore[arg-type]
    hi = make_trial(ws, name="hi", oos_returns=SERIES_HIGH)  # type: ignore[arg-type]
    return lo.research_result_id, mid.research_result_id, hi.research_result_id


def test_happy_path_selects_greatest_sharpe(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    lo, mid, hi = _three_trials(ws)
    engine = campaign_engine(ws)
    result = engine.evaluate(campaign_spec((lo, mid, hi)))
    assert result.summary.valid_trials == 3
    # trial_3 is the HIGH-Sharpe series (request order lo, mid, hi).
    assert result.summary.selected_trial == "trial_3"
    assert result.summary.deflated_sharpe.value is not None
    assert result.summary.expected_max_sharpe.value is not None
    assert all(t.status is TrialStatus.VALID for t in result.trials)


def test_result_is_persisted_and_reproducible(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    lo, mid, hi = _three_trials(ws)
    engine = campaign_engine(ws)
    spec = campaign_spec((lo, mid, hi))
    first = engine.evaluate(spec)
    # Persisted to the shared sidecar under its own id.
    stored = ws.research_result_store.read_as(
        first.research_result_id, ResearchCampaignEvaluation.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()
    # Rebuilding the identical request is byte-identical (idempotent write).
    second = engine.evaluate(spec)
    assert second.research_result_id == first.research_result_id
    assert second.to_dict() == first.to_dict()


def test_trial_order_changes_the_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    lo, mid, hi = _three_trials(ws)
    engine = campaign_engine(ws)
    forward = engine.evaluate(campaign_spec((lo, mid, hi)))
    reversed_ = engine.evaluate(campaign_spec((hi, mid, lo)))
    assert forward.research_result_id != reversed_.research_result_id
    # Same selection (HIGH), different label position.
    assert reversed_.summary.selected_trial == "trial_1"


def test_benchmark_lowers_per_trial_psr(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    lo, mid, hi = _three_trials(ws)
    engine = campaign_engine(ws)
    zero = engine.evaluate(campaign_spec((lo, mid, hi), benchmark_sharpe="0"))
    high = engine.evaluate(
        campaign_spec((lo, mid, hi), benchmark_sharpe="1.0", name="bench")
    )
    from decimal import Decimal

    assert Decimal(high.trials[2].psr.value or "0") < Decimal(
        zero.trials[2].psr.value or "0"
    )


def test_non_spec_argument_raises(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_engine(ws)
    with pytest.raises(CampaignConfigurationError):
        engine.evaluate(object())  # type: ignore[arg-type]


def test_missing_trial_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    hi = make_trial(ws, name="hi", oos_returns=SERIES_HIGH)
    engine = campaign_engine(ws)
    spec = campaign_spec((hi.research_result_id, "sha256:does-not-exist"))
    with pytest.raises(CampaignConsistencyError):
        engine.evaluate(spec)


def test_non_walkforward_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    hi = make_trial(ws, name="hi", oos_returns=SERIES_HIGH)
    dummy = _DummyRecord(research_result_id="sha256:not-a-walk")
    ws.research_result_store.write(dummy)
    engine = campaign_engine(ws)
    spec = campaign_spec((hi.research_result_id, dummy.research_result_id))
    with pytest.raises(CampaignConsistencyError):
        engine.evaluate(spec)


def test_non_realized_trial_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    hi = make_trial(ws, name="hi", oos_returns=SERIES_HIGH)
    undef = make_trial(ws, name="undef", oos_returns=SERIES_MID, realized_windows=1)
    engine = campaign_engine(ws)
    spec = campaign_spec((hi.research_result_id, undef.research_result_id))
    with pytest.raises(CampaignConsistencyError):
        engine.evaluate(spec)


def test_incommensurable_schedule_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_trial(ws, name="a", oos_returns=SERIES_HIGH)
    b = make_trial(ws, name="b", oos_returns=SERIES_MID, schedule_id="other-schedule")
    engine = campaign_engine(ws)
    with pytest.raises(CampaignConsistencyError):
        engine.evaluate(campaign_spec((a.research_result_id, b.research_result_id)))


def test_incommensurable_factor_engine_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_trial(ws, name="a", oos_returns=SERIES_HIGH)
    b = make_trial(
        ws, name="b", oos_returns=SERIES_MID, factor_engine_version_id="other-fpe/1"
    )
    engine = campaign_engine(ws)
    with pytest.raises(CampaignConsistencyError):
        engine.evaluate(campaign_spec((a.research_result_id, b.research_result_id)))


def test_too_few_valid_trials_is_recorded_not_raised(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    # One valid trial, one zero-variance (undefined) trial: campaign is undefined.
    good = make_trial(ws, name="good", oos_returns=SERIES_HIGH)
    flat = make_trial(ws, name="flat", oos_returns=("0.03", "0.03", "0.03"))
    engine = campaign_engine(ws)
    result = engine.evaluate(
        campaign_spec((good.research_result_id, flat.research_result_id))
    )
    assert result.summary.selected_trial is None
    assert (
        result.summary.expected_max_sharpe.reason
        is CampaignUndefinedReason.INSUFFICIENT_VALID_TRIALS
    )
    # The undefined trial is recorded with its reason, never dropped.
    flat_stat = next(t for t in result.trials if t.label == "trial_2")
    assert flat_stat.status is TrialStatus.UNDEFINED
    assert flat_stat.sharpe.reason is CampaignUndefinedReason.ZERO_OOS_VARIANCE


def test_pins_are_unioned_across_trials(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_trial(ws, name="a", oos_returns=SERIES_HIGH, dataset_version_ids=("ds-1",))
    b = make_trial(ws, name="b", oos_returns=SERIES_MID, dataset_version_ids=("ds-2",))
    engine = campaign_engine(ws)
    result = engine.evaluate(
        campaign_spec((a.research_result_id, b.research_result_id))
    )
    assert result.dataset_version_ids == ("ds-1", "ds-2")
    assert result.pin_mismatch is True
