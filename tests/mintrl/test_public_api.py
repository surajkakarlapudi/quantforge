"""The Phase 28 front doors are re-exported and wired into the Workspace."""

from __future__ import annotations

from pathlib import Path

import quantforge
from quantforge.mintrl.engine import MinimumTrackRecordLengthEngine
from tests.mintrl.builders import workspace


def test_public_exports() -> None:
    assert quantforge.MinimumTrackRecordLength is not None
    assert quantforge.MinimumTrackRecordLengthSpecification is not None
    assert "MinimumTrackRecordLength" in quantforge.__all__
    assert "MinimumTrackRecordLengthSpecification" in quantforge.__all__


def test_workspace_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = ws.mintrl_engine
    assert isinstance(engine, MinimumTrackRecordLengthEngine)
    # Cached: the same instance on repeat access.
    assert ws.mintrl_engine is engine
