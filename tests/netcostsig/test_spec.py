"""The declarative net-of-cost-significance request validates its own shape (§14)."""

from __future__ import annotations

import pytest

from quantforge.netcostsig.errors import NetCostSigConfigurationError
from quantforge.netcostsig.spec import NetOfCostSignificanceSpecification
from quantforge.netcostsig.version import NETCOSTSIG_SPEC_VERSION


def test_valid_spec_round_trips_to_dict() -> None:
    spec = NetOfCostSignificanceSpecification(
        name="phase32", source_net_of_cost_id="sha256:nc"
    )
    assert spec.spec_version == NETCOSTSIG_SPEC_VERSION
    assert spec.to_dict() == {
        "spec_version": NETCOSTSIG_SPEC_VERSION,
        "name": "phase32",
        "source_net_of_cost_id": "sha256:nc",
    }


def test_empty_name_is_rejected() -> None:
    with pytest.raises(NetCostSigConfigurationError):
        NetOfCostSignificanceSpecification(name="", source_net_of_cost_id="sha256:nc")


def test_empty_source_id_is_rejected() -> None:
    with pytest.raises(NetCostSigConfigurationError):
        NetOfCostSignificanceSpecification(name="phase32", source_net_of_cost_id="")


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(NetCostSigConfigurationError):
        NetOfCostSignificanceSpecification(
            name="phase32", source_net_of_cost_id="sha256:nc", spec_version=""
        )
