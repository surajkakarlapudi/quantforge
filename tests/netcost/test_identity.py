"""The content-addressed net-of-cost ids are deterministic and honestly sensitive."""

from __future__ import annotations

from quantforge.netcost.identity import net_of_cost_id, net_of_cost_result_hash


def _cells() -> list[dict[str, object]]:
    return [
        {"block": "coverage_descriptor", "n_windows": 2, "n_realized": 2},
        {"block": "window", "index": 0, "gross_return": "0.02"},
        {"block": "summary", "net_status": "measured"},
    ]


def _kw(**over: str) -> dict[str, str]:
    base = {
        "net_of_cost_engine_version_id": "sha256:eng",
        "name": "n",
        "spec_version": "netcost/1",
        "source_stability_id": "sha256:stab",
        "source_result_hash": "sha256:rh",
        "cost_rate": "0.001",
        "result_hash": "sha256:answer",
    }
    base.update(over)
    return base


def test_result_hash_deterministic() -> None:
    assert net_of_cost_result_hash(_cells()) == net_of_cost_result_hash(_cells())


def test_result_hash_sensitive_to_a_cell() -> None:
    other = _cells()
    other[1]["gross_return"] = "0.03"
    assert net_of_cost_result_hash(_cells()) != net_of_cost_result_hash(other)


def test_id_deterministic() -> None:
    assert net_of_cost_id(**_kw()) == net_of_cost_id(**_kw())
    assert net_of_cost_id(**_kw()).startswith("sha256:")


def test_id_sensitive_to_each_fold() -> None:
    base = net_of_cost_id(**_kw())
    for field in _kw():
        changed = net_of_cost_id(**_kw(**{field: "sha256:CHANGED-value-x"}))
        assert changed != base, field


def test_cost_rate_changes_id() -> None:
    zero = net_of_cost_id(**_kw(cost_rate="0"))
    assert zero != net_of_cost_id(**_kw(cost_rate="0.001"))


def test_domain_separation() -> None:
    """The id is not merely the result hash (a distinct domain-tagged construction)."""
    kw = _kw()
    assert net_of_cost_id(**kw) != kw["result_hash"]
    assert net_of_cost_id(**kw) != net_of_cost_result_hash(_cells())
