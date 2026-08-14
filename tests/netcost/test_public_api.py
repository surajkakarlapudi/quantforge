"""The Phase 31 public surface is importable and correctly re-exported."""

from __future__ import annotations

import quantforge
import quantforge.netcost as netcost


def test_top_level_exports() -> None:
    """The two headline types are reachable from the package root and in ``__all__``."""
    assert quantforge.NetOfCostPerformance is netcost.NetOfCostPerformance
    assert quantforge.NetOfCostSpecification is netcost.NetOfCostSpecification
    assert "NetOfCostPerformance" in quantforge.__all__
    assert "NetOfCostSpecification" in quantforge.__all__


def test_package_exports_are_public() -> None:
    """Every name in ``quantforge.netcost.__all__`` resolves to an attribute."""
    for name in netcost.__all__:
        assert hasattr(netcost, name), name


def test_engine_and_versions_present() -> None:
    """The engine, version dataclass, and version constants are exported."""
    assert netcost.NetOfCostEngine is not None
    assert netcost.NetOfCostEngineVersion is not None
    assert netcost.NETCOST_SPEC_VERSION == "netcost/1"
    assert netcost.NETCOST_ENGINE_VERSION == "netcost-engine/1"
    assert netcost.NETCOST_METHOD_VERSION == "netcost-method/1"
