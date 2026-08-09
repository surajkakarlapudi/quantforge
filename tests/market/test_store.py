"""File-based derived store: round-trips, integrity, determinism (section 13, D7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantforge.market.errors import MarketConsistencyError
from quantforge.market.store import MARKET_FORMAT_VERSION, MarketDataStore
from tests.market.builders import SECURITY_ID, bar, ingest_bars


def test_instrument_round_trip(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    instrument = store.read_instrument(SECURITY_ID)
    assert instrument is not None
    assert instrument.security_id == SECURITY_ID


def test_observations_round_trip(tmp_path: Path) -> None:
    ingest_bars(
        tmp_path, [bar("2020-01-02", close="105"), bar("2020-01-03", close="106")]
    )
    store = MarketDataStore(tmp_path / "market")
    obs = store.read_observations(SECURITY_ID)
    assert {o.trading_date for o in obs} == {"2020-01-02", "2020-01-03"}


def test_availability_round_trip(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    avail = store.read_availability_map(SECURITY_ID)
    assert len(avail) == 1


def test_slug_handles_reserved_chars(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    # The file exists despite ':' and '#' in the security_id.
    assert store.has_instrument(SECURITY_ID)
    files = list((tmp_path / "market" / "canonical").glob("*.json"))
    assert len(files) == 1
    assert ":" not in files[0].name and "#" not in files[0].name


def test_corrupted_observation_id_fails_closed(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    path = store._canonical_path(SECURITY_ID)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["observations"][0]["price_observation_id"] = "sha256:tampered"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(MarketConsistencyError):
        store.read_observations(SECURITY_ID)


def test_non_object_document_fails_closed(tmp_path: Path) -> None:
    store = MarketDataStore(tmp_path / "market")
    path = store._canonical_path(SECURITY_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(MarketConsistencyError):
        store.read_observations(SECURITY_ID)


def test_write_is_deterministic_byte_identical(tmp_path: Path) -> None:
    ingest_bars(tmp_path / "a", [bar("2020-01-02", close="105")])
    ingest_bars(tmp_path / "b", [bar("2020-01-02", close="105")])
    a = (tmp_path / "a" / "market" / "canonical").glob("*.json")
    b = (tmp_path / "b" / "market" / "canonical").glob("*.json")
    a_bytes = next(a).read_bytes()
    b_bytes = next(b).read_bytes()
    assert a_bytes == b_bytes


def test_format_version_recorded(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    document = json.loads(store._canonical_path(SECURITY_ID).read_text("utf-8"))
    assert document["market_format_version"] == MARKET_FORMAT_VERSION


def test_missing_instrument_returns_empty(tmp_path: Path) -> None:
    store = MarketDataStore(tmp_path / "market")
    assert store.read_instrument("cik:0#class:x") is None
    assert store.read_observations("cik:0#class:x") == []
    assert store.read_availability("cik:0#class:x") == []


def test_list_security_ids(tmp_path: Path) -> None:
    ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    store = MarketDataStore(tmp_path / "market")
    assert store.list_security_ids() == [SECURITY_ID]
