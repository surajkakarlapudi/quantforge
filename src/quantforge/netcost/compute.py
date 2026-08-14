"""The pure, deterministic net-of-cost accounting (§11, §12).

Given the realized windows of one sealed
:class:`~quantforge.stability.result.WalkForwardStability` - each carrying its chained
gross out-of-sample (OOS) return sub-series (from the walk-forward beneath the stability
record) and its one-way ``turnover_from_prev`` (KNOWN, or ``None`` when there is no
adjacent realized predecessor) - plus the declared linear cost rate ``c`` and the
inherited gross summary (the source's KNOWN gross moments, carried verbatim, NC-4),
:func:`compute_net_of_cost` computes the net-of-cost performance and the parameter-free
break-even cost rate. All arithmetic runs under an explicit :class:`decimal.Context`, in
exact ``Decimal``, with no RNG, no floating point, and no data-dependent iteration; the
only elementary transcendental is the ``Decimal.sqrt`` **inside** the reused Phase 19
:func:`~quantforge.factorportfolio.stats.series_summary` (the net Sharpe).

**The alignment (the load-bearing decision).** Gross performance is a *per-period*
chained series; turnover is a *per-window* one-way quantity. They are **not** zippable.
The cost of re-solving the book at the start of realized window ``w`` is a one-time
charge ``c · turnover_w`` borne at that window's **first** OOS period - so the net
series equals the gross series with ``c · turnover_w`` subtracted from the first period
of each realized window that has a KNOWN turnover:

    net[first period of window w] = gross[first period of window w] - c · turnover_w

A window with no adjacent realized predecessor (Phase 27's
``NO_PRIOR_REALIZED_WINDOW``) has no turnover to charge, so it bears **zero** cost (no
fabricated entry cost, NC-3 - a documented deviation from the proposal's
``entry_cost_convention``) and its gross periods pass through unchanged.

The net series is then summarized with the *identical* reused Phase 19 summary the
walk-forward used for its gross summary, so the net annualized Sharpe is directly
comparable to the gross one. The aggregate cost drag is ``gross_mean - net_mean`` and
``gross_sharpe - net_sharpe`` (UNDEFINED-propagating). The break-even cost rate is
``c* = Σ gross / Σ turnover`` when total one-way turnover is strictly positive - the
declared-``c``-independent rate at which the gross edge is exactly erased - else
UNDEFINED ``DEGENERATE_NO_TURNOVER`` (a never-trading strategy has no such rate), never
a divide-by-zero (NC-5).

Pure: a function of the windows, the cost rate, the inherited gross moments, the
annualization convention, and the context - no wall clock, no RNG, no iteration-order
dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.factorportfolio.model import FactorPortfolioStatus, StatValue
from quantforge.factorportfolio.stats import series_summary
from quantforge.netcost.model import (
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
    StatStatus,
)

__all__ = [
    "NetCostComputation",
    "RealizedWindowInput",
    "WindowNetCost",
    "compute_net_of_cost",
]

_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class RealizedWindowInput:
    """One realized window's chained gross returns + its one-way turnover (NC-2/NC-4).

    ``index`` is the source window's index; ``oos_returns`` are the window's realized
    OOS return decimal strings in test-date order (the same numbers as the walk's
    chained gross series, sliced per window; consumed verbatim, NC-4); ``turnover`` is
    the KNOWN one-way ``turnover_from_prev`` parsed once to a ``Decimal``, or ``None``
    when the source sealed it UNDEFINED (no adjacent realized predecessor, so no trade
    to charge).
    """

    index: int
    oos_returns: tuple[str, ...]
    turnover: Decimal | None


@dataclass(frozen=True, slots=True)
class WindowNetCost:
    """One realized window's gross / turnover / cost / net aggregate (§11).

    ``n_periods`` is the window's OOS-period count; ``gross_return`` the additive
    aggregate ``Σ`` of its per-period gross returns (the aggregate consistent with the
    arithmetic-mean summary and the one-time linear cost); ``turnover`` and ``cost`` are
    UNDEFINED-preserving cells (both ``NO_PRIOR_REALIZED_WINDOW`` when the window has no
    adjacent realized predecessor - zero cost, no fabricated entry cost); ``net_return``
    the additive aggregate of the window's per-period net returns
    (``gross_return - cost`` for a charged window).
    """

    index: int
    n_periods: int
    gross_return: str
    turnover: NetCostStat
    cost: NetCostStat
    net_return: str


@dataclass(frozen=True, slots=True)
class NetCostComputation:
    """The full pure result: per-window cells + the aggregate net-of-cost summary
    (§11)."""

    windows: tuple[WindowNetCost, ...]
    gross_mean: NetCostStat
    gross_volatility: NetCostStat
    gross_sharpe: NetCostStat
    net_mean: NetCostStat
    net_volatility: NetCostStat
    net_sharpe: NetCostStat
    cost_drag_mean: NetCostStat
    sharpe_drag: NetCostStat
    break_even_cost_rate: NetCostStat
    total_gross_return: str
    total_turnover: str
    total_cost: str
    n_periods: int
    n_charged: int
    net_status: NetCostStatus
    status_reason: NetCostUndefinedReason | None


def compute_net_of_cost(
    windows: tuple[RealizedWindowInput, ...],
    *,
    gross_mean: NetCostStat,
    gross_volatility: NetCostStat,
    gross_sharpe: NetCostStat,
    cost_rate: Decimal,
    risk_free_per_period: str,
    periods_per_year: str,
    context: Context,
) -> NetCostComputation:
    """Charge the cost, summarize net-of-cost, find the break-even (§11, NC-2..NC-5).

    ``windows`` are the realized windows in source order; ``gross_mean`` /
    ``gross_volatility`` / ``gross_sharpe`` are the source walk's KNOWN (or UNDEFINED)
    gross moments carried verbatim (NC-4); ``cost_rate`` is the declared linear one-way
    rate; ``risk_free_per_period`` / ``periods_per_year`` are the annualization
    convention carried from the walk (so the net Sharpe matches the gross convention);
    ``context`` is the pinned decimal context. Deterministic: identical inputs yield
    identical ``Decimal`` strings on any machine.
    """
    with localcontext(context):
        window_cells: list[WindowNetCost] = []
        net_series: list[str] = []
        total_gross = _ZERO
        total_turnover = _ZERO
        total_cost = _ZERO
        n_periods = 0
        n_charged = 0

        for window in windows:
            gross_vals = [+Decimal(r) for r in window.oos_returns]
            gross_sum = sum(gross_vals, _ZERO)
            n_periods += len(gross_vals)

            if window.turnover is None:
                # No adjacent realized predecessor: no trade to charge, so zero cost (no
                # fabricated entry cost, NC-3). Gross passes through to the net series.
                turnover_cell = NetCostStat.undefined(
                    NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW
                )
                cost_cell = NetCostStat.undefined(
                    NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW
                )
                net_vals = list(gross_vals)
                net_sum = gross_sum
            else:
                cost = +(cost_rate * window.turnover)
                turnover_cell = NetCostStat.known(str(+window.turnover))
                cost_cell = NetCostStat.known(str(+cost))
                total_turnover += window.turnover
                total_cost += cost
                n_charged += 1
                # The one-time rebalancing cost is borne at the window's first OOS
                # period (NC-2). A realized window always has >= 1 OOS period.
                net_vals = list(gross_vals)
                net_vals[0] = +(net_vals[0] - cost)
                net_sum = gross_sum - cost

            total_gross += gross_sum
            net_series.extend(str(+v) for v in net_vals)
            window_cells.append(
                WindowNetCost(
                    index=window.index,
                    n_periods=len(gross_vals),
                    gross_return=str(+gross_sum),
                    turnover=turnover_cell,
                    cost=cost_cell,
                    net_return=str(+net_sum),
                )
            )

        total_gross = +total_gross
        total_turnover = +total_turnover
        total_cost = +total_cost

        # Break-even cost rate: the declared-cost-independent rate at which the gross
        # edge is exactly erased. UNDEFINED (never a divide-by-zero) when the strategy
        # never trades (NC-5).
        if total_turnover == _ZERO:
            break_even = NetCostStat.undefined(
                NetCostUndefinedReason.DEGENERATE_NO_TURNOVER
            )
        else:
            break_even = NetCostStat.known(str(+(total_gross / total_turnover)))

        # Summarize the net series with the reused Phase 19 method (the identical
        # convention the walk used for gross), so the net Sharpe is comparable (NC-4).
        net_summary = series_summary(
            net_series,
            risk_free_per_period=risk_free_per_period,
            periods_per_year=periods_per_year,
            context=context,
        )
        net_mean = _from_series_cell(net_summary.mean_period_return)
        net_volatility = _from_series_cell(net_summary.volatility)
        net_sharpe = _from_series_cell(net_summary.annualized_sharpe)

        cost_drag_mean = _subtract(gross_mean, net_mean)
        sharpe_drag = _subtract(gross_sharpe, net_sharpe)

    if net_sharpe.status is StatStatus.KNOWN:
        net_status = NetCostStatus.MEASURED
        status_reason: NetCostUndefinedReason | None = None
    else:
        net_status = NetCostStatus.UNDEFINED
        status_reason = net_sharpe.reason

    return NetCostComputation(
        windows=tuple(window_cells),
        gross_mean=gross_mean,
        gross_volatility=gross_volatility,
        gross_sharpe=gross_sharpe,
        net_mean=net_mean,
        net_volatility=net_volatility,
        net_sharpe=net_sharpe,
        cost_drag_mean=cost_drag_mean,
        sharpe_drag=sharpe_drag,
        break_even_cost_rate=break_even,
        total_gross_return=str(total_gross),
        total_turnover=str(total_turnover),
        total_cost=str(total_cost),
        n_periods=n_periods,
        n_charged=n_charged,
        net_status=net_status,
        status_reason=status_reason,
    )


def _from_series_cell(cell: StatValue) -> NetCostStat:
    """Map a reused Phase 19 summary cell to a :class:`NetCostStat` (NC-4).

    A KNOWN cell carries its canonical decimal string across verbatim; an UNDEFINED cell
    carries its reason across by value (the three summary reason strings are identical
    across the two enums, so this never re-interprets - it only relabels the owning
    layer). A summary cell can only be UNDEFINED for one of those three reasons; an
    unexpected reason is a corrupt primitive and surfaces as a ``ValueError``.
    """
    if cell.status is FactorPortfolioStatus.KNOWN:
        assert cell.value is not None  # guaranteed by StatValue.__post_init__
        return NetCostStat.known(cell.value)
    assert cell.reason is not None  # guaranteed by StatValue.__post_init__
    return NetCostStat.undefined(NetCostUndefinedReason(cell.reason.value))


def _subtract(a: NetCostStat, b: NetCostStat) -> NetCostStat:
    """``a - b`` as a cell, propagating UNDEFINED (must run inside a ``localcontext``).

    When both operands are KNOWN, the difference is a KNOWN canonical decimal string;
    when either is UNDEFINED the result is UNDEFINED with the first undefined operand's
    reason (``a`` takes precedence) - a drag against a missing moment is itself missing,
    never fabricated (NC-5).
    """
    if a.status is not StatStatus.KNOWN:
        assert a.reason is not None
        return NetCostStat.undefined(a.reason)
    if b.status is not StatStatus.KNOWN:
        assert b.reason is not None
        return NetCostStat.undefined(b.reason)
    assert a.value is not None and b.value is not None
    return NetCostStat.known(str(+(Decimal(a.value) - Decimal(b.value))))
