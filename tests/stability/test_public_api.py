"""The Phase 27 front doors are re-exported and wired into the Workspace."""

from __future__ import annotations

from pathlib import Path

import quantforge
from quantforge.stability.engine import WalkForwardStabilityEngine
from tests.stability.builders import workspace


def test_public_exports() -> None:
    assert quantforge.WalkForwardStability is not None
    assert quantforge.WalkForwardStabilitySpecification is not None
    assert "WalkForwardStability" in quantforge.__all__
    assert "WalkForwardStabilitySpecification" in quantforge.__all__


def test_workspace_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = ws.stability_engine
    assert isinstance(engine, WalkForwardStabilityEngine)
    # Cached: the same instance on repeat access.
    assert ws.stability_engine is engine
