"""Deterministic exact-``Decimal`` standard-normal CDF Φ and inverse-CDF Z⁻¹.

Several research layers need the standard-normal cumulative distribution function ``Φ``
(the Phase 23 campaign's Probabilistic/Deflated Sharpe Ratios; the Phase 24 comparison's
two-sided paired-difference p-value) and its inverse ``Z⁻¹`` (Phase 23's
expected-maximum-Sharpe threshold). Neither may be taken from ``math`` / ``statistics``
/ numpy: a ``float`` ``erf`` would break the project's exact-``Decimal`` determinism
(Principle 10) - the same input could round differently across platforms or libc
versions, and a sealed id could then drift. So this module computes both in stdlib
:class:`~decimal.Decimal` under an explicit :class:`~decimal.Context`, exactly the way
the risk/optimization layers already lean on ``Decimal.sqrt`` / ``Decimal.exp`` (both
correctly rounded per the General Decimal Arithmetic Specification, hence bit-identical
on every platform).

* :func:`standard_normal_cdf` - ``Φ(x) = ½·(1 + erf(x/√2))``. ``erf`` is summed via its
  **well-conditioned, all-positive-term** series
  ``erf(z) = (2/√π)·e^{-z²}·Σ_{k≥0} 2^k z^{2k+1} / (1·3·5···(2k+1))`` (no catastrophic
  cancellation, unlike the naive alternating Taylor series), under a working context
  carrying :data:`_GUARD_DIGITS` extra digits, then rounded back to the caller's
  context and clamped to ``[0, 1]``.
* :func:`standard_normal_ppf` - ``Z⁻¹(p)`` for ``p ∈ (0, 1)``, by deterministic
  bisection of the monotone :func:`standard_normal_cdf` on a fixed bracket for a fixed
  number of iterations (no data-dependent early exit, so the result is a pure function
  of ``p`` and the context).
* :data:`EULER_MASCHERONI` - the Euler-Mascheroni constant ``gamma`` as a documented
  high-precision literal (the expected-max-Sharpe formula's ``(1-gamma)·Z⁻¹(1-1/N) +
  gamma·Z⁻¹(1-1/(N·e))`` weighting), the deterministic analogue of the pinned decimal
  context: a literal, never a non-terminating series whose truncation could drift.

No wall clock, no RNG, no ``float``, no ``id()``, no iteration-order dependence enters
any value here - the two functions are pure functions of their argument and the passed
context, reproducible on any machine.
"""

from __future__ import annotations

from decimal import Context, Decimal, localcontext

__all__ = [
    "EULER_MASCHERONI",
    "standard_normal_cdf",
    "standard_normal_ppf",
]

#: The Euler-Mascheroni constant ``gamma`` to 50 significant digits - a documented
#: literal, not a truncated series, so it can never drift between runs or platforms.
#: Used only by the expected-maximum-Sharpe weighting; folded (via that computation)
#: into the sealed campaign answer, so its value is pinned by
#: :data:`~quantforge.campaign.version.\
#: CAMPAIGN_NORMAL_VERSION` (bump that tag if this constant ever changes).
EULER_MASCHERONI = Decimal("0.57721566490153286060651209008240243104215933593992")

#: ``π`` to 60 significant digits - a documented literal used only to derive ``√π`` for
#: the ``erf`` normalization. More digits than any working precision this module
#: reaches, so ``√π`` is accurate to the full guarded precision. Also pinned by the
#: normal-method version.
_PI = Decimal("3.14159265358979323846264338327950288419716939937510582097494459230782")

#: Extra precision carried above the caller's context while summing the ``erf`` series
#: and bisecting the inverse, so accumulated rounding never reaches the caller-visible
#: digits; every public result is rounded back to the caller's context at the end.
_GUARD_DIGITS = 12

#: Hard cap on ``erf`` series terms. The positive-term series converges for every
#: argument these layers evaluate (``|z|`` well under 10), far inside this backstop; it
#: exists only so a pathological argument can never spin forever (the fail-closed
#: analogue of the solve layer's structural guards).
_ERF_MAX_TERMS = 10_000

