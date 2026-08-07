"""The canonical :class:`Fact` model, its identity, and its provenance.

A :class:`Fact` is **one observation of one concept, for one period, in one
dimensional context, as asserted by one filing** (data-model §3). It is derived
from one or more :class:`~quantforge.xbrl.model.RawFact` records by the Phase 4
normalizer, and it retains complete lineage back to the raw source (requirement
1: *do not throw away raw information during canonicalization*).

Two identity functions live here, both following data-model §11 exactly:

* :func:`obs_key` — the **observation key** (§6.2): the tuple that decides when
  two observations describe "the same thing." Critically, it uses the *fully
  qualified concept* (Clark notation, prefix-independent) and the *raw structural
  unit ref* — never the coarse taxonomy label or the derived canonical unit token
  — so two issuer extensions sharing a local name never collide, and two units
  that both canonicalize to ``UNKNOWN`` never merge (requirement 15 cases 6/8/13).
* :func:`fact_id` — ``sha256(transformation_version_id, filing_id, obs_key)``.
  It **includes the transformation version** (so re-normalization yields a new,
  distinct Fact while the old one is retained — requirement 11) and **excludes
  ``raw_fact_id``** (so a genuine duplicate raw fact collapses to one Fact —
  §11, §13 case 8). Identity depends on no ticker, name, retrieval time, wall
  clock, random value, or mutable normalized value (requirement 12, invariant 18).

What deliberately does **not** live on the Fact in Phase 4 (documented in
``docs/canonicalization.md``, not a contradiction with §3.1):

* ``fiscal_year`` / ``fiscal_quarter`` — the *filing's* document focus, reporting
  metadata that is not per-observation truth (requirement 4); deferred.
* ``security_id`` — requires an external security master absent from EDGAR (recon
  §Company≠Security); we fail closed to ``None`` rather than guess.
* the three availability fields (``derived_public_availability_timestamp``,
  ``availability_status``, ``availability_policy_id``) — Phase 5+ point-in-time
  concerns that §22 explicitly forbids computing here.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.canonical.concept import Concept
from quantforge.canonical.taxonomy import Taxonomy
from quantforge.sec.artifacts import sha256_hex
from quantforge.xbrl.contexts import PeriodType

__all__ = [
    "CanonicalDimension",
    "Fact",
    "FactProvenance",
    "fact_id",
    "obs_key",
]

# A separator that cannot occur in any obs_key component (Qnames, dates, hashes,
# ids are all printable and NUL-free), so the joined key is unambiguous.
_SEP = "\x00"


def obs_key(
    *,
    company_id: str,
    security_id: str | None,
    concept_clark: str,
    period_type: str,
    period_start: str | None,
    period_end: str | None,
    unit_ref: str,
    dimensions_hash: str,
) -> str:
    """Return the canonical observation key string (data-model §6.2).

    ``obs_key = (company_id, security_id, taxonomy, concept, period_type,
    period_start, period_end, unit, dimensions_hash)``. Here:

    * **concept** is the fully-qualified Clark notation, which *subsumes* the
      taxonomy label — using the coarse ``taxonomy`` enum instead would let two
      distinct issuer concepts sharing a local name collide, so the qualified
      concept is authoritative (requirement 2, 15 case 8);
    * **unit** is the *raw structural* ``unit_ref`` (measure QNames + role), not
      the derived canonical token — so two different units that both canonicalize
      to ``UNKNOWN`` never merge (requirement 6, 15 cases 6 & 13).

    Order-independence is not needed (the fields are positional); determinism is
    guaranteed by the fixed field order and the NUL join.
    """
    parts = (
        company_id,
        security_id or "",
        concept_clark,
        period_type,
        period_start or "",
        period_end or "",
        unit_ref,
        dimensions_hash,
    )
    return _SEP.join(parts)


def fact_id(
    *,
    transformation_version_id: str,
    filing_id: str,
    obs_key_value: str,
) -> str:
    """Compute the deterministic canonical ``fact_id`` (data-model §11).

    ``sha256(transformation_version_id, filing_id, obs_key)``, NUL-joined.
    Includes the transformation version (re-normalization ⇒ a new distinct Fact,
    old retained — requirement 11) and excludes ``raw_fact_id`` (duplicate raw
    facts collapse to one Fact — §13 case 8). Depends on nothing mutable
    (requirement 12, invariant 18).
    """
    payload = _SEP.join((transformation_version_id, filing_id, obs_key_value))
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


@dataclass(frozen=True, slots=True)
class CanonicalDimension:
    """One explicit or typed dimension on a Fact, preserved losslessly (req. 5).

    Mirrors the Phase 3 :class:`~quantforge.xbrl.dimensions.RawDimension` shape so
    a segmented fact never collides with the consolidated fact and the dimensional
    detail companyfacts discards is retained. ``axis``/``member``/``typed_child``
    are Clark-notation QNames.
    """

    axis: str
    member: str | None
    is_typed: bool
    typed_child: str | None
    typed_text: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis,
            "member": self.member,
            "is_typed": self.is_typed,
            "typed_child": self.typed_child,
            "typed_text": self.typed_text,
        }


@dataclass(frozen=True, slots=True)
class FactProvenance:
    """Complete lineage from a canonical Fact back to the SEC source (req. 13).

    The unbroken chain (data-model §5): Fact → ``raw_fact_id`` (the exact
    pre-normalization observation) → ``raw_document_id`` (the parsed instance) →
    ``source_artifact_sha256`` (the immutable Phase 1 blob) → ``source_url`` (the
    SEC URL) → ``filing_id``/``accession``/``company_id`` (Phase 2 identity). The
    normalizer ``transformation_version_id`` records which code+config produced
    the Fact. ``raw_fact_ids`` lists *every* raw fact that reduced to this Fact
    (the canonical representative first), so a collapsed duplicate is still
    traceable (§4 cardinality).
    """

    #: The canonical representative raw fact (lowest ordinal) this Fact derives
    #: from — the §3.1 ``raw_fact_id`` FK.
    raw_fact_id: str
    #: Every raw fact that reduced to this Fact, sorted; includes ``raw_fact_id``.
    raw_fact_ids: tuple[str, ...]
    raw_document_id: str
    filing_id: str
    accession: str
    company_id: str
    source_artifact_sha256: str
    source_url: str
    source_document_name: str | None
    transformation_version_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_fact_id": self.raw_fact_id,
            "raw_fact_ids": list(self.raw_fact_ids),
            "raw_document_id": self.raw_document_id,
            "filing_id": self.filing_id,
            "accession": self.accession,
            "company_id": self.company_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_url": self.source_url,
            "source_document_name": self.source_document_name,
            "transformation_version_id": self.transformation_version_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FactProvenance:
        return cls(
            raw_fact_id=_req_str(raw, "raw_fact_id"),
            raw_fact_ids=_str_tuple(raw, "raw_fact_ids"),
            raw_document_id=_req_str(raw, "raw_document_id"),
            filing_id=_req_str(raw, "filing_id"),
            accession=_req_str(raw, "accession"),
            company_id=_req_str(raw, "company_id"),
            source_artifact_sha256=_req_str(raw, "source_artifact_sha256"),
            source_url=_req_str(raw, "source_url"),
            source_document_name=_opt_str(raw, "source_document_name"),
            transformation_version_id=_req_str(raw, "transformation_version_id"),
        )


@dataclass(frozen=True, slots=True)
class Fact:
    """One canonical financial observation, with complete lineage (data-model §3).

    Every raw distinction that could separate two observations is preserved:
    the fully-qualified concept, the period, the raw structural unit ref, and the
    dimensional segment (via ``dimensions``/``dimensions_hash``). The canonical
    ``value_numeric`` is in base units (scale & sign folded exactly once) while
    the raw lexical value, raw scale, raw sign, and raw decimals survive verbatim
    for audit (invariant 26). Identity (``fact_id``) is deterministic (§11).
    """

    fact_id: str
    obs_key: str
    company_id: str
    security_id: str | None
    concept: Concept
    taxonomy: Taxonomy
    period_type: PeriodType
    period_start: str | None
    period_end: str | None
    # Canonical numeric outcome (base units) + non-numeric text; nil ≠ zero.
    value_numeric_str: str | None
    value_text: str | None
    is_nil: bool
    # Unit: canonical label + currency, backed by the raw structural ref/measures.
    unit: str
    currency: str | None
    unit_ref: str
    unit_numerator: tuple[str, ...]
    unit_denominator: tuple[str, ...]
    unit_is_divide: bool
    # Precision/scale metadata: canonical folded scale + parsed decimals, plus the
    # raw lexical value/scale/sign/decimals retained verbatim (invariant 26).
    scale: int
    decimals: int | None
    raw_value: str | None
    raw_scale: str | None
    raw_sign: str | None
    raw_decimals: str | None
    # Dimensional segment (preserved; companyfacts loses this).
    dimensions: tuple[CanonicalDimension, ...]
    dimensions_hash: str
    # Lineage.
    filing_id: str
    transformation_version_id: str
    provenance: FactProvenance

    def to_dict(self) -> dict[str, object]:
        """Deterministic serialization (no wall-clock, no ordering surprises)."""
        return {
            "fact_id": self.fact_id,
            "obs_key": self.obs_key,
            "company_id": self.company_id,
            "security_id": self.security_id,
            "concept": self.concept.to_dict(),
            "taxonomy": self.taxonomy.value,
            "period_type": self.period_type.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "value_numeric": self.value_numeric_str,
            "value_text": self.value_text,
            "is_nil": self.is_nil,
            "unit": self.unit,
            "currency": self.currency,
            "unit_ref": self.unit_ref,
            "unit_numerator": list(self.unit_numerator),
            "unit_denominator": list(self.unit_denominator),
            "unit_is_divide": self.unit_is_divide,
            "scale": self.scale,
            "decimals": self.decimals,
            "raw_value": self.raw_value,
            "raw_scale": self.raw_scale,
            "raw_sign": self.raw_sign,
            "raw_decimals": self.raw_decimals,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "dimensions_hash": self.dimensions_hash,
            "filing_id": self.filing_id,
            "transformation_version_id": self.transformation_version_id,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Fact:
        from quantforge.canonical.concept import Concept as _Concept

        concept_raw = raw["concept"]
        if not isinstance(concept_raw, dict):
            raise ValueError("concept must be an object")
        provenance_raw = raw["provenance"]
        if not isinstance(provenance_raw, dict):
            raise ValueError("provenance must be an object")
        return cls(
            fact_id=_req_str(raw, "fact_id"),
            obs_key=_req_str(raw, "obs_key"),
            company_id=_req_str(raw, "company_id"),
            security_id=_opt_str(raw, "security_id"),
            concept=_Concept(
                clark=_req_str(concept_raw, "clark"),
                namespace_uri=_opt_str(concept_raw, "namespace_uri"),
                local_name=_req_str(concept_raw, "local_name"),
                taxonomy=Taxonomy(_req_str(concept_raw, "taxonomy")),
            ),
            taxonomy=Taxonomy(_req_str(raw, "taxonomy")),
            period_type=PeriodType(_req_str(raw, "period_type")),
            period_start=_opt_str(raw, "period_start"),
            period_end=_opt_str(raw, "period_end"),
            value_numeric_str=_opt_str(raw, "value_numeric"),
            value_text=_opt_str(raw, "value_text"),
            is_nil=bool(raw.get("is_nil", False)),
            unit=_req_str(raw, "unit"),
            currency=_opt_str(raw, "currency"),
            unit_ref=_req_str(raw, "unit_ref"),
            unit_numerator=_str_tuple(raw, "unit_numerator"),
            unit_denominator=_str_tuple(raw, "unit_denominator"),
            unit_is_divide=bool(raw.get("unit_is_divide", False)),
            scale=_req_int(raw, "scale"),
            decimals=_opt_int(raw, "decimals"),
            raw_value=_opt_str(raw, "raw_value"),
            raw_scale=_opt_str(raw, "raw_scale"),
            raw_sign=_opt_str(raw, "raw_sign"),
            raw_decimals=_opt_str(raw, "raw_decimals"),
            dimensions=tuple(
                CanonicalDimension(
                    axis=_req_str(d, "axis"),
                    member=_opt_str(d, "member"),
                    is_typed=bool(d.get("is_typed", False)),
                    typed_child=_opt_str(d, "typed_child"),
                    typed_text=_opt_str(d, "typed_text"),
                )
                for d in _dim_list(raw)
            ),
            dimensions_hash=_req_str(raw, "dimensions_hash"),
            filing_id=_req_str(raw, "filing_id"),
            transformation_version_id=_req_str(raw, "transformation_version_id"),
            provenance=FactProvenance.from_dict(provenance_raw),
        )


def _dim_list(raw: dict[str, object]) -> list[dict[str, object]]:
    value = raw.get("dimensions", [])
    if not isinstance(value, list):
        return []
    return [d for d in value if isinstance(d, dict)]


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _req_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an int")
    return value


def _opt_int(raw: dict[str, object], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an int or null")
    return value


def _str_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(value)
