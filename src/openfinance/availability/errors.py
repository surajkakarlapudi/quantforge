"""Exception hierarchy for the public-availability & point-in-time layer (Phase 5).

Rooted at :class:`AvailabilityError` so a caller can catch every failure of this
layer with one type. Phase 5 *derives* public-availability from immutable filing
evidence via a versioned :class:`~openfinance.availability.version.AvailabilityPolicy`
and answers point-in-time (PIT) / revised queries over the append-only Fact set.

The governing posture (data-model §PA.3, §12 invariants 6-17) is **fail closed**:
when evidence is insufficient or a policy is misconfigured, we never fabricate a
too-early availability (a look-ahead correctness bug) — we mark the filing
``unknown`` (which is *never* PIT-eligible) or raise. A raised error or a withheld
fact is always preferable to a wrong, look-ahead-admitting one.

The distinct error types map to distinct failure modes:

* :class:`PolicyConfigurationError` — the *policy set* is internally inconsistent
  (overlapping active scopes, a rule the deriver cannot interpret). This is our
  configuration bug, surfaced rather than silently resolved (§PA.2: "overlapping
  active scopes are a configuration error").
* :class:`ModeError` — a resolution query violated the knowledge-state integrity
  rules (§KS.4 / invariants 27-28): no explicit mode, a naive ``as_of``, or an
  attempt to feed a ``REVISED`` value where a ``PIT`` value is required.
* :class:`AvailabilityConsistencyError` — a stored availability record contradicts
  an invariant on read (e.g. a filing's triple drifting, invariant 17), caught so
  corrupted derived state fails closed rather than propagating.
"""

from __future__ import annotations

__all__ = [
    "AvailabilityConsistencyError",
    "AvailabilityError",
    "ModeError",
    "PolicyConfigurationError",
]


class AvailabilityError(Exception):
    """Base class for all public-availability / point-in-time errors."""


class PolicyConfigurationError(AvailabilityError):
    """The availability policy set cannot deterministically govern a filing.

    Data-model §PA.2: for a given ``(form, acceptance date)`` **exactly one**
    active policy version must match; overlapping active scopes are a
    configuration error, not something we may arbitrate by picking one. Also
    raised when a policy's declarative ``rule_definition`` names a rule the
    deriver does not implement — we refuse to guess a rule's intent.
    """


class ModeError(AvailabilityError):
    """A resolution query violated the PIT/REVISED knowledge-state contract.

    Data-model §KS.4 invariants 27-28 and §6.4: mode is explicit and required
    (no implicit default), a ``PIT`` ``as_of`` must be timezone-aware (a naive
    instant is an ambiguous look-ahead risk, invariant 15), and a ``REVISED``
    result must never be consumed where a historical ``PIT`` value is required
    (invariant 28, enforced at the type boundary).
    """


class AvailabilityConsistencyError(AvailabilityError):
    """A stored availability record violates an integrity invariant on read.

    Fail-closed guard for derived state: e.g. a single filing whose facts carry
    more than one availability triple (invariant 17), or a stored status/policy
    pairing that violates invariant 12. Surfaced rather than trusted so corrupted
    derived state can never silently admit a wrong PIT answer.
    """
