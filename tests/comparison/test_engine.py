"""End-to-end strategy comparison through the engine (§6, SC-1..SC-8)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from quantforge.comparison.errors import (
    ComparisonConfigurationError,
    ComparisonConsistencyError,
)
from quantforge.comparison.model import ComparisonStatus, ComparisonUndefinedReason
from quantforge.comparison.result import StrategyComparison
from tests.comparison.builders import (
    DATES_LATE,
    SERIES_A,
    SERIES_B,
    SERIES_C,
    SERIES_D,
    comparison_engine,
    comparison_spec,
    make_strategy,
    workspace,
)


@dataclass(frozen=True)
class _DummyRecord:
    """A non-``WalkForwardEvaluation`` :class:`ResearchRecord` for fail-closed tests."""

    research_result_id: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": "not-a-walk", "id": self.research_result_id}


def _two_distinct(ws: object) -> tuple[str, str]:
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))  # type: ignore[arg-type]
    b = make_strategy(ws, name="beta", series=(SERIES_C, SERIES_D))  # type: ignore[arg-type]
    return a.research_result_id, b.research_result_id


# -- happy path --------------------------------------------------------------


def test_happy_path_seals_full_matrix(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a, b = _two_distinct(ws)
    engine = comparison_engine(ws)
    result = engine.compare(comparison_spec((a, b)))
    assert result.coverage.n_strategies == 2
    assert result.coverage.n_pairs == 1
    assert result.coverage.n_defined_pairs == 1
    assert result.coverage.n_undefined_pairs == 0
    cell = result.cell(0, 1)
    assert cell.status is ComparisonStatus.KNOWN
    assert cell.overlap_periods == 3
    assert cell.mean_diff.value is not None
    assert cell.p_value.value is not None
    # The per-strategy summary carries the sealed OOS Sharpe and reconstructed axis.
    assert len(result.trials) == 2
    assert all(t.axis_periods == 6 for t in result.trials)


def test_three_strategies_form_three_pairs(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="a", series=(SERIES_A, SERIES_B))
    b = make_strategy(ws, name="b", series=(SERIES_C, SERIES_D))
    c = make_strategy(ws, name="c", series=(SERIES_B, SERIES_C))
    engine = comparison_engine(ws)
    result = engine.compare(
        comparison_spec(
            (a.research_result_id, b.research_result_id, c.research_result_id)
        )
    )
    assert result.coverage.n_pairs == 3
    assert result.coverage.n_defined_pairs == 3


# -- persistence + reproducibility -------------------------------------------


def test_result_is_persisted_and_reproducible(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a, b = _two_distinct(ws)
    engine = comparison_engine(ws)
    spec = comparison_spec((a, b))
    first = engine.compare(spec)
    stored = ws.research_result_store.read_as(
        first.research_result_id, StrategyComparison.from_dict
    )
    assert stored is not None
    assert stored.to_dict() == first.to_dict()
    second = engine.compare(spec)
    assert second.research_result_id == first.research_result_id
    assert second.to_dict() == first.to_dict()


def test_strategy_order_changes_the_id(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a, b = _two_distinct(ws)
    engine = comparison_engine(ws)
    forward = engine.compare(comparison_spec((a, b), name="fwd"))
    reversed_ = engine.compare(comparison_spec((b, a), name="rev"))
    assert forward.research_result_id != reversed_.research_result_id


# -- antisymmetry (SC-8) -----------------------------------------------------


def test_transpose_matches_a_reversed_computation(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a, b = _two_distinct(ws)
    engine = comparison_engine(ws)
    forward = engine.compare(comparison_spec((a, b), name="fwd"))
    reversed_ = engine.compare(comparison_spec((b, a), name="rev"))
    # The (j, i) view of the forward matrix equals a genuine reversed computation,
    # to the last sealed digit (regression guard for the exact sign flip).
    transposed = forward.cell(1, 0)
    real = reversed_.cell(0, 1)
    assert transposed.mean_diff.value == real.mean_diff.value
    assert transposed.t_stat.value == real.t_stat.value
    assert transposed.sharpe_diff.value == real.sharpe_diff.value
    assert transposed.p_value.value == real.p_value.value


# -- undefined data conditions are recorded, never raised (SC-4) -------------


def test_insufficient_overlap_is_recorded(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    early = make_strategy(ws, name="early", series=(SERIES_A, SERIES_B))
    late = make_strategy(ws, name="late", series=(SERIES_A, SERIES_B), dates=DATES_LATE)
    engine = comparison_engine(ws)
    result = engine.compare(
        comparison_spec((early.research_result_id, late.research_result_id))
    )
    cell = result.cell(0, 1)
    assert cell.status is ComparisonStatus.UNDEFINED
    assert cell.overlap_periods == 0
    assert cell.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
    assert cell.mean_diff.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
    assert result.coverage.n_undefined_pairs == 1
    assert result.coverage.n_defined_pairs == 0


def test_zero_difference_variance_is_recorded(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    # Two strategies from the identical factor series (distinct names ⇒ distinct
    # records) seal identical OOS returns, so the paired difference is exactly zero.
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    dup = make_strategy(ws, name="alpha-dup", series=(SERIES_A, SERIES_B))
    engine = comparison_engine(ws)
    result = engine.compare(
        comparison_spec((a.research_result_id, dup.research_result_id))
    )
    cell = result.cell(0, 1)
    assert cell.status is ComparisonStatus.KNOWN  # the pair does overlap
    assert Decimal(cell.mean_diff.value or "1") == Decimal(0)
    assert cell.t_stat.reason is ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE
    assert cell.p_value.reason is ComparisonUndefinedReason.ZERO_DIFFERENCE_VARIANCE
    # Identical Sharpe ⇒ the descriptive Sharpe difference is a defined zero.
    assert Decimal(cell.sharpe_diff.value or "1") == Decimal(0)


# -- configuration / consistency defects raise (SC-1/SC-2) -------------------


def test_non_spec_argument_raises(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    engine = comparison_engine(ws)
    with pytest.raises(ComparisonConfigurationError):
        engine.compare(object())  # type: ignore[arg-type]


def test_missing_strategy_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    engine = comparison_engine(ws)
    spec = comparison_spec((a.research_result_id, "sha256:does-not-exist"))
    with pytest.raises(ComparisonConsistencyError):
        engine.compare(spec)


def test_non_walkforward_record_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    dummy = _DummyRecord(research_result_id="sha256:not-a-walk")
    ws.research_result_store.write(dummy)
    engine = comparison_engine(ws)
    spec = comparison_spec((a.research_result_id, dummy.research_result_id))
    with pytest.raises(ComparisonConsistencyError):
        engine.compare(spec)


def test_incommensurable_schedule_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    b = make_strategy(
        ws, name="beta", series=(SERIES_C, SERIES_D), schedule_id="other-schedule"
    )
    engine = comparison_engine(ws)
    with pytest.raises(ComparisonConsistencyError):
        engine.compare(comparison_spec((a.research_result_id, b.research_result_id)))


def test_incommensurable_periods_per_year_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    b = make_strategy(
        ws, name="beta", series=(SERIES_C, SERIES_D), periods_per_year="12"
    )
    engine = comparison_engine(ws)
    with pytest.raises(ComparisonConsistencyError):
        engine.compare(comparison_spec((a.research_result_id, b.research_result_id)))


def test_incommensurable_risk_free_fails_closed(tmp_path: Path) -> None:
    ws = workspace(tmp_path)
    a = make_strategy(ws, name="alpha", series=(SERIES_A, SERIES_B))
    b = make_strategy(
        ws, name="beta", series=(SERIES_C, SERIES_D), risk_free_per_period="0.001"
    )
    engine = comparison_engine(ws)
    with pytest.raises(ComparisonConsistencyError):
        engine.compare(comparison_spec((a.research_result_id, b.research_result_id)))
