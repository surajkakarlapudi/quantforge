"""The pure multiplicity-correction procedures over one ``p`` value family (§11, §12).

Given a family of ``m`` KNOWN ``p`` values (in the source comparison's upper-triangle
order) and a declared ``alpha``, :func:`correct_family` computes, for each requested
:class:`~quantforge.multiplicity.model.CorrectionMethod`, the adjusted ``p`` value and
the rejection flag of every family member - all under an explicit
:class:`decimal.Context`, in exact ``Decimal`` arithmetic, with no RNG, no floating
point, and no data-dependent iteration (a single ascending sort plus closed-form
monotone step recursions).

The four procedures, in the ascending-sorted rank space ``p_(1) ≤ … ≤ p_(m)`` (ties
broken by the family index, a total order):

* **Bonferroni** (single-step FWE): ``p_adj_(k) = min(1, m · p_(k))``.
* **Holm** (step-down FWE): raw ``q_(k) = (m - k + 1) · p_(k)``; enforce monotonicity
  with a **running max** from the smallest rank up (``p_adj_(k) = max_{l ≤ k} q_(l)``);
  cap at ``1``.
* **Benjamini-Hochberg** (step-up FDR, independence / PRDS): raw
  ``q_(k) = (m / k) · p_(k)``; enforce monotonicity with a **running min** from the
  largest rank down (``p_adj_(k) = min_{l ≥ k} q_(l)``); cap at ``1``.
* **Benjamini-Yekutieli** (step-up FDR, arbitrary dependence): as Benjamini-Hochberg but
  scaled by the harmonic constant ``c(m) = Σ_{k=1}^{m} 1/k`` (raw
  ``q_(k) = (m · c(m) / k) · p_(k)``), so it is valid under arbitrary dependence.

The running min / running max make tied ``p`` values receive **identical** adjusted
values (MC-4). Rejection is defined **uniformly** as ``p_adj ≤ alpha`` for every method,
so the adjusted value and its rejection flag can never disagree - the sealed record is
internally self-consistent (MC-5). This is the standard step-function rejection set for
each procedure under exact arithmetic.

Pure: a function of the ``p`` values, the methods, ``alpha``, and the context - no wall
clock, no RNG, no iteration-order dependence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.multiplicity.model import CorrectionMethod

__all__ = [
    "MethodComputation",
    "correct_family",
]

_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class MethodComputation:
    """One method's adjusted ``p`` values + rejection flags, in **family order**.

    ``adjusted`` and ``rejected`` are aligned index-for-index to the ``p_values`` passed
    to :func:`correct_family` (the source upper-triangle order), *not* the internal
    ascending-sorted order - so the engine can map each result straight back onto its
    ``(i, j)`` cell.
    """

    method: CorrectionMethod
    adjusted: tuple[Decimal, ...]
    rejected: tuple[bool, ...]


def correct_family(
    p_values: Sequence[Decimal],
    methods: Sequence[CorrectionMethod],
    alpha: Decimal,
    *,
    context: Context,
) -> tuple[MethodComputation, ...]:
    """Adjust one ``p`` value family by each method; flag rejections at ``alpha`` (§11).

    ``p_values`` are the family's KNOWN ``p`` values in source upper-triangle order
    (each a ``Decimal`` in ``[0, 1]``). Returns one :class:`MethodComputation` per
    method, in the requested order, each aligned back to family order. An **empty
    family** (``len(p_values) == 0``) returns, per method, empty ``adjusted`` /
    ``rejected`` tuples - never a divide-by-zero (MC-3). Deterministic: identical inputs
    yield identical ``Decimal`` values on any machine.
    """
    m = len(p_values)
    if m == 0:
        return tuple(MethodComputation(method, (), ()) for method in methods)

    with localcontext(context):
        # A total order: ascending p, ties broken by family index (which is the
        # upper-triangle (i, j) order). Deterministic and machine-independent.
        order = sorted(range(m), key=lambda idx: (p_values[idx], idx))
        sorted_p = [p_values[idx] for idx in order]
        m_dec = Decimal(m)

        results: list[MethodComputation] = []
        for method in methods:
            adjusted_sorted = _adjust_sorted(method, sorted_p, m_dec)
            # Map the sorted-rank results back to the original family order.
            adjusted_family: list[Decimal] = [_ZERO] * m
            for rank, idx in enumerate(order):
                adjusted_family[idx] = adjusted_sorted[rank]
            rejected_family = tuple(value <= alpha for value in adjusted_family)
            results.append(
                MethodComputation(
                    method=method,
                    adjusted=tuple(adjusted_family),
                    rejected=rejected_family,
                )
            )
    return tuple(results)


def _adjust_sorted(
    method: CorrectionMethod, sorted_p: list[Decimal], m_dec: Decimal
) -> list[Decimal]:
    """Adjusted ``p`` values in ascending-sorted rank order for one ``method``.

    ``sorted_p`` is ascending; ``m_dec`` is the family size as a ``Decimal``. Returns
    the monotone, ``[0, 1]``-capped adjusted values in the same rank order. All
    arithmetic runs under the caller's active (pinned) decimal context.
    """
    m = len(sorted_p)
    if method is CorrectionMethod.BONFERRONI:
        # Single step: min(1, m · p). Already non-decreasing (p is sorted ascending).
        return [_min1(m_dec * p) for p in sorted_p]

    if method is CorrectionMethod.HOLM:
        # Step-down FWE: raw (m - k + 1)·p_(k); running max up; cap 1.
        raw = [Decimal(m - rank) * sorted_p[rank] for rank in range(m)]
        return _running_max_capped(raw)

    if method is CorrectionMethod.BENJAMINI_HOCHBERG:
        # Step-up FDR: raw (m / k)·p_(k); running min down; cap 1.
        raw = [(m_dec / Decimal(rank + 1)) * sorted_p[rank] for rank in range(m)]
        return _running_min_capped(raw)

    if method is CorrectionMethod.BENJAMINI_YEKUTIELI:
        # Step-up FDR under arbitrary dependence: Benjamini-Hochberg scaled by the
        # harmonic constant c(m) = Σ 1/k. An exact finite Decimal sum, no truncation.
        cm = _harmonic(m)
        raw = [(m_dec * cm / Decimal(rank + 1)) * sorted_p[rank] for rank in range(m)]
        return _running_min_capped(raw)

    # A CorrectionMethod with no branch is a programming error, not a data condition.
    raise AssertionError(f"unhandled correction method {method!r}")


def _harmonic(m: int) -> Decimal:
    """The harmonic constant ``c(m) = Σ_{k=1}^{m} 1/k`` under the active context.

    A finite, deterministic sum (no series truncation ambiguity); the only arithmetic in
    the layer beyond multiply / divide / compare. Summed in ascending ``k`` order so the
    accumulation is reproducible.
    """
    total = _ZERO
    for k in range(1, m + 1):
        total += _ONE / Decimal(k)
    return total


def _running_max_capped(raw: list[Decimal]) -> list[Decimal]:
    """Enforce non-decreasing monotonicity by a forward running max, then cap at 1.

    Holm's step-down enforcement: the adjusted value at rank ``k`` is the largest raw
    value at any rank ``≤ k`` (so it never decreases as the rank rises), capped at
    ``1``. Tied ``p`` values collapse to one shared adjusted value (MC-4).
    """
    out: list[Decimal] = []
    running = None
    for value in raw:
        running = value if running is None or value > running else running
        out.append(_min1(running))
    return out


def _running_min_capped(raw: list[Decimal]) -> list[Decimal]:
    """Enforce non-decreasing monotonicity by a backward running min, then cap at 1.

    The Benjamini-Hochberg / Benjamini-Yekutieli step-up enforcement: the adjusted value
    at rank ``k`` is the smallest raw value at any rank ``≥ k`` (so it is non-decreasing
    in ``k``), capped at ``1``. Tied ``p`` values collapse to one shared adjusted value
    (MC-4).
    """
    out: list[Decimal | None] = [None] * len(raw)
    running = None
    for rank in range(len(raw) - 1, -1, -1):
        value = raw[rank]
        running = value if running is None or value < running else running
        out[rank] = _min1(running)
    # Every slot is populated by the reverse pass above.
    return [value for value in out if value is not None]


def _min1(value: Decimal) -> Decimal:
    """Cap an adjusted ``p`` value at ``1`` (a probability never exceeds one)."""
    return value if value < _ONE else _ONE
