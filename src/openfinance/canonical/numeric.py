"""Safe numeric normalization: scale, sign, nil, and exact decimals (req. 7, 8).

This module turns a Phase 3 :class:`~openfinance.xbrl.model.RawFact`'s raw
lexical value + ``scale``/``sign``/``decimals`` metadata into the canonical
``value_numeric`` (in **base units**, scale and sign folded in exactly once),
``value_text`` (for non-numeric concepts), and the parsed ``scale``/``decimals``.

The load-bearing rules (requirements 7 & 8, invariants 25 & 26):

* **nil ≠ zero (invariant 25).** A nil fact yields ``value_numeric = None`` and
  ``value_text = None``; it is *never* coerced to ``0``. It remains a first-class
  observation (the Fact keeps ``is_nil = True``).
* **Exact arithmetic.** All numeric work uses :class:`~decimal.Decimal`, never
  binary ``float``, so no rounding drift is introduced.
* **Scale folded in exactly once.** Phase 3 deliberately does **not** apply
  ``scale`` to the raw value. Phase 4 folds it in once —
  ``value_numeric = raw_value * 10**scale`` — so a value=123 scale=3 becomes
  123000 and is *not* scaled twice (a specific requirement 8 test). The default
  XBRL scale is 0.
* **Sign folded in exactly once.** XBRL ``sign="-"`` means the reported magnitude
  is negated; Phase 3 preserves ``sign`` verbatim without applying it, so Phase 4
  negates once. Any ``sign`` other than absent or ``"-"`` is malformed.
* **Raw always survives.** The raw lexical value, raw scale, raw sign, and raw
  decimals are retained verbatim on the canonical Fact (invariant 26), so the
  normalization is fully re-derivable and auditable — this module never discards
  source metadata, it only *adds* the folded canonical value.
* **Fail closed on an uninterpretable scale.** ``scale`` directly determines the
  value's magnitude; a non-integer ``scale`` on a numeric fact means we cannot
  compute a correct value, so we raise rather than guess (requirement 17). A
  non-integer/``INF`` ``decimals`` is precision metadata only (audit/rounding);
  it degrades to ``None`` with the raw string retained, never a hard failure.

Deterministic serialization (requirement 7): the canonical value is serialized
with :func:`canonical_decimal_str`, a plain-notation form (no scientific
notation, trailing fractional zeros stripped, negative zero normalized to ``0``)
so equal magnitudes always serialize to identical bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from openfinance.canonical.errors import CanonicalError
from openfinance.xbrl.model import RawFact

__all__ = ["NumericValue", "canonical_decimal_str", "canonicalize_numeric"]

#: The XBRL "infinite precision" decimals sentinel (kept only as raw metadata).
_DECIMALS_INF = "INF"


def canonical_decimal_str(value: Decimal) -> str:
    """Serialize a :class:`Decimal` to a deterministic, plain-notation string.

    Uses fixed-point (never scientific) notation, strips trailing zeros in the
    fractional part (and a bare trailing point), and normalizes negative zero to
    ``"0"`` — so two Decimals of equal mathematical value always produce identical
    bytes regardless of how scale folding constructed them. Precision is *not*
    lost here: it is carried separately by the ``decimals`` field (audit).
    """
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


@dataclass(frozen=True, slots=True)
class NumericValue:
    """The canonicalized numeric outcome for one fact.

    ``value_numeric_str`` is the base-unit value (scale & sign folded), serialized
    deterministically, or ``None`` for nil / non-numeric facts. ``value_text``
    carries a non-numeric concept's raw text. ``scale`` is the folded-in power of
    ten (0 by default). ``decimals`` is the parsed precision, or ``None`` when
    absent, ``INF``, or non-integer (raw retained on the Fact regardless).
    """

    value_numeric_str: str | None
    value_text: str | None
    scale: int
    decimals: int | None


def _parse_scale(raw_scale: str | None) -> int | None:
    """Parse the raw ``scale`` string to an int, or ``None`` if uninterpretable.

    A missing scale is the XBRL default of 0 (handled by the caller). This helper
    returns ``None`` only when a *present* scale cannot be read as an integer.
    """
    if raw_scale is None:
        return 0
    text = raw_scale.strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return None


def _parse_decimals(raw_decimals: str | None) -> int | None:
    """Parse the raw ``decimals`` string to an int; ``INF``/absent/odd → ``None``.

    ``decimals`` is precision metadata used only for audit and rounding, so an
    ``INF`` (infinite precision) or otherwise non-integer value degrades to
    ``None`` — the raw string is preserved on the Fact, so nothing is lost.
    """
    if raw_decimals is None:
        return None
    text = raw_decimals.strip()
    if not text or text.upper() == _DECIMALS_INF:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def canonicalize_numeric(raw: RawFact) -> NumericValue:
    """Canonicalize one raw fact's value, folding scale and sign exactly once.

    * nil → ``value_numeric = None``, ``value_text = None`` (nil ≠ zero).
    * numeric → ``value_numeric = raw_value * 10**scale``, negated iff
      ``sign == "-"``, serialized deterministically; ``value_text = None``.
    * non-numeric (raw value present but not a finite number) → ``value_text``
      carries the raw string; ``value_numeric = None``.

    Raises :class:`CanonicalError` on a numeric fact whose ``scale`` or ``sign``
    cannot be interpreted — we never fabricate a value from a guessed scale/sign.
    """
    decimals = _parse_decimals(raw.decimals)

    if raw.is_nil:
        # nil is an explicit "reported nothing" — never a zero (invariant 25).
        return NumericValue(
            value_numeric_str=None, value_text=None, scale=0, decimals=decimals
        )

    base = raw.value_numeric  # exact Decimal parse of the raw lexical value, or None
    if base is None:
        # Non-numeric concept (or an unparseable numeric lexeme): preserve the
        # raw text as value_text; never invent a number.
        return NumericValue(
            value_numeric_str=None,
            value_text=raw.value_raw,
            scale=0,
            decimals=decimals,
        )

    scale = _parse_scale(raw.scale)
    if scale is None:
        raise CanonicalError(
            f"fact {raw.raw_fact_id} has an uninterpretable scale "
            f"{raw.scale!r}; refusing to fabricate a value"
        )

    if raw.sign is not None and raw.sign not in ("", "-"):
        raise CanonicalError(
            f"fact {raw.raw_fact_id} has an unsupported sign {raw.sign!r}; "
            "refusing to fabricate a value"
        )

    scaled = base * (Decimal(10) ** scale)
    if raw.sign == "-":
        scaled = -scaled

    return NumericValue(
        value_numeric_str=canonical_decimal_str(scaled),
        value_text=None,
        scale=scale,
        decimals=decimals,
    )
