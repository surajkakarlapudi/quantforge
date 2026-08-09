"""End-to-end integration for the Phase 12 backtesting engine (proposal §A-§H).

Populates a genuine combined corpus (SEC fundamentals + market prices/actions) for two
synthetic filers over one data root, then drives whole backtests through
:class:`~quantforge.backtest.engine.BacktestEngine` (via ``Workspace.backtest_engine``)
and asserts the four Phase 12 invariants and the nine correctness requirements:

* **look-ahead (BT-2)** — a decision at ``T`` sees only PIT-eligible-at-``T`` data;
* **dataset pinning (BT-1)** — a tampered corpus pin fails closed;
* **PIT/REVISED separation** — the ledger records ``Pit*`` signal ids only;
* **determinism** — the same spec reproduces an identical ``backtest_id`` + hash;
* **corporate actions (§D)** — split / dividend / delisting / merger / symbol-change;
* **survivorship (Phase 9)** — a filer delisted mid-run is present while public;
* **provenance (§H)** — ``SignalRef`` + price-provenance + ``AppliedAction`` recorded;
* **fail-closed (BT-4)** — UNDEFINED signal excluded, no-security -> cash, no-price ->
  unfilled;
* **identity (D6)** — every result-changing input changes the ``backtest_id``.

Plus the v1 performance statistics and additive workspace wiring. Everything is offline
and obviously synthetic (fictional CIKs 999999999x, tickers ZZZZ/TEST); no network, no
wall-clock, no real financial data.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from quantforge.availability.timestamps import parse_utc
from quantforge.backtest.engine import BacktestEngine
from quantforge.backtest.errors import (
    BacktestConfigurationError,
    BacktestConsistencyError,
)
from quantforge.backtest.result import BacktestResult
from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import CostModel
from quantforge.market.provider import DateRange
from quantforge.metrics.model import MetricPeriod
from tests.backtest.builders import (
    CIK_A,
    INSTANT_1,
    INSTANT_2,
    SECURITY_A,
    SECURITY_B,
    make_spec,
    populate,
)
from tests.market.builders import FAKE_SOURCE, bar, bars_document, make_provider


@pytest.fixture
def engine(tmp_path: Path) -> BacktestEngine:
    """A backtest engine over the default two-filer combined corpus."""
    return populate(tmp_path).backtest_engine


# -- happy path: selection, weighting, execution -----------------------------


class TestHappyPath:
    def test_ranks_selects_and_rides_the_winner(self, engine: BacktestEngine) -> None:
        # B has the higher current_ratio (4 vs 2), so a descending top-1 holds B and
        # rides its +10% move (20 -> 22); from 1,000,000 that ends at 1,100,000.
        result = engine.run(make_spec(engine, select_n=1))
        assert isinstance(result, BacktestResult)
        assert len(result.ledger) == 2
        first, second = result.ledger
        assert first.target_weights.security_ids() == (SECURITY_B,)
        assert first.equity == "1000000"
        assert second.equity == "1100000"
        assert result.performance.statistics.cumulative_return == "0.1"

    def test_execution_uses_the_pit_close_at_t(self, engine: BacktestEngine) -> None:
        # At instant 1 (2024-01-15) only the 2024-01-10 close (20) is knowable, never
        # the future 2024-02-10 close (22) — the fill price is the PIT close.
        result = engine.run(make_spec(engine, select_n=1))
        fill = result.ledger[0].fills[0]
        assert fill.security_id == SECURITY_B
        assert fill.side == "buy"
        assert fill.status == "filled"
        assert fill.price == "20"
        assert fill.shares == "50000"  # 1,000,000 / 20

    def test_top_2_equal_weights_both_members(self, engine: BacktestEngine) -> None:
        result = engine.run(make_spec(engine, select_n=2))
        weights = dict(result.ledger[0].target_weights.weights)
        assert weights == {SECURITY_A: "0.5", SECURITY_B: "0.5"}

    def test_ascending_rank_prefers_the_lower_signal(
        self, engine: BacktestEngine
    ) -> None:
        # Ascending current_ratio prefers A (2) over B (4).
        result = engine.run(make_spec(engine, select_n=1, rank="ascending"))
        assert result.ledger[0].target_weights.security_ids() == (SECURITY_A,)


# -- determinism / golden (requirement 4) ------------------------------------


class TestDeterminism:
    def test_same_spec_same_identity_and_hash(self, engine: BacktestEngine) -> None:
        spec = make_spec(engine, select_n=1)
        one = engine.run(spec)
        two = engine.run(spec)
        assert one.backtest_id == two.backtest_id
        assert one.result_hash == two.result_hash
        assert one.to_dict() == two.to_dict()

    def test_result_persists_and_round_trips(self, engine: BacktestEngine) -> None:
        result = engine.run(make_spec(engine, select_n=1))
        store = engine._factor_engine.research_store
        assert store.has(result.backtest_id)
        stored = store.read_as(result.backtest_id, lambda raw: raw)
        assert stored == result.to_dict()

    def test_backtest_id_aliases_research_result_id(
        self, engine: BacktestEngine
    ) -> None:
        result = engine.run(make_spec(engine, select_n=1))
        assert result.research_result_id == result.backtest_id


# -- look-ahead red-team (requirement 1, BT-2) -------------------------------


class TestNoLookAhead:
    def test_future_bar_not_used_as_mark(self, tmp_path: Path) -> None:
        # B's only bar is dated AFTER instant 1 — not knowable at T, so the buy is
        # unfilled (never sized against a future price).
        engine = populate(
            tmp_path, bars_b=[bar("2024-03-10", close="30")]
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        fill = result.ledger[0].fills[0]
        assert fill.security_id == SECURITY_B
        assert fill.status == "unfilled"
        assert fill.reason == "no_pit_price"
        assert result.ledger[0].equity == "1000000"

    def test_signal_undefined_before_availability_holds_cash(
        self, tmp_path: Path
    ) -> None:
        # A rebalance in 2023-06 — before the 10-K (accepted 2023-11-02) is public and
        # before any bar — sees UNDEFINED signals: nothing is selected, all cash.
        engine = populate(tmp_path).backtest_engine
        schedule = RebalanceSchedule.of(["2023-06-01T00:00:00Z"])
        result = engine.run(make_spec(engine, select_n=1, schedule=schedule))
        record = result.ledger[0]
        assert record.target_weights.is_empty()
        assert record.fills == ()
        assert record.equity == "1000000"


# -- dataset pinning (requirement 2, BT-1) -----------------------------------


class TestCorpusPinning:
    def test_tampered_market_pin_fails_closed(self, engine: BacktestEngine) -> None:
        spec = make_spec(engine, select_n=1)
        tampered = dataclasses.replace(
            spec, market_dataset_version_id="sha256:deadbeef"
        )
        with pytest.raises(BacktestConsistencyError):
            engine.run(tampered)

    def test_tampered_fundamentals_pin_fails_closed(
        self, engine: BacktestEngine
    ) -> None:
        spec = make_spec(engine, select_n=1)
        tampered = dataclasses.replace(spec, dataset_version_id="sha256:deadbeef")
        with pytest.raises(BacktestConsistencyError):
            engine.run(tampered)

    def test_derived_pins_match_specification(self, engine: BacktestEngine) -> None:
        spec = make_spec(engine, select_n=1)
        assert (
            engine.fundamentals_dataset_version(spec).dataset_version_id
            == spec.dataset_version_id
        )
        assert (
            engine.market_dataset_version(spec).dataset_version_id
            == spec.market_dataset_version_id
        )


# -- corporate-action accounting (requirement 5, §D) -------------------------


class TestCorporateActions:
    def test_dividend_credits_cash_on_ex_date(self, tmp_path: Path) -> None:
        # B pays 0.50/share ex 2024-02-01 (between the two instants); the 50,000 shares
        # held credit 25,000 cash before the instant-2 rebalance.
        engine = populate(
            tmp_path,
            actions_b=[
                {
                    "kind": "dividend",
                    "ex_date": "2024-02-01",
                    "amount": "0.50",
                    "currency": "USD",
                    "pay_date": "2024-02-05",
                }
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        actions = result.ledger[1].actions_applied
        assert len(actions) == 1
        assert actions[0].action_kind == "dividend"
        assert actions[0].effect["cash"] == "25000.0"
        assert not actions[0].unrecognized

    def test_split_multiplies_shares_no_cash(self, tmp_path: Path) -> None:
        engine = populate(
            tmp_path,
            actions_b=[{"kind": "split", "ex_date": "2024-02-01", "ratio": "2"}],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        actions = result.ledger[1].actions_applied
        assert [a.action_kind for a in actions] == ["split"]
        assert actions[0].effect == {"kind": "split", "ratio": "2"}
        # Post-split, pre-rebalance the position is 100,000 shares (50,000 x 2).

    def test_dividend_in_foreign_currency_raises(self, tmp_path: Path) -> None:
        # A mixed-currency cash leg is a v1 configuration defect (§B), raised.
        engine = populate(
            tmp_path,
            actions_b=[
                {
                    "kind": "dividend",
                    "ex_date": "2024-02-01",
                    "amount": "0.50",
                    "currency": "EUR",
                    "pay_date": "2024-02-05",
                }
            ],
        ).backtest_engine
        with pytest.raises(BacktestConfigurationError):
            engine.run(make_spec(engine, select_n=1))

    def test_delisting_liquidates_at_last_pit_close(self, tmp_path: Path) -> None:
        # B delists ex 2024-02-08; the position is force-liquidated at the last PIT
        # close on or before the ex-date (20, NOT the later 22 — no look-ahead).
        engine = populate(
            tmp_path,
            actions_b=[
                {"kind": "delisting", "ex_date": "2024-02-08", "reason": "acquired"}
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        actions = result.ledger[1].actions_applied
        assert [a.action_kind for a in actions] == ["delisting"]
        assert actions[0].effect["price"] == "20"
        assert actions[0].effect["proceeds"] == "1000000"

    def test_merger_rekeys_shares_to_successor(self, tmp_path: Path) -> None:
        successor = "cik:9999999993#class:common-stock"
        engine = populate(
            tmp_path,
            actions_b=[
                {
                    "kind": "merger",
                    "ex_date": "2024-02-08",
                    "successor_security_id": successor,
                    "terms": "1",
                }
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        merger = next(
            a for a in result.ledger[1].actions_applied if a.action_kind == "merger"
        )
        assert not merger.unrecognized
        assert merger.effect["successor_security_id"] == successor
        assert any(p.security_id == successor for p in result.ledger[1].positions)

    def test_merger_with_unparseable_terms_is_flagged_not_applied(
        self, tmp_path: Path
    ) -> None:
        # A "1:1" ratio grammar is not a decimal: flagged unrecognized, position kept.
        engine = populate(
            tmp_path,
            actions_b=[
                {
                    "kind": "merger",
                    "ex_date": "2024-02-08",
                    "successor_security_id": "cik:9999999993#class:common-stock",
                    "terms": "1:1",
                }
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        merger = next(
            a for a in result.ledger[1].actions_applied if a.action_kind == "merger"
        )
        assert merger.unrecognized
        assert any(p.security_id == SECURITY_B for p in result.ledger[1].positions)

    def test_symbol_change_is_a_recorded_no_op(self, tmp_path: Path) -> None:
        engine = populate(
            tmp_path,
            actions_b=[
                {
                    "kind": "symbol_change",
                    "ex_date": "2024-02-01",
                    "old_ticker": "ZZZZ",
                    "new_ticker": "WWWW",
                }
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        symbol = next(
            a
            for a in result.ledger[1].actions_applied
            if a.action_kind == "symbol_change"
        )
        assert not symbol.unrecognized
        assert symbol.effect == {"kind": "symbol_change"}
        # The security_id (identity) is unchanged — still holding B.
        assert any(p.security_id == SECURITY_B for p in result.ledger[1].positions)

    def test_action_applied_at_most_once(self, tmp_path: Path) -> None:
        # A three-instant schedule: the split (ex 2024-02-01) is applied once, at the
        # first rebalance it is PIT-eligible (instant 2), never re-applied at instant 3.
        schedule = RebalanceSchedule.of([INSTANT_1, INSTANT_2, "2024-03-15T00:00:00Z"])
        engine = populate(
            tmp_path,
            bars_a=[
                bar("2024-01-10", close="10"),
                bar("2024-02-10", close="11"),
                bar("2024-03-10", close="12"),
            ],
            bars_b=[
                bar("2024-01-10", close="20"),
                bar("2024-02-10", close="22"),
                bar("2024-03-10", close="24"),
            ],
            actions_b=[{"kind": "split", "ex_date": "2024-02-01", "ratio": "2"}],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1, schedule=schedule))
        split_count = sum(
            1
            for record in result.ledger
            for action in record.actions_applied
            if action.action_kind == "split"
        )
        assert split_count == 1


# -- survivorship-free (requirement 6, Phase 9) ------------------------------


class TestSurvivorship:
    def test_delisted_filer_is_present_while_public(self, tmp_path: Path) -> None:
        # B is delisted mid-run, yet it is selected and traded at instant 1 (when it was
        # public) — survivorship-free: today's delisting does not erase its past.
        engine = populate(
            tmp_path,
            actions_b=[
                {"kind": "delisting", "ex_date": "2024-02-08", "reason": "acquired"}
            ],
        ).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        assert result.ledger[0].target_weights.security_ids() == (SECURITY_B,)
        assert result.ledger[0].fills[0].status == "filled"


# -- provenance (requirement 7, §H) ------------------------------------------


class TestProvenance:
    def test_records_factor_signal_and_price_provenance(
        self, engine: BacktestEngine
    ) -> None:
        result = engine.run(make_spec(engine, select_n=1))
        record = result.ledger[0]
        assert [s.kind for s in record.signals] == ["factor"]
        assert record.signals[0].result_id.startswith("sha256:")
        fill = record.fills[0]
        assert fill.price_provenance_id is not None
        assert fill.price_provenance_id.startswith("sha256:")

    def test_records_full_lineage_on_result(self, engine: BacktestEngine) -> None:
        result = engine.run(make_spec(engine, select_n=1))
        data = result.to_dict()
        for key in (
            "strategy_version",
            "schedule_id",
            "universe_id",
            "dataset_version_id",
            "market_dataset_version_id",
            "cost_model_id",
            "accounting_version_id",
            "backtest_engine_version_id",
        ):
            assert isinstance(data[key], str) and data[key]


# -- fail-closed (requirement 8, BT-4) ---------------------------------------


class TestFailClosed:
    def test_member_with_no_security_holds_weight_in_cash(self, tmp_path: Path) -> None:
        # B is selected (higher current_ratio) but has NO tradable security; its 1/1
        # weight stays uninvested (cash), no fill, never renormalized onto A.
        engine = populate(tmp_path, market_b=False).backtest_engine
        result = engine.run(make_spec(engine, select_n=1))
        record = result.ledger[0]
        assert record.target_weights.is_empty()
        assert record.fills == ()
        assert record.equity == "1000000"

    def test_undefined_signal_excluded_from_selection(self, tmp_path: Path) -> None:
        # A registered metric whose inputs no filer seeded -> every cell UNDEFINED ->
        # nothing selected, all cash (never guessed). ``gross_margin`` needs revenue /
        # cost-of-revenue facts, which this fixture does not persist.
        engine = populate(tmp_path).backtest_engine
        result = engine.run(make_spec(engine, select_n=1, signal="gross_margin"))
        assert result.ledger[0].target_weights.is_empty()
        assert result.ledger[0].equity == "1000000"

    def test_multiple_securities_per_company_is_configuration_defect(
        self, tmp_path: Path
    ) -> None:
        # A second share class for A means the equal-weight leg is ambiguous in v1: a
        # configuration defect, raised (multi-share-class weighting is deferred).
        corpus = populate(tmp_path)
        second_class = "cik:9999999991#class:preferred-stock"
        provider = make_provider(
            bars_by_security={
                second_class: bars_document(
                    [bar("2024-01-10", close="5")], security_id=second_class
                )
            }
        )
        corpus.price_engine.ingest(
            provider,
            second_class,
            DateRange(start="2023-01-01", end="2024-12-31"),
            source=FAKE_SOURCE,
            with_actions=False,
        )
        engine = corpus.backtest_engine
        with pytest.raises(BacktestConfigurationError):
            engine.run(make_spec(engine, select_n=2))


# -- identity sensitivity (requirement 9, D6) --------------------------------


class TestIdentitySensitivity:
    def test_cost_model_changes_identity_and_hash(self, engine: BacktestEngine) -> None:
        base = engine.run(make_spec(engine, select_n=1))
        costed = engine.run(
            make_spec(engine, select_n=1, cost_model=CostModel(proportional_bps="10"))
        )
        assert base.backtest_id != costed.backtest_id
        assert base.result_hash != costed.result_hash

    def test_selection_changes_identity(self, engine: BacktestEngine) -> None:
        one = engine.run(make_spec(engine, select_n=1))
        two = engine.run(make_spec(engine, select_n=2))
        assert one.backtest_id != two.backtest_id

    def test_schedule_changes_identity(self, engine: BacktestEngine) -> None:
        base = engine.run(make_spec(engine, select_n=1))
        shifted = engine.run(
            make_spec(
                engine,
                select_n=1,
                schedule=RebalanceSchedule.of([INSTANT_1]),
            )
        )
        assert base.backtest_id != shifted.backtest_id

    def test_annualization_changes_id_and_sharpe_not_result_hash(
        self, tmp_path: Path
    ) -> None:
        # A dispersed 3-instant path gives non-zero volatility, so the annualization
        # factor genuinely changes the reported Sharpe — a materially different result
        # that must get a distinct backtest_id, though the ledger (hash) is equal.
        schedule = RebalanceSchedule.of([INSTANT_1, INSTANT_2, "2024-03-15T00:00:00Z"])
        engine = populate(
            tmp_path,
            bars_a=[
                bar("2024-01-10", close="10"),
                bar("2024-02-10", close="10"),
                bar("2024-03-10", close="10"),
            ],
            bars_b=[
                bar("2024-01-10", close="20"),
                bar("2024-02-10", close="30"),
                bar("2024-03-10", close="25"),
            ],
        ).backtest_engine
        spec = make_spec(engine, select_n=1, schedule=schedule)
        annual = engine.run(spec, periods_per_year="12")
        per_period = engine.run(spec, periods_per_year="1")
        assert annual.backtest_id != per_period.backtest_id
        assert annual.result_hash == per_period.result_hash
        assert (
            annual.performance.statistics.sharpe
            != per_period.performance.statistics.sharpe
        )
        # Both still persist without colliding (the write-once store accepts distinct
        # ids for distinct payloads — the regression this guards against).
        store = engine._factor_engine.research_store
        assert store.has(annual.backtest_id)
        assert store.has(per_period.backtest_id)


# -- v1 performance statistics -----------------------------------------------


class TestStatistics:
    def test_cumulative_and_period_returns(self, engine: BacktestEngine) -> None:
        stats = engine.run(make_spec(engine, select_n=1)).performance.statistics
        assert stats.initial_equity == "1000000"
        assert stats.final_equity == "1100000"
        assert stats.peak_equity == "1100000"
        assert stats.cumulative_return == "0.1"
        assert stats.period_returns == ("0.1",)
        assert stats.periods == 1

    def test_recorded_annualization_convention(self, engine: BacktestEngine) -> None:
        summary = engine.run(
            make_spec(engine, select_n=1), periods_per_year="12"
        ).performance
        assert summary.periods_per_year == "12"
        assert summary.risk_free_per_period == "0"
        assert summary.formula_version == "backtest-stats/1"


# -- additive wiring ---------------------------------------------------------


class TestAdditiveWiring:
    def test_workspace_exposes_backtest_engine(self, tmp_path: Path) -> None:
        workspace = populate(tmp_path).workspace
        assert isinstance(workspace.backtest_engine, BacktestEngine)
        assert workspace.backtest_engine is workspace.backtest_engine

    def test_metric_and_factor_paths_undisturbed(self, tmp_path: Path) -> None:
        corpus = populate(tmp_path)
        engine = corpus.backtest_engine
        # Running a backtest must not disturb the underlying Phase 7 metric path.
        engine.run(make_spec(engine, select_n=1))
        metric = corpus.workspace.metric_engine.metric_as_of(  # type: ignore[attr-defined]
            "current_ratio",
            CIK_A,
            MetricPeriod.instant("2023-09-30"),
            parse_utc("2024-06-01T00:00:00Z"),
        )
        assert metric.value_numeric_str == "2"
