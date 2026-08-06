"""The XBRL instance parser — bytes ⇒ immutable RawDocument + RawFacts.

This is the heart of Phase 3. It parses a **standard XBRL instance document**
(the ``.xml`` instance in pre-inline filings, and the SEC-extracted ``*_htm.xml``
instance in inline/iXBRL-era filings — both parse to the same fact model, recon
§15.10) into the raw records defined in :mod:`openfinance.xbrl.model`.

What it does, and just as importantly what it does **not** do:

* It **preserves the source bytes exactly** — the parser receives bytes it never
  mutates, and the immutable copy lives in the Phase 1 store (requirement 2).
* It extracts facts, contexts, units, dimensions, namespaces, concepts,
  decimals, scale, sign, nil status, the raw lexical value, a best-effort numeric
  value, and full provenance (requirement 3).
* It performs **no semantic normalization** (requirement 5): units are not
  converted or mapped, concepts are not merged or rewritten, competing
  observations are not resolved, nil is never turned into zero.
* It **fails closed** on malformed or structurally unsound input (requirement
  12): a fact referencing a missing context/unit, a duplicate context/unit id,
  a context with no period, non-well-formed XML, or a document that is not an
  XBRL instance all raise rather than yield an invented value.
* It is **deterministic** (requirement 13, invariant 18): identity, ordering,
  and serialization are pure functions of the bytes; no wall-clock, RNG, or
  input-order dependence enters any id.

Modularity (requirement 15): namespace resolution (:mod:`.qnames`), dimension
handling (:mod:`.dimensions`), unit representation (:mod:`.units`), context
representation (:mod:`.contexts`), and raw-fact representation (:mod:`.model`)
are separate modules; this file owns element-level extraction, split into
``_extract_contexts`` / ``_extract_units`` / ``_extract_facts`` /
``_extract_dimensions``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO

from openfinance.sec.artifacts import ArtifactType
from openfinance.xbrl.contexts import PeriodType, RawContext
from openfinance.xbrl.dimensions import RawDimension
from openfinance.xbrl.errors import MalformedXbrlError, UnsupportedXbrlError
from openfinance.xbrl.model import (
    RawDocument,
    RawFact,
    RawFactProvenance,
    parse_numeric,
    raw_document_id_for_bytes,
    raw_fact_id,
)
from openfinance.xbrl.namespaces import XBRLDI_NS, XBRLI_NS, XSI_NS
from openfinance.xbrl.qnames import NamespaceContext, QName
from openfinance.xbrl.units import RawUnit
from openfinance.xbrl.version import XbrlParserVersion

__all__ = ["ParsedInstance", "SourceIdentity", "parse_instance"]


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """The filing/artifact identity a parse is attributed to (provenance).

    Supplied by the caller (the ingestion façade, from the Phase 2 registry and
    Phase 1 metadata) — the parser never guesses a filing or company from the
    bytes. All fields flow verbatim into :class:`RawDocument`/:class:`RawFact`
    provenance (requirement 7).
    """

    filing_id: str
    accession: str
    company_id: str
    source_artifact_sha256: str
    source_url: str
    source_document_name: str | None = None
    source_artifact_type: ArtifactType = ArtifactType.XBRL_INSTANCE


@dataclass(frozen=True, slots=True)
class ParsedInstance:
    """The full deterministic result of parsing one XBRL instance.

    Contexts and units are keyed by their document-local id and are retained in
    full (not just those referenced by a fact) so the raw structure is
    recoverable. Facts are emitted in document order with deterministic ordinals.
    """

    document: RawDocument
    contexts: dict[str, RawContext]
    units: dict[str, RawUnit]
    facts: tuple[RawFact, ...]


def parse_instance(
    data: bytes,
    identity: SourceIdentity,
    version: XbrlParserVersion | None = None,
) -> ParsedInstance:
    """Parse exact XBRL instance ``data`` into an immutable :class:`ParsedInstance`.

    ``data`` must be the exact bytes as acquired (the caller reads them from the
    Phase 1 store; they are never rewritten). ``identity`` supplies provenance.
    Raises :class:`MalformedXbrlError` / :class:`UnsupportedXbrlError` on input
    that cannot be parsed without fabricating financial data (requirement 12).
    """
    version = version or XbrlParserVersion()
    _reject_doctype(data)
    ns_context, root = _load_tree(data)
    _require_xbrl_root(root)

    raw_document_id = raw_document_id_for_bytes(data)
    document = RawDocument(
        raw_document_id=raw_document_id,
        filing_id=identity.filing_id,
        accession=identity.accession,
        company_id=identity.company_id,
        source_artifact_sha256=identity.source_artifact_sha256,
        source_artifact_type=identity.source_artifact_type,
        source_url=identity.source_url,
        source_document_name=identity.source_document_name,
    )

    contexts = _extract_contexts(root, ns_context)
    units = _extract_units(root, ns_context)
    facts = _extract_facts(
        root, ns_context, contexts, units, raw_document_id, identity, version
    )
    return ParsedInstance(
        document=document, contexts=contexts, units=units, facts=facts
    )


# -- XML loading & structural guards ------------------------------------------


def _reject_doctype(data: bytes) -> None:
    """Fail closed on any DOCTYPE declaration (entity-expansion defense).

    A valid XBRL instance never carries a DTD. ``xml.etree.ElementTree`` expands
    internal general entities, which is the "billion laughs" / quadratic-blowup
    denial-of-service vector for hostile input. Rejecting a DOCTYPE outright
    closes that vector without a custom parser and never rejects legitimate SEC
    data (a security consideration documented in ``docs/xbrl-ingestion.md``).
    """
    # DOCTYPE can only legally appear in the prolog; scanning the whole document
    # is a conservative superset that cannot false-negative.
    if b"<!DOCTYPE" in data or b"<!doctype" in data:
        raise UnsupportedXbrlError(
            "XBRL instance carries a DOCTYPE/DTD; refused (entity-expansion "
            "safety, and valid instances have no DTD)"
        )


def _load_tree(data: bytes) -> tuple[NamespaceContext, ET.Element]:
    """Parse bytes into (namespace context, root element), failing closed.

    Namespace bindings are collected from ``start-ns`` events so QName *values*
    (dimension axes/members) resolve to stable, prefix-independent Clark
    notation. A prefix rebound to a different URI is refused by
    :class:`NamespaceContext` (ambiguous global resolution).
    """
    ns_context = NamespaceContext({})
    root: ET.Element | None = None
    try:
        for event, obj in ET.iterparse(BytesIO(data), events=("start-ns", "start")):
            if event == "start-ns":
                prefix, uri = obj
                ns_context.add(prefix, uri)
            elif event == "start" and root is None:
                # iterparse mutates this element in place as parsing proceeds,
                # so by loop end it is the fully-populated document root.
                root = obj
    except ET.ParseError as exc:
        raise MalformedXbrlError(f"not well-formed XML: {exc}") from exc
    if root is None:
        raise MalformedXbrlError("empty document: no root element")
    return ns_context, root


def _require_xbrl_root(root: ET.Element) -> None:
    """Require the document root to be ``{xbrli}xbrl`` — else it is not an instance."""
    if root.tag != f"{{{XBRLI_NS}}}xbrl":
        raise MalformedXbrlError(
            f"root element is {root.tag!r}, not an XBRL instance ({{{XBRLI_NS}}}xbrl)"
        )


# -- context extraction -------------------------------------------------------


def _extract_contexts(root: ET.Element, ns: NamespaceContext) -> dict[str, RawContext]:
    """Extract every ``<xbrli:context>`` into a :class:`RawContext` by id.

    A duplicate context id is a malformed document (facts could not
    unambiguously reference a context) → fail closed. A context missing its
    period or entity is likewise malformed.
    """
    contexts: dict[str, RawContext] = {}
    for elem in root.findall(f"{{{XBRLI_NS}}}context"):
        context_id = elem.get("id")
        if not context_id:
            raise MalformedXbrlError("context element missing 'id'")
        if context_id in contexts:
            raise MalformedXbrlError(f"duplicate context id {context_id!r}")
        contexts[context_id] = _build_context(context_id, elem, ns)
    return contexts


def _build_context(
    context_id: str, elem: ET.Element, ns: NamespaceContext
) -> RawContext:
    entity = elem.find(f"{{{XBRLI_NS}}}entity")
    if entity is None:
        raise MalformedXbrlError(f"context {context_id!r} has no <entity>")
    identifier = entity.find(f"{{{XBRLI_NS}}}identifier")
    if identifier is None or identifier.text is None:
        raise MalformedXbrlError(f"context {context_id!r} entity has no <identifier>")
    scheme = identifier.get("scheme")
    if not scheme:
        raise MalformedXbrlError(f"context {context_id!r} identifier has no 'scheme'")

    period_type, instant, start, end = _extract_period(context_id, elem)
    dimensions = _extract_dimensions(elem, entity, ns)

    return RawContext(
        context_ref=context_id,
        entity_identifier=identifier.text.strip(),
        entity_scheme=scheme,
        period_type=period_type,
        instant=instant,
        start=start,
        end=end,
        dimensions=dimensions,
    )


def _extract_period(
    context_id: str, elem: ET.Element
) -> tuple[PeriodType, str | None, str | None, str | None]:
    """Extract the context's period, preserving instant vs duration exactly."""
    period = elem.find(f"{{{XBRLI_NS}}}period")
    if period is None:
        raise MalformedXbrlError(f"context {context_id!r} has no <period>")

    instant_el = period.find(f"{{{XBRLI_NS}}}instant")
    if instant_el is not None:
        return PeriodType.INSTANT, _text(instant_el), None, None

    start_el = period.find(f"{{{XBRLI_NS}}}startDate")
    end_el = period.find(f"{{{XBRLI_NS}}}endDate")
    if start_el is not None and end_el is not None:
        return (
            PeriodType.DURATION,
            None,
            _text(start_el),
            _text(end_el),
        )

    if period.find(f"{{{XBRLI_NS}}}forever") is not None:
        return PeriodType.FOREVER, None, None, None

    raise MalformedXbrlError(
        f"context {context_id!r} period is neither instant, duration, nor forever"
    )


