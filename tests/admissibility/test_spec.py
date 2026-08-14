"""The declarative strategy-admissibility request validates its own shape (§14)."""

from __future__ import annotations

import pytest

from quantforge.admissibility.errors import AdmissibilityConfigurationError
from quantforge.admissibility.spec import DEFAULT_ALPHA, AdmissibilitySpecification
from quantforge.admissibility.version import ADMISSIBILITY_SPEC_VERSION


def _spec(**overrides: str) -> AdmissibilitySpecification:
    base: dict[str, str] = {
        "name": "phase33",
        "source_stability_id": "sha256:stab",
        "source_calibration_significance_id": "sha256:cal",
        "source_net_of_cost_significance_id": "sha256:net",
    }
    base.update(overrides)
    return AdmissibilitySpecification(**base)


def test_valid_spec_round_trips_to_dict() -> None:
    spec = _spec()
    assert spec.spec_version == ADMISSIBILITY_SPEC_VERSION
    assert spec.alpha == DEFAULT_ALPHA
    assert spec.to_dict() == {
        "spec_version": ADMISSIBILITY_SPEC_VERSION,
        "name": "phase33",
        "source_stability_id": "sha256:stab",
        "source_calibration_significance_id": "sha256:cal",
        "source_net_of_cost_significance_id": "sha256:net",
        "alpha": DEFAULT_ALPHA,
    }


def test_empty_name_is_rejected() -> None:
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(name="")


def test_empty_source_ids_are_rejected() -> None:
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(source_stability_id="")
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(source_calibration_significance_id="")
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(source_net_of_cost_significance_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(spec_version="")


def test_alpha_is_canonicalized() -> None:
    # "0.050" and "0.05" are the same request and yield the same canonical alpha.
    assert _spec(alpha="0.050").alpha == "0.05"


def test_alpha_outside_unit_interval_is_rejected() -> None:
    for bad in ("0", "1", "-0.1", "1.5"):
        with pytest.raises(AdmissibilityConfigurationError):
            _spec(alpha=bad)


def test_non_decimal_alpha_is_rejected() -> None:
    with pytest.raises(AdmissibilityConfigurationError):
        _spec(alpha="not-a-number")
