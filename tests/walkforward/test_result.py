"""The sealed walk-forward record: sealing, round-trip, derived ids, roll-ups (§14)."""

from __future__ import annotations

from quantforge.walkforward.model import (
    StatValue,
    WalkForwardSummary,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.result import (
    BOUNDARY_PIT,
    MIN_VALID_WINDOWS,
    WalkForwardEvaluation,
    WindowResult,
)


def _summary() -> WalkForwardSummary:
    known = StatValue.known("0.1")
    return WalkForwardSummary(
        cumulative_return=known,
        mean_period_return=known,
        volatility=known,
        annualized_sharpe=known,
        mean_t_stat=known,
        hit_rate=known,
        n_valid_periods=2,
    )


def _realized_window(index: int, *, ret: str = "0.01") -> WindowResult:
    return WindowResult(
        index=index,
        train_start=0,
        train_end=3 + index,
        test_start=3 + index,
        test_end=4 + index,
        status=WindowStatus.REALIZED,
        reason=None,
        weights=(StatValue.known("0.5"), StatValue.known("0.5")),
        predicted_variance=StatValue.known("0.2"),
        realized_variance=StatValue.known("0.3"),
        oos_returns=(ret,),
    )


def _singular_window(index: int) -> WindowResult:
    undef = StatValue.undefined(WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE)
    return WindowResult(
        index=index,
        train_start=0,
        train_end=2,
        test_start=2,
        test_end=3,
        status=WindowStatus.UNDEFINED,
        reason=WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE,
        weights=(),
        predicted_variance=undef,
        realized_variance=undef,
        oos_returns=(),
    )


def _seal(
    *,
    windows: tuple[WindowResult, ...],
    oos_returns: tuple[str, ...],
    dataset_version_ids: tuple[str, ...] = ("ds-1",),
    market_dataset_version_ids: tuple[str, ...] = ("mkt-1",),
) -> WalkForwardEvaluation:
    return WalkForwardEvaluation.seal(
        walk_forward_engine_version_id="sha256:engine",
        walk_forward_spec={
            "spec_version": "walkforward/1",
            "name": "w",
            "optimization_id": "sha256:opt",
            "training_policy": {
                "window": "expanding",
                "min_train_periods": 3,
                "test_periods": 1,
            },
        },
        optimization_ref=("sha256:opt", "sha256:opthash"),
        boundary_kind=BOUNDARY_PIT,
        schedule_id="sched",
        factor_portfolio_engine_version_id="fpe/1",
        n_factors=2,
        factor_labels=("factor_1", "factor_2"),
        periods_per_year="1",
        risk_free_per_period="0",
        common_periods=6,
        windows=windows,
        oos_returns=oos_returns,
        summary=_summary(),
        realized_variance=StatValue.known("0.25"),
        dataset_version_ids=dataset_version_ids,
        market_dataset_version_ids=market_dataset_version_ids,
    )


class TestSealAndRoundTrip:
    def test_round_trip_is_byte_identical(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        restored = WalkForwardEvaluation.from_dict(record.to_dict())
        assert restored.to_dict() == record.to_dict()
        assert restored.result_hash == record.result_hash
        assert restored.walk_forward_id == record.walk_forward_id

    def test_research_result_id_aliases_walk_forward_id(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        assert record.research_result_id == record.walk_forward_id
        assert record.optimization_id == "sha256:opt"

    def test_derived_id_ignores_tampered_stored_id(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        raw = record.to_dict()
        raw["walk_forward_id"] = "sha256:tampered"
        raw["research_result_id"] = "sha256:tampered"
        restored = WalkForwardEvaluation.from_dict(raw)
        assert restored.walk_forward_id == record.walk_forward_id

    def test_result_hash_sensitive_to_a_computed_value(self) -> None:
        a = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        b = _seal(
            windows=(_realized_window(0), _realized_window(1, ret="0.09")),
            oos_returns=("0.01", "0.09"),
        )
        assert a.result_hash != b.result_hash


class TestRollUps:
    def test_status_realized_when_enough_windows(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        assert record.status is WindowStatus.REALIZED

    def test_status_undefined_below_threshold(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _singular_window(1)),
            oos_returns=("0.01",),
        )
        assert MIN_VALID_WINDOWS == 2
        assert record.status is WindowStatus.UNDEFINED

    def test_predicted_vs_realized_omits_undefined_windows(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _singular_window(1), _realized_window(2)),
            oos_returns=("0.01", "0.03"),
        )
        pairs = record.predicted_vs_realized
        assert [idx for idx, _, _ in pairs] == [0, 2]

    def test_pin_mismatch_false_when_singular(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
        )
        assert record.pin_mismatch is False

    def test_pin_mismatch_true_when_multiple_pins(self) -> None:
        record = _seal(
            windows=(_realized_window(0), _realized_window(1)),
            oos_returns=("0.01", "0.02"),
            dataset_version_ids=("ds-1", "ds-2"),
        )
        assert record.pin_mismatch is True
