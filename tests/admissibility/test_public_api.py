"""The Phase 33 front doors are re-exported and wired into the Workspace."""

from __future__ import annotations

from pathlib import Path

import quantforge
from quantforge.admissibility.engine import AdmissibilityEngine
from tests.admissibility.builders import workspace


def test_public_exports() -> None:
    assert quantforge.StrategyAdmissibility is not None
    assert quantforge.AdmissibilitySpecification is not None
    assert "StrategyAdmissibility" in quantforge.__all__
    assert "AdmissibilitySpecification" in quantforge.__all__


def test_workspace_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = ws.admissibility_engine
    assert isinstance(engine, AdmissibilityEngine)
    # Cached: the same instance on repeat access.
    assert ws.admissibility_engine is engine
