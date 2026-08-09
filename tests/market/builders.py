"""Deterministic, obviously-synthetic fixtures for Phase 11 market-data tests.

Everything here is fictional and offline (Principle 8, proposal section 19): a made-up
CIK (``9999999999``), the fictional ticker ``ZZZZ`` on a fictional exchange ``TEST``,
round-number OHLCV values, and no network. The helpers assemble the provider-neutral
*canonical vendor JSON* the :class:`~quantforge.market.canonical.MarketCanonicalizer`
consumes, wrap it in a :class:`~quantforge.market.provider.FakeMarketDataProvider`, and
build a :class:`~quantforge.market.engine.PriceEngine` over a ``tmp_path`` store so a
whole PIT round-trip runs with no real data anywhere near it.
"""

from __future__ import annotations

import json
from pathlib import Path

from quantforge.market.engine import PriceEngine
from quantforge.market.identity import security_id as make_security_id
from quantforge.market.model import MarketDataSource
from quantforge.market.provider import DateRange, FakeMarketDataProvider
from quantforge.market.store import MarketDataStore

# A fictional issuer + instrument. The CIK is not a real EDGAR CIK; the class is a
# stable, normalizable label. Ticker ZZZZ / exchange TEST are obviously synthetic.
FAKE_CIK = "9999999999"
FAKE_CLASS = "common-stock"
FAKE_TICKER = "ZZZZ"
FAKE_EXCHANGE = "TEST"

SECURITY_ID = make_security_id(cik=FAKE_CIK, security_class=FAKE_CLASS)

# A synthetic source; USD, standard US-eastern calendar, dissemination NOT trusted.
FAKE_SOURCE = MarketDataSource(
    source_id="fake-market-data",
    name="Fake Market Data (test)",
    default_currency="USD",
)


def bars_document(
    bars: list[dict[str, object]],
    *,
    security_id: str = SECURITY_ID,
    currency: str = "USD",
    security_type: str = "common-stock",
    ticker: str = FAKE_TICKER,
    exchange: str = FAKE_EXCHANGE,
    effective_from: str = "2020-01-02",
) -> bytes:
    """Serialize a canonical daily-bar document for one instrument to bytes."""
    document = {
        "security_id": security_id,
        "security_type": security_type,
        "currency": currency,
        "ticker_history": [
            {
                "ticker": ticker,
                "exchange": exchange,
                "effective_from": effective_from,
                "effective_to": None,
            }
        ],
        "bars": bars,
    }
    return json.dumps(document).encode("utf-8")


def actions_document(
    actions: list[dict[str, object]],
    *,
    security_id: str = SECURITY_ID,
) -> bytes:
    """Serialize a canonical corporate-action document for one instrument to bytes."""
    document = {"security_id": security_id, "actions": actions}
    return json.dumps(document).encode("utf-8")


def bar(
    trading_date: str,
    *,
    close: str,
    open_: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: str | None = None,
    observation_timestamp_utc: str | None = None,
    currency: str | None = None,
) -> dict[str, object]:
    """One canonical daily bar. Only the fields provided are emitted (per-field)."""
    row: dict[str, object] = {"trading_date": trading_date, "close": close}
    if open_ is not None:
        row["open"] = open_
    if high is not None:
        row["high"] = high
    if low is not None:
        row["low"] = low
    if volume is not None:
        row["volume"] = volume
    if observation_timestamp_utc is not None:
        row["observation_timestamp_utc"] = observation_timestamp_utc
    if currency is not None:
        row["currency"] = currency
    return row


def make_provider(
    *,
    bars_by_security: dict[str, bytes],
    actions_by_security: dict[str, bytes] | None = None,
    retrieved_at: str = "2024-01-01T00:00:00Z",
) -> FakeMarketDataProvider:
    """A synthetic provider serving the given fixture bytes, no network."""
    return FakeMarketDataProvider(
        bars_by_security=bars_by_security,
        actions_by_security=actions_by_security,
        retrieved_at=retrieved_at,
    )


def make_engine(root: Path) -> PriceEngine:
    """A :class:`PriceEngine` over a fresh file store under ``root/market``."""
    return PriceEngine(MarketDataStore(root / "market"))


def ingest_bars(
    root: Path,
    bars: list[dict[str, object]],
    *,
    actions: list[dict[str, object]] | None = None,
    retrieved_at: str = "2024-01-01T00:00:00Z",
    security_id: str = SECURITY_ID,
    date_range: DateRange | None = None,
) -> PriceEngine:
    """End-to-end: build a provider from ``bars``/``actions`` and ingest one instrument.

    Returns the :class:`PriceEngine` (with the instrument persisted) so a test can go
    straight to :meth:`PriceEngine.price_as_of` and friends.
    """
    engine = make_engine(root)
    bars_by = {security_id: bars_document(bars, security_id=security_id)}
    actions_by = (
        {security_id: actions_document(actions, security_id=security_id)}
        if actions is not None
        else None
    )
    provider = make_provider(
        bars_by_security=bars_by,
        actions_by_security=actions_by,
        retrieved_at=retrieved_at,
    )
    rng = date_range or DateRange(start="2020-01-01", end="2024-12-31")
    engine.ingest(
        provider,
        security_id,
        rng,
        source=FAKE_SOURCE,
        with_actions=actions is not None,
    )
    return engine
