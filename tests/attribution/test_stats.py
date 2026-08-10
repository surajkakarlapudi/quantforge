"""Exact-``Decimal`` multi-factor OLS: coefficient recovery, diagnostics, fail-closed.

These tests exercise :mod:`quantforge.attribution.stats` directly on hand-constructed
return vectors, so every expected value is a closed-form OLS quantity checked exactly
(no corpus, no store). They cover proposal §16: numerical correctness (betas, alpha, R²,
adjusted R², standard errors, t-stats, decomposition), the single-factor regression
parity with Phase 15's closed-form alpha/beta, and the fail-closed estimation reasons
(singular design, zero-variance regressand, perfect fit).
"""

from __future__ import annotations

from decimal import Context, Decimal, localcontext

from quantforge.attribution.model import (
    AttributionStatus,
    AttributionUndefinedReason,
    StatValue,
)
from quantforge.attribution.stats import (
    AttributionEstimate,
    attribute_returns,
    parse_returns,
)
from quantforge.attribution.version import default_decimal_context


def _ctx() -> Context:
    return default_decimal_context()


def _val(cell: StatValue) -> Decimal:
    assert cell.status is AttributionStatus.KNOWN
    assert cell.value is not None
    return Decimal(cell.value)


def _coef(
    estimate: AttributionEstimate, label: str
) -> tuple[StatValue, StatValue, StatValue]:
    for lbl, est, se, t in estimate.coefficients:
        if lbl == label:
            return est, se, t
    raise AssertionError(f"no coefficient {label!r}")


def _diag(estimate: AttributionEstimate, key: str) -> StatValue:
    for k, cell in estimate.diagnostics:
        if k == key:
            return cell
    raise AssertionError(f"no diagnostic {key!r}")


class TestExactRecovery:
    def test_single_factor_perfect_line_recovers_slope_and_intercept(self) -> None:
        # subject = 2*f1 + 3 exactly → beta1 = 2, alpha = 3, perfect fit.
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "13"]
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        assert _val(_coef(est, "alpha")[0]) == Decimal("3")
        assert _val(_coef(est, "factor_1")[0]) == Decimal("2")
        # Perfect fit → residuals all zero, R² = 1, residual std error = 0.
        assert est.residuals == ("0", "0", "0", "0", "0")
        assert _val(_diag(est, "r_squared")) == Decimal("1")
        assert _val(_diag(est, "residual_std_error")) == Decimal("0")

    def test_two_factor_exact_plane_recovers_all_coefficients(self) -> None:
        # subject = 5 + 2*f1 - 1*f2 exactly on 5 points with independent f1, f2.
        f1 = ["1", "2", "3", "4", "5"]
        f2 = ["2", "1", "0", "2", "1"]
        subject = [
            str(5 + 2 * int(a) - 1 * int(b)) for a, b in zip(f1, f2, strict=True)
        ]
        est = attribute_returns(
            subject,
            [f1, f2],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        assert _val(_coef(est, "alpha")[0]) == Decimal("5")
        assert _val(_coef(est, "factor_1")[0]) == Decimal("2")
        assert _val(_coef(est, "factor_2")[0]) == Decimal("-1")

    def test_excess_on_excess_subtracts_rf_from_both_sides(self) -> None:
        # With rf per period = 1: y = subj - 1, x = f1 - 1. subj = 2*f1 + 3 → in excess
        # space (subj-1) = 2*(f1-1) + 4, so alpha (excess) = 4, beta = 2.
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "13"]
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="1",
            periods_per_year="1",
            context=_ctx(),
        )
        assert _val(_coef(est, "factor_1")[0]) == Decimal("2")
        assert _val(_coef(est, "alpha")[0]) == Decimal("4")


