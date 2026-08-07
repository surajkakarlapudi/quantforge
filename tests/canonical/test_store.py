"""Deterministic canonical-fact store: round-trip and byte-stable output."""

from __future__ import annotations

import json
from pathlib import Path

from quantforge.canonical.canonicalize import Canonicalizer, CanonicalizeResult
from quantforge.canonical.store import (
    CANONICAL_FACTS_FORMAT_VERSION,
    CanonicalFactStore,
)
from quantforge.canonical.version import CanonicalFactVersion
from tests.xbrl.builders import Ctx, ExplicitDim, Fact, InstanceBuilder, Unit

from .builders import parse

USD = Unit("usd", measures=["iso4217:USD"])


def _sample_result() -> CanonicalizeResult:
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
        .with_unit(USD)
        .with_fact(Fact("us-gaap:Cash", "c1", value="100", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Revenues", "seg", value="200", unit_ref="usd"))
        .with_fact(Fact("us-gaap:Goodwill", "c1", unit_ref="usd", nil=True))
    )
    return Canonicalizer().canonicalize(parse(b))


def test_round_trip_preserves_facts(tmp_path: Path) -> None:
    result = _sample_result()
    store = CanonicalFactStore(tmp_path)
    version_id = CanonicalFactVersion().transformation_version_id
    store.write_instance(result, version_id)

    read = store.read_instance(result.raw_document_id)
    assert read is not None
    by_id = {f.fact_id: f for f in read}
    for original in result.facts:
        assert by_id[original.fact_id] == original


def test_write_is_byte_deterministic(tmp_path: Path) -> None:
    result = _sample_result()
    version_id = CanonicalFactVersion().transformation_version_id
    a = CanonicalFactStore(tmp_path / "a")
    b = CanonicalFactStore(tmp_path / "b")
    pa = a.write_instance(result, version_id)
    pb = b.write_instance(result, version_id)
    assert pa.read_bytes() == pb.read_bytes()


def test_rewrite_is_idempotent(tmp_path: Path) -> None:
    result = _sample_result()
    version_id = CanonicalFactVersion().transformation_version_id
    store = CanonicalFactStore(tmp_path)
    p1 = store.write_instance(result, version_id)
    first = p1.read_bytes()
    p2 = store.write_instance(result, version_id)
    assert p1 == p2
    assert p2.read_bytes() == first


def test_envelope_records_format_and_version(tmp_path: Path) -> None:
    result = _sample_result()
    version_id = CanonicalFactVersion().transformation_version_id
    store = CanonicalFactStore(tmp_path)
    path = store.write_instance(result, version_id)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["canonical_facts_format_version"] == CANONICAL_FACTS_FORMAT_VERSION
    assert envelope["transformation_version_id"] == version_id
    # Facts are emitted sorted by fact_id.
    ids = [f["fact_id"] for f in envelope["facts"]]
    assert ids == sorted(ids)


def test_missing_instance_reads_none(tmp_path: Path) -> None:
    store = CanonicalFactStore(tmp_path)
    assert store.read_instance("sha256:deadbeef") is None
    assert store.has_instance("sha256:deadbeef") is False


def test_list_document_ids(tmp_path: Path) -> None:
    result = _sample_result()
    store = CanonicalFactStore(tmp_path)
    store.write_instance(result, CanonicalFactVersion().transformation_version_id)
    assert store.list_document_ids() == [result.raw_document_id]


def test_read_company_returns_matching_facts_sorted(tmp_path: Path) -> None:
    result = _sample_result()
    store = CanonicalFactStore(tmp_path)
    store.write_instance(result, CanonicalFactVersion().transformation_version_id)
    company = result.facts[0].company_id

    facts = store.read_company(company)
    assert facts, "expected facts for the sample company"
    assert all(f.company_id == company for f in facts)
    # Deterministic order, independent of instance iteration.
    assert [f.fact_id for f in facts] == sorted(f.fact_id for f in facts)
    # Matches the full instance's fact set for this single-company sample.
    assert {f.fact_id for f in facts} == {f.fact_id for f in result.facts}


def test_read_company_absent_is_empty(tmp_path: Path) -> None:
    store = CanonicalFactStore(tmp_path)
    assert store.read_company("cik:0000000001") == []
