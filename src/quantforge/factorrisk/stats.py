"""Pure, deterministic second-moment estimation over aligned factor return series (§12).

Everything Phase 20 computes, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context - no numpy, no float, no wall-clock, no RNG (Principle 10). The input is
the complete-case-aligned matrix the engine built: an ordered list of *N* factor
return series, each a list of the **same** ``M`` already-canonical decimal strings (the
factor's
KNOWN per-period returns on the common estimation window, in shared date order). Every
statistic is a pure function of that matrix, so identical inputs reproduce identical
strings on any machine.

This module reads no store and holds no state; the engine resolves, verifies, and aligns
the inputs and hands their aligned vectors here. A statistic that is genuinely
undefined for the data (a correlation cell whose factor has zero volatility over the
common window)
is returned as a first-class UNDEFINED
:class:`~quantforge.factorrisk.model.StatValue` with the ``ZERO_VARIANCE`` reason -
**never** a divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, or a silent omission
(§12, FR-4).

**Pinned formula methods** (folded into ``factorrisk-stats/1``; changing one bumps
:class:`~quantforge.factorrisk.version.FactorRiskEngineVersion`):

* **Per-factor mean** ``mean_i = (1/M) Σ_t f_{i,t}``.
* **Per-factor population volatility** ``vol_i = √( (1/M) Σ_t (f_{i,t}-mean_i)² )`` (via
  ``Decimal.sqrt`` under the pinned context - the Phase 12/19 precedent). Population
  (÷M), not sample (÷M-1): a covariance/correlation matrix is internally consistent only
  when every second moment uses the same divisor, and the population divisor makes the
  correlation of a factor with itself exactly ``1`` (approved decision, §11). The
  volatility is KNOWN even at exactly ``0``.
* **Population covariance** ``cov(i,j) = (1/M) Σ_t (f_{i,t}-mean_i)(f_{j,t}-mean_j)``,
  symmetric, so only the upper triangle (``i <= j``) is computed; the diagonal
  ``cov(i,i)`` is the factor's own population variance (``vol_i²``, recomputed from the
  sum of squares - not squared back from the rounded volatility).
* **Correlation** ``corr(i,j) = cov(i,j) / (vol_i · vol_j)``. When either ``vol_i`` or
  ``vol_j`` is exactly ``0`` the denominator is zero and the correlation is UNDEFINED
  ``ZERO_VARIANCE`` (never a divide-by-zero); otherwise it is KNOWN, and the diagonal
  ``corr(i,i)`` of a positive-variance factor is exactly ``1`` (``cov(i,i)`` and
  ``vol_i²`` are the identical sum-of-squares expression under the pinned context).
* **Annualization** ``annualized_vol_i = vol_i · √periods_per_year`` and
  ``annualized_cov(i,j) = cov(i,j) · periods_per_year`` (variances/covariances scale
  linearly in time, volatilities by the square root - the Phase 12/19 convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge.factorrisk.errors import FactorRiskConsistencyError
from quantforge.factorrisk.model import (
    CorrelationCell,
    CovarianceCell,
    FactorMoment,
    FactorRiskUndefinedReason,
    StatValue,
    factor_label,
)

__all__ = [
    "MomentEstimate",
    "estimate_moments",
]

_ZERO = Decimal(0)


def _parse_decimal(raw: str, *, what: str) -> Decimal:
    """Parse one finite :class:`~decimal.Decimal` (fail closed).

    The referenced factor portfolios sealed every KNOWN factor return via
    ``str(+Decimal(...))``; a non-decimal or non-finite element is a corrupt sealed
    value and raises :class:`FactorRiskConsistencyError` rather than being guessed
    (FR-4's
    fail-closed posture for a corrupt input cell).
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise FactorRiskConsistencyError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise FactorRiskConsistencyError(f"{what} {raw!r} must be finite")
    return +value


