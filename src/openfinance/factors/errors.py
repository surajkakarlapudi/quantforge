"""Exception hierarchy for the cross-sectional factor layer (Phase 8).

Rooted at :class:`FactorError` so a caller can catch every failure of this layer
with one type. Phase 8 *composes* the Phase 7 metric engine across an explicit
universe of filers at one shared boundary; it computes no arithmetic of its own
beyond the pure cross-sectional transforms (``docs/factors.md`` §6.2).

The governing posture matches Phase 7 (``docs/factors.md`` §1.5, §6.1; data-model
§12) — a sharp split between two failure kinds:

* A **data condition** — a universe member has no facts, or a required metric
  input is not yet public at ``as_of`` — is **never** an exception. It is a
  first-class ``UNDEFINED`` :class:`~openfinance.factors.model.FactorCell` carrying
  the Phase 7 :class:`~openfinance.metrics.model.UndefinedReason`. A factor over a
  large universe must record "undefined for filer X, because Y" without aborting.
* A **configuration/consistency defect** — an empty universe, a duplicate member
  that cannot be canonicalized, an unknown transform, a boundary/type misuse, or
  stored derived state that violates an invariant on read — *is* raised. These are
  our bugs, surfaced rather than silently resolved. A raised error is always
  preferable to a wrong factor.
"""

from __future__ import annotations

__all__ = [
    "FactorConfigurationError",
    "FactorConsistencyError",
    "FactorError",
]


class FactorError(Exception):
    """Base class for all cross-sectional factor errors."""


class FactorConfigurationError(FactorError):
    """A factor request is internally inconsistent — our bug, surfaced.

    Raised for an empty universe (a factor over nobody is a configuration bug, not
    an empty result), a member identifier that cannot be canonicalized to a
    ``company_id``, an unknown transform id, or a boundary/type misuse. We refuse
    to guess a factor's intent, exactly as Phase 7 refuses to guess a
    misconfigured formula and Phase 5 a misconfigured policy.
    """


class FactorConsistencyError(FactorError):
    """A computed or stored factor/ResearchResult violates an invariant on read.

    Fail-closed guard for derived state (data-model §12): surfaced rather than
    trusted so a corrupted or contradictory result can never silently masquerade
    as valid. In particular, a re-computed :class:`ResearchResult` whose payload
    differs from a stored one under the same ``research_result_id`` is a
    determinism violation and is raised, never silently overwritten (§7, §15).
    """
