"""Deterministic raw->canonical normalization (section 8, D4)."""

from __future__ import annotations

import pytest

from quantforge.market.canonical import CanonicalMarketData, MarketCanonicalizer
from quantforge.market.model import CorporateActionKind, PriceField
from quantforge.market.provider import DateRange, FakeMarketDataProvider
from tests.market.builders import (
    FAKE_SOURCE,
    SECURITY_ID,
    actions_document,
    bar,
    bars_document,
)


def _canonicalize(
    bars_bytes: bytes, actions_bytes: bytes | None = None
) -> CanonicalMarketData:
    provider = FakeMarketDataProvider(
        bars_by_security={SECURITY_ID: bars_bytes},
        actions_by_security=(
            {SECURITY_ID: actions_bytes} if actions_bytes is not None else None
        ),
        retrieved_at="2024-01-01T00:00:00Z",
    )
    rng = DateRange(start="2020-01-01", end="2024-12-31")
    bars_doc = provider.fetch_daily_bars(SECURITY_ID, rng)
    actions_doc = (
        provider.fetch_corporate_actions(SECURITY_ID, rng)
        if actions_bytes is not None
        else None
    )
    return MarketCanonicalizer().canonicalize(
        bars_document=bars_doc, actions_document=actions_doc, source=FAKE_SOURCE
    )


def test_ohlcv_becomes_per_field_observations() -> None:
    doc = bars_document(
        [
            bar(
                "2020-01-02",
                open_="100",
                high="110",
                low="90",
                close="105",
                volume="1000",
            )
        ]
    )
    result = _canonicalize(doc)
    fields = {o.field for o in result.observations}
    assert fields == {
        PriceField.OPEN,
        PriceField.HIGH,
        PriceField.LOW,
        PriceField.CLOSE,
        PriceField.VOLUME,
    }


def test_missing_field_yields_no_observation() -> None:
    # Only a close is provided: exactly one observation, no guessed zeros.
    result = _canonicalize(bars_document([bar("2020-01-02", close="105")]))
    assert len(result.observations) == 1
    assert result.observations[0].field is PriceField.CLOSE


def test_numeric_values_are_canonicalized() -> None:
    # "105.00" and "105" must normalize to the same identity-bearing string.
    a = _canonicalize(bars_document([bar("2020-01-02", close="105.00")]))
    b = _canonicalize(bars_document([bar("2020-01-02", close="105")]))
    assert a.observations[0].value_numeric_str == b.observations[0].value_numeric_str
    assert (
        a.observations[0].price_observation_id == b.observations[0].price_observation_id
    )


def test_malformed_numeric_fails_closed() -> None:
    from quantforge.market.errors import MarketDataError

    with pytest.raises(MarketDataError):
        _canonicalize(bars_document([bar("2020-01-02", close="not-a-number")]))


def test_instrument_metadata_and_company_id() -> None:
    result = _canonicalize(bars_document([bar("2020-01-02", close="105")]))
    assert result.instrument.security_id == SECURITY_ID
    assert result.instrument.company_id == "cik:9999999999"
    assert result.instrument.ticker_history[0].ticker == "ZZZZ"


def test_corporate_actions_parse_via_typed_constructors() -> None:
    actions = actions_document(
        [
            {"kind": "split", "ex_date": "2020-06-01", "ratio": "2"},
            {
                "kind": "dividend",
                "ex_date": "2020-03-02",
                "amount": "0.50",
                "currency": "USD",
                "pay_date": "2020-03-16",
            },
            {
                "kind": "symbol_change",
                "ex_date": "2020-09-01",
                "old_ticker": "ZZZZ",
                "new_ticker": "WWWW",
            },
            {"kind": "delisting", "ex_date": "2021-01-04", "reason": "acquired"},
            {
                "kind": "merger",
                "ex_date": "2021-01-04",
                "successor_security_id": "cik:8888888888#class:common-stock",
                "terms": "1:1",
            },
        ]
    )
    result = _canonicalize(bars_document([bar("2020-01-02", close="105")]), actions)
    kinds = {a.action_kind for a in result.actions}
    assert kinds == {
        CorporateActionKind.SPLIT,
        CorporateActionKind.DIVIDEND,
        CorporateActionKind.SYMBOL_CHANGE,
        CorporateActionKind.DELISTING,
        CorporateActionKind.MERGER,
    }


def test_security_id_mismatch_between_docs_raises() -> None:
    from quantforge.market.errors import MarketDataError

    other = actions_document(
        [{"kind": "split", "ex_date": "2020-06-01", "ratio": "2"}],
        security_id="cik:1111111111#class:common-stock",
    )
    with pytest.raises(MarketDataError):
        _canonicalize(bars_document([bar("2020-01-02", close="105")]), other)


def test_unknown_action_kind_fails_closed() -> None:
    from quantforge.market.errors import MarketDataError

    bad = actions_document([{"kind": "spinoff", "ex_date": "2020-06-01"}])
    with pytest.raises(MarketDataError):
        _canonicalize(bars_document([bar("2020-01-02", close="105")]), bad)


def test_evidence_dedups_sessions() -> None:
    # A bar and a same-day action share one session (section 9).
    actions = actions_document(
        [
            {
                "kind": "dividend",
                "ex_date": "2020-01-02",
                "amount": "0.10",
                "currency": "USD",
            }
        ]
    )
    result = _canonicalize(bars_document([bar("2020-01-02", close="105")]), actions)
    dates = [e.event_date for e in result.evidence]
    assert dates == ["2020-01-02"]  # one session, not two


def test_canonicalization_is_deterministic() -> None:
    doc = bars_document(
        [bar("2020-01-02", close="105"), bar("2020-01-03", close="106")]
    )
    a = _canonicalize(doc)
    b = _canonicalize(doc)
    assert [o.price_observation_id for o in a.observations] == [
        o.price_observation_id for o in b.observations
    ]
