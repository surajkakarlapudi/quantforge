"""The pure one-sample calibration-significance math (§11, CS-3/CS-4/CS-5)."""

from __future__ import annotations

from decimal import Decimal

from quantforge.calsig.compute import (
    CalibratableFamily,
)
from quantforge.calsig.compute import (
    test_calibration_significance as run_significance,
)
from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStatus,
    SignificanceUndefinedReason,
    StatStatus,
)
from quantforge.calsig.version import default_decimal_context

_CTX = default_decimal_context()
_NULL = Decimal("1")


def _family(mean: str, dispersion: str, k: int) -> CalibratableFamily:
    return CalibratableFamily(
        mean_variance_ratio=Decimal(mean),
        variance_ratio_dispersion=Decimal(dispersion),
        n_calibratable=k,
    )


# -- happy path (CS-4/CS-5) --------------------------------------------------


def test_known_statistics_and_direction() -> None:
    # se = 0.2/sqrt(4) = 0.1; t = (1.2-1)/0.1 = 2.0; p = 2*(1-Phi(2)) ~ 0.0455.
    result = run_significance(_family("1.2", "0.2", 4), null_mean=_NULL, context=_CTX)
    assert result.significance_status is SignificanceStatus.TESTED
    assert result.status_reason is None
    assert result.n_calibratable == 4
    assert result.bias_direction is BiasDirection.UNDER_FORECAST
    assert result.mean_variance_ratio.value == "1.2"
    assert result.standard_error.value == "0.1"
    assert result.t_statistic.value == "2"
    p = Decimal(result.p_value.value or "-1")
    assert Decimal("0.045") < p < Decimal("0.046")


def test_over_forecast_direction_and_symmetric_p() -> None:
    # Mirror mean below the null: same |t|, so the same two-sided p, opposite direction.
    under = run_significance(_family("1.2", "0.2", 4), null_mean=_NULL, context=_CTX)
    over = run_significance(_family("0.8", "0.2", 4), null_mean=_NULL, context=_CTX)
    assert over.bias_direction is BiasDirection.OVER_FORECAST
    assert over.p_value.value == under.p_value.value
    assert over.t_statistic.value == "-2"


def test_unbiased_direction_when_mean_equals_null() -> None:
    result = run_significance(_family("1", "0.2", 4), null_mean=_NULL, context=_CTX)
    assert result.bias_direction is BiasDirection.UNBIASED
    assert Decimal(result.t_statistic.value or "-1") == Decimal("0")
    # p = 2*(1 - Phi(0)) = 2*0.5 = 1.
    assert Decimal(result.p_value.value or "-1") == Decimal("1")


# -- fail-closed: zero dispersion (CS-3) -------------------------------------


def test_zero_dispersion_leaves_mean_known_but_t_p_undefined() -> None:
    result = run_significance(_family("1.3", "0", 5), null_mean=_NULL, context=_CTX)
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.status_reason is SignificanceUndefinedReason.ZERO_RATIO_DISPERSION
    # Mean + direction stay KNOWN; standard error is a known zero; t / p undefined.
    assert result.mean_variance_ratio.value == "1.3"
    assert result.bias_direction is BiasDirection.UNDER_FORECAST
    assert result.standard_error.value == "0"
    assert result.t_statistic.status is StatStatus.UNDEFINED
    assert result.p_value.status is StatStatus.UNDEFINED
    assert (
        result.t_statistic.reason is SignificanceUndefinedReason.ZERO_RATIO_DISPERSION
    )


# -- fail-closed: absent family (CS-2) ---------------------------------------


def test_absent_family_is_all_undefined() -> None:
    result = run_significance(None, null_mean=_NULL, context=_CTX)
    assert result.significance_status is SignificanceStatus.UNDEFINED
    assert result.status_reason is SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED
    assert result.n_calibratable == 0
    assert result.bias_direction is None
    for cell in (
        result.mean_variance_ratio,
        result.standard_error,
        result.t_statistic,
        result.p_value,
    ):
        assert cell.status is StatStatus.UNDEFINED
        assert cell.reason is SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED


# -- p-value clamp & determinism ---------------------------------------------


def test_p_value_never_exceeds_one_for_tiny_t() -> None:
    # A tiny t keeps 2*(1-Phi(|t|)) at or just under 1 - clamped, never > 1.
    result = run_significance(
        _family("1.0000001", "1", 4), null_mean=_NULL, context=_CTX
    )
    p = Decimal(result.p_value.value or "-1")
    assert Decimal("0") <= p <= Decimal("1")


def test_recompute_is_identical() -> None:
    first = run_significance(
        _family("1.2", "0.2", 4), null_mean=_NULL, context=default_decimal_context()
    )
    second = run_significance(
        _family("1.2", "0.2", 4), null_mean=_NULL, context=default_decimal_context()
    )
    assert first == second
