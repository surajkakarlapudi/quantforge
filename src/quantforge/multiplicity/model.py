"""The multiple-comparison-correction vocabulary: methods and their honest labels.

A **multiple-comparison correction** treats the KNOWN pairwise ``p`` values of one
sealed :class:`~quantforge.comparison.result.StrategyComparison` as a single hypothesis
family and adjusts them so that a family-wise error rate (FWE) or a false-discovery rate
(FDR) is controlled at a declared ``alpha``. This module defines the closed method
vocabulary and - load-bearing for honesty (MC-6) - the **dependence assumption each
method makes**, because the pairwise ``p`` values of one comparison are *not*
independent (pairs share strategies).

* :class:`CorrectionMethod` - the closed set of procedures: ``BONFERRONI`` and ``HOLM``
  (FWE), ``BENJAMINI_HOCHBERG`` and ``BENJAMINI_YEKUTIELI`` (FDR).
* :class:`ErrorRate` - which error quantity a method controls (family-wise vs
  false-discovery).
* :class:`DependenceAssumption` - the dependence structure under which a method's
  guarantee holds: ``ARBITRARY`` (valid under any dependence - Bonferroni, Holm,
  Benjamini-Yekutieli) or ``INDEPENDENCE_OR_PRDS`` (valid only under independence or
  positive-regression dependence - Benjamini-Hochberg). Sealed alongside every method's
  results so the record is self-describing and Benjamini-Hochberg can never be mistaken
  for a dependence-robust guarantee (MC-6).
* :func:`method_error_rate` / :func:`method_dependence` - the single source of truth for
  a method's labels, so the engine never re-states them inconsistently.

Every value is a plain ``StrEnum`` string - deterministically serializable, no
wall-clock, no RNG, no iteration-order dependence.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CorrectionMethod",
    "DependenceAssumption",
    "ErrorRate",
    "method_dependence",
    "method_error_rate",
]


class CorrectionMethod(StrEnum):
    """The closed set of multiplicity-correction procedures (MC-5).

    ``BONFERRONI`` (single-step FWE) and ``HOLM`` (step-down FWE) control the
    family-wise error rate; ``BENJAMINI_HOCHBERG`` (step-up FDR) and
    ``BENJAMINI_YEKUTIELI`` (step-up FDR with the harmonic penalty) control the
    false-discovery rate. See :func:`method_error_rate` / :func:`method_dependence` for
    each method's controlled quantity and dependence assumption.
    """

    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"
    BENJAMINI_YEKUTIELI = "benjamini_yekutieli"


class ErrorRate(StrEnum):
    """Which multiple-testing error quantity a method controls."""

    #: The probability of *one or more* false rejections across the family.
    FAMILY_WISE = "family_wise"
    #: The expected *proportion* of false rejections among the rejections.
    FALSE_DISCOVERY = "false_discovery"


class DependenceAssumption(StrEnum):
    """The dependence structure under which a method's guarantee holds (MC-6).

    The pairwise ``p`` values of a single strategy comparison are dependent (pairs share
    strategies), so this label is load-bearing: it records, in the sealed answer,
    whether a method's control is valid for that dependent family or only under an
    *assumed* independence / positive-regression structure.
    """

    #: Valid under arbitrary dependence (Bonferroni, Holm, Benjamini-Yekutieli).
    ARBITRARY = "arbitrary"
    #: Valid only under independence or positive-regression dependence (PRDS) -
    #: Benjamini-Hochberg. An explicitly *assumed* structure for the dependent pairwise
    #: family, never a guarantee.
    INDEPENDENCE_OR_PRDS = "independence_or_prds"


# The single source of truth for each method's honest labels (MC-6). A closed mapping so
# adding a method is a deliberate, reviewed change - never a silent default.
_ERROR_RATE: dict[CorrectionMethod, ErrorRate] = {
    CorrectionMethod.BONFERRONI: ErrorRate.FAMILY_WISE,
    CorrectionMethod.HOLM: ErrorRate.FAMILY_WISE,
    CorrectionMethod.BENJAMINI_HOCHBERG: ErrorRate.FALSE_DISCOVERY,
    CorrectionMethod.BENJAMINI_YEKUTIELI: ErrorRate.FALSE_DISCOVERY,
}

_DEPENDENCE: dict[CorrectionMethod, DependenceAssumption] = {
    CorrectionMethod.BONFERRONI: DependenceAssumption.ARBITRARY,
    CorrectionMethod.HOLM: DependenceAssumption.ARBITRARY,
    CorrectionMethod.BENJAMINI_HOCHBERG: DependenceAssumption.INDEPENDENCE_OR_PRDS,
    CorrectionMethod.BENJAMINI_YEKUTIELI: DependenceAssumption.ARBITRARY,
}


def method_error_rate(method: CorrectionMethod) -> ErrorRate:
    """The error quantity ``method`` controls (family-wise vs false-discovery)."""
    return _ERROR_RATE[method]


def method_dependence(method: CorrectionMethod) -> DependenceAssumption:
    """The dependence structure under which ``method``'s guarantee holds (MC-6)."""
    return _DEPENDENCE[method]
