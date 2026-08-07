"""Canonical-fact transformation version (data-model §9/§11, requirement 11).

Per ``docs/data-model.md`` §9, a ``TransformationVersion`` identifies the
deterministic code+config that turns raw material into derived state:

    transformation_version_id = hash(code_git_sha, config_hash)

For Phase 4 the "transformation" is the **normalizer** that turns immutable
:class:`~quantforge.xbrl.model.RawFact` records into canonical
:class:`~quantforge.canonical.model.Fact` records: concept/taxonomy
classification, period canonicalization, conservative unit canonicalization, and
safe scale/sign folding into ``value_numeric``. This module pins that normalizer
logic with a stable version id, following the exact pattern of the Phase 2/3
versions (:mod:`quantforge.registry.version`, :mod:`quantforge.xbrl.version`).

Two properties are load-bearing (requirement 11, 12, 14; §11, §12 invariants
18-21):

* **The normalizer version is part of the canonical ``fact_id``** (unlike the
  parser version, which is deliberately *excluded* from ``raw_fact_id``). §11:
  ``fact_id = sha256(transformation_version_id, filing_id, obs_key)``. So a
  future change to normalization logic produces *new, distinct* Facts under a new
  version while the old Facts remain valid and untouched — normalization is never
  silently mutated in place (requirement 11, invariant 20).
* **The version depends only on code + config**, never on wall-clock time, a
  random UUID, or input ordering (invariant 21). ``config_hash`` folds in the
  unit-canonicalization and taxonomy maps that affect output; it deliberately
  does **not** include any availability rule (that is a separately-versioned
  ``AvailabilityPolicy``, Phase 5+).

Changing the normalizer logic in a way that can alter derived Facts must bump
:data:`CANONICAL_FACT_VERSION` (or pass a new ``code_version``).
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "CANONICAL_FACT_VERSION",
    "CanonicalFactVersion",
]

# Bump this whenever the normalizer's canonicalization logic changes in a way
# that can alter the derived Fact records (e.g. a new unit mapping, a changed
# scale-folding rule). It is the normalizer's analogue of a code git SHA for the
# (as-yet uncommitted) transformation code. Kept explicit and stable so derived
# identity never depends on the wall clock or a random value.
CANONICAL_FACT_VERSION = "canonical-fact/2"


@dataclass(frozen=True, slots=True)
class CanonicalFactVersion:
    """Immutable identity of the canonical-fact normalizer logic + config.

    Attributes
    ----------
    code_version:
        Revision string for the normalizer logic (git SHA in practice).
    config_hash:
        SHA-256 hex of the configuration that affects output — in particular the
        unit-canonicalization and taxonomy classification maps. Empty-config
        normalizations use the hash of the empty byte string.
    """

    code_version: str = CANONICAL_FACT_VERSION
    config_hash: str = sha256_hex(b"")

    @property
    def transformation_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§11)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    @classmethod
    def for_config(
        cls, config_bytes: bytes = b"", *, code_version: str | None = None
    ) -> CanonicalFactVersion:
        """Build a version pinning ``config_bytes`` (hashed) and code revision."""
        return cls(
            code_version=code_version or CANONICAL_FACT_VERSION,
            config_hash=sha256_hex(config_bytes),
        )
