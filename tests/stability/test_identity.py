"""Content-addressed identity for the stability layer (§10, §11, WS-1)."""

from __future__ import annotations

from quantforge.stability.identity import (
    walk_forward_stability_id,
    walk_forward_stability_result_hash,
)


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "stability_engine_version_id": "sha256:engine",
        "name": "stab",
        "spec_version": "stability/1",
        "source_walk_forward_id": "sha256:src",
        "source_result_hash": "sha256:srchash",
        "min_stability_transitions": 2,
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return walk_forward_stability_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert walk_forward_stability_result_hash([{"block": "x"}]).startswith("sha256:")


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_each_fold_changes_the_id() -> None:
    base = _id()
    assert _id(stability_engine_version_id="sha256:other") != base
    assert _id(name="other") != base
    assert _id(spec_version="stability/2") != base
    assert _id(source_walk_forward_id="sha256:other") != base
    # The transitive pin: a change to the source walk's answer changes our id (WS-1).
    assert _id(source_result_hash="sha256:other") != base
    assert _id(min_stability_transitions=3) != base
    assert _id(result_hash="sha256:other") != base


def test_result_hash_is_sensitive_to_a_single_cell() -> None:
    a = walk_forward_stability_result_hash(
        [{"block": "window", "gross_leverage": "1.0"}]
    )
    b = walk_forward_stability_result_hash(
        [{"block": "window", "gross_leverage": "1.1"}]
    )
    assert a != b


def test_result_hash_is_order_sensitive() -> None:
    a = walk_forward_stability_result_hash(
        [{"block": "window", "index": 0}, {"block": "window", "index": 1}]
    )
    b = walk_forward_stability_result_hash(
        [{"block": "window", "index": 1}, {"block": "window", "index": 0}]
    )
    assert a != b
