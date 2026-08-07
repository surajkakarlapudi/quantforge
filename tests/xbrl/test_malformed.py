"""Fail-closed handling of malformed / unsupported XBRL (requirement 12)."""

from __future__ import annotations

import pytest

from quantforge.xbrl.errors import MalformedXbrlError, UnsupportedXbrlError
from quantforge.xbrl.parser import ParsedInstance, parse_instance

from .builders import Ctx, Fact, InstanceBuilder, Unit, source_identity


def _parse_bytes(data: bytes) -> ParsedInstance:
    return parse_instance(data, source_identity(data=data))


def test_not_well_formed_xml_raises() -> None:
    data = b"<xbrli:xbrl><unclosed>"
    with pytest.raises(MalformedXbrlError, match="well-formed"):
        _parse_bytes(data)


def test_non_xbrl_root_raises() -> None:
    data = b'<?xml version="1.0"?>\n<html><body/></html>'
    with pytest.raises(MalformedXbrlError, match="not an XBRL instance"):
        _parse_bytes(data)


def test_empty_document_raises() -> None:
    with pytest.raises(MalformedXbrlError):
        _parse_bytes(b"")


def test_doctype_rejected_as_unsupported() -> None:
    data = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE xbrli:xbrl [<!ENTITY x "boom">]>\n'
        b'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"/>'
    )
    with pytest.raises(UnsupportedXbrlError, match="DOCTYPE"):
        _parse_bytes(data)


def test_fact_referencing_missing_context_fails_closed() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "MISSING", value="1", unit_ref="usd"))
    )
    with pytest.raises(MalformedXbrlError, match="undeclared context"):
        _parse_bytes(b.to_bytes())


def test_fact_referencing_missing_unit_fails_closed() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="1", unit_ref="MISSING"))
    )
    with pytest.raises(MalformedXbrlError, match="undeclared unit"):
        _parse_bytes(b.to_bytes())


def test_duplicate_context_id_fails_closed() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_context(Ctx("c1", instant="2022-09-30"))
    )
    with pytest.raises(MalformedXbrlError, match="duplicate context"):
        _parse_bytes(b.to_bytes())


def test_duplicate_unit_id_fails_closed() -> None:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_unit(Unit("usd", measures=["xbrli:shares"]))
    )
    with pytest.raises(MalformedXbrlError, match="duplicate unit"):
        _parse_bytes(b.to_bytes())


def test_context_missing_period_fails_closed() -> None:
    # Hand-craft a context with an entity but no period.
    data = (
        b'<?xml version="1.0"?>\n'
        b'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">\n'
        b'  <xbrli:context id="c1">\n'
        b"    <xbrli:entity>\n"
        b'      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193'
        b"</xbrli:identifier>\n"
        b"    </xbrli:entity>\n"
        b"  </xbrli:context>\n"
        b"</xbrli:xbrl>\n"
    )
    with pytest.raises(MalformedXbrlError, match="no <period>"):
        _parse_bytes(data)


def test_prefix_rebinding_conflict_fails_closed() -> None:
    # Same prefix bound to two different URIs on nested elements → ambiguous.
    data = (
        b'<?xml version="1.0"?>\n'
        b'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"'
        b' xmlns:us-gaap="http://fasb.org/us-gaap/2023">\n'
        b'  <xbrli:context id="c1">\n'
        b"    <xbrli:entity>\n"
        b'      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193'
        b"</xbrli:identifier>\n"
        b"    </xbrli:entity>\n"
        b"    <xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period>\n"
        b"  </xbrli:context>\n"
        b'  <us-gaap:Cash xmlns:us-gaap="http://fasb.org/DIFFERENT"'
        b' contextRef="c1">1</us-gaap:Cash>\n'
        b"</xbrli:xbrl>\n"
    )
    with pytest.raises(UnsupportedXbrlError, match="rebound"):
        _parse_bytes(data)


def test_typed_member_with_multiple_children_unsupported() -> None:
    data = (
        b'<?xml version="1.0"?>\n'
        b'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"'
        b' xmlns:xbrldi="http://xbrl.org/2006/xbrldi"'
        b' xmlns:us-gaap="http://fasb.org/us-gaap/2023">\n'
        b'  <xbrli:context id="c1">\n'
        b"    <xbrli:entity>\n"
        b'      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193'
        b"</xbrli:identifier>\n"
        b"      <xbrli:segment>\n"
        b'        <xbrldi:typedMember dimension="us-gaap:Axis">'
        b"<us-gaap:A>1</us-gaap:A><us-gaap:B>2</us-gaap:B>"
        b"</xbrldi:typedMember>\n"
        b"      </xbrli:segment>\n"
        b"    </xbrli:entity>\n"
        b"    <xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period>\n"
        b"  </xbrli:context>\n"
        b"</xbrli:xbrl>\n"
    )
    with pytest.raises(UnsupportedXbrlError, match="exactly one"):
        _parse_bytes(data)


def test_never_invents_value_on_malformed_input() -> None:
    # Fail-closed guarantee: a malformed doc yields an exception, never a
    # partial ParsedInstance with fabricated facts.
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_fact(Fact("us-gaap:Cash", "c1", value="1", unit_ref="MISSING"))
    )
    with pytest.raises(MalformedXbrlError):
        _parse_bytes(b.to_bytes())
