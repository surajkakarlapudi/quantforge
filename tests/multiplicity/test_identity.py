"""Content-addressed identity for the multiplicity layer (§10, §11)."""

from __future__ import annotations

from quantforge.multiplicity.identity import (
    multiple_comparison_id,
    multiple_comparison_result_hash,
)


def _id(**overrides: object) -> str:
    base: dict[str, object] = {
        "multiplicity_engine_version_id": "sha256:engine",
        "name": "corr",
        "spec_version": "multiplicity/1",
        "source_strategy_comparison_id": "sha256:src",
        "source_result_hash": "sha256:srchash",
        "alpha": "0.05",
        "methods": ["holm", "benjamini_yekutieli"],
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return multiple_comparison_id(**base)  # type: ignore[arg-type]


def test_ids_are_sha256_prefixed() -> None:
    assert _id().startswith("sha256:")
    assert multiple_comparison_result_hash([{"block": "x"}]).startswith("sha256:")


def test_identity_is_deterministic() -> None:
    assert _id() == _id()


def test_method_order_is_folded() -> None:
    forward = _id(methods=["holm", "benjamini_yekutieli"])
    reversed_ = _id(methods=["benjamini_yekutieli", "holm"])
    assert forward != reversed_


def test_each_fold_changes_the_id() -> None:
    base = _id()
    assert _id(multiplicity_engine_version_id="sha256:other") != base
    assert _id(name="other") != base
    assert _id(spec_version="multiplicity/2") != base
    assert _id(source_strategy_comparison_id="sha256:other") != base
    assert _id(source_result_hash="sha256:other") != base
    assert _id(alpha="0.01") != base
    assert _id(methods=["holm"]) != base
    assert _id(result_hash="sha256:other") != base


def test_result_hash_is_sensitive_to_a_single_cell() -> None:
    a = multiple_comparison_result_hash([{"block": "family", "p_value": "0.01"}])
    b = multiple_comparison_result_hash([{"block": "family", "p_value": "0.02"}])
    assert a != b
