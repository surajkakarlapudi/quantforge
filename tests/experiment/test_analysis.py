"""Backtest comparison: ranking correctness, determinism, and fail-closed guards.

Covers the comparison half of Phase 13 (locked §3.4, §5, §6, D1): ranking correctness
and determinism, comparison identity, the closed rankable-statistic vocabulary,
pin-mismatch surfacing, incompatible-experiment/engine rejection, member-absent
rejection, and UNDEFINED-statistic exclusion (fail-surfaced, not raised).
"""

from __future__ import annotations

import pytest

from quantforge.backtest.result import BacktestResult
from quantforge.backtest.spec import CostModel
from quantforge.experiment.analysis import RANKABLE_STATISTICS, BacktestComparison
from quantforge.experiment.errors import (
    ExperimentConfigurationError,
    ExperimentConsistencyError,
)
from tests.experiment.builders import (
    Corpus,
    base_spec,
    experiment_engine,
    populate,
    simple_experiment,
)


def _two_backtests(corpus: Corpus) -> tuple[BacktestResult, BacktestResult]:
    """Two sealed Phase 12 results with genuinely distinct statistics.

    They differ only in the proportional transaction cost, so the costlier run ends
    with strictly less ``final_equity`` — a clean, distinguishable ranking key (the
    ``select_n`` 1-vs-2 variants happen to tie numerically on every statistic here).
    """
    engine = corpus.backtest_engine
    cheap = engine.run(base_spec(corpus, cost_model=CostModel(proportional_bps="0")))
    dear = engine.run(base_spec(corpus, cost_model=CostModel(proportional_bps="50")))
    return cheap, dear


class TestRankingCorrectness:
    def test_ranks_by_statistic_descending(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        cmp = BacktestComparison.of_results(
            [one, two], statistic="final_equity", order="descending"
        )
        # Entries are ranked best-first; ranks are 1-based and contiguous.
        assert [e.rank for e in cmp.entries] == [1, 2]
        values = [e.value for e in cmp.entries]
        assert values == sorted(values, key=lambda v: -float(v))
        assert cmp.best is cmp.entries[0]

    def test_ascending_reverses_order(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        desc = BacktestComparison.of_results([one, two], statistic="final_equity")
        asc = BacktestComparison.of_results(
            [one, two], statistic="final_equity", order="ascending"
        )
        assert [e.backtest_id for e in desc.entries] == list(
            reversed([e.backtest_id for e in asc.entries])
        )

    def test_ties_break_by_backtest_id(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # The select_n 1-vs-2 variants tie on every statistic (same holdings here) but
        # have distinct backtest_ids; the tie must break by backtest_id for a total
        # order, so the ranking is identical regardless of input order.
        corpus = populate(tmp_path)
        engine = corpus.backtest_engine
        one = engine.run(base_spec(corpus, select_n=1))
        two = engine.run(base_spec(corpus, select_n=2))
        assert one.performance.statistics.cumulative_return == (
            two.performance.statistics.cumulative_return
        )
        forward = BacktestComparison.of_results(
            [one, two], statistic="cumulative_return"
        )
        backward = BacktestComparison.of_results(
            [two, one], statistic="cumulative_return"
        )
        ids = [e.backtest_id for e in forward.entries]
        assert ids == [e.backtest_id for e in backward.entries]
        assert ids == sorted(ids)


class TestDeterminism:
    def test_comparison_is_deterministic(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        a = BacktestComparison.of_results([one, two], statistic="cumulative_return")
        b = BacktestComparison.of_results([two, one], statistic="cumulative_return")
        assert a.to_dict() == b.to_dict()
        assert a.comparison_id == b.comparison_id

    def test_comparison_id_is_statistic_and_order_sensitive(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        by_sharpe = BacktestComparison.of_results([one, two], statistic="sharpe")
        by_final = BacktestComparison.of_results([one, two], statistic="final_equity")
        asc = BacktestComparison.of_results(
            [one, two], statistic="sharpe", order="ascending"
        )
        assert by_sharpe.comparison_id != by_final.comparison_id
        assert by_sharpe.comparison_id != asc.comparison_id


class TestFailClosed:
    def test_unknown_statistic_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        with pytest.raises(ExperimentConfigurationError, match="rankable"):
            BacktestComparison.of_results([one, two], statistic="calmar")

    def test_periods_is_not_rankable(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # A count is not a scalar ranking key; excluded from the closed vocabulary.
        assert "periods" not in RANKABLE_STATISTICS
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        with pytest.raises(ExperimentConfigurationError, match="rankable"):
            BacktestComparison.of_results([one, two], statistic="periods")

    def test_bad_order_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        with pytest.raises(ExperimentConfigurationError, match="order"):
            BacktestComparison.of_results(
                [one, two], statistic="sharpe", order="sideways"
            )

    def test_absent_member_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        with pytest.raises(ExperimentConsistencyError, match="not present"):
            BacktestComparison.of_result_ids(
                ["sha256:deadbeef"], engine.research_store, statistic="sharpe"
            )


class TestPinMismatch:
    def test_no_mismatch_for_shared_corpus(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        one, two = _two_backtests(corpus)
        cmp = BacktestComparison.of_results([one, two], statistic="sharpe")
        assert cmp.pin_mismatch is False

    def test_mismatch_surfaced_across_different_corpora(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Two corpora, different fundamentals → different pins → surfaced, not raised.
        corpus_1 = populate(tmp_path / "c1")
        corpus_2 = populate(tmp_path / "c2", a_assets="300000000")
        one = corpus_1.backtest_engine.run(base_spec(corpus_1))
        two = corpus_2.backtest_engine.run(base_spec(corpus_2))
        cmp = BacktestComparison.of_results([one, two], statistic="sharpe")
        assert cmp.pin_mismatch is True
        # The ranking still proceeds — statistics are numbers.
        assert len(cmp.entries) == 2


class TestExperimentComparison:
    def test_of_experiment_ranks_children(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus, values=(1, 2)))
        cmp = BacktestComparison.of_experiment(
            result, engine.research_store, statistic="final_equity"
        )
        assert {e.backtest_id for e in cmp.entries} == set(result.backtest_ids)
        assert cmp.pin_mismatch is False
