"""Exception hierarchy for the point-in-time Market Data Layer (Phase 11).

Rooted at :class:`MarketDataError` so a caller can catch every failure of this
layer with one type, mirroring the Phase 5
:class:`~quantforge.availability.errors.AvailabilityError` discipline
(``docs/phase11-market-data-locked.md`` §16). The layer *derives* a canonical,
point-in-time price/market-data view from immutable, content-addressed vendor
bytes via a versioned :class:`~quantforge.market.version.MarketAvailabilityPolicy`
and answers PIT / REVISED queries over the append-only observation set.

The governing posture (data-model §12 invariants 6-17) is **fail closed**, and it
draws the same sharp line Phases 5/10 draw between two failure kinds:

* A **data condition** — a bar the source never reported, a bar whose availability
  is ``UNKNOWN`` (fail-closed, excluded), a pre-listing / post-delisting / halt
  date — is **never** an exception. It is a first-class ``UNDEFINED`` / absent
  point-in-time result carrying a reason, never dropped, never imputed (Principle
  8). This mirrors :class:`~quantforge.availability.resolve.PitValue` with
  ``fact is None``.
* A **configuration / consistency defect** — a naive ``as_of`` (reusing the Phase
  5 :class:`~quantforge.availability.errors.ModeError` choke point), an
  overlapping / uninterpretable market policy scope, an empty or malformed date
  axis, a currency mismatch within a series, an ambiguous instrument resolution,
  or stored derived state that violates an invariant on read — *is* raised. These
  are our bugs, surfaced rather than silently resolved. A raised error or a
  withheld price is always preferable to a wrong, look-ahead-admitting one.

:class:`~quantforge.availability.errors.ModeError` is deliberately **reused**, not
re-declared: the market layer imports and reuses the Phase 5 ``timestamps.py``
choke point, so a naive PIT ``as_of`` raises the very same error type the rest of
the system already raises (invariant 15).
"""

from __future__ import annotations

__all__ = [
    "MarketConsistencyError",
    "MarketDataError",
    "MarketPolicyConfigurationError",
]


class MarketDataError(Exception):
    """Base class for all Market Data Layer (Phase 11) errors."""


class MarketPolicyConfigurationError(MarketDataError):
    """The market-data configuration cannot deterministically govern a query.

    The market-data analogue of
    :class:`~quantforge.availability.errors.PolicyConfigurationError` (§16): for a
    given ``(session date)`` **exactly one** active market
    :class:`~quantforge.market.version.MarketAvailabilityPolicy` version must
    govern; overlapping active eras are a configuration error, not something we may
    arbitrate by picking one. Also raised when a policy's declarative rule names a
    ``rule_kind`` / ``calendar`` the deriver does not implement (we refuse to guess
    a rule's intent), when a requested date axis is empty / malformed, or when a
    price series mixes currencies — all our bugs, surfaced rather than resolved.
    """


class MarketConsistencyError(MarketDataError):
    """A stored market record violates an integrity invariant on read.

    Fail-closed guard for derived state (mirrors
    :class:`~quantforge.availability.errors.AvailabilityConsistencyError` and
    :class:`~quantforge.factors.errors.FactorConsistencyError`): e.g. an
    observation whose recomputed ``price_observation_id`` disagrees with its stored
    id, a canonical store payload that cannot be decoded, or two observations that
    must share a ``market_transformation_version_id`` but do not. Surfaced rather
    than trusted so corrupted derived state can never silently admit a wrong PIT
    price.
    """
