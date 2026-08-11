"""End-to-end engine tests over synthetic sealed risk models (§6, PO-1..PO-5).

These prove the orchestration: resolving + verifying the referenced
:class:`~quantforge.factorrisk.result.FactorRiskModel`, enforcing the factor-count
bound, reconstructing the symmetric covariance, solving the GMV, sealing + write-once
persistence, determinism, the ex-post boundary, and the Workspace wiring. The exact GMV
arithmetic is proven in ``test_solve``; here the numbers are checked for structure and
the known closed form. Synthetic covariance only, fully offline.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from quantforge.factorrisk.spec import N_MAX
from quantforge.optimization.engine import PortfolioOptimizationEngine
from quantforge.optimization.errors import (
    PortfolioOptimizationConfigurationError,
    PortfolioOptimizationConsistencyError,
)
from quantforge.optimization.model import (
    OptimizationStatus,
    OptimizationUndefinedReason,
    StatValue,
)
from quantforge.optimization.result import PortfolioOptimization
from tests.optimization.builders import (
    DummyRecord,
    make_opt_spec,
    make_risk_model,
    opt_engine,
    seal_risk_model,
    workspace,
)

# Reused hand-computed covariance: diag(1,1,2) -> GMV weights (0.4, 0.4, 0.2), var 0.4.
DIAG_THREE = [["1", "0", "0"], ["0", "1", "0"], ["0", "0", "2"]]
CORRELATED = [["1", "1.5"], ["1.5", "4"]]  # w = (1.25, -0.25), var 0.875
COLLINEAR = [["1", "1"], ["1", "1"]]  # not PD -> SINGULAR_COVARIANCE


def _dec(cell: StatValue) -> Decimal:
    """The KNOWN decimal value of ``cell`` (asserts it is not UNDEFINED)."""
    assert cell.value is not None
    return Decimal(cell.value)


class TestEndToEnd:
    def test_multi_factor_gmv_known_closed_form(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))

        assert result.status is OptimizationStatus.OPTIMAL
        assert result.n_factors == 3
        assert result.factor_labels == ("factor_1", "factor_2", "factor_3")
        assert [_dec(w.value) for w in result.weights] == [
            Decimal("0.4"),
            Decimal("0.4"),
            Decimal("0.2"),
        ]
        assert _dec(result.portfolio_variance) == Decimal("0.4")

    def test_weight_cells_are_labelled_in_factor_order(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))
        assert [w.label for w in result.weights] == [
            "factor_1",
            "factor_2",
            "factor_3",
        ]

    def test_provenance_is_carried_from_the_risk_model(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        model = make_risk_model(CORRELATED)
        ws.research_result_store.write(model)
        result = opt_engine(ws).optimize(make_opt_spec(model.research_result_id))

        assert result.risk_model_ref == (model.research_result_id, model.result_hash)
        assert result.schedule_id == model.schedule_id
        assert (
            result.factor_portfolio_engine_version_id
            == model.factor_portfolio_engine_version_id
        )
        assert result.covariance_basis == "per_period"
        assert result.objective == "minimum_variance"
        assert result.constraint_spec == {"fully_invested": True}

    def test_negative_weight_is_carried_through(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, CORRELATED)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))
        assert [_dec(w.value) for w in result.weights] == [
            Decimal("1.25"),
            Decimal("-0.25"),
        ]


class TestSingularCovariance:
    def test_singular_is_recorded_undefined_not_raised(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, COLLINEAR)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))

        assert result.status is OptimizationStatus.UNDEFINED
        reason = OptimizationUndefinedReason.SINGULAR_COVARIANCE
        assert all(w.value.reason is reason for w in result.weights)
        assert result.portfolio_variance.reason is reason
        assert result.portfolio_volatility.reason is reason
        # An UNDEFINED result is still a first-class sealed, persisted record.
        assert ws.research_result_store.has(result.research_result_id)


class TestFactorCountBound:
    def test_single_factor_is_refused(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, [["5"]])
        with pytest.raises(PortfolioOptimizationConsistencyError):
            opt_engine(ws).optimize(make_opt_spec(risk_id))

    def test_more_than_n_max_is_refused(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        big = N_MAX + 1
        matrix = [[("1" if i == j else "0") for j in range(big)] for i in range(big)]
        risk_id = seal_risk_model(ws, matrix)
        with pytest.raises(PortfolioOptimizationConsistencyError):
            opt_engine(ws).optimize(make_opt_spec(risk_id))

    def test_exactly_n_max_is_accepted(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        matrix = [
            [("1" if i == j else "0") for j in range(N_MAX)] for i in range(N_MAX)
        ]
        risk_id = seal_risk_model(ws, matrix)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))
        assert result.n_factors == N_MAX
        assert result.status is OptimizationStatus.OPTIMAL


class TestReferenceVerification:
    def test_missing_reference_fails_closed(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        with pytest.raises(PortfolioOptimizationConsistencyError):
            opt_engine(ws).optimize(make_opt_spec("sha256:never-sealed"))

    def test_non_risk_model_payload_fails_closed(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        dummy = DummyRecord(research_result_id="sha256:not-a-risk-model")
        ws.research_result_store.write(dummy)
        with pytest.raises(PortfolioOptimizationConsistencyError):
            opt_engine(ws).optimize(make_opt_spec(dummy.research_result_id))

    def test_non_spec_argument_is_a_configuration_error(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        with pytest.raises(PortfolioOptimizationConfigurationError):
            opt_engine(ws).optimize(object())  # type: ignore[arg-type]


class TestIdentitySensitivity:
    def test_different_referenced_model_changes_optimization_id(
        self, tmp_path: Path
    ) -> None:
        ws = workspace(tmp_path)
        id_a = seal_risk_model(ws, DIAG_THREE, name="risk-a")
        id_b = seal_risk_model(ws, CORRELATED, name="risk-b")
        a = opt_engine(ws).optimize(make_opt_spec(id_a))
        b = opt_engine(ws).optimize(make_opt_spec(id_b))
        assert a.optimization_id != b.optimization_id

    def test_different_request_name_changes_optimization_id(
        self, tmp_path: Path
    ) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE)
        a = opt_engine(ws).optimize(make_opt_spec(risk_id, name="one"))
        b = opt_engine(ws).optimize(make_opt_spec(risk_id, name="two"))
        assert a.optimization_id != b.optimization_id


class TestPersistenceAndDeterminism:
    def test_record_persists_and_round_trips_from_sidecar(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE)
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))
        restored = ws.research_result_store.read_as(
            result.optimization_id, PortfolioOptimization.from_dict
        )
        assert restored is not None
        assert restored.to_dict() == result.to_dict()

    def test_re_optimization_is_byte_identical_noop(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE)
        engine = opt_engine(ws)
        spec = make_opt_spec(risk_id)
        first = engine.optimize(spec)
        second = engine.optimize(spec)
        assert first.to_dict() == second.to_dict()
        assert first.optimization_id == second.optimization_id

    def test_two_independent_workspaces_agree(self, tmp_path: Path) -> None:
        def build(root: Path) -> PortfolioOptimization:
            ws = workspace(root)
            risk_id = seal_risk_model(ws, DIAG_THREE)
            return opt_engine(ws).optimize(make_opt_spec(risk_id))

        a = build(tmp_path / "one")
        b = build(tmp_path / "two")
        assert a.to_dict() == b.to_dict()

    def test_pin_mismatch_is_surfaced(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        risk_id = seal_risk_model(ws, DIAG_THREE, dataset_version_ids=("ds-1", "ds-2"))
        result = opt_engine(ws).optimize(make_opt_spec(risk_id))
        assert result.pin_mismatch is True


class TestWorkspaceWiring:
    def test_optimization_engine_is_cached(self, tmp_path: Path) -> None:
        ws = workspace(tmp_path)
        assert isinstance(ws.optimization_engine, PortfolioOptimizationEngine)
        assert ws.optimization_engine is ws.optimization_engine