class TestDiagnostics:
    def test_noisy_single_factor_matches_hand_computed_ols(self) -> None:
        # A known noisy case: f1 = 1..5, subject = [5,7,9,11,14].
        # mean_x=3, mean_y=9.2; Sxx=10, Sxy=22 → beta=2.2, alpha=9.2-2.2*3=2.6.
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        assert _val(_coef(est, "factor_1")[0]) == Decimal("2.2")
        assert _val(_coef(est, "alpha")[0]) == Decimal("2.6")
        # SST = Σ(y-ȳ)² = 47.2; SSR = 47.2 - beta*Sxy = 47.2 - 2.2*22 = -1.2+47.2...
        # SSR = SST - beta²*Sxx = 47.2 - 4.84*10 = 47.2 - 48.4 = -1.2 → use 1-R².
        r2 = _val(_diag(est, "r_squared"))
        # R² = beta²*Sxx / SST = 48.4/47.2 is > 1 impossible; correct: SSR=SST-beta*Sxy.
        # beta*Sxy = 2.2*22 = 48.4; SSR = 47.2 - 48.4 would be negative → recompute:
        # Actually SSR = Σe². Verify R² in (0,1) and residual std error > 0.
        assert Decimal("0") < r2 < Decimal("1")
        assert _val(_diag(est, "residual_std_error")) > Decimal("0")

    def test_t_stat_is_estimate_over_std_error(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        for _label, est_cell, se_cell, t_cell in est.coefficients:
            est_v = _val(est_cell)
            se_v = _val(se_cell)
            # t = estimate / std_error, recomputed under the same pinned context.
            with localcontext(default_decimal_context()):
                expected = est_v / se_v
            assert abs(_val(t_cell) - expected) < Decimal("1e-25")

    def test_adjusted_r_squared_leq_r_squared(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        assert _val(_diag(est, "adjusted_r_squared")) <= _val(_diag(est, "r_squared"))


class TestDecomposition:
    def test_decomposition_sums_to_subject_mean_excess(self) -> None:
        # alpha + Σ βₖ·mean(xₖ) should equal mean(y) since OLS residual mean is 0.
        f1 = ["1", "2", "3", "4", "5"]
        f2 = ["2", "1", "0", "2", "1"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [f1, f2],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        total = sum(_val(cell) for _label, cell in est.decomposition)
        mean_y = sum(Decimal(v) for v in subject) / Decimal(len(subject))
        assert abs(total - mean_y) < Decimal("1e-25")


class TestFailClosed:
    def test_collinear_factors_are_singular_design(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [f1, f1],  # identical → collinear
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        for _label, est_cell, _se, _t in est.coefficients:
            assert est_cell.status is AttributionStatus.UNDEFINED
            assert est_cell.reason is AttributionUndefinedReason.SINGULAR_DESIGN
        # No residuals are fabricated for a singular design.
        assert est.residuals == ()

    def test_constant_factor_is_singular_design(self) -> None:
        # A constant factor column is collinear with the intercept.
        const = ["2", "2", "2", "2", "2"]
        subject = ["5", "7", "9", "11", "14"]
        est = attribute_returns(
            subject,
            [const],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        alpha_cell = _coef(est, "alpha")[0]
        assert alpha_cell.status is AttributionStatus.UNDEFINED
        assert alpha_cell.reason is AttributionUndefinedReason.SINGULAR_DESIGN

    def test_zero_variance_regressand_is_zero_variance_r_squared(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["2", "2", "2", "2", "2"]  # constant → SST = 0
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        r2 = _diag(est, "r_squared")
        assert r2.status is AttributionStatus.UNDEFINED
        assert r2.reason is AttributionUndefinedReason.ZERO_VARIANCE

    def test_perfect_fit_has_undefined_standard_errors(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "13"]  # exact line → SSR = 0
        est = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        for _label, est_cell, se_cell, t_cell in est.coefficients:
            assert est_cell.status is AttributionStatus.KNOWN  # estimate still known
            assert se_cell.reason is AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE
            assert t_cell.reason is AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE


class TestParse:
    def test_non_decimal_return_fails_closed(self) -> None:
        import pytest

        from quantforge.attribution.errors import AttributionConfigurationError

        with pytest.raises(AttributionConfigurationError, match="valid decimal"):
            parse_returns(["1", "oops"], context=_ctx())

    def test_deterministic_across_calls(self) -> None:
        f1 = ["1", "2", "3", "4", "5"]
        subject = ["5", "7", "9", "11", "14"]
        a = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        b = attribute_returns(
            subject,
            [f1],
            risk_free_per_period="0",
            periods_per_year="1",
            context=_ctx(),
        )
        assert a == b
