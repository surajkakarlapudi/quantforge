"""The pure net-of-cost accounting: cost placement, net summary, drag, break-even."""

from __future__ import annotations

from decimal import Decimal

from quantforge.factorportfolio.model import FactorPortfolioStatus
from quantforge.factorportfolio.model import StatValue as FPStatValue
from quantforge.factorportfolio.stats import series_summary
from quantforge.netcost.compute import (
    NetCostComputation,
    RealizedWindowInput,
    compute_net_of_cost,
)
from quantforge.netcost.model import (
    NetCostStat,
    NetCostStatus,
    NetCostUndefinedReason,
    StatStatus,
)
from quantforge.netcost.version import default_decimal_context

_PPY = "1"
_RF = "0"


def _known(cell: NetCostStat) -> Decimal:
    """The numeric value of a KNOWN cell (canonical trailing zeros ignored)."""
    assert cell.status is StatStatus.KNOWN
    assert cell.value is not None
    return Decimal(cell.value)


def _gross_cells(chained: list[str]) -> tuple[NetCostStat, NetCostStat, NetCostStat]:
    """The gross (mean, vol, sharpe) cells from the reused Phase 19 summary."""
    s = series_summary(
        chained,
        risk_free_per_period=_RF,
        periods_per_year=_PPY,
        context=default_decimal_context(),
    )

    def _c(cell: FPStatValue) -> NetCostStat:
        if cell.status is FactorPortfolioStatus.KNOWN:
            assert cell.value is not None
            return NetCostStat.known(cell.value)
        assert cell.reason is not None
        return NetCostStat.undefined(NetCostUndefinedReason(cell.reason.value))

    return _c(s.mean_period_return), _c(s.volatility), _c(s.annualized_sharpe)


def _run(windows: list[RealizedWindowInput], cost_rate: str) -> NetCostComputation:
    chained: list[str] = []
    for w in windows:
        chained.extend(w.oos_returns)
    gross_mean, gross_vol, gross_sharpe = _gross_cells(chained)
    return compute_net_of_cost(
        tuple(windows),
        gross_mean=gross_mean,
        gross_volatility=gross_vol,
        gross_sharpe=gross_sharpe,
        cost_rate=Decimal(cost_rate),
        risk_free_per_period=_RF,
        periods_per_year=_PPY,
        context=default_decimal_context(),
    )


# A first window with no prior (turnover UNDEFINED), then a charged window.
_GOLDEN = [
    RealizedWindowInput(index=0, oos_returns=("0.02",), turnover=None),
    RealizedWindowInput(index=1, oos_returns=("0.04",), turnover=Decimal("0.6")),
]


def test_golden_per_window_cells() -> None:
    comp = _run(_GOLDEN, "0.1")
    w0, w1 = comp.windows
    # Window 0: no prior -> zero cost, gross passes through.
    assert w0.gross_return == "0.02"
    assert w0.net_return == "0.02"
    assert w0.turnover.status is StatStatus.UNDEFINED
    assert w0.turnover.reason is NetCostUndefinedReason.NO_PRIOR_REALIZED_WINDOW
    assert w0.cost.status is StatStatus.UNDEFINED
    # Window 1: charged c*turnover = 0.1*0.6 = 0.06 at its first period.
    assert w1.gross_return == "0.04"
    assert _known(w1.turnover) == Decimal("0.6")
    assert _known(w1.cost) == Decimal("0.06")
    assert Decimal(w1.net_return) == Decimal("-0.02")


def test_golden_aggregates() -> None:
    comp = _run(_GOLDEN, "0.1")
    assert Decimal(comp.total_gross_return) == Decimal("0.06")
    assert Decimal(comp.total_turnover) == Decimal("0.6")
    assert Decimal(comp.total_cost) == Decimal("0.06")
    assert comp.n_periods == 2
    assert comp.n_charged == 1
    # net series = ["0.02", "-0.02"] -> mean 0, vol 0.02, sharpe 0.
    assert _known(comp.net_mean) == Decimal("0")
    assert _known(comp.net_volatility) == Decimal("0.02")
    assert _known(comp.net_sharpe) == Decimal("0")
    assert comp.net_status is NetCostStatus.MEASURED
    # gross mean 0.03 -> cost drag 0.03; gross sharpe 3 -> sharpe drag 3.
    assert _known(comp.gross_mean) == Decimal("0.03")
    assert _known(comp.cost_drag_mean) == Decimal("0.03")
    assert _known(comp.sharpe_drag) == Decimal("3")


