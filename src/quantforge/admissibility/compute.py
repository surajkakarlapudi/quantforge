"""The pure, deterministic joint admissibility decision rule (§11, §12).

Given the already-computed answers of one strategy's three sealed ex-post verdicts -
reduced by the engine to the primitive facts each contributes (AD-4: the sealed statuses
and p-values are consumed verbatim, no statistic is recomputed here) - plus the declared
significance level ``alpha``, :func:`decide_admissibility` evaluates the three
admissibility criteria and rolls them up into a single verdict. The rule is a set of
exact-``Decimal`` comparisons; it evaluates no transcendental (the ``Φ`` CDF was applied
and sealed by the significance layers) and has no RNG, no floating point, and no
data-dependent iteration.

The three criteria (ordered STABILITY, CALIBRATION, NET_OF_COST_EDGE - a fixed order so
the answer seal is deterministic):

* **Stability** - PASS iff the source book was STABLE; else UNDEFINED
  (``STABILITY_UNDEFINED``). The stability layer's status is binary (STABLE vs
  UNDEFINED: it never asserts "unstable", only "not assessable"), so this criterion
  never FAILs - it either passes or is undefined.
* **Calibration** - a two-sided test of the variance-ratio null ``1``. PASS iff the
  sealed p-value is ``> alpha`` (we fail to reject calibration - the risk model is not
  significantly mis-calibrated); FAIL iff ``<= alpha`` (significantly mis-calibrated);
  UNDEFINED (``CALIBRATION_UNDEFINED``) iff the source was not TESTED / its p-value is
  not KNOWN.
* **Net-of-cost edge** - a one-sided upper-tailed test of the mean-return null ``0``.
  PASS iff the sealed p-value is ``<= alpha`` **and** the edge is PROFITABLE
  (significantly positive after costs); FAIL otherwise; UNDEFINED
  (``NET_OF_COST_UNDEFINED``) iff the source was not TESTED / its p-value is not KNOWN.

The fail-closed roll-up (AD-2): ``ADMISSIBLE`` iff all three criteria PASS;
``UNDEFINED`` iff **any** criterion is UNDEFINED (a strategy whose stability,
calibration, or after-cost edge could not even be assessed is not silently called
inadmissible - the verdict is undefined); otherwise ``INADMISSIBLE`` (every criterion
decidable, at least one FAIL).

Pure: a function of the primitive inputs, the level, and the context - no wall clock, no
RNG, no iteration-order dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from quantforge.admissibility.model import (
    AdmissibilityUndefinedReason,
    AdmissibilityVerdict,
    Criterion,
    CriterionKind,
    CriterionStatus,
)

__all__ = [
    "AdmissibilityComputation",
    "AdmissibilityInputs",
    "decide_admissibility",
]


@dataclass(frozen=True, slots=True)
class AdmissibilityInputs:
    """The primitive facts the engine extracts from the three sealed verdicts (AD-4).

    Every field is read verbatim from a source record - no statistic is recomputed:

    * ``stability_stable`` - the source book's ``stability_status`` is STABLE.
    * ``calibration_defined`` / ``calibration_p`` - the calibration test was TESTED with
      a KNOWN p-value, and that (two-sided) p-value as a ``Decimal``; ``calibration_p``
      is ``None`` iff not defined.
    * ``net_defined`` / ``net_p`` / ``net_profitable`` - the net-of-cost test was TESTED
      with a KNOWN p-value, that (one-sided) p-value as a ``Decimal``, and whether the
      sealed edge direction is PROFITABLE; ``net_p`` is ``None`` iff not defined.
    """

    stability_stable: bool
    calibration_defined: bool
    calibration_p: Decimal | None
    net_defined: bool
    net_p: Decimal | None
    net_profitable: bool


@dataclass(frozen=True, slots=True)
class AdmissibilityComputation:
    """The full pure result: the verdict + the three ordered criteria (§11)."""

    verdict: AdmissibilityVerdict
    criteria: tuple[Criterion, ...]


def decide_admissibility(
    inputs: AdmissibilityInputs,
    *,
    alpha: Decimal,
    context: Context,
) -> AdmissibilityComputation:
    """Evaluate the three criteria and roll them up into a verdict (§11,
    AD-2/AD-3/AD-4).

    ``inputs`` are the primitive facts extracted verbatim from the three sealed
    verdicts; ``alpha`` is the declared significance level (``0 < alpha < 1``);
    ``context`` is the pinned decimal context. Deterministic: identical inputs yield an
    identical verdict and identical criteria on any machine.
    """
    with localcontext(context):
        stability = _stability_criterion(inputs)
        calibration = _calibration_criterion(inputs, alpha)
        net_edge = _net_edge_criterion(inputs, alpha)

    criteria = (stability, calibration, net_edge)
    verdict = _roll_up(criteria)
    return AdmissibilityComputation(verdict=verdict, criteria=criteria)


def _stability_criterion(inputs: AdmissibilityInputs) -> Criterion:
    """PASS iff the source book was STABLE; else UNDEFINED (AD-3)."""
    if inputs.stability_stable:
        return Criterion.passed(CriterionKind.STABILITY, detail="stable")
    return Criterion.undefined(
        CriterionKind.STABILITY,
        AdmissibilityUndefinedReason.STABILITY_UNDEFINED,
    )


def _calibration_criterion(inputs: AdmissibilityInputs, alpha: Decimal) -> Criterion:
    """PASS iff the two-sided calibration p-value ``> alpha``; FAIL if ``<=``; else
    UNDEFINED (AD-3)."""
    if not inputs.calibration_defined or inputs.calibration_p is None:
        return Criterion.undefined(
            CriterionKind.CALIBRATION,
            AdmissibilityUndefinedReason.CALIBRATION_UNDEFINED,
        )
    detail = str(+inputs.calibration_p)
    if inputs.calibration_p > alpha:
        return Criterion.passed(CriterionKind.CALIBRATION, detail=detail)
    return Criterion.failed(CriterionKind.CALIBRATION, detail=detail)


def _net_edge_criterion(inputs: AdmissibilityInputs, alpha: Decimal) -> Criterion:
    """PASS iff the one-sided net p-value ``<= alpha`` **and** PROFITABLE; FAIL if
    decidable but not; else UNDEFINED (AD-3)."""
    if not inputs.net_defined or inputs.net_p is None:
        return Criterion.undefined(
            CriterionKind.NET_OF_COST_EDGE,
            AdmissibilityUndefinedReason.NET_OF_COST_UNDEFINED,
        )
    detail = str(+inputs.net_p)
    if inputs.net_p <= alpha and inputs.net_profitable:
        return Criterion.passed(CriterionKind.NET_OF_COST_EDGE, detail=detail)
    return Criterion.failed(CriterionKind.NET_OF_COST_EDGE, detail=detail)


def _roll_up(criteria: tuple[Criterion, ...]) -> AdmissibilityVerdict:
    """The fail-closed roll-up over the ordered criteria (AD-2).

    UNDEFINED if any criterion is UNDEFINED; ADMISSIBLE if every criterion PASSed;
    INADMISSIBLE otherwise (every criterion decidable, at least one FAIL).
    """
    if any(c.status is CriterionStatus.UNDEFINED for c in criteria):
        return AdmissibilityVerdict.UNDEFINED
    if all(c.status is CriterionStatus.PASS for c in criteria):
        return AdmissibilityVerdict.ADMISSIBLE
    return AdmissibilityVerdict.INADMISSIBLE
