"""Exception hierarchy for the multiple-comparison-correction layer (Phase 25, §15).

Rooted at :class:`MultiplicityError` so a caller can catch every failure of this layer
with one type. Phase 25 is a *pure consumer* strictly above Phase 24: it resolves
exactly one already-sealed :class:`~quantforge.comparison.result.StrategyComparison`
from the shared research sidecar, treats that comparison's KNOWN pairwise ``p`` values
as one hypothesis family, and seals the family-wise-error / false-discovery-rate
adjusted ``p`` values plus a rejection set at a declared ``alpha``. It resolves no data
at any ``T`` and re-derives nothing from source, so its only failures are of the request
or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the comparison layer
in particular:

* A **data / evaluation condition** - a pairwise cell whose ``p`` value the source
  sealed as UNDEFINED (too little date overlap, or a zero-variance paired difference) -
  is **never** an exception. It is excluded from the corrected family and recorded as a
  first-class :class:`~quantforge.multiplicity.model.ExcludedCell` carrying *why*
  (MC-3/MC-4), never imputed, never coerced to a number, never silently dropped.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  source id, an ``alpha`` outside the open interval ``(0, 1)``, an empty or duplicated
  method list, the source id absent from the sidecar, or a resolved record whose
  ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.comparison.result.StrategyComparison` - *is* raised. These are our
  bugs, surfaced rather than silently resolved. A raised error is always preferable to a
  wrong multiplicity correction.
"""

from __future__ import annotations

__all__ = [
    "MultiplicityConfigurationError",
    "MultiplicityConsistencyError",
    "MultiplicityError",
]


class MultiplicityError(Exception):
    """Base class for all multiple-comparison-correction-layer errors."""


class MultiplicityConfigurationError(MultiplicityError):
    """A multiple-comparison-correction request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification` (an empty
    ``name`` / ``spec_version`` / ``source_strategy_comparison_id``; an ``alpha`` that
    is not a decimal string strictly inside ``(0, 1)``; an empty method tuple or a
    duplicated method) or for a
    non-:class:`~quantforge.multiplicity.spec.MultipleComparisonSpecification` argument
    to the engine. We refuse to guess a request's intent, exactly as the comparison and
    campaign layers refuse a misconfigured request."""


class MultiplicityConsistencyError(MultiplicityError):
    """A correction cannot be honestly evaluated from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, MC-1): the
    ``source_strategy_comparison_id`` is absent from the research sidecar; the resolved
    record does not decode as a
    :class:`~quantforge.comparison.result.StrategyComparison`; or the resolved record's
    ``research_result_id`` disagrees with the requested id (the sidecar is
    inconsistent). Each is a consistency violation and is raised - never silently
    computed around. (A pairwise cell whose ``p`` value the source sealed as UNDEFINED
    is *not* raised: it is genuinely undefined for the data, so it is excluded from the
    family and recorded as a first-class
    :class:`~quantforge.multiplicity.model.ExcludedCell`, MC-3/MC-4.)"""
