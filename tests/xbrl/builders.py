"""Deterministic in-memory XBRL instance builders for Phase 3 tests.

These assemble the exact bytes of a standard XBRL instance document without any
network access, so parser tests are pure functions of their inputs. The emitted
XML mirrors the real SEC shapes recon documented: an ``{xbrli}xbrl`` root with
namespace declarations, ``<context>`` elements (instant / duration / forever,
with explicit and typed dimensional segments and scenarios), ``<unit>`` elements
(simple and ``divide``), and item facts (numeric, non-numeric, nil).

The builder writes XML text by hand rather than via ElementTree so tests can
exercise byte-exact edge cases (attribute ordering, ``xsi:nil``, custom
prefixes, duplicate ids, malformed structures) that a serializer would hide.

A small set of canonical namespaces is declared by default; extra bindings and
custom issuer prefixes can be added per instance. Everything is deterministic:
no wall-clock, no RNG, stable element order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from quantforge.sec.endpoints import filing_document_url
from quantforge.xbrl.parser import SourceIdentity

# Fixed provenance: none of it influences any derived identity, so the exact
# values are irrelevant to the parsed records — they only prove provenance flows.
FIXED_RETRIEVED_AT = "2026-08-05T00:00:00+00:00"
UA = "QuantForge test@example.com"

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XLINK = "http://www.w3.org/1999/xlink"
LINK = "http://www.xbrl.org/2003/linkbase"
ISO4217 = "http://www.xbrl.org/2003/iso4217"
XBRLI_TYPES = "http://www.xbrl.org/2003/instance"
US_GAAP = "http://fasb.org/us-gaap/2023"
DEI = "http://xbrl.sec.gov/dei/2023"
SRT = "http://fasb.org/srt/2023"

#: Default prefix -> URI bindings present on every built instance.
DEFAULT_NS: dict[str, str] = {
    "xbrli": XBRLI,
    "xbrldi": XBRLDI,
    "xsi": XSI,
    "xlink": XLINK,
    "link": LINK,
    "iso4217": ISO4217,
    "us-gaap": US_GAAP,
    "dei": DEI,
    "srt": SRT,
}


@dataclass
class ExplicitDim:
    """An ``xbrldi:explicitMember`` on a context segment/scenario."""

    axis: str  # prefixed QName, e.g. "srt:ProductOrServiceAxis"
    member: str  # prefixed QName, e.g. "us-gaap:ProductMember"


@dataclass
class TypedDim:
    """An ``xbrldi:typedMember`` carrying a structured child value."""

    axis: str
    child: str  # prefixed child element QName, e.g. "us-gaap:ScheduleItem"
    value: str


@dataclass
class Ctx:
    """One ``<xbrli:context>`` to emit.

    ``instant`` xor (``start`` and ``end``) selects the period type; set
    ``forever=True`` for a ``<forever>`` period. Dimensions in ``segment`` land
    under ``<entity><segment>``; those in ``scenario`` under ``<scenario>``.
    """

    cid: str
    instant: str | None = None
    start: str | None = None
    end: str | None = None
    forever: bool = False
    entity: str = "0000320193"
    scheme: str = "http://www.sec.gov/CIK"
    segment: list[ExplicitDim | TypedDim] = field(default_factory=list)
    scenario: list[ExplicitDim | TypedDim] = field(default_factory=list)


@dataclass
class Unit:
    """One ``<xbrli:unit>`` — a simple measure list or a ``divide`` ratio."""

    uid: str
    measures: list[str] = field(default_factory=list)  # prefixed measure QNames
    numerator: list[str] | None = None
    denominator: list[str] | None = None


@dataclass
class Fact:
    """One item fact element.

    ``value`` is the raw lexical text (``None`` for an empty/nil element).
    ``unit_ref`` names a declared unit for numeric facts. ``nil=True`` emits
    ``xsi:nil="true"``. ``decimals`` / ``scale`` / ``sign`` map to the raw
    attributes.
    """

    concept: str  # prefixed QName, e.g. "us-gaap:Revenues"
    context_ref: str
    value: str | None = None
    unit_ref: str | None = None
    decimals: str | None = None
    scale: str | None = None
    sign: str | None = None
    nil: bool = False


@dataclass
class InstanceBuilder:
    """Assemble a full XBRL instance document as deterministic bytes."""

    contexts: list[Ctx] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    extra_ns: dict[str, str] = field(default_factory=dict)

    def with_context(self, ctx: Ctx) -> InstanceBuilder:
        self.contexts.append(ctx)
        return self

    def with_unit(self, unit: Unit) -> InstanceBuilder:
        self.units.append(unit)
        return self

    def with_unit_from(self, spec: tuple[str, list[str]]) -> InstanceBuilder:
        """Convenience: append a simple ``(unit_id, [measure, ...])`` unit."""
        uid, measures = spec
        self.units.append(Unit(uid, measures=measures))
        return self

    def with_fact(self, fact: Fact) -> InstanceBuilder:
        self.facts.append(fact)
        return self

    def with_ns(self, prefix: str, uri: str) -> InstanceBuilder:
        self.extra_ns[prefix] = uri
        return self

    def _namespaces(self) -> dict[str, str]:
        return {**DEFAULT_NS, **self.extra_ns}

    def _render_member(self, dim: ExplicitDim | TypedDim) -> str:
        if isinstance(dim, ExplicitDim):
            return (
                f'      <xbrldi:explicitMember dimension="{dim.axis}">'
                f"{dim.member}</xbrldi:explicitMember>\n"
            )
        return (
            f'      <xbrldi:typedMember dimension="{dim.axis}">'
            f"<{dim.child}>{dim.value}</{dim.child}>"
            f"</xbrldi:typedMember>\n"
        )

    def _render_context(self, ctx: Ctx) -> str:
        parts = [f'  <xbrli:context id="{ctx.cid}">\n']
        parts.append("    <xbrli:entity>\n")
        parts.append(
            f'      <xbrli:identifier scheme="{ctx.scheme}">'
            f"{ctx.entity}</xbrli:identifier>\n"
        )
        if ctx.segment:
            parts.append("      <xbrli:segment>\n")
            for dim in ctx.segment:
                parts.append("  " + self._render_member(dim))
            parts.append("      </xbrli:segment>\n")
        parts.append("    </xbrli:entity>\n")
        parts.append("    <xbrli:period>\n")
        if ctx.forever:
            parts.append("      <xbrli:forever/>\n")
        elif ctx.instant is not None:
            parts.append(f"      <xbrli:instant>{ctx.instant}</xbrli:instant>\n")
        else:
            parts.append(f"      <xbrli:startDate>{ctx.start}</xbrli:startDate>\n")
            parts.append(f"      <xbrli:endDate>{ctx.end}</xbrli:endDate>\n")
        parts.append("    </xbrli:period>\n")
        if ctx.scenario:
            parts.append("    <xbrli:scenario>\n")
            for dim in ctx.scenario:
                parts.append(self._render_member(dim))
            parts.append("    </xbrli:scenario>\n")
        parts.append("  </xbrli:context>\n")
        return "".join(parts)

    def _render_unit(self, unit: Unit) -> str:
        if unit.numerator is not None or unit.denominator is not None:
            num = "".join(
                f"<xbrli:measure>{m}</xbrli:measure>" for m in (unit.numerator or [])
            )
            den = "".join(
                f"<xbrli:measure>{m}</xbrli:measure>" for m in (unit.denominator or [])
            )
            return (
                f'  <xbrli:unit id="{unit.uid}">\n'
                f"    <xbrli:divide>\n"
                f"      <xbrli:unitNumerator>{num}</xbrli:unitNumerator>\n"
                f"      <xbrli:unitDenominator>{den}</xbrli:unitDenominator>\n"
                f"    </xbrli:divide>\n"
                f"  </xbrli:unit>\n"
            )
        measures = "".join(
            f"    <xbrli:measure>{m}</xbrli:measure>\n" for m in unit.measures
        )
        return f'  <xbrli:unit id="{unit.uid}">\n{measures}  </xbrli:unit>\n'

    def _render_fact(self, fact: Fact) -> str:
        attrs = [f'contextRef="{fact.context_ref}"']
        if fact.unit_ref is not None:
            attrs.append(f'unitRef="{fact.unit_ref}"')
        if fact.decimals is not None:
            attrs.append(f'decimals="{fact.decimals}"')
        if fact.scale is not None:
            attrs.append(f'scale="{fact.scale}"')
        if fact.sign is not None:
            attrs.append(f'sign="{fact.sign}"')
        if fact.nil:
            attrs.append('xsi:nil="true"')
        attr_str = " ".join(attrs)
        if fact.nil or fact.value is None:
            return f"  <{fact.concept} {attr_str}/>\n"
        return f"  <{fact.concept} {attr_str}>{fact.value}</{fact.concept}>\n"

    def to_xml(self) -> str:
        ns_decls = " ".join(
            f'xmlns:{prefix}="{uri}"'
            for prefix, uri in sorted(self._namespaces().items())
        )
        body = ['<?xml version="1.0" encoding="UTF-8"?>\n']
        body.append(f"<xbrli:xbrl {ns_decls}>\n")
        for ctx in self.contexts:
            body.append(self._render_context(ctx))
        for unit in self.units:
            body.append(self._render_unit(unit))
        for fact in self.facts:
            body.append(self._render_fact(fact))
        body.append("</xbrli:xbrl>\n")
        return "".join(body)

    def to_bytes(self) -> bytes:
        return self.to_xml().encode("utf-8")


def source_identity(
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    filename: str = "aapl-20230930_htm.xml",
    data: bytes | None = None,
) -> SourceIdentity:
    """Build a :class:`SourceIdentity` mirroring what the ingest façade derives."""
    from quantforge.registry.identity import company_id, filing_id

    url = filing_document_url(cik, accession, filename)
    payload = data if data is not None else b""
    return SourceIdentity(
        filing_id=filing_id(accession),
        accession=accession,
        company_id=company_id(cik),
        source_artifact_sha256=sha256_hex(payload),
        source_url=url,
        source_document_name=filename,
        source_artifact_type=ArtifactType.XBRL_INSTANCE,
    )


def instance_artifact(
    data: bytes,
    *,
    cik: int = 320193,
    accession: str = "0000320193-23-000106",
    filename: str = "aapl-20230930_htm.xml",
) -> Artifact:
    """Wrap instance bytes as a Phase 1 :class:`Artifact` for ingest tests."""
    url = filing_document_url(cik, accession, filename)
    meta = AcquisitionMetadata(
        source_url=url,
        artifact_type=ArtifactType.XBRL_INSTANCE,
        sha256=sha256_hex(data),
        retrieved_at=FIXED_RETRIEVED_AT,
        http_status=200,
        user_agent=UA,
        content_type="application/xml",
        content_length=len(data),
        cik=str(cik),
        accession=accession,
    )
    return Artifact(data, meta)
