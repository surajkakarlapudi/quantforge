"""ReportEngine: resolve, verify, seal, persist — determinism & fail-closed guards.

Covers the orchestration half of Phase 14 (locked §7, §13, §15, D1, D5, D8): the same
spec over the same sidecar seals a byte-identical report, references pin the subject by
content hash, comparisons are recomputed by intent and pinned by ``comparison_id``
(Phase 13 analysis is never modified), the report persists write-once to the shared
sidecar, and any missing/absent reference fails closed.
"""

from __future__ import annotations

import pytest

from quantforge.report.errors import ReportConsistencyError
from quantforge.report.result import BOUNDARY_PIT, ResearchReport
from quantforge.report.spec import ComparisonDirective
from tests.report.builders import (
    backtest_report_spec,
    experiment_report_spec,
    populate,
    report_engine,
    seal_backtest,
    seal_experiment,
)


class TestBacktestReport:
    def test_build_references_the_subject_backtest(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        assert report.scope == "backtest"
        assert len(report.references) == 1
        ref = report.references[0]
        assert ref.kind == "backtest"
        assert ref.reference_id == backtest.backtest_id
        assert ref.content_hash == backtest.result_hash
        assert report.boundary_kind == BOUNDARY_PIT

    def test_absent_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = report_engine(corpus)
        with pytest.raises(ReportConsistencyError, match="not present"):
            engine.build(backtest_report_spec("sha256:deadbeef"))


class TestExperimentReport:
    def test_build_references_experiment_and_comparison(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        report = engine.build(experiment_report_spec(experiment.experiment_result_id))
        kinds = [ref.kind for ref in report.references]
        assert kinds == ["experiment", "comparison"]
        exp_ref, cmp_ref = report.references
        assert exp_ref.reference_id == experiment.experiment_result_id
        assert exp_ref.content_hash == experiment.result_hash
        # A comparison self-addresses: reference_id == content_hash == comparison_id.
        assert cmp_ref.reference_id == cmp_ref.content_hash
        assert cmp_ref.detail["statistic"] == "final_equity"
        assert cmp_ref.detail["member_scope"] == "experiment_children"

    def test_comparison_pins_recomputed_comparison_id(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from quantforge.experiment.analysis import BacktestComparison

        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        report = engine.build(experiment_report_spec(experiment.experiment_result_id))
        recomputed = BacktestComparison.of_experiment(
            experiment, engine.research_store, statistic="final_equity"
        )
        cmp_ref = report.references[1]
        assert cmp_ref.content_hash == recomputed.comparison_id

    def test_directives_are_sorted_deterministically(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        spec = experiment_report_spec(
            experiment.experiment_result_id,
            comparisons=(
                ComparisonDirective(statistic="sharpe"),
                ComparisonDirective(statistic="final_equity"),
            ),
        )
        report = engine.build(spec)
        comparison_stats: list[str] = []
        for ref in report.references:
            if ref.kind == "comparison":
                statistic = ref.detail["statistic"]
                assert isinstance(statistic, str)
                comparison_stats.append(statistic)
        assert comparison_stats == sorted(comparison_stats)


class TestDeterminism:
    def test_identical_spec_yields_identical_report(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        spec = experiment_report_spec(experiment.experiment_result_id)
        first = engine.build(spec)
        second = engine.build(spec)
        assert first.report_result_id == second.report_result_id
        assert first.to_dict() == second.to_dict()


class TestSidecar:
    def test_report_is_persisted_write_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        assert engine.research_store.has(report.report_result_id)

    def test_report_round_trips_from_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        loaded = engine.research_store.read_as(
            report.report_result_id, ResearchReport.from_dict
        )
        assert loaded is not None
        assert loaded.to_dict() == report.to_dict()


class TestWorkspaceWiring:
    def test_report_engine_is_cached(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        assert corpus.workspace.report_engine is corpus.workspace.report_engine

    def test_report_engine_shares_the_research_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # The report must resolve exactly the artifacts the backtest engine sealed.
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        assert engine.research_store is corpus.workspace.research_result_store
        assert engine.research_store.has(backtest.backtest_id)