def test_break_even_is_total_gross_over_total_turnover() -> None:
    comp = _run(_GOLDEN, "0.1")
    # c* = 0.06 / 0.6 = 0.1 (independent of the declared cost_rate).
    assert _known(comp.break_even_cost_rate) == Decimal("0.1")
    # Same break-even at a different declared rate.
    assert _known(_run(_GOLDEN, "0.5").break_even_cost_rate) == Decimal("0.1")


def test_zero_cost_identity() -> None:
    comp = _run(_GOLDEN, "0")
    assert Decimal(comp.total_cost) == Decimal("0")
    # At cost_rate == 0 the net moments equal the gross moments byte-identically.
    assert comp.net_mean == comp.gross_mean
    assert comp.net_volatility == comp.gross_volatility
    assert comp.net_sharpe == comp.gross_sharpe
    assert _known(comp.cost_drag_mean) == Decimal("0")
    assert _known(comp.sharpe_drag) == Decimal("0")


def test_net_mean_monotonic_decreasing_in_cost() -> None:
    means = [_known(_run(_GOLDEN, c).net_mean) for c in ("0", "0.05", "0.1")]
    assert means[0] > means[1] > means[2]


def test_degenerate_no_turnover() -> None:
    windows = [
        RealizedWindowInput(index=0, oos_returns=("0.05",), turnover=None),
        RealizedWindowInput(index=1, oos_returns=("0.08",), turnover=None),
    ]
    comp = _run(windows, "0.1")
    assert Decimal(comp.total_turnover) == Decimal("0")
    assert Decimal(comp.total_cost) == Decimal("0")
    assert comp.n_charged == 0
    assert comp.break_even_cost_rate.status is StatStatus.UNDEFINED
    assert (
        comp.break_even_cost_rate.reason
        is NetCostUndefinedReason.DEGENERATE_NO_TURNOVER
    )
    # No cost anywhere -> net equals gross.
    assert comp.net_mean == comp.gross_mean


def test_zero_net_variance_undefines_sharpe_only() -> None:
    windows = [
        RealizedWindowInput(index=0, oos_returns=("0.05",), turnover=None),
        RealizedWindowInput(index=1, oos_returns=("0.08",), turnover=Decimal("0.6")),
    ]
    # cost = 0.05*0.6 = 0.03 -> net = ["0.05", "0.05"] (constant).
    comp = _run(windows, "0.05")
    assert _known(comp.net_mean) == Decimal("0.05")
    assert _known(comp.net_volatility) == Decimal("0")
    assert comp.net_sharpe.status is StatStatus.UNDEFINED
    assert comp.net_sharpe.reason is NetCostUndefinedReason.ZERO_RETURN_VARIANCE
    assert comp.net_status is NetCostStatus.UNDEFINED
    assert comp.status_reason is NetCostUndefinedReason.ZERO_RETURN_VARIANCE


def test_multi_period_window_charges_only_first_period() -> None:
    windows = [
        RealizedWindowInput(index=0, oos_returns=("0.01", "0.02"), turnover=None),
        RealizedWindowInput(
            index=1, oos_returns=("0.03", "0.05"), turnover=Decimal("0.4")
        ),
    ]
    comp = _run(windows, "0.1")
    w1 = comp.windows[1]
    # cost = 0.1*0.4 = 0.04 at the first period only; window net sum = 0.08 - 0.04.
    assert _known(w1.cost) == Decimal("0.04")
    assert Decimal(w1.net_return) == Decimal("0.04")
    assert comp.n_periods == 4
