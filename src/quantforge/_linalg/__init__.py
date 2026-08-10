"""Shared internal exact-``Decimal`` linear-algebra primitives (no float, no numpy).

A single, dependency-free home for the exact-``Decimal`` LDLᵀ (Cholesky-family)
factorization and its solves, promoted so the multi-factor time-series regression
(:mod:`quantforge.attribution`) and the cross-sectional Fama-MacBeth regression
(:mod:`quantforge.crosssection`) share **one** verified solver rather than each
carrying a copy. The primitives are pure functions of their :class:`~decimal.Decimal`
inputs and hold no state; callers run them inside their own pinned ``localcontext``
so the arithmetic (and therefore every canonical string) is identical on any machine.

This is an internal helper (leading underscore): it is not part of the public API and
is reached only through the phases that compose it.
"""

from __future__ import annotations

from quantforge._linalg.decimal_ols import inverse_diagonal, ldl, ldl_solve

__all__ = ["inverse_diagonal", "ldl", "ldl_solve"]