@dataclass(frozen=True, slots=True)
class MomentEstimate:
    """The computed second-moment structure over the aligned window (§9, §12).

    ``factors`` the ordered per-factor moment records (mean, population volatility,
    annualized volatility); ``covariance`` the upper-triangle (``i <= j``) covariance
    cells (per-period + annualized); ``correlation`` the upper-triangle correlation
    cells.
    Every collection is in canonical stored order, ready to fold into the sealed record.
    """

    factors: tuple[FactorMoment, ...]
    covariance: tuple[CovarianceCell, ...]
    correlation: tuple[CorrelationCell, ...]


def estimate_moments(
    series: list[list[str]],
    *,
    periods_per_year: str,
    context: Context,
) -> MomentEstimate:
    """Estimate the factor means, (co)variances, and correlations (§12).

    ``series`` is the complete-case-aligned matrix: ``series[i]`` is factor ``i``'s
    KNOWN per-period returns over the common estimation window (already-canonical
    decimal
    strings), in shared date order. Every row must have the same length ``M >= 2`` (the
    engine guarantees this; a shorter or ragged matrix is a caller bug and raises).
    ``periods_per_year`` is the canonical annualization convention.

    Returns a :class:`MomentEstimate` whose factor moments and matrix cells are all
    under the pinned context. Volatilities are KNOWN even at exactly ``0``; a
    correlation whose
    factor has zero volatility is UNDEFINED ``ZERO_VARIANCE`` (never a divide-by-zero).
    """
    n = len(series)
    if n < 2:
        raise FactorRiskConsistencyError(
            "estimate_moments needs at least two factor series"
        )
    m = len(series[0])
    if m < 2:
        raise FactorRiskConsistencyError(
            "estimate_moments needs a common window of at least two periods"
        )
    for row in series:
        if len(row) != m:
            raise FactorRiskConsistencyError(
                "every aligned factor series must have the same length"
            )

    with localcontext(context):
        # Parse once; the deviation vectors and their pairwise products drive every
        # moment. Population divisor Decimal(m) is shared across all second moments.
        parsed = [
            [_parse_decimal(v, what="factor return") for v in row] for row in series
        ]
        divisor = Decimal(m)
        means = [sum(row, _ZERO) / divisor for row in parsed]
        deviations = [[value - means[i] for value in parsed[i]] for i in range(n)]
        ppy = _parse_decimal(periods_per_year, what="periods_per_year")
        sqrt_ppy = ppy.sqrt(context)

        # Population variances (÷M) drive both the volatilities and the correlation
        # denominators; compute them once from the sum of squared deviations.
        variances = [
            sum((d * d for d in deviations[i]), _ZERO) / divisor for i in range(n)
        ]
        volatilities = [variances[i].sqrt(context) for i in range(n)]

        factors = tuple(
            FactorMoment(
                label=factor_label(i),
                mean=StatValue.known(str(+means[i])),
                volatility=StatValue.known(str(+volatilities[i])),
                annualized_volatility=StatValue.known(
                    str(+(volatilities[i] * sqrt_ppy))
                ),
            )
            for i in range(n)
        )

        covariance: list[CovarianceCell] = []
        correlation: list[CorrelationCell] = []
        for i in range(n):
            for j in range(i, n):
                cov = (
                    sum(
                        (deviations[i][t] * deviations[j][t] for t in range(m)),
                        _ZERO,
                    )
                    / divisor
                )
                covariance.append(
                    CovarianceCell(
                        i=i,
                        j=j,
                        value=StatValue.known(str(+cov)),
                        annualized=StatValue.known(str(+(cov * ppy))),
                    )
                )
                if volatilities[i] == _ZERO or volatilities[j] == _ZERO:
                    corr_cell = StatValue.undefined(
                        FactorRiskUndefinedReason.ZERO_VARIANCE
                    )
                else:
                    corr = cov / (volatilities[i] * volatilities[j])
                    corr_cell = StatValue.known(str(+corr))
                correlation.append(CorrelationCell(i=i, j=j, value=corr_cell))

    return MomentEstimate(
        factors=factors,
        covariance=tuple(covariance),
        correlation=tuple(correlation),
    )
