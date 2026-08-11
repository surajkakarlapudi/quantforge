"""Sealed optimization record: sealing, round-trip, identity, ex-post (§14, PO-2)."""

from __future__ import annotations

from quantforge.optimization.model import (
    OptimizationStatus,
    StatValue,
    WeightCell,
    factor_label,
)
from quantforge.optimization.result import (
    BOUNDARY_PIT,
    COVARIANCE_BASIS_PER_PERIOD,
    PortfolioOptimization,
)


def _seal(
    *,
    weights: tuple[str, ...] = ("0.5", "0.5"),
    variance: str = "2",
    volatility: str = "1.4",
    dataset_version_ids: tuple[str, ...] = ("ds-1",),
    market_dataset_version_ids: tuple[str, ...] = ("mkt-1",),
    name: str = "m",
) -> PortfolioOptimization:
    n = len(weights)
    labels = tuple(factor_label(i) for i in range(n))
    weight_cells = tuple(
        WeightCell(label=labels[i], value=StatValue.known(weights[i])) for i in range(n)
    )
    spec: dict[str, object] = {
        "spec_version": "optimization/1",
        "name": name,
        "factor_risk_id": "sha256:risk",
        "objective": "minimum_variance",
        "fully_invested": True,
    }
    return PortfolioOptimization.seal(
        optimization_engine_version_id="sha256:engine",
        optimization_spec=spec,
        objective="minimum_variance",
        constraint_spec={"fully_invested": True},
        covariance_basis=COVARIANCE_BASIS_PER_PERIOD,
        risk_model_ref=("sha256:risk", "sha256:answer"),
        boundary_kind=BOUNDARY_PIT,
        schedule_id="schedule-1",
        factor_portfolio_engine_version_id="fpe-1",
        n_factors=n,
        factor_labels=labels,
        status=OptimizationStatus.OPTIMAL,
        weights=weight_cells,
        portfolio_variance=StatValue.known(variance),
        portfolio_volatility=StatValue.known(volatility),
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )


class TestSealAndIdentity:
    def test_result_hash_and_id_are_prefixed(self) -> None:
        record = _seal()
        assert record.result_hash.startswith("sha256:")
        assert record.optimization_id.startswith("sha256:")

    def test_research_result_id_aliases_optimization_id(self) -> None:
        record = _seal()
        assert record.research_result_id == record.optimization_id
        assert record.factor_risk_id == "sha256:risk"

    def test_differing_answer_changes_id(self) -> None:
        assert (
            _seal(weights=("0.5", "0.5")).optimization_id
            != _seal(weights=("0.6", "0.4")).optimization_id
        )

    def test_id_is_rederived_not_stored(self) -> None:
        # The id property re-derives from fields, so a byte round-trip yields the same
        # id.
        record = _seal()
        assert record.to_dict()["optimization_id"] == record.optimization_id


class TestRoundTrip:
    def test_from_dict_is_byte_identical_inverse(self) -> None:
        record = _seal()
        restored = PortfolioOptimization.from_dict(record.to_dict())
        assert restored.to_dict() == record.to_dict()
        assert restored.optimization_id == record.optimization_id
        assert restored.result_hash == record.result_hash


class TestPinMismatch:
    def test_singular_pins_are_not_a_mismatch(self) -> None:
        assert _seal().pin_mismatch is False

    def test_multiple_fundamentals_pins_flag_mismatch(self) -> None:
        assert _seal(dataset_version_ids=("ds-1", "ds-2")).pin_mismatch is True

    def test_multiple_market_pins_flag_mismatch(self) -> None:
        assert _seal(market_dataset_version_ids=("mkt-1", "mkt-2")).pin_mismatch is True


class TestExPostNotPit:
    def test_record_exposes_no_pit_or_as_of_accessor(self) -> None:
        names = dir(_seal())
        assert not any(n.lower().startswith("pit") for n in names)
        assert not any(n == "as_of" or n.startswith("as_of_") for n in names)

    def test_boundary_kind_documents_input_side_only(self) -> None:
        assert _seal().boundary_kind == "pit"

    def test_record_is_not_a_backtest_result(self) -> None:
        from quantforge.backtest import BacktestResult

        assert not isinstance(_seal(), BacktestResult)
