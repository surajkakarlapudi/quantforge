"""The Phase 29 front doors are re-exported and wired into the Workspace."""

from __future__ import annotations

from pathlib import Path

import quantforge
from quantforge.calsig.engine import CalibrationSignificanceEngine
from tests.calsig.builders import workspace


def test_public_exports() -> None:
    assert quantforge.CalibrationSignificance is not None
    assert quantforge.CalibrationSignificanceSpecification is not None
    assert "CalibrationSignificance" in quantforge.__all__
    assert "CalibrationSignificanceSpecification" in quantforge.__all__


def test_workspace_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = ws.calibration_significance_engine
    assert isinstance(engine, CalibrationSignificanceEngine)
    # Cached: the same instance on repeat access.
    assert ws.calibration_significance_engine is engine
