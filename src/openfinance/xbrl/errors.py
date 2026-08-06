"""Exception hierarchy for the raw XBRL ingestion layer.

Rooted at :class:`XbrlError` so callers can catch every ingestion-specific
failure with one type. Phase 3 *derives* an immutable raw-fact representation
from the exact XBRL instance bytes acquired by Phase 1; these errors signal that
the derivation could not be performed **without fabricating financial data**.

The governing rule (data-model §12, requirement 12) is **fail closed**: when the
source is malformed, ambiguous, or structurally unsound, we raise rather than
invent a value, drop a fact silently, or guess a missing context/unit.
"""

from __future__ import annotations

__all__ = [
    "MalformedXbrlError",
    "UnsupportedXbrlError",
    "XbrlError",
]


class XbrlError(Exception):
    """Base class for all raw XBRL ingestion errors."""


class MalformedXbrlError(XbrlError):
    """The source bytes are not a structurally valid XBRL instance.

    Raised when the document is not well-formed XML, is not an XBRL instance,
    or is internally inconsistent in a way that would force us to invent data
    to proceed (a fact referencing a missing context or unit, a duplicate
    context/unit id, a context with no period, ...). We fail closed rather than
    fabricate financial values (requirement 12).
    """


class UnsupportedXbrlError(XbrlError):
    """The document is well-formed XBRL but uses a construct we do not parse.

    Distinct from :class:`MalformedXbrlError`: the source is not broken, but it
    exercises a structure outside this parser version's supported set (e.g. a
    nested namespace redefinition, documented in ``docs/xbrl-ingestion.md``).
    Raised — never silently mishandled — so the limitation is explicit and the
    fact is never misrepresented.
    """
