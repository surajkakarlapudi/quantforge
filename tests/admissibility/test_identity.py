"""Content-addressed identity is deterministic and sensitive to every fold (§10)."""

from __future__ import annotations

from quantforge.admissibility.identity import (
    admissibility_id,
    admissibility_result_hash,
)


def _id(**overrides: str) -> str:
    base: dict[str, str] = {
        "admissibility_engine_version_id": "sha256:engine",
        "name": "phase33",
        "spec_version": "admissibility/1",
        "source_stability_id": "sha256:stab",
        "source_stability_result_hash": "sha256:stab-hash",
        "source_calibration_significance_id": "sha256:cal",
        "source_calibration_result_hash": "sha256:cal-hash",
        "source_net_of_cost_significance_id": "sha256:net",
        "source_net_of_cost_result_hash": "sha256:net-hash",
        "alpha": "0.05",
        "result_hash": "sha256:answer",
    }
    base.update(overrides)
    return admissibility_id(**base)


def test_result_hash_is_deterministic_and_sha256() -> None:
    cells: list[dict[str, object]] = [{"block": "summary", "verdict": "admissible"}]
    first = admissibility_result_hash(cells)
    second = admissibility_result_hash(cells)
    assert first == second
    assert first.startswith("sha256:")


def test_result_hash_changes_with_a_differing_cell() -> None:
    a_cells: list[dict[str, object]] = [{"block": "summary", "verdict": "admissible"}]
    b_cells: list[dict[str, object]] = [{"block": "summary", "verdict": "inadmissible"}]
    assert admissibility_result_hash(a_cells) != admissibility_result_hash(b_cells)


def test_id_is_deterministic() -> None:
    assert _id() == _id()
    assert _id().startswith("sha256:")


def test_id_is_sensitive_to_every_fold() -> None:
    base = _id()
    assert _id(admissibility_engine_version_id="sha256:v2") != base
    assert _id(name="other") != base
    assert _id(spec_version="admissibility/2") != base
    assert _id(source_stability_id="sha256:other") != base
    assert _id(source_stability_result_hash="sha256:other") != base
    assert _id(source_calibration_significance_id="sha256:other") != base
    assert _id(source_calibration_result_hash="sha256:other") != base
    assert _id(source_net_of_cost_significance_id="sha256:other") != base
    assert _id(source_net_of_cost_result_hash="sha256:other") != base
    assert _id(alpha="0.01") != base
    assert _id(result_hash="sha256:other-answer") != base


def test_id_and_result_hash_are_distinct_domains() -> None:
    # The record id and the answer seal never collide for the same content.
    cells: list[dict[str, object]] = [{"block": "summary", "verdict": "admissible"}]
    rhash = admissibility_result_hash(cells)
    assert _id(result_hash=rhash) != rhash
