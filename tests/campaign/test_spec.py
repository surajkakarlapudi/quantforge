"""The research-campaign request validates its own shape, fail closed (§14)."""

from __future__ import annotations

import pytest

from quantforge.campaign.errors import CampaignConfigurationError
from quantforge.campaign.spec import N_MAX, ResearchCampaignSpecification


def _ids(n: int) -> tuple[str, ...]:
    return tuple(f"sha256:trial-{i}" for i in range(n))


def test_valid_spec_round_trips_to_dict() -> None:
    spec = ResearchCampaignSpecification(
        name="campaign", trial_ids=_ids(3), benchmark_sharpe="0.10"
    )
    payload = spec.to_dict()
    assert payload == {
        "spec_version": "campaign/1",
        "name": "campaign",
        "trial_ids": ["sha256:trial-0", "sha256:trial-1", "sha256:trial-2"],
        "benchmark_sharpe": "0.10",
    }


def test_trial_order_is_preserved_never_sorted() -> None:
    ordered = ("sha256:b", "sha256:a", "sha256:c")
    spec = ResearchCampaignSpecification(name="c", trial_ids=ordered)
    assert spec.to_dict()["trial_ids"] == list(ordered)


def test_benchmark_sharpe_is_canonicalized() -> None:
    # Canonicalization strips the sign form and normalizes exponent notation to the
    # project-wide ``str(+Decimal(...))`` form (it does not strip significant zeros).
    plus = ResearchCampaignSpecification(
        name="c", trial_ids=_ids(2), benchmark_sharpe="+0.5"
    )
    exponent = ResearchCampaignSpecification(
        name="c", trial_ids=_ids(2), benchmark_sharpe="5E-1"
    )
    assert plus.benchmark_sharpe == "0.5"
    assert exponent.benchmark_sharpe == "0.5"


def test_negative_benchmark_sharpe_is_accepted() -> None:
    spec = ResearchCampaignSpecification(
        name="c", trial_ids=_ids(2), benchmark_sharpe="-0.25"
    )
    assert spec.benchmark_sharpe == "-0.25"


def test_default_benchmark_is_zero() -> None:
    spec = ResearchCampaignSpecification(name="c", trial_ids=_ids(2))
    assert spec.benchmark_sharpe == "0"


def test_empty_name_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="", trial_ids=_ids(2))


def test_fewer_than_two_trials_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="c", trial_ids=_ids(1))


def test_more_than_n_max_trials_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="c", trial_ids=_ids(N_MAX + 1))


def test_n_max_trials_is_accepted() -> None:
    spec = ResearchCampaignSpecification(name="c", trial_ids=_ids(N_MAX))
    assert len(spec.trial_ids) == N_MAX


def test_duplicate_trial_id_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="c", trial_ids=("sha256:a", "sha256:a"))


def test_empty_trial_id_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="c", trial_ids=("sha256:a", ""))


def test_non_tuple_trial_ids_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(
            name="c",
            trial_ids=["sha256:a", "sha256:b"],  # type: ignore[arg-type]
        )


def test_non_decimal_benchmark_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(
            name="c", trial_ids=_ids(2), benchmark_sharpe="abc"
        )


def test_non_finite_benchmark_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(
            name="c", trial_ids=_ids(2), benchmark_sharpe="NaN"
        )


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(CampaignConfigurationError):
        ResearchCampaignSpecification(name="c", trial_ids=_ids(2), spec_version="")
