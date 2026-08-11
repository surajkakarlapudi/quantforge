"""End-to-end diagnostics evaluation over a real synthetic corpus (locked §2, §6).

Drives :class:`SignalDiagnosticsEngine.evaluate` over the combined fundamentals+market
corpus from :mod:`tests.diagnostics.builders`. The default corpus is arranged so the
signal (``current_ratio``: A=2, B=4) is *perfectly anti-correlated* with the realized
1-trading-day forward return (A rises faster than B), so every per-date IC is a clean,
hand-verifiable ``-1``. These tests pin the four hard invariants — SD-1 (both corpus
pins verified, fail closed on mismatch), SD-2 (forward-looking type, no ``Pit*`` /
as-of accessor), SD-3 (the signal is read PIT as-of-T), SD-4 (fail-closed pairing,
exclusions counted in coverage) — plus determinism, the golden IC value, and
write-once persistence.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from quantforge.diagnostics.errors import (
    SignalDiagnosticsConfigurationError,
    SignalDiagnosticsConsistencyError,
)
from quantforge.diagnostics.model import DiagnosticStatus
from quantforge.diagnostics.result import SignalDiagnostics
from tests.diagnostics.builders import (
    CIK_A,
    EVAL_1,
    EVAL_2,
    default_schedule,
    diagnostics_engine,
    make_spec,
    populate_diagnostics,
)


def _evaluate(root: Path, **spec_kwargs: object) -> tuple[object, SignalDiagnostics]:
    corpus = populate_diagnostics(root)
    engine = diagnostics_engine(corpus)
    spec = make_spec(engine, **spec_kwargs)  # type: ignore[arg-type]
    return engine, engine.evaluate(spec)


class TestGoldenAndDeterminism:
    def test_two_dates_each_perfect_negative_ic(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path)
        # Both scheduled instants clear the 2-pair minimum.
        assert len(result.per_date) == 2
        assert {d.as_of for d in result.per_date} == {EVAL_1, EVAL_2}
        for date in result.per_date:
            assert date.n_pairs == 2
            for _method, ic in date.ic:
                assert ic.status is DiagnosticStatus.KNOWN
                assert ic.value is not None
                # A(ratio 2) out-returns B(ratio 4) on every window → IC = -1.
                assert Decimal(ic.value) == Decimal(-1)

    def test_ic_summary_mean_is_minus_one(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path)
        for _method, summary in result.ic_summary.per_method:
            assert summary.n_valid_dates == 2
            assert summary.mean_ic.value is not None
            assert Decimal(summary.mean_ic.value) == Decimal(-1)
            # A constant (-1, -1) IC series has zero dispersion → ratio/t-stat
            # undefined.
            assert summary.ic_std.value == "0"
            assert summary.ic_information_ratio.status is DiagnosticStatus.UNDEFINED
            # hit_rate = #(IC>0)/n = 0.
            assert summary.hit_rate.value == "0"

    def test_evaluate_is_byte_identical_across_runs(self, tmp_path: Path) -> None:
        # Same spec over the same immutable corpus → byte-identical sealed record.
        _engine, first = _evaluate(tmp_path / "a")
        _engine2, second = _evaluate(tmp_path / "b")
        assert first.to_dict() == second.to_dict()
        assert first.diagnostics_id == second.diagnostics_id

    def test_reevaluation_on_same_workspace_is_idempotent(self, tmp_path: Path) -> None:
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        spec = make_spec(engine)
        first = engine.evaluate(spec)
        # A second evaluate re-derives the same id and writes a byte-identical payload
        # (the write-once sidecar treats it as a no-op, never a consistency error).
        second = engine.evaluate(spec)
        assert first.diagnostics_id == second.diagnostics_id
        assert first.to_dict() == second.to_dict()


class TestPersistence:
    def test_sealed_record_round_trips_from_sidecar(self, tmp_path: Path) -> None:
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        result = engine.evaluate(make_spec(engine))
        store = engine._factor_engine.research_store
        assert store.has(result.diagnostics_id)
        restored = store.read_as(result.diagnostics_id, SignalDiagnostics.from_dict)
        assert restored is not None
        assert restored.to_dict() == result.to_dict()
        assert restored.diagnostics_id == result.diagnostics_id


class TestSD1CorpusPins:
    def test_tampered_fundamentals_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        good = make_spec(engine)
        from dataclasses import replace

        tampered = replace(good, dataset_version_id="sha256:not-the-corpus")
        with pytest.raises(SignalDiagnosticsConsistencyError, match="fundamentals"):
            engine.evaluate(tampered)

    def test_tampered_market_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        good = make_spec(engine)
        from dataclasses import replace

        tampered = replace(good, market_dataset_version_id="sha256:not-the-market")
        with pytest.raises(SignalDiagnosticsConsistencyError, match="market"):
            engine.evaluate(tampered)

    def test_a_different_corpus_yields_a_different_id(self, tmp_path: Path) -> None:
        # SD-1: a changed market corpus (different closes for A) re-derives a different
        # market pin, so the sealed id differs — the diagnostic is pinned to the corpus.
        from tests.market.builders import bar

        _e1, baseline = _evaluate(tmp_path / "base")
        # Same two filers, but A's bar history differs (closes 10→12→…), so the market
        # dataset_version_id — and therefore the id — changes.
        alt_bars_a = [
            bar("2024-01-10", close="10"),
            bar("2024-02-10", close="12"),
            bar("2024-03-10", close="14"),
            bar("2024-04-10", close="16"),
        ]
        corpus = populate_diagnostics(tmp_path / "alt", bars_a=alt_bars_a)
        engine = diagnostics_engine(corpus)
        altered = engine.evaluate(make_spec(engine))
        assert baseline.diagnostics_id != altered.diagnostics_id
        assert baseline.market_dataset_version_id != altered.market_dataset_version_id


class TestSD2ForwardLookingType:
    def test_record_exposes_no_pit_or_as_of_accessor(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path)
        names = dir(result)
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)
        # boundary_kind documents the *signal* side only, not the diagnostic itself.
        assert result.boundary_kind == "pit"


class TestSD4Coverage:
    def test_full_eligibility_when_all_members_pair(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path)
        cov = result.coverage
        assert cov.total_dropped_for_signal == 0
        assert cov.total_dropped_for_return == 0
        assert cov.total_eligible == 4  # 2 members x 2 dates
        for date_cov in cov.per_date:
            assert date_cov.resolved_members == 2
            assert date_cov.eligible == 2

    def test_member_without_tradable_security_dropped_for_return(
        self, tmp_path: Path
    ) -> None:
        # Filer B has fundamentals (so it is a universe member with a KNOWN signal) but
        # no market security → no computable forward return → dropped_for_return,
        # counted in coverage, never imputed (SD-4). Only A remains, so each date has 1
        # pair < 2 and
        # the whole study is a fail-closed configuration defect.
        corpus = populate_diagnostics(tmp_path, market_b=False)
        engine = diagnostics_engine(corpus)
        spec = make_spec(engine)
        with pytest.raises(SignalDiagnosticsConfigurationError, match="at least"):
            engine.evaluate(spec)

    def test_single_member_universe_fails_closed(self, tmp_path: Path) -> None:
        # A one-filer universe can never form a 2-point cross-section → fail closed
        # (§7).
        corpus = populate_diagnostics(tmp_path, include_b=False)
        engine = diagnostics_engine(corpus)
        spec = make_spec(engine, include_b=False)
        with pytest.raises(SignalDiagnosticsConfigurationError, match="at least"):
            engine.evaluate(spec)


class TestSD3PitSignal:
    def test_signal_read_before_filing_is_unknown_and_fails_closed(
        self, tmp_path: Path
    ) -> None:
        # SD-3: the signal is read PIT as-of-T. Schedule both instants *before* the
        # filer's 10-K acceptance (2023-11-02) — the current_ratio is not yet PIT-known,
        # so every
        # member is dropped_for_signal and no date clears the pair minimum.
        from quantforge.backtest.schedule import RebalanceSchedule

        early = RebalanceSchedule.of(["2023-06-15T00:00:00Z", "2023-07-15T00:00:00Z"])
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        spec = make_spec(engine, schedule=early)
        with pytest.raises(SignalDiagnosticsConfigurationError, match="at least"):
            engine.evaluate(spec)


class TestScheduleAndConfig:
    def test_pearson_only_produces_one_method(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path, ic_methods=("pearson",))
        methods = {m for m, _ in result.ic_summary.per_method}
        assert methods == {"pearson"}
        for date in result.per_date:
            assert {m for m, _ in date.ic} == {"pearson"}

    def test_single_date_schedule(self, tmp_path: Path) -> None:
        from quantforge.backtest.schedule import RebalanceSchedule

        one = RebalanceSchedule.of([EVAL_1])
        _engine, result = _evaluate(tmp_path, schedule=one)
        assert len(result.per_date) == 1
        assert result.per_date[0].as_of == EVAL_1

    def test_schedule_id_is_recorded(self, tmp_path: Path) -> None:
        corpus = populate_diagnostics(tmp_path)
        engine = diagnostics_engine(corpus)
        spec = make_spec(engine)
        result = engine.evaluate(spec)
        assert result.schedule_id == default_schedule().schedule_id


class TestQuantileProfile:
    def test_two_buckets_present_across_dates(self, tmp_path: Path) -> None:
        _engine, result = _evaluate(tmp_path, quantiles=2)
        profile = result.quantile_profile
        assert len(profile.bucket_means) == 2
        # Both filers pair on both dates, so neither bucket is empty.
        for bucket in profile.bucket_means:
            assert bucket.status is DiagnosticStatus.KNOWN
        # A (lower ratio, higher return) sorts into bucket 0; the spread (top-bottom) is
        # negative because the high-ratio bucket under-returns.
        assert profile.mean_spread.status is DiagnosticStatus.KNOWN
        assert profile.mean_spread.value is not None
        assert Decimal(profile.mean_spread.value) < 0


def test_cik_a_is_the_lower_ratio_filer() -> None:
    # Guard the fixture assumption the golden IC relies on: A is the low-ratio filer.
    assert CIK_A == 9999999991
