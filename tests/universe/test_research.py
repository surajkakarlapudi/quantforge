"""Tests for the Phase 9 research layer: inspection, summary, comparison, export.

Two altitudes, matching the layer's own split:

* **Offline** — over universes assembled from resolved identities
  (:meth:`Universe.from_identities`), covering inspection, the bare-universe
  :class:`UniverseSummary`, membership :class:`UniverseComparison`, tabular export,
  and determinism, with no backend.
* **Constructed** — over a genuine Phase 1/2/4 backend driven through
  :class:`UniverseBuilder` (the fixture mirrors ``test_builder.py``), covering
  construction provenance in the summary, the exclusion inspection surface, the
  export tagging, and — critically — that PIT and REVISED constructions are never
  silently treated as the same knowledge state.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from quantforge.availability.store import AvailabilityStore
from quantforge.availability.timestamps import parse_utc
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.identity.model import CompanyIdentity, ResolutionSource
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
from quantforge.universe import (
    CompanyMetricFilter,
    ComparisonOperator,
    ExplicitCompanyFilter,
    Universe,
    UniverseBuilder,
    UniverseComparison,
    UniverseSpecification,
    UniverseSummary,
)
from quantforge.workspace import Workspace

# -- offline fixtures --------------------------------------------------------

APPLE = 320193
MSFT = 789019
NVDA = 1045810
BERKSHIRE = 1067983  # deliberately never populated (no facts)
FY_END = "2023-09-30"
PERIOD = MetricPeriod.instant(FY_END)


def _identity(cik: int, ticker: str, name: str) -> CompanyIdentity:
    return CompanyIdentity.from_cik(
        cik,
        resolved_from=ticker,
        source=ResolutionSource.TICKER,
        ticker=ticker,
        name=name,
    )


def _apple() -> CompanyIdentity:
    return _identity(APPLE, "AAPL", "Apple Inc.")


def _msft() -> CompanyIdentity:
    return _identity(MSFT, "MSFT", "MICROSOFT CORP")


def _nvda() -> CompanyIdentity:
    return _identity(NVDA, "NVDA", "NVIDIA CORP")


# -- inspection --------------------------------------------------------------


class TestInspection:
    def test_members_are_full_identities(self) -> None:
        universe = Universe.from_identities([_apple(), _msft()])
        members = universe.members()
        assert tuple(m.company_id for m in members) == (
            _company_id(APPLE),
            _company_id(MSFT),
        )
        # The identity-layer value object is reused unchanged (no new model).
        assert members[0].ticker == "AAPL"
        assert members[0].source is ResolutionSource.TICKER

    def test_company_ids_and_len(self) -> None:
        universe = Universe.from_identities([_apple(), _msft(), _nvda()])
        assert universe.company_ids == (
            _company_id(APPLE),
            _company_id(MSFT),
            _company_id(NVDA),
        )
        assert len(universe) == 3

    def test_contains_is_by_canonical_id(self) -> None:
        universe = Universe.from_identities([_apple()])
        assert universe.contains(_company_id(APPLE))
        assert not universe.contains(_company_id(MSFT))
        # A ticker is not an identity — never a member key.
        assert not universe.contains("AAPL")

    def test_resolved_from_provenance_survives_inspection(self) -> None:
        universe = Universe.from_identities([_apple()])
        (member,) = universe.members()
        assert member.resolved_from == "AAPL"


# -- summary (describe) ------------------------------------------------------


class TestSummary:
    def test_bare_universe_summary_fields(self) -> None:
        universe = Universe.from_identities([_apple(), _msft()])
        summary = universe.describe()
        assert isinstance(summary, UniverseSummary)
        assert summary.member_count == 2
        assert summary.company_ids == (_company_id(APPLE), _company_id(MSFT))
        assert summary.universe_id == universe.universe_id
        assert summary.builder_version_id.startswith("sha256:")
        assert not summary.is_constructed
        # Construction-only fields are absent for a bare universe.
        assert summary.construction_id is None
        assert summary.mode is None

    def test_summary_is_deterministic(self) -> None:
        a = Universe.from_identities([_apple(), _msft()]).describe()
        b = Universe.from_identities([_apple(), _msft()]).describe()
        assert a == b
        assert a.to_dict() == b.to_dict()

    def test_summary_to_dict_has_stable_shape(self) -> None:
        summary = Universe.from_identities([_apple()]).describe()
        record = summary.to_dict()
        # All construction-only keys present (null), so the shape never varies.
        for key in (
            "construction_id",
            "specification_id",
            "mode",
            "boundary_value",
            "exclusions_by_reason",
        ):
            assert key in record
        assert record["mode"] is None
        assert record["exclusions_by_reason"] == {}

    def test_summary_does_not_compute_financials(self) -> None:
        # The summary is structural only — no metric/value keys leak in.
        record = Universe.from_identities([_apple()]).describe().to_dict()
        forbidden = {"value", "value_numeric", "metric", "price", "market_cap"}
        assert forbidden.isdisjoint(record.keys())


# -- comparison --------------------------------------------------------------


class TestComparison:
    def test_identical_universes(self) -> None:
        left = Universe.from_identities([_apple(), _msft()])
        right = Universe.from_identities([_apple(), _msft()])
        cmp = left.compare(right)
        assert cmp.is_identical
        assert cmp.added == ()
        assert cmp.removed == ()
        assert cmp.retained == (_company_id(APPLE), _company_id(MSFT))

    def test_completely_different_universes(self) -> None:
        left = Universe.from_identities([_apple()])
        right = Universe.from_identities([_nvda()])
        cmp = left.compare(right)
        assert cmp.added == (_company_id(NVDA),)
        assert cmp.removed == (_company_id(APPLE),)
        assert cmp.retained == ()
        assert not cmp.is_identical

    def test_partial_overlap_added_and_removed(self) -> None:
        left = Universe.from_identities([_apple(), _msft()])
        right = Universe.from_identities([_msft(), _nvda()])
        cmp = left.compare(right)
        assert cmp.removed == (_company_id(APPLE),)
        assert cmp.retained == (_company_id(MSFT),)
        assert cmp.added == (_company_id(NVDA),)
        assert (cmp.removed_count, cmp.retained_count, cmp.added_count) == (1, 1, 1)

    def test_ordering_is_deterministic_off_source_universes(self) -> None:
        # removed/retained follow the LEFT order; added follows the RIGHT order.
        left = Universe.from_identities([_nvda(), _apple(), _msft()])
        right = Universe.from_identities([_msft(), _apple()])
        cmp = left.compare(right)
        assert cmp.removed == (_company_id(NVDA),)
        assert cmp.retained == (_company_id(APPLE), _company_id(MSFT))

    def test_comparison_is_deterministic(self) -> None:
        left = Universe.from_identities([_apple(), _msft()])
        right = Universe.from_identities([_msft(), _nvda()])
        assert left.compare(right).to_dict() == left.compare(right).to_dict()

    def test_bare_comparison_has_no_mode_claim(self) -> None:
        left = Universe.from_identities([_apple()])
        right = Universe.from_identities([_apple()])
        cmp = left.compare(right)
        assert cmp.left_mode is None
        assert cmp.right_mode is None
        assert cmp.mode_mismatch is None  # unknown, so no claim

    def test_comparison_serializes(self) -> None:
        left = Universe.from_identities([_apple(), _msft()])
        right = Universe.from_identities([_msft()])
        record = left.compare(right).to_dict()
        assert record["removed"] == [_company_id(APPLE)]
        assert record["retained"] == [_company_id(MSFT)]
        assert record["added"] == []
        assert record["is_identical"] is False


# -- export ------------------------------------------------------------------


class TestExport:
    def test_to_records_is_ordered_and_canonical(self) -> None:
        universe = Universe.from_identities([_apple(), _msft()])
        records = universe.to_records()
        assert [r["company_id"] for r in records] == [
            _company_id(APPLE),
            _company_id(MSFT),
        ]
        # company_id is authoritative; ticker/name are descriptive columns.
        assert records[0]["ticker"] == "AAPL"
        assert records[0]["cik"] == "320193"

    def test_to_records_is_deterministic(self) -> None:
        u = Universe.from_identities([_apple(), _msft()])
        assert u.to_records() == u.to_records()

    def test_to_dict_round_trips_membership(self) -> None:
        universe = Universe.from_identities([_apple(), _msft()])
        record = universe.to_dict()
        members = cast(list[dict[str, object]], record["members"])
        assert [m["company_id"] for m in members] == list(universe.company_ids)

    def test_records_contain_only_canonical_authority(self) -> None:
        # Every row carries company_id; ticker may be None but is never the key.
        universe = Universe.from_identities([_apple()])
        (row,) = universe.to_records()
        assert row["company_id"] == _company_id(APPLE)


# -- determinism across input ordering ---------------------------------------


class TestDeterminism:
    def test_same_members_different_order_are_distinct_but_stable(self) -> None:
        # Order is semantically meaningful for a universe (it drives id + cell order),
        # so a different order is a different universe — but each is reproducible.
        one = Universe.from_identities([_apple(), _msft()])
        two = Universe.from_identities([_msft(), _apple()])
        assert one.universe_id != two.universe_id
        assert (
            one.describe() == Universe.from_identities([_apple(), _msft()]).describe()
        )

    def test_comparison_added_removed_independent_of_set_iteration(self) -> None:
        # Build the same logical diff many times; the ordered outputs never vary.
        left = Universe.from_identities([_apple(), _msft(), _nvda()])
        right = Universe.from_identities([_nvda(), _apple()])
        results = {
            cast(list[str], left.compare(right).to_dict()["removed"])[0]
            for _ in range(20)
        }
        assert results == {_company_id(MSFT)}


# ===========================================================================
# Constructed universes — real backend (mirrors test_builder.py)
# ===========================================================================

USD_MEASURES = ["iso4217:USD"]
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
    from tests.canonical.builders import canonicalize
    from tests.registry.builders import FilingRow, SubmissionsBuilder
    from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
    from tests.xbrl.builders import Fact as XbrlFact

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
        .with_unit(Unit("usd", measures=USD_MEASURES))
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
    # working_capital: AAPL 100M, MSFT 500M, NVDA -40M.
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
    return Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=CompanyResolver(artifacts),
        availability_store=AvailabilityStore(root / "availability"),
    )


def _as_of() -> datetime:
    return parse_utc("2024-06-01T00:00:00Z")


@pytest.fixture
def builder(tmp_path: Path) -> UniverseBuilder:
    return UniverseBuilder(_populate(tmp_path))


def _positive_wc_spec() -> UniverseSpecification:
    return UniverseSpecification(
        name="positive-working-capital",
        filters=(
            ExplicitCompanyFilter(identifiers=("AAPL", "MSFT", "NVDA")),
            CompanyMetricFilter(
                metric_key="working_capital",
                period=PERIOD,
                operator=ComparisonOperator.GT,
                threshold="0",
            ),
        ),
    )


class TestConstructionSummary:
    def test_describe_carries_construction_provenance(
        self, builder: UniverseBuilder
    ) -> None:
        result = builder.build_as_of(_positive_wc_spec(), _as_of())
        summary = result.describe()
        assert summary.is_constructed
        assert summary.name == "positive-working-capital"
        assert summary.construction_id == result.construction.construction_id
        assert summary.specification_id == result.construction.specification_id
        assert summary.mode == "pit"
        # NVDA excluded on the metric threshold — surfaced in the summary counts.
        assert summary.excluded_count == 1
        assert summary.exclusions_by_reason == {"metric_threshold_not_met": 1}
        assert len(summary.applied_filters) == 2

    def test_construction_summary_is_deterministic(
        self, builder: UniverseBuilder
    ) -> None:
        spec = _positive_wc_spec()
        one = builder.build_as_of(spec, _as_of()).describe()
        two = builder.build_as_of(spec, _as_of()).describe()
        assert one.to_dict() == two.to_dict()

    def test_summary_mode_distinguishes_pit_from_revised(
        self, builder: UniverseBuilder
    ) -> None:
        spec = _positive_wc_spec()
        pit = builder.build_as_of(spec, _as_of()).describe()
        rev = builder.build_revised(spec).describe()
        assert pit.mode == "pit"
        assert rev.mode == "rev"


class TestConstructionInspection:
    def test_provenance_returns_the_record(self, builder: UniverseBuilder) -> None:
        result = builder.build_as_of(_positive_wc_spec(), _as_of())
        assert result.provenance() is result.construction

    def test_excluded_for_explains_a_non_member(self, builder: UniverseBuilder) -> None:
        result = builder.build_as_of(_positive_wc_spec(), _as_of())
        drops = result.construction.excluded_for(_company_id(NVDA))
        assert len(drops) == 1
        assert drops[0].reason.value == "metric_threshold_not_met"
        # A member has no exclusion record.
        assert result.construction.excluded_for(_company_id(APPLE)) == ()

    def test_records_are_tagged_with_construction_and_mode(
        self, builder: UniverseBuilder
    ) -> None:
        result = builder.build_as_of(_positive_wc_spec(), _as_of())
        rows = result.to_records()
        assert all(
            r["construction_id"] == result.construction.construction_id for r in rows
        )
        assert all(r["mode"] == "pit" for r in rows)
        assert [r["company_id"] for r in rows] == list(result.universe.company_ids)


class TestConstructionComparison:
    def test_compare_same_membership_flags_mode_mismatch(
        self, builder: UniverseBuilder
    ) -> None:
        # PIT and REVISED here resolve to the same members, but the comparison must
        # NOT silently treat them as the same knowledge state.
        spec = _positive_wc_spec()
        pit = builder.build_as_of(spec, _as_of())
        rev = builder.build_revised(spec)
        cmp = pit.compare(rev)
        assert cmp.is_identical  # same membership
        assert cmp.left_mode == "pit"
        assert cmp.right_mode == "rev"
        assert cmp.mode_mismatch is True

    def test_compare_same_mode_no_mismatch(self, builder: UniverseBuilder) -> None:
        spec = _positive_wc_spec()
        a = builder.build_as_of(spec, _as_of())
        b = builder.build_as_of(spec, _as_of())
        cmp = a.compare(b)
        assert cmp.mode_mismatch is False
        assert cmp.is_identical

    def test_comparison_of_constructions_serializes(
        self, builder: UniverseBuilder
    ) -> None:
        spec = _positive_wc_spec()
        pit = builder.build_as_of(spec, _as_of())
        rev = builder.build_revised(spec)
        record = pit.compare(rev).to_dict()
        assert record["mode_mismatch"] is True
        assert record["left_mode"] == "pit"
        assert record["right_mode"] == "rev"


def test_top_level_research_exports() -> None:
    from quantforge import UniverseComparison as TLComparison
    from quantforge import UniverseSummary as TLSummary

    assert TLSummary is UniverseSummary
    assert TLComparison is UniverseComparison
