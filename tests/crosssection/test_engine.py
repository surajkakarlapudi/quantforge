"""End-to-end engine tests over the synthetic multi-filer corpus (§6, XS-1..4).

These prove the *orchestration*: PIT signal resolution, ex-post forward-return pairing,
per-date DoF gating, Fama-MacBeth aggregation, sealing + write-once persistence,
determinism, and the four Phase 18 invariants. The exact arithmetic is proven in
``test_stats``; here the numbers are checked for structure and coverage. Synthetic data
only, fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.crosssection.engine import CrossSectionalRegressionEngine
from quantforge.crosssection.errors import (
    CrossSectionConfigurationError,
    CrossSectionConsistencyError,
)
from quantforge.crosssection.model import CrossSectionStatus
from quantforge.crosssection.result import CrossSectionalRegression
from quantforge.crosssection.spec import FactorSpec
from tests.crosssection.builders import (
    EVAL_1,
    EVAL_2,
    PERIOD,
    crosssection_engine,
    make_spec,
    populate,
)


def _estimate(
    tmp_path: Path, **spec_kwargs: object
) -> tuple[CrossSectionalRegressionEngine, CrossSectionalRegression]:
    n_filers = spec_kwargs.pop("n_filers", 5)
    assert isinstance(n_filers, int)
    corpus = populate(tmp_path, n_filers=n_filers)
    engine = crosssection_engine(corpus)
    spec = make_spec(engine, **spec_kwargs)  # type: ignore[arg-type]
    return engine, engine.estimate(spec)


# -- happy path --------------------------------------------------------------


class TestEndToEnd:
    def test_all_dates_and_members_resolve(self, tmp_path: Path) -> None:
        _engine, reg = _estimate(tmp_path)
        assert {d.as_of for d in reg.per_date} == {EVAL_1, EVAL_2}
        for date_block in reg.per_date:
            assert date_block.n_members == 5
            for _, cell in date_block.coefficients:
                assert cell.status is CrossSectionStatus.KNOWN

    def test_premia_cover_intercept_and_both_factors(self, tmp_path: Path) -> None:
        _engine, reg = _estimate(tmp_path)
        labels = [p.label for p in reg.premia]
        assert labels == ["alpha", "factor_1", "factor_2"]
        for premium in reg.premia:
            assert premium.n_valid_dates == 2
            assert premium.mean.status is CrossSectionStatus.KNOWN
            assert premium.std_error.status is CrossSectionStatus.KNOWN
            assert premium.t_stat.status is CrossSectionStatus.KNOWN

    def test_full_coverage_no_drops(self, tmp_path: Path) -> None:
        _engine, reg = _estimate(tmp_path)
        cov = reg.coverage
        assert cov.total_eligible == 10  # 5 members x 2 dates
        assert cov.total_dropped_for_signal == 0
        assert cov.total_dropped_for_return == 0
        assert cov.total_dropped_for_singular_date == 0
        for date_cov in cov.per_date:
            assert date_cov.regression_status == "known"


# -- persistence + determinism -----------------------------------------------


class TestPersistenceAndDeterminism:
    def test_record_persists_and_round_trips_from_sidecar(self, tmp_path: Path) -> None:
        engine, reg = _estimate(tmp_path)
        store = engine._factor_engine.research_store
        restored = store.read_as(
            reg.crosssection_id, CrossSectionalRegression.from_dict
        )
        assert restored is not None
        assert restored.to_dict() == reg.to_dict()

    def test_re_estimation_is_byte_identical_noop(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = crosssection_engine(corpus)
        spec = make_spec(engine)
        first = engine.estimate(spec)
        second = engine.estimate(spec)
        assert first.to_dict() == second.to_dict()
        assert first.crosssection_id == second.crosssection_id

    def test_two_independent_corpora_agree(self, tmp_path: Path) -> None:
        _e1, a = _estimate(tmp_path / "one")
        _e2, b = _estimate(tmp_path / "two")
        assert a.to_dict() == b.to_dict()


# -- XS-2: ex-post, not PIT --------------------------------------------------


class TestXS2ExPost:
    def test_record_exposes_no_pit_or_as_of_accessor(self, tmp_path: Path) -> None:
        _engine, reg = _estimate(tmp_path)
        names = dir(reg)
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)
        assert reg.boundary_kind == "pit"


# -- XS-1: corpus-pin verification -------------------------------------------


class TestXS1CorpusPins:
    def test_mismatched_fundamentals_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = crosssection_engine(corpus)
        good = make_spec(engine)
        from dataclasses import replace

        tampered = replace(good, dataset_version_id="sha256:not-the-corpus")
        with pytest.raises(CrossSectionConsistencyError):
            engine.estimate(tampered)

    def test_mismatched_market_pin_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = crosssection_engine(corpus)
        good = make_spec(engine)
        from dataclasses import replace

        tampered = replace(good, market_dataset_version_id="sha256:not-the-corpus")
        with pytest.raises(CrossSectionConsistencyError):
            engine.estimate(tampered)


# -- XS-4: fail-closed pairing, recorded not imputed -------------------------


class TestXS4Coverage:
    def test_member_without_tradable_security_dropped_for_return(
        self, tmp_path: Path
    ) -> None:
        # Drop filer 4's market security: it is still a fundamentals universe member
        # (its signals resolve) but has no forward return, so it is dropped-for-return
        # at every date - never imputed. Four members remain, still above the DoF
        # floor for a two-factor + intercept design (n >= 4).
        corpus = populate(tmp_path, market_indices={0, 1, 2, 3})
        engine = crosssection_engine(corpus)
        reg = engine.estimate(make_spec(engine))
        cov = reg.coverage
        assert cov.total_dropped_for_return == 2  # filer 4, both dates
        for date_block in reg.per_date:
            assert date_block.n_members == 4

    def test_below_dof_floor_is_insufficient_members_not_raised(
        self, tmp_path: Path
    ) -> None:
        # Only three filers -> a two-factor + intercept design needs n >= 4, so every
        # date is INSUFFICIENT_MEMBERS. That leaves zero valid dates, which the engine
        # refuses (< 2 valid) - but as a configuration error, having *recorded* the
        # per-date UNDEFINED blocks first (never a raise from the per-date path).
        corpus = populate(tmp_path, n_filers=3)
        engine = crosssection_engine(corpus)
        spec = make_spec(engine, n_filers=3)
        with pytest.raises(CrossSectionConfigurationError):
            engine.estimate(spec)


# -- fail-closed configuration -----------------------------------------------


class TestFailClosed:
    def test_single_factor_no_intercept_clears_floor(self, tmp_path: Path) -> None:
        # One factor, no intercept: floor is n >= 2, easily cleared; a leaner design
        # that still yields KNOWN premia over both dates.
        _engine, reg = _estimate(
            tmp_path,
            factors=(FactorSpec("current_ratio", PERIOD),),
            include_intercept=False,
        )
        assert [p.label for p in reg.premia] == ["factor_1"]
        assert reg.premia[0].n_valid_dates == 2

    def test_single_scheduled_date_fails_min_valid_dates(self, tmp_path: Path) -> None:
        from quantforge.backtest.schedule import RebalanceSchedule

        corpus = populate(tmp_path)
        engine = crosssection_engine(corpus)
        spec = make_spec(engine, schedule=RebalanceSchedule.of([EVAL_1]))
        with pytest.raises(CrossSectionConfigurationError):
            engine.estimate(spec)
