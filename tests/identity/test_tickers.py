"""Tests for parsing and querying the official SEC ticker → CIK mapping."""

from __future__ import annotations

import pytest

from openfinance.identity.errors import AmbiguousSymbolError, UnknownSymbolError
from openfinance.identity.tickers import TickerMap

SAMPLE = (
    b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    b'"1":{"cik_str":789019,"ticker":"MSFT","title":"MICROSOFT CORP"},'
    b'"2":{"cik_str":1318605,"ticker":"TSLA","title":"Tesla, Inc."}}'
)


def _map() -> TickerMap:
    return TickerMap.from_bytes(SAMPLE)


def test_parses_all_rows() -> None:
    assert len(_map()) == 3


def test_resolve_ticker_case_insensitive() -> None:
    m = _map()
    assert m.cik_for_ticker("AAPL") == "320193"
    assert m.cik_for_ticker("aapl") == "320193"
    assert m.cik_for_ticker("  Aapl ") == "320193"


def test_resolve_title_case_insensitive() -> None:
    m = _map()
    assert m.cik_for_title("Apple Inc.") == "320193"
    assert m.cik_for_title("microsoft corp") == "789019"


def test_cik_canonicalized_to_bare_integer() -> None:
    # SEC supplies an integer cik_str; we emit the canonical bare-integer form.
    assert _map().cik_for_ticker("TSLA") == "1318605"


def test_entry_for_cik_accepts_any_cik_form() -> None:
    m = _map()
    entry = m.entry_for_cik("0000320193")
    assert entry is not None
    assert entry.ticker == "AAPL"
    assert entry.title == "Apple Inc."


def test_entry_for_unlisted_cik_is_none() -> None:
    # A filer with no assigned ticker is simply absent — not an error.
    assert _map().entry_for_cik(999999) is None


def test_unknown_ticker_fails_closed() -> None:
    with pytest.raises(UnknownSymbolError):
        _map().cik_for_ticker("NOPE")


def test_ambiguous_ticker_fails_closed() -> None:
    # A ticker reused across two CIKs must not silently pick one.
    data = (
        b'{"0":{"cik_str":111,"ticker":"DUP","title":"First Corp"},'
        b'"1":{"cik_str":222,"ticker":"DUP","title":"Second Corp"}}'
    )
    m = TickerMap.from_bytes(data)
    with pytest.raises(AmbiguousSymbolError) as exc:
        m.cik_for_ticker("DUP")
    assert exc.value.candidates == ["111", "222"]


def test_skips_incomplete_rows() -> None:
    data = (
        b'{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
        b'"1":{"cik_str":null,"ticker":"BAD","title":"No CIK"},'
        b'"2":{"cik_str":789019,"ticker":"","title":"Empty ticker"}}'
    )
    m = TickerMap.from_bytes(data)
    assert len(m) == 1
    assert m.cik_for_ticker("AAPL") == "320193"


def test_rejects_non_object_document() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        TickerMap.from_bytes(b"[1, 2, 3]")


def test_iteration_is_deterministic() -> None:
    # Same bytes → same ordered entry list regardless of source key order.
    a = list(TickerMap.from_bytes(SAMPLE))
    b = list(TickerMap.from_bytes(SAMPLE))
    assert a == b
    assert [e.cik for e in a] == sorted(e.cik for e in a)
