"""The point-in-time Market Data Layer (Phase 11).

A deterministic, provider-neutral layer that derives a canonical, point-in-time view
of daily market data (unadjusted OHLCV bars + first-class corporate actions) from
immutable, content-addressed vendor bytes, mirroring the SEC stack's discipline one
domain over. Canonical prices are **unadjusted**; adjusted prices are a derived,
PIT-gated view. PIT and REVISED are distinct, un-confusable result types; there is
**no default-mode accessor**.

Public front doors (§18):

* :class:`~quantforge.market.engine.PriceEngine` — ingest, resolve, and adjust
  point-in-time market data; the Phase 12 hand-off surface (``price_as_of``,
  ``price_series_as_of``, ``adjusted_series_as_of``, and the explicitly-named
  ``revised_price``). Reached via ``Workspace.price_engine``.
* :class:`~quantforge.market.axis.PriceAxis` — the explicit, ordered,
  content-addressed trading-date axis a price series is resolved over.
* :class:`~quantforge.market.provider.MarketDataProvider` — the narrow, vendor-facing
  acquisition seam (with :class:`~quantforge.market.provider.FakeMarketDataProvider`
  for offline tests).

The PIT/REVISED result types (:class:`~quantforge.market.result.PitPrice` /
:class:`~quantforge.market.result.RevisedPrice`) are re-exported from the top-level
:mod:`quantforge` package so the distinction is visible at the import site.
"""

from __future__ import annotations

from quantforge.market.axis import PriceAxis
from quantforge.market.engine import PriceEngine
from quantforge.market.provider import (
    DateRange,
    FakeMarketDataProvider,
    MarketDataProvider,
    RawMarketDocument,
)
from quantforge.market.result import PitPrice, PitPriceSeries, RevisedPrice

__all__ = [
    "DateRange",
    "FakeMarketDataProvider",
    "MarketDataProvider",
    "PitPrice",
    "PitPriceSeries",
    "PriceAxis",
    "PriceEngine",
    "RawMarketDocument",
    "RevisedPrice",
]
