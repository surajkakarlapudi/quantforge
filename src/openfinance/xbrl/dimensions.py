"""Dimensional context modeling and the deterministic ``dimensions_hash``.

Dimensions are the single most information-dense part of an XBRL context and the
one companyfacts throws away entirely (recon: 92-98% of contexts are
dimensional). Requirement 4 is categorical: *dimensional information must not be
discarded, and the* ``dimensions_hash`` *must be deterministic.* This module owns
both the loss-preserving representation of a dimension and the canonical
serialization that feeds the hash.

Canonical serialization (data-model §15.5, validated in recon §II.7):

* **Explicit members** — the sorted set of ``(axis_qname, member_qname)`` pairs,
  each QName in stable Clark notation so the value is filing-independent.
* **Typed members** — ``(axis_qname, "[typed]" + child_element_qname + "=" +
  normalized_text)``. The child element QName and its normalized text content
  capture the typed value structurally.
* **Undimensioned / default context** — the empty sentinel ``""``.

Sorting makes the key order-independent; Clark-notation QNames make it
prefix-independent. Both properties are required for determinism (invariant 18).

Typed-member text normalization is intentionally minimal and lossless-for-identity:
leading/trailing whitespace is stripped and internal runs of XML whitespace are
collapsed to single spaces (XML attribute/text whitespace handling), but the
value is **not** otherwise reinterpreted (no numeric parsing, no case folding) —
we are building an identity key, not interpreting the value.
"""

from __future__ import annotations

from dataclasses import dataclass

from openfinance.sec.artifacts import sha256_hex
from openfinance.xbrl.qnames import QName

__all__ = [
    "EMPTY_DIMENSIONS_SENTINEL",
    "RawDimension",
    "canonical_dimensions_key",
    "dimensions_hash",
    "normalize_typed_text",
]

#: The canonical key of a context with no dimensions (data-model §3.1, §15.5).
EMPTY_DIMENSIONS_SENTINEL = ""


def normalize_typed_text(text: str | None) -> str:
    """Collapse XML whitespace in a typed-member value for identity purposes.

    Strips leading/trailing whitespace and collapses internal whitespace runs to
    a single space. This is deterministic and identity-preserving; it does not
    interpret the value (requirement 5 — no semantic normalization).
    """
    if text is None:
        return ""
    return " ".join(text.split())


@dataclass(frozen=True, slots=True)
class RawDimension:
    """One dimensional constraint on a context, exactly as parsed.

    Attributes
    ----------
    axis:
        The dimension axis QName (e.g. ``us-gaap:StatementBusinessSegmentsAxis``),
        resolved to stable Clark notation.
    member:
        For an **explicit** member, the member QName in Clark notation. ``None``
        for a typed member.
    is_typed:
        Whether this is a typed (structured-value) dimension rather than an
        explicit (enumerated-member) one.
    typed_child:
        For a **typed** member, the QName of the child element carrying the typed
        value, in Clark notation. ``None`` for an explicit member.
    typed_text:
        For a **typed** member, the normalized text content of the typed value
        element. ``None`` for an explicit member.
    """

    axis: str
    member: str | None = None
    is_typed: bool = False
    typed_child: str | None = None
    typed_text: str | None = None

    @classmethod
    def explicit(cls, axis: QName, member: QName) -> RawDimension:
        return cls(axis=axis.clark, member=member.clark)

    @classmethod
    def typed(cls, axis: QName, child: QName, text: str | None) -> RawDimension:
        return cls(
            axis=axis.clark,
            is_typed=True,
            typed_child=child.clark,
            typed_text=normalize_typed_text(text),
        )

    def canonical_member(self) -> str:
        """The canonical member serialization used in the dimensions key.

        Explicit → the member QName; typed → ``[typed]child=value`` (§15.5).
        """
        if self.is_typed:
            child = self.typed_child or ""
            text = self.typed_text or ""
            return f"[typed]{child}={text}"
        return self.member or ""

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis,
            "member": self.member,
            "is_typed": self.is_typed,
            "typed_child": self.typed_child,
            "typed_text": self.typed_text,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawDimension:
        axis = raw["axis"]
        if not isinstance(axis, str):
            raise ValueError("dimension axis must be a string")
        return cls(
            axis=axis,
            member=_opt_str(raw, "member"),
            is_typed=bool(raw.get("is_typed", False)),
            typed_child=_opt_str(raw, "typed_child"),
            typed_text=_opt_str(raw, "typed_text"),
        )


def canonical_dimensions_key(dimensions: tuple[RawDimension, ...]) -> str:
    """Return the deterministic canonical key for a set of dimensions (§15.5).

    Order-independent (pairs are sorted) and prefix-independent (Clark-notation
    QNames). The undimensioned/default context maps to the empty sentinel.

    The pair separator (U+001F, unit separator) and record separator (U+001E)
    are control characters that cannot occur in a QName or in whitespace-collapsed
    text, so the serialization is unambiguous and injective for valid input.
    """
    if not dimensions:
        return EMPTY_DIMENSIONS_SENTINEL
    pairs = sorted((d.axis, d.canonical_member()) for d in dimensions)
    return "\x1e".join(f"{axis}\x1f{member}" for axis, member in pairs)


def dimensions_hash(dimensions: tuple[RawDimension, ...]) -> str:
    """Return ``sha256:<hex>`` of the canonical dimensions key (§3.1, §15.5).

    The default (undimensioned) context hashes the empty sentinel to a stable,
    well-known digest, so *every* context — dimensional or not — has a
    deterministic ``dimensions_hash``.
    """
    key = canonical_dimensions_key(dimensions)
    return f"sha256:{sha256_hex(key.encode('utf-8'))}"


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value
