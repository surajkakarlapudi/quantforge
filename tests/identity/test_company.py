"""Integration tests for the Company façade over the real Phase 2/4 backend.

These populate a genuine Phase 1 artifact store, Phase 2 registry, and Phase 4
canonical store, then drive them exclusively through ``Company.resolve(...)`` —
proving the façade delegates to the existing layers without duplicating them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openfinance.availability.store import AvailabilityStore
from openfinance.canonical.store import CanonicalFactStore
from openfinance.canonical.version import CanonicalFactVersion
from openfinance.company import Company
from openfinance.identity.resolve import CompanyResolver
from openfinance.registry.registry import FilingRegistry
from openfinance.registry.store import RegistryStore
from openfinance.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from openfinance.sec.storage import ArtifactStore
from openfinance.workspace import Workspace
from tests.canonical.builders import canonicalize
from tests.registry.builders import FilingRow, SubmissionsBuilder
from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
from tests.xbrl.builders import Fact as XbrlFact

APPLE = 320193
TICKERS = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":1318605,"ticker":"TSLA","title":"Tesla, Inc."}}'
)
USD = Unit("usd", measures=["iso4217:USD"])


def _store_tickers(store: ArtifactStore) -> None:
    meta = AcquisitionMetadata(
        source_url="https://www.sec.gov/files/company_tickers.json",
        artifact_type=ArtifactType.COMPANY_TICKERS,
        sha256=sha256_hex(TICKERS),
        retrieved_at="2026-01-01T00:00:00",
        http_status=200,
        user_agent="test test@example.com",
    )
    store.store(Artifact(data=TICKERS, metadata=meta))


def _populate(root: Path) -> Workspace:
    """Build a full data root: artifacts + registry + canonical facts for Apple."""
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)

    # Phase 2: derive a registry from a submissions artifact.
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    subs = SubmissionsBuilder(APPLE).add(
        FilingRow(
            accession="0000320193-23-000106",
            form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            acceptance="2023-11-02T18:01:14.000Z",
            primary_document="aapl-20230930.htm",
        )
    )
    registry.build_company_from_artifacts([subs.primary_artifact()])

    # Phase 4: canonicalize an instance and persist its facts for Apple.
    canonical = CanonicalFactStore(root / "canonical")
    instance = (
        InstanceBuilder()
        .with_context(Ctx("c1", instant="2023-09-30"))
        .with_unit(USD)
        .with_fact(
            XbrlFact("us-gaap:Assets", "c1", value="352755000000", unit_ref="usd")
        )
    )
    result = canonicalize(instance, cik=APPLE)
    canonical.write_instance(result, CanonicalFactVersion().transformation_version_id)

    resolver = CompanyResolver(artifacts)  # offline; tickers already cached
    return Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=resolver,
        availability_store=AvailabilityStore(root / "availability"),
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return _populate(tmp_path)


def test_resolve_by_ticker(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    assert apple.company_id == "cik:0000320193"
    assert apple.cik == "320193"
    assert apple.ticker == "AAPL"
    assert apple.name == "Apple Inc."


def test_resolve_by_cik(workspace: Workspace) -> None:
    apple = Company.resolve("320193", workspace=workspace)
    assert apple.company_id == "cik:0000320193"
    # CIK path still enriches ticker/name from the cached mapping.
    assert apple.ticker == "AAPL"


def test_repr_is_readable(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    assert repr(apple) == "Company('AAPL', cik='320193')"


def test_filings_delegates_to_registry(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    filings = apple.filings()
    assert len(filings) == 1
    assert filings[0].form == "10-K"
    assert filings[0].filing_date == "2023-11-03"
    # Identical to calling the registry directly with the resolved CIK.
    assert filings == workspace.registry.list_filings("320193")


def test_filings_by_form(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    assert len(apple.filings_by_form("10-K")) == 1
    assert apple.filings_by_form("8-K") == []


def test_facts_delegates_to_canonical_store(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    facts = apple.facts()
    assert len(facts) == 1
    assert facts[0].company_id == "cik:0000320193"
    # Identical to reading the canonical store directly.
    assert facts == workspace.canonical_store.read_company("cik:0000320193")


def test_facts_full_provenance_preserved(workspace: Workspace) -> None:
    apple = Company.resolve("AAPL", workspace=workspace)
    prov = apple.facts()[0].provenance
    # The façade preserves the complete lineage — it copies nothing and loses
    # nothing.
    assert prov.company_id == "cik:0000320193"
    assert prov.accession == "0000320193-23-000106"
    assert prov.source_artifact_sha256
    assert prov.source_url


def test_unknown_filer_has_empty_views(workspace: Workspace) -> None:
    # Tesla resolves (it is in the mapping) but has no registry/canonical data.
    tesla = Company.resolve("TSLA", workspace=workspace)
    assert tesla.cik == "1318605"
    assert tesla.filings() == []
    assert tesla.facts() == []


def test_resolution_is_deterministic(workspace: Workspace) -> None:
    a = Company.resolve("AAPL", workspace=workspace)
    b = Company.resolve("aapl", workspace=workspace)
    # The canonical identity is stable across input case; only ``resolved_from``
    # differs, because it faithfully preserves the exact input for provenance.
    assert (a.company_id, a.cik, a.ticker, a.name) == (
        b.company_id,
        b.cik,
        b.ticker,
        b.name,
    )
    assert a.identity.resolved_from == "AAPL"
    assert b.identity.resolved_from == "aapl"
