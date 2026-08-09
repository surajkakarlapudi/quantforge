"""Deterministic multi-period backend for Phase 10 panel integration tests.

Populates a genuine Phase 1 artifact store, Phase 2 registry, and Phase 4 canonical
store with **several fiscal years** of 10-K filings for one or two filers — the shape
a panel's time axis needs. Each year is its own filing (its own acceptance instant),
so a period becomes PIT-eligible only after that year's filing is accepted; this lets
the tests exercise real availability boundaries over a period axis rather than
hand-mocking eligibility.

Everything is offline and deterministic (no network, no wall-clock).
"""

from __future__ import annotations

from pathlib import Path

from quantforge.availability.store import AvailabilityStore
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.identity.resolve import CompanyResolver
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from quantforge.sec.storage import ArtifactStore
from quantforge.workspace import Workspace
from tests.canonical.builders import canonicalize
from tests.registry.builders import FilingRow, SubmissionsBuilder
from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
from tests.xbrl.builders import Fact as XbrlFact

APPLE = 320193
MSFT = 789019
USD = Unit("usd", measures=["iso4217:USD"])

TICKERS = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":789019,"ticker":"MSFT","title":"Microsoft Corp."}}'
)


def _store_tickers(store: ArtifactStore) -> None:
    meta = AcquisitionMetadata(
        source_url="https://www.sec.gov/files/company_tickers.json",
        artifact_type=ArtifactType.COMPANY_TICKERS,
        sha256=sha256_hex(TICKERS),
        retrieved_at="2020-01-01T00:00:00",
        http_status=200,
        user_agent="test test@example.com",
    )
    store.store(Artifact(data=TICKERS, metadata=meta))


class Year:
    """One fiscal year's balance-sheet inputs for a filer.

    ``assets`` / ``liabilities`` are the year-end current-asset / current-liability
    amounts; a ``None`` value omits that fact, so the year's current_ratio resolves
    to a first-class UNDEFINED (an explicit gap in the panel, never a dropped cell).
    """

    def __init__(
        self, year: int, *, assets: str | None, liabilities: str | None
    ) -> None:
        self.year = year
        self.assets = assets
        self.liabilities = liabilities

    @property
    def fy_end(self) -> str:
        return f"{self.year}-12-31"


def _accession(cik: int, year: int, seq: int) -> str:
    """A deterministic accession for filer ``cik`` reporting fiscal ``year``."""
    return f"{cik:010d}-{(year + 1) % 100:02d}-{seq:06d}"


def _canonicalize_year(
    canonical: CanonicalFactStore, *, cik: int, accession: str, year: Year
) -> None:
    doc = f"{cik}-{year.fy_end}.htm"
    builder = (
        InstanceBuilder().with_context(Ctx("i", instant=year.fy_end)).with_unit(USD)
    )
    if year.assets is not None:
        builder = builder.with_fact(
            XbrlFact("us-gaap:AssetsCurrent", "i", value=year.assets, unit_ref="usd")
        )
    if year.liabilities is not None:
        builder = builder.with_fact(
            XbrlFact(
                "us-gaap:LiabilitiesCurrent",
                "i",
                value=year.liabilities,
                unit_ref="usd",
            )
        )
    result = canonicalize(builder, cik=cik, accession=accession, filename=doc)
    canonical.write_instance(result, CanonicalFactVersion().transformation_version_id)


def _load_filer(
    registry: FilingRegistry,
    canonical: CanonicalFactStore,
    *,
    cik: int,
    years: list[Year],
    base_seq: int,
) -> None:
    """Register every year's 10-K in one submissions page, then canonicalize each.

    All rows go on a single submissions page so the registry holds the filer's whole
    filing history (one ``build_company_from_artifacts`` per filer, not per year); the
    canonical store accumulates facts across the distinct per-year accessions.
    """
    subs = SubmissionsBuilder(cik)
    accessions: list[str] = []
    for idx, year in enumerate(years):
        accession = _accession(cik, year.year, base_seq + idx)
        accessions.append(accession)
        subs.add(
            FilingRow(
                accession=accession,
                form="10-K",
                filing_date=f"{year.year + 1}-02-15",
                report_date=year.fy_end,
                acceptance=f"{year.year + 1}-02-15T12:00:00.000Z",
                primary_document=f"{cik}-{year.fy_end}.htm",
            )
        )
    registry.build_company_from_artifacts([subs.primary_artifact()])
    for accession, year in zip(accessions, years, strict=True):
        _canonicalize_year(canonical, cik=cik, accession=accession, year=year)


def populate(
    root: Path,
    *,
    apple_years: list[Year],
    msft_years: list[Year] | None = None,
) -> Workspace:
    """Build a workspace with several fiscal years for Apple (+ optionally MSFT).

    A year ``Y`` is filed on ``(Y+1)-02-15`` and accepted the same day, so a period
    ending ``Y-12-31`` is PIT-eligible only from that instant on.
    """
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    canonical = CanonicalFactStore(root / "canonical")

    _load_filer(registry, canonical, cik=APPLE, years=apple_years, base_seq=100)
    if msft_years is not None:
        _load_filer(registry, canonical, cik=MSFT, years=msft_years, base_seq=500)

    resolver = CompanyResolver(artifacts)
    return Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=resolver,
        availability_store=AvailabilityStore(root / "availability"),
    )