# -- dimension handling -------------------------------------------------------


def _extract_dimensions(
    context: ET.Element, entity: ET.Element, ns: NamespaceContext
) -> tuple[RawDimension, ...]:
    """Extract explicit + typed dimensions from a context's segment/scenario.

    Both ``<segment>`` (under ``<entity>``) and ``<scenario>`` (under
    ``<period>``'s parent ``context``) may carry dimensions; SEC predominantly
    uses ``segment`` but ``scenario`` is valid, so both are read to avoid
    discarding dimensional information (requirement 4). Dimensions are returned
    in document order; the deterministic hash sorts them (§15.5), so order here
    does not affect identity.
    """
    dimensions: list[RawDimension] = []
    containers: list[ET.Element] = []

    segment = entity.find(f"{{{XBRLI_NS}}}segment")
    if segment is not None:
        containers.append(segment)
    scenario = context.find(f"{{{XBRLI_NS}}}scenario")
    if scenario is not None:
        containers.append(scenario)

    for container in containers:
        for member in container:
            dimensions.append(_build_dimension(member, ns))
    return tuple(dimensions)


def _build_dimension(member: ET.Element, ns: NamespaceContext) -> RawDimension:
    tag_uri, tag_local = _split(member.tag)
    axis_value = member.get("dimension")
    if not axis_value:
        raise MalformedXbrlError(
            f"dimensional member {member.tag!r} missing 'dimension' axis"
        )
    axis = ns.resolve(axis_value)

    if tag_uri == XBRLDI_NS and tag_local == "explicitMember":
        member_text = member.text
        if member_text is None or not member_text.strip():
            raise MalformedXbrlError(
                f"explicitMember on axis {axis.clark!r} has no member value"
            )
        return RawDimension.explicit(axis, ns.resolve(member_text))

    if tag_uri == XBRLDI_NS and tag_local == "typedMember":
        children = list(member)
        if len(children) != 1:
            raise UnsupportedXbrlError(
                f"typedMember on axis {axis.clark!r} must have exactly one "
                f"child element, found {len(children)}"
            )
        child = children[0]
        return RawDimension.typed(axis, QName.from_clark(child.tag), child.text)

    raise UnsupportedXbrlError(
        f"unsupported dimensional element {member.tag!r} in segment/scenario"
    )


