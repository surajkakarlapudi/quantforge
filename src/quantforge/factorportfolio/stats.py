"""Pure, deterministic quantile leg formation + factor-return series aggregation (§12).

Everything Phase 19 computes, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context - no numpy, no float, no wall-clock, no RNG (Principle 10). The inputs
are the eligible per-member ``(company_id, signal_string, forward_return_string)``
triples the engine paired at each rebalance date, plus the per-period factor-return
series it chains across the valid dates. Every statistic is a pure function of those, so
identical inputs reproduce identical strings on any machine.

This module reads no store and holds no state; the engine resolves and pairs the inputs
and hands their vectors here. A statistic that is genuinely undefined for the data (a
period below the leg floor, an empty long or short leg, a series with no or a single
valid period, a zero-dispersion series for the Sharpe / t-statistic) is returned as a
first-class UNDEFINED :class:`~quantforge.factorportfolio.model.StatValue` with a reason
- **never** a divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, a dropped member,
or a silent omission (§9, §12, P19-4).

**Pinned formula methods** (folded into ``factorportfolio-stats/1``; changing one bumps
:class:`~quantforge.factorportfolio.version.FactorPortfolioEngineVersion`):

* **Quantile leg formation** reuses the Phase 16 ``quantile_buckets`` rule **verbatim**
  (D-QUANTILE): members are ordered by (signal ascending, then ``company_id``); the
  member at ``0``-based ordinal ``i`` is assigned ``bucket = floor(i·Q/n)`` (clamped to
  ``Q-1``). The **bottom** bucket (``0``, the lowest-signal members) is the **short**
  leg; the **top** bucket (``Q-1``, the highest-signal members) is the **long** leg
  (high-minus-low on the raw signal, no sign flip - D-LEG).
* **Per-leg return** is the equal-weight mean forward return of the leg's members
  (``Σ/n``, D-WEIGHT); the **per-period factor return** is the long-minus-short spread
  ``f_T = mean(long) - mean(short)`` (dollar-neutral, gross - D-LEG).
* **Series summary** over the ``M`` valid per-period factor returns (D-SUMMARY):
  ``cumulative = ∏(1+f_T) - 1`` (compounded); ``mean = (1/M) Σ f_T``; ``volatility`` the
  **population** standard deviation ``√(Σ(f_T-mean)²/M)``; ``annualized_sharpe =
  (mean - rf)/volatility · √periods_per_year`` (via ``Decimal.sqrt`` under the pinned
  context, the Phase 12 precedent); the mean's ``t_stat = mean/(volatility/√M)``;
  ``hit_rate = #(f_T > 0)/M``. ``M = 0`` is ``NO_VALID_PERIODS``; ``M = 1`` leaves the
  cumulative / mean / hit-rate KNOWN but the dispersion cells (volatility / Sharpe /
  t-stat) ``SINGLE_VALID_PERIOD``; a zero population dispersion leaves the Sharpe /
  t-statistic ``ZERO_RETURN_VARIANCE`` (volatility is a KNOWN ``0``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge.factorportfolio.errors import FactorPortfolioConsistencyError
from quantforge.factorportfolio.model import (
    FactorPortfolioUndefinedReason,
    StatValue,
)

__all__ = [
    "PeriodLegResult",
    "SeriesSummary",
    "period_factor_return",
    "series_summary",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _parse_decimal(raw: str, *, what: str) -> Decimal:
    """Parse one finite :class:`~decimal.Decimal` (fail closed).

    The panel / forward-return machinery sealed every value via ``str(+Decimal(...))``;
    a non-decimal or non-finite element is a corrupt corpus value and raises
    :class:`FactorPortfolioConsistencyError` rather than being guessed (P19-4's
    fail-closed posture for a corrupt corpus value).
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise FactorPortfolioConsistencyError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise FactorPortfolioConsistencyError(f"{what} {raw!r} must be finite")
    return +value


def _mean(xs: list[Decimal]) -> Decimal:
    return sum(xs, _ZERO) / Decimal(len(xs))


