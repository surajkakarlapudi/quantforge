"""Exception hierarchy for the strategy-admissibility layer (Phase 33, §15).

Rooted at :class:`AdmissibilityError` so a caller can catch every failure of this layer
with one type. Phase 33 is a *pure consumer* strictly above Phases 27/29/32: it resolves
the three already-sealed ex-post verdicts of one strategy - a
:class:`~quantforge.stability.result.WalkForwardStability`, a
:class:`~quantforge.calsig.result.CalibrationSignificance`, and a
:class:`~quantforge.netcostsig.result.NetOfCostSignificance` - from the shared research
sidecar, reads their sealed statuses / p-values / edge direction verbatim, and seals a
single joint admissibility verdict. It resolves no data and re-derives no statistic from
source (AD-4), so its only failures are of the request or of a consistency invariant.

The governing posture mirrors every prior layer's split (§15), and the significance
layers (Phases 29/32) in particular:

* A **data / evaluation condition** - any consumed verdict that is itself UNDEFINED (the
  book's stability was never assessable; the calibration test or the net-of-cost test
  was never run) - is **never** an exception. It makes the corresponding criterion
  UNDEFINED, and the joint verdict fails closed to UNDEFINED (AD-2), sealed honestly
  with which criteria were undefined; never fabricated, never coerced into a pass or a
  fail.
* A **configuration / consistency defect** - an empty ``name`` / ``spec_version`` /
  source id, an ``alpha`` outside ``(0, 1)``, a source id absent from the sidecar, or a
  resolved record whose ``research_result_id`` disagrees with the request or that is not
  the expected record type - *is* raised. These are our bugs, surfaced rather than
  silently resolved. A raised error is always preferable to a wrong admissibility
  verdict.
"""

from __future__ import annotations

__all__ = [
    "AdmissibilityConfigurationError",
    "AdmissibilityConsistencyError",
    "AdmissibilityError",
]


class AdmissibilityError(Exception):
    """Base class for all strategy-admissibility-layer errors."""


class AdmissibilityConfigurationError(AdmissibilityError):
    """A strategy-admissibility request is internally inconsistent - our bug.

    Raised for a malformed
    :class:`~quantforge.admissibility.spec.AdmissibilitySpecification` (an empty
    ``name`` / ``spec_version`` / source id, or an ``alpha`` that is not a decimal
    string strictly inside ``(0, 1)``) or for a non-spec argument to the engine. We
    refuse to guess a request's intent, exactly as the significance layers refuse a
    misconfigured request."""


class AdmissibilityConsistencyError(AdmissibilityError):
    """An admissibility verdict cannot be honestly formed from a reference - surfaced.

    Fail-closed guard for the reference contract (§15, AD-1): a named source id is
    absent from the research sidecar; a resolved record does not decode as its expected
    type (a :class:`~quantforge.stability.result.WalkForwardStability`, a
    :class:`~quantforge.calsig.result.CalibrationSignificance`, or a
    :class:`~quantforge.netcostsig.result.NetOfCostSignificance`); or a resolved
    record's ``research_result_id`` disagrees with the requested id (the sidecar is
    inconsistent). Each is a consistency violation and is raised - never silently
    computed around. (A consumed verdict that is genuinely UNDEFINED is *not* raised:
    the joint verdict fails closed to UNDEFINED, AD-2.)"""
