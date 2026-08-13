"""The declarative campaign-multiplicity request validates its own shape (§14)."""

from __future__ import annotations

import pytest

from quantforge.campaignmult.errors import CampaignMultiplicityConfigurationError
from quantforge.campaignmult.model import CorrectionMethod
from quantforge.campaignmult.spec import (
    DEFAULT_METHODS,
    CampaignMultiplicitySpecification,
)
from quantforge.campaignmult.version import CAMPAIGNMULT_SPEC_VERSION


def _spec(**kw: object) -> CampaignMultiplicitySpecification:
    base: dict[str, object] = {
        "name": "c",
        "source_campaign_id": "sha256:campaign",
        "alpha": "0.05",
    }
    base.update(kw)
    return CampaignMultiplicitySpecification(**base)  # type: ignore[arg-type]


def test_defaults_are_holm_and_by() -> None:
    spec = _spec()
    assert spec.methods == DEFAULT_METHODS
    assert DEFAULT_METHODS == (
        CorrectionMethod.HOLM,
        CorrectionMethod.BENJAMINI_YEKUTIELI,
    )
    assert spec.spec_version == CAMPAIGNMULT_SPEC_VERSION


def test_alpha_is_canonicalized() -> None:
    assert _spec(alpha="0.050").alpha == "0.05"
    assert _spec(alpha="0.05").alpha == "0.05"


@pytest.mark.parametrize("bad", ["0", "1", "-0.1", "1.5", "abc", "NaN", ""])
def test_alpha_out_of_open_interval_or_nonfinite_rejected(bad: str) -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(alpha=bad)


def test_empty_name_rejected() -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(name="")


def test_empty_source_id_rejected() -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(source_campaign_id="")


def test_empty_methods_rejected() -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(methods=())


def test_duplicate_method_rejected() -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(methods=(CorrectionMethod.HOLM, CorrectionMethod.HOLM))


def test_non_method_rejected() -> None:
    with pytest.raises(CampaignMultiplicityConfigurationError):
        _spec(methods=("holm",))


def test_to_dict_preserves_method_order() -> None:
    spec = _spec(methods=(CorrectionMethod.BENJAMINI_YEKUTIELI, CorrectionMethod.HOLM))
    payload = spec.to_dict()
    assert payload["methods"] == ["benjamini_yekutieli", "holm"]
    assert payload["source_campaign_id"] == "sha256:campaign"
    assert payload["alpha"] == "0.05"
