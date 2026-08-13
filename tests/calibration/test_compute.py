"""The pure risk-forecast-calibration procedures (§11, §12, RC-3/RC-4/RC-5).

Exact-arithmetic hand-calculations of the per-window ratios and the aggregate bias /
dispersion / frequency statistics, the empty-family guard (RC-3), the
below-floor UNDEFINED status (RC-5), and determinism.
"""

from __future__ import annotations

from decimal import Decimal

from quantforge.calibration.compute import CalibratableWindow, calibrate
from quantforge.calibration.model import (
    CalibrationStatus,
    CalibrationUndefinedReason,
    StatStatus,
)
from quantforge.calibration.version import default_decimal_context

CTX = default_decimal_context()


def _win(index: int, predicted: str, realized: str) -> CalibratableWindow:
    return CalibratableWindow(
        index=index, predicted=Decimal(predicted), realized=Decimal(realized)
    )


# -- hand-calculations (exact) -----------------------------------------------


def test_hand_calc_two_windows() -> None:
    # predicted = (4, 1), realized = (1, 4): every ratio and root is exact.
    out = calibrate(
        [_win(0, "4", "1"), _win(1, "1", "4")], min_calibratable=2, context=CTX
    )
    w0, w1 = out.windows
    assert (w0.predicted_volatility, w0.realized_volatility) == ("2", "1")
    assert (w0.variance_ratio, w0.volatility_ratio) == ("0.25", "0.5")
    assert (w1.predicted_volatility, w1.realized_volatility) == ("1", "2")
    assert (w1.variance_ratio, w1.volatility_ratio) == ("4", "2")

    s = out.summary
    assert s.calibration_status is CalibrationStatus.CALIBRATED
    assert s.status_reason is None
    assert s.mean_variance_ratio.value == "2.125"  # (0.25 + 4) / 2
    assert s.aggregate_bias.value == "1"  # (1 + 4) / (4 + 1)
    assert s.variance_ratio_dispersion.value == "1.875"  # sqrt(((1.875)^2)*2 / 2)
    assert s.underforecast_frequency.value == "0.5"  # only window 1 under-forecasts
    assert s.max_variance_ratio.value == "4"
    assert s.min_variance_ratio.value == "0.25"


def test_variances_are_consumed_verbatim() -> None:
    # RC-4: the sealed predicted / realized strings are carried through unchanged.
    out = calibrate([_win(0, "0.0016", "0.0009")], min_calibratable=1, context=CTX)
    (w0,) = out.windows
    assert w0.predicted_variance == "0.0016"
    assert w0.realized_variance == "0.0009"
    # 0.0009 / 0.0016 = 0.5625 exactly; sqrt(0.0016)=0.04, sqrt(0.0009)=0.03.
    assert w0.variance_ratio == "0.5625"
    assert (w0.predicted_volatility, w0.realized_volatility) == ("0.04", "0.03")
    assert w0.volatility_ratio == "0.75"


# -- floor / status (RC-5) ---------------------------------------------------


def test_single_window_below_floor_is_undefined_status() -> None:
    out = calibrate([_win(0, "4", "1")], min_calibratable=2, context=CTX)
    s = out.summary
    # The (one) per-window ratio still seals, but the roll-up status is UNDEFINED.
    assert len(out.windows) == 1
    assert s.calibration_status is CalibrationStatus.UNDEFINED
    assert (
        s.status_reason is CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
    )
    # The aggregates over the single window are still KNOWN.
    assert s.mean_variance_ratio.value == "0.25"
    assert s.variance_ratio_dispersion.value == "0"


def test_single_window_at_floor_one_is_calibrated() -> None:
    out = calibrate([_win(0, "4", "1")], min_calibratable=1, context=CTX)
    assert out.summary.calibration_status is CalibrationStatus.CALIBRATED
    assert out.summary.status_reason is None


# -- empty family (RC-3) -----------------------------------------------------


def test_empty_family_is_all_undefined_never_divides() -> None:
    out = calibrate([], min_calibratable=2, context=CTX)
    assert out.windows == ()
    s = out.summary
    for cell in (
        s.mean_variance_ratio,
        s.aggregate_bias,
        s.variance_ratio_dispersion,
        s.underforecast_frequency,
        s.max_variance_ratio,
        s.min_variance_ratio,
    ):
        assert cell.status is StatStatus.UNDEFINED
        assert cell.reason is CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS
    assert s.calibration_status is CalibrationStatus.UNDEFINED
    assert (
        s.status_reason is CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
    )


# -- under-forecast frequency & perfect calibration --------------------------


def test_perfectly_calibrated_family_has_unit_ratios() -> None:
    out = calibrate(
        [_win(0, "4", "4"), _win(1, "9", "9")], min_calibratable=2, context=CTX
    )
    s = out.summary
    assert s.mean_variance_ratio.value == "1"
    assert s.aggregate_bias.value == "1"
    assert s.variance_ratio_dispersion.value == "0"
    # realized == predicted is not strictly greater, so nothing under-forecasts.
    assert s.underforecast_frequency.value == "0"


def test_all_underforecast_frequency_is_one() -> None:
    out = calibrate(
        [_win(0, "1", "2"), _win(1, "1", "3")], min_calibratable=2, context=CTX
    )
    assert out.summary.underforecast_frequency.value == "1"


# -- determinism -------------------------------------------------------------


def test_repeated_calls_are_byte_identical() -> None:
    windows = [_win(0, "4", "1"), _win(1, "1", "4"), _win(2, "0.02", "0.05")]
    first = calibrate(windows, min_calibratable=2, context=CTX)
    second = calibrate(windows, min_calibratable=2, context=CTX)
    assert [w.variance_ratio for w in first.windows] == [
        w.variance_ratio for w in second.windows
    ]
    assert first.summary.mean_variance_ratio.value == (
        second.summary.mean_variance_ratio.value
    )
    assert first.summary.aggregate_bias.value == second.summary.aggregate_bias.value
