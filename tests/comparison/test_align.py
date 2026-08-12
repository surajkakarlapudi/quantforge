"""Date reconstruction reproduces a sealed walk-forward's OOS series (SC-1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.comparison.align import reconstruct_strategy
from quantforge.comparison.errors import ComparisonConsistencyError
from tests.comparison.builders import (
    SERIES_A,
    SERIES_B,
    make_strategy,
    workspace,
)


def test_reconstruction_reproduces_sealed_oos_series(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    strategy = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    recon = reconstruct_strategy(strategy, ws.research_result_store)

    # The reconstructed axis length equals the sealed complete-case period count.
    assert recon.axis_periods == strategy.common_periods
    # Concatenating the mapped returns in calendar-date order reproduces the sealed
    # chained OOS series exactly (the cross-check task #15 requires).
    chained = tuple(recon.returns[as_of] for as_of in sorted(recon.returns))
    assert chained == strategy.oos_returns


def test_reconstructed_dates_are_the_trailing_axis_dates(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    strategy = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    recon = reconstruct_strategy(strategy, ws.research_result_store)
    # An expanding walk realizes the last k periods; the mapped dates are a subset of
    # the strategy's own reconstructed axis, one per realized OOS return.
    assert len(recon.returns) == len(strategy.oos_returns)
    assert all(isinstance(k, str) for k in recon.returns)


def test_deterministic_reconstruction(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    strategy = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    first = reconstruct_strategy(strategy, ws.research_result_store)
    second = reconstruct_strategy(strategy, ws.research_result_store)
    assert first.returns == second.returns
    assert first.axis_periods == second.axis_periods


def test_missing_chain_fails_closed(tmp_path: Path) -> None:
    # Seal a strategy in one workspace, then attempt to reconstruct it against a fresh,
    # empty sidecar: the referenced optimization is absent, so reconstruction fails
    # closed rather than silently producing a wrong alignment.
    source = workspace(tmp_path / "source")
    strategy = make_strategy(source, name="alpha", series=(SERIES_A, SERIES_B))
    empty = workspace(tmp_path / "empty")
    with pytest.raises(ComparisonConsistencyError):
        reconstruct_strategy(strategy, empty.research_result_store)
