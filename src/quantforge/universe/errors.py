"""Exception vocabulary for the universe-management layer (Phase 9.1).

Rooted at :class:`UniverseError` so a caller can catch every failure of this
layer with one type. The layer *composes* the existing company identity layer to
turn caller-supplied identifiers into an ordered, provenance-carrying set of
canonical filer identities; it introduces no new identifier system and no
storage.

The governing posture matches the identity and factor layers (a sharp split
between two failure kinds):

* A **resolution failure** — an unknown ticker, an ambiguous symbol, or a missing
  ticker mapping — is *not* raised by this layer. It is surfaced by the identity
  layer as an :class:`~quantforge.identity.errors.IdentityError` and propagates
  unchanged; we never re-wrap or soften it, because it is already fail-closed and
  already carries the offending identifier.
* A **configuration defect** — an empty universe (a universe over nobody is a
  configuration bug, not an empty result), or a mis-typed argument — *is* raised
  here as a :class:`UniverseConfigurationError`. We refuse to guess a universe's
  intent, exactly as the factor layer refuses an empty factor universe.
"""

from __future__ import annotations

__all__ = [
    "UniverseConfigurationError",
    "UniverseError",
    "UniverseSpecificationError",
]


class UniverseError(Exception):
    """Base class for all universe-management errors."""


class UniverseConfigurationError(UniverseError):
    """A universe request is internally inconsistent — our bug, surfaced.

    Raised for an empty universe (no identifiers, or every identifier collapsing
    to nothing after de-duplication), or for a mis-typed argument (for example a
    bare string passed where an iterable of identifiers is expected). A raised
    error is always preferable to a silently wrong or empty universe.
    """


class UniverseSpecificationError(UniverseConfigurationError):
    """A universe *construction* specification is internally inconsistent (§9.2).

    A subclass of :class:`UniverseConfigurationError` (a mis-specified construction
    is a configuration bug), raised by the Phase 9.2 construction layer for a
    specification defect our code should refuse rather than guess around:

    * a specification with no filters (a construction that selects on nothing is a
      bug, not a request for "everyone");
    * a :class:`CompanyMetricFilter` naming an unknown ``metric_key`` — surfaced by
      the same fail-closed :class:`~quantforge.metrics.registry.FormulaRegistry`
      lookup that refuses a mis-typed metric (this is what rejects a not-yet-modeled
      metric such as ``market_cap``);
    * a serialized filter/specification whose ``kind`` or fields cannot be
      reconstructed.

    A **data condition** — a filter that legitimately excludes a company because a
    metric is ``UNDEFINED`` at the boundary, or because it has no sector under the
    supplied classification — is *never* raised here; it is recorded as a
    first-class :class:`~quantforge.universe.filters.ExcludedCompany` with a reason.
    Only an *empty final universe* fails closed, via
    :class:`UniverseConfigurationError`, exactly as Phase 9.1 does.
    """
