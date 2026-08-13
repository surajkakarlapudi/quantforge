"""Exception hierarchy for the walk-forward turnover & stability layer (Phase 27, §15).

Rooted at :class:`StabilityError` so a caller can catch every failure of this layer with
one type. Phase 27 is a *pure consumer* strictly above Phase 22: it resolves exactly one
already-sealed :class:`~quantforge.walkforward.result.WalkForwardEvaluation` from the
shared research sidecar, reads its per-window sealed ``weights`` (the re-estimated GMV
training vector, in factor order), and seals the per-window weight-vector stability
metrics and one-way turnover plus the aggregate turnover / concentration profile. It
resolves no data at any ``T`` and re-derives nothing from source - it never re-solves a
window's GMV (WS-4) - so its only failures are of the request or of a consistency
invariant.

The governing posture mirrors every prior layer's split (§15), and the calibration /
walk-forward layers in particular:

* A **data / evaluation condition** - a window the source sealed as UNDEFINED, a window
  with no adjacent REALIZED predecessor to trade from, or a walk with too few
  realized-adjacent transitions - is **never** an exception. It is excluded from the
  family and recorded as a first-class
  :class:`~quantforge.stability.result.ExcludedWindow`, or preserved as an UNDEFINED
  cell / status carrying *why* (WS-3), never imputed, never coerced to a number, never
  silently dropped.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  ``source_walk_forward_id``, the source id absent from the sidecar, a resolved record
  whose ``research_result_id`` disagrees with the request or that is not a
  :class:`~quantforge.walkforward.result.WalkForwardEvaluation`, or a REALIZED source
  window whose weight vector is malformed (any non-KNOWN cell, or a length that
  disagrees with the walk's factor count) - *is* raised. These are our bugs (or a
  corrupt sidecar), surfaced rather than silently resolved. A raised error is always
  preferable to a wrong stability statistic.
"""

from __future__ import annotations

__all__ = [
    "StabilityConfigurationError",
    "StabilityConsistencyError",
    "StabilityError",
]


class StabilityError(Exception):
    """Base class for all walk-forward turnover & stability-layer errors."""


class StabilityConfigurationError(StabilityError):
    """A stability request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.stability.spec.WalkForwardStabilitySpecification` (an empty
    ``name`` / ``spec_version`` / ``source_walk_forward_id``) or for a
    non-:class:`~quantforge.stability.spec.WalkForwardStabilitySpecification` argument
    passed to the engine. We refuse to guess a request's intent, exactly as the
    walk-forward and calibration layers refuse a misconfigured request."""


class StabilityConsistencyError(StabilityError):
    """A stability analysis cannot be honestly computed from the reference - surfaced.

    Fail-closed guard for the reference contract (§15, WS-1/WS-4): the
    ``source_walk_forward_id`` is absent from the research sidecar; the resolved record
    does not decode as a :class:`~quantforge.walkforward.result.WalkForwardEvaluation`;
    the resolved record's ``research_result_id`` disagrees with the requested id (the
    sidecar is inconsistent); or a REALIZED source window carries a malformed weight
    vector (any non-KNOWN cell, or a length that disagrees with the walk's
    ``n_factors``). Each is a consistency violation and is raised - never silently
    computed around. (A
    window the source sealed as UNDEFINED, or a window with no adjacent REALIZED
    predecessor, is *not* raised: it is genuinely undefined for the data, so it is
    excluded from the family or preserved as an UNDEFINED cell, WS-3.)"""
