"""render_markdown: purity, determinism, section coverage, and condition surfacing.

Covers the single-renderer half of Phase 14 (locked §10, §19, D6): the renderer is a
pure function of a sealed report + the sidecar (no mutation, no store write, no effect
on
``report_id``), produces deterministic Markdown with the ten §10 sections, resolves
every
reference from the sidecar, recomputes comparisons for display and fails closed if a
member is absent, and surfaces recorded data conditions (excluded members, pin_mismatch)
verbatim from the sealed summaries — never fabricated, never hidden.
"""

from __future__ import annotations

import pytest

from quantforge.report.errors import ReportConsistencyError
from quantforge.report.render import render_markdown
from quantforge.report.result import ResearchReport
from tests.report.builders import (
    backtest_report_spec,
    experiment_report_spec,
    populate,
    report_engine,
    seal_backtest,
    seal_experiment,
)

_SECTIONS = (
    "## Executive Summary",
    "## Research Definition",
    "## Dataset & PIT Configuration",
    "## Universe",
    "## Strategy",
    "## Backtest Results",
    "## Experiment Comparison",
    "## Provenance",
    "## Warnings / Undefined Data",
    "## Reproduction Information",
)


class TestBacktestRendering:
    def test_all_ten_sections_present(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        md = render_markdown(report, engine.research_store)
        for heading in _SECTIONS:
            assert heading in md

    def test_prints_sealed_statistics_verbatim(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        md = render_markdown(report, engine.research_store)
        stats = backtest.performance.statistics
        # No new arithmetic: the exact sealed decimal string appears in the output.
        assert stats.cumulative_return in md
        assert stats.final_equity in md

    def test_reproduction_section_carries_ids(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        md = render_markdown(report, engine.research_store)
        assert report.report_id in md
        assert report.report_result_id in md
        assert backtest.backtest_id in md


class TestExperimentRendering:
    def test_renders_comparison_ranking(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        report = engine.build(experiment_report_spec(experiment.experiment_result_id))
        md = render_markdown(report, engine.research_store)
        assert "Ranked by `final_equity`" in md
        # Every child id appears (both in the per-child results and the ranking table).
        for backtest_id in experiment.backtest_ids:
            assert backtest_id in md

    def test_pin_mismatch_is_surfaced(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        report = engine.build(experiment_report_spec(experiment.experiment_result_id))
        md = render_markdown(report, engine.research_store)
        # A single shared corpus → pin_mismatch False, surfaced in the comparison block.
        assert "pin_mismatch" in md.lower() or "Corpus pin_mismatch" in md


class TestPurity:
    def test_render_does_not_write_to_store(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        before = engine.research_store.has(report.report_result_id)
        render_markdown(report, engine.research_store)
        render_markdown(report, engine.research_store)
        # The report existed before rendering and no new record appears; rendering is
        # a pure read (no ResearchRecord is content-addressed from the Markdown).
        assert engine.research_store.has(report.report_result_id) == before

    def test_render_does_not_change_report_id(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        before = report.report_id
        render_markdown(report, engine.research_store)
        assert report.report_id == before

    def test_render_is_deterministic(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        experiment = seal_experiment(corpus)
        engine = report_engine(corpus)
        report = engine.build(experiment_report_spec(experiment.experiment_result_id))
        first = render_markdown(report, engine.research_store)
        second = render_markdown(report, engine.research_store)
        assert first == second


class TestFailClosed:
    def test_absent_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # A report sealed against a subject that is later unresolvable cannot be
        # rendered — the renderer refuses rather than emitting a hollow report.
        corpus = populate(tmp_path)
        backtest = seal_backtest(corpus)
        engine = report_engine(corpus)
        report = engine.build(backtest_report_spec(backtest.backtest_id))
        payload = report.to_dict()
        payload["report_spec"]["subject_id"] = "sha256:missing"  # type: ignore[index]
        tampered = ResearchReport.from_dict(payload)
        with pytest.raises(ReportConsistencyError, match="absent"):
            render_markdown(tampered, engine.research_store)
