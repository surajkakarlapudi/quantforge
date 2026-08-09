"""Deterministic, ``Decimal``-only performance statistics (proposal §34, D9, §G).

Everything a v1 :class:`~quantforge.backtest.result.PerformanceSummary` reports,
computed in stdlib :class:`~decimal.Decimal` under the engine's pinned context — no
numpy, no float, no wall-clock (Principle 10; proposal §21, D9). The input is the equity
curve the engine marks at each rebalance (cash + sum shares x PIT mark), plus the
per-rebalance turnover the engine measures; every statistic is a pure function of those,
so identical inputs reproduce identical strings on any machine (proposal §G).

The v1 set (proposal §34), each documented and versioned into the summary:

* **period returns** — ``equity[i] / equity[i-1] - 1`` per step;
* **cumulative return** — ``equity[-1] / equity[0] - 1``;
* **arithmetic mean** period return and **volatility** (population standard deviation
  via :meth:`Decimal.sqrt`);
* **Sharpe** — ``(mean - rf_per_period) / vol`` annualized by
``sqrt(periods_per_year)``,
  with an **explicit** risk-free per-period constant (default ``"0"``) and an explicit
  ``periods_per_year`` — the annualization convention is a recorded input, never
  implicit (proposal §L open question 3, resolved: constant risk-free default + explicit
  ``periods_per_year``);
* **max drawdown** — the largest peak-to-trough decline of the equity curve;
* **turnover** — the mean per-rebalance turnover the engine supplies;
* **final / peak equity**.

Deferred (proposal §35): anything needing linear algebra or distributional machinery
(attribution, regression alpha/beta, information ratio, bootstrapped intervals).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from itertools import pairwise

from quantforge.backtest.errors import BacktestConfigurationError

__all__ = ["PerformanceStatistics", "compute_statistics"]

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class PerformanceStatistics:
    """The computed v1 statistic set, all canonical decimal strings (§34).

    A plain value object; the :class:`~quantforge.backtest.result.PerformanceSummary`
    wraps it with the annualization convention and the formula version for provenance.
    ``periods`` is the number of *return* observations (one fewer than equity marks).
    """

    periods: int
    initial_equity: str
    final_equity: str
    peak_equity: str
    cumulative_return: str
    mean_period_return: str
    volatility: str
    sharpe: str
    max_drawdown: str
    mean_turnover: str
    period_returns: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "periods": self.periods,
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "peak_equity": self.peak_equity,
            "cumulative_return": self.cumulative_return,
            "mean_period_return": self.mean_period_return,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "mean_turnover": self.mean_turnover,
            "period_returns": list(self.period_returns),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PerformanceStatistics:
        """Reconstruct the statistics from their :meth:`to_dict` payload (Phase 13 D3).

        The additive inverse of :meth:`to_dict`, so a sealed
        :class:`~quantforge.backtest.result.BacktestResult` round-trips byte-identically
        through the research sidecar. ``periods`` is a required int, every statistic a
        required decimal string, and ``period_returns`` an ordered list of decimal
        strings; a malformed payload fails closed with a :class:`ValueError`.
        """
        periods = raw["periods"]
        if not isinstance(periods, int):
            raise ValueError("periods must be an int")
        returns = raw["period_returns"]
        if not isinstance(returns, list) or not all(
            isinstance(r, str) for r in returns
        ):
            raise ValueError("period_returns must be a list of strings")
        return cls(
            periods=periods,
            initial_equity=_req_str(raw, "initial_equity"),
            final_equity=_req_str(raw, "final_equity"),
            peak_equity=_req_str(raw, "peak_equity"),
            cumulative_return=_req_str(raw, "cumulative_return"),
            mean_period_return=_req_str(raw, "mean_period_return"),
            volatility=_req_str(raw, "volatility"),
            sharpe=_req_str(raw, "sharpe"),
            max_drawdown=_req_str(raw, "max_drawdown"),
            mean_turnover=_req_str(raw, "mean_turnover"),
            period_returns=tuple(returns),
        )


def _req_str(raw: dict[str, object], key: str) -> str:
    """Read a required string from a decoded payload; fail closed otherwise."""
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def compute_statistics(
    equity_curve: list[Decimal],
    turnovers: list[Decimal],
    *,
    context: Context,
    risk_free_per_period: str = "0",
    periods_per_year: str = "1",
) -> PerformanceStatistics:
    """Compute the v1 statistics from an equity curve + per-rebalance turnovers (§34).

    Parameters
    ----------
    equity_curve:
        The ordered total-equity marks, one per rebalance (cash + sum shares x mark),
        in schedule order. Must be non-empty; the first mark is the opening equity.
    turnovers:
        The per-rebalance turnover fractions the engine measured (traded notional over
        equity); averaged into ``mean_turnover``. May be empty (no rebalance traded).
    context:
        The pinned decimal context (precision 34, ``ROUND_HALF_EVEN``); all arithmetic
        runs under it via ``localcontext``, so results are independent of caller state.
    risk_free_per_period:
        The risk-free return **per period** as a decimal string (default ``"0"``),
        subtracted from the mean before the Sharpe ratio. An explicit, recorded input.
    periods_per_year:
        The annualization factor as a decimal string; Sharpe is scaled by its square
        root. ``"1"`` leaves Sharpe un-annualized (per-period). An explicit input.

    A zero opening equity, or a zero-equity mark that would make a period return
    undefined, is a configuration defect (a backtest cannot start with no capital), and
    is raised — not silently divided (proposal §L: a raised error beats a wrong stat).
    """
    if not equity_curve:
        raise BacktestConfigurationError(
            "cannot compute statistics: the equity curve is empty; a backtest must "
            "produce at least one equity mark"
        )
    with localcontext(context):
        curve = [+value for value in equity_curve]
        initial = curve[0]
        if initial <= _ZERO:
            raise BacktestConfigurationError(
                f"opening equity {initial} must be strictly positive to compute "
                "returns; a backtest cannot start with no capital"
            )
        final = curve[-1]
        peak = max(curve)

        # -- period returns --------------------------------------------------
        returns: list[Decimal] = []
        for prev, cur in pairwise(curve):
            if prev <= _ZERO:
                raise BacktestConfigurationError(
                    f"equity mark {prev} is non-positive; a period return is undefined "
                    "against a wiped-out portfolio (fail closed, not divide-by-zero)"
                )
            returns.append(cur / prev - _ONE)

        cumulative = final / initial - _ONE

        # -- mean / volatility (population std dev) --------------------------
        n = len(returns)
        if n == 0:
            mean = _ZERO
            volatility = _ZERO
        else:
            mean = sum(returns, _ZERO) / Decimal(n)
            variance = sum(((r - mean) * (r - mean) for r in returns), _ZERO) / Decimal(
                n
            )
            volatility = variance.sqrt(context)

        # -- Sharpe (explicit rf + annualization) ----------------------------
        rf = +Decimal(risk_free_per_period)
        ppy = +Decimal(periods_per_year)
        if ppy <= _ZERO:
            raise BacktestConfigurationError(
                f"periods_per_year {periods_per_year!r} must be strictly positive"
            )
        if volatility == _ZERO:
            # No dispersion → Sharpe is undefined; report 0 rather than divide by zero
            # (a flat curve has no risk-adjusted signal). Recorded, not fabricated.
            sharpe = _ZERO
        else:
            sharpe = (mean - rf) / volatility * ppy.sqrt(context)

        # -- max drawdown ----------------------------------------------------
        max_dd = _ZERO
        running_peak = curve[0]
        for value in curve:
            if value > running_peak:
                running_peak = value
            if running_peak > _ZERO:
                drawdown = (value - running_peak) / running_peak
                if drawdown < max_dd:
                    max_dd = drawdown

        # -- turnover --------------------------------------------------------
        if turnovers:
            mean_turnover = sum((+t for t in turnovers), _ZERO) / Decimal(
                len(turnovers)
            )
        else:
            mean_turnover = _ZERO

        return PerformanceStatistics(
            periods=n,
            initial_equity=str(+initial),
            final_equity=str(+final),
            peak_equity=str(+peak),
            cumulative_return=str(+cumulative),
            mean_period_return=str(+mean),
            volatility=str(+volatility),
            sharpe=str(+sharpe),
            max_drawdown=str(+max_dd),
            mean_turnover=str(+mean_turnover),
            period_returns=tuple(str(+r) for r in returns),
        )
