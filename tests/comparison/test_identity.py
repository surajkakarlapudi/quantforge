"""Content-addressed identity for the comparison layer (§10, §11)."""

from __future__ import annotations

from quantforge.comparison.identity import (
    strategy_comparison_id,
    strategy_comparison_result_hash,
)


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "strategy_comparison_engine_version_id": "sha256:engine",
        "name": "cmp",
        "spec_version": "comparison/1",
        "walk_forward_ids": ["sha256:a", "sha256:b"],
        "strategy_result_hashes": ["sha256:ha", "sha256:hb"],
        "periods_per_year": "1",
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return strategy_comparison_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert strategy_comparison_result_hash([{"block": "x"}]).startswith("sha256:")


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_strategy_order_is_semantic() -> None:
    forward = _id(walk_forward_ids=["sha256:a", "sha256:b"])
    reversed_ = _id(walk_forward_ids=["sha256:b", "sha256:a"])
    assert forward != reversed_


def test_each_fold_changes_the_id() -> None:
    baseline = _id()
    assert _id(strategy_comparison_engine_version_id="sha256:other") != baseline
    assert _id(name="other") != baseline
    assert _id(spec_version="comparison/2") != baseline
    assert _id(walk_forward_ids=["sha256:b", "sha256:a"]) != baseline
    assert _id(strategy_result_hashes=["sha256:hx", "sha256:hb"]) != baseline
    assert _id(periods_per_year="12") != baseline
    assert _id(result_hash="sha256:other") != baseline


def test_result_hash_sensitive_to_every_cell() -> None:
    a = strategy_comparison_result_hash([{"block": "pair", "mean_diff": "1"}])
    b = strategy_comparison_result_hash([{"block": "pair", "mean_diff": "2"}])
    assert a != b


def test_result_hash_is_order_sensitive() -> None:
    cells = [{"block": "pair", "i": 0}, {"block": "pair", "i": 1}]
    assert strategy_comparison_result_hash(cells) != strategy_comparison_result_hash(
        list(reversed(cells))
    )
