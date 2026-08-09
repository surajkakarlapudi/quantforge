"""Experiment engine: orchestration, determinism, reuse, sealing, and provenance.

Covers the run half of Phase 13 (locked §3.3, §4, D2, D4, D5): identical experiment →
identical id/result, fixed corpus pinning threaded to children, the annualization
convention threaded unchanged (D5), the write-once sidecar (D4), full provenance and
backtest-id preservation, the ``ExperimentResult`` byte-identical round trip, and
interaction with existing Phase 12 backtests.
"""

from __future__ import annotations

from quantforge.backtest.result import BacktestResult
from quantforge.experiment.result import ExperimentResult
from tests.experiment.builders import (
    base_spec,
    experiment_engine,
    populate,
    simple_experiment,
)


class TestRunDeterminism:
    def test_identical_experiment_yields_identical_result(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        spec = simple_experiment(corpus)
        first = engine.run(spec)
        second = engine.run(spec)
        assert first.experiment_result_id == second.experiment_result_id
        assert first.result_hash == second.result_hash
        assert first.to_dict() == second.to_dict()

    def test_experiment_id_matches_spec_derivation(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        spec = simple_experiment(corpus)
        result = engine.run(spec)
        assert result.experiment_id == spec.experiment_id(
            risk_free_per_period="0", periods_per_year="1"
        )

    def test_run_ordering_is_deterministic(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus, values=(1, 2)))
        # Runs follow the deterministic expansion order (coordinate-sorted).
        coords = [run.coordinate for run in result.runs]
        assert coords == sorted(coords)


class TestCorpusPinning:
    def test_children_carry_the_base_pins(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Locked D2: the experiment surfaces the single inherited pin pair, and every
        # child backtest was run under it (BT-1 verification passed for each).
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        base = base_spec(corpus)
        result = engine.run(simple_experiment(corpus))
        assert result.dataset_version_id == base.dataset_version_id
        assert result.market_dataset_version_id == base.market_dataset_version_id
        store = engine.research_store
        for backtest_id in result.backtest_ids:
            child = store.read_as(backtest_id, BacktestResult.from_dict)
            assert child is not None
            assert child.dataset_version_id == base.dataset_version_id
            assert child.market_dataset_version_id == base.market_dataset_version_id


class TestAnnualizationConvention:
    def test_convention_threads_unchanged_to_children(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Locked D5: the convention is a run arg, threaded to every child, not swept.
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(
            simple_experiment(corpus), risk_free_per_period="0", periods_per_year="12"
        )
        assert result.periods_per_year == "12"
        store = engine.research_store
        for backtest_id in result.backtest_ids:
            child = store.read_as(backtest_id, BacktestResult.from_dict)
            assert child is not None
            assert child.performance.periods_per_year == "12"

    def test_convention_changes_experiment_identity(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        spec = simple_experiment(corpus)
        a = engine.run(spec, periods_per_year="1")
        b = engine.run(spec, periods_per_year="12")
        assert a.experiment_id != b.experiment_id
        assert a.experiment_result_id != b.experiment_result_id

    def test_convention_is_canonicalized(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # "1" and "1.0" and "01" fold to one canonical convention → one identity.
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        spec = simple_experiment(corpus)
        a = engine.run(spec, periods_per_year="1")
        b = engine.run(spec, periods_per_year="01")
        assert a.experiment_id == b.experiment_id
        assert a.periods_per_year == b.periods_per_year == "1"


class TestSidecar:
    def test_experiment_is_persisted_write_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus))
        store = engine.research_store
        assert store.has(result.experiment_result_id)
        # Re-running is an idempotent no-op (byte-identical payload under the same id).
        again = engine.run(simple_experiment(corpus))
        assert again.experiment_result_id == result.experiment_result_id

    def test_experiment_round_trips_from_sidecar(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus))
        loaded = engine.research_store.read_as(
            result.experiment_result_id, ExperimentResult.from_dict
        )
        assert loaded is not None
        assert loaded.to_dict() == result.to_dict()


class TestProvenance:
    def test_every_child_backtest_id_is_preserved(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus, values=(1, 2)))
        assert len(result.backtest_ids) == 2
        # Each id resolves to a sealed Phase 12 result in the shared sidecar.
        for backtest_id in result.backtest_ids:
            assert engine.research_store.has(backtest_id)

    def test_result_records_base_request_and_axes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        spec = simple_experiment(corpus)
        result = engine.run(spec)
        assert result.base_backtest_request == base_spec(corpus).to_dict()
        assert result.axis_ids == spec.sorted_axis_ids()

    def test_interacts_with_standalone_phase12_backtest(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # A child of the experiment is byte-identical to the same spec run directly by
        # Phase 12 — comparative research consumes already-sealed Phase 12 results.
        corpus = populate(tmp_path)
        bt_engine = corpus.backtest_engine
        direct = bt_engine.run(base_spec(corpus))  # select_n defaults to 1
        exp_engine = experiment_engine(corpus)
        result = exp_engine.run(simple_experiment(corpus, values=(1, 2)))
        # The select_n=1 child shares the standalone backtest's id and sealed payload.
        assert direct.backtest_id in result.backtest_ids
        reloaded = exp_engine.research_store.read_as(
            direct.backtest_id, BacktestResult.from_dict
        )
        assert reloaded is not None
        assert reloaded.to_dict() == direct.to_dict()


class TestResultRoundTrip:
    def test_experiment_result_roundtrip_is_byte_identical(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        engine = experiment_engine(corpus)
        result = engine.run(simple_experiment(corpus))
        rebuilt = ExperimentResult.from_dict(result.to_dict())
        assert rebuilt.to_dict() == result.to_dict()
        assert rebuilt.experiment_result_id == result.experiment_result_id
        assert rebuilt.result_hash == result.result_hash

    def test_backtest_result_roundtrip_is_byte_identical(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # D3: the additive BacktestResult.from_dict round-trips byte-identically.
        corpus = populate(tmp_path)
        direct = corpus.backtest_engine.run(base_spec(corpus))
        rebuilt = BacktestResult.from_dict(direct.to_dict())
        assert rebuilt.to_dict() == direct.to_dict()
        assert rebuilt.backtest_id == direct.backtest_id
        assert rebuilt.result_hash == direct.result_hash
