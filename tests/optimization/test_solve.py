"""The pure GMV compute layer (§11, PO-4).

Exact-``Decimal`` closed-form checks against hand-computed global minimum-variance
solutions, the fully-invested constraint, the achieved variance / volatility, the
scale-invariance of GMV weights, and the fail-closed / UNDEFINED behaviour on singular
and malformed matrices. No corpus, no store - just the solve function.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.optimization.errors import PortfolioOptimizationConsistencyError
from quantforge.optimization.model import (
    OptimizationStatus,
    OptimizationUndefinedReason,
    StatValue,
)
from quantforge.optimization.solve import MinVarianceSolution, solve_min_variance
from quantforge.optimization.version import default_decimal_context

CTX = default_decimal_context()

# Hand-computed exact-decimal GMV cases (weights and variance are exact terminating
# decimals under the pinned precision, so equality is asserted directly).
DIAG_EQUAL = [["4", "0"], ["0", "4"]]  # w = (1/2, 1/2), var = 2
CORRELATED = [["1", "1.5"], ["1.5", "4"]]  # w = (5/4, -1/4), var = 7/8 (long/short)
DIAG_THREE = [["1", "0", "0"], ["0", "1", "0"], ["0", "0", "2"]]  # w=(.4,.4,.2), var=.4
SINGLE = [["5"]]  # w = (1,), var = 5

COLLINEAR = [["1", "1"], ["1", "1"]]  # rank-deficient -> not PD
ZEROS = [["0", "0"], ["0", "0"]]  # zero matrix -> not PD
INDEFINITE = [["1", "2"], ["2", "1"]]  # eigenvalues 3, -1 -> not PD


def _solve(matrix: list[list[str]]) -> MinVarianceSolution:
    return solve_min_variance(matrix, context=CTX)


def _dec(cell: StatValue) -> Decimal:
    """The KNOWN decimal value of ``cell`` (asserts it is not UNDEFINED)."""
    assert cell.value is not None
    return Decimal(cell.value)


def _weights(matrix: list[list[str]]) -> list[str]:
    solution = solve_min_variance(matrix, context=CTX)
    return [w.value for w in solution.weights if w.value is not None]


class TestKnownClosedForm:
    def test_single_factor_gmv_is_full_weight(self) -> None:
        solution = _solve(SINGLE)
        assert solution.status is OptimizationStatus.OPTIMAL
        assert [w.value for w in solution.weights] == ["1"]
        assert _dec(solution.variance) == Decimal("5")

    def test_two_factor_diagonal_equal_variance(self) -> None:
        solution = _solve(DIAG_EQUAL)
        assert solution.status is OptimizationStatus.OPTIMAL
        assert [_dec(w) for w in solution.weights] == [
            Decimal("0.5"),
            Decimal("0.5"),
        ]
        assert _dec(solution.variance) == Decimal("2")

    def test_three_factor_diagonal(self) -> None:
        solution = _solve(DIAG_THREE)
        assert [_dec(w) for w in solution.weights] == [
            Decimal("0.4"),
            Decimal("0.4"),
            Decimal("0.2"),
        ]
        assert _dec(solution.variance) == Decimal("0.4")

    def test_correlated_factors_admit_negative_weight(self) -> None:
        # A GMV weight may be negative - an honest long/short across factors; no
        # non-negativity constraint applies in the fully-invested v1.
        solution = _solve(CORRELATED)
        assert [_dec(w) for w in solution.weights] == [
            Decimal("1.25"),
            Decimal("-0.25"),
        ]
        assert _dec(solution.variance) == Decimal("0.875")


class TestFullyInvested:
    @pytest.mark.parametrize("matrix", [DIAG_EQUAL, CORRELATED, DIAG_THREE, SINGLE])
    def test_weights_sum_to_one(self, matrix: list[list[str]]) -> None:
        total = sum((Decimal(w) for w in _weights(matrix)), Decimal(0))
        assert total == Decimal("1")


class TestVarianceAndVolatility:
    @pytest.mark.parametrize("matrix", [DIAG_EQUAL, CORRELATED, DIAG_THREE, SINGLE])
    def test_variance_equals_quadratic_form(self, matrix: list[list[str]]) -> None:
        # var = wᵀΣw, recomputed independently here from the returned weights.
        solution = _solve(matrix)
        w = [_dec(cell) for cell in solution.weights]
        n = len(matrix)
        expected = sum(
            (w[i] * Decimal(matrix[i][j]) * w[j] for i in range(n) for j in range(n)),
            Decimal(0),
        )
        assert _dec(solution.variance) == +expected

    @pytest.mark.parametrize("matrix", [DIAG_EQUAL, CORRELATED, DIAG_THREE, SINGLE])
    def test_volatility_is_sqrt_of_variance(self, matrix: list[list[str]]) -> None:
        solution = _solve(matrix)
        assert _dec(solution.volatility) == _dec(solution.variance).sqrt(CTX)


class TestScaleInvariance:
    def test_positive_scaling_preserves_weights(self) -> None:
        # GMV weights depend only on the direction of Σ⁻¹1, so scaling Σ by any positive
        # constant leaves the weights unchanged (only the variance scales).
        scaled = [[str(Decimal(v) * 2) for v in row] for row in DIAG_THREE]
        assert _weights(scaled) == _weights(DIAG_THREE)
        base = _solve(DIAG_THREE)
        big = _solve(scaled)
        assert _dec(big.variance) == _dec(base.variance) * 2


class TestSingular:
    @pytest.mark.parametrize("matrix", [COLLINEAR, ZEROS, INDEFINITE])
    def test_non_positive_definite_is_undefined_never_raised(
        self, matrix: list[list[str]]
    ) -> None:
        solution = _solve(matrix)
        assert solution.status is OptimizationStatus.UNDEFINED
        reason = OptimizationUndefinedReason.SINGULAR_COVARIANCE
        assert all(w.reason is reason for w in solution.weights)
        assert solution.variance.reason is reason
        assert solution.volatility.reason is reason
        assert all(w.value is None for w in solution.weights)


class TestFailClosed:
    def test_empty_matrix_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConsistencyError):
            _solve([])

    def test_ragged_matrix_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConsistencyError):
            _solve([["1", "0"], ["0"]])

    def test_non_decimal_cell_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConsistencyError):
            _solve([["1", "0"], ["0", "not-a-number"]])

    def test_non_finite_cell_raises(self) -> None:
        with pytest.raises(PortfolioOptimizationConsistencyError):
            _solve([["1", "0"], ["0", "Infinity"]])


class TestDeterminism:
    def test_repeated_solve_is_identical(self) -> None:
        first = _solve(CORRELATED)
        second = _solve(CORRELATED)
        assert [w.value for w in first.weights] == [w.value for w in second.weights]
        assert first.variance.value == second.variance.value
        assert first.volatility.value == second.volatility.value
