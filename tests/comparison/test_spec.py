"""The strategy-comparison request validates its own shape, fail closed (§14)."""

from __future__ import annotations

import pytest

from quantforge.comparison.errors import ComparisonConfigurationError
from quantforge.comparison.spec import N_MAX, StrategyComparisonSpecification


def _ids(n: int) -> tuple[str, ...]:
    return tuple(f"sha256:strategy-{i}" for i in range(n))


def test_valid_spec_round_trips_to_dict() -> None:
    spec = StrategyComparisonSpecification(name="cmp", walk_forward_ids=_ids(3))
    assert spec.to_dict() == {
        "spec_version": "comparison/1",
        "name": "cmp",
        "walk_forward_ids": [
            "sha256:strategy-0",
            "sha256:strategy-1",
            "sha256:strategy-2",
        ],
    }


def test_strategy_order_is_preserved_never_sorted() -> None:
    ordered = ("sha256:b", "sha256:a", "sha256:c")
    spec = StrategyComparisonSpecification(name="c", walk_forward_ids=ordered)
    assert spec.to_dict()["walk_forward_ids"] == list(ordered)


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(name="", walk_forward_ids=_ids(2))


def test_fewer_than_two_strategies_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(name="c", walk_forward_ids=_ids(1))


def test_more_than_n_max_strategies_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(name="c", walk_forward_ids=_ids(N_MAX + 1))


def test_n_max_strategies_is_accepted() -> None:
    spec = StrategyComparisonSpecification(name="c", walk_forward_ids=_ids(N_MAX))
    assert len(spec.walk_forward_ids) == N_MAX


def test_duplicate_strategy_id_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(
            name="c", walk_forward_ids=("sha256:a", "sha256:a")
        )


def test_empty_strategy_id_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(name="c", walk_forward_ids=("sha256:a", ""))


def test_non_tuple_walk_forward_ids_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(
            name="c",
            walk_forward_ids=["sha256:a", "sha256:b"],  # type: ignore[arg-type]
        )


def test_empty_spec_version_is_rejected() -> None:
    with pytest.raises(ComparisonConfigurationError):
        StrategyComparisonSpecification(
            name="c", walk_forward_ids=_ids(2), spec_version=""
        )
