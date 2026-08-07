"""End-to-end integration for the Phase 7 engine over the real backend.

Populates a genuine Phase 1 artifact store, Phase 2 registry, and Phase 4 canonical
store, then drives metrics through the :class:`Company` façade and :class:`Workspace`
— proving the engine composes Phases 4 & 5 additively (deriving availability on
demand), returns the two distinct types, and never introduces a new store.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from quantforge.availability.store import AvailabilityStore
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.company import Company
from quantforge.identity.resolve import CompanyResolver
from quantforge.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    RevisedMetricValue,
)
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
ACC = "0000320193-23-000106"
FY_END = "2023-09-30"
FY_START = "2022-10-01"
TICKERS = b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}'
USD = Unit("usd", measures=["iso4217:USD"])


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


def _populate(root: Path) -> Workspace:
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)

    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    subs = SubmissionsBuilder(APPLE).add(
        FilingRow(
            accession=ACC,
            form="10-K",
            filing_date="2023-11-03",
            report_date=FY_END,
            acceptance="2023-11-02T18:01:14.000Z",
            primary_document="aapl-20230930.htm",
        )
    )
    registry.build_company_from_artifacts([subs.primary_artifact()])

    # A balance sheet + income statement subset: current ratio + gross margin.
    canonical = CanonicalFactStore(root / "canonical")
    instance = (
        InstanceBuilder()
        .with_context(Ctx("i", instant=FY_END))
        .with_context(Ctx("d", start=FY_START, end=FY_END))
        .with_unit(USD)
        .with_fact(
            XbrlFact("us-gaap:AssetsCurrent", "i", value="200000000", unit_ref="usd")
        )
        .with_fact(
            XbrlFact(
                "us-gaap:LiabilitiesCurrent", "i", value="100000000", unit_ref="usd"
            )
        )
        .with_fact(
            XbrlFact("us-gaap:Revenues", "d", value="1000000000", unit_ref="usd")
        )
        .with_fact(
            XbrlFact("us-gaap:CostOfRevenue", "d", value="600000000", unit_ref="usd")
        )
    )
    result = canonicalize(instance, cik=APPLE, accession=ACC)
    canonical.write_instance(result, CanonicalFactVersion().transformation_version_id)

    resolver = CompanyResolver(artifacts)
    return Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=resolver,
        availability_store=AvailabilityStore(root / "availability"),
    )


@pytest.fixture
def apple(tmp_path: Path) -> Company:
    return Company.resolve("AAPL", workspace=_populate(tmp_path))


def _as_of() -> datetime:
    from quantforge.availability.timestamps import parse_utc

    return parse_utc("2024-06-01T00:00:00Z")


class TestPitMetric:
    def test_current_ratio_known(self, apple: Company) -> None:
        m = apple.metric_as_of("current_ratio", MetricPeriod.instant(FY_END), _as_of())
        assert isinstance(m, PitMetricValue)
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"
        assert m.company_id == "cik:0000320193"

    def test_gross_margin_known(self, apple: Company) -> None:
        m = apple.metric_as_of(
            "gross_margin", MetricPeriod.duration(FY_START, FY_END), _as_of()
        )
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "0.4"

    def test_before_availability_is_undefined(self, apple: Company) -> None:
        from quantforge.availability.timestamps import parse_utc

        m = apple.metric_as_of(
            "current_ratio",
            MetricPeriod.instant(FY_END),
            parse_utc("2023-01-01T00:00:00Z"),
        )
        assert m.status is MetricStatus.UNDEFINED


class TestRevisedMetric:
    def test_revised_current_ratio(self, apple: Company) -> None:
        dv = apple.dataset_version()
        m = apple.revised_metric("current_ratio", MetricPeriod.instant(FY_END), dv)
        assert isinstance(m, RevisedMetricValue)
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"

    def test_dataset_version_is_reproducible(self, apple: Company) -> None:
        assert (
            apple.dataset_version().dataset_version_id
            == apple.dataset_version().dataset_version_id
        )


class TestReinterpret:
    def test_reinterpret_as_pit_reresolves(
        self, apple: Company, tmp_path: Path
    ) -> None:
        dv = apple.dataset_version()
        revised = apple.revised_metric(
            "current_ratio", MetricPeriod.instant(FY_END), dv
        )
        engine = apple._metric_engine  # the wired MetricEngine
        pit = revised.reinterpret_as_pit(engine, _as_of())
        assert isinstance(pit, PitMetricValue)
        assert pit.status is MetricStatus.KNOWN
        assert pit.value_numeric_str == "2"


class TestAdditiveWiring:
    def test_facts_still_readable(self, apple: Company) -> None:
        # The metric path never disturbs the Phase 4 view.
        assert len(apple.facts()) == 4

    def test_unknown_metric_key_fails_closed(self, apple: Company) -> None:
        from quantforge.metrics.errors import FormulaConfigurationError

        with pytest.raises(FormulaConfigurationError):
            apple.metric_as_of("ebitda", MetricPeriod.instant(FY_END), _as_of())

    def test_metric_engine_is_cached(self, tmp_path: Path) -> None:
        ws = _populate(tmp_path)
        assert ws.metric_engine is ws.metric_engine
