"""The pure, deterministic one-sample calibration-significance test (§11, §12).

Given the sealed aggregate statistics of one
:class:`~quantforge.calibration.result.RiskForecastCalibration`'s calibratable-window
family - the mean variance ratio ``m``, the population dispersion ``s`` (the population
standard deviation of the per-window variance ratios), and the window count ``K`` (the
engine has already resolved and gated the source, CS-2) - plus the null mean
``null_mean`` (``1``), :func:`test_calibration_significance` computes the one-sample
large-sample two-sided test of ``H0: population mean variance ratio = null_mean``. All
arithmetic runs under an explicit :class:`decimal.Context`, in exact ``Decimal``, with
no RNG, no floating point, and no data-dependent iteration; the only elementary
transcendental is ``Decimal.sqrt`` (the standard error) and the only distribution is the
*reused* deterministic :func:`~quantforge._stats.normal.standard_normal_cdf` (``Φ``).

The family is passed as a :class:`CalibratableFamily` (``m``, ``s``, ``K``), or
``None`` when the source is not defensibly CALIBRATED (CS-2). With a family present
(CS-4 - the sealed statistics are consumed verbatim, never recomputed from the
per-window ratios):

* ``standard_error = s / sqrt(K)`` (the population-moment convention shared with
  Phase 24; equals ``sqrt(variance / K)`` since ``s = sqrt(variance)``).
* If ``s == 0`` the standard error is zero and ``t`` / ``p`` are UNDEFINED
  ``ZERO_RATIO_DISPERSION`` (never a divide-by-zero); ``m`` and the bias direction stay
  KNOWN (CS-3).
* Else ``t = (m - null_mean) / standard_error`` and the two-sided
  ``p = 2·(1 - Φ(|t|))``, clamped to ``[0, 1]`` - the large-sample test, deferring a
  finite-sample ``t``-distribution to a later phase (★, disclosed, matching Phase 24).

The **descriptive** bias direction (no significance): ``UNDER_FORECAST`` when
``m > null_mean``, ``OVER_FORECAST`` when ``m < null_mean``, ``UNBIASED`` when
``m == null_mean`` - KNOWN whenever ``m`` is (a present family).

``significance_status`` is ``TESTED`` when ``t`` / ``p`` are KNOWN, else ``UNDEFINED``
with the reason (``SOURCE_NOT_CALIBRATED`` for an absent family,
``ZERO_RATIO_DISPERSION`` for a degenerate one) - the engine seals a record either way
(CS-2/CS-3).

Pure: a function of the family, the null mean, and the context - no wall clock, no RNG,
no iteration-order dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge._stats.normal import standard_normal_cdf
from quantforge.calsig.model import (
    BiasDirection,
    SignificanceStat,
    SignificanceStatus,
    SignificanceUndefinedReason,
)

__all__ = [
    "CalibratableFamily",
    "SignificanceComputation",
    "test_calibration_significance",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)
_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class CalibratableFamily:
    """The sealed aggregate statistics of one calibratable-window family (CS-4).

    ``mean_variance_ratio`` and ``variance_ratio_dispersion`` are the source's KNOWN
    aggregate mean and population dispersion, each a ``Decimal`` parsed once from the
    sealed canonical decimal strings - never recomputed (CS-4); ``n_calibratable`` is
    the source's window count ``K`` (``>= 1``). Constructed by the engine only when the
    source is defensibly CALIBRATED; otherwise the family is ``None`` (CS-2).
    """

    mean_variance_ratio: Decimal
    variance_ratio_dispersion: Decimal
    n_calibratable: int


@dataclass(frozen=True, slots=True)
class SignificanceComputation:
    """The full pure result: the one-sample test statistics + roll-up (§11)."""

    mean_variance_ratio: SignificanceStat
    standard_error: SignificanceStat
    t_statistic: SignificanceStat
    p_value: SignificanceStat
    bias_direction: BiasDirection | None
    n_calibratable: int
    significance_status: SignificanceStatus
    status_reason: SignificanceUndefinedReason | None


def test_calibration_significance(
    family: CalibratableFamily | None,
    *,
    null_mean: Decimal,
    context: Context,
) -> SignificanceComputation:
    """Compute the one-sample two-sided significance test (§11, CS-2/CS-3/CS-4/CS-5).

    ``family`` is the sealed ``(mean, dispersion, K)`` bundle when the source is
    defensibly CALIBRATED, else ``None`` (CS-2). ``null_mean`` is the hypothesized mean
    (``1``); ``context`` is the pinned decimal context. Deterministic: identical inputs
    yield identical ``Decimal`` strings on any machine.
    """
    if family is None:
        undefined = SignificanceStat.undefined(
            SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED
        )
        return SignificanceComputation(
            mean_variance_ratio=undefined,
            standard_error=undefined,
            t_statistic=undefined,
            p_value=undefined,
            bias_direction=None,
            n_calibratable=0,
            significance_status=SignificanceStatus.UNDEFINED,
            status_reason=SignificanceUndefinedReason.SOURCE_NOT_CALIBRATED,
        )

    with localcontext(context):
        mean = family.mean_variance_ratio
        dispersion = family.variance_ratio_dispersion
        k = family.n_calibratable

        mean_cell = SignificanceStat.known(str(+mean))
        bias_direction = _bias_direction(mean, null_mean)

        if dispersion == _ZERO:
            # Degenerate family: no standard error, so t / p do not exist. The mean and
            # direction stay KNOWN; t / p are UNDEFINED, never a divide-by-zero (CS-3).
            zero_disp = SignificanceUndefinedReason.ZERO_RATIO_DISPERSION
            return SignificanceComputation(
                mean_variance_ratio=mean_cell,
                standard_error=SignificanceStat.known(str(+_ZERO)),
                t_statistic=SignificanceStat.undefined(zero_disp),
                p_value=SignificanceStat.undefined(zero_disp),
                bias_direction=bias_direction,
                n_calibratable=k,
                significance_status=SignificanceStatus.UNDEFINED,
                status_reason=zero_disp,
            )

        standard_error = dispersion / Decimal(k).sqrt()
        t_stat = (mean - null_mean) / standard_error
        abs_t = -t_stat if t_stat < _ZERO else t_stat
        cdf = standard_normal_cdf(abs_t, context=context)
        p_value = _TWO * (_ONE - cdf)
        if p_value < _ZERO:
            p_value = _ZERO
        elif p_value > _ONE:
            p_value = _ONE

    return SignificanceComputation(
        mean_variance_ratio=mean_cell,
        standard_error=SignificanceStat.known(str(+standard_error)),
        t_statistic=SignificanceStat.known(str(+t_stat)),
        p_value=SignificanceStat.known(str(+p_value)),
        bias_direction=bias_direction,
        n_calibratable=k,
        significance_status=SignificanceStatus.TESTED,
        status_reason=None,
    )


def _bias_direction(mean: Decimal, null_mean: Decimal) -> BiasDirection:
    """The descriptive sign of the mis-calibration (no significance; CS-5)."""
    if mean > null_mean:
        return BiasDirection.UNDER_FORECAST
    if mean < null_mean:
        return BiasDirection.OVER_FORECAST
    return BiasDirection.UNBIASED
