"""The Phase 32 front doors are re-exported and wired into the Workspace."""

from __future__ import annotations

from pathlib import Path

import quantforge
from quantforge.netcostsig.engine import NetOfCostSignificanceEngine
from tests.netcostsig.builders import workspace


def test_public_exports() -> None:
    assert quantforge.NetOfCostSignificance is not None
    assert quantforge.NetOfCostSignificanceSpecification is not None
    assert "NetOfCostSignificance" in quantforge.__all__
    assert "NetOfCostSignificanceSpecification" in quantforge.__all__


def test_workspace_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = ws.net_of_cost_significance_engine
    assert isinstance(engine, NetOfCostSignificanceEngine)
    # Cached: the same instance on repeat access.
    assert ws.net_of_cost_significance_engine is engine
