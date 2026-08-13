"""The sealed correction record round-trips byte-identically (§9, §10)."""

from __future__ import annotations

import pytest

from quantforge.campaign.model import CampaignUndefinedReason
from quantforge.campaignmult.model import (
    CorrectionMethod,
    DependenceAssumption,
    ErrorRate,
)
from quantforge.campaignmult.result import (
    CampaignMultiplicityCorrection,
    CampaignMultiplicityCoverage,
    ExcludedTrialCell,
    MethodResult,
    TrialFamilyCell,
    TrialMethodCell,
)


def _record() -> CampaignMultiplicityCorrection:
    family = (
        TrialFamilyCell(index=0, label="trial_1", psr="0.99", p_value="0.01"),
        TrialFamilyCell(index=2, label="trial_3", psr="0.90", p_value="0.10"),
    )
    excluded = (
        ExcludedTrialCell(
            index=1,
            label="trial_2",
            reason=CampaignUndefinedReason.ZERO_OOS_VARIANCE,
        ),
    )
    corrections = (
        MethodResult(
            method=CorrectionMethod.BONFERRONI,
            error_rate=ErrorRate.FAMILY_WISE,
            dependence=DependenceAssumption.ARBITRARY,
            cells=(
                TrialMethodCell(index=0, p_adjusted="0.02", rejected=True),
                TrialMethodCell(index=2, p_adjusted="0.20", rejected=False),
            ),
            n_rejected=1,
        ),
    )
    coverage = CampaignMultiplicityCoverage(
        n_trials_total=3, family_size=2, n_excluded=1
    )
    return CampaignMultiplicityCorrection.seal(
        campaign_multiplicity_engine_version_id="sha256:engine",
        correction_spec={
            "spec_version": "campaignmult/1",
            "name": "c",
            "source_campaign_id": "sha256:campaign",
            "alpha": "0.05",
            "methods": ["bonferroni"],
        },
        source_ref=("sha256:campaign", "sha256:rh"),
        boundary_kind="pit",
        family=family,
        excluded=excluded,
        corrections=corrections,
        coverage=coverage,
    )


def test_round_trip_is_byte_identical() -> None:
    rec = _record()
    again = CampaignMultiplicityCorrection.from_dict(rec.to_dict())
    assert again.to_dict() == rec.to_dict()
    assert again.result_hash == rec.result_hash
    assert again.campaign_multiplicity_id == rec.campaign_multiplicity_id


def test_research_result_id_aliases_the_derived_id() -> None:
    rec = _record()
    assert rec.research_result_id == rec.campaign_multiplicity_id
    assert rec.source_campaign_id == "sha256:campaign"
    assert rec.source_result_hash == "sha256:rh"
    assert rec.alpha == "0.05"
    assert rec.family_size == 2


def test_id_is_reemitted_not_read_from_state() -> None:
    rec = _record()
    payload = rec.to_dict()
    payload["campaign_multiplicity_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = CampaignMultiplicityCorrection.from_dict(payload)
    # The derived id ignores the tampered stored value.
    assert restored.campaign_multiplicity_id == rec.campaign_multiplicity_id


def test_coverage_counts_do_not_alter_hash_beyond_descriptor() -> None:
    # family_size / n_excluded ARE folded (via the descriptor); n_trials_total is not.
    rec = _record()
    payload = rec.to_dict()
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    coverage["n_trials_total"] = 999
    restored = CampaignMultiplicityCorrection.from_dict(payload)
    assert restored.result_hash == rec.result_hash


def test_correction_lookup_and_missing_method() -> None:
    rec = _record()
    assert rec.correction(CorrectionMethod.BONFERRONI).n_rejected == 1
    with pytest.raises(KeyError):
        rec.correction(CorrectionMethod.HOLM)


def test_boundary_is_pit_not_a_pit_type() -> None:
    rec = _record()
    assert rec.boundary_kind == "pit"
    # Ex-post: no as-of accessor (CM-6).
    assert not hasattr(rec, "as_of")
