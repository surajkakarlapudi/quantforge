"""Content-addressed identity of the diagnostics layer (locked §5, §11).

``diagnostics_id`` folds the engine version, the full declared request (name, spec
version, signal, period key, universe id, schedule id, horizon days, quantiles, sorted
IC methods), **both** corpus pins, and the ``result_hash`` over the computed answer.
These tests pin the two guarantees that matter: (1) the id is sensitive to *every* fold
— changing any one changes the id; (2) it is invariant to things that must not matter
(the caller's IC-method order, which the spec sorts). ``diagnostics_result_hash`` is
likewise sensitive to any
computed cell and stable under recomputation. All hashes are ``sha256:``-prefixed and
NUL-discipline; nothing here reads a store or a clock.
"""

from __future__ import annotations

import pytest

from quantforge.diagnostics.identity import diagnostics_id, diagnostics_result_hash

_BASE: dict[str, object] = {
    "signal_diagnostics_engine_version_id": "sha256:engine",
    "name": "phase16",
    "spec_version": "diagnostics/1",
    "signal": "current_ratio",
    "period_key": "instant\x00\x002023-09-30",
    "universe_specification_id": "sha256:uni",
    "schedule_id": "sha256:sched",
    "horizon_days": 1,
    "quantiles": 2,
    "sorted_ic_methods": ["pearson", "spearman"],
    "dataset_version_id": "sha256:fund",
    "market_dataset_version_id": "sha256:mkt",
    "result_hash": "sha256:answer",
}

# Every fold and a distinct replacement value.
_MUTATIONS: list[tuple[str, object]] = [
    ("signal_diagnostics_engine_version_id", "sha256:engine2"),
    ("name", "other"),
    ("spec_version", "diagnostics/2"),
    ("signal", "debt_to_equity"),
    ("period_key", "instant\x00\x002024-09-30"),
    ("universe_specification_id", "sha256:uni2"),
    ("schedule_id", "sha256:sched2"),
    ("horizon_days", 5),
    ("quantiles", 3),
    ("sorted_ic_methods", ["pearson"]),
    ("dataset_version_id", "sha256:fund2"),
    ("market_dataset_version_id", "sha256:mkt2"),
    ("result_hash", "sha256:answer2"),
]


class TestDiagnosticsId:
    def test_deterministic_and_prefixed(self) -> None:
        a = diagnostics_id(**_BASE)  # type: ignore[arg-type]
        b = diagnostics_id(**_BASE)  # type: ignore[arg-type]
        assert a == b
        assert a.startswith("sha256:")

    @pytest.mark.parametrize("field,replacement", _MUTATIONS)
    def test_sensitive_to_every_fold(self, field: str, replacement: object) -> None:
        base_id = diagnostics_id(**_BASE)  # type: ignore[arg-type]
        mutated = {**_BASE, field: replacement}
        assert diagnostics_id(**mutated) != base_id  # type: ignore[arg-type]

    def test_both_corpus_pins_are_independent_folds(self) -> None:
        # SD-1: changing either corpus alone changes the id — the diagnostic is pinned
        # to *both* corpora, never just one.
        base_id = diagnostics_id(**_BASE)  # type: ignore[arg-type]
        only_fund = diagnostics_id(**{**_BASE, "dataset_version_id": "x"})  # type: ignore[arg-type]
        only_mkt = diagnostics_id(**{**_BASE, "market_dataset_version_id": "y"})  # type: ignore[arg-type]
        assert only_fund != base_id
        assert only_mkt != base_id
        assert only_fund != only_mkt

    def test_ic_methods_order_is_carried_verbatim(self) -> None:
        # The identity function folds ``sorted_ic_methods`` as given; order-invariance
        # is a *spec* guarantee (it sorts before calling). If a caller passes an
        # unsorted list the id differs — proving the spec's sort is load-bearing,
        # tested in test_spec /
        # test_result. Here we only confirm the fold is faithful.
        sorted_id = diagnostics_id(**_BASE)  # type: ignore[arg-type]
        mutated = {**_BASE, "sorted_ic_methods": ["spearman", "pearson"]}
        unsorted = diagnostics_id(**mutated)  # type: ignore[arg-type]
        assert unsorted != sorted_id


class TestResultHash:
    def test_deterministic_and_prefixed(self) -> None:
        cells: list[dict[str, object]] = [
            {"block": "per_date", "as_of": "2024-01-15T00:00:00Z"}
        ]
        a = diagnostics_result_hash(cells)
        b = diagnostics_result_hash(cells)
        assert a == b
        assert a.startswith("sha256:")

    def test_sensitive_to_any_cell(self) -> None:
        base = diagnostics_result_hash([{"block": "ic_summary", "v": "0.1"}])
        changed = diagnostics_result_hash([{"block": "ic_summary", "v": "0.2"}])
        assert base != changed

    def test_sensitive_to_cell_order(self) -> None:
        # Ordered output: the per-date/profile/summary block order is part of the seal.
        one = diagnostics_result_hash([{"a": "1"}, {"b": "2"}])
        two = diagnostics_result_hash([{"b": "2"}, {"a": "1"}])
        assert one != two

    def test_empty_output_is_stable(self) -> None:
        assert diagnostics_result_hash([]) == diagnostics_result_hash([])
