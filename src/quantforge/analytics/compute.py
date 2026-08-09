"""Pure, deterministic statistic functions over sealed return vectors (§I, §J.3, O).

Everything Phase 15 computes that Phase 12 deferred, in stdlib :class:`~decimal.Decimal`
under the engine's pinned context — no numpy, no float, no wall-clock, no RNG (Principle
10; §O). The inputs are the sealed ``period_returns`` decimal strings of a
:class:`~quantforge.backtest.result.BacktestResult` (and, for the relative block, a
benchmark's), plus the recorded annualization convention. Every statistic is a pure
function of those, so identical inputs reproduce identical strings on any machine (§O).

These functions read no store and hold no state; the engine resolves and verifies the
sealed inputs and hands their vectors here. A statistic that is genuinely undefined for
the data (zero denominator, unmet precondition) is returned as a first-class UNDEFINED
:class:`~quantforge.analytics.model.StatValue` with a reason — **never** a
divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, or a silent omission (§Q, D5).

**Pinned formula methods** (folded into ``analytics-stats/1``; changing one bumps
:class:`~quantforge.analytics.version.AnalyticsEngineVersion`):

* **Moments are population moments** (matching ``stats.py``'s population volatility,
  D11):
  ``variance = Σ(x-μ)²/n``. ``skewness = μ₃/σ³``; ``excess_kurtosis = μ₄/σ⁴ - 3``.
* **Ratios are annualized by √(periods_per_year)** (Sortino, information ratio), exactly
  as ``stats.py`` annualizes Sharpe; raw dispersions (downside deviation, tracking
  error) are reported **per period**.
* **Downside deviation** is measured against the ``risk_free_per_period`` MAR target
  over
  **all** ``n`` observations: ``√(Σ min(rᵢ-target, 0)²/n)``.
* **Drawdown** is scale-invariant, so it is computed on the equity curve reconstructed
  by
  compounding the sealed returns (``e₀=1``, ``eᵢ=eᵢ₋₁·(1+rᵢ)``) — which equals the
  sealed curve divided by its opening equity, so this layer's drawdown matches the
  sealed ``max_drawdown`` by the identical scale-invariant formula, with no second
  source of truth. **Duration** = periods from the pre-drawdown peak to the max-drawdown
  trough; **recovery** = periods from that trough until the peak is regained
  (``UNRECOVERED`` otherwise).
* **Historical VaR/CVaR** use the **nearest-rank** empirical quantile (§J.3, D7): for
  confidence ``c`` the tail rank is ``k = ceil((1-c)·n)``; ``var`` is the ``k``-th
  smallest period return (signed — a negative value is a loss), and ``cvar`` is the
  arithmetic mean of the ``k`` smallest returns. No interpolation, no distribution
  assumption, no resampling, no RNG.
* **Single-factor OLS** (D4): ``beta = cov(r_p, r_b)/var(r_b)``;
  ``alpha = mean(r_p) - [rf + beta·(mean(r_b) - rf)]`` — closed-form scalar, no matrix.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Context, Decimal, InvalidOperation, localcontext

from quantforge.analytics.errors import AnalyticsConfigurationError
from quantforge.analytics.model import (
    ABSOLUTE_KEYS,
    RELATIVE_KEYS,
    AnalyticsUndefinedReason,
    StatValue,
)

__all__ = [
    "absolute_statistics",
    "parse_returns",
    "relative_statistics",
    "var_statistics",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)
_THREE = Decimal(3)


# -- parsing -----------------------------------------------------------------


def parse_returns(
    returns: tuple[str, ...] | list[str], *, context: Context
) -> list[Decimal]:
    """Parse a return vector into finite :class:`~decimal.Decimal`s (fail closed).

    Each element must be a finite decimal string (they are, having been sealed by the
    Phase 12 engine via ``str(+Decimal(...))``); a non-decimal or non-finite element is
    a corrupt input and raises :class:`AnalyticsConfigurationError` rather than being
    guessed. Parsing runs under the pinned ``context`` so the canonical form matches the
    engine's.
    """
    with localcontext(context):
        parsed: list[Decimal] = []
        for raw in returns:
            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError) as exc:
                raise AnalyticsConfigurationError(
                    f"period return {raw!r} is not a valid decimal string"
                ) from exc
            if not value.is_finite():
                raise AnalyticsConfigurationError(
                    f"period return {raw!r} must be finite"
                )
            parsed.append(+value)
        return parsed


# -- small population-moment helpers (run inside an active localcontext) ------


def _mean(xs: list[Decimal]) -> Decimal:
    return sum(xs, _ZERO) / Decimal(len(xs))


def _pvariance(xs: list[Decimal], mean: Decimal) -> Decimal:
    n = Decimal(len(xs))
    return sum(((x - mean) * (x - mean) for x in xs), _ZERO) / n


def _pstd(xs: list[Decimal], mean: Decimal, *, context: Context) -> Decimal:
    return _pvariance(xs, mean).sqrt(context)


def _covariance(
    xs: list[Decimal], ys: list[Decimal], mx: Decimal, my: Decimal
) -> Decimal:
    n = Decimal(len(xs))
    return sum(((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)), _ZERO) / n


def _known(value: Decimal) -> StatValue:
    """A KNOWN cell holding the canonical string form of ``value`` (under context)."""
    return StatValue.known(str(+value))


def _undef(reason: AnalyticsUndefinedReason) -> StatValue:
    return StatValue.undefined(reason)


# -- drawdown episode --------------------------------------------------------


class _Drawdown:
    """The max-drawdown episode of a compounded equity curve (scale-invariant)."""

    __slots__ = ("duration", "had_drawdown", "magnitude", "recovery")

    def __init__(
        self,
        *,
        magnitude: Decimal,
        duration: int | None,
        recovery: int | None,
        had_drawdown: bool,
    ) -> None:
        self.magnitude = magnitude
        self.duration = duration
        self.recovery = recovery
        self.had_drawdown = had_drawdown


def _drawdown_episode(returns: list[Decimal]) -> _Drawdown:
    """Locate the deepest drawdown of the compounded curve and its duration/recovery.

    The curve is ``e₀=1, eᵢ=eᵢ₋₁·(1+rᵢ)`` (``n+1`` points). The trough is the point of
    most-negative drawdown ``(eᵢ-peak)/peak`` (first occurrence on ties, so the result
    is deterministic); the pre-drawdown peak is the running-peak index at the trough.
    Duration is ``trough-peak``; recovery is the offset from the trough to the first
    later point that regains the peak level (``None`` if never regained). ``magnitude``
    is the positive depth ``-min_dd``.
    """
    curve = [_ONE]
    for r in returns:
        curve.append(curve[-1] * (_ONE + r))

    running_peak = curve[0]
    running_peak_idx = 0
    min_dd = _ZERO
    trough_idx = 0
    peak_idx = 0
    for i, value in enumerate(curve):
        if value > running_peak:
            running_peak = value
            running_peak_idx = i
        if running_peak > _ZERO:
            dd = (value - running_peak) / running_peak
            if dd < min_dd:
                min_dd = dd
                trough_idx = i
                peak_idx = running_peak_idx

    if min_dd == _ZERO:
        return _Drawdown(
            magnitude=_ZERO, duration=None, recovery=None, had_drawdown=False
        )

    peak_level = curve[peak_idx]
    recovery: int | None = None
    for j in range(trough_idx + 1, len(curve)):
        if curve[j] >= peak_level:
            recovery = j - trough_idx
            break
    return _Drawdown(
        magnitude=-min_dd,
        duration=trough_idx - peak_idx,
        recovery=recovery,
        had_drawdown=True,
    )


# -- absolute block ----------------------------------------------------------


def absolute_statistics(
    returns: list[str] | tuple[str, ...],
    *,
    risk_free_per_period: str,
    periods_per_year: str,
    context: Context,
) -> tuple[tuple[str, StatValue], ...]:
    """The absolute risk / distribution block over one return vector (§J.3).

    Returns the closed :data:`~quantforge.analytics.model.ABSOLUTE_KEYS` set in sorted
    key order, each a KNOWN or UNDEFINED :class:`~quantforge.analytics.model.StatValue`.
    Independent of any benchmark. Assumes ``n ≥ 2`` (the engine raises otherwise); a
    variance-based statistic still degrades to ``INSUFFICIENT_PERIODS`` if handed ``n <
    2`` directly, and to ``ZERO_VARIANCE`` / ``ZERO_DOWNSIDE`` / ``NO_DRAWDOWN`` when
    its denominator is zero — never a divide-by-zero.
    """
    with localcontext(context):
        r = parse_returns(returns, context=context)
        n = len(r)
        rf = +Decimal(risk_free_per_period)
        ppy = +Decimal(periods_per_year)
        ppy_root = ppy.sqrt(context)

        mean = _mean(r) if n else _ZERO
        std = _pstd(r, mean, context=context) if n else _ZERO

        out: dict[str, StatValue] = {}

        # -- distribution shape ---------------------------------------------
        out["best_period_return"] = (
            _known(max(r))
            if n
            else _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
        )
        out["worst_period_return"] = (
            _known(min(r))
            if n
            else _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
        )
        if n:
            positives = sum(_ONE for x in r if x > _ZERO)
            out["positive_period_fraction"] = _known(positives / Decimal(n))
        else:
            out["positive_period_fraction"] = _undef(
                AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
            )

        if n < 2:
            out["skewness"] = _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
            out["excess_kurtosis"] = _undef(
                AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
            )
        elif std == _ZERO:
            out["skewness"] = _undef(AnalyticsUndefinedReason.ZERO_VARIANCE)
            out["excess_kurtosis"] = _undef(AnalyticsUndefinedReason.ZERO_VARIANCE)
        else:
            m3 = sum(((x - mean) ** 3 for x in r), _ZERO) / Decimal(n)
            m4 = sum(((x - mean) ** 4 for x in r), _ZERO) / Decimal(n)
            out["skewness"] = _known(m3 / (std * std * std))
            out["excess_kurtosis"] = _known(m4 / (std * std * std * std) - _THREE)

        # -- downside deviation + Sortino -----------------------------------
        if n < 2:
            out["downside_deviation"] = _undef(
                AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
            )
            out["sortino"] = _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
        else:
            downside_sq = sum(
                ((x - rf) * (x - rf) for x in r if (x - rf) < _ZERO),
                _ZERO,
            )
            downside_dev = (downside_sq / Decimal(n)).sqrt(context)
            out["downside_deviation"] = _known(downside_dev)
            if downside_dev == _ZERO:
                out["sortino"] = _undef(AnalyticsUndefinedReason.ZERO_DOWNSIDE)
            else:
                out["sortino"] = _known((mean - rf) / downside_dev * ppy_root)

        # -- drawdown block (Calmar, duration, recovery) --------------------
        if n < 2:
            out["calmar"] = _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
            out["max_drawdown_duration_periods"] = _undef(
                AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
            )
            out["max_drawdown_recovery_periods"] = _undef(
                AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
            )
        else:
            dd = _drawdown_episode(r)
            if not dd.had_drawdown:
                out["calmar"] = _undef(AnalyticsUndefinedReason.NO_DRAWDOWN)
                out["max_drawdown_duration_periods"] = _undef(
                    AnalyticsUndefinedReason.NO_DRAWDOWN
                )
                out["max_drawdown_recovery_periods"] = _undef(
                    AnalyticsUndefinedReason.NO_DRAWDOWN
                )
            else:
                out["calmar"] = _known(mean * ppy / dd.magnitude)
                assert dd.duration is not None
                out["max_drawdown_duration_periods"] = _known(Decimal(dd.duration))
                if dd.recovery is None:
                    out["max_drawdown_recovery_periods"] = _undef(
                        AnalyticsUndefinedReason.UNRECOVERED_DRAWDOWN
                    )
                else:
                    out["max_drawdown_recovery_periods"] = _known(Decimal(dd.recovery))

        return tuple((key, out[key]) for key in ABSOLUTE_KEYS)


# -- relative block ----------------------------------------------------------


def relative_statistics(
    subject: list[str] | tuple[str, ...],
    benchmark: list[str] | tuple[str, ...],
    *,
    risk_free_per_period: str,
    periods_per_year: str,
    context: Context,
) -> tuple[tuple[str, StatValue], ...]:
    """The subject-vs-benchmark relative block (§J.3); vectors must be equal-length.

    Returns the closed :data:`~quantforge.analytics.model.RELATIVE_KEYS` set in sorted
    key order. Beta/alpha/capture become ``ZERO_BENCHMARK_VARIANCE`` when the benchmark
    has no dispersion / no up- or down-market denominator; information ratio becomes
    ``ZERO_TRACKING_ERROR`` with no active-return dispersion; correlation becomes
    ``ZERO_BENCHMARK_VARIANCE`` (benchmark flat) or ``ZERO_VARIANCE`` (subject flat) —
    all fail-closed, never a divide-by-zero (§Q).
    """
    with localcontext(context):
        rp = parse_returns(subject, context=context)
        rb = parse_returns(benchmark, context=context)
        if len(rp) != len(rb):  # pragma: no cover - engine verifies length first
            raise AnalyticsConfigurationError(
                "subject and benchmark return vectors must be equal length"
            )
        n = len(rp)
        rf = +Decimal(risk_free_per_period)
        ppy = +Decimal(periods_per_year)
        ppy_root = ppy.sqrt(context)

        out: dict[str, StatValue] = {}

        if n < 2:
            for key in RELATIVE_KEYS:
                out[key] = _undef(AnalyticsUndefinedReason.INSUFFICIENT_PERIODS)
            return tuple((key, out[key]) for key in RELATIVE_KEYS)

        mean_p = _mean(rp)
        mean_b = _mean(rb)
        var_b = _pvariance(rb, mean_b)
        var_p = _pvariance(rp, mean_p)
        cov = _covariance(rp, rb, mean_p, mean_b)

        # -- active return (arithmetic) + cumulative active return ----------
        out["active_return"] = _known(mean_p - mean_b)
        cum_p = _ONE
        cum_b = _ONE
        for x in rp:
            cum_p *= _ONE + x
        for x in rb:
            cum_b *= _ONE + x
        out["cumulative_active_return"] = _known((cum_p - _ONE) - (cum_b - _ONE))

        # -- tracking error + information ratio -----------------------------
        active = [p - b for p, b in zip(rp, rb, strict=True)]
        mean_active = _mean(active)
        tracking_error = _pstd(active, mean_active, context=context)
        out["tracking_error"] = _known(tracking_error)
        if tracking_error == _ZERO:
            out["information_ratio"] = _undef(
                AnalyticsUndefinedReason.ZERO_TRACKING_ERROR
            )
        else:
            out["information_ratio"] = _known(mean_active / tracking_error * ppy_root)

        # -- single-factor OLS beta / alpha ---------------------------------
        if var_b == _ZERO:
            out["beta"] = _undef(AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
            out["alpha"] = _undef(AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
        else:
            beta = cov / var_b
            out["beta"] = _known(beta)
            out["alpha"] = _known((mean_p - rf) - beta * (mean_b - rf))

        # -- correlation ----------------------------------------------------
        if var_b == _ZERO:
            out["correlation"] = _undef(
                AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE
            )
        elif var_p == _ZERO:
            out["correlation"] = _undef(AnalyticsUndefinedReason.ZERO_VARIANCE)
        else:
            std_p = var_p.sqrt(context)
            std_b = var_b.sqrt(context)
            out["correlation"] = _known(cov / (std_p * std_b))

        # -- up / down capture ----------------------------------------------
        out["up_capture"] = _capture(rp, rb, up=True)
        out["down_capture"] = _capture(rp, rb, up=False)

        return tuple((key, out[key]) for key in RELATIVE_KEYS)


def _capture(rp: list[Decimal], rb: list[Decimal], *, up: bool) -> StatValue:
    """Up-/down-market capture: mean subject return over mean benchmark return in the
    benchmark's up (``rb>0``) or down (``rb<0``) periods.

    Undefined (``ZERO_BENCHMARK_VARIANCE``) when there are no qualifying benchmark
    periods or their mean return is zero — a zero benchmark denominator, recorded never
    divided (§J.3 assigns capture to this reason).
    """
    subject_sum = _ZERO
    benchmark_sum = _ZERO
    count = 0
    for p, b in zip(rp, rb, strict=True):
        qualifies = b > _ZERO if up else b < _ZERO
        if qualifies:
            subject_sum += p
            benchmark_sum += b
            count += 1
    if count == 0 or benchmark_sum == _ZERO:
        return _undef(AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
    return _known(subject_sum / benchmark_sum)


# -- historical VaR / CVaR ---------------------------------------------------


def var_statistics(
    returns: list[str] | tuple[str, ...],
    confidences: list[str] | tuple[str, ...],
    *,
    context: Context,
) -> tuple[tuple[str, StatValue, StatValue], ...]:
    """Historical nearest-rank VaR & CVaR per confidence (§J.3, D7).

    For each confidence ``c`` (already validated strictly in ``(0, 1)`` and
    canonicalized by the spec), the tail rank is ``k = ceil((1-c)·n)`` and:

    * ``var`` = the ``k``-th smallest period return (ascending) — signed; a negative
      value
      is a loss;
    * ``cvar`` = the arithmetic mean of the ``k`` smallest returns.

    Returned as ``(confidence, var, cvar)`` triples sorted by confidence. With ``n ≥ 2``
    (engine-enforced) and ``c ∈ (0, 1)``, ``1 ≤ k ≤ n`` always, so both are KNOWN.
    """
    with localcontext(context):
        r = parse_returns(returns, context=context)
        n = len(r)
        ordered = sorted(r)
        result: list[tuple[str, StatValue, StatValue]] = []
        for c in sorted({str(+Decimal(conf)) for conf in confidences}):
            if n < 2:
                reason = AnalyticsUndefinedReason.INSUFFICIENT_PERIODS
                result.append((c, _undef(reason), _undef(reason)))
                continue
            tail = (_ONE - Decimal(c)) * Decimal(n)
            k = int(tail.to_integral_value(rounding=ROUND_CEILING))
            if k < 1:
                k = 1
            worst = ordered[:k]
            var_value = ordered[k - 1]
            cvar_value = sum(worst, _ZERO) / Decimal(len(worst))
            result.append((c, _known(var_value), _known(cvar_value)))
        return tuple(result)
