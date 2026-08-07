"""The universe-construction transformation version (data-model §9).

Per ``docs/data-model.md`` §9, a ``TransformationVersion`` identifies the
deterministic code that turns inputs into derived state:

    universe_version_id = hash(code_version)

For Phase 9.1 the "transformation" is the **universe builder**: the pure function
that resolves caller-supplied identifiers through the company identity layer,
canonicalizes and de-duplicates them preserving first-seen order, and hashes the
ordered membership into a ``universe_id``. This module pins that logic with a
stable version id, following the exact pattern of
:class:`~quantforge.metrics.version.MetricEngineVersion` and
:class:`~quantforge.availability.version.AvailabilityPolicy` — the id is a
``sha256:`` hash of the content and nothing depends on the wall clock.

The version records **how a universe's membership was derived**, so a
:class:`~quantforge.universe.model.Universe` built under one builder can never be
confused with one built under a builder that canonicalizes or de-duplicates
differently. Changing the construction logic in a way that can alter membership or
its ordering must bump :data:`UNIVERSE_BUILDER_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "UNIVERSE_BUILDER_VERSION",
    "UNIVERSE_CONSTRUCTION_VERSION",
    "UniverseBuilderVersion",
    "UniverseConstructionVersion",
]

# Bump this whenever the construction logic (canonicalization, de-duplication, or
# ordering rule) changes in a way that can alter a universe's membership or member
# order. It is the universe builder's analogue of a code git SHA, kept explicit and
# stable so derived identity never depends on the wall clock or a random value.
UNIVERSE_BUILDER_VERSION = "universe-builder/1"

# The Phase 9.2 construction-rule engine's version. Distinct from the Phase 9.1
# membership builder above: this pins the *rule-evaluation* logic (how a
# specification's ordered filters are applied to resolve eligible members and record
# exclusions). Bump it whenever a change could alter which companies a specification
# selects, their order, or the recorded exclusion reasons — so a universe built
# under one construction engine can never be confused with one built under a
# different rule semantics. It participates in every ``construction_id``.
UNIVERSE_CONSTRUCTION_VERSION = "universe-construction/1"


@dataclass(frozen=True, slots=True)
class UniverseBuilderVersion:
    """Immutable identity of the universe-construction logic (§9).

    Attributes
    ----------
    code_version:
        Revision string for the construction logic (git SHA in practice).
    """

    code_version: str = UNIVERSE_BUILDER_VERSION

    @property
    def universe_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version)`` (§9)."""
        return f"sha256:{sha256_hex(self.code_version.encode('utf-8'))}"


@dataclass(frozen=True, slots=True)
class UniverseConstructionVersion:
    """Immutable identity of the Phase 9.2 construction-rule engine (§9).

    The rule engine's analogue of :class:`UniverseBuilderVersion`: it pins the code
    that turns a :class:`~quantforge.universe.specification.UniverseSpecification`
    (a set of ordered filters) into a resolved :class:`Universe` plus recorded
    exclusions. Following the exact pattern of
    :class:`~quantforge.metrics.version.MetricEngineVersion`, the id is a
    ``sha256:`` hash of the content and nothing depends on the wall clock.

    Attributes
    ----------
    code_version:
        Revision string for the rule-evaluation logic (git SHA in practice).
    """

    code_version: str = UNIVERSE_CONSTRUCTION_VERSION

    @property
    def construction_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version)`` (§9)."""
        return f"sha256:{sha256_hex(self.code_version.encode('utf-8'))}"
