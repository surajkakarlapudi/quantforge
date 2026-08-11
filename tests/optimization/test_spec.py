"""The declarative optimization request and its fail-closed validation (§14)."""

from __future__ import annotations

import pytest

from quantforge.optimization.errors import PortfolioOptimizationConfigurationError
from quantforge.optimization.spec import (
    OBJECTIVE_MINIMUM_VARIANCE,
    PortfolioOptimizationSpecification,
)
from quantforge.optimization.version import OPTIMIZATION_SPEC_VERSION


class TestValidConstruction:
    def test_defaults_are_minimum_variance_fully_invested(self) -> None:
        spec = PortfolioOptimizationSpecification(name="m", factor_risk_id="sha256:abc")
        assert spec.objective == OBJECTIVE_MINIMUM_VARIANCE
        assert spec.fully_invested is True
        assert spec.spec_version == OPTIMIZATION_SPEC_VERSION

    def test_to_dict_is_canonical_request(self) -> None:
        spec = PortfolioOptimizationSpecification(name="m", factor_risk_id="sha256:abc")
        assert spec.to_dict() == {
            "spec_version": OPTIMIZATION_SPEC_VERSION,
            "name": "m",
            "factor_risk_id": "sha256:abc",
            "objective": OBJECTIVE_MINIMUM_VARIANCE,
            "fully_invested": True,
        }


class TestFailClosed:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(name="", factor_risk_id="sha256:abc")

    def test_empty_factor_risk_id_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(name="m", factor_risk_id="")

    def test_empty_spec_version_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(
                name="m", factor_risk_id="sha256:abc", spec_version=""
            )

    def test_unknown_objective_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(
                name="m", factor_risk_id="sha256:abc", objective="max_sharpe"
            )

    def test_fully_invested_false_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(
                name="m", factor_risk_id="sha256:abc", fully_invested=False
            )

    def test_fully_invested_int_one_does_not_masquerade_as_true(self) -> None:
        # bool is a subclass of int; the spec uses an identity check so 1 is refused.
        with pytest.raises(PortfolioOptimizationConfigurationError):
            PortfolioOptimizationSpecification(
                name="m",
                factor_risk_id="sha256:abc",
                fully_invested=1,  # type: ignore[arg-type]
            )