#: Fixed bisection iterations for the inverse CDF. On the bracket
#: ``[-_PPF_BRACKET, +_PPF_BRACKET]`` this halves the interval to below ``10⁻⁶⁰`` - past
#: any guarded working precision these layers use - for every ``p`` they evaluate. A
#: *fixed* count (not a tolerance-based early exit) keeps the inverse fully
#: deterministic.
_PPF_ITERATIONS = 240

#: The symmetric bracket the inverse bisects over. ``Φ(±50)`` rounds to ``1`` / ``0`` at
#: any precision these layers use, so the true quantile of every evaluated ``p`` (all
#: with ``|Z⁻¹(p)| < 10``) is strictly bracketed.
_PPF_BRACKET = Decimal(50)

_ZERO = Decimal(0)
_ONE = Decimal(1)
_TWO = Decimal(2)


def _working(context: Context) -> Context:
    """A copy of ``context`` carrying :data:`_GUARD_DIGITS` extra precision."""
    return Context(prec=context.prec + _GUARD_DIGITS, rounding=context.rounding)


def _erf(z: Decimal, context: Context) -> Decimal:
    """``erf(z)`` via the all-positive-term series (no cancellation), under ``context``.

    ``erf(z) = (2/√π)·e^{-z²}·Σ_{k≥0} 2^k z^{2k+1} / (1·3·5···(2k+1))``. Each term is
    the previous one times ``2·z²/(2k+1)`` (all positive, so no subtractive
    cancellation); the sum runs until a term is negligible relative to the running
    total at the working precision, or the :data:`_ERF_MAX_TERMS` backstop. ``erf`` is
    odd, so a negative argument is handled by symmetry.
    """
    if z == _ZERO:
        return _ZERO
    negative = z < _ZERO
    magnitude = -z if negative else z
    with localcontext(context):
        z_squared = magnitude * magnitude
        term = magnitude  # k = 0: 2⁰·z¹ / 1 = z
        total = term
        tiny = Decimal(10) ** (-(context.prec + 2))
        k = 1
        while k < _ERF_MAX_TERMS:
            term = term * (_TWO * z_squared) / (_TWO * k + _ONE)
            total = total + term
            if term <= total * tiny:
                break
            k += 1
        erf = (_TWO / _PI.sqrt(context)) * (-z_squared).exp(context) * total
    return -erf if negative else erf


def standard_normal_cdf(x: Decimal, *, context: Context) -> Decimal:
    """The standard-normal CDF ``Φ(x) = ½·(1 + erf(x/√2))`` (deterministic, exact).

    Computed under a guarded working context and rounded back to ``context``; the result
    is clamped to ``[0, 1]`` so a final-digit rounding can never emit a probability just
    outside the unit interval. A pure function of ``x`` and ``context`` - identical
    inputs yield identical strings on any machine.
    """
    working = _working(context)
    with localcontext(working):
        cdf = (_ONE + _erf(x / _TWO.sqrt(working), working)) / _TWO
    with localcontext(context):
        result = +cdf
    if result < _ZERO:
        return _ZERO
    if result > _ONE:
        return _ONE
    return result


def standard_normal_ppf(p: Decimal, *, context: Context) -> Decimal:
    """The standard-normal quantile ``Z⁻¹(p)`` for ``p ∈ (0, 1)`` (deterministic).

    Bisects the monotone :func:`standard_normal_cdf` on the fixed bracket
    ``[-_PPF_BRACKET, +_PPF_BRACKET]`` for a fixed :data:`_PPF_ITERATIONS` iterations,
    so the result is a pure function of ``p`` and ``context`` (no data-dependent early
    exit). ``p`` outside the open unit interval is a caller bug and raises rather than
    being guessed.
    """
    if not (_ZERO < p < _ONE):
        raise ValueError(f"standard_normal_ppf requires 0 < p < 1, got {p!r}")
    working = _working(context)
    with localcontext(working):
        low = -_PPF_BRACKET
        high = _PPF_BRACKET
        for _ in range(_PPF_ITERATIONS):
            mid = (low + high) / _TWO
            if standard_normal_cdf(mid, context=working) < p:
                low = mid
            else:
                high = mid
        estimate = (low + high) / _TWO
    with localcontext(context):
        return +estimate
