"""Deterministic taxonomy classification (requirement 3, data-model §3.1).

The canonical :class:`~openfinance.canonical.model.Fact` carries a ``taxonomy``
enum (``us-gaap``, ``dei``, ``ifrs-full``, ``srt``, …) *alongside* — never
instead of — the fully-qualified concept. The enum is a convenience label for
querying; the authoritative identity is always the concept's namespace URI plus
local name (see :mod:`openfinance.canonical.concept`).

The governing rules:

* **Do not hard-code a closed vocabulary that rejects issuer extensions**
  (requirement 3). A namespace URI we do not recognize is **not** an error and is
  **not** dropped: it is classified :data:`Taxonomy.CUSTOM` (a versioned or
  issuer-specific namespace) and the full namespace URI is preserved on the Fact,
  so a ``khc:`` or ``tsla:`` extension concept round-trips losslessly.
* **Classification is by namespace URI, never by prefix** — prefixes are
  filing-local aliases (recon §II.7). We match the *stable* standard-taxonomy URI
  stems the SEC/FASB/IFRS publish, which embed the owner but vary by yearly
  version (``.../us-gaap/2023`` vs ``.../us-gaap/2024``); we therefore match on a
  stem, and the exact versioned URI stays on the concept.
* A concept with **no namespace** (an unqualified tag) is :data:`Taxonomy.UNKNOWN`
  — we never guess which taxonomy an unqualified name belongs to.

This module maps a namespace URI → :class:`Taxonomy`. It is pure and deterministic
and interprets no financial meaning.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Taxonomy", "classify_taxonomy"]


class Taxonomy(StrEnum):
    """The reporting taxonomy a concept belongs to.

    ``US_GAAP``/``DEI``/``SRT``/``IFRS_FULL`` are the well-known standard
    taxonomies. ``CUSTOM`` is any other *namespaced* taxonomy — most importantly
    a company-specific issuer extension (``<ticker>:*``), which must be preserved,
    never rejected (requirement 3). ``UNKNOWN`` is an unqualified concept with no
    namespace at all, which we refuse to guess about.
    """

    US_GAAP = "us-gaap"
    DEI = "dei"
    SRT = "srt"
    IFRS_FULL = "ifrs-full"
    #: A namespaced taxonomy that is not one of the standard ones above —
    #: typically a company-specific issuer extension. Preserved, never dropped.
    CUSTOM = "custom"
    #: A concept with no namespace URI at all. We do not guess its taxonomy.
    UNKNOWN = "unknown"


# Stable URI *stems* for the standard taxonomies. Matched by ``startswith`` so a
# yearly-versioned URI (``http://fasb.org/us-gaap/2024`` etc.) classifies
# correctly while the exact versioned URI is preserved verbatim on the concept.
# This is a recognition list, NOT a closed vocabulary: an unrecognized namespace
# is classified CUSTOM (or UNKNOWN when absent), never rejected (requirement 3).
_STANDARD_TAXONOMY_STEMS: tuple[tuple[str, Taxonomy], ...] = (
    ("http://fasb.org/us-gaap/", Taxonomy.US_GAAP),
    ("http://xbrl.us/us-gaap/", Taxonomy.US_GAAP),  # pre-FASB-hosted era
    ("http://xbrl.sec.gov/dei/", Taxonomy.DEI),
    ("http://xbrl.us/dei/", Taxonomy.DEI),
    ("http://fasb.org/srt/", Taxonomy.SRT),
    ("http://xbrl.sec.gov/srt/", Taxonomy.SRT),
    ("http://xbrl.ifrs.org/taxonomy/", Taxonomy.IFRS_FULL),
    ("https://xbrl.ifrs.org/taxonomy/", Taxonomy.IFRS_FULL),
)


def classify_taxonomy(namespace_uri: str | None) -> Taxonomy:
    """Classify a concept's namespace URI into a :class:`Taxonomy`.

    Deterministic and total. A recognized standard-taxonomy URI stem returns the
    corresponding member; any other *namespaced* URI is :data:`Taxonomy.CUSTOM`
    (an issuer extension or unrecognized taxonomy, preserved not rejected); a
    missing namespace is :data:`Taxonomy.UNKNOWN` (we never guess).
    """
    if namespace_uri is None or not namespace_uri:
        return Taxonomy.UNKNOWN
    for stem, taxonomy in _STANDARD_TAXONOMY_STEMS:
        if namespace_uri.startswith(stem):
            return taxonomy
    return Taxonomy.CUSTOM
