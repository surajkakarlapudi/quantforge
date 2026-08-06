"""Exception hierarchy for the canonical fact layer (Phase 4).

Rooted at :class:`CanonicalError` so callers can catch every canonicalization
failure with one type. Phase 4 *derives* the canonical :class:`Fact` from the
immutable :class:`~openfinance.xbrl.model.RawFact` records produced by Phase 3.

The governing rule (data-model §12, requirement 17) is **fail closed**: when the
raw material is internally contradictory or cannot be interpreted without
inventing a financial value, we raise rather than guess, silently drop, or
manufacture a number. A raised error is always preferable to a wrong fact.
"""

from __future__ import annotations

__all__ = [
    "CanonicalContradictionError",
    "CanonicalError",
]


class CanonicalError(Exception):
    """Base class for all canonical-fact derivation errors."""


class CanonicalContradictionError(CanonicalError):
    """Two raw facts share one observation key and filing but disagree on value.

    Data-model §13 case 8: within a *single* filing, two raw facts that reduce to
    the same ``obs_key`` are either a genuine duplicate (identical value → they
    collapse to one :class:`Fact`) or a **contradiction** (different value). A
    contradiction is a data-quality defect in the source, not something we may
    silently merge or arbitrate — canonicalization would have to choose a value,
    which it must never do. We fail closed and surface the conflict.
    """