@dataclass(frozen=True, slots=True)
class PeriodLegResult:
    """One rebalance date's leg membership + leg means + the long-minus-short spread.

    ``long_ids`` / ``short_ids`` are the ``company_id``s the quantile sort placed in the
    top / bottom bucket, each **sorted ascending** by ``company_id`` (deterministic
    audit metadata). ``long_return`` / ``short_return`` are each leg's equal-weight mean
    forward return; ``factor_return`` the long-minus-short spread - each a
    :class:`~quantforge.factorportfolio.model.StatValue`. A period below the leg floor
    or with an empty long / short leg yields UNDEFINED legs and factor return (with the
    floor / empty-leg reason) and empty membership tuples - recorded, never dropped.
    """

    long_ids: tuple[str, ...]
    short_ids: tuple[str, ...]
    long_return: StatValue
    short_return: StatValue
    factor_return: StatValue


def period_factor_return(
    members: list[tuple[str, str, str]],
    quantiles: int,
    *,
    context: Context,
) -> PeriodLegResult:
    """Form the long/short legs and the factor return for one rebalance date (§12).

    ``members`` is the eligible list of ``(company_id, signal_string,
    forward_return_string)`` for this date (a member lacking the PIT signal or a
    computable forward return was already excluded by the engine and counted in
    coverage). Members are ordered by (signal ascending, then ``company_id``); ordinal
    ``i`` is assigned ``bucket = floor(i·Q/n)`` (clamped to ``Q-1``). The bottom bucket
    is the short leg, the top bucket the long leg; each leg's return is its equal-weight
    mean forward return, and the factor return is long-minus-short.

    A period with ``n_members < 2·Q`` (the leg floor, both legs guaranteed non-empty)
    yields all-``INSUFFICIENT_MEMBERS`` cells and empty membership; a
    defensively-detected empty top / bottom bucket yields ``EMPTY_LONG_LEG`` /
    ``EMPTY_SHORT_LEG``. Never a divide-by-zero, never a fabricated leg (P19-4).
    """
    n = len(members)
    empty = ()
    if n < 2 * quantiles:
        reason = FactorPortfolioUndefinedReason.INSUFFICIENT_MEMBERS
        undef = StatValue.undefined(reason)
        return PeriodLegResult(
            long_ids=empty,
            short_ids=empty,
            long_return=undef,
            short_return=undef,
            factor_return=undef,
        )
    with localcontext(context):
        parsed = [
            (
                cid,
                _parse_decimal(sig, what="signal"),
                _parse_decimal(ret, what="forward return"),
            )
            for cid, sig, ret in members
        ]
        ordered = sorted(parsed, key=lambda t: (t[1], t[0]))
        buckets: list[list[tuple[str, Decimal]]] = [[] for _ in range(quantiles)]
        for i, (cid, _sig, ret) in enumerate(ordered):
            b = (i * quantiles) // n
            if b >= quantiles:
                b = quantiles - 1
            buckets[b].append((cid, ret))

        short_bucket = buckets[0]
        long_bucket = buckets[quantiles - 1]
        long_ids = tuple(sorted(cid for cid, _ret in long_bucket))
        short_ids = tuple(sorted(cid for cid, _ret in short_bucket))

        if not long_bucket:
            reason = FactorPortfolioUndefinedReason.EMPTY_LONG_LEG
            undef = StatValue.undefined(reason)
            return PeriodLegResult(
                long_ids=long_ids,
                short_ids=short_ids,
                long_return=undef,
                short_return=undef,
                factor_return=undef,
            )
        if not short_bucket:
            reason = FactorPortfolioUndefinedReason.EMPTY_SHORT_LEG
            undef = StatValue.undefined(reason)
            return PeriodLegResult(
                long_ids=long_ids,
                short_ids=short_ids,
                long_return=undef,
                short_return=undef,
                factor_return=undef,
            )

        long_mean = _mean([ret for _cid, ret in long_bucket])
        short_mean = _mean([ret for _cid, ret in short_bucket])
        factor = long_mean - short_mean
        return PeriodLegResult(
            long_ids=long_ids,
            short_ids=short_ids,
            long_return=StatValue.known(str(+long_mean)),
            short_return=StatValue.known(str(+short_mean)),
            factor_return=StatValue.known(str(+factor)),
        )


