"""ReportSpecification / ComparisonDirective: validation & the closed vocabulary.

Covers the declarative-request half of Phase 14 (locked §8.3, §18, D7): the closed
scope vocabulary, comparison directives valid only on an experiment scope, reuse of
Phase 13's rankable-statistic vocabulary, duplicate-directive rejection, and the
deterministic ``to_dict`` / sorted-descriptor shape.
"""

from __future__ import annotations

import pytest

from quantforge.report.errors import ReportConfigurationError
from quantforge.report.spec import (
    REPORT_SCOPES,
    REPORT_SPEC_VERSION,
    ComparisonDirective,
    ReportSpecification,
)


class TestReportSpecificationValidation:
    def test_empty_name_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="non-empty name"):
            ReportSpecification(name="", scope="backtest", subject_id="sha256:abc")

    def test_unknown_scope_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="closed v1 vocabulary"):
            ReportSpecification(name="r", scope="portfolio", subject_id="sha256:abc")

    def test_empty_subject_id_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="subject_id"):
            ReportSpecification(name="r", scope="backtest", subject_id="")

    def test_scope_vocabulary_is_closed(self) -> None:
        assert REPORT_SCOPES == ("backtest", "experiment")

    def test_valid_backtest_spec_constructs(self) -> None:
        spec = ReportSpecification(name="r", scope="backtest", subject_id="sha256:abc")
        assert spec.spec_version == REPORT_SPEC_VERSION
        assert spec.comparisons == ()


class TestComparisonDirectiveScope:
    def test_comparison_on_backtest_scope_is_rejected(self) -> None:
        # A single backtest has no members to rank (locked D7).
        with pytest.raises(ReportConfigurationError, match="only valid"):
            ReportSpecification(
                name="r",
                scope="backtest",
                subject_id="sha256:abc",
                comparisons=(ComparisonDirective(statistic="sharpe"),),
            )

    def test_comparison_on_experiment_scope_is_allowed(self) -> None:
        spec = ReportSpecification(
            name="r",
            scope="experiment",
            subject_id="sha256:abc",
            comparisons=(ComparisonDirective(statistic="sharpe"),),
        )
        assert len(spec.comparisons) == 1

    def test_duplicate_directive_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="duplicate"):
            ReportSpecification(
                name="r",
                scope="experiment",
                subject_id="sha256:abc",
                comparisons=(
                    ComparisonDirective(statistic="sharpe", order="descending"),
                    ComparisonDirective(statistic="sharpe", order="descending"),
                ),
            )

    def test_same_statistic_distinct_order_is_allowed(self) -> None:
        spec = ReportSpecification(
            name="r",
            scope="experiment",
            subject_id="sha256:abc",
            comparisons=(
                ComparisonDirective(statistic="sharpe", order="descending"),
                ComparisonDirective(statistic="sharpe", order="ascending"),
            ),
        )
        assert len(spec.comparisons) == 2


class TestComparisonDirectiveVocabulary:
    def test_unknown_statistic_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="rankable"):
            ComparisonDirective(statistic="calmar")

    def test_periods_is_not_rankable(self) -> None:
        with pytest.raises(ReportConfigurationError, match="rankable"):
            ComparisonDirective(statistic="periods")

    def test_bad_order_is_rejected(self) -> None:
        with pytest.raises(ReportConfigurationError, match="order"):
            ComparisonDirective(statistic="sharpe", order="sideways")


class TestSerialization:
    def test_to_dict_shape(self) -> None:
        spec = ReportSpecification(
            name="r",
            scope="experiment",
            subject_id="sha256:abc",
            comparisons=(ComparisonDirective(statistic="final_equity"),),
        )
        assert spec.to_dict() == {
            "spec_version": REPORT_SPEC_VERSION,
            "name": "r",
            "scope": "experiment",
            "subject_id": "sha256:abc",
            "comparisons": [{"statistic": "final_equity", "order": "descending"}],
        }

    def test_sorted_comparison_descriptors_are_order_independent(self) -> None:
        forward = ReportSpecification(
            name="r",
            scope="experiment",
            subject_id="sha256:abc",
            comparisons=(
                ComparisonDirective(statistic="sharpe"),
                ComparisonDirective(statistic="final_equity"),
            ),
        )
        backward = ReportSpecification(
            name="r",
            scope="experiment",
            subject_id="sha256:abc",
            comparisons=(
                ComparisonDirective(statistic="final_equity"),
                ComparisonDirective(statistic="sharpe"),
            ),
        )
        assert (
            forward.sorted_comparison_descriptors()
            == backward.sorted_comparison_descriptors()
        )
