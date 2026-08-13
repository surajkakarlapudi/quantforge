"""The pure risk-forecast-calibration procedures over one walk's windows (§11, §12).

Given the calibratable windows of one sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` - each a
``(index, predicted_variance, realized_variance)`` triple with
``predicted_variance > 0`` and ``realized_variance >= 0`` (the engine has already
classified and excluded every non-calibratable window, RC-3) - :func:`calibrate`
computes, per window, the forecast-vs-outcome ratios, and over the family the aggregate
bias / dispersion statistics. All arithmetic runs under an explicit
:class:`decimal.Context`, in exact ``Decimal``, with no RNG, no floating point, and no
data-dependent iteration (``Decimal.sqrt`` is the only transcendental, the exact method
Phases 19/20/22 already use).

Per calibratable window (RC-4 - the sealed forecast and outcome are consumed verbatim,
never recomputed from ``oos_returns``):

* ``variance_ratio = realized / predicted`` (the risk-model bias, 1.0 = perfect)
* ``predicted_volatility = sqrt(predicted)``
* ``realized_volatility = sqrt(realized)``
* ``volatility_ratio = realized_volatility / predicted_volatility``

Over the family of ``K`` calibratable windows (KNOWN iff ``K >= 1``; every cell
UNDEFINED with ``NO_CALIBRATABLE_WINDOWS`` when ``K = 0`` - never a divide-by-zero):

* ``mean_variance_ratio = (sum variance_ratio_k) / K``
* ``aggregate_bias = (sum realized_k) / (sum predicted_k)`` (pooled, Barra-style)
* ``variance_ratio_dispersion = sqrt( sum (variance_ratio_k - mean)^2 / K )``
  (population)
* ``underforecast_frequency = |{k : realized_k > predicted_k}| / K``
* ``max_variance_ratio`` / ``min_variance_ratio``

``calibration_status`` is ``CALIBRATED`` iff ``K >= min_calibratable``, else
``UNDEFINED`` (``INSUFFICIENT_CALIBRATABLE_WINDOWS``) - the record seals either way
(RC-3).

Pure: a function of the calibratable windows, the count of windows, the floor, and the
context - no wall clock, no RNG, no iteration-order dependence. The per-window
``variance_ratio`` values are computed once and reused for every aggregate, so a cell's
ratio and the aggregates over it can never disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.calibration.model import (
    CalibrationStat,
    CalibrationStatus,
    CalibrationUndefinedReason,
)

__all__ = [
    "CalibratableWindow",
    "CalibrationComputation",
    "CalibrationSummaryComputation",
    "WindowRatios",
    "calibrate",
]

_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class CalibratableWindow:
    """One source window that yields a forecast-vs-outcome ratio (RC-2).

    ``index`` is the source window's index; ``predicted`` its KNOWN in-sample
    ``predicted_variance`` (strictly positive, verified by the engine); ``realized``
    its KNOWN out-of-sample ``realized_variance`` (non-negative). Both are
    ``Decimal`` parsed once from the source's canonical decimal strings - never
    recomputed (RC-4).
    """

    index: int
    predicted: Decimal
    realized: Decimal


@dataclass(frozen=True, slots=True)
class WindowRatios:
    """The computed per-window ratios, as canonical decimal strings (§11).

    ``variance_ratio`` and ``volatility_ratio`` are the risk-model bias on the variance
    and volatility scale; ``predicted_volatility`` / ``realized_volatility`` are the
    ``sqrt`` of the sealed variances (carried for readability, derivable, excluded from
    the record hash's cell payload). Aligned index-for-index to the calibratable windows
    passed to :func:`calibrate`.
    """

    index: int
    predicted_variance: str
    realized_variance: str
    predicted_volatility: str
    realized_volatility: str
    variance_ratio: str
    volatility_ratio: str


@dataclass(frozen=True, slots=True)
class CalibrationSummaryComputation:
    """The aggregate calibration statistics, as UNDEFINED-preserving cells (§11)."""

    mean_variance_ratio: CalibrationStat
    aggregate_bias: CalibrationStat
    variance_ratio_dispersion: CalibrationStat
    underforecast_frequency: CalibrationStat
    max_variance_ratio: CalibrationStat
    min_variance_ratio: CalibrationStat
    calibration_status: CalibrationStatus
    status_reason: CalibrationUndefinedReason | None


@dataclass(frozen=True, slots=True)
class CalibrationComputation:
    """The full pure result: per-window ratios + the aggregate summary (§11)."""

    windows: tuple[WindowRatios, ...]
    summary: CalibrationSummaryComputation


def calibrate(
    calibratable: Sequence[CalibratableWindow],
    *,
    min_calibratable: int,
    context: Context,
) -> CalibrationComputation:
    """Compute per-window ratios + aggregate statistics (§11, RC-3/RC-4/RC-5).

    ``calibratable`` are the source's calibratable windows in source order (each
    with ``predicted > 0``); ``min_calibratable`` is the floor below which
    ``calibration_status`` is UNDEFINED; ``context`` is the pinned decimal context.
    An **empty** family (``K == 0``) yields empty per-window ratios and every
    aggregate cell UNDEFINED (``NO_CALIBRATABLE_WINDOWS``) - never a divide-by-zero
    (RC-3). Deterministic: identical inputs yield identical ``Decimal`` values on
    any machine.
    """
    with localcontext(context):
        ratios: list[WindowRatios] = []
        variance_ratios: list[Decimal] = []
        sum_predicted = _ZERO
        sum_realized = _ZERO
        n_underforecast = 0
        for window in calibratable:
            predicted = window.predicted
            realized = window.realized
            variance_ratio = realized / predicted
            predicted_volatility = predicted.sqrt()
            realized_volatility = realized.sqrt()
            volatility_ratio = realized_volatility / predicted_volatility
            ratios.append(
                WindowRatios(
                    index=window.index,
                    predicted_variance=str(+predicted),
                    realized_variance=str(+realized),
                    predicted_volatility=str(+predicted_volatility),
                    realized_volatility=str(+realized_volatility),
                    variance_ratio=str(+variance_ratio),
                    volatility_ratio=str(+volatility_ratio),
                )
            )
            variance_ratios.append(variance_ratio)
            sum_predicted += predicted
            sum_realized += realized
            if realized > predicted:
                n_underforecast += 1

        summary = _summarize(
            variance_ratios=variance_ratios,
            sum_predicted=sum_predicted,
            sum_realized=sum_realized,
            n_underforecast=n_underforecast,
            min_calibratable=min_calibratable,
        )
    return CalibrationComputation(windows=tuple(ratios), summary=summary)


def _summarize(
    *,
    variance_ratios: list[Decimal],
    sum_predicted: Decimal,
    sum_realized: Decimal,
    n_underforecast: int,
    min_calibratable: int,
) -> CalibrationSummaryComputation:
    """Aggregate the per-window ratios (called inside the pinned context)."""
    k = len(variance_ratios)
    if k == 0:
        # No calibratable windows: every aggregate is undefined, never a divide-by-zero.
        undefined = CalibrationStat.undefined(
            CalibrationUndefinedReason.NO_CALIBRATABLE_WINDOWS
        )
        return CalibrationSummaryComputation(
            mean_variance_ratio=undefined,
            aggregate_bias=undefined,
            variance_ratio_dispersion=undefined,
            underforecast_frequency=undefined,
            max_variance_ratio=undefined,
            min_variance_ratio=undefined,
            calibration_status=CalibrationStatus.UNDEFINED,
            status_reason=(
                CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
            ),
        )

    k_dec = Decimal(k)
    mean_variance_ratio = sum(variance_ratios, _ZERO) / k_dec
    # Pooled, Barra-style bias ratio: sum_predicted > 0 (every predicted is strictly
    # positive and K >= 1), so this never divides by zero.
    aggregate_bias = sum_realized / sum_predicted
    dispersion_sq = (
        sum(((r - mean_variance_ratio) ** 2 for r in variance_ratios), _ZERO) / k_dec
    )
    dispersion = dispersion_sq.sqrt()
    underforecast_frequency = Decimal(n_underforecast) / k_dec
    max_ratio = max(variance_ratios)
    min_ratio = min(variance_ratios)

    calibrated = k >= min_calibratable
    return CalibrationSummaryComputation(
        mean_variance_ratio=CalibrationStat.known(str(+mean_variance_ratio)),
        aggregate_bias=CalibrationStat.known(str(+aggregate_bias)),
        variance_ratio_dispersion=CalibrationStat.known(str(+dispersion)),
        underforecast_frequency=CalibrationStat.known(str(+underforecast_frequency)),
        max_variance_ratio=CalibrationStat.known(str(+max_ratio)),
        min_variance_ratio=CalibrationStat.known(str(+min_ratio)),
        calibration_status=(
            CalibrationStatus.CALIBRATED if calibrated else CalibrationStatus.UNDEFINED
        ),
        status_reason=(
            None
            if calibrated
            else CalibrationUndefinedReason.INSUFFICIENT_CALIBRATABLE_WINDOWS
        ),
    )
