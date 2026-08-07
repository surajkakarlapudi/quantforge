"""The raw XBRL fact model — immutable observations and their provenance.

These are the *raw* records Phase 3 derives from the exact XBRL instance bytes
acquired by Phase 1. They follow ``docs/data-model.md`` — the **RawDocument** and
**RawFact** entities (§4), their identifiers (§11), and the loss-preserving
invariants (§12, esp. 18, 25, 26). They hold the observation **exactly as
parsed, before any normalization** (requirement 6): raw unit structure, raw
scale/decimals, raw context ref, raw lexical value.

Design commitments encoded here (each traceable to a requirement / invariant):

* **RawDocument identity = content (§11).** ``raw_document_id`` is
  ``sha256:<hex>`` of the exact source bytes; identical bytes are the same
  document. The bytes themselves are never stored here — they live untouched in
  the Phase 1 content-addressed store (requirement 2, 16) — only the content
  address and provenance are recorded.
* **RawFact identity is content-derived and version-independent (§11).**
  ``raw_fact_id = sha256(raw_document_id, xbrl_context_ref, concept, unit_ref,
  segment_key, ordinal)``. It deliberately excludes the parser version and every
  mutable/normalized value (requirement 6, 13): re-parsing identical bytes with
  any parser version reproduces the same raw ids.
* **Complete provenance (requirement 7).** Every :class:`RawFact` carries a
  :class:`RawFactProvenance` tracing it to ``filing_id``, ``accession``, the
  source artifact content hash, the source document, the XBRL concept/context,
  and the parser version.
* **nil ≠ zero (requirement 10, invariant 25).** ``is_nil`` is a first-class
  flag; a nil fact has ``value_raw = None`` and ``value_numeric = None`` and is
  never coerced to ``0``. A concept simply *absent* produces no RawFact at all.
* **Loss-preserving (requirement 11, invariant 26).** ``value_raw``,
  ``unit_ref``/:class:`RawUnit`, ``scale``, ``decimals``, and ``sign`` are all
  retained so any later normalization is re-derivable and auditable. Numeric
  parsing is best-effort and non-destructive: ``value_numeric`` is populated only
  when the raw lexical value parses safely, and the raw string always survives.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from quantforge.sec.artifacts import ArtifactType, sha256_hex

__all__ = [
    "RawDocument",
    "RawFact",
    "RawFactProvenance",
    "parse_numeric",
    "raw_document_id_for_bytes",
    "raw_fact_id",
]


def raw_document_id_for_bytes(data: bytes) -> str:
    """Return the content-addressed ``raw_document_id`` for exact bytes (§11)."""
    return f"sha256:{sha256_hex(data)}"


def raw_fact_id(
    *,
    raw_document_id: str,
    xbrl_context_ref: str,
    concept: str,
    unit_ref: str,
    segment_key: str,
    ordinal: int,
) -> str:
    """Compute the deterministic ``raw_fact_id`` (data-model §11).

    ``sha256`` of ``(raw_document_id, xbrl_context_ref, concept, unit_ref,
    segment_key, ordinal)``, joined by a NUL separator that cannot occur in any
    component. Excludes the parser version and every normalized value, so
    re-parsing the same bytes always reproduces the id (invariant 18). The
    ``ordinal`` disambiguates genuine duplicate observations that are otherwise
    identical (data-model §13 case 8), so no fact is ever silently dropped.
    """
    payload = "\x00".join(
        (
            raw_document_id,
            xbrl_context_ref,
            concept,
            unit_ref,
            segment_key,
            str(ordinal),
        )
    )
    return f"sha256:{sha256_hex(payload.encode('utf-8'))}"


def parse_numeric(value_raw: str | None) -> Decimal | None:
    """Best-effort, non-destructive numeric parse of a raw lexical value.

    Returns a :class:`~decimal.Decimal` when ``value_raw`` is a value that parses
    exactly and safely, else ``None`` — the raw string is always preserved
    separately, so a ``None`` here never loses information (requirement 3, 11).
    ``Decimal`` is used rather than ``float`` to avoid binary-rounding drift; no
    scale is applied and no precision metadata is consumed (requirement 5 — no
    normalization). A nil or absent value yields ``None`` (nil ≠ zero).
    """
    if value_raw is None:
        return None
    text = value_raw.strip()
    if not text:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    # Reject non-finite lexical inputs (NaN/Infinity): they are not XBRL numeric
    # values and must never masquerade as a parsed magnitude. Fail closed to
    # ``None`` and keep the raw string.
    if not result.is_finite():
        return None
    return result


@dataclass(frozen=True, slots=True)
class RawFactProvenance:
    """Complete provenance for one :class:`RawFact` (requirement 7).

    Traces a raw fact back to the filing that asserted it, the immutable source
    artifact it was parsed from (by content hash and type), the source document
    identity, and the parser version that performed the extraction. Nothing here
    is part of ``raw_fact_id`` (that is pure content); this is the audit trail.
    """

    filing_id: str
    accession: str
    company_id: str
    source_artifact_sha256: str
    source_artifact_type: ArtifactType
    source_url: str
    source_document_name: str | None
    transformation_version_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "filing_id": self.filing_id,
            "accession": self.accession,
            "company_id": self.company_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_artifact_type": self.source_artifact_type.value,
            "source_url": self.source_url,
            "source_document_name": self.source_document_name,
            "transformation_version_id": self.transformation_version_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawFactProvenance:
        return cls(
            filing_id=_req_str(raw, "filing_id"),
            accession=_req_str(raw, "accession"),
            company_id=_req_str(raw, "company_id"),
            source_artifact_sha256=_req_str(raw, "source_artifact_sha256"),
            source_artifact_type=ArtifactType(_req_str(raw, "source_artifact_type")),
            source_url=_req_str(raw, "source_url"),
            source_document_name=_opt_str(raw, "source_document_name"),
            transformation_version_id=_req_str(raw, "transformation_version_id"),
        )


@dataclass(frozen=True, slots=True)
class RawDocument:
    """The immutable XBRL instance bytes a set of RawFacts were parsed from.

    Content-addressed (``raw_document_id = sha256:<hex>`` of the exact bytes,
    §11). The bytes are **not** duplicated here: they remain in the Phase 1
    content-addressed store, recoverable by ``source_artifact_sha256`` — this
    record is the parsed document's identity and provenance, never a second copy
    of the source (requirements 2, 16).
    """

    raw_document_id: str
    filing_id: str
    accession: str
    company_id: str
    source_artifact_sha256: str
    source_artifact_type: ArtifactType
    source_url: str
    source_document_name: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_document_id": self.raw_document_id,
            "filing_id": self.filing_id,
            "accession": self.accession,
            "company_id": self.company_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_artifact_type": self.source_artifact_type.value,
            "source_url": self.source_url,
            "source_document_name": self.source_document_name,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawDocument:
        return cls(
            raw_document_id=_req_str(raw, "raw_document_id"),
            filing_id=_req_str(raw, "filing_id"),
            accession=_req_str(raw, "accession"),
            company_id=_req_str(raw, "company_id"),
            source_artifact_sha256=_req_str(raw, "source_artifact_sha256"),
            source_artifact_type=ArtifactType(_req_str(raw, "source_artifact_type")),
            source_url=_req_str(raw, "source_url"),
            source_document_name=_opt_str(raw, "source_document_name"),
        )


@dataclass(frozen=True, slots=True)
class RawFact:
    """One XBRL fact, exactly as parsed — pre-normalization (data-model §4).

    Identity (``raw_fact_id``) is a pure function of source content (§11); every
    other field is the raw observation, preserved losslessly (invariant 26).

    Attributes
    ----------
    raw_fact_id:
        Deterministic content hash (§11); independent of parser version and of
        every normalized value.
    raw_document_id:
        The :class:`RawDocument` these bytes were parsed from.
    concept:
        The reported concept QName in stable Clark notation (namespace-resolved),
        covering ``us-gaap``/``dei``/``srt`` and custom ``<issuer>:*`` concepts
        identically (requirement 3).
    context_ref:
        The document-local ``contextRef`` the fact carried (``xbrl_context_ref``
        in §11), preserved verbatim.
    unit_ref:
        The stable structural unit identity (from :class:`RawUnit`), or ``""``
        for a non-numeric fact with no unit. Part of ``raw_fact_id``.
    dimensions_hash:
        The deterministic hash of the fact's context's dimensional segment,
        denormalized here so a fact's dimensional identity is self-contained.
    ordinal:
        A stable, deterministic disambiguator among facts that are otherwise
        identical in ``(context_ref, concept, unit_ref, dimensions)`` within one
        document (data-model §13 case 8) — assigned in document order.
    value_raw:
        The exact lexical value as it appeared in the instance. ``None`` for a
        nil fact (nil ≠ zero — invariant 25).
    value_numeric:
        A best-effort :class:`~decimal.Decimal` parse of ``value_raw`` as a
        string, populated only when it parses safely; ``None`` otherwise and for
        nil facts. Never a substitute for ``value_raw``.
    is_nil:
        Whether the fact carried ``xsi:nil="true"`` — a first-class "reported
        nothing" observation (requirement 10, invariant 25).
    decimals / scale:
        The XBRL ``decimals`` and ``scale`` attributes exactly as supplied
        (strings, since ``decimals`` may be ``INF``); precision metadata is never
        discarded (requirement 11).
    sign:
        The ``sign`` attribute exactly as supplied (``"-"`` when present), so a
        negated fact is auditable without mutating ``value_raw`` (requirement 3).
    provenance:
        Complete provenance back to the filing and source artifact.
    """

    raw_fact_id: str
    raw_document_id: str
    concept: str
    context_ref: str
    unit_ref: str
    dimensions_hash: str
    ordinal: int
    value_raw: str | None
    value_numeric_str: str | None
    is_nil: bool
    decimals: str | None
    scale: str | None
    sign: str | None
    provenance: RawFactProvenance

    @property
    def value_numeric(self) -> Decimal | None:
        """The parsed numeric value as a :class:`~decimal.Decimal`, or ``None``.

        Reconstructed from the stored lexical ``value_numeric_str`` (kept as a
        string so serialization is exact and deterministic).
        """
        if self.value_numeric_str is None:
            return None
        return Decimal(self.value_numeric_str)

    def to_dict(self) -> dict[str, object]:
        """Deterministic serialization (no wall-clock, no ordering surprises)."""
        return {
            "raw_fact_id": self.raw_fact_id,
            "raw_document_id": self.raw_document_id,
            "concept": self.concept,
            "context_ref": self.context_ref,
            "unit_ref": self.unit_ref,
            "dimensions_hash": self.dimensions_hash,
            "ordinal": self.ordinal,
            "value_raw": self.value_raw,
            "value_numeric": self.value_numeric_str,
            "is_nil": self.is_nil,
            "decimals": self.decimals,
            "scale": self.scale,
            "sign": self.sign,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> RawFact:
        provenance_raw = raw["provenance"]
        if not isinstance(provenance_raw, dict):
            raise ValueError("provenance must be an object")
        ordinal = raw["ordinal"]
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise ValueError("ordinal must be an int")
        return cls(
            raw_fact_id=_req_str(raw, "raw_fact_id"),
            raw_document_id=_req_str(raw, "raw_document_id"),
            concept=_req_str(raw, "concept"),
            context_ref=_req_str(raw, "context_ref"),
            unit_ref=_req_str(raw, "unit_ref"),
            dimensions_hash=_req_str(raw, "dimensions_hash"),
            ordinal=ordinal,
            value_raw=_opt_str(raw, "value_raw"),
            value_numeric_str=_opt_str(raw, "value_numeric"),
            is_nil=bool(raw.get("is_nil", False)),
            decimals=_opt_str(raw, "decimals"),
            scale=_opt_str(raw, "scale"),
            sign=_opt_str(raw, "sign"),
            provenance=RawFactProvenance.from_dict(provenance_raw),
        )


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
