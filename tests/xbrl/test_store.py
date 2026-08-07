"""Deterministic raw-XBRL store: round-trip and byte-stable serialization."""

from __future__ import annotations

from pathlib import Path

from quantforge.xbrl.parser import ParsedInstance, parse_instance
from quantforge.xbrl.store import RAW_XBRL_FORMAT_VERSION, RawXbrlStore
from quantforge.xbrl.version import XbrlParserVersion

from .builders import (
    Ctx,
    ExplicitDim,
    Fact,
    InstanceBuilder,
    Unit,
    source_identity,
)


def _sample() -> ParsedInstance:
    b = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_context(
            Ctx(
                "seg",
                instant="2023-09-30",
                segment=[
                    ExplicitDim("srt:ProductOrServiceAxis", "us-gaap:ProductMember")
                ],
            )
        )
        .with_unit(Unit("usd", measures=["iso4217:USD"]))
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "seg", value="200", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
    )
    data = b.to_bytes()
    return parse_instance(data, source_identity(data=data))


def test_round_trip_preserves_everything(tmp_path: Path) -> None:
    parsed = _sample()
    store = RawXbrlStore(tmp_path)
    version_id = XbrlParserVersion().transformation_version_id
    store.write_instance(parsed, version_id)

    read = store.read_instance(parsed.document.raw_document_id)
    assert read is not None
    document, contexts, units, facts = read
    assert document == parsed.document
    assert contexts == parsed.contexts
    assert units == parsed.units
    assert sorted(facts, key=lambda f: f.raw_fact_id) == sorted(
        parsed.facts, key=lambda f: f.raw_fact_id
    )


def test_write_is_byte_deterministic(tmp_path: Path) -> None:
    parsed = _sample()
    version_id = XbrlParserVersion().transformation_version_id
    store_a = RawXbrlStore(tmp_path / "a")
    store_b = RawXbrlStore(tmp_path / "b")
    path_a = store_a.write_instance(parsed, version_id)
    path_b = store_b.write_instance(parsed, version_id)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_rewrite_is_idempotent(tmp_path: Path) -> None:
    parsed = _sample()
    version_id = XbrlParserVersion().transformation_version_id
    store = RawXbrlStore(tmp_path)
    p1 = store.write_instance(parsed, version_id)
    first = p1.read_bytes()
    p2 = store.write_instance(parsed, version_id)
    assert p1 == p2
    assert p2.read_bytes() == first


def test_envelope_has_format_and_transformation_version(tmp_path: Path) -> None:
    import json

    parsed = _sample()
    version_id = XbrlParserVersion().transformation_version_id
    store = RawXbrlStore(tmp_path)
    path = store.write_instance(parsed, version_id)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["raw_xbrl_format_version"] == RAW_XBRL_FORMAT_VERSION
    assert envelope["transformation_version_id"] == version_id


def test_missing_instance_reads_none(tmp_path: Path) -> None:
    store = RawXbrlStore(tmp_path)
    assert store.read_instance("sha256:deadbeef") is None
    assert store.has_instance("sha256:deadbeef") is False


def test_list_document_ids(tmp_path: Path) -> None:
    parsed = _sample()
    store = RawXbrlStore(tmp_path)
    store.write_instance(parsed, XbrlParserVersion().transformation_version_id)
    assert store.list_document_ids() == [parsed.document.raw_document_id]
