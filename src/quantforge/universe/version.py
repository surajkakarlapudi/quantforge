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
    "UniverseBuilderVersion",
]

# Bump this whenever the construction logic (canonicalization, de-duplication, or
# ordering rule) changes in a way that can alter a universe's membership or member
# order. It is the universe builder's analogue of a code git SHA, kept explicit and
# stable so derived identity never depends on the wall clock or a random value.
UNIVERSE_BUILDER_VERSION = "universe-builder/1"


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
