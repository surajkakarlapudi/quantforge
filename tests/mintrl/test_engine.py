"""End-to-end minimum-track-record-length through the engine (§6, MT-1..MT-6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from quantforge.campaign.result import TrialStat
from quantforge.factors.errors import FactorConsistencyError
from quantforge.mintrl.errors import (
    MinTrlConfigurationError,
    MinTrlConsistencyError,
)
from quantforge.mintrl.model import (
    MinTrlExcludedReason,
    MinTrlStatus,
    StatStatus,
)
from quantforge.mintrl.result import MinimumTrackRecordLength
from tests.mintrl.builders import (
    make_campaign,
    make_spec,
    mintrl_engine,
    moments_undefined_trial,
    undefined_trial,
    valid_trial,
    workspace,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``ResearchCampaignEvaluation`` :class:`ResearchRecord` for fail-closed
    tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-campaign", "id": self.research_result_id}


def _v(label: str, *, n: int, sharpe: str) -> TrialStat:
    return valid_trial(label, n=n, sharpe=sharpe, skew="0", kurtosis="3")


# -- happy path (MT-2/MT-4/MT-5) ---------------------------------------------


def test_happy_path_evaluates_full_family(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(
        ws,
        trials=[
            valid_trial("trial_1", n=100, sharpe="0.5", skew="0", kurtosis="3"),
            valid_trial("trial_2", n=100, sharpe="0.3", skew="0", kurtosis="3"),
        ],
    )
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))

    assert isinstance(result, MinimumTrackRecordLength)
    assert result.mintrl_status is MinTrlStatus.EVALUATED
    assert result.coverage.n_trials == 2
    assert result.coverage.n_evaluable == 2
    assert result.coverage.n_excluded == 0
    assert result.summary.n_determined == 2
    # Per-trial cells map back to source order by label.
    assert [c.label for c in result.trials] == ["trial_1", "trial_2"]
    for cell in result.trials:
        assert cell.min_track_record_length.status is StatStatus.KNOWN


def test_source_reference_is_pinned(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))
    assert result.source_campaign_id == campaign.research_result_id
    assert result.source_result_hash == campaign.result_hash


# -- trial classification / exclusion (MT-3) ---------------------------------


def test_every_exclusion_reason_is_classified(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(
        ws,
        trials=[
            valid_trial("trial_1", n=100, sharpe="0.5", skew="0", kurtosis="3"),
            undefined_trial("trial_2"),  # TRIAL_UNDEFINED
            moments_undefined_trial("trial_3"),  # MOMENTS_UNDEFINED (defensive)
        ],
    )
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))

    assert result.coverage.n_trials == 3
    assert result.coverage.n_evaluable == 1
    assert result.coverage.n_excluded == 2
    by_label = {e.label: e.reason for e in result.excluded}
    assert by_label == {
        "trial_2": MinTrlExcludedReason.TRIAL_UNDEFINED,
        "trial_3": MinTrlExcludedReason.MOMENTS_UNDEFINED,
    }
    # Below the floor of 2 determined: the record still seals, status UNDEFINED.
    assert result.mintrl_status is MinTrlStatus.UNDEFINED


def test_all_undefined_family_is_empty(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(
        ws, trials=[undefined_trial("trial_1"), undefined_trial("trial_2")]
    )
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))
    assert result.coverage.n_evaluable == 0
    assert result.trials == ()
    assert result.mintrl_status is MinTrlStatus.UNDEFINED
    # Every aggregate is UNDEFINED, never a divide-by-zero.
    assert result.summary.mean_min_trl.status is StatStatus.UNDEFINED


def test_boundary_is_carried_and_record_is_not_pit(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))
    assert result.boundary_kind == campaign.boundary_kind == "pit"
    assert not hasattr(result, "as_of")


# -- request parameters flow through (confidence / benchmark) ----------------


def test_confidence_changes_the_answer_and_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(
        ws,
        trials=[
            valid_trial("trial_1", n=100, sharpe="0.5", skew="0", kurtosis="3"),
            valid_trial("trial_2", n=100, sharpe="0.3", skew="0", kurtosis="3"),
        ],
    )
    engine = mintrl_engine(ws)
    lo = engine.evaluate(make_spec(campaign.research_result_id, confidence="0.90"))
    hi = engine.evaluate(make_spec(campaign.research_result_id, confidence="0.99"))
    assert lo.minimum_track_record_length_id != hi.minimum_track_record_length_id
    # A higher confidence demands a longer track record.
    assert Decimal(hi.summary.mean_min_trl.value or "0") > Decimal(
        lo.summary.mean_min_trl.value or "0"
    )


def test_benchmark_changes_the_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    engine = mintrl_engine(ws)
    a = engine.evaluate(make_spec(campaign.research_result_id, benchmark_sharpe="0"))
    b = engine.evaluate(make_spec(campaign.research_result_id, benchmark_sharpe="0.1"))
    assert a.minimum_track_record_length_id != b.minimum_track_record_length_id


# -- determinism & persistence -----------------------------------------------


def test_recompute_is_byte_identical_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(
        ws,
        trials=[
            _v("trial_1", n=100, sharpe="0.5"),
            _v("trial_2", n=100, sharpe="0.3"),
        ],
    )
    engine = mintrl_engine(ws)
    first = engine.evaluate(make_spec(campaign.research_result_id))
    second = engine.evaluate(make_spec(campaign.research_result_id))
    assert first.minimum_track_record_length_id == second.minimum_track_record_length_id
    assert first.to_dict() == second.to_dict()
    stored = ws.research_result_store.read_as(
        first.research_result_id, MinimumTrackRecordLength.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()


# -- identity sensitivity ----------------------------------------------------


def test_different_source_answer_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")], name="a")
    b = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.6")], name="b")
    engine = mintrl_engine(ws)
    ra = engine.evaluate(make_spec(a.research_result_id))
    rb = engine.evaluate(make_spec(b.research_result_id))
    assert ra.minimum_track_record_length_id != rb.minimum_track_record_length_id


def test_request_name_changes_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    engine = mintrl_engine(ws)
    one = engine.evaluate(make_spec(campaign.research_result_id, name="one"))
    two = engine.evaluate(make_spec(campaign.research_result_id, name="two"))
    assert one.minimum_track_record_length_id != two.minimum_track_record_length_id


# -- fail-closed guards (MT-1) -----------------------------------------------


def test_absent_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(MinTrlConsistencyError):
        mintrl_engine(ws).evaluate(make_spec("sha256:does-not-exist"))


def test_non_campaign_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    dummy = _DummyRecord(research_result_id="sha256:dummy")
    ws.research_result_store.write(dummy)
    with pytest.raises(MinTrlConsistencyError):
        mintrl_engine(ws).evaluate(make_spec(dummy.research_result_id))


def test_id_mismatch_fails_closed(tmp_path: Path) -> None:
    # A record stored at a path whose id disagrees with its content is inconsistent.
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    store = ws.research_result_store
    real_bytes = store._result_path(campaign.research_result_id).read_bytes()
    fake_id = "sha256:00000000"
    store._result_path(fake_id).write_bytes(real_bytes)
    with pytest.raises(MinTrlConsistencyError):
        mintrl_engine(ws).evaluate(make_spec(fake_id))


def test_non_spec_argument_is_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    with pytest.raises(MinTrlConfigurationError):
        mintrl_engine(ws).evaluate(object())  # type: ignore[arg-type]


def test_tampered_stored_payload_conflicts(tmp_path: Path) -> None:
    # A differing payload under an existing MinTRL id fails closed at the store.
    ws = workspace(tmp_path)
    campaign = make_campaign(ws, trials=[_v("trial_1", n=100, sharpe="0.5")])
    result = mintrl_engine(ws).evaluate(make_spec(campaign.research_result_id))
    store = ws.research_result_store

    @dataclass(frozen=True)
    class _Same:
        research_result_id: str
        payload: dict[str, object]

        def to_dict(self) -> dict[str, object]:
            return self.payload

    tampered = result.to_dict()
    tampered["boundary_kind"] = "tampered"
    with pytest.raises(FactorConsistencyError):
        store.write(
            _Same(
                research_result_id=result.research_result_id,
                payload=tampered,
            )
        )
