"""End-to-end integration for the Phase 8 factor engine over the real backend.

Populates a genuine Phase 1 artifact store, Phase 2 registry, and Phase 4 canonical
store for a small **explicit** universe of two filers, then drives factors through
:class:`FactorEngine` and :class:`Workspace` — proving the engine fans Phase 7 out
across the universe, preserves order, records one cell per member (mixed
KNOWN/UNDEFINED, never dropped), keeps PIT and REVISED distinct, applies transforms
over KNOWN cells only, reproduces the ``research_result_id`` + values, and wires
onto the workspace additively without disturbing the metric/fact paths.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from openfinance.availability.store import AvailabilityStore
from openfinance.availability.timestamps import parse_utc
from openfinance.canonical.store import CanonicalFactStore
from openfinance.canonical.version import CanonicalFactVersion
from openfinance.factors.engine import FactorEngine
from openfinance.factors.model import PitFactor, RevisedFactor
from openfinance.factors.transform import Transform
from openfinance.factors.universe import Universe
from openfinance.identity.resolve import CompanyResolver
from openfinance.metrics.model import MetricPeriod, MetricStatus, RevisedMetricValue
from openfinance.registry.identity import company_id as _company_id
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
MSFT = 789019
FY_END = "2023-09-30"
FY_START = "2022-10-01"
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
    """Register one 10-K filer and persist a current-ratio-computable fact set."""
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


def _populate(root: Path, *, msft_liabilities: str = "500000000") -> Workspace:
    artifacts = ArtifactStore(root / "sec")
    _store_tickers(artifacts)
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    canonical = CanonicalFactStore(root / "canonical")

    # Apple: current ratio 200M / 100M = 2.
    _add_filer(
        registry,
        canonical,
        cik=APPLE,
        accession="0000320193-23-000106",
        doc="aapl-20230930.htm",
        assets_current="200000000",
        liabilities_current="100000000",
    )
    # Microsoft: current ratio 1000M / 500M = 2 by default (overridable).
    _add_filer(
        registry,
        canonical,
        cik=MSFT,
        accession="0000789019-23-000105",
        doc="msft-20230930.htm",
        assets_current="1000000000",
        liabilities_current=msft_liabilities,
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
def engine(workspace: Workspace) -> FactorEngine:
    return FactorEngine(workspace)


@pytest.fixture
def universe() -> Universe:
    # Declared order Apple, then Microsoft — the cross-section's cell order.
    return Universe.of(APPLE, MSFT)


class TestPitFactor:
    def test_returns_pit_type(self, engine: FactorEngine, universe: Universe) -> None:
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        assert isinstance(f, PitFactor)
        assert f.as_of == _as_of()

    def test_one_cell_per_member_in_universe_order(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        assert [c.company_id for c in f.cells] == [
            _company_id(APPLE),
            _company_id(MSFT),
        ]

    def test_known_cells_match_standalone_phase7(
        self, engine: FactorEngine, universe: Universe, workspace: Workspace
    ) -> None:
        from openfinance.registry.identity import cik_from_company_id

        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        metric_engine = workspace.metric_engine
        for cell in f.cells:
            standalone = metric_engine.metric_as_of(  # type: ignore[attr-defined]
                "current_ratio", cik_from_company_id(cell.company_id), PERIOD, _as_of()
            )
            assert cell.metric.value_numeric_str == standalone.value_numeric_str
            assert cell.metric.status is standalone.status

    def test_missing_filer_is_undefined_cell_never_dropped(
        self, engine: FactorEngine
    ) -> None:
        # A filer with no facts in the workspace is a first-class UNDEFINED cell.
        universe = Universe.of(APPLE, 1067983)  # Berkshire — not populated
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        assert len(f.cells) == 2
        missing = f.cells[1]
        assert missing.company_id == _company_id(1067983)
        assert missing.metric.status is MetricStatus.UNDEFINED

    def test_before_availability_is_undefined(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        f = engine.factor_as_of(
            "current_ratio", universe, PERIOD, parse_utc("2023-01-01T00:00:00Z")
        )
        assert all(c.metric.status is MetricStatus.UNDEFINED for c in f.cells)

    def test_summary_counts_known_and_reasons(self, engine: FactorEngine) -> None:
        universe = Universe.of(APPLE, 1067983)
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        assert f.summary.total == 2
        assert f.summary.known == 1
        assert sum(f.summary.undefined_by_reason.values()) == 1

    def test_naive_as_of_rejected(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        from openfinance.availability.errors import ModeError

        with pytest.raises(ModeError):
            engine.factor_as_of(
                "current_ratio",
                universe,
                PERIOD,
                datetime(2024, 6, 1),  # naive
            )


class TestTransforms:
    def test_zscore_over_known_cells(self, tmp_path: Path) -> None:
        # Distinct ratios so the population has non-zero spread: AAPL=2, MSFT=4.
        ws = _populate(tmp_path, msft_liabilities="250000000")
        engine = FactorEngine(ws)
        universe = Universe.of(APPLE, MSFT)
        f = engine.factor_as_of(
            "current_ratio", universe, PERIOD, _as_of(), transform=Transform.zscore()
        )
        transformed = {c.company_id: c.transformed_value_numeric_str for c in f.cells}
        # Two-point population is symmetric about the mean: ±1 (population stdev).
        assert transformed[_company_id(APPLE)] == "-1"
        assert transformed[_company_id(MSFT)] == "1"

    def test_undefined_cell_excluded_from_population(
        self, engine: FactorEngine
    ) -> None:
        universe = Universe.of(APPLE, 1067983)  # one KNOWN, one UNDEFINED
        f = engine.factor_as_of(
            "current_ratio", universe, PERIOD, _as_of(), transform=Transform.rank()
        )
        by_id = {c.company_id: c for c in f.cells}
        # The lone KNOWN cell ranks 1; the UNDEFINED cell has no transformed value.
        assert by_id[_company_id(APPLE)].transformed_value_numeric_str == "1"
        assert by_id[_company_id(1067983)].transformed_value_numeric_str is None


class TestRevisedFactor:
    def test_returns_revised_type_with_shared_snapshot(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        f = engine.revised_factor("current_ratio", universe, PERIOD)
        assert isinstance(f, RevisedFactor)
        # Every cell records the same universe-wide dataset_version_id (§8.1).
        for cell in f.cells:
            assert isinstance(cell.metric, RevisedMetricValue)
            assert cell.metric.dataset_version_id == f.dataset_version_id

    def test_universe_wide_snapshot_is_reproducible(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        one = engine.revised_factor("current_ratio", universe, PERIOD)
        two = engine.revised_factor("current_ratio", universe, PERIOD)
        assert one.dataset_version_id == two.dataset_version_id


class TestReinterpret:
    def test_reinterpret_as_pit_reevaluates_whole_vector(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        revised = engine.revised_factor("current_ratio", universe, PERIOD)
        pit = revised.reinterpret_as_pit(engine, _as_of())
        assert isinstance(pit, PitFactor)
        assert [c.company_id for c in pit.cells] == [
            _company_id(APPLE),
            _company_id(MSFT),
        ]
        assert all(c.metric.status is MetricStatus.KNOWN for c in pit.cells)


class TestReproducibility:
    def test_same_request_same_research_result_id_and_values(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        one = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        two = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        assert one.research_result_id == two.research_result_id
        assert one.research_result.result_hash == two.research_result.result_hash

    def test_research_result_is_persisted_and_round_trips(
        self, engine: FactorEngine, universe: Universe, workspace: Workspace
    ) -> None:
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        stored = workspace.research_result_store.read(f.research_result_id)
        assert stored is not None
        assert stored.to_dict() == f.research_result.to_dict()

    def test_research_result_maps_datamodel_fields(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        f = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        data = f.research_result.to_dict()
        # §9 alias: metric_engine_version_id IS the factor_version.
        assert data["factor_version"] == data["metric_engine_version_id"]
        query_params = data["query_params"]
        assert isinstance(query_params, dict)
        assert query_params["metric_key"] == "current_ratio"
        assert data["as_of_timestamp"] is not None
        # strategy_version is reserved for the deferred backtester (§1.2) — absent.
        assert "strategy_version" not in data


class TestDistinctBoundaries:
    def test_pit_and_revised_have_different_research_result_ids(
        self, engine: FactorEngine, universe: Universe
    ) -> None:
        pit = engine.factor_as_of("current_ratio", universe, PERIOD, _as_of())
        rev = engine.revised_factor("current_ratio", universe, PERIOD)
        assert pit.research_result_id != rev.research_result_id


class TestAdditiveWiring:
    def test_factor_engine_cached_on_workspace(self, workspace: Workspace) -> None:
        assert workspace.factor_engine is workspace.factor_engine

    def test_metric_and_fact_paths_undisturbed(self, workspace: Workspace) -> None:
        # Building factors must not disturb the Phase 7 metric path.
        metric_engine = workspace.metric_engine
        m = metric_engine.metric_as_of(  # type: ignore[attr-defined]
            "current_ratio", APPLE, PERIOD, _as_of()
        )
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"

    def test_research_store_under_data_root_not_repo(
        self, workspace: Workspace, tmp_path: Path
    ) -> None:
        store = workspace.research_result_store
        assert Path(store.root) == tmp_path
