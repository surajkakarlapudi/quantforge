"""Well-known XBRL namespace URIs.

These are the *structural* namespaces of the XBRL 2.1 / Dimensions specs — the
grammar of an instance document (contexts, units, periods, dimensional
segments, the nil marker). They are stable, standardized URIs and are used only
to **locate** structural elements while parsing; they are never used to
interpret financial meaning (that is Phase 4).

Reporting taxonomies (``us-gaap``, ``dei``, ``srt``, ``ifrs-full``, and every
company-specific ``<issuer>:*`` namespace) are deliberately **not** enumerated
here: the parser treats every reported concept, axis, and member as an opaque,
namespace-resolved QName, so custom issuer concepts survive untouched
(requirement 3, recon Implementation Contract).
"""

from __future__ import annotations

__all__ = [
    "XBRLDI_NS",
    "XBRLI_NS",
    "XLINK_NS",
    "XSI_NS",
]

#: The XBRL instance namespace: ``xbrli:xbrl``, ``context``, ``unit``,
#: ``period``, ``entity``, ``measure``, ``divide``, ``shares``, ``pure``, ...
XBRLI_NS = "http://www.xbrl.org/2003/instance"

#: The XBRL Dimensions namespace: ``xbrldi:explicitMember`` / ``typedMember``.
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"

#: XML Schema instance namespace — carries the ``xsi:nil`` marker (nil ≠ zero).
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

#: XLink namespace, present on instance roots; not otherwise interpreted here.
XLINK_NS = "http://www.w3.org/1999/xlink"
