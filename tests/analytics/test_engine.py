"""AnalyticsEngine: resolve, verify, compute, seal, persist — end to end.

Covers proposal §I / §M / §O / §P / §Q / D1 / D3: the engine analyses only
already-sealed PIT-correct backtests from the shared sidecar, computes the absolute (+
relative) + VaR blocks, seals a content-addressed record write-once, and fails closed on
a missing / drifted reference, a too-short subject, or an incommensurable benchmark. The
same spec over the same immutable sidecar rebuilds a byte-identical record.
"""

from __future__ import annotations

import pytest

from quantforge.analytics.engine import AnalyticsEngine
from quantforge.analytics.errors import (
    AnalyticsConfigurationError,
    AnalyticsConsistencyError,
)
from quantforge.analytics.model import ABSOLUTE_KEYS, RELATIVE_KEYS
from quantforge.analytics.result import BOUNDARY_PIT, PerformanceAnalytics
from tests.analytics.builders import (
    FOUR_INSTANTS,
    analytics_engine,
    analytics_spec,
    multi_period_corpus,
    seal_benchmark,
    seal_subject,
)
from tests.backtest.builders import make_spec


class TestAbsoluteOnly:
    def test_computes_the_full_absolute_block(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(analytics_spec(subject.backtest_id))
        assert tuple(key for key, _ in record.absolute) == ABSOLUTE_KEYS
        assert record.relative == ()  # no benchmark → empty relative block
        assert record.boundary_kind == BOUNDARY_PIT
        assert record.periods == 3
        assert record.subject_ref == (subject.backtest_id, subject.result_hash)
        assert record.benchmark_ref is None

    def test_var_block_matches_requested_confidences(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(
            analytics_spec(subject.backtest_id, var_confidences=("0.95", "0.99"))
        )
        assert [c for c, _, _ in record.var] == ["0.95", "0.99"]

    def test_carries_the_subject_corpus_pins(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(analytics_spec(subject.backtest_id))
        assert record.dataset_version_ids == (subject.dataset_version_id,)
        assert record.market_dataset_version_ids == (subject.market_dataset_version_id,)


class TestBenchmarkRelative:
    def test_computes_the_relative_block(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        benchmark = seal_benchmark(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(
            analytics_spec(subject.backtest_id, benchmark_id=benchmark.backtest_id)
        )
        assert tuple(key for key, _ in record.relative) == RELATIVE_KEYS
        assert record.benchmark_ref == (benchmark.backtest_id, benchmark.result_hash)

    def test_shared_corpus_pins_do_not_flag_mismatch(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        benchmark = seal_benchmark(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(
            analytics_spec(subject.backtest_id, benchmark_id=benchmark.backtest_id)
        )
        # Both ran over the same corpus snapshot → one distinct pin each → no mismatch.
        assert record.pin_mismatch is False


class TestFailClosed:
    def test_absent_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        engine = analytics_engine(corpus)
        with pytest.raises(AnalyticsConsistencyError, match="not present"):
            engine.compute(analytics_spec("sha256:deadbeef"))

    def test_absent_benchmark_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        with pytest.raises(AnalyticsConsistencyError, match="not present"):
            engine.compute(
                analytics_spec(subject.backtest_id, benchmark_id="sha256:deadbeef")
            )

    def test_too_short_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # The default (two-instant) schedule yields a single return — below the floor.
        corpus = multi_period_corpus(tmp_path)
        short = corpus.backtest_engine.run(make_spec(corpus.backtest_engine))
        engine = analytics_engine(corpus)
        with pytest.raises(AnalyticsConfigurationError, match="at least"):
            engine.compute(analytics_spec(short.backtest_id))

    def test_incommensurable_schedule_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from quantforge.backtest.schedule import RebalanceSchedule

        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        # A benchmark on a different (three-instant) schedule → distinct schedule_id.
        alt = RebalanceSchedule.of(list(FOUR_INSTANTS.instants[:3]))
        benchmark = seal_benchmark(corpus, schedule=alt)
        engine = analytics_engine(corpus)
        with pytest.raises(AnalyticsConsistencyError, match="schedule"):
            engine.compute(
                analytics_spec(subject.backtest_id, benchmark_id=benchmark.backtest_id)
            )

    def test_non_spec_argument_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        engine = analytics_engine(corpus)
        with pytest.raises(AnalyticsConfigurationError, match="AnalyticsSpecification"):
            engine.compute("not-a-spec")  # type: ignore[arg-type]

    def test_drifted_subject_fails_closed(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        import json

        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        # Rewrite the sealed record's stored result_hash so its ledger no longer
        # recomputes to it — the engine must refuse to analyse a drifted record.
        store = engine.research_store
        slug = subject.backtest_id.replace(":", "-")
        path = store.root / "research" / f"{slug}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["research_result"]["result_hash"] = "sha256:tampered"
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(AnalyticsConsistencyError, match="drift"):
            engine.compute(analytics_spec(subject.backtest_id))


class TestPersistence:
    def test_record_is_persisted_write_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(analytics_spec(subject.backtest_id))
        assert engine.research_store.has(record.research_result_id)

    def test_record_round_trips_from_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        record = engine.compute(analytics_spec(subject.backtest_id))
        loaded = engine.research_store.read_as(
            record.research_result_id, PerformanceAnalytics.from_dict
        )
        assert loaded is not None
        assert loaded.to_dict() == record.to_dict()

    def test_rebuild_is_idempotent(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        spec = analytics_spec(subject.backtest_id)
        first = engine.compute(spec)
        second = engine.compute(spec)  # write-once no-op, not an error
        assert first.to_dict() == second.to_dict()


class TestReproducibility:
    def test_identical_spec_yields_identical_record(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        benchmark = seal_benchmark(corpus)
        engine = analytics_engine(corpus)
        spec = analytics_spec(subject.backtest_id, benchmark_id=benchmark.backtest_id)
        first = engine.compute(spec)
        second = engine.compute(spec)
        assert first.analytics_id == second.analytics_id
        assert first.to_dict() == second.to_dict()

    def test_independent_workspaces_agree(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Two independently populated corpora produce byte-identical analytics for the
        # same declared request — no machine/order/wall-clock dependence.
        left = multi_period_corpus(tmp_path / "left")
        right = multi_period_corpus(tmp_path / "right")
        subj_l = seal_subject(left)
        subj_r = seal_subject(right)
        assert subj_l.backtest_id == subj_r.backtest_id
        rec_l = analytics_engine(left).compute(analytics_spec(subj_l.backtest_id))
        rec_r = analytics_engine(right).compute(analytics_spec(subj_r.backtest_id))
        assert rec_l.to_dict() == rec_r.to_dict()


class TestWorkspaceWiring:
    def test_analytics_engine_is_cached(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        assert corpus.workspace.analytics_engine is corpus.workspace.analytics_engine

    def test_engine_shares_the_research_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        subject = seal_subject(corpus)
        engine = analytics_engine(corpus)
        assert engine.research_store is corpus.workspace.research_result_store
        assert engine.research_store.has(subject.backtest_id)

    def test_engine_type_from_workspace(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = multi_period_corpus(tmp_path)
        assert isinstance(corpus.workspace.analytics_engine, AnalyticsEngine)
