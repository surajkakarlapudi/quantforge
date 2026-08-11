"""Pure, deterministic global minimum-variance solve over a covariance matrix (§11).

Everything Phase 21 computes, in stdlib :class:`~decimal.Decimal` under the engine's
pinned context - no numpy, no float, no wall-clock, no RNG, and **no iteration** (the
closed form is a single exact solve). The input is the full symmetric ``N x N`` factor
covariance matrix ``Σ`` the engine reconstructed from the sealed
:class:`~quantforge.factorrisk.result.FactorRiskModel` (an ordered list of ``N`` rows,
each ``N`` already-canonical decimal strings). The output is the fully-invested GMV
factor-weight vector, the achieved per-period portfolio variance, and its volatility.

This module reads no store and holds no state; the engine resolves, verifies, and
reconstructs ``Σ`` and hands it here. A problem that is genuinely undefined for the data
(a non-positive-definite ``Σ``, so ``Σ⁻¹1`` does not exist) is returned as a first-class
UNDEFINED :class:`~quantforge.optimization.model.MinVarianceSolution` with the
``SINGULAR_COVARIANCE`` reason - **never** a divide-by-zero, a fabricated ``0``, a
``NaN`` / ``Inf``, a repaired / regularized / pseudo-inverted matrix, or a silent
omission (§15, PO-4).

**Pinned solution method** (folded into ``optimization-solve/1``; changing it bumps
:class:`~quantforge.optimization.version.PortfolioOptimizationEngineVersion`):

* **Factorize** ``Σ = L·D·Lᵀ`` via the shared exact-``Decimal`` LDLᵀ routine
  (:func:`quantforge._linalg.ldl`). Its exact zero-pivot test (a non-positive pivot)
  *is* the positive-definiteness / singularity test - no float tolerance. A ``None``
  return is ``SINGULAR_COVARIANCE``.
* **Solve** ``Σ x = 1`` (the all-ones vector) via :func:`quantforge._linalg.ldl_solve`;
  ``x = Σ⁻¹1``.
* **Normalize** ``s = Σ xᵢ = 1ᵀΣ⁻¹1`` (strictly positive for a positive-definite ``Σ``;
  a non-positive ``s`` is treated, defensively, as ``SINGULAR_COVARIANCE`` so the
  fully-invested weight ``w = x/s`` is never a divide-by-zero), then
  ``wᵢ = xᵢ / s`` - the closed-form GMV weights, summing to exactly one.
* **Variance** ``wᵀΣw`` as an inline quadratic form over the reconstructed ``Σ`` (a
  double loop of exact-``Decimal`` multiply-adds; algebraically equal to ``1/s``, so the
  computation self-verifies), and **volatility** ``√(wᵀΣw)`` via ``Decimal.sqrt`` under
  the pinned context. A negative quadratic form (unreachable for a positive-definite
  ``Σ``) is treated, defensively, as ``SINGULAR_COVARIANCE`` rather than a domain error.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext

from quantforge._linalg import ldl, ldl_solve
from quantforge.optimization.errors import PortfolioOptimizationConsistencyError
from quantforge.optimization.model import (
    OptimizationStatus,
    OptimizationUndefinedReason,
    StatValue,
)

__all__ = [
    "MinVarianceSolution",
    "solve_min_variance",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _parse_decimal(raw: str, *, what: str) -> Decimal:
    """Parse one finite :class:`~decimal.Decimal` (fail closed).

    The referenced risk model sealed every covariance cell via ``str(+Decimal(...))``; a
    non-decimal or non-finite element is a corrupt sealed value and raises
    :class:`PortfolioOptimizationConsistencyError` rather than being guessed (the
    fail-closed posture for a corrupt input cell, PO-3).
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise PortfolioOptimizationConsistencyError(
            f"{what} {raw!r} is not a valid decimal string"
        ) from exc
    if not value.is_finite():
        raise PortfolioOptimizationConsistencyError(f"{what} {raw!r} must be finite")
    return +value


