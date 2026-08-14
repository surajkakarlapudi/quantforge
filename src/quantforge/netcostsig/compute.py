"""The pure, deterministic one-sample net-of-cost-significance test (§11, §12).

Given the sealed aggregate statistics of one
:class:`~quantforge.netcost.result.NetOfCostPerformance`'s realized net series - the
after-cost mean return ``m``, the population volatility ``s`` (the population standard
deviation of the per-period net returns), and the period count ``n`` (the engine has
already resolved and gated the source, NS-2) - plus the null mean ``null_mean`` (``0``),
:func:`test_net_of_cost_significance` computes the one-sample large-sample
**upper-tailed** test of ``H0: population net mean return <= null_mean`` vs ``H1: >
null_mean``. All arithmetic runs under an explicit :class:`decimal.Context`, in exact
``Decimal``, with no RNG, no floating point, and no data-dependent iteration; the only
elementary transcendental is ``Decimal.sqrt`` (the standard error) and the only
distribution is the *reused* deterministic
:func:`~quantforge._stats.normal.standard_normal_cdf` (``Φ``).

The series is passed as a :class:`MeasuredNetSeries` (``m``, ``s``, ``n``), or ``None``
when the source is not defensibly MEASURED (NS-2). With a series present (NS-4 - the
sealed statistics are consumed verbatim, never recomputed from the per-window cells):

* ``standard_error = s / sqrt(n)`` (the standard error of the mean; the
  population-moment convention shared with Phases 24/29).
* If ``s == 0`` the standard error is zero and ``t`` / ``p`` are UNDEFINED
  ``ZERO_NET_VOLATILITY`` (never a divide-by-zero); ``m`` and the edge direction stay
  KNOWN (NS-3).
* Else ``t = (m - null_mean) / standard_error`` and the one-sided upper-tailed
  ``p = 1 - Φ(t)``, clamped to ``[0, 1]`` - the large-sample test, deferring a
  finite-sample ``t``-distribution to a later phase (★, disclosed, matching Phases
  24/29). The test is one-sided because after-cost profitability is inherently
  directional (does the strategy earn a *positive* return after costs?), matching the
  one-sided posture of the Phase 23 Probabilistic Sharpe Ratio.

The **descriptive** edge direction (no significance): ``PROFITABLE`` when
``m > null_mean``, ``UNPROFITABLE`` when ``m < null_mean``, ``FLAT`` when
``m == null_mean`` - KNOWN whenever ``m`` is (a present series).

``significance_status`` is ``TESTED`` when ``t`` / ``p`` are KNOWN, else ``UNDEFINED``
with the reason (``SOURCE_NOT_MEASURED`` for an absent series, ``ZERO_NET_VOLATILITY``
for a degenerate one) - the engine seals a record either way (NS-2/NS-3).

Pure: a function of the series, the null mean, and the context - no wall clock, no RNG,
no iteration-order dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge._stats.normal import standard_normal_cdf
from quantforge.netcostsig.model import (
    EdgeDirection,
    NetCostSigUndefinedReason,
    SignificanceStat,
    SignificanceStatus,
)

__all__ = [
    "MeasuredNetSeries",
    "SignificanceComputation",
    "test_net_of_cost_significance",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class MeasuredNetSeries:
    """The sealed aggregate statistics of one realized net series (NS-4).

    ``net_mean`` and ``net_volatility`` are the source's KNOWN after-cost mean and
    population volatility, each a ``Decimal`` parsed once from the sealed canonical
    decimal strings - never recomputed (NS-4); ``n_periods`` is the source's net-series
    period count ``n`` (``>= 1``). Constructed by the engine only when the source is
    defensibly MEASURED; otherwise the series is ``None`` (NS-2).
    """

    net_mean: Decimal
    net_volatility: Decimal
    n_periods: int


@dataclass(frozen=True, slots=True)
class SignificanceComputation:
    """The full pure result: the one-sample test statistics + roll-up (§11)."""

    net_mean: SignificanceStat
    standard_error: SignificanceStat
    t_statistic: SignificanceStat
    p_value: SignificanceStat
    edge_direction: EdgeDirection | None
    n_periods: int
    significance_status: SignificanceStatus
    status_reason: NetCostSigUndefinedReason | None


def test_net_of_cost_significance(
    series: MeasuredNetSeries | None,
    *,
    null_mean: Decimal,
    context: Context,
) -> SignificanceComputation:
    """Compute the one-sample upper-tailed significance test (§11, NS-2/NS-3/NS-4/NS-5).

    ``series`` is the sealed ``(mean, volatility, n)`` bundle when the source is
    defensibly MEASURED, else ``None`` (NS-2). ``null_mean`` is the hypothesized mean
    (``0``); ``context`` is the pinned decimal context. Deterministic: identical inputs
    yield identical ``Decimal`` strings on any machine.
    """
    if series is None:
        undefined = SignificanceStat.undefined(
            NetCostSigUndefinedReason.SOURCE_NOT_MEASURED
        )
        return SignificanceComputation(
            net_mean=undefined,
            standard_error=undefined,
            t_statistic=undefined,
            p_value=undefined,
            edge_direction=None,
            n_periods=0,
            significance_status=SignificanceStatus.UNDEFINED,
            status_reason=NetCostSigUndefinedReason.SOURCE_NOT_MEASURED,
        )

    with localcontext(context):
        mean = series.net_mean
        volatility = series.net_volatility
        n = series.n_periods

        mean_cell = SignificanceStat.known(str(+mean))
        edge_direction = _edge_direction(mean, null_mean)

        if volatility == _ZERO:
            # Degenerate net series: no standard error, so t / p do not exist. The mean
            # and direction stay KNOWN; t / p are UNDEFINED, never a divide-by-zero
            # (NS-3).
            zero_vol = NetCostSigUndefinedReason.ZERO_NET_VOLATILITY
            return SignificanceComputation(
                net_mean=mean_cell,
                standard_error=SignificanceStat.known(str(+_ZERO)),
                t_statistic=SignificanceStat.undefined(zero_vol),
                p_value=SignificanceStat.undefined(zero_vol),
                edge_direction=edge_direction,
                n_periods=n,
                significance_status=SignificanceStatus.UNDEFINED,
                status_reason=zero_vol,
            )

        standard_error = volatility / Decimal(n).sqrt()
        t_stat = (mean - null_mean) / standard_error
        cdf = standard_normal_cdf(t_stat, context=context)
        p_value = _ONE - cdf
        if p_value < _ZERO:
            p_value = _ZERO
        elif p_value > _ONE:
            p_value = _ONE

    return SignificanceComputation(
        net_mean=mean_cell,
        standard_error=SignificanceStat.known(str(+standard_error)),
        t_statistic=SignificanceStat.known(str(+t_stat)),
        p_value=SignificanceStat.known(str(+p_value)),
        edge_direction=edge_direction,
        n_periods=n,
        significance_status=SignificanceStatus.TESTED,
        status_reason=None,
    )


def _edge_direction(mean: Decimal, null_mean: Decimal) -> EdgeDirection:
    """The descriptive sign of the after-cost edge (no significance; NS-5)."""
    if mean > null_mean:
        return EdgeDirection.PROFITABLE
    if mean < null_mean:
        return EdgeDirection.UNPROFITABLE
    return EdgeDirection.FLAT
