"""Registry transformation version.

Per ``docs/data-model.md`` §9, a ``TransformationVersion`` identifies the
deterministic code+config that turns raw material into derived state:

    transformation_version_id = hash(code_git_sha, config_hash)

For the filing registry the "transformation" is the logic that turns
submissions/index artifacts into filing records (parsing, accession
canonicalization, amendment inference, document association). This module pins
that logic with a stable version id.

Critically (data-model §9, §12 invariants 18-21): the version - and therefore
the derived registry's logical identity - **must not depend on wall-clock time,
a random UUID, or input ordering.** It depends only on:

* ``code_version`` — a caller-supplied revision string for the registry logic
  (in practice a git SHA); defaults to a constant tied to this module's
  behavior so tests and offline use are deterministic.
* ``config_hash`` — a hash of any configuration that changes the output.

Changing the logic ⇒ bump ``REGISTRY_LOGIC_VERSION`` (or pass a new
``code_version``) ⇒ a distinguishable ``transformation_version_id``. Same logic
+ same config ⇒ identical id across machines and runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.sec.artifacts import sha256_hex

__all__ = [
    "REGISTRY_LOGIC_VERSION",
    "TransformationVersion",
]

# Bump this whenever the registry's derivation logic changes in a way that can
# alter the derived records. It is the registry's analogue of a code git SHA
# for the (as-yet uncommitted) transformation code. Kept explicit and stable so
# derived identity never depends on the wall clock or a random value.
REGISTRY_LOGIC_VERSION = "filing-registry/1"


@dataclass(frozen=True, slots=True)
class TransformationVersion:
    """Immutable identity of the registry derivation logic + config.

    Attributes
    ----------
    code_version:
        Revision string for the registry logic (git SHA in practice).
    config_hash:
        SHA-256 hex of the configuration that affects output. Empty-config
        derivations use the hash of the empty byte string.
    """

    code_version: str = REGISTRY_LOGIC_VERSION
    config_hash: str = sha256_hex(b"")

    @property
    def transformation_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§11)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    @classmethod
    def for_config(
        cls, config_bytes: bytes = b"", *, code_version: str | None = None
    ) -> TransformationVersion:
        """Build a version pinning ``config_bytes`` (hashed) and code revision."""
        return cls(
            code_version=code_version or REGISTRY_LOGIC_VERSION,
            config_hash=sha256_hex(config_bytes),
        )
