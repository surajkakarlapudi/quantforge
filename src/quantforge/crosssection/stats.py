"""Pure, deterministic per-date cross-sectional OLS + Fama-MacBeth aggregation (§6).

Everything Phase 18 estimates, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context - no numpy, no float, no wall-clock, no RNG (Principle 10). The inputs
are the eligible per-member signal columns and forward-return vector the engine paired
at each date, plus the aggregated per-date coefficient series. Every statistic is a pure
function of those, so identical inputs reproduce identical strings on any machine.

This module reads no store and holds no state; the engine resolves and pairs the inputs
and hands their vectors here. A statistic that is genuinely undefined for the data (a
singular per-date design, a zero-variance regressand, a premium with no or a single
valid date, a premium with zero cross-date dispersion) is returned as a first-class
UNDEFINED :class:`~quantforge.crosssection.model.StatValue` with a reason - **never** a
divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, a dropped factor, or a silent
omission (§9, XS-4).

**Pinned formula methods** (folded into ``crosssection-stats/1``; changing one bumps
:class:`~quantforge.crosssection.version.CrossSectionEngineVersion`):

* **Per-date design matrix** ``X = [1? | x₁ | ... | x_K]`` (an optional intercept column
  plus ``K`` raw signal columns - no standardization, AG-4), ``n`` member rows.
* **Ordinary least squares** (AG-3) solves the normal equations ``(XᵀX)β = Xᵀy`` via an
  exact ``Decimal`` LDLᵀ (Cholesky-family) factorization with an **exact zero-pivot
  test**: a non-positive pivot means ``XᵀX`` is not positive-definite (collinear /
  degenerate signals across that date's members) and the whole per-date coefficient
  block (and its R²) is ``SINGULAR_DESIGN`` - never a fabricated coefficient (§9, XS-4).
* **Per-date R²** ``= 1 - SSR/SST`` where ``SST = Σ(yᵢ - ȳ)²`` and ``SSR = Σeᵢ²``; a
  zero ``SST`` (a constant regressand) is ``ZERO_VARIANCE`` - the coefficients remain
  KNOWN.
* **Fama-MacBeth aggregation** (AG-2): writing ``g_k,T`` for the coefficient's per-date
  value, the premium is the time-series mean ``mean_k = (1/M) Σ_T g_k,T`` over the ``M``
  valid dates; its standard error is the plain (iid) ``se_k = popStd(g_k,.)/sqrt(M)``
  where ``popStd`` is the **population** standard deviation over the valid dates; its
  t-statistic is ``mean_k / se_k``. ``M = 0`` is ``NO_VALID_DATES``; ``M = 1`` leaves
  the mean KNOWN but the dispersion cells ``SINGLE_VALID_DATE``; a zero population
  dispersion leaves the t-statistic ``ZERO_COEFFICIENT_VARIANCE`` (the standard error is
  a KNOWN ``0``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge._linalg import ldl as _ldl
from quantforge._linalg import ldl_solve as _ldl_solve
from quantforge.crosssection.errors import CrossSectionConsistencyError
from quantforge.crosssection.model import (
    INTERCEPT_LABEL,
    CrossSectionUndefinedReason,
    StatValue,
    factor_label,
)

__all__ = [
    "PerDateEstimate",
    "coefficient_labels",
    "cross_section_ols",
    "premium_estimate",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class PerDateEstimate:
    """One date's computed coefficient block + R² + whether the design was singular.

    ``coefficients`` is the ordered ``(label, StatValue)`` block (intercept first when
    the model includes one, then one cell per factor in request order). ``r_squared`` is
    the per-date coefficient of determination. ``singular`` is ``True`` iff ``XᵀX`` was
    not positive-definite - in which case every coefficient cell and ``r_squared`` are
    ``SINGULAR_DESIGN`` and the date contributes **no** coefficient to the premia.
    """

    coefficients: tuple[tuple[str, StatValue], ...]
    r_squared: StatValue
    singular: bool


def coefficient_labels(k: int, *, include_intercept: bool) -> tuple[str, ...]:
    """The ordered coefficient labels: ``alpha?`` then ``factor_1..factor_K``."""
    labels = [factor_label(i) for i in range(k)]
    if include_intercept:
        return (INTERCEPT_LABEL, *labels)
    return tuple(labels)


def _parse_column(values: list[str], *, what: str, context: Context) -> list[Decimal]:
    """Parse a member vector into finite :class:`~decimal.Decimal`s (fail closed).

    Each element must be a finite decimal string (the panel / forward-return machinery
    sealed them via ``str(+Decimal(...))``); a non-decimal or non-finite element is a
    corrupt input and raises :class:`CrossSectionConsistencyError` rather than being
    guessed (XS-4's fail-closed posture for a corrupt corpus value).
    """
    parsed: list[Decimal] = []
    for raw in values:
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError) as exc:
            raise CrossSectionConsistencyError(
                f"{what} {raw!r} is not a valid decimal string"
            ) from exc
        if not value.is_finite():
            raise CrossSectionConsistencyError(f"{what} {raw!r} must be finite")
        parsed.append(+value)
    return parsed


def cross_section_ols(
    signal_columns: list[list[str]],
    returns: list[str],
    *,
    include_intercept: bool,
    context: Context,
) -> PerDateEstimate:
    """Regress one date's forward returns on ``K`` raw signals across members (§6).

    ``signal_columns`` is the list of ``K`` equal-length signal vectors (one per factor,
    in request order) and ``returns`` the equal-length forward-return vector; every
    entry is a member's value in the same member order. Returns a
    :class:`PerDateEstimate` whose coefficient / R² cells are KNOWN or UNDEFINED
    :class:`StatValue`\\ s. A singular design yields an all-``SINGULAR_DESIGN`` block; a
    zero-variance regressand yields ``ZERO_VARIANCE`` R² (the coefficients stay KNOWN) -
    never a divide-by-zero (XS-4). The engine guarantees the degrees-of-freedom floor
    before calling (``n >= p + 1``).
    """
    with localcontext(context):
        y = _parse_column(returns, what="forward return", context=context)
        columns = [
            _parse_column(col, what="signal", context=context) for col in signal_columns
        ]
        n = len(y)
        k = len(columns)
        p = k + (1 if include_intercept else 0)
        labels = coefficient_labels(k, include_intercept=include_intercept)

        def design_row(i: int) -> list[Decimal]:
            row = [columns[c][i] for c in range(k)]
            if include_intercept:
                return [_ONE, *row]
            return row

        # Normal equations A = XᵀX (pxp), rhs = Xᵀy (p-vector). Upper triangle filled,
        # then symmetrized.
        a = [[_ZERO] * p for _ in range(p)]
        rhs = [_ZERO] * p
        for i in range(n):
            row = design_row(i)
            for r in range(p):
                rhs[r] += row[r] * y[i]
                for c in range(r, p):
                    a[r][c] += row[r] * row[c]
        for r in range(p):
            for c in range(r):
                a[r][c] = a[c][r]

        factored = _ldl(a)
        if factored is None:
            reason = CrossSectionUndefinedReason.SINGULAR_DESIGN
            coefficients = tuple(
                (label, StatValue.undefined(reason)) for label in labels
            )
            return PerDateEstimate(
                coefficients=coefficients,
                r_squared=StatValue.undefined(reason),
                singular=True,
            )
        lower, diag = factored
        beta = _ldl_solve(lower, diag, rhs)

        coefficients = tuple(
            (label, StatValue.known(str(+beta[c]))) for c, label in enumerate(labels)
        )

        # Residuals e = y - Xβ; SSR = Σeᵢ². Total sum of squares SST = Σ(yᵢ - ȳ)².
        ssr = _ZERO
        for i in range(n):
            row = design_row(i)
            fitted = sum((row[c] * beta[c] for c in range(p)), _ZERO)
            residual = y[i] - fitted
            ssr += residual * residual
        mean_y = sum(y, _ZERO) / Decimal(n)
        sst = sum(((v - mean_y) * (v - mean_y) for v in y), _ZERO)
        if sst == _ZERO:
            r_squared = StatValue.undefined(CrossSectionUndefinedReason.ZERO_VARIANCE)
        else:
            r_squared = StatValue.known(str(+(_ONE - ssr / sst)))

        return PerDateEstimate(
            coefficients=coefficients, r_squared=r_squared, singular=False
        )


def premium_estimate(
    label: str,
    coefficient_values: list[str],
    *,
    context: Context,
) -> tuple[StatValue, StatValue, StatValue, int]:
    """Aggregate a coefficient's per-date series into a Fama-MacBeth premium (§6).

    ``coefficient_values`` is the ordered list of the coefficient's **KNOWN** per-date
    decimal strings over the valid dates (singular dates contribute nothing). Returns
    ``(mean, std_error, t_stat, n_valid_dates)``:

    * ``M = 0`` -> all three ``NO_VALID_DATES`` (there is no series to aggregate);
    * ``M = 1`` -> ``mean`` KNOWN, ``std_error`` / ``t_stat`` ``SINGLE_VALID_DATE``;
    * ``M >= 2`` -> ``mean`` KNOWN, ``std_error`` the plain FM ``popStd/√M``
      (KNOWN); ``t_stat`` KNOWN unless the population dispersion is exactly zero, in
      which case it is ``ZERO_COEFFICIENT_VARIANCE`` (never a divide-by-zero).
    """
    m = len(coefficient_values)
    if m == 0:
        reason = CrossSectionUndefinedReason.NO_VALID_DATES
        undef = StatValue.undefined(reason)
        return undef, undef, undef, 0
    with localcontext(context):
        values = [
            +Decimal(v) for v in coefficient_values
        ]  # already-canonical KNOWN strings
        mean = sum(values, _ZERO) / Decimal(m)
        mean_cell = StatValue.known(str(+mean))
        if m == 1:
            single = StatValue.undefined(CrossSectionUndefinedReason.SINGLE_VALID_DATE)
            return mean_cell, single, single, 1
        variance = sum(((v - mean) * (v - mean) for v in values), _ZERO) / Decimal(m)
        pop_std = variance.sqrt(context)
        std_error = pop_std / Decimal(m).sqrt(context)
        std_error_cell = StatValue.known(str(+std_error))
        if std_error == _ZERO:
            t_stat_cell = StatValue.undefined(
                CrossSectionUndefinedReason.ZERO_COEFFICIENT_VARIANCE
            )
        else:
            t_stat_cell = StatValue.known(str(+(mean / std_error)))
        return mean_cell, std_error_cell, t_stat_cell, m
