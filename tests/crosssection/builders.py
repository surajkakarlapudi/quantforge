"""Offline, obviously-synthetic fixtures for Phase 18 cross-sectional-regression tests.

A cross-sectional regression needs a *wide* cross-section: at each evaluation date
the eligible-member count must clear the degrees-of-freedom floor
``n >= K + intercept + 1``, so a two-filer corpus (enough for the univariate Phase 16
IC) is too small. This module seeds a configurable number of synthetic filers, each
with the current-asset / current-liability / inventory facts that make **two**
independent signals computable (``current_ratio`` and ``quick_ratio``), fused with a
per-filer market history so every member also has a realized forward return.
Everything is fictional and offline (Principle 8): made-up CIKs ``9999999901..``,
round-number values, no network.

The default corpus has five filers (indices 0..4). Filer ``i`` gets
``AssetsCurrent = (2 + i) * 100M``, ``LiabilitiesCurrent = 100M``, ``InventoryNet =
i**2 * 10M`` - so ``current_ratio = 2 + i`` (linear in ``i``) and ``quick_ratio =
(2 + i) - i**2/10`` (quadratic in ``i``) are two distinct, **non-collinear** signals
across the members. The quadratic inventory is deliberate: a *linear* inventory would
make ``quick_ratio`` an exact affine function of ``current_ratio``, so a design with
both signals plus an intercept would be singular; the quadratic term keeps the two
columns independent so the with-intercept regression is well posed. Each filer's
monthly closes rise from a distinct base so every evaluation date resolves a valid
one-trading-day-forward window. The values are round and the per-date design is
hand-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantforge.availability.store import AvailabilityStore
from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.canonical.store import CanonicalFactStore
from quantforge.canonical.version import CanonicalFactVersion
from quantforge.crosssection.engine import CrossSectionalRegressionEngine
from quantforge.crosssection.spec import (
    CrossSectionalRegressionSpecification,
    FactorSpec,
)
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
    bar,
    bars_document,
    make_provider,
)
from tests.registry.builders import FilingRow, SubmissionsBuilder
from tests.xbrl.builders import Ctx, InstanceBuilder, Unit
from tests.xbrl.builders import Fact as XbrlFact

FY_END = "2023-09-30"
PERIOD: MetricPeriod = MetricPeriod.instant(FY_END)
USD = Unit("usd", measures=["iso4217:USD"])

# Two evaluation instants; each picks a distinct base close and (with a one-trading-day
# horizon over the stored monthly axis) a distinct valid forward window - mirroring the
# Phase 16 diagnostics builders.
EVAL_1 = "2024-01-15T00:00:00Z"
EVAL_2 = "2024-02-15T00:00:00Z"

# A far-future retrieval keeps every default bar PIT-eligible in 2024.
DEFAULT_RETRIEVED_AT = "2025-01-01T00:00:00Z"

_BASE_CIK = 9999999901


def cik_for(index: int) -> int:
    """The synthetic CIK of the ``index``-th filer (0-based)."""
    return _BASE_CIK + index


def security_for(index: int) -> str:
    """The market ``security_id`` of the ``index``-th filer."""
    return make_security_id(cik=str(cik_for(index)), security_class="common-stock")


def default_schedule() -> RebalanceSchedule:
    return RebalanceSchedule.of([EVAL_1, EVAL_2])


def default_bars(index: int) -> list[dict[str, object]]:
    """Four monthly closes for the ``index``-th filer, rising from a distinct base.

    Filer ``i`` starts at close ``10 + 10*i`` and rises by ``1`` each month, so every
    member has four stored closes and every evaluation date resolves a forward window.
    """
    base = 10 + 10 * index
    return [
        bar("2024-01-10", close=str(base)),
        bar("2024-02-10", close=str(base + 1)),
        bar("2024-03-10", close=str(base + 2)),
        bar("2024-04-10", close=str(base + 3)),
    ]


def _add_filer(
    registry: FilingRegistry,
    canonical: CanonicalFactStore,
    *,
    cik: int,
    assets_current: str,
    liabilities_current: str,
    inventory: str,
) -> None:
    """Register one 10-K filer and persist a current-ratio / quick-ratio fact set."""
    accession = f"{cik}-23-000001"
    subs = SubmissionsBuilder(cik).add(
        FilingRow(
            accession=accession,
            form="10-K",
            filing_date="2023-11-03",
            report_date=FY_END,
            acceptance="2023-11-02T18:01:14.000Z",
            primary_document=f"{cik}-20230930.htm",
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
        .with_fact(
            XbrlFact("us-gaap:InventoryNet", "i", value=inventory, unit_ref="usd")
        )
    )
    result = canonicalize(instance, cik=cik, accession=accession)
    canonical.write_instance(result, CanonicalFactVersion().transformation_version_id)


@dataclass(frozen=True)
class Corpus:
    """A populated combined corpus: the workspace plus the seeded filer count."""

    workspace: Workspace
    n_filers: int

    @property
    def price_engine(self) -> PriceEngine:
        engine = self.workspace.price_engine
        assert isinstance(engine, PriceEngine)
        return engine


def populate(
    root: Path,
    *,
    n_filers: int = 5,
    bars_by_index: dict[int, list[dict[str, object]]] | None = None,
    market_indices: set[int] | None = None,
    retrieved_at: str = DEFAULT_RETRIEVED_AT,
) -> Corpus:
    """Populate both corpora under one root and return the assembled workspace.

    ``n_filers`` filers are seeded (indices ``0..n_filers-1``); filer ``i`` gets
    ``current_ratio = 2 + i`` and a distinct ``quick_ratio``. ``market_indices``
    (default: all) selects which filers get a tradable security - drop one to exercise
    the fail-closed "member with no tradable security" forward-return path.
    ``bars_by_index`` overrides a filer's price history.
    """
    market = set(range(n_filers)) if market_indices is None else market_indices
    artifacts = ArtifactStore(root / "sec")
    registry = FilingRegistry(
        RegistryStore(root / "registry"), artifact_store=artifacts
    )
    canonical = CanonicalFactStore(root / "canonical")

    for index in range(n_filers):
        _add_filer(
            registry,
            canonical,
            cik=cik_for(index),
            assets_current=str((2 + index) * 100_000_000),
            liabilities_current="100000000",
            inventory=str(index * index * 10_000_000),
        )

    workspace = Workspace(
        artifact_store=artifacts,
        registry=registry,
        canonical_store=canonical,
        resolver=CompanyResolver(artifacts),
        availability_store=AvailabilityStore(root / "availability"),
    )

    securities = [
        (
            security_for(index),
            (
                default_bars(index)
                if bars_by_index is None or index not in bars_by_index
                else bars_by_index[index]
            ),
        )
        for index in range(n_filers)
        if index in market
    ]
    bars_by = {sid: bars_document(bars, security_id=sid) for sid, bars in securities}
    provider = make_provider(bars_by_security=bars_by, retrieved_at=retrieved_at)
    rng = DateRange(start="2023-01-01", end="2024-12-31")
    price_engine = workspace.price_engine
    assert isinstance(price_engine, PriceEngine)
    for sid, _ in securities:
        price_engine.ingest(provider, sid, rng, source=FAKE_SOURCE, with_actions=False)
    return Corpus(workspace=workspace, n_filers=n_filers)


def crosssection_engine(corpus: Corpus) -> CrossSectionalRegressionEngine:
    """The workspace's Phase 18 engine, narrowed from the ``object`` property."""
    engine = corpus.workspace.crosssection_engine
    assert isinstance(engine, CrossSectionalRegressionEngine)
    return engine


