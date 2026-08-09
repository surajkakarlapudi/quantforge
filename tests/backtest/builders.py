"""Offline, obviously-synthetic fixtures fusing fundamentals + market for Phase 12.

A backtest integration test needs *one* data root holding both corpora: the SEC
fundamentals side (filings -> canonical facts -> metrics/factors/universe) and the
market side (PIT bars + corporate actions), with each synthetic filer's fundamentals
``company_id`` matching its market ``security_id`` (so ``company_id_of_security_id``
lines them up). This module builds exactly that, reusing the existing fundamentals
builders (``tests/registry``, ``tests/xbrl``, ``tests/canonical``) and market builders
(``tests/market``). Everything is fictional and offline (Principle 8): two made-up
CIKs (``9999999991`` / ``9999999992``), round-number OHLC values, no network.

Two synthetic filers, both with a 10-K accepted ``2023-11-02`` so their metrics are
PIT-known from late 2023 onward:

* filer A (``current_ratio`` = 200M / 100M = ``2``);
* filer B (``current_ratio`` = 400M / 100M = ``4``).

so a ``descending`` rank on ``current_ratio`` always prefers B, then A. Default market
bars give A closes 10 -> 11 and B closes 20 -> 22 across two months, so a top-1
descending strategy holds B and rides its +10% move (non-trivial statistics).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantforge.availability.store import AvailabilityStore
from quantforge.backtest.engine import BacktestEngine
from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import (
    AccountingPolicy,
    BacktestSpecification,
    CostModel,
    StrategySpecification,
)
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.identity.resolve import CompanyResolver
from quantforge.market.engine import PriceEngine
from quantforge.market.identity import security_id as make_security_id
from quantforge.market.provider import DateRange
from quantforge.metrics.model import MetricPeriod
from quantforge.registry.registry import FilingRegistry
from quantforge.registry.store import RegistryStore
from quantforge.sec.storage import ArtifactStore
from quantforge.universe.filters import ExplicitCompanyFilter
from quantforge.universe.specification import UniverseSpecification
from quantforge.workspace import Workspace
from tests.canonical.builders import canonicalize
from tests.market.builders import (
    FAKE_SOURCE,
    actions_document,
    bar,
    bars_document,
    make_provider,
)
from tests.registry.builders import FilingRow, SubmissionsBuilder
from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
from tests.xbrl.builders import Fact as XbrlFact

# -- fictional identities ----------------------------------------------------

CIK_A = 9999999991
CIK_B = 9999999992
ACCESSION_A = "9999999991-23-000001"
ACCESSION_B = "9999999992-23-000001"
FY_END = "2023-09-30"
USD = Unit("usd", measures=["iso4217:USD"])

SECURITY_A = make_security_id(cik=str(CIK_A), security_class="common-stock")
SECURITY_B = make_security_id(cik=str(CIK_B), security_class="common-stock")

# All bars are knowable by this retrieval instant; a bar cannot be public before it is
# retrieved, so a far-future retrieval keeps every default bar PIT-eligible in 2024.
DEFAULT_RETRIEVED_AT = "2025-01-01T00:00:00Z"

# The signal period: the instant fiscal period the current_ratio is ranked at.
PERIOD = MetricPeriod.instant(FY_END)

# Default two-instant schedule; both instants sit well after the default bars'
# availability, so the latest PIT close at instant 1 is the 2024-01-10 bar and at
# instant 2 is the 2024-02-10 bar.
INSTANT_1 = "2024-01-15T00:00:00Z"
INSTANT_2 = "2024-02-15T00:00:00Z"


def default_bars_a() -> list[dict[str, object]]:
    return [bar("2024-01-10", close="10"), bar("2024-02-10", close="11")]


def default_bars_b() -> list[dict[str, object]]:
    return [bar("2024-01-10", close="20"), bar("2024-02-10", close="22")]


def default_schedule() -> RebalanceSchedule:
    return RebalanceSchedule.of([INSTANT_1, INSTANT_2])


# -- fundamentals seeding ----------------------------------------------------


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


@dataclass(frozen=True)
class Corpus:
    """A populated combined corpus: the workspace plus its two security ids."""

    workspace: Workspace
    security_a: str = SECURITY_A
    security_b: str = SECURITY_B

    @property
    def backtest_engine(self) -> BacktestEngine:
        """The workspace's Phase 12 engine, narrowed from the ``object`` property.

        :attr:`Workspace.backtest_engine` is typed ``object`` (to keep the engine
        import lazy and cycle-free); this accessor asserts the concrete type once so
        every test reads a fully typed :class:`BacktestEngine`.
        """
        engine = self.workspace.backtest_engine
        assert isinstance(engine, BacktestEngine)
        return engine

    @property
    def price_engine(self) -> PriceEngine:
        """The workspace's Phase 11 price engine, narrowed from ``object``."""
        engine = self.workspace.price_engine
        assert isinstance(engine, PriceEngine)
        return engine


