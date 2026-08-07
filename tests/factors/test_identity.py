"""Tests for the content-addressed factor identities (``docs/factors.md`` §7).

``factor_definition_id`` names *which factor* (metric + formula + transform);
``result_hash`` fingerprints the *output* (ordered cell outcomes);
``research_result_id`` pins both request and output. All must be deterministic,
sha256-prefixed, and sensitive to every component.
"""

from __future__ import annotations

from quantforge.factors.identity import (
    boundary_key,
    factor_definition_id,
    research_result_id,
    result_hash,
)

_DEF_KW = {
    "metric_key": "current_ratio",
    "formula_id": "sha256:formula",
    "transform_id": "zscore",
}

_RR_KW = {
    "factor_definition_id": "sha256:def",
    "metric_engine_version_id": "sha256:engine",
    "universe_id": "sha256:universe",
    "period_key": "instant\x00\x002023-09-30",
    "boundary_key": "pit:2023-11-05T21:30:00Z",
    "result_hash": "sha256:result",
}

_CELLS: list[dict[str, object]] = [
    {"company_id": "cik:0000320193", "status": "known", "value_numeric": "2"},
    {"company_id": "cik:0000789019", "status": "undefined", "reason": "missing_input"},
]


class TestFactorDefinitionId:
    def test_deterministic_and_prefixed(self) -> None:
        one = factor_definition_id(**_DEF_KW)
        assert one.startswith("sha256:")
        assert one == factor_definition_id(**_DEF_KW)

    def test_each_component_is_load_bearing(self) -> None:
        base = factor_definition_id(**_DEF_KW)
        for key in _DEF_KW:
            changed = factor_definition_id(**{**_DEF_KW, key: _DEF_KW[key] + "-x"})
            assert changed != base, f"factor_definition_id insensitive to {key}"


class TestResultHash:
    def test_deterministic_and_prefixed(self) -> None:
        one = result_hash(_CELLS)
        assert one.startswith("sha256:")
        assert one == result_hash(_CELLS)

    def test_sensitive_to_a_cell_value(self) -> None:
        changed = [dict(_CELLS[0], value_numeric="3"), _CELLS[1]]
        assert result_hash(changed) != result_hash(_CELLS)

    def test_sensitive_to_a_cell_status(self) -> None:
        changed = [dict(_CELLS[0], status="undefined"), _CELLS[1]]
        assert result_hash(changed) != result_hash(_CELLS)

    def test_order_is_load_bearing(self) -> None:
        # Cell order is the cross-section's order — not re-sorted (§7, §12).
        assert result_hash(_CELLS) != result_hash(list(reversed(_CELLS)))


class TestBoundaryKey:
    def test_pit_and_revised_never_collide(self) -> None:
        pit = boundary_key(kind="pit", value="2023-11-05T21:30:00Z")
        rev = boundary_key(kind="rev", value="sha256:dataset")
        assert pit != rev
        assert pit.startswith("pit:")
        assert rev.startswith("rev:")


class TestResearchResultId:
    def test_deterministic_and_prefixed(self) -> None:
        one = research_result_id(**_RR_KW)
        assert one.startswith("sha256:")
        assert one == research_result_id(**_RR_KW)

    def test_each_component_is_load_bearing(self) -> None:
        base = research_result_id(**_RR_KW)
        for key in _RR_KW:
            changed = research_result_id(**{**_RR_KW, key: _RR_KW[key] + "-x"})
            assert changed != base, f"research_result_id insensitive to {key}"