# -- unit extraction ----------------------------------------------------------


def _extract_units(root: ET.Element, ns: NamespaceContext) -> dict[str, RawUnit]:
    """Extract every ``<xbrli:unit>`` structurally, coercing nothing.

    Simple (measure-list) and ``divide`` (numerator/denominator) units are both
    represented; custom ``<issuer>:*`` measures pass through as resolved QNames.
    A duplicate unit id is malformed (ambiguous ``unitRef``) → fail closed.
    """
    units: dict[str, RawUnit] = {}
    for elem in root.findall(f"{{{XBRLI_NS}}}unit"):
        unit_id = elem.get("id")
        if not unit_id:
            raise MalformedXbrlError("unit element missing 'id'")
        if unit_id in units:
            raise MalformedXbrlError(f"duplicate unit id {unit_id!r}")
        units[unit_id] = _build_unit(unit_id, elem, ns)
    return units


def _build_unit(unit_id: str, elem: ET.Element, ns: NamespaceContext) -> RawUnit:
    divide = elem.find(f"{{{XBRLI_NS}}}divide")
    if divide is not None:
        numerator = _measures(divide.find(f"{{{XBRLI_NS}}}unitNumerator"), unit_id, ns)
        denominator = _measures(
            divide.find(f"{{{XBRLI_NS}}}unitDenominator"), unit_id, ns
        )
        if not numerator or not denominator:
            raise MalformedXbrlError(
                f"divide unit {unit_id!r} missing numerator or denominator measures"
            )
        return RawUnit.divide(unit_id, numerator, denominator)

    measures = tuple(
        ns.resolve(_require_measure_text(m, unit_id))
        for m in elem.findall(f"{{{XBRLI_NS}}}measure")
    )
    if not measures:
        raise MalformedXbrlError(f"unit {unit_id!r} has neither <measure> nor <divide>")
    return RawUnit.simple(unit_id, measures)