def populate(
    root: Path,
    *,
    a_assets: str = "200000000",
    a_liabilities: str = "100000000",
    b_assets: str = "400000000",
    b_liabilities: str = "100000000",
    bars_a: list[dict[str, object]] | None = None,
    bars_b: list[dict[str, object]] | None = None,
    actions_a: list[dict[str, object]] | None = None,
    actions_b: list[dict[str, object]] | None = None,
    retrieved_at: str = DEFAULT_RETRIEVED_AT,
    include_b: bool = True,
    market_a: bool = True,
    market_b: bool = True,
) -> Corpus:
    """Populate both corpora under one root and return the assembled workspace.

    Fundamentals and market data land in the same ``root`` tree, so the workspace's
    lazy ``factor_engine`` / ``price_engine`` / ``UniverseBuilder`` all read one corpus.
    Each filer's ``company_id`` matches its ``security_id`` by construction (same CIK).

    ``market_a`` / ``market_b`` control whether that filer gets a tradable security in
    the market store; set one ``False`` to test the fail-closed "member with no tradable
    security" path (the filer still has fundamentals and is a universe member).
    """
    artifacts = ArtifactStore(root / "sec")
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    canonical = CanonicalFactStore(root / "canonical")

    _add_filer(
        registry,
        canonical,
        cik=CIK_A,
        accession=ACCESSION_A,
        doc="a-20230930.htm",
        assets_current=a_assets,
        liabilities_current=a_liabilities,
    )
    if include_b:
        _add_filer(
            registry,
            canonical,
            cik=CIK_B,
            accession=ACCESSION_B,
            doc="b-20230930.htm",
            assets_current=b_assets,
            liabilities_current=b_liabilities,
        )

    workspace = Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=CompanyResolver(artifacts),
        availability_store=AvailabilityStore(root / "availability"),
    )

    # Market side: ingest each security into <root>/market via the workspace engine.
    securities: list[
        tuple[str, list[dict[str, object]], list[dict[str, object]] | None]
    ]
    securities = []
    if market_a:
        securities.append(
            (SECURITY_A, default_bars_a() if bars_a is None else bars_a, actions_a)
        )
    if include_b and market_b:
        securities.append(
            (SECURITY_B, default_bars_b() if bars_b is None else bars_b, actions_b)
        )

    bars_by = {sid: bars_document(bars, security_id=sid) for sid, bars, _ in securities}
    actions_by = {
        sid: actions_document(actions, security_id=sid)
        for sid, _, actions in securities
        if actions is not None
    }
    provider = make_provider(
        bars_by_security=bars_by,
        actions_by_security=actions_by or None,
        retrieved_at=retrieved_at,
    )
    rng = DateRange(start="2023-01-01", end="2024-12-31")
    price_engine = workspace.price_engine
    assert isinstance(price_engine, PriceEngine)
    for sid, _, actions in securities:
        price_engine.ingest(
            provider,
            sid,
            rng,
            source=FAKE_SOURCE,
            with_actions=actions is not None,
        )
    return Corpus(workspace=workspace)


# -- specification assembly --------------------------------------------------


def universe_spec(*, include_b: bool = True) -> UniverseSpecification:
    """An explicit two-filer (or one-filer) universe keyed by bare CIK strings."""
    identifiers = (str(CIK_A), str(CIK_B)) if include_b else (str(CIK_A),)
    return UniverseSpecification(
        name="phase12-synthetic",
        filters=(ExplicitCompanyFilter(identifiers=identifiers),),
    )


def make_spec(
    engine: BacktestEngine,
    *,
    select_n: int = 1,
    rank: str = "descending",
    schedule: RebalanceSchedule | None = None,
    cost_model: CostModel | None = None,
    accounting: AccountingPolicy | None = None,
    initial_capital: str = "1000000",
    signal: str = "current_ratio",
    include_b: bool = True,
) -> BacktestSpecification:
    """Assemble a fully pinned :class:`BacktestSpecification` for ``engine``'s corpus.

    Pins are re-derived from the engine (exactly as a real caller does): a throwaway
    spec with placeholder pins gives the source company ids, from which the true
    fundamentals + market dataset-version ids are computed and folded into the final
    spec (so ``run`` re-derives them and BT-1 verification passes).
    """
    strategy = StrategySpecification.rank_select_weight(
        signal=signal,
        period=PERIOD,
        select=f"top_n:{select_n}",
        rank=rank,
    )
    universe = universe_spec(include_b=include_b)
    sched = schedule or default_schedule()
    costs = cost_model or CostModel()
    acct = accounting or AccountingPolicy()

    def _spec(fundamentals_id: str, market_id: str) -> BacktestSpecification:
        return BacktestSpecification(
            strategy=strategy,
            schedule=sched,
            universe=universe,
            dataset_version_id=fundamentals_id,
            market_dataset_version_id=market_id,
            cost_model=costs,
            accounting=acct,
            initial_capital=initial_capital,
        )

    placeholder = _spec("pending", "pending")
    fundamentals_id = engine.fundamentals_dataset_version(
        placeholder
    ).dataset_version_id
    market_id = engine.market_dataset_version(placeholder).dataset_version_id
    return _spec(fundamentals_id, market_id)
