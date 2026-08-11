"""Content-addressed identity: determinism and per-fold sensitivity (§13, PO-1)."""

from __future__ import annotations

import pytest

from quantforge.optimization.identity import (
    optimization_id,
    optimization_result_hash,
)

_BASE: dict[str, object] = {
    "optimization_engine_version_id": "sha256:engine",
    "name": "m",
    "spec_version": "optimization/1",
    "objective": "minimum_variance",
    "constraint_spec": {"fully_invested": True},
    "covariance_basis": "per_period",
    "factor_risk_id": "sha256:risk",
    "factor_risk_result_hash": "sha256:answer",
    "result_hash": "sha256:result",
}


def _cells() -> list[dict[str, object]]:
    return [
        {"block": "status", "status": "optimal"},
        {
            "block": "weight",
            "label": "factor_1",
            "value": {"status": "optimal", "value": "0.5"},
        },
        {
            "block": "weight",
            "label": "factor_2",
            "value": {"status": "optimal", "value": "0.5"},
        },
        {"block": "variance", "value": {"status": "optimal", "value": "2"}},
        {"block": "volatility", "value": {"status": "optimal", "value": "1.4"}},
    ]


class TestResultHash:
    def test_is_prefixed_and_deterministic(self) -> None:
        first = optimization_result_hash(_cells())
        second = optimization_result_hash(_cells())
        assert first == second
        assert first.startswith("sha256:")

    def test_differing_weight_changes_hash(self) -> None:
        cells = _cells()
        cells[1]["value"] = {"status": "optimal", "value": "0.6"}
        assert optimization_result_hash(cells) != optimization_result_hash(_cells())

    def test_weight_order_changes_hash(self) -> None:
        cells = _cells()
        cells[1], cells[2] = cells[2], cells[1]
        assert optimization_result_hash(cells) != optimization_result_hash(_cells())


class TestOptimizationId:
    def test_is_prefixed_and_deterministic(self) -> None:
        assert optimization_id(**_BASE) == optimization_id(**_BASE)  # type: ignore[arg-type]
        assert optimization_id(**_BASE).startswith("sha256:")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("optimization_engine_version_id", "sha256:engine-2"),
            ("name", "n"),
            ("spec_version", "optimization/2"),
            ("objective", "other"),
            ("covariance_basis", "annualized"),
            ("factor_risk_id", "sha256:risk-2"),
            ("factor_risk_result_hash", "sha256:answer-2"),
            ("result_hash", "sha256:result-2"),
        ],
    )
    def test_every_scalar_fold_changes_id(self, key: str, value: str) -> None:
        changed = {**_BASE, key: value}
        assert optimization_id(**changed) != optimization_id(**_BASE)  # type: ignore[arg-type]

    def test_constraint_spec_fold_changes_id(self) -> None:
        changed = {**_BASE, "constraint_spec": {"fully_invested": True, "extra": 1}}
        assert optimization_id(**changed) != optimization_id(**_BASE)  # type: ignore[arg-type]
