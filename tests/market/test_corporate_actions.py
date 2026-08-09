"""Corporate-action semantics: symbol change, delisting, ticker reuse (section 7/10)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from quantforge.market.identity import security_id as make_security_id
from quantforge.market.model import CorporateActionKind
from quantforge.market.provider import DateRange
from tests.market.builders import (
    FAKE_SOURCE,
    SECURITY_ID,
    bar,
    bars_document,
    ingest_bars,
    make_engine,
    make_provider,
)

AFTER = datetime(2024, 1, 1, tzinfo=UTC)


def test_symbol_change_is_new_history_row_not_reidentity(tmp_path: Path) -> None:
    # A symbol change is recorded as an action + ticker history; the security_id (the
    # identity) is unchanged. History is not re-pointed.
    engine = ingest_bars(
        tmp_path,
        [bar("2020-01-02", close="105")],
        actions=[
            {
                "kind": "symbol_change",
                "ex_date": "2020-09-01",
                "old_ticker": "ZZZZ",
                "new_ticker": "WWWW",
            }
        ],
    )
    # The observation is still keyed by the original security_id.
    price = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    assert price.security_id == SECURITY_ID
    actions = engine.store.read_actions(SECURITY_ID)
    assert any(a.action_kind is CorporateActionKind.SYMBOL_CHANGE for a in actions)


def test_delisting_preserves_history(tmp_path: Path) -> None:
    # A delisting is a terminal record; the pre-delisting bars remain resolvable
    # (survivorship-bias-free).
    engine = ingest_bars(
        tmp_path,
        [bar("2020-01-02", close="105"), bar("2020-01-03", close="106")],
        actions=[{"kind": "delisting", "ex_date": "2020-01-06", "reason": "acquired"}],
    )
    price = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    assert price.is_known
    actions = engine.store.read_actions(SECURITY_ID)
    assert any(a.action_kind is CorporateActionKind.DELISTING for a in actions)


def test_ticker_reuse_across_issuers_does_not_collide(tmp_path: Path) -> None:
    # Two DIFFERENT issuers use the same ticker ZZZZ. Because identity is the CIK-based
    # security_id (never the ticker), their observations never collide.
    other_id = make_security_id(cik="1111111111", security_class="common-stock")
    engine = make_engine(tmp_path)
    provider = make_provider(
        bars_by_security={
            SECURITY_ID: bars_document(
                [bar("2020-01-02", close="105")], security_id=SECURITY_ID
            ),
            other_id: bars_document(
                [bar("2021-01-04", close="50")],
                security_id=other_id,
            ),
        },
    )
    rng = DateRange(start="2020-01-01", end="2021-12-31")
    engine.ingest(provider, SECURITY_ID, rng, source=FAKE_SOURCE, with_actions=False)
    engine.ingest(provider, other_id, rng, source=FAKE_SOURCE, with_actions=False)

    first = engine.price_as_of(SECURITY_ID, "2020-01-02", AFTER)
    second = engine.price_as_of(other_id, "2021-01-04", AFTER)
    assert first.value_numeric_str == "105"
    assert second.value_numeric_str == "50"
    # The first issuer never reported 2021-01-04 (that's the OTHER issuer's ZZZZ bar).
    cross = engine.price_as_of(SECURITY_ID, "2021-01-04", AFTER)
    assert not cross.is_known


def test_corporate_action_is_pit_gated(tmp_path: Path) -> None:
    # An action not yet knowable at as_of is excluded from the eligible set.
    engine = ingest_bars(
        tmp_path,
        [bar("2020-05-29", close="720"), bar("2020-06-01", close="105")],
        actions=[{"kind": "split", "ex_date": "2020-06-01", "ratio": "7"}],
    )
    # Before the split is knowable, _pit_eligible_actions must exclude it.
    before = datetime(2020, 5, 30, 12, 0, tzinfo=UTC)
    eligible = engine._pit_eligible_actions(SECURITY_ID, before)
    assert eligible == []
    # After, it is included.
    after_split = engine._pit_eligible_actions(SECURITY_ID, AFTER)
    assert len(after_split) == 1
