"""End-to-end engine tests over the synthetic multi-filer corpus (§5, P19-1..5).

These prove the *orchestration*: PIT signal resolution, ex-post forward-return pairing,
quantile leg formation, per-date leg-floor gating, series aggregation, sealing +
write-once persistence, determinism, and the Phase 19 invariants. The exact arithmetic
is proven in ``test_stats``; here the numbers are checked for structure and coverage.
Synthetic data only, fully offline.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.factorportfolio.engine import FactorPortfolioEngine
from quantforge.factorportfolio.errors import (
    FactorPortfolioConfigurationError,
    FactorPortfolioConsistencyError,
)
from quantforge.factorportfolio.model import FactorPortfolioStatus, LegKind
from quantforge.factorportfolio.result import FactorPortfolio
from tests.factorportfolio.builders import (
    EVAL_1,
    EVAL_2,
    cik_for,
    factor_portfolio_engine,
    make_spec,
    populate,
)


def _company_id(index: int) -> str:
    return f"cik:{cik_for(index)}"


def _construct(
    tmp_path: Path, **spec_kwargs: object
) -> tuple[FactorPortfolioEngine, FactorPortfolio]:
    n_filers = spec_kwargs.pop("n_filers", 5)
    assert isinstance(n_filers, int)
    corpus = populate(tmp_path, n_filers=n_filers)
    engine = factor_portfolio_engine(corpus)
    spec = make_spec(engine, n_filers=n_filers, **spec_kwargs)  # type: ignore[arg-type]
    return engine, engine.construct(spec)


# -- happy path --------------------------------------------------------------


class TestEndToEnd:
    def test_all_dates_resolve_with_known_factor_return(self, tmp_path: Path) -> None:
        _engine, r = _construct(tmp_path)
        assert {p.as_of for p in r.per_period} == {EVAL_1, EVAL_2}
        for period in r.per_period:
            assert period.n_members == 5
            assert period.factor_return.status is FactorPortfolioStatus.KNOWN
            assert period.long_return.status is FactorPortfolioStatus.KNOWN
            assert period.short_return.status is FactorPortfolioStatus.KNOWN

    def test_legs_follow_the_monotone_signal(self, tmp_path: Path) -> None:
        # current_ratio = 2 + i strictly increases in i; Q=2, n=5 -> buckets
        # {0,0,0,1,1}:
        # short = the three lowest-signal filers (0,1,2), long = the two highest (3,4).
        _engine, r = _construct(tmp_path)
        for period in r.per_period:
            assert period.long_membership.kind is LegKind.LONG
            assert period.short_membership.kind is LegKind.SHORT
            assert period.long_membership.company_ids == (
                _company_id(3),
                _company_id(4),
            )
            assert period.short_membership.company_ids == (
                _company_id(0),
                _company_id(1),
                _company_id(2),
            )

    def test_summary_covers_all_valid_periods(self, tmp_path: Path) -> None:
        _engine, r = _construct(tmp_path)
        s = r.summary
        assert s.n_valid_periods == 2
        assert s.cumulative_return.status is FactorPortfolioStatus.KNOWN
        assert s.mean_period_return.status is FactorPortfolioStatus.KNOWN
        assert s.volatility.status is FactorPortfolioStatus.KNOWN
        assert s.annualized_sharpe.status is FactorPortfolioStatus.KNOWN
        assert s.mean_t_stat.status is FactorPortfolioStatus.KNOWN
        assert s.hit_rate.status is FactorPortfolioStatus.KNOWN

    def test_full_coverage_no_drops(self, tmp_path: Path) -> None:
        _engine, r = _construct(tmp_path)
        cov = r.coverage
        assert cov.total_resolved == 10  # 5 members x 2 dates
        assert cov.total_dropped_for_signal == 0
        assert cov.total_dropped_for_return == 0
        assert cov.total_undefined_periods == 0
        for date_cov in cov.per_date:
            assert date_cov.period_status == "known"


# -- persistence + determinism -----------------------------------------------


class TestPersistenceAndDeterminism:
    def test_record_persists_and_round_trips_from_sidecar(self, tmp_path: Path) -> None:
        engine, r = _construct(tmp_path)
        restored = engine.research_store.read_as(
            r.factor_portfolio_id, FactorPortfolio.from_dict
        )
        assert restored is not None
        assert restored.to_dict() == r.to_dict()

    def test_re_construction_is_byte_identical_noop(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = factor_portfolio_engine(corpus)
        spec = make_spec(engine)
        first = engine.construct(spec)
        second = engine.construct(spec)
        assert first.to_dict() == second.to_dict()
        assert first.factor_portfolio_id == second.factor_portfolio_id

    def test_two_independent_corpora_agree(self, tmp_path: Path) -> None:
        _e1, a = _construct(tmp_path / "one")
        _e2, b = _construct(tmp_path / "two")
        assert a.to_dict() == b.to_dict()


# -- P19-2: ex-post, not PIT -------------------------------------------------


class TestP19_2ExPost:
    def test_record_exposes_no_pit_or_as_of_accessor(self, tmp_path: Path) -> None:
        _engine, r = _construct(tmp_path)
        names = dir(r)
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)
        assert r.boundary_kind == "pit"

    def test_record_is_not_a_backtest_result(self, tmp_path: Path) -> None:
        from quantforge.backtest import BacktestResult

        _engine, r = _construct(tmp_path)
        assert not isinstance(r, BacktestResult)


# -- P19-1: corpus-pin verification ------------------------------------------


class TestP19_1CorpusPins:
    def test_mismatched_fundamentals_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = factor_portfolio_engine(corpus)
        tampered = replace(
            make_spec(engine), dataset_version_id="sha256:not-the-corpus"
        )
        with pytest.raises(FactorPortfolioConsistencyError):
            engine.construct(tampered)

    def test_mismatched_market_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = factor_portfolio_engine(corpus)
        tampered = replace(
            make_spec(engine), market_dataset_version_id="sha256:not-the-corpus"
        )
        with pytest.raises(FactorPortfolioConsistencyError):
            engine.construct(tampered)


# -- P19-4: fail-closed pairing, recorded not imputed ------------------------


class TestP19_4Coverage:
    def test_member_without_tradable_security_dropped_for_return(
        self, tmp_path: Path
    ) -> None:
        # Drop filer 4's market security: it is still a fundamentals universe member
        # (its signal resolves) but has no forward return, so it is dropped-for-return
        # at every date - never imputed. Four members remain, still above the leg floor
        # 2*Q=4.
        corpus = populate(tmp_path, market_indices={0, 1, 2, 3})
        engine = factor_portfolio_engine(corpus)
        r = engine.construct(make_spec(engine))
        assert r.coverage.total_dropped_for_return == 2  # filer 4, both dates
        for period in r.per_period:
            assert period.n_members == 4
            assert period.factor_return.status is FactorPortfolioStatus.KNOWN

    def test_below_leg_floor_is_recorded_then_refused(self, tmp_path: Path) -> None:
        # Three filers with Q=2 needs n >= 4, so every date is INSUFFICIENT_MEMBERS ->
        # zero valid periods, which the engine refuses as a configuration error, having
        # *recorded* the per-date UNDEFINED blocks first (never a raise from per-date).
        corpus = populate(tmp_path, n_filers=3)
        engine = factor_portfolio_engine(corpus)
        spec = make_spec(engine, n_filers=3)
        with pytest.raises(FactorPortfolioConfigurationError):
            engine.construct(spec)


# -- fail-closed configuration -----------------------------------------------


class TestFailClosed:
    def test_single_scheduled_date_fails_min_valid_periods(
        self, tmp_path: Path
    ) -> None:
        corpus = populate(tmp_path)
        engine = factor_portfolio_engine(corpus)
        spec = make_spec(engine, schedule=RebalanceSchedule.of([EVAL_1]))
        with pytest.raises(FactorPortfolioConfigurationError):
            engine.construct(spec)
