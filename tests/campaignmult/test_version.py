"""The engine version pins the reused correction core (§13, CM-5)."""

from __future__ import annotations

from quantforge.campaignmult.version import (
    CAMPAIGNMULT_CORRECTION_VERSION,
    CampaignMultiplicityEngineVersion,
)
from quantforge.multiplicity.version import MULTIPLICITY_METHOD_VERSION


def test_correction_version_binds_to_reused_core() -> None:
    # An honest transitive pin: Phase 30's correction version IS Phase 25's method
    # version, so a change to the reused correction core changes Phase 30's identity.
    assert CAMPAIGNMULT_CORRECTION_VERSION == MULTIPLICITY_METHOD_VERSION


def test_version_id_stable_and_prefixed() -> None:
    v = CampaignMultiplicityEngineVersion()
    assert v.campaign_multiplicity_engine_version_id.startswith("sha256:")
    assert (
        v.campaign_multiplicity_engine_version_id
        == CampaignMultiplicityEngineVersion().campaign_multiplicity_engine_version_id
    )


def test_version_id_changes_with_each_folded_input() -> None:
    base = CampaignMultiplicityEngineVersion()
    base_id = base.campaign_multiplicity_engine_version_id
    assert (
        CampaignMultiplicityEngineVersion(
            code_version="campaignmult-engine/2"
        ).campaign_multiplicity_engine_version_id
        != base_id
    )
    assert (
        CampaignMultiplicityEngineVersion(
            method_version="campaignmult-method/2"
        ).campaign_multiplicity_engine_version_id
        != base_id
    )
    assert (
        CampaignMultiplicityEngineVersion(
            correction_version="multiplicity-method/2"
        ).campaign_multiplicity_engine_version_id
        != base_id
    )
    assert (
        CampaignMultiplicityEngineVersion(
            decimal_precision=28
        ).campaign_multiplicity_engine_version_id
        != base_id
    )
