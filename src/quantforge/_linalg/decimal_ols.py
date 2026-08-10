"""Exact-``Decimal`` LDLᵀ factorization and solves for the normal equations.

The exact linear algebra behind ordinary least squares: solving ``(XᵀX)β = Xᵀy`` via
an exact ``Decimal`` LDLᵀ (Cholesky-family) factorization with an **exact zero-pivot
test** — a non-positive pivot means ``XᵀX`` is not positive-definite (a collinear /
rank-deficient design) and yields ``None`` so the caller records a first-class
``SINGULAR_DESIGN`` result rather than fabricating a coefficient. No float tolerance
enters the test; the pivot is an exact ``Decimal``.

These functions are pure (no store, no state, no wall-clock, no RNG) and expect to run
inside a caller-supplied :func:`~decimal.localcontext` — they were promoted verbatim
from the Phase 17 attribution solver so both regression layers share one implementation
with byte-identical output (Principle 10).
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["inverse_diagonal", "ldl", "ldl_solve"]

_ZERO = Decimal(0)
_ONE = Decimal(1)


def ldl(a: list[list[Decimal]]) -> tuple[list[list[Decimal]], list[Decimal]] | None:
    """LDLᵀ factorization of a symmetric matrix; ``None`` if not positive-definite.

    Returns unit-lower-triangular ``L`` and the diagonal ``D`` such that ``A = L·D·Lᵀ``.
    A pivot ``D[j] <= 0`` means ``A`` is not positive-definite (rank-deficient /
    collinear design) — the exact zero-pivot test — and yields ``None`` so the caller
    records ``SINGULAR_DESIGN`` rather than fabricating a coefficient. No float
    tolerance enters the test; the pivot is an exact ``Decimal``.
    """
    p = len(a)
    lower = [[_ZERO] * p for _ in range(p)]
    diag = [_ZERO] * p
    for j in range(p):
        pivot = a[j][j] - sum((lower[j][k] ** 2) * diag[k] for k in range(j))
        if pivot <= _ZERO:
            return None
        diag[j] = pivot
        lower[j][j] = _ONE
        for i in range(j + 1, p):
            off = a[i][j] - sum(lower[i][k] * lower[j][k] * diag[k] for k in range(j))
            lower[i][j] = off / pivot
    return lower, diag


def ldl_solve(
    lower: list[list[Decimal]], diag: list[Decimal], b: list[Decimal]
) -> list[Decimal]:
    """Solve ``A·x = b`` given the ``A = L·D·Lᵀ`` factorization (forward/diag/back)."""
    p = len(diag)
    # Forward: L z = b (L unit lower triangular).
    z = [_ZERO] * p
    for i in range(p):
        z[i] = b[i] - sum(lower[i][k] * z[k] for k in range(i))
    # Diagonal: D w = z.
    w = [z[i] / diag[i] for i in range(p)]
    # Back: Lᵀ x = w (Lᵀ unit upper triangular).
    x = [_ZERO] * p
    for i in range(p - 1, -1, -1):
        x[i] = w[i] - sum(lower[k][i] * x[k] for k in range(i + 1, p))
    return x


def inverse_diagonal(lower: list[list[Decimal]], diag: list[Decimal]) -> list[Decimal]:
    """The diagonal of ``A⁻¹`` from the factorization (one solve per unit vector).

    Only the diagonal is needed — the coefficient standard errors are
    ``√(sigma_sq·(A⁻¹)ᵢᵢ)`` — so column ``j`` of ``A⁻¹`` is obtained by solving ``A·z =
    eⱼ`` and its ``j``-th entry taken.
    """
    p = len(diag)
    out: list[Decimal] = []
    for j in range(p):
        unit = [_ZERO] * p
        unit[j] = _ONE
        column = ldl_solve(lower, diag, unit)
        out.append(column[j])
    return out
