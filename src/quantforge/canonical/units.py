"""Conservative unit canonicalization (requirement 6, data-model §3.1).

This module maps a Phase 3 :class:`~quantforge.xbrl.units.RawUnit` (a structural
measure list or ``divide`` ratio) to a canonical unit token *only when the
mapping is deterministic and unambiguous*. Everything else stays
:data:`CANONICAL_UNIT_UNKNOWN` — never guessed, never silently coerced.

The rules (requirement 6, invariant 26):

* **Separate raw unit from canonical unit.** The raw structure (numerator /
  denominator measure QNames, the document-local ``unit_id``) is always retained
  on the Fact via :class:`~quantforge.canonical.model.Fact` fields — this module
  only *adds* a canonical label; it never replaces the raw structure.
* **Do not infer units from concept names** (requirement 6). Canonicalization
  looks only at the declared measure QNames, never at the concept.
* **Explicit, deterministic mappings only:**
  - a single ``iso4217:<CCC>`` measure → the currency code ``<CCC>``
    (``currency = <CCC>``, monetary);
  - a single ``xbrli:shares`` measure → ``shares``;
  - a single ``xbrli:pure`` measure → ``pure`` (a dimensionless ratio — **not**
    a percent; we never assume a scale);
  - a ``divide`` of a single ``iso4217:<CCC>`` numerator over a single
    ``xbrli:shares`` denominator → ``<CCC>/shares`` (e.g. per-share amounts),
    ``currency = <CCC>``.
* **Everything else → UNKNOWN.** Compound units we do not recognize, custom
  ``<issuer>:*`` measures, ``utr:*`` unit-registry measures (``utr:D`` days,
  etc.), multi-measure units, and any divide shape outside the one above are all
  left ``UNKNOWN`` with ``currency = None``. The raw structure still fully
  survives, so a later transformation version can canonicalize more once a
  mapping is justified — we simply refuse to guess now (requirement 17).

No unit is ever *converted* (no FX, no scaling); canonicalization is pure
labelling. Scale folding into the numeric value is a separate concern
(:mod:`quantforge.canonical.numeric`).
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.xbrl.qnames import split_clark
from quantforge.xbrl.units import RawUnit

__all__ = [
    "CANONICAL_UNIT_UNKNOWN",
    "CanonicalUnit",
    "canonicalize_unit",
]

#: The canonical unit token for any unit we cannot canonicalize with confidence.
#: Never a silent coercion — the raw structure is always preserved alongside it.
CANONICAL_UNIT_UNKNOWN = "UNKNOWN"

# Structural namespace URIs used to recognize standard measures. Matched on the
# namespace URI (prefix-independent), never the source prefix.
_ISO4217_NS = "http://www.xbrl.org/2003/iso4217"
_XBRLI_NS = "http://www.xbrl.org/2003/instance"


@dataclass(frozen=True, slots=True)
class CanonicalUnit:
    """The canonical labelling of a raw unit — token plus optional currency.

    ``token`` is a canonical unit string (``USD``, ``shares``, ``USD/shares``,
    ``pure``) or :data:`CANONICAL_UNIT_UNKNOWN`. ``currency`` is the ISO 4217 code
    when the unit is monetary, else ``None``. Neither field ever replaces the raw
    unit structure retained on the Fact (invariant 26).
    """

    token: str
    currency: str | None

    @property
    def is_known(self) -> bool:
        return self.token != CANONICAL_UNIT_UNKNOWN

    def to_dict(self) -> dict[str, object]:
        return {"token": self.token, "currency": self.currency}


def _single_measure(measures: tuple[str, ...]) -> tuple[str | None, str] | None:
    """Return ``(namespace_uri, local)`` if exactly one measure, else ``None``."""
    if len(measures) != 1:
        return None
    return split_clark(measures[0])


def canonicalize_unit(unit: RawUnit | None) -> CanonicalUnit:
    """Map a raw unit to a :class:`CanonicalUnit`, conservatively.

    Returns :data:`CANONICAL_UNIT_UNKNOWN` (with ``currency = None``) for a
    non-numeric fact with no unit (``unit is None``) and for any unit outside the
    small set of deterministic mappings above. Never guesses, never converts,
    never infers from the concept (requirement 6).
    """
    if unit is None:
        return CanonicalUnit(CANONICAL_UNIT_UNKNOWN, None)

    if unit.is_divide:
        return _canonicalize_divide(unit)
    return _canonicalize_simple(unit)


def _canonicalize_simple(unit: RawUnit) -> CanonicalUnit:
    measure = _single_measure(unit.numerator)
    if measure is None:
        return CanonicalUnit(CANONICAL_UNIT_UNKNOWN, None)
    ns, local = measure
    if ns == _ISO4217_NS:
        # A currency code, e.g. iso4217:USD -> "USD", monetary.
        return CanonicalUnit(local, local)
    if ns == _XBRLI_NS and local == "shares":
        return CanonicalUnit("shares", None)
    if ns == _XBRLI_NS and local == "pure":
        return CanonicalUnit("pure", None)
    return CanonicalUnit(CANONICAL_UNIT_UNKNOWN, None)


def _canonicalize_divide(unit: RawUnit) -> CanonicalUnit:
    numerator = _single_measure(unit.numerator)
    denominator = _single_measure(unit.denominator)
    if numerator is None or denominator is None:
        return CanonicalUnit(CANONICAL_UNIT_UNKNOWN, None)
    num_ns, num_local = numerator
    den_ns, den_local = denominator
    # The one recognized ratio: currency-per-share (e.g. EPS), CUR/shares.
    if num_ns == _ISO4217_NS and den_ns == _XBRLI_NS and den_local == "shares":
        return CanonicalUnit(f"{num_local}/shares", num_local)
    return CanonicalUnit(CANONICAL_UNIT_UNKNOWN, None)
