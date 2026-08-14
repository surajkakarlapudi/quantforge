"""Content-addressed identity is deterministic and sensitive to every fold (§10)."""

from __future__ import annotations

from quantforge.netcostsig.identity import (
    net_of_cost_significance_id,
    net_of_cost_significance_result_hash,
)


def _id(**overrides: str) -> str:
    base: dict[str, str] = {
        "net_of_cost_significance_engine_version_id": "sha256:engine",
        "name": "phase32",
        "spec_version": "netcostsig/1",
        "source_net_of_cost_id": "sha256:nc",
        "source_result_hash": "sha256:nc-hash",
        "null_mean_return": "0",
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return net_of_cost_significance_id(**base)


def test_result_hash_is_deterministic_and_sha256() -> None:
    cells: list[dict[str, object]] = [
        {"block": "summary", "t_statistic": {"status": "known", "value": "2"}}
    ]
    first = net_of_cost_significance_result_hash(cells)
    second = net_of_cost_significance_result_hash(cells)
    assert first == second
    assert first.startswith("sha256:")


def test_result_hash_changes_with_a_differing_cell() -> None:
    a_cells: list[dict[str, object]] = [{"block": "summary", "t": "2"}]
    b_cells: list[dict[str, object]] = [{"block": "summary", "t": "3"}]
    assert net_of_cost_significance_result_hash(
        a_cells
    ) != net_of_cost_significance_result_hash(b_cells)


def test_id_is_deterministic() -> None:
    assert _id() == _id()
    assert _id().startswith("sha256:")


def test_id_is_sensitive_to_every_fold() -> None:
    base = _id()
    assert _id(name="other") != base
    assert _id(source_net_of_cost_id="sha256:other") != base
    assert _id(source_result_hash="sha256:other-hash") != base
    assert _id(null_mean_return="0.01") != base
    assert _id(result_hash="sha256:other-answer") != base
    assert _id(net_of_cost_significance_engine_version_id="sha256:v2") != base


def test_id_and_result_hash_are_distinct_domains() -> None:
    # The record id and the answer seal never collide for the same content.
    cells: list[dict[str, object]] = [{"block": "summary", "t": "2"}]
    rhash = net_of_cost_significance_result_hash(cells)
    assert _id(result_hash=rhash) != rhash
