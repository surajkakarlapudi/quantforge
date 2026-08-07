"""Exception hierarchy for the filing registry.

Rooted at :class:`RegistryError` so callers can catch every registry-specific
failure with one type. The registry *derives* state from immutable acquisition
artifacts; these errors signal that a derivation could not be performed safely
(missing identity, corrupt source, or an ambiguity we refuse to guess through).
"""

from __future__ import annotations

__all__ = [
    "AccessionFormatError",
    "DocumentAssociationError",
    "RegistryError",
    "SourceValidationError",
]


class RegistryError(Exception):
    """Base class for all filing-registry errors."""


class AccessionFormatError(RegistryError, ValueError):
    """A string could not be canonicalized to a valid SEC accession number."""

    def __init__(self, value: object) -> None:
        self.value = value
        super().__init__(f"not a valid SEC accession number: {value!r}")


class SourceValidationError(RegistryError):
    """A source acquisition artifact was malformed or internally inconsistent.

    Raised when derived state cannot be produced without fabricating a value
    (e.g. a submissions row with no accession number, or JSON that does not
    have the expected columnar shape). The registry fails closed rather than
    invent data.
    """


class DocumentAssociationError(RegistryError):
    """A document could not be unambiguously associated with a filing.

    Raised when the provenance of an acquired artifact contradicts the filing
    it would attach to (e.g. an accession that matches but a CIK that does
    not). We never fabricate an association; ambiguity fails closed.
    """
