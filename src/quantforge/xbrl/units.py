"""Structured raw-unit representation.

Requirement 9: *handle units structurally; preserve the original unit definition
and numerator/denominator structure; unknown units remain unknown and are never
silently coerced.* A single string token is insufficient — recon (§II.8) found
compound units (``USD/shares`` expressed as an XBRL ``divide`` of two measures),
FX pairs, duration units (``utr:D``), and many custom ``<issuer>:*`` units.

A :class:`RawUnit` therefore captures the unit **exactly as declared**:

* a simple unit is one or more ``<measure>`` QNames (typically one);
* a ``divide`` unit is a numerator measure set over a denominator measure set.

No unit is interpreted, mapped, or converted here (requirement 5): a
``iso4217:USD`` measure is preserved as the QName ``{...}USD``, not turned into a
canonical ``USD`` token; a ``ge:segment`` custom unit is preserved verbatim.
Canonical unit tokens/currency inference are Phase 4's job. What we guarantee is
that the raw structure survives losslessly and hashes deterministically.

``unit_ref`` — the stable identity token for a unit, used inside ``raw_fact_id``
(§11) — is the canonical serialization of this structure, so two facts with a
structurally identical unit share a ``unit_ref`` regardless of source prefixes,
and two facts with different units never collide.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.xbrl.qnames import QName

__all__ = ["RawUnit"]


@dataclass(frozen=True, slots=True)
class RawUnit:
    """An XBRL unit definition, preserved structurally and without coercion.

    Attributes
    ----------
    unit_id:
        The unit's ``id`` attribute as written in the instance (the token facts
        reference via ``unitRef``). Preserved verbatim for audit; it is *local*
        to the document and so is **not** used for cross-filing identity.
    numerator:
        The numerator measure QNames, in Clark notation, in document order. A
        simple (non-``divide``) unit puts its measure(s) here.
    denominator:
        The denominator measure QNames for a ``divide`` unit, in Clark notation;
        an empty tuple for a simple unit.
    is_divide:
        Whether the unit was declared as an XBRL ``divide`` (a ratio of
        measures) rather than a simple measure list.
    """

    unit_id: str
    numerator: tuple[str, ...]
    denominator: tuple[str, ...] = ()
    is_divide: bool = False

    @classmethod
    def simple(cls, unit_id: str, measures: tuple[QName, ...]) -> RawUnit:
        return cls(
            unit_id=unit_id,
            numerator=tuple(m.clark for m in measures),
        )

    @classmethod
    def divide(
        cls,
        unit_id: str,
        numerator: tuple[QName, ...],
        denominator: tuple[QName, ...],
    ) -> RawUnit:
        return cls(
            unit_id=unit_id,
            numerator=tuple(m.clark for m in numerator),
            denominator=tuple(m.clark for m in denominator),
            is_divide=True,
        )

    def unit_ref(self) -> str:
        """The stable, filing-independent unit identity token (used in §11).

        Built from the *structure* (measure QNames, numerator/denominator role),
        never the document-local ``unit_id``, so structurally identical units
        from different filings share a ref. Measures within a numerator or
        denominator are sorted so declaration order cannot change identity;
        numerator vs denominator roles are preserved because ``A/B`` ≠ ``B/A``.

        The separators are control characters (U+001F between measures, U+001E
        between the numerator and denominator groups) that cannot appear in a
        QName, keeping the serialization unambiguous.
        """
        num = "\x1f".join(sorted(self.numerator))
        if self.is_divide:
            den = "\x1f".join(sorted(self.denominator))
            return f"divide\x1e{num}\x1e{den}"
        return num

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "numerator": list(self.numerator),
            "denominator": list(self.denominator),
            "is_divide": self.is_divide,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawUnit:
        unit_id = raw["unit_id"]
        if not isinstance(unit_id, str):
            raise ValueError("unit_id must be a string")
        return cls(
            unit_id=unit_id,
            numerator=_str_tuple(raw, "numerator"),
            denominator=_str_tuple(raw, "denominator"),
            is_divide=bool(raw.get("is_divide", False)),
        )


def _str_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(value)
