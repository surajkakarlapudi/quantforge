"""XBRL parser transformation version.

Per ``docs/data-model.md`` §9/§11, a ``TransformationVersion`` identifies the
deterministic code+config that turns raw material into derived state:

    transformation_version_id = hash(code_git_sha, config_hash)

For Phase 3 the "transformation" is the **parser** that turns exact XBRL
instance bytes into immutable ``RawDocument`` + ``RawFact`` records (context,
unit, dimension, and fact extraction; deterministic identity/serialization).
This module pins that parser logic with a stable version id, following the exact
pattern of the Phase 2 registry :class:`TransformationVersion`
(:mod:`quantforge.registry.version`).

Critically (data-model §12, invariants 18 & 21): the parser version — and
therefore every ``RawFact`` identity derived under it — **must not depend on
wall-clock time, a random UUID, or input ordering.** It depends only on:

* ``code_version`` — a caller-supplied revision string for the parser logic (a
  git SHA in practice); defaults to a constant tied to this module's behavior so
  tests and offline use are deterministic.
* ``config_hash`` — a hash of any configuration that changes the output.

Note (data-model §11): the parser version is recorded as **provenance** on every
``RawFact``, but is deliberately **not** part of the ``raw_fact_id`` — the raw id
is a pure function of the source content (``raw_document_id``, context ref,
concept, unit ref, segment key, ordinal), so re-parsing identical bytes always
reproduces the same raw ids. The parser version *is* part of the canonical
``Fact`` id, which is Phase 4's concern. Changing the parser logic in a way that
can alter derived records must bump :data:`XBRL_PARSER_VERSION` (or pass a new
``code_version``).
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.sec.artifacts import sha256_hex

__all__ = [
    "XBRL_PARSER_VERSION",
    "XbrlParserVersion",
]

# Bump this whenever the parser's extraction logic changes in a way that can
# alter the derived RawFact/RawContext/RawUnit records or their serialization.
# It is the parser's analogue of a code git SHA for the (as-yet uncommitted)
# transformation code. Kept explicit and stable so derived provenance never
# depends on the wall clock or a random value.
XBRL_PARSER_VERSION = "xbrl-parser/1"


@dataclass(frozen=True, slots=True)
class XbrlParserVersion:
    """Immutable identity of the XBRL parser logic + config.

    Attributes
    ----------
    code_version:
        Revision string for the parser logic (git SHA in practice).
    config_hash:
        SHA-256 hex of the configuration that affects output. Empty-config
        parses use the hash of the empty byte string.
    """

    code_version: str = XBRL_PARSER_VERSION
    config_hash: str = sha256_hex(b"")

    @property
    def transformation_version_id(self) -> str:
        """Deterministic id: ``sha256(code_version, config_hash)`` (§11)."""
        payload = f"{self.code_version}\x00{self.config_hash}".encode()
        return f"sha256:{sha256_hex(payload)}"

    @classmethod
    def for_config(
        cls, config_bytes: bytes = b"", *, code_version: str | None = None
    ) -> XbrlParserVersion:
        """Build a version pinning ``config_bytes`` (hashed) and code revision."""
        return cls(
            code_version=code_version or XBRL_PARSER_VERSION,
            config_hash=sha256_hex(config_bytes),
        )
