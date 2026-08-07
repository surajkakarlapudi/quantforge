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
