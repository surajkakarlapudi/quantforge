"""Top-level exports and Workspace wiring for the market layer (section 18)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from quantforge.market.provider import DateRange
from tests.market.builders import (
    FAKE_SOURCE,
    SECURITY_ID,
    bar,
    bars_document,
    make_provider,
)


def test_top_level_pit_revised_exports() -> None:
    import quantforge

    assert hasattr(quantforge, "PitPrice")
    assert hasattr(quantforge, "RevisedPrice")
    from quantforge import PitPrice, RevisedPrice

    assert PitPrice is not RevisedPrice  # type: ignore[comparison-overlap]


def test_market_package_exports() -> None:
    from quantforge.market import (
        DateRange,
        FakeMarketDataProvider,
        MarketDataProvider,
        PitPrice,
        PitPriceSeries,
        PriceAxis,
        PriceEngine,
        RawMarketDocument,
        RevisedPrice,
    )

    # A smoke check that all are importable, distinct symbols.
    names = {
        DateRange,
        FakeMarketDataProvider,
        MarketDataProvider,
        PitPrice,
        PitPriceSeries,
        PriceAxis,
        PriceEngine,
        RawMarketDocument,
        RevisedPrice,
    }
    assert len(names) == 9


def test_workspace_price_engine_is_lazy_and_cached(tmp_path: Path) -> None:
    from quantforge.workspace import Workspace

    ws = Workspace.open(tmp_path)
    engine = ws.price_engine
    assert engine is ws.price_engine  # cached
    # It is a real PriceEngine over <root>/market.
    from quantforge.market.engine import PriceEngine

    assert isinstance(engine, PriceEngine)


def test_workspace_price_engine_end_to_end(tmp_path: Path) -> None:
    from quantforge.market.engine import PriceEngine
    from quantforge.workspace import Workspace

    ws = Workspace.open(tmp_path)
    engine = ws.price_engine
    assert isinstance(engine, PriceEngine)
    provider = make_provider(
        bars_by_security={SECURITY_ID: bars_document([bar("2020-01-02", close="105")])},
    )
    engine.ingest(
        provider,
        SECURITY_ID,
        DateRange(start="2020-01-01", end="2020-12-31"),
        source=FAKE_SOURCE,
        with_actions=False,
    )
    price = engine.price_as_of(
        SECURITY_ID, "2020-01-02", datetime(2024, 1, 1, tzinfo=UTC)
    )
    assert price.is_known
    assert price.value_numeric_str == "105"
