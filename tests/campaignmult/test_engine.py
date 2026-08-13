"""End-to-end campaign-multiplicity correction through the engine (§6, CM-1..CM-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.campaign.model import CampaignUndefinedReason
from quantforge.campaignmult.errors import (
    CampaignMultiplicityConfigurationError,
    CampaignMultiplicityConsistencyError,
)
from quantforge.campaignmult.model import CorrectionMethod
from quantforge.campaignmult.result import CampaignMultiplicityCorrection

from .builders import (
    campaign_multiplicity_engine,
    make_campaign,
    make_spec,
    psr_trial,
    undefined_psr_trial,
    workspace,
)


def test_family_transform_and_bonferroni(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(
        ws,
        trials=[
            psr_trial("trial_1", psr="0.99"),
            psr_trial("trial_2", psr="0.98"),
            psr_trial("trial_3", psr="0.90"),
        ],
    )
    spec = make_spec(
        campaign.research_result_id,
        alpha="0.05",
        methods=(CorrectionMethod.BONFERRONI,),
    )
    result = engine.correct(spec)

    # p_i = 1 - PSR_i, consumed verbatim + derived exactly (CM-4).
    assert [(c.index, c.psr, c.p_value) for c in result.family] == [
        (0, "0.99", "0.01"),
        (1, "0.98", "0.02"),
        (2, "0.90", "0.10"),
    ]
    assert result.coverage.n_trials_total == 3
    assert result.coverage.family_size == 3
    assert result.coverage.n_excluded == 0

    # Bonferroni m=3: min(1, 3*p) = 0.03, 0.06, 0.30; rejected at alpha 0.05.
    bonf = result.correction(CorrectionMethod.BONFERRONI)
    assert [(c.index, c.p_adjusted, c.rejected) for c in bonf.cells] == [
        (0, "0.03", True),
        (1, "0.06", False),
        (2, "0.30", False),
    ]
    assert bonf.n_rejected == 1


def test_undefined_psr_is_a_first_class_exclusion(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(
        ws,
        trials=[
            psr_trial("trial_1", psr="0.99"),
            undefined_psr_trial(
                "trial_2", reason=CampaignUndefinedReason.DEGENERATE_SHARPE_ESTIMATOR
            ),
            psr_trial("trial_3", psr="0.90"),
        ],
    )
    result = engine.correct(
        make_spec(campaign.research_result_id, methods=(CorrectionMethod.BONFERRONI,))
    )
    assert result.coverage.family_size == 2
    assert result.coverage.n_excluded == 1
    assert [(c.index, c.label, c.reason.value) for c in result.excluded] == [
        (1, "trial_2", "degenerate_sharpe_estimator")
    ]
    # The family skips the excluded index; m=2 for the correction.
    assert [c.index for c in result.family] == [0, 2]
    bonf = result.correction(CorrectionMethod.BONFERRONI)
    # 2*0.01=0.02, 2*0.10=0.20.
    assert [(c.index, c.p_adjusted) for c in bonf.cells] == [(0, "0.02"), (2, "0.20")]


def test_empty_family_no_divide_by_zero(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(
        ws,
        trials=[undefined_psr_trial("trial_1"), undefined_psr_trial("trial_2")],
    )
    result = engine.correct(make_spec(campaign.research_result_id))
    assert result.family == ()
    assert result.coverage.family_size == 0
    assert result.coverage.n_excluded == 2
    for method_result in result.corrections:
        assert method_result.cells == ()
        assert method_result.n_rejected == 0


def test_boundary_and_transitive_pin_carried(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(ws, trials=[psr_trial("trial_1", psr="0.99")])
    result = engine.correct(make_spec(campaign.research_result_id))
    assert result.boundary_kind == "pit"
    assert result.source_campaign_id == campaign.research_result_id
    assert result.source_result_hash == campaign.result_hash


def test_deterministic_and_idempotent(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(
        ws,
        trials=[psr_trial("trial_1", psr="0.99"), psr_trial("trial_2", psr="0.80")],
    )
    spec = make_spec(campaign.research_result_id)
    first = engine.correct(spec)
    second = engine.correct(spec)  # idempotent write, byte-identical
    assert first.research_result_id == second.research_result_id
    assert first.to_dict() == second.to_dict()
    # And it is readable back from the shared sidecar as a typed record.
    restored = ws.research_result_store.read_as(
        first.research_result_id, CampaignMultiplicityCorrection.from_dict
    )
    assert restored is not None
    assert restored.to_dict() == first.to_dict()


def test_method_order_yields_distinct_records(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(
        ws,
        trials=[psr_trial("trial_1", psr="0.99"), psr_trial("trial_2", psr="0.80")],
    )
    a = engine.correct(
        make_spec(
            campaign.research_result_id,
            methods=(CorrectionMethod.HOLM, CorrectionMethod.BENJAMINI_YEKUTIELI),
        )
    )
    b = engine.correct(
        make_spec(
            campaign.research_result_id,
            methods=(CorrectionMethod.BENJAMINI_YEKUTIELI, CorrectionMethod.HOLM),
        )
    )
    assert a.research_result_id != b.research_result_id


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    with pytest.raises(CampaignMultiplicityConsistencyError):
        engine.correct(make_spec("sha256:not-present"))


def test_wrong_type_source_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    campaign = make_campaign(ws, trials=[psr_trial("trial_1", psr="0.99")])
    correction = engine.correct(make_spec(campaign.research_result_id))
    # Point a new request at the CORRECTION's id (not a campaign) => consistency defect.
    with pytest.raises(CampaignMultiplicityConsistencyError):
        engine.correct(make_spec(correction.research_result_id))


def test_non_spec_argument_rejected(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = campaign_multiplicity_engine(ws)
    with pytest.raises(CampaignMultiplicityConfigurationError):
        engine.correct(object())  # type: ignore[arg-type]
