"""The declarative stability request validates its own shape (§14, WS fail-closed)."""

from __future__ import annotations

import pytest

from quantforge.stability.errors import StabilityConfigurationError
from quantforge.stability.spec import WalkForwardStabilitySpecification
from quantforge.stability.version import STABILITY_SPEC_VERSION


def test_valid_spec_defaults_spec_version() -> None:
    spec = WalkForwardStabilitySpecification(
        name="analysis", source_walk_forward_id="sha256:wf"
    )
    assert spec.spec_version == STABILITY_SPEC_VERSION
    assert spec.to_dict() == {
        "spec_version": STABILITY_SPEC_VERSION,
        "name": "analysis",
        "source_walk_forward_id": "sha256:wf",
    }


def test_empty_name_is_rejected() -> None:
    with pytest.raises(StabilityConfigurationError):
        WalkForwardStabilitySpecification(name="", source_walk_forward_id="sha256:wf")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(StabilityConfigurationError):
        WalkForwardStabilitySpecification(name="analysis", source_walk_forward_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(StabilityConfigurationError):
        WalkForwardStabilitySpecification(
            name="analysis", source_walk_forward_id="sha256:wf", spec_version=""
        )