@dataclass(frozen=True, slots=True)
class MinVarianceSolution:
    """The computed GMV weight vector + achieved variance/volatility (§11, §14).

    ``status`` is ``OPTIMAL`` when ``Σ`` is positive-definite and the closed-form
    weights exist, else ``UNDEFINED``. ``weights`` are the per-factor GMV weights in
    factor order (each a KNOWN decimal string when ``OPTIMAL``, or an UNDEFINED
    ``SINGULAR_COVARIANCE`` cell - the whole vector together, never a partial answer).
    ``variance`` is the achieved per-period ``wᵀΣw`` and ``volatility`` its square
    root (both KNOWN iff ``OPTIMAL``). Every value is a first-class
    :class:`StatValue`.
    """

    status: OptimizationStatus
    weights: tuple[StatValue, ...]
    variance: StatValue
    volatility: StatValue

    @classmethod
    def optimal(
        cls, *, weights: tuple[str, ...], variance: str, volatility: str
    ) -> MinVarianceSolution:
        """An ``OPTIMAL`` solution from canonical decimal strings."""
        return cls(
            status=OptimizationStatus.OPTIMAL,
            weights=tuple(StatValue.known(w) for w in weights),
            variance=StatValue.known(variance),
            volatility=StatValue.known(volatility),
        )

    @classmethod
    def singular(cls, n: int) -> MinVarianceSolution:
        """An ``UNDEFINED`` ``SINGULAR_COVARIANCE`` solution over ``n`` factors.

        Every weight is UNDEFINED together, and the variance / volatility are
        UNDEFINED - the honest recording of a covariance matrix whose GMV does not
        exist. Never a divide-by-zero, never a repaired matrix (PO-4).
        """
        reason = OptimizationUndefinedReason.SINGULAR_COVARIANCE
        return cls(
            status=OptimizationStatus.UNDEFINED,
            weights=tuple(StatValue.undefined(reason) for _ in range(n)),
            variance=StatValue.undefined(reason),
            volatility=StatValue.undefined(reason),
        )


def solve_min_variance(
    covariance: list[list[str]], *, context: Context
) -> MinVarianceSolution:
    """Solve the fully-invested GMV over ``covariance`` (§11).

    ``covariance`` is the full symmetric ``N x N`` matrix ``Σ`` (``N >= 1``), each entry
    an already-canonical decimal string; the engine reconstructs it from the sealed
    upper-triangle covariance cells. A ragged (non-square) matrix is a caller bug and
    raises. Every arithmetic step runs under the pinned ``context`` (no float, no RNG,
    no wall-clock, no iteration), so identical inputs reproduce identical strings on any
    machine.

    Returns a :class:`MinVarianceSolution`: ``OPTIMAL`` with the closed-form weights,
    achieved per-period variance ``wᵀΣw``, and volatility when ``Σ`` is
    positive-definite; otherwise ``UNDEFINED`` ``SINGULAR_COVARIANCE`` (never a
    divide-by-zero, never a repaired matrix).
    """
    n = len(covariance)
    if n < 1:
        raise PortfolioOptimizationConsistencyError(
            "solve_min_variance needs at least one factor"
        )
    for row in covariance:
        if len(row) != n:
            raise PortfolioOptimizationConsistencyError(
                f"the covariance matrix must be square ({n}x{n}); a ragged row breaks "
                "the solve (fail closed)"
            )

    with localcontext(context):
        sigma = [
            [_parse_decimal(covariance[i][j], what="covariance") for j in range(n)]
            for i in range(n)
        ]

        # Factorize + the exact zero-pivot positive-definiteness test. A non-PD Σ has no
        # inverse, so the fully-invested GMV is genuinely undefined (PO-4).
        factored = ldl(sigma)
        if factored is None:
            return MinVarianceSolution.singular(n)
        lower, diag = factored

        # x = Σ⁻¹1; s = 1ᵀΣ⁻¹1 (strictly positive for a PD Σ). The non-positive guard is
        # defensive - it can only fire on a matrix the PD test should already have
        # rejected - and keeps w = x/s from ever dividing by zero.
        ones = [_ONE] * n
        x = ldl_solve(lower, diag, ones)
        s = sum(x, _ZERO)
        if s <= _ZERO:
            return MinVarianceSolution.singular(n)

        weights = [xi / s for xi in x]

        # Achieved per-period variance wᵀΣw, computed inline (algebraically 1/s, so this
        # self-verifies the closed form). A negative quadratic form is unreachable for a
        # PD Σ; guarded defensively so √ never hits a domain error.
        variance = _ZERO
        for i in range(n):
            sigma_row = sigma[i]
            w_i = weights[i]
            for j in range(n):
                variance += w_i * sigma_row[j] * weights[j]
        if variance < _ZERO:
            return MinVarianceSolution.singular(n)

        volatility = variance.sqrt(context)

        return MinVarianceSolution.optimal(
            weights=tuple(str(+w) for w in weights),
            variance=str(+variance),
            volatility=str(+volatility),
        )
