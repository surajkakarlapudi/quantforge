"""Tests for the sidecar availability store (Decision 3): round-trip & determinism.

The store is derived state — it must round-trip byte-identically, sort records
deterministically regardless of input order, and mirror the RegistryStore
``cik-<zfill10>.json`` layout so registry & availability files align 1:1.
"""

from __future__ import annotations

from pathlib import Path

from openfinance.availability.model import AvailabilityStatus, FilingAvailability
from openfinance.availability.store import (
    AVAILABILITY_FORMAT_VERSION,
    AvailabilityStore,
)
from openfinance.registry.identity import company_id as _company_id
from tests.availability.builders import availability


def _records() -> list[FilingAvailability]:
    return [
        availability(
            accession="0000320193-22-000001",
            timestamp="2022-05-01T21:30:00Z",
            status=AvailabilityStatus.DERIVED,
            policy_id="sha256:p1",
        ),
        availability(
            accession="0000320193-20-000001",
            timestamp="2020-03-01T21:30:00Z",
            status=AvailabilityStatus.DERIVED,
            policy_id="sha256:p1",
        ),
    ]


class TestStoreRoundTrip:
    def test_write_then_read(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        company = _company_id(320193)
        store.write_company(company, _records(), ["sha256:p1"])
        read = store.read_company(company)
        assert {r.filing_id for r in read} == {r.filing_id for r in _records()}

    def test_records_sorted_by_filing_id(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        company = _company_id(320193)
        store.write_company(company, _records(), ["sha256:p1"])
        read = store.read_company(company)
        assert [r.filing_id for r in read] == sorted(r.filing_id for r in read)

    def test_byte_identical_regardless_of_order(self, tmp_path: Path) -> None:
        company = _company_id(320193)
        recs = _records()
        s1 = AvailabilityStore(tmp_path / "a")
        s2 = AvailabilityStore(tmp_path / "b")
        p1 = s1.write_company(company, recs, ["sha256:p1"])
        p2 = s2.write_company(company, list(reversed(recs)), ["sha256:p1"])
        assert p1.read_bytes() == p2.read_bytes()

    def test_filename_mirrors_registry_layout(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        company = _company_id(320193)
        path = store.write_company(company, _records(), ["sha256:p1"])
        assert path.name == "cik-0000320193.json"
        assert path.parent.name == "availability"

    def test_format_version_stamped(self, tmp_path: Path) -> None:
        import json

        store = AvailabilityStore(tmp_path)
        company = _company_id(320193)
        path = store.write_company(company, _records(), ["sha256:p1"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["availability_format_version"] == AVAILABILITY_FORMAT_VERSION
        assert doc["availability_policy_ids"] == ["sha256:p1"]

    def test_read_company_map(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        company = _company_id(320193)
        store.write_company(company, _records(), ["sha256:p1"])
        mapping = store.read_company_map(company)
        assert set(mapping) == {r.filing_id for r in _records()}

    def test_missing_company_is_empty(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        assert store.read_company(_company_id(999)) == []
        assert not store.has_company(_company_id(999))

    def test_list_company_ids(self, tmp_path: Path) -> None:
        store = AvailabilityStore(tmp_path)
        store.write_company(_company_id(320193), _records(), ["sha256:p1"])
        assert store.list_company_ids() == [_company_id(320193)]
