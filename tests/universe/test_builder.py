"""End-to-end integration for the Phase 9.2 :class:`UniverseBuilder`.

Populates a genuine Phase 1 artifact store, Phase 2 registry, and Phase 4 canonical
store for a small explicit universe of filers, then drives constructions through
:class:`UniverseBuilder` — proving the builder composes the existing resolver and
metric engine to evaluate a :class:`UniverseSpecification` at a PIT/REVISED boundary,
narrows in declared order, records every exclusion with its reason, fails closed on
an empty result, and content-addresses the whole construction reproducibly.

The backend fixture mirrors ``tests/factors/test_engine_integration.py`` so the two
cross-sectional layers are exercised over the same kind of real data.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from quantforge.availability.store import AvailabilityStore
from quantforge.availability.timestamps import parse_utc
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.identity.resolve import CompanyResolver
from quantforge.metrics.model import MetricPeriod
from quantforge.registry.identity import company_id as _company_id
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.artifacts import (
    AcquisitionMetadata,
    Artifact,
    ArtifactType,
    sha256_hex,
)
from quantforge.sec.storage import ArtifactStore
from quantforge.universe.builder import UniverseBuilder
from quantforge.universe.errors import (
    UniverseConfigurationError,
    UniverseSpecificationError,
)
from quantforge.universe.filters import (
    CompanyMetricFilter,
    ComparisonOperator,
    ExclusionReason,
    ExplicitCompanyFilter,
    SectorClassification,
    SectorFilter,
)
from quantforge.universe.model import Universe
from quantforge.universe.specification import UniverseSpecification
from quantforge.workspace import Workspace
from tests.canonical.builders import canonicalize
from tests.registry.builders import FilingRow, SubmissionsBuilder
from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
from tests.xbrl.builders import Fact as XbrlFact

APPLE = 320193
MSFT = 789019
NVDA = 1045810
BERKSHIRE = 1067983  # deliberately never populated (no facts)
FY_END = "2023-09-30"
USD = Unit("usd", measures=["iso4217:USD"])
TICKERS = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":789019,"ticker":"MSFT","title":"Microsoft Corp."},'
    b'"2":{"cik_str":1045810,"ticker":"NVDA","title":"NVIDIA CORP"},'
    b'"3":{"cik_str":1067983,"ticker":"BRK-B","title":"BERKSHIRE HATHAWAY"}}'
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


def _add_filer(
    registry: FilingRegistry,
    canonical: CanonicalFactStore,
    *,
    cik: int,
    accession: str,
    doc: str,
    assets_current: str,
    liabilities_current: str,
) -> None:
    """Register one 10-K filer and persist a working_capital-computable fact set."""
    subs = SubmissionsBuilder(cik).add(
        FilingRow(
            accession=accession,
            form="10-K",
            filing_date="2023-11-03",
            report_date=FY_END,
            acceptance="2023-11-02T18:01:14.000Z",
            primary_document=doc,
        )
    )
    registry.build_company_from_artifacts([subs.primary_artifact()])
    instance = (
        InstanceBuilder()
        .with_context(Ctx("i", instant=FY_END))
        .with_unit(USD)
        .with_fact(
            XbrlFact("us-gaap:AssetsCurrent", "i", value=assets_current, unit_ref="usd")
        )
        .with_fact(
            XbrlFact(
                "us-gaap:LiabilitiesCurrent",
                "i",
                value=liabilities_current,
                unit_ref="usd",
            )
        )
    )
    result = canonicalize(instance, cik=cik, accession=accession)
    canonical.write_instance(result, CanonicalFactVersion().transformation_version_id)


def _populate(root: Path) -> Workspace:
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    canonical = CanonicalFactStore(root / "canonical")

    # working_capital = assets_current - liabilities_current.
    # AAPL: 200M - 100M = 100M ; MSFT: 1000M - 500M = 500M ; NVDA: 60M - 100M = -40M.
    _add_filer(
        registry,
        canonical,
        cik=APPLE,
        accession="0000320193-23-000106",
        doc="aapl-20230930.htm",
        assets_current="200000000",
        liabilities_current="100000000",
    )
    _add_filer(
        registry,
        canonical,
        cik=MSFT,
        accession="0000789019-23-000105",
        doc="msft-20230930.htm",
        assets_current="1000000000",
        liabilities_current="500000000",
    )
    _add_filer(
        registry,
        canonical,
        cik=NVDA,
        accession="0001045810-23-000100",
        doc="nvda-20230930.htm",
        assets_current="60000000",
        liabilities_current="100000000",
    )

    resolver = CompanyResolver(artifacts)
    return Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=resolver,
        availability_store=AvailabilityStore(root / "availability"),
    )


def _as_of() -> datetime:
    return parse_utc("2024-06-01T00:00:00Z")


PERIOD = MetricPeriod.instant(FY_END)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return _populate(tmp_path)


@pytest.fixture
def builder(workspace: Workspace) -> UniverseBuilder:
    return UniverseBuilder(workspace)


def _wc_positive() -> CompanyMetricFilter:
    return CompanyMetricFilter(
        metric_key="working_capital",
        period=PERIOD,
        operator=ComparisonOperator.GT,
        threshold="0",
    )


# -- explicit source construction -------------------------------------------


class TestExplicitSource:
    def test_source_seeds_membership_in_declared_order(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="three",
            filters=(ExplicitCompanyFilter(identifiers=("MSFT", "AAPL", "NVDA")),),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (
            _company_id(MSFT),
            _company_id(APPLE),
            _company_id(NVDA),
        )

    def test_source_deduplicates_first_seen(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="dupes",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "320193", "MSFT", "AAPL")),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (_company_id(APPLE), _company_id(MSFT))

    def test_returns_a_phase91_universe(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="one", filters=(ExplicitCompanyFilter(identifiers=("AAPL",)),)
        )
        result = builder.build_as_of(spec, _as_of())
        assert isinstance(result.universe, Universe)


# -- metric filtering --------------------------------------------------------


class TestMetricFilter:
    def test_keeps_only_threshold_passers(self, builder: UniverseBuilder) -> None:
        # AAPL(+100M) and MSFT(+500M) pass > 0; NVDA(-40M) is excluded.
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (_company_id(APPLE), _company_id(MSFT))

    def test_excluded_recorded_with_reason(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        excluded = {e.company_id: e for e in result.construction.excluded}
        assert _company_id(NVDA) in excluded
        assert (
            excluded[_company_id(NVDA)].reason
            is ExclusionReason.METRIC_THRESHOLD_NOT_MET
        )
        assert excluded[_company_id(NVDA)].detail == "-40000000"

    def test_threshold_between_members(self, builder: UniverseBuilder) -> None:
        # > 200M keeps only MSFT (500M); AAPL (100M) drops.
        spec = UniverseSpecification(
            name="big-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                CompanyMetricFilter(
                    metric_key="working_capital",
                    period=PERIOD,
                    operator=ComparisonOperator.GT,
                    threshold="200000000",
                ),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (_company_id(MSFT),)

    def test_metric_undefined_before_availability_fails_closed(
        self, builder: UniverseBuilder
    ) -> None:
        # Before any filing is public, working_capital is UNDEFINED for every member,
        # so the whole membership drops out — an empty universe fails closed (Phase
        # 9.1), with the UNDEFINED exclusions still surfaced in the raised path's
        # provenance is not available here, so we assert the fail-closed contract.
        spec = UniverseSpecification(
            name="early",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT")),
                _wc_positive(),
            ),
        )
        with pytest.raises(UniverseConfigurationError):
            builder.build_as_of(spec, parse_utc("2023-01-01T00:00:00Z"))

    def test_member_without_facts_is_excluded_as_undefined(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="missing",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "1067983")),
                _wc_positive(),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (_company_id(APPLE),)
        excluded = {e.company_id: e for e in result.construction.excluded}
        assert (
            excluded[_company_id(BERKSHIRE)].reason is ExclusionReason.METRIC_UNDEFINED
        )

    def test_unknown_metric_key_fails_closed(self, builder: UniverseBuilder) -> None:
        # market_cap is not a registered formula (SEC filings carry no share price).
        spec = UniverseSpecification(
            name="no-such-metric",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL",)),
                CompanyMetricFilter(
                    metric_key="market_cap",
                    period=PERIOD,
                    operator=ComparisonOperator.GT,
                    threshold="0",
                ),
            ),
        )
        with pytest.raises(UniverseSpecificationError, match="market_cap"):
            builder.build_as_of(spec, _as_of())


# -- sector filtering --------------------------------------------------------


class TestSectorFilter:
    def _classification(self) -> SectorClassification:
        return SectorClassification(
            scheme="demo",
            assignments={
                _company_id(APPLE): "Technology",
                _company_id(MSFT): "Technology",
                _company_id(NVDA): "Technology",
            },
        )

    def test_keeps_matching_sector(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="tech",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                SectorFilter(scheme="demo", sector="Technology"),
            ),
        )
        result = builder.build_as_of(
            spec, _as_of(), classifications=(self._classification(),)
        )
        assert len(result.universe) == 3

    def test_unclassified_company_excluded_with_reason(
        self, builder: UniverseBuilder
    ) -> None:
        classification = SectorClassification(
            scheme="demo",
            assignments={_company_id(APPLE): "Technology"},  # MSFT missing
        )
        spec = UniverseSpecification(
            name="tech",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT")),
                SectorFilter(scheme="demo", sector="Technology"),
            ),
        )
        result = builder.build_as_of(spec, _as_of(), classifications=(classification,))
        assert result.universe.company_ids == (_company_id(APPLE),)
        excluded = {e.company_id: e for e in result.construction.excluded}
        assert excluded[_company_id(MSFT)].reason is ExclusionReason.SECTOR_UNCLASSIFIED

    def test_sector_mismatch_excluded_with_detail(
        self, builder: UniverseBuilder
    ) -> None:
        classification = SectorClassification(
            scheme="demo",
            assignments={
                _company_id(APPLE): "Technology",
                _company_id(MSFT): "Financials",
            },
        )
        spec = UniverseSpecification(
            name="tech-only",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT")),
                SectorFilter(scheme="demo", sector="Technology"),
            ),
        )
        result = builder.build_as_of(spec, _as_of(), classifications=(classification,))
        assert result.universe.company_ids == (_company_id(APPLE),)
        excluded = {e.company_id: e for e in result.construction.excluded}
        assert excluded[_company_id(MSFT)].reason is ExclusionReason.SECTOR_MISMATCH
        assert excluded[_company_id(MSFT)].detail == "Financials"

    def test_missing_classification_fails_closed(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="tech",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL",)),
                SectorFilter(scheme="demo", sector="Technology"),
            ),
        )
        with pytest.raises(UniverseSpecificationError, match="SectorClassification"):
            builder.build_as_of(spec, _as_of())  # no classifications supplied


# -- explicit intersection (whitelist role) ---------------------------------


class TestExplicitIntersection:
    def test_second_explicit_filter_intersects(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="intersect",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                ExplicitCompanyFilter(identifiers=("MSFT", "NVDA")),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.universe.company_ids == (_company_id(MSFT), _company_id(NVDA))
        excluded = {e.company_id: e for e in result.construction.excluded}
        assert (
            excluded[_company_id(APPLE)].reason is ExclusionReason.NOT_IN_EXPLICIT_SET
        )


# -- empty result fails closed ----------------------------------------------


class TestEmptyResult:
    def test_all_filtered_out_fails_closed(self, builder: UniverseBuilder) -> None:
        # Threshold no one meets → empty membership → fail closed (like Phase 9.1).
        spec = UniverseSpecification(
            name="impossible",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                CompanyMetricFilter(
                    metric_key="working_capital",
                    period=PERIOD,
                    operator=ComparisonOperator.GT,
                    threshold="999000000000",
                ),
            ),
        )
        with pytest.raises(UniverseConfigurationError):
            builder.build_as_of(spec, _as_of())


# -- determinism & reproducibility ------------------------------------------


class TestDeterminism:
    def test_same_spec_same_construction_id_and_universe_id(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        one = builder.build_as_of(spec, _as_of())
        two = builder.build_as_of(spec, _as_of())
        assert one.construction.construction_id == two.construction.construction_id
        assert one.universe.universe_id == two.universe.universe_id

    def test_construction_id_is_sha256_prefixed(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="s", filters=(ExplicitCompanyFilter(identifiers=("AAPL",)),)
        )
        result = builder.build_as_of(spec, _as_of())
        assert result.construction.construction_id.startswith("sha256:")

    def test_pit_and_revised_have_distinct_construction_ids(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT")),
                _wc_positive(),
            ),
        )
        pit = builder.build_as_of(spec, _as_of())
        rev = builder.build_revised(spec)
        assert pit.construction.construction_id != rev.construction.construction_id
        # Same membership, but the boundary discriminator differs.
        assert pit.universe.universe_id == rev.universe.universe_id
        assert pit.construction.boundary_kind == "pit"
        assert rev.construction.boundary_kind == "rev"

    def test_different_boundary_can_change_membership(
        self, builder: UniverseBuilder
    ) -> None:
        # PIT before availability yields all-undefined → empty (fails closed);
        # PIT after availability yields the positive-WC members.
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT")),
                _wc_positive(),
            ),
        )
        after = builder.build_as_of(spec, _as_of())
        assert len(after.universe) == 2
        with pytest.raises(UniverseConfigurationError):
            builder.build_as_of(spec, parse_utc("2023-01-01T00:00:00Z"))


class TestRevisedConstruction:
    def test_revised_snapshot_is_reproducible(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        one = builder.build_revised(spec)
        two = builder.build_revised(spec)
        assert one.construction.boundary_value == two.construction.boundary_value
        assert one.construction.construction_id == two.construction.construction_id
        # boundary_value is the universe-wide dataset_version_id.
        assert one.construction.boundary_value.startswith("sha256:")


# -- provenance --------------------------------------------------------------


class TestProvenance:
    def test_construction_records_specification_identity(
        self, builder: UniverseBuilder
    ) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        c = result.construction
        assert c.specification_id == spec.specification_id
        assert c.specification_name == "positive-wc"
        assert c.filter_ids == spec.filter_ids
        assert c.construction_version_id.startswith("sha256:")

    def test_applied_filters_tally(self, builder: UniverseBuilder) -> None:
        spec = UniverseSpecification(
            name="positive-wc",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
                _wc_positive(),
            ),
        )
        result = builder.build_as_of(spec, _as_of())
        applied = result.construction.applied_filters
        assert len(applied) == 2
        # Source seeds 3 (received 0), metric filter receives 3, keeps 2, drops 1.
        assert applied[0].received == 0
        assert applied[0].kept == 3
        assert applied[1].received == 3
        assert applied[1].kept == 2
        assert applied[1].excluded == 1

    def test_construction_to_dict_is_serializable_and_complete(
        self, builder: UniverseBuilder
    ) -> None:
        classification = SectorClassification(
            scheme="demo", assignments={_company_id(APPLE): "Technology"}
        )
        spec = UniverseSpecification(
            name="tech",
            filters=(
                ExplicitCompanyFilter(identifiers=("AAPL",)),
                SectorFilter(scheme="demo", sector="Technology"),
            ),
        )
        result = builder.build_as_of(spec, _as_of(), classifications=(classification,))
        record = result.construction.to_dict()
        assert record["construction_id"] == result.construction.construction_id
        assert record["universe_id"] == result.universe.universe_id
        assert record["classification_ids"] == [classification.classification_id]
        assert isinstance(record["applied_filters"], list)
        assert isinstance(record["excluded"], list)


# -- top-level exports -------------------------------------------------------


def test_top_level_exports() -> None:
    from quantforge import (
        CompanyMetricFilter as TLMetric,
    )
    from quantforge import (
        ExplicitCompanyFilter as TLExplicit,
    )
    from quantforge import (
        SectorFilter as TLSector,
    )
    from quantforge import (
        UniverseBuilder as TLBuilder,
    )
    from quantforge import (
        UniverseSpecification as TLSpec,
    )

    assert TLBuilder is UniverseBuilder
    assert TLSpec is UniverseSpecification
    assert TLExplicit is ExplicitCompanyFilter
    assert TLMetric is CompanyMetricFilter
    assert TLSector is SectorFilter
