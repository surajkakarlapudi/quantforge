"""PIT / REVISED resolution: no-look-ahead, fail-closed, type separation (section 9)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantforge.availability.errors import ModeError
from quantforge.market.engine import PriceEngine
from quantforge.market.model import PriceField, PriceStatus, PriceUndefinedReason
from quantforge.market.result import PitPrice, RevisedPrice
from tests.market.builders import SECURITY_ID, bar, ingest_bars

# The 2020-01-02 close becomes knowable at 2020-01-03T01:00:00Z (16:00 ET + 240 min).
BEFORE = datetime(2020, 1, 2, 12, 0, tzinfo=UTC)
AFTER = datetime(2020, 1, 5, 0, 0, tzinfo=UTC)


def test_price_known_after_availability(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    price = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    assert isinstance(price, PitPrice)
    assert price.is_known
    assert price.value_numeric_str == "105"
    assert price.currency == "USD"


def test_price_not_knowable_before_availability(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    price = engine.price_as_of(SECURITY_ID, "2020-01-02", BEFORE)
    assert not price.is_known
    assert price.status is PriceStatus.UNDEFINED
    assert price.reason is PriceUndefinedReason.NOT_KNOWABLE_YET


def test_unreported_date_is_not_reported(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    price = engine.price_as_of(SECURITY_ID, "2020-01-03", AFTER)
    assert price.reason is PriceUndefinedReason.NOT_REPORTED


def test_naive_as_of_raises_mode_error(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    with pytest.raises(ModeError):
        engine.price_as_of(SECURITY_ID, "2020-01-02", datetime(2020, 1, 5, 0, 0))


def test_revised_price_is_distinct_type(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    revised = engine.revised_price(SECURITY_ID, "2020-01-02")
    assert isinstance(revised, RevisedPrice)
    assert not isinstance(revised, PitPrice)
    assert revised.is_known
    assert revised.dataset_version_id.startswith("sha256:")


def test_pit_and_revised_do_not_share_a_type(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    pit = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    revised = engine.revised_price(SECURITY_ID, "2020-01-02")
    assert type(pit) is not type(revised)  # type: ignore[comparison-overlap]


def _ingest_correction(engine: PriceEngine) -> None:
    """Ingest a corrected close (106) for the same session, from a later retrieval."""
    from quantforge.market.provider import DateRange
    from tests.market.builders import (
        FAKE_SOURCE,
        bars_document,
        make_provider,
    )

    corrected = make_provider(
        bars_by_security={SECURITY_ID: bars_document([bar("2020-01-02", close="106")])},
        retrieved_at="2020-02-01T00:00:00Z",
    )
    engine.ingest(
        corrected,
        SECURITY_ID,
        DateRange(start="2020-01-01", end="2020-12-31"),
        source=FAKE_SOURCE,
        with_actions=False,
    )


def test_correction_ingest_is_append_only(tmp_path: Path) -> None:
    # Regression for a bug found while writing these tests: a second ingest (a vendor
    # correction) must ADD an observation, never overwrite the instrument file and
    # destroy the earlier vintage (invariant 4). Both values must coexist so the
    # pre-correction vintage stays reproducible and auditable.
    engine = ingest_bars(
        tmp_path, [bar("2020-01-02", close="105")], retrieved_at="2020-01-03T02:00:00Z"
    )
    _ingest_correction(engine)
    obs = engine.store.read_observations(SECURITY_ID)
    assert {o.value_numeric_str for o in obs} == {"105", "106"}


def test_correction_resolution_is_deterministic(tmp_path: Path) -> None:
    # With two observations for one session, the total order (availability desc, then
    # observation_id desc) yields a single, deterministic winner and records BOTH as
    # present candidates (full provenance of the discarded value). NOTE: the v1
    # provisional policy derives availability per SESSION (close + lag), so a
    # correction does not receive a distinct, later availability - the winner is
    # decided by the stable observation-id tiebreak, reproducibly.
    engine = ingest_bars(
        tmp_path, [bar("2020-01-02", close="105")], retrieved_at="2020-01-03T02:00:00Z"
    )
    _ingest_correction(engine)
    first = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    second = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    assert first.value_numeric_str == second.value_numeric_str  # deterministic
    assert len(first.provenance.present_candidates) == 2  # both audited


def test_reinterpret_as_pit_reresolves(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105")])
    revised = engine.revised_price(SECURITY_ID, "2020-01-02")
    resolver = engine._resolver_for(SECURITY_ID)
    # Re-interpreting at an instant before availability yields UNDEFINED (re-resolved).
    pit = revised.reinterpret_as_pit(resolver, BEFORE)
    assert isinstance(pit, PitPrice)
    assert not pit.is_known


def test_field_selection(tmp_path: Path) -> None:
    engine = ingest_bars(tmp_path, [bar("2020-01-02", close="105", open_="100")])
    close = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER, field=PriceField.CLOSE)
    open_ = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER, field=PriceField.OPEN)
    assert close.value_numeric_str == "105"
    assert open_.value_numeric_str == "100"
