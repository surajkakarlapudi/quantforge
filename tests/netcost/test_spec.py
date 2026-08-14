"""The declarative net-of-cost request validates shape and canonicalizes cost_rate."""

from __future__ import annotations

import pytest

from quantforge.netcost.errors import NetOfCostConfigurationError
from quantforge.netcost.spec import NetOfCostSpecification
from quantforge.netcost.version import NETCOST_SPEC_VERSION


def _spec(**kw: str) -> NetOfCostSpecification:
    base = {"name": "n", "source_stability_id": "sha256:s", "cost_rate": "0.001"}
    base.update(kw)
    return NetOfCostSpecification(**base)


def test_defaults_and_to_dict() -> None:
    spec = _spec()
    assert spec.spec_version == NETCOST_SPEC_VERSION
    assert spec.to_dict() == {
        "spec_version": NETCOST_SPEC_VERSION,
        "name": "n",
        "source_stability_id": "sha256:s",
        "cost_rate": "0.001",
    }


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("0.001", "0.001"),
        ("0.0010", "0.001"),
        ("0", "0"),
        ("0.0", "0"),
        ("1E-3", "0.001"),
    ],
)
def test_cost_rate_canonicalization(raw: str, canonical: str) -> None:
    """Trailing-zero / exponent variants collapse to one canonical decimal string."""
    assert _spec(cost_rate=raw).cost_rate == canonical


def test_zero_cost_rate_is_permitted() -> None:
    """A zero rate is a valid (gross-equals-net) counterfactual."""
    assert _spec(cost_rate="0").cost_rate == "0"


@pytest.mark.parametrize("bad", ["-0.001", "-1"])
def test_negative_cost_rate_refused(bad: str) -> None:
    with pytest.raises(NetOfCostConfigurationError):
        _spec(cost_rate=bad)


@pytest.mark.parametrize("bad", ["", "abc", "1/2", "NaN", "Infinity", "-Infinity"])
def test_non_finite_or_non_decimal_cost_rate_refused(bad: str) -> None:
    with pytest.raises(NetOfCostConfigurationError):
        _spec(cost_rate=bad)


@pytest.mark.parametrize("field", ["name", "source_stability_id"])
def test_empty_required_string_refused(field: str) -> None:
    with pytest.raises(NetOfCostConfigurationError):
        _spec(**{field: ""})


def test_empty_spec_version_refused() -> None:
    with pytest.raises(NetOfCostConfigurationError):
        NetOfCostSpecification(
            name="n",
            source_stability_id="sha256:s",
            cost_rate="0.001",
            spec_version="",
        )


def test_frozen() -> None:
    spec = _spec()
    with pytest.raises(AttributeError):
        spec.name = "other"  # type: ignore[misc]