def universe_spec(*, n_filers: int) -> UniverseSpecification:
    """An explicit ``n_filers``-member universe keyed by bare CIK strings."""
    identifiers = tuple(str(cik_for(index)) for index in range(n_filers))
    return UniverseSpecification(
        name="phase18-synthetic",
        filters=(ExplicitCompanyFilter(identifiers=identifiers),),
    )


def make_spec(
    engine: CrossSectionalRegressionEngine,
    *,
    n_filers: int = 5,
    factors: tuple[FactorSpec, ...] | None = None,
    forward_horizon: str = "1d",
    include_intercept: bool = True,
    schedule: RebalanceSchedule | None = None,
    name: str = "phase18-synthetic",
) -> CrossSectionalRegressionSpecification:
    """Assemble a fully pinned specification for the corpus.

    Pins are re-derived from the engine exactly as a real caller does: a throwaway spec
    with placeholder pins gives the source company ids, from which the true
    fundamentals + market dataset-version ids are computed and folded into the final
    spec (so ``estimate`` re-derives them and XS-1 verification passes).
    """
    facts = factors or (
        FactorSpec(metric_key="current_ratio", period=PERIOD),
        FactorSpec(metric_key="quick_ratio", period=PERIOD),
    )
    universe = universe_spec(n_filers=n_filers)
    sched = schedule or default_schedule()

    def _spec(
        fundamentals_id: str, market_id: str
    ) -> CrossSectionalRegressionSpecification:
        return CrossSectionalRegressionSpecification(
            name=name,
            factors=facts,
            universe=universe,
            schedule=sched,
            forward_horizon=forward_horizon,
            dataset_version_id=fundamentals_id,
            market_dataset_version_id=market_id,
            include_intercept=include_intercept,
        )

    placeholder = _spec("pending", "pending")
    fundamentals_id = engine.fundamentals_dataset_version(
        placeholder
    ).dataset_version_id
    market_id = engine.market_dataset_version(placeholder).dataset_version_id
    return _spec(fundamentals_id, market_id)


__all__ = [
    "DEFAULT_RETRIEVED_AT",
    "EVAL_1",
    "EVAL_2",
    "FY_END",
    "PERIOD",
    "Corpus",
    "cik_for",
    "crosssection_engine",
    "default_bars",
    "default_schedule",
    "make_spec",
    "populate",
    "security_for",
    "universe_spec",
]