@dataclass(frozen=True, slots=True)
class SeriesSummary:
    """The aggregated summary cells + the count of valid periods (§12).

    Six UNDEFINED-preserving :class:`~quantforge.factorportfolio.model.StatValue` cells
    (cumulative, mean, volatility, annualized Sharpe, mean t-statistic, hit rate) plus
    ``n_valid_periods`` - the count of per-period factor returns that were KNOWN.
    """

    cumulative_return: StatValue
    mean_period_return: StatValue
    volatility: StatValue
    annualized_sharpe: StatValue
    mean_t_stat: StatValue
    hit_rate: StatValue
    n_valid_periods: int


def series_summary(
    factor_returns: list[str],
    *,
    risk_free_per_period: str,
    periods_per_year: str,
    context: Context,
) -> SeriesSummary:
    """Aggregate the valid per-period factor returns into a performance summary (§12).

    ``factor_returns`` is the ordered list of the **KNOWN** per-period factor-return
    decimal strings over the valid rebalance dates (UNDEFINED periods contribute
    nothing). ``risk_free_per_period`` / ``periods_per_year`` are canonical decimal
    strings (the annualization convention, folded into identity). Returns a
    :class:`SeriesSummary`:

    * ``M = 0`` -> every cell ``NO_VALID_PERIODS`` (there is no series to aggregate);
    * ``M = 1`` -> cumulative / mean / hit-rate KNOWN, volatility / Sharpe / t-stat
      ``SINGLE_VALID_PERIOD``;
    * ``M >= 2`` -> cumulative / mean / volatility / hit-rate KNOWN; Sharpe / t-stat
      KNOWN unless the population volatility is exactly zero, in which case both are
      ``ZERO_RETURN_VARIANCE`` (never a divide-by-zero).
    """
    m = len(factor_returns)
    if m == 0:
        undef = StatValue.undefined(FactorPortfolioUndefinedReason.NO_VALID_PERIODS)
        return SeriesSummary(
            cumulative_return=undef,
            mean_period_return=undef,
            volatility=undef,
            annualized_sharpe=undef,
            mean_t_stat=undef,
            hit_rate=undef,
            n_valid_periods=0,
        )
    with localcontext(context):
        values = [
            +Decimal(v) for v in factor_returns
        ]  # already-canonical KNOWN strings
        # Cumulative compounded return ∏(1+f_T) - 1.
        compounded = _ONE
        for v in values:
            compounded *= _ONE + v
        cumulative_cell = StatValue.known(str(+(compounded - _ONE)))
        mean = sum(values, _ZERO) / Decimal(m)
        mean_cell = StatValue.known(str(+mean))
        positive = sum(1 for v in values if v > _ZERO)
        hit_rate_cell = StatValue.known(str(+(Decimal(positive) / Decimal(m))))

        if m == 1:
            single = StatValue.undefined(
                FactorPortfolioUndefinedReason.SINGLE_VALID_PERIOD
            )
            return SeriesSummary(
                cumulative_return=cumulative_cell,
                mean_period_return=mean_cell,
                volatility=single,
                annualized_sharpe=single,
                mean_t_stat=single,
                hit_rate=hit_rate_cell,
                n_valid_periods=1,
            )

        variance = sum(((v - mean) * (v - mean) for v in values), _ZERO) / Decimal(m)
        volatility = variance.sqrt(context)
        volatility_cell = StatValue.known(str(+volatility))
        if volatility == _ZERO:
            zero_var = StatValue.undefined(
                FactorPortfolioUndefinedReason.ZERO_RETURN_VARIANCE
            )
            return SeriesSummary(
                cumulative_return=cumulative_cell,
                mean_period_return=mean_cell,
                volatility=volatility_cell,
                annualized_sharpe=zero_var,
                mean_t_stat=zero_var,
                hit_rate=hit_rate_cell,
                n_valid_periods=m,
            )
        rf = _parse_decimal(risk_free_per_period, what="risk_free_per_period")
        ppy = _parse_decimal(periods_per_year, what="periods_per_year")
        sharpe = ((mean - rf) / volatility) * ppy.sqrt(context)
        std_error = volatility / Decimal(m).sqrt(context)
        t_stat = mean / std_error
        return SeriesSummary(
            cumulative_return=cumulative_cell,
            mean_period_return=mean_cell,
            volatility=volatility_cell,
            annualized_sharpe=StatValue.known(str(+sharpe)),
            mean_t_stat=StatValue.known(str(+t_stat)),
            hit_rate=hit_rate_cell,
            n_valid_periods=m,
        )
