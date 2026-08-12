"""The pure train->test window partition (§12, WF-2: strict train-before-test)."""

from __future__ import annotations

import pytest

from quantforge.walkforward.spec import (
    WINDOW_EXPANDING,
    WINDOW_ROLLING,
    TrainingPolicy,
)
from quantforge.walkforward.windows import build_windows


def _expanding(min_train: int = 3, test_periods: int = 1) -> TrainingPolicy:
    return TrainingPolicy(
        window=WINDOW_EXPANDING,
        min_train_periods=min_train,
        test_periods=test_periods,
    )


class TestExpanding:
    def test_cuts_and_bounds(self) -> None:
        # M=6, min_train=3, test=1 -> cuts 3,4,5 -> 3 windows.
        windows = build_windows(6, _expanding())
        bounds = [
            (w.train_start, w.train_end, w.test_start, w.test_end) for w in windows
        ]
        assert bounds == [
            (0, 3, 3, 4),
            (0, 4, 4, 5),
            (0, 5, 5, 6),
        ]

    def test_indices_are_dense_and_ordered(self) -> None:
        windows = build_windows(6, _expanding())
        assert [w.index for w in windows] == [0, 1, 2]

    def test_final_test_block_truncates(self) -> None:
        # test_periods=2 over M=6 from min_train=3: cuts 3 (test 3..5), 5 (test 5..6).
        windows = build_windows(6, _expanding(test_periods=2))
        assert [(w.train_end, w.test_start, w.test_end) for w in windows] == [
            (3, 3, 5),
            (5, 5, 6),
        ]

    def test_train_always_grows_from_zero(self) -> None:
        for w in build_windows(6, _expanding()):
            assert w.train_start == 0


class TestRolling:
    def test_train_start_slides(self) -> None:
        policy = TrainingPolicy(
            window=WINDOW_ROLLING,
            min_train_periods=2,
            test_periods=1,
            rolling_length=2,
        )
        # cuts 2,3,4,5 over M=6; rolling length 2 -> train_start = cut-2.
        windows = build_windows(6, policy)
        assert [(w.train_start, w.train_end) for w in windows] == [
            (0, 2),
            (1, 3),
            (2, 4),
            (3, 5),
        ]

    def test_train_start_floored_at_zero(self) -> None:
        policy = TrainingPolicy(
            window=WINDOW_ROLLING,
            min_train_periods=3,
            test_periods=1,
            rolling_length=5,
        )
        # First cut 3, rolling length 5 -> max(0, 3-5) == 0.
        assert build_windows(6, policy)[0].train_start == 0


class TestInvariants:
    @pytest.mark.parametrize("m", range(0, 9))
    def test_strict_train_before_test_no_look_ahead(self, m: int) -> None:
        for w in build_windows(m, _expanding(min_train=2)):
            assert w.train_end == w.test_start  # WF-2: no overlap, no gap
            assert w.train_length >= 2
            assert w.test_length >= 1
            assert 0 <= w.train_start < w.train_end <= w.test_start < w.test_end <= m

    def test_axis_shorter_than_first_cut_yields_none(self) -> None:
        assert build_windows(3, _expanding(min_train=3)) == []
        assert build_windows(2, _expanding(min_train=3)) == []

    def test_exactly_one_more_than_min_train_yields_one_window(self) -> None:
        assert len(build_windows(4, _expanding(min_train=3))) == 1

    def test_negative_length_raises(self) -> None:
        with pytest.raises(ValueError):
            build_windows(-1, _expanding())
