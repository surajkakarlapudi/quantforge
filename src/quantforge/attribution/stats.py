"""Pure, deterministic multi-factor OLS over sealed return vectors (§6, §11, §18).

Everything Phase 17 estimates, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context — no numpy, no float, no wall-clock, no RNG (Principle 10; §8). The
inputs are the sealed ``period_returns`` decimal strings of a subject
:class:`~quantforge.backtest.result.BacktestResult` and of each of *K* factor backtests,
plus the recorded annualization convention. Every statistic is a pure function of those,
so identical inputs reproduce identical strings on any machine (§8).

This module reads no store and holds no state; the engine resolves and verifies the
sealed inputs and hands their vectors here. A statistic that is genuinely undefined for
the data (a singular design, a zero-variance regressand, a perfect fit) is returned as a
first-class UNDEFINED :class:`~quantforge.attribution.model.StatValue` with a reason —
**never** a divide-by-zero, a fabricated ``0``, a ``NaN``/``Inf``, a dropped factor, or
a silent omission (§11, FA-4).

**Pinned formula methods** (folded into ``attribution-stats/1``; changing one bumps
:class:`~quantforge.attribution.version.AttributionEngineVersion`):

* **Excess-on-excess** (approved open-question 1): the regressand is ``y = subject -
rf``
  and each regressor column is ``xₖ - rf`` (the risk-free per-period rate subtracted
  from
  *both* the subject and every factor), so the intercept is the subject's excess-return
  alpha net of the factors' excess exposures.
* **Design matrix** ``X = [1 | x₁-rf | … | x_K-rf]`` (an intercept column plus *K*
factor
  excess-return columns), ``n`` rows.
* **Ordinary least squares** solves the normal equations ``(XᵀX)β = Xᵀy`` via an exact
  ``Decimal`` LDLᵀ (Cholesky-family) factorization with an **exact zero-pivot test**: a
  non-positive pivot means ``XᵀX`` is not positive-definite (collinear/degenerate
  factors) and the whole coefficient block is ``SINGULAR_DESIGN`` — never a fabricated
  coefficient (§18, FA-4).
* **R²** ``= 1 - SSR/SST`` where ``SST = Σ(yᵢ - ȳ)²`` and ``SSR = Σeᵢ²``; **adjusted
R²**
  ``= 1 - (1 - R²)·(n - 1)/(n - K - 1)`` (guarding ``n - K - 1 > 0``, engine-enforced).
* **Residual variance** ``sigma_sq = SSR/(n - K - 1)``; **residual standard error** ``=
√sigma_sq``.
* **Coefficient covariance** ``sigma_sq·(XᵀX)⁻¹``; each coefficient's **standard error**
is the
  square root of its diagonal entry and its **t-statistic** is ``estimate / std_error``.
* **Sample return decomposition**: the intercept contributes ``alpha`` and factor ``k``
  contributes ``βₖ · mean(xₖ - rf)`` to the subject's mean excess return (they sum to
  it,
  since the OLS residual mean is zero under an intercept).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge._linalg import inverse_diagonal as _inverse_diagonal
from quantforge._linalg import ldl as _ldl
from quantforge._linalg import ldl_solve as _ldl_solve
from quantforge.attribution.errors import AttributionConfigurationError
from quantforge.attribution.model import (
    DIAGNOSTIC_KEYS,
    INTERCEPT_LABEL,
    AttributionUndefinedReason,
    StatValue,
    factor_label,
)

__all__ = [
    "AttributionEstimate",
    "attribute_returns",
    "parse_returns",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)

# A coefficient cell: (label, estimate, std_error, t_stat).
_Coefficient = tuple[str, StatValue, StatValue, StatValue]


@dataclass(frozen=True, slots=True)
class AttributionEstimate:
    """The computed OLS blocks the engine seals into a record (§6).

    ``coefficients`` is the ordered ``(label, estimate, std_error, t_stat)`` block — the
    intercept (``alpha``) first, then one cell per factor in request order.
    ``diagnostics`` is the closed :data:`~quantforge.attribution.model.DIAGNOSTIC_KEYS`
    set sorted by key. ``decomposition`` is the ordered ``(label, StatValue)``
    mean-excess contribution block (alpha, then per factor). ``residuals`` is the
    ordered canonical residual series — the engine folds only its **digest** into the
    record (D4), never the series itself.
    """

    coefficients: tuple[_Coefficient, ...]
    diagnostics: tuple[tuple[str, StatValue], ...]
    decomposition: tuple[tuple[str, StatValue], ...]
    residuals: tuple[str, ...]


# -- parsing -----------------------------------------------------------------


def parse_returns(
    returns: tuple[str, ...] | list[str], *, context: Context
) -> list[Decimal]:
    """Parse a return vector into finite :class:`~decimal.Decimal`s (fail closed).

    Each element must be a finite decimal string (they are, having been sealed by the
    Phase 12 engine via ``str(+Decimal(...))``); a non-decimal or non-finite element is
    a corrupt input and raises :class:`AttributionConfigurationError` rather than being
    guessed. Parsing runs under the pinned ``context`` so the canonical form matches the
    engine's.
    """
    with localcontext(context):
        parsed: list[Decimal] = []
        for raw in returns:
            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError) as exc:
                raise AttributionConfigurationError(
                    f"period return {raw!r} is not a valid decimal string"
                ) from exc
            if not value.is_finite():
                raise AttributionConfigurationError(
                    f"period return {raw!r} must be finite"
                )
            parsed.append(+value)
        return parsed


# -- exact-Decimal linear algebra --------------------------------------------
# The LDLᵀ factorization / solves live in the shared internal helper
# ``quantforge._linalg`` (imported above as ``_ldl`` / ``_ldl_solve`` /
# ``_inverse_diagonal``) so this layer and the cross-sectional regression share one
# verified, byte-identical solver. They run inside the ``localcontext`` opened below.


def _known(value: Decimal) -> StatValue:
    """A KNOWN cell holding the canonical string form of ``value`` (under context)."""
    return StatValue.known(str(+value))


def _undef(reason: AttributionUndefinedReason) -> StatValue:
    return StatValue.undefined(reason)


# -- the multi-factor OLS regression -----------------------------------------


def attribute_returns(
    subject: tuple[str, ...] | list[str],
    factors: list[tuple[str, ...]] | list[list[str]],
    *,
    risk_free_per_period: str,
    periods_per_year: str,
    context: Context,
) -> AttributionEstimate:
    """Regress the subject's excess return on *K* factor excess returns (§6, §11).

    ``subject`` and each element of ``factors`` are equal-length sealed
    ``period_returns`` vectors (the engine verifies commensurability first). Returns an
    :class:`AttributionEstimate` whose coefficient / diagnostic / decomposition cells
    are each a KNOWN or UNDEFINED :class:`~quantforge.attribution.model.StatValue`. A
    singular design yields an all-``SINGULAR_DESIGN`` block; a zero-variance regressand
    yields ``ZERO_VARIANCE`` R²; a perfect fit yields ``ZERO_RESIDUAL_VARIANCE``
    standard errors / t-statistics — never a divide-by-zero (FA-4). ``periods_per_year``
    is recorded on the sealed record and folded into its identity; the v1 diagnostics
    are reported per period (annualization of the intercept is out of scope for v1 — the
    convention is retained for provenance and future use).
    """
    with localcontext(context):
        y_raw = parse_returns(subject, context=context)
        columns = [parse_returns(f, context=context) for f in factors]
        n = len(y_raw)
        k = len(columns)
        p = k + 1  # intercept + K factor columns

        rf = +Decimal(risk_free_per_period)
        # Excess-on-excess: subtract rf from the subject and from every factor column.
        y = [v - rf for v in y_raw]
        excess_columns = [[v - rf for v in col] for col in columns]

        # Design matrix rows X[i] = [1, x1_i, ..., xK_i]; assembled implicitly below.
        # Normal equations A = XᵀX (pxp), rhs = Xᵀy (p-vector).
        a = [[_ZERO] * p for _ in range(p)]
        rhs = [_ZERO] * p

        def design_row(i: int) -> list[Decimal]:
            return [_ONE, *(excess_columns[c][i] for c in range(k))]

        for i in range(n):
            row = design_row(i)
            for r in range(p):
                rhs[r] += row[r] * y[i]
                for c in range(r, p):
                    a[r][c] += row[r] * row[c]
        # Symmetrize (we only filled the upper triangle).
        for r in range(p):
            for c in range(r):
                a[r][c] = a[c][r]

        factored = _ldl(a)
        if factored is None:
            return _singular_estimate(k)
        lower, diag = factored

        beta = _ldl_solve(lower, diag, rhs)

        # Residuals e = y - Xβ; SSR = Σeᵢ².
        residuals: list[Decimal] = []
        for i in range(n):
            row = design_row(i)
            fitted = sum((row[c] * beta[c] for c in range(p)), _ZERO)
            residuals.append(y[i] - fitted)
        ssr = sum((e * e for e in residuals), _ZERO)

        # Total sum of squares SST = Σ(yᵢ - ȳ)².
        mean_y = sum(y, _ZERO) / Decimal(n)
        sst = sum(((v - mean_y) * (v - mean_y) for v in y), _ZERO)

        residual_df = Decimal(n - p)  # engine guarantees n - p >= 1

        # -- diagnostics ----------------------------------------------------
        diagnostics = _diagnostics(ssr=ssr, sst=sst, n=n, p=p, context=context)

        # -- coefficient standard errors / t-stats -------------------------
        sigma_sq = ssr / residual_df
        coefficients = _coefficients(
            beta=beta,
            sigma_sq=sigma_sq,
            lower=lower,
            diag=diag,
            context=context,
        )

        # -- sample mean-excess decomposition ------------------------------
        decomposition = _decomposition(beta=beta, excess_columns=excess_columns, n=n)

        return AttributionEstimate(
            coefficients=coefficients,
            diagnostics=diagnostics,
            decomposition=decomposition,
            residuals=tuple(str(+e) for e in residuals),
        )


def _diagnostics(
    *, ssr: Decimal, sst: Decimal, n: int, p: int, context: Context
) -> tuple[tuple[str, StatValue], ...]:
    """R², adjusted R², and residual standard error (fail-closed on zero SST)."""
    out: dict[str, StatValue] = {}
    if sst == _ZERO:
        # A constant regressand: explained/total is 0/0 — genuinely undefined.
        out["r_squared"] = _undef(AttributionUndefinedReason.ZERO_VARIANCE)
        out["adjusted_r_squared"] = _undef(AttributionUndefinedReason.ZERO_VARIANCE)
    else:
        r_squared = _ONE - ssr / sst
        out["r_squared"] = _known(r_squared)
        # n - p >= 1 (engine-enforced n >= K + 2), so the adjustment never divides by 0.
        adj = _ONE - (_ONE - r_squared) * Decimal(n - 1) / Decimal(n - p)
        out["adjusted_r_squared"] = _known(adj)
    residual_variance = ssr / Decimal(n - p)
    out["residual_std_error"] = _known(residual_variance.sqrt(context))
    return tuple((key, out[key]) for key in DIAGNOSTIC_KEYS)


def _coefficients(
    *,
    beta: list[Decimal],
    sigma_sq: Decimal,
    lower: list[list[Decimal]],
    diag: list[Decimal],
    context: Context,
) -> tuple[_Coefficient, ...]:
    """The ``(label, estimate, std_error, t_stat)`` block; std errors fail closed at
    fit.

    At a perfect in-sample fit (``sigma_sq == 0``) the coefficient standard errors and
    t-statistics are undefinable (a zero standard error would divide the t-statistic),
    so both cells are ``ZERO_RESIDUAL_VARIANCE`` — the estimate itself is still KNOWN.
    """
    p = len(beta)
    labels = [INTERCEPT_LABEL, *(factor_label(i) for i in range(p - 1))]
    out: list[_Coefficient] = []
    if sigma_sq == _ZERO:
        for c in range(p):
            out.append(
                (
                    labels[c],
                    _known(beta[c]),
                    _undef(AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE),
                    _undef(AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE),
                )
            )
        return tuple(out)
    inv_diag = _inverse_diagonal(lower, diag)
    for c in range(p):
        std_err = (sigma_sq * inv_diag[c]).sqrt(context)
        estimate = _known(beta[c])
        # pragma below: PD ⇒ positive diagonal, so this is guarded but unreachable.
        if std_err == _ZERO:  # pragma: no cover
            out.append(
                (
                    labels[c],
                    estimate,
                    _undef(AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE),
                    _undef(AttributionUndefinedReason.ZERO_RESIDUAL_VARIANCE),
                )
            )
        else:
            out.append(
                (labels[c], estimate, _known(std_err), _known(beta[c] / std_err))
            )
    return tuple(out)


def _decomposition(
    *, beta: list[Decimal], excess_columns: list[list[Decimal]], n: int
) -> tuple[tuple[str, StatValue], ...]:
    """The mean-excess-return contribution block: alpha, then ``βₖ·mean(xₖ-rf)``."""
    out: list[tuple[str, StatValue]] = [(INTERCEPT_LABEL, _known(beta[0]))]
    for i, column in enumerate(excess_columns):
        mean_excess = sum(column, _ZERO) / Decimal(n)
        out.append((factor_label(i), _known(beta[i + 1] * mean_excess)))
    return tuple(out)


def _singular_estimate(k: int) -> AttributionEstimate:
    """An all-``SINGULAR_DESIGN`` estimate: no coefficient/diagnostic/residual
    fabricated.

    Every coefficient (estimate, std error, t-stat), every diagnostic, and every
    decomposition contribution is ``UNDEFINED(SINGULAR_DESIGN)``; the residual series is
    empty (there is no fitted model to residualize against), so its digest is the digest
    of the empty series — deterministic and distinct from any real residual set.
    """
    reason = AttributionUndefinedReason.SINGULAR_DESIGN
    labels = [INTERCEPT_LABEL, *(factor_label(i) for i in range(k))]
    coefficients = tuple(
        (label, _undef(reason), _undef(reason), _undef(reason)) for label in labels
    )
    diagnostics = tuple((key, _undef(reason)) for key in DIAGNOSTIC_KEYS)
    decomposition = tuple((label, _undef(reason)) for label in labels)
    return AttributionEstimate(
        coefficients=coefficients,
        diagnostics=diagnostics,
        decomposition=decomposition,
        residuals=(),
    )
