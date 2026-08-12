"""The sealed comparison record round-trips, self-verifies, and transposes (§9, §10)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.comparison.model import (
    ComparisonStatus,
    ComparisonUndefinedReason,
    StatStatus,
    StatValue,
)
from quantforge.comparison.result import (
    BOUNDARY_PIT,
    ComparisonCell,
    Coverage,
    StrategyComparison,
    TrialSummary,
)


def _trial(label: str, sharpe: str) -> TrialSummary:
    return TrialSummary(
        label=label,
        sharpe=StatValue.known(sharpe),
        n_valid_periods=3,
        axis_periods=6,
    )


def _known_cell(i: int, j: int, mean: str) -> ComparisonCell:
    return ComparisonCell(
        i=i,
        j=j,
        label_i=f"strategy_{i + 1}",
        label_j=f"strategy_{j + 1}",
        status=ComparisonStatus.KNOWN,
        overlap_periods=3,
        mean_diff=StatValue.known(mean),
        stderr_diff=StatValue.known("0.01"),
        t_stat=StatValue.known("1.25"),
        p_value=StatValue.known("0.2"),
        sharpe_diff=StatValue.known("0.3"),
    )


def _undefined_cell(i: int, j: int) -> ComparisonCell:
    reason = ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
    cell = StatValue.undefined(reason)
    return ComparisonCell(
        i=i,
        j=j,
        label_i=f"strategy_{i + 1}",
        label_j=f"strategy_{j + 1}",
        status=ComparisonStatus.UNDEFINED,
        overlap_periods=0,
        mean_diff=cell,
        stderr_diff=cell,
        t_stat=cell,
        p_value=cell,
        sharpe_diff=cell,
        reason=reason,
    )


def _sealed() -> StrategyComparison:
    comparisons = (
        _known_cell(0, 1, "0.05"),
        _undefined_cell(0, 2),
        _known_cell(1, 2, "-0.02"),
    )
    coverage = Coverage(
        n_strategies=3, n_pairs=3, n_defined_pairs=2, n_undefined_pairs=1
    )
    return StrategyComparison.seal(
        strategy_comparison_engine_version_id="sha256:engine",
        comparison_spec={
            "spec_version": "comparison/1",
            "name": "cmp",
            "walk_forward_ids": ["sha256:a", "sha256:b", "sha256:c"],
        },
        strategy_refs=(
            ("strategy_1", "sha256:a", "sha256:ha"),
            ("strategy_2", "sha256:b", "sha256:hb"),
            ("strategy_3", "sha256:c", "sha256:hc"),
        ),
        boundary_kind=BOUNDARY_PIT,
        schedule_id="schedule",
        factor_portfolio_engine_version_id="fpe/1",
        periods_per_year="1",
        risk_free_per_period="0",
        trials=(
            _trial("strategy_1", "0.5"),
            _trial("strategy_2", "0.3"),
            _trial("strategy_3", "0.4"),
        ),
        comparisons=comparisons,
        coverage=coverage,
        dataset_version_ids=("ds",),
        market_dataset_version_ids=("mkt",),
    )


def test_round_trips_byte_identically() -> None:
    record = _sealed()
    restored = StrategyComparison.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.result_hash == record.result_hash
    assert restored.strategy_comparison_id == record.strategy_comparison_id


def test_research_result_id_aliases_comparison_id() -> None:
    record = _sealed()
    assert record.research_result_id == record.strategy_comparison_id


def test_id_is_rederived_ignoring_tampered_stored_value() -> None:
    record = _sealed()
    payload = record.to_dict()
    payload["strategy_comparison_id"] = "sha256:tampered"
    payload["research_result_id"] = "sha256:tampered"
    restored = StrategyComparison.from_dict(payload)
    assert restored.strategy_comparison_id == record.strategy_comparison_id


def test_walk_forward_ids_property_in_request_order() -> None:
    assert _sealed().walk_forward_ids == ("sha256:a", "sha256:b", "sha256:c")


def test_boundary_is_pit() -> None:
    assert _sealed().boundary_kind == "pit"
    assert BOUNDARY_PIT == "pit"


def test_pin_mismatch_flagged_on_multiple_pins() -> None:
    record = _sealed()
    assert record.pin_mismatch is False
    multi = StrategyComparison.from_dict(
        {**record.to_dict(), "dataset_version_ids": ["ds1", "ds2"]}
    )
    assert multi.pin_mismatch is True


# -- cell() lookup + antisymmetry (SC-8) -------------------------------------


def test_cell_returns_stored_upper_triangle() -> None:
    record = _sealed()
    assert record.cell(0, 1).mean_diff.value == "0.05"
    assert record.cell(1, 2).mean_diff.value == "-0.02"


def test_cell_transpose_sign_flips_antisymmetric_stats() -> None:
    record = _sealed()
    upper = record.cell(0, 1)
    lower = record.cell(1, 0)
    # Antisymmetric statistics flip sign; symmetric ones are preserved.
    lower_mean = Decimal(lower.mean_diff.value or "0")
    assert lower_mean == -Decimal(upper.mean_diff.value or "0")
    assert Decimal(lower.t_stat.value or "0") == -Decimal(upper.t_stat.value or "0")
    assert Decimal(lower.sharpe_diff.value or "0") == -Decimal(
        upper.sharpe_diff.value or "0"
    )
    assert lower.p_value.value == upper.p_value.value
    assert lower.stderr_diff.value == upper.stderr_diff.value
    assert lower.overlap_periods == upper.overlap_periods
    assert lower.label_i == upper.label_j and lower.label_j == upper.label_i


def test_transpose_is_exact_no_ambient_rounding() -> None:
    # A high-precision mean must sign-flip losslessly (regression: unary minus rounds
    # to the ambient decimal context; copy_negate does not).
    precise = "0.000817631494612714912541835771792191"
    cell = _known_cell(0, 1, precise)
    flipped = cell.transpose().mean_diff.value
    assert flipped == "-" + precise


def test_transpose_of_zero_is_canonical_positive_zero() -> None:
    cell = _known_cell(0, 1, "0E-36")
    assert cell.transpose().mean_diff.value == "0E-36"


def test_transpose_preserves_undefined_cells() -> None:
    cell = _undefined_cell(0, 2)
    flipped = cell.transpose()
    assert flipped.status is ComparisonStatus.UNDEFINED
    assert flipped.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP
    assert flipped.mean_diff.reason is ComparisonUndefinedReason.INSUFFICIENT_OVERLAP


def test_self_comparison_cell_raises() -> None:
    with pytest.raises(ValueError):
        _sealed().cell(1, 1)


def test_out_of_range_cell_raises() -> None:
    with pytest.raises(IndexError):
        _sealed().cell(0, 9)


def test_undefined_cell_round_trips() -> None:
    cell = _undefined_cell(0, 2)
    restored = ComparisonCell.from_dict(cell.to_dict())
    assert restored == cell


# -- StatValue fail-closed construction --------------------------------------


def test_stat_value_known_requires_value_without_reason() -> None:
    with pytest.raises(ValueError):
        StatValue(status=StatStatus.KNOWN, value=None)


def test_stat_value_undefined_requires_reason_without_value() -> None:
    with pytest.raises(ValueError):
        StatValue(status=StatStatus.UNDEFINED, value="0.1")


def test_stat_value_from_dict_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        StatValue.from_dict({"status": "undefined", "reason": "not_a_reason"})