def _measures(
    container: ET.Element | None, unit_id: str, ns: NamespaceContext
) -> tuple[QName, ...]:
    if container is None:
        return ()
    return tuple(
        ns.resolve(_require_measure_text(m, unit_id))
        for m in container.findall(f"{{{XBRLI_NS}}}measure")
    )


def _require_measure_text(measure: ET.Element, unit_id: str) -> str:
    if measure.text is None or not measure.text.strip():
        raise MalformedXbrlError(f"unit {unit_id!r} has an empty <measure>")
    return measure.text


# -- fact extraction ----------------------------------------------------------


def _extract_facts(
    root: ET.Element,
    ns: NamespaceContext,
    contexts: dict[str, RawContext],
    units: dict[str, RawUnit],
    raw_document_id: str,
    identity: SourceIdentity,
    version: XbrlParserVersion,
) -> tuple[RawFact, ...]:
    """Extract every item fact in document order with deterministic ordinals.

    A fact is any element carrying a ``contextRef`` (this cleanly skips
    ``schemaRef``/``roleRef``/``footnoteLink`` and the ``context``/``unit``
    structural elements). Each fact's ``contextRef`` **must** resolve to a
    declared context and, when numeric, its ``unitRef`` **must** resolve to a
    declared unit — an unresolved reference is malformed (fail closed).

    Ordinals disambiguate facts that are otherwise identical in
    ``(context_ref, concept, unit_ref, dimensions)`` within this document, so a
    genuine duplicate is preserved as a distinct :class:`RawFact` rather than
    silently collapsed (data-model §13 case 8).
    """
    facts: list[RawFact] = []
    ordinals: dict[tuple[str, str, str, str], int] = {}

    version_id = version.transformation_version_id
    provenance = RawFactProvenance(
        filing_id=identity.filing_id,
        accession=identity.accession,
        company_id=identity.company_id,
        source_artifact_sha256=identity.source_artifact_sha256,
        source_artifact_type=identity.source_artifact_type,
        source_url=identity.source_url,
        source_document_name=identity.source_document_name,
        transformation_version_id=version_id,
    )

    for elem in root:
        context_ref = elem.get("contextRef")
        if context_ref is None:
            continue  # not a fact (structural element / linkbase ref)

        concept = QName.from_clark(elem.tag).clark
        context = contexts.get(context_ref)
        if context is None:
            raise MalformedXbrlError(
                f"fact {concept!r} references undeclared context {context_ref!r}"
            )

        unit_ref_attr = elem.get("unitRef")
        if unit_ref_attr is not None:
            unit = units.get(unit_ref_attr)
            if unit is None:
                raise MalformedXbrlError(
                    f"fact {concept!r} references undeclared unit {unit_ref_attr!r}"
                )
            unit_ref = unit.unit_ref()
        else:
            unit_ref = ""

        is_nil = elem.get(f"{{{XSI_NS}}}nil") == "true"
        value_raw = None if is_nil else elem.text
        value_numeric = None if is_nil else parse_numeric(value_raw)

        segment_key = context.dimensions_hash
        key = (context_ref, concept, unit_ref, segment_key)
        ordinal = ordinals.get(key, 0)
        ordinals[key] = ordinal + 1

        facts.append(
            RawFact(
                raw_fact_id=raw_fact_id(
                    raw_document_id=raw_document_id,
                    xbrl_context_ref=context_ref,
                    concept=concept,
                    unit_ref=unit_ref,
                    segment_key=segment_key,
                    ordinal=ordinal,
                ),
                raw_document_id=raw_document_id,
                concept=concept,
                context_ref=context_ref,
                unit_ref=unit_ref,
                dimensions_hash=segment_key,
                ordinal=ordinal,
                value_raw=value_raw,
                value_numeric_str=(
                    None if value_numeric is None else str(value_numeric)
                ),
                is_nil=is_nil,
                decimals=elem.get("decimals"),
                scale=elem.get("scale"),
                sign=elem.get("sign"),
                provenance=provenance,
            )
        )
    return tuple(facts)


# -- small helpers ------------------------------------------------------------


def _text(elem: ET.Element) -> str | None:
    return None if elem.text is None else elem.text.strip()


def _split(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        end = tag.find("}")
        return tag[1:end], tag[end + 1 :]
    return None, tag
