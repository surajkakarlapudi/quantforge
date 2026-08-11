"""End-to-end engine tests over the synthetic corpus (§6, FR-1..FR-5).

These prove the *orchestration*: resolving + verifying the referenced factor portfolios,
enforcing commensurability, complete-case aligning the return series, estimating the
matrix under the pinned context, sealing + write-once persistence, determinism, and the
Phase 20 invariants. The exact arithmetic is proven in ``test_stats``; here the numbers
are checked for structure and coverage. Synthetic data only, fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.factorrisk.errors import FactorRiskConsistencyError
from quantforge.factorrisk.model import FactorRiskStatus
from quantforge.factorrisk.result import FactorRiskModel
from quantforge.factorrisk.spec import FactorRiskSpecification
from tests.factorrisk.builders import (
    EVAL_1,
    factor_risk_engine,
    make_risk_spec,
    populate,
    seal_factor,
    seal_two_factors,
)

# -- happy path --------------------------------------------------------------


class TestEndToEnd:
    def test_full_matrix_over_two_commensurable_factors(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))

        assert model.periods == 2
        assert len(model.factors) == 2
        # Upper triangle only: N=2 -> (0,0),(0,1),(1,1).
        assert [(c.i, c.j) for c in model.covariance] == [(0, 0), (0, 1), (1, 1)]
        assert [(c.i, c.j) for c in model.correlation] == [(0, 0), (0, 1), (1, 1)]
        for moment in model.factors:
            assert moment.mean.status is FactorRiskStatus.KNOWN
            assert moment.volatility.status is FactorRiskStatus.KNOWN
        assert model.boundary_kind == "pit"

    def test_factor_refs_and_coverage_in_request_order(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))

        assert model.factor_portfolio_ids == (
            f1.research_result_id,
            f2.research_result_id,
        )
        assert [ref[0] for ref in model.factor_refs] == ["factor_1", "factor_2"]
        # Each ref folds the child's result_hash (transitive pinning, FR-1).
        assert model.factor_refs[0][2] == f1.result_hash
        assert model.factor_refs[1][2] == f2.result_hash
        assert model.coverage.aligned_periods == 2
        assert model.coverage.dropped_for_alignment == 0

    def test_distinct_factors_give_distinct_moments(self, tmp_path: Path) -> None:
        # Two factors on the same signal but different quantile granularity produce
        # genuinely different return series (and thus distinct volatilities).
        corpus = populate(tmp_path, n_filers=6)
        a = seal_factor(
            corpus, signal="current_ratio", name="a", n_filers=6, quantiles=2
        )
        b = seal_factor(
            corpus, signal="current_ratio", name="b", n_filers=6, quantiles=3
        )
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(a, b))
        assert model.factors[0].volatility.value != model.factors[1].volatility.value

    def test_annualization_is_carried(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=6)
        a = seal_factor(
            corpus, signal="current_ratio", name="a", n_filers=6, quantiles=2
        )
        b = seal_factor(
            corpus, signal="current_ratio", name="b", n_filers=6, quantiles=3
        )
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(a, b, periods_per_year="4"))
        assert model.periods_per_year == "4"
        # Annualized vol = per-period vol * sqrt(4) = 2x, computed under the engine's
        # pinned decimal context (so the expected value must be too).
        from decimal import Decimal

        from quantforge.factorrisk.version import default_decimal_context

        ctx = default_decimal_context()
        for moment in model.factors:
            assert moment.volatility.value is not None
            assert moment.annualized_volatility.value is not None
            assert Decimal(moment.annualized_volatility.value) == ctx.multiply(
                Decimal(moment.volatility.value), Decimal(4).sqrt(ctx)
            )


# -- persistence + determinism -----------------------------------------------


class TestPersistenceAndDeterminism:
    def test_record_persists_and_round_trips_from_sidecar(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))
        restored = engine.research_store.read_as(
            model.factor_risk_id, FactorRiskModel.from_dict
        )
        assert restored is not None
        assert restored.to_dict() == model.to_dict()

    def test_re_estimation_is_byte_identical_noop(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        spec = make_risk_spec(f1, f2)
        first = engine.estimate(spec)
        second = engine.estimate(spec)
        assert first.to_dict() == second.to_dict()
        assert first.factor_risk_id == second.factor_risk_id

    def test_two_independent_corpora_agree(self, tmp_path: Path) -> None:
        def build(root: Path) -> FactorRiskModel:
            corpus = populate(root, n_filers=5)
            f1, f2 = seal_two_factors(corpus)
            engine = factor_risk_engine(corpus)
            return engine.estimate(make_risk_spec(f1, f2))

        a = build(tmp_path / "one")
        b = build(tmp_path / "two")
        assert a.to_dict() == b.to_dict()

    def test_factor_order_changes_identity(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        forward = engine.estimate(make_risk_spec(f1, f2))
        reverse = engine.estimate(make_risk_spec(f2, f1))
        assert forward.factor_risk_id != reverse.factor_risk_id


# -- FR-2: ex-post, not PIT --------------------------------------------------


class TestFR2ExPost:
    def test_record_exposes_no_pit_or_as_of_accessor(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))
        names = dir(model)
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)

    def test_record_is_not_a_backtest_result(self, tmp_path: Path) -> None:
        from quantforge.backtest import BacktestResult

        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))
        assert not isinstance(model, BacktestResult)


# -- FR-1: reference verification --------------------------------------------


class TestFR1References:
    def test_missing_reference_fails_closed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        (f1,) = (seal_factor(corpus, signal="current_ratio", name="a"),)
        engine = factor_risk_engine(corpus)
        spec = FactorRiskSpecification(
            name="m",
            factor_portfolio_ids=(f1.research_result_id, "sha256:never-sealed"),
        )
        with pytest.raises(FactorRiskConsistencyError):
            engine.estimate(spec)


# -- FR-3: commensurability --------------------------------------------------


class TestFR3Commensurability:
    def test_different_schedule_fails_closed(self, tmp_path: Path) -> None:
        # One factor on the default two-date schedule, one on a single-date schedule:
        # the return series do not share a rebalance calendar, so it is refused.
        corpus = populate(tmp_path, n_filers=5)
        a = seal_factor(corpus, signal="current_ratio", name="a")
        b = seal_factor(
            corpus,
            signal="quick_ratio",
            name="b",
            schedule=RebalanceSchedule.of([EVAL_1, "2024-03-15T00:00:00Z"]),
        )
        engine = factor_risk_engine(corpus)
        with pytest.raises(FactorRiskConsistencyError):
            engine.estimate(make_risk_spec(a, b))


# -- FR-4: complete-case alignment -------------------------------------------


class TestFR4Alignment:
    """The engine's complete-case alignment (FR-4).

    The engine intersects the dates where *every* factor carries a KNOWN return and
    estimates over exactly that window. With commensurable public factors the window is
    the full shared schedule, so ``periods`` equals the schedule length and nothing is
    dropped. The degenerate ``M < 2`` floor is unreachable through commensurable factors
    (they share one ``schedule_id`` per FR-3, and each factor portfolio itself requires
    >= 2 periods to seal), so that fail-closed guard is proven directly at the compute
    layer in ``test_stats.TestFailClosed.test_single_period_is_refused``.
    """

    def test_estimation_window_is_the_common_known_axis(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path, n_filers=5)
        f1, f2 = seal_two_factors(corpus)
        engine = factor_risk_engine(corpus)
        model = engine.estimate(make_risk_spec(f1, f2))
        # Both factors are KNOWN across the whole shared schedule: complete-case window
        # is the full length, nothing dropped.
        assert model.periods == model.coverage.aligned_periods
        assert model.coverage.dropped_for_alignment == 0
        for factor in model.coverage.per_factor:
            assert factor.used == model.periods
            assert factor.available == model.periods
