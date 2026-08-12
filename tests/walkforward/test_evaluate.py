"""Per-window re-estimate, re-solve, and OOS realization (§12, WF-2/WF-4).

Every scenario feeds :func:`evaluate_window` a small complete-case-aligned matrix and a
hand-built :class:`WindowSpec`, so the train/test bounds - and thus which windows are
positive-definite - are under exact control. The defensive ``INSUFFICIENT_TRAINING`` /
``EMPTY_TEST_WINDOW`` guards cannot arise from the axis-derived generator, so they are
exercised here with directly-constructed degenerate windows.
"""

from __future__ import annotations

from quantforge.walkforward.evaluate import WindowEvaluation, evaluate_window
from quantforge.walkforward.model import (
    StatStatus,
    WalkForwardUndefinedReason,
    WindowStatus,
)
from quantforge.walkforward.version import default_decimal_context
from quantforge.walkforward.windows import WindowSpec

# Two independent series: any span of >= 3 observations is positive-definite; a
# 2-observation span is rank-1 and therefore singular.
_A = ["0.01", "-0.02", "0.03", "-0.01", "0.02"]
_B = ["0.02", "0.01", "-0.03", "0.015", "-0.01"]
_CTX = default_decimal_context()


def _evaluate(series: list[list[str]], window: WindowSpec) -> WindowEvaluation:
    return evaluate_window(series, window, n=2, periods_per_year="1", context=_CTX)


class TestRealized:
    def test_positive_definite_training_window_realizes_oos(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 4))
        assert ev.status is WindowStatus.REALIZED
        assert ev.reason is None
        assert len(ev.weights) == 2
        assert all(w.status is StatStatus.KNOWN for w in ev.weights)
        assert ev.predicted_variance.status is StatStatus.KNOWN
        assert len(ev.oos_returns) == 1

    def test_weights_are_fully_invested(self) -> None:
        from decimal import Decimal

        ev = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 4))
        total = sum(Decimal(w.value) for w in ev.weights if w.value is not None)
        assert total == Decimal(1)

    def test_single_test_period_has_undefined_realized_variance(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 4))
        assert ev.realized_variance.status is StatStatus.UNDEFINED
        assert (
            ev.realized_variance.reason
            is WalkForwardUndefinedReason.SINGLE_VALID_PERIOD
        )

    def test_multi_test_period_has_known_realized_variance(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 5))
        assert ev.status is WindowStatus.REALIZED
        assert len(ev.oos_returns) == 2
        assert ev.realized_variance.status is StatStatus.KNOWN

    def test_determinism(self) -> None:
        a = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 5))
        b = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 5))
        assert a.oos_returns == b.oos_returns
        assert a.predicted_variance == b.predicted_variance


class TestUndefined:
    def test_two_observation_training_is_singular(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 2, 2, 4))
        assert ev.status is WindowStatus.UNDEFINED
        assert ev.reason is WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE
        assert ev.weights == ()
        assert ev.oos_returns == ()

    def test_collinear_factors_are_singular_even_with_enough_obs(self) -> None:
        ev = _evaluate([_A, _A], WindowSpec(0, 0, 3, 3, 4))
        assert ev.status is WindowStatus.UNDEFINED
        assert ev.reason is WalkForwardUndefinedReason.SINGULAR_TRAINING_COVARIANCE


class TestDefensiveGuards:
    def test_short_training_span_hits_insufficient_training(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 1, 1, 2))
        assert ev.status is WindowStatus.UNDEFINED
        assert ev.reason is WalkForwardUndefinedReason.INSUFFICIENT_TRAINING

    def test_empty_test_span_hits_empty_test_window(self) -> None:
        ev = _evaluate([_A, _B], WindowSpec(0, 0, 3, 3, 3))
        assert ev.status is WindowStatus.UNDEFINED
        assert ev.reason is WalkForwardUndefinedReason.EMPTY_TEST_WINDOW
