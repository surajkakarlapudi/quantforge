"""Pure, deterministic train->test window partition of the aligned axis (§12, WF-2).

The complete-case-aligned factor-return axis has ``M`` ordered periods (indices
``0..M-1``), each an ``as_of`` instant where **every** factor carries a KNOWN return
(the engine builds it via the Phase 20 alignment idiom). This module partitions that
axis into ordered train->test windows governed by a
:class:`~quantforge.walkforward.spec.TrainingPolicy`, with **no store, no decimal, no
float, no wall-clock, no RNG** - a pure function of two integers and the policy, so
identical inputs reproduce identical windows on any machine.

**The load-bearing invariant is WF-2: strict train-before-test, no look-ahead.** Each
window is a pair of half-open index ranges ``[train_start, train_end)`` and
``[test_start, test_end)`` with ``train_end == test_start`` - the test span begins
exactly where the training span ends, so a window's GMV weights (estimated on the
training span) are only ever realized against **strictly-subsequent** returns. The
training span never overlaps the test span, and no future period ever informs a window's
weights.

The rebalance cuts are ``c_k = min_train_periods + k · test_periods`` for ``k = 0, 1,
...`` while ``c_k < M`` (so every emitted window has at least one test period). The
training span is:

* **expanding** - ``[0, c_k)`` (the whole aligned history up to the cut);
* **rolling** - ``[max(0, c_k - rolling_length), c_k)`` (the most recent
  ``rolling_length`` periods up to the cut).

The test span is ``[c_k, min(c_k + test_periods, M))`` - a full ``test_periods`` block,
truncated only for the final window when the axis runs out. Because ``c_k >= min_train``
and ``c_k < M`` for every emitted window, the training span is always at least
``min_train_periods`` long and the test span is always non-empty - so the
``INSUFFICIENT_TRAINING`` / ``EMPTY_TEST_WINDOW`` reasons are structurally unreachable
here (retained as defensive guards in the evaluate layer, WF-4).
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.walkforward.spec import WINDOW_ROLLING, TrainingPolicy

__all__ = [
    "WindowSpec",
    "build_windows",
]


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """One train->test window as half-open index ranges over the aligned axis (WF-2).

    ``index`` is the 0-based window ordinal in schedule order. ``[train_start,
    train_end)`` is the training span and ``[test_start, test_end)`` the test span, with
    ``train_end == test_start`` (strict train-before-test, no overlap). All four are
    axis indices, not dates; the engine maps them back to the aligned ``as_of`` axis.
    """

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def train_length(self) -> int:
        """The number of training periods (``train_end - train_start``)."""
        return self.train_end - self.train_start

    @property
    def test_length(self) -> int:
        """The number of test periods (``test_end - test_start``)."""
        return self.test_end - self.test_start


def build_windows(m: int, policy: TrainingPolicy) -> list[WindowSpec]:
    """Partition an ``M``-period aligned axis into ordered train->test windows (§12).

    ``m`` is the aligned-axis length; ``policy`` the :class:`TrainingPolicy`. Returns
    the windows in schedule order (possibly empty when the axis is shorter than
    ``min_train_periods + 1``). Pure: no store, no decimal, no float, no wall-clock, no
    RNG. Every emitted window satisfies WF-2 (``train_end == test_start``), has a
    training span of at least ``min_train_periods`` periods, and a non-empty test span.
    """
    if m < 0:
        raise ValueError("the aligned-axis length must be non-negative")
    windows: list[WindowSpec] = []
    index = 0
    cut = policy.min_train_periods
    while cut < m:
        if policy.window == WINDOW_ROLLING:
            assert policy.rolling_length is not None  # guaranteed by TrainingPolicy
            train_start = max(0, cut - policy.rolling_length)
        else:
            train_start = 0
        test_end = min(cut + policy.test_periods, m)
        windows.append(
            WindowSpec(
                index=index,
                train_start=train_start,
                train_end=cut,
                test_start=cut,
                test_end=test_end,
            )
        )
        index += 1
        cut += policy.test_periods
    return windows
