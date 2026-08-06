"""Tests for the availability façade (Decision 1 & 3 wiring).

Exercises the two mandate-critical joins the ingestor performs: the Phase 1
``retrieved_at`` upper bound joined **only** at derivation (Decision 1), and the
sidecar persistence keyed by ``filing_id`` that never rewrites facts (Decision 3).
Uses the Phase 2 registry builders (no network, no real artifacts).
"""

from __future__ import annotations

from pathlib import Path

from openfinance.availability.ingest import AvailabilityIngestor
from openfinance.availability.model import AvailabilityStatus
from openfinance.availability.store import AvailabilityStore
from openfinance.registry.identity import company_id as _company_id
from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from tests.registry.builders import FilingRow, SubmissionsBuilder

CIK = 320193


def _registry(tmp_path: Path) -> FilingRegistry:
    store = RegistryStore(tmp_path / "registry")
    registry = FilingRegistry(store)
    builder = SubmissionsBuilder(cik=CIK)
    builder.add(
        FilingRow(
            accession="0000320193-24-000081",
            form="10-Q",
            filing_date="2024-08-02",
            report_date="2024-06-29",
            acceptance="2024-08-01T22:03:34.000Z",
        )
    )
    builder.add(
        FilingRow(
            accession="0000320193-05-000001",
            form="10-K",
            filing_date="2005-12-01",
            report_date="2005-09-30",
            acceptance="2005-12-01T12:00:00.000Z",  # pre-era → unknown
        )
    )
    registry.build_company_from_artifacts([builder.primary_artifact()])
    return registry


class TestDeriveCompany:
    def test_derives_and_classifies(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        store = AvailabilityStore(tmp_path / "avail")
        ingestor = AvailabilityIngestor(registry, store)
        result = ingestor.derive_company(CIK)
        # One post-era 10-Q derived; one pre-era filing fails closed to unknown.
        assert result.derived_count == 1
        assert result.unknown_count == 1
        assert result.verified_count == 0  # Decision 4: never verified

    def test_persisted_and_reloadable(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        store = AvailabilityStore(tmp_path / "avail")
        AvailabilityIngestor(registry, store).derive_company(CIK)
        reloaded = store.read_company_map(_company_id(CIK))
        assert len(reloaded) == 2

    def test_derivation_is_deterministic(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        s1 = AvailabilityStore(tmp_path / "a")
        s2 = AvailabilityStore(tmp_path / "b")
        p1 = AvailabilityIngestor(registry, s1).derive_company(CIK)
        p2 = AvailabilityIngestor(registry, s2).derive_company(CIK)
        assert [r.to_dict() for r in p1.records] == [r.to_dict() for r in p2.records]

    def test_derived_timestamp_respects_cutoff(self, tmp_path: Path) -> None:
        # 10-Q accepted Thu 2024-08-01 22:03Z (18:03 EDT, after 17:30) → next
        # business day Fri 2024-08-02 17:30 EDT = 21:30Z.
        registry = _registry(tmp_path)
        store = AvailabilityStore(tmp_path / "avail")
        result = AvailabilityIngestor(registry, store).derive_company(CIK)
        derived = next(
            r
            for r in result.records
            if r.availability_status is AvailabilityStatus.DERIVED
        )
        assert derived.derived_public_availability_timestamp == "2024-08-02T21:30:00Z"


class TestPolicyIds:
    def test_default_policy_is_edgar_std_v1(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        ingestor = AvailabilityIngestor(registry, AvailabilityStore(tmp_path / "a"))
        assert len(ingestor.policies) == 1
        assert ingestor.policies[0].policy_id == "edgar-std"
        assert ingestor.policies[0].policy_version == "v1"
        assert all(pid.startswith("sha256:") for pid in ingestor.policy_ids)
