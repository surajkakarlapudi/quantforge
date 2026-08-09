"""Deterministic tests for the content-addressed panel identities (locked §5, §11).

Pins that every id is ``sha256:``-prefixed and reproducible, that each component of
``panel_definition_id`` / ``panel_id`` is load-bearing (changing any one changes the
id), that ``result_hash`` is order-sensitive, and that the three boundary kinds
produce distinct keys.
"""

from __future__ import annotations

from quantforge.panel.identity import (
    boundary_key,
    panel_definition_id,
    panel_id,
    result_hash,
)

_DEF_KW = dict(
    metric_key="current_ratio",
    formula_id="sha256:formula",
    derivation_id="growth",
    axis_id="sha256:axis",
    shape="period_series",
)


class TestPanelDefinitionId:
    def test_prefixed_and_reproducible(self) -> None:
        a = panel_definition_id(**_DEF_KW)
        b = panel_definition_id(**_DEF_KW)
        assert a == b
        assert a.startswith("sha256:")

    def test_each_component_is_load_bearing(self) -> None:
        base = panel_definition_id(**_DEF_KW)
        for field, value in [
            ("metric_key", "quick_ratio"),
            ("formula_id", "sha256:other"),
            ("derivation_id", "ttm"),
            ("axis_id", "sha256:other-axis"),
            ("shape", "cross_section"),
        ]:
            kw = {**_DEF_KW, field: value}
            assert panel_definition_id(**kw) != base


class TestBoundaryKey:
    def test_three_kinds_distinct(self) -> None:
        pit = boundary_key(kind="pit", value="2024-06-01T00:00:00Z")
        vintage = boundary_key(kind="pit-vintage", value="2024-06-01T00:00:00Z")
        rev = boundary_key(kind="rev", value="sha256:dv")
        assert len({pit, vintage, rev}) == 3
        assert pit.startswith("pit:")
        assert vintage.startswith("pit-vintage:")
        assert rev.startswith("rev:")


class TestResultHash:
    def test_order_sensitive(self) -> None:
        a = result_hash([{"k": 1}, {"k": 2}])
        b = result_hash([{"k": 2}, {"k": 1}])
        assert a != b

    def test_reproducible_and_prefixed(self) -> None:
        outcomes: list[dict[str, object]] = [{"company_id": "cik:1", "v": "2"}]
        assert result_hash(outcomes) == result_hash(outcomes)
        assert result_hash(outcomes).startswith("sha256:")


class TestPanelId:
    def _kw(self) -> dict[str, str]:
        return dict(
            panel_definition_id="sha256:def",
            metric_engine_version_id="sha256:mev",
            member_key="cik:0000320193",
            boundary_key="pit:2024-06-01T00:00:00Z",
            result_hash="sha256:rh",
        )

    def test_reproducible(self) -> None:
        assert panel_id(**self._kw()) == panel_id(**self._kw())

    def test_each_component_is_load_bearing(self) -> None:
        base = panel_id(**self._kw())
        for field in self._kw():
            kw = {**self._kw(), field: "sha256:changed"}
            assert panel_id(**kw) != base
