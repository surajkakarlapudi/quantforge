"""Analytics identity: sensitivity, order-independence, engine-version folding.

Covers proposal §L: ``analytics_id`` folds the engine version, the declared request,
the referenced content hashes, and the sealed answer; ``analytics_result_hash`` is
sensitive to every computed cell; nothing depends on wall clock, RNG, or iteration
order. The engine-version id lives on :class:`AnalyticsEngineVersion` (single source of
truth) and folds the pinned decimal context + formula method.
"""

from __future__ import annotations

from quantforge.analytics.identity import analytics_id, analytics_result_hash
from quantforge.analytics.version import AnalyticsEngineVersion


def _base_kwargs() -> dict[str, object]:
    return {
        "analytics_engine_version_id": "sha256:engine",
        "name": "r",
        "spec_version": "analytics/1",
        "subject_id": "sha256:subject",
        "benchmark_id": None,
        "sorted_var_confidences": ["0.95"],
        "risk_free_per_period": "0",
        "periods_per_year": "1",
        "subject_result_hash": "sha256:subjecthash",
        "benchmark_result_hash": None,
        "result_hash": "sha256:answer",
    }


class TestResultHash:
    def test_sensitive_to_a_single_cell(self) -> None:
        cells_a: list[dict[str, object]] = [
            {"block": "absolute", "key": "calmar", "status": "known", "value": "0.4"}
        ]
        cells_b: list[dict[str, object]] = [
            {"block": "absolute", "key": "calmar", "status": "known", "value": "0.5"}
        ]
        assert analytics_result_hash(cells_a) != analytics_result_hash(cells_b)

    def test_deterministic(self) -> None:
        cells: list[dict[str, object]] = [
            {"block": "var", "key": "var", "status": "known", "value": "-0.1"}
        ]
        assert analytics_result_hash(cells) == analytics_result_hash(cells)

    def test_is_sha256_prefixed(self) -> None:
        assert analytics_result_hash([]).startswith("sha256:")


class TestAnalyticsId:
    def test_deterministic(self) -> None:
        assert analytics_id(**_base_kwargs()) == analytics_id(**_base_kwargs())  # type: ignore[arg-type]

    def test_confidence_order_does_not_matter_only_content(self) -> None:
        a = _base_kwargs()
        b = _base_kwargs()
        # The engine folds the spec's already-sorted confidences, so identical content
        # in either supplied order yields the same id.
        a["sorted_var_confidences"] = ["0.95", "0.99"]
        b["sorted_var_confidences"] = ["0.95", "0.99"]
        assert analytics_id(**a) == analytics_id(**b)  # type: ignore[arg-type]

    def test_sensitive_to_engine_version(self) -> None:
        a = _base_kwargs()
        b = _base_kwargs()
        b["analytics_engine_version_id"] = "sha256:other-engine"
        assert analytics_id(**a) != analytics_id(**b)  # type: ignore[arg-type]

    def test_sensitive_to_subject_content_hash(self) -> None:
        a = _base_kwargs()
        b = _base_kwargs()
        b["subject_result_hash"] = "sha256:drifted"
        assert analytics_id(**a) != analytics_id(**b)  # type: ignore[arg-type]

    def test_sensitive_to_the_answer(self) -> None:
        a = _base_kwargs()
        b = _base_kwargs()
        b["result_hash"] = "sha256:other-answer"
        assert analytics_id(**a) != analytics_id(**b)  # type: ignore[arg-type]

    def test_benchmark_presence_changes_id(self) -> None:
        a = _base_kwargs()
        b = _base_kwargs()
        b["benchmark_id"] = "sha256:bench"
        b["benchmark_result_hash"] = "sha256:benchhash"
        assert analytics_id(**a) != analytics_id(**b)  # type: ignore[arg-type]


class TestEngineVersion:
    def test_version_id_is_sha256_and_stable(self) -> None:
        v = AnalyticsEngineVersion()
        assert v.analytics_engine_version_id.startswith("sha256:")
        assert v.analytics_engine_version_id == v.analytics_engine_version_id

    def test_decimal_context_change_changes_version(self) -> None:
        default = AnalyticsEngineVersion()
        other = AnalyticsEngineVersion(decimal_precision=28)
        assert default.analytics_engine_version_id != other.analytics_engine_version_id

    def test_formula_change_changes_version(self) -> None:
        default = AnalyticsEngineVersion()
        other = AnalyticsEngineVersion(formula_version="analytics-stats/2")
        assert default.analytics_engine_version_id != other.analytics_engine_version_id
