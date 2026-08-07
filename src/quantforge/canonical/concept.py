"""Deterministic concept representation (requirement 2, data-model §3.1).

A canonical concept preserves, without interpretation:

* the **namespace URI** (stable, prefix-independent identity of the taxonomy);
* the **local name** (the XBRL tag local part, verbatim);
* the **Clark notation** (``{uri}local``) as the canonical, prefix-independent
  identity string;
* the classified **taxonomy** label (see :mod:`quantforge.canonical.taxonomy`).

The categorical rule (requirement 2): **we do not aggressively map concepts.**
``us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`` and
``us-gaap:Revenues`` are *different concepts* and remain distinguishable; an
issuer-specific ``<ticker>:*`` concept is preserved intact. There is **no**
concept-to-concept normalization, synonym table, or "canonical concept" mapping
here — none can be established with high confidence in this phase, so we preserve
the original concept exactly (requirement 2: "If a concept mapping cannot be
established with high confidence: PRESERVE THE ORIGINAL CONCEPT. No guessing.").

The Phase 3 :class:`~quantforge.xbrl.model.RawFact` already stores the concept in
Clark notation (``{uri}local``). This module *reads* that identity and splits it
into its parts plus a taxonomy label; it never rewrites the concept.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.canonical.taxonomy import Taxonomy, classify_taxonomy
from quantforge.xbrl.qnames import split_clark

__all__ = ["Concept", "concept_from_clark"]


@dataclass(frozen=True, slots=True)
class Concept:
    """A reported concept, preserved losslessly and prefix-independently.

    Identity is the Clark notation (``{uri}local``); ``namespace_uri`` and
    ``local_name`` are the decomposed parts, and ``taxonomy`` is the convenience
    classification. Never a normalized/mapped concept — the original always
    survives (requirement 2).
    """

    #: The canonical, prefix-independent identity string: ``{uri}local`` (or the
    #: bare local name when the concept has no namespace).
    clark: str
    #: The namespace URI, or ``None`` for an unqualified concept.
    namespace_uri: str | None
    #: The local name (XBRL tag local part), verbatim.
    local_name: str
    #: The classified taxonomy label; the full ``namespace_uri`` is authoritative.
    taxonomy: Taxonomy

    def to_dict(self) -> dict[str, object]:
        return {
            "clark": self.clark,
            "namespace_uri": self.namespace_uri,
            "local_name": self.local_name,
            "taxonomy": self.taxonomy.value,
        }


def concept_from_clark(clark: str) -> Concept:
    """Build a :class:`Concept` from a Clark-notation concept string.

    Splits ``{uri}local`` into its namespace URI and local name (never guessing a
    namespace for an unqualified tag) and classifies the taxonomy from the URI.
    The concept is preserved exactly; nothing is mapped or merged (requirement 2).
    """
    namespace_uri, local = split_clark(clark)
    return Concept(
        clark=clark,
        namespace_uri=namespace_uri,
        local_name=local,
        taxonomy=classify_taxonomy(namespace_uri),
    )
