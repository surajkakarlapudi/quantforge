"""The pure stability procedures over synthetic weight paths (§11, WS-3/WS-5)."""

from __future__ import annotations

from decimal import Context, Decimal

from quantforge.stability.compute import SourceWindow, analyze_stability
from quantforge.stability.model import StabilityStatus, StabilityUndefinedReason
from quantforge.stability.version import default_decimal_context


def _ctx() -> Context:
    return default_decimal_context()


def _realized(index: int, weights: list[str]) -> SourceWindow:
    return SourceWindow(
        index=index,
        realized=True,
        weights=tuple(Decimal(w) for w in weights),
    )


def _gap(index: int) -> SourceWindow:
    return SourceWindow(index=index, realized=False, weights=())


def test_per_window_metrics_are_exact_decimal() -> None:
    windows = [
        _realized(0, ["0.5", "0.5"]),
        _realized(1, ["0.5", "-0.5"]),
        _realized(2, ["-0.5", "0.5"]),
    ]
    comp = analyze_stability(windows, min_transitions=2, context=_ctx())
    assert [m.index for m in comp.windows] == [0, 1, 2]
    assert comp.windows[0].gross_leverage == "1.0"
    assert comp.windows[0].concentration_hhi == "0.50"
    assert comp.windows[0].max_abs_weight == "0.5"
    assert comp.windows[0].effective_breadth.value == "2"
    assert comp.windows[1].turnover_from_prev.value == "0.5"
    assert comp.windows[2].turnover_from_prev.value == "1.0"


def test_stable_when_transitions_meet_floor() -> None:
    windows = [
        _realized(0, ["0.5", "0.5"]),
        _realized(1, ["0.5", "-0.5"]),
        _realized(2, ["-0.5", "0.5"]),
    ]
    comp = analyze_stability(windows, min_transitions=2, context=_ctx())
    assert comp.summary.stability_status is StabilityStatus.STABLE
    assert comp.summary.status_reason is None
    assert comp.summary.mean_turnover.value == "0.75"
    assert comp.summary.turnover_dispersion.value == "0.25"


def test_first_window_and_post_gap_window_have_no_prior() -> None:
    windows = [
        _realized(0, ["0.5", "0.5"]),
        _gap(1),
        _realized(2, ["1.0", "0.0"]),
    ]
    comp = analyze_stability(windows, min_transitions=2, context=_ctx())
    # The gap contributes no per-window cell; only realized windows do.
    assert [m.index for m in comp.windows] == [0, 2]
    for metrics in comp.windows:
        assert (
            metrics.turnover_from_prev.reason
            is StabilityUndefinedReason.NO_PRIOR_REALIZED_WINDOW
        )


def test_no_transitions_yields_undefined_turnover_aggregates() -> None:
    windows = [
        _realized(0, ["0.5", "0.5"]),
        _gap(1),
        _realized(2, ["1.0", "0.0"]),
    ]
    comp = analyze_stability(windows, min_transitions=2, context=_ctx())
    s = comp.summary
    for cell in (
        s.mean_turnover,
        s.turnover_dispersion,
        s.max_turnover,
        s.min_turnover,
    ):
        assert cell.reason is StabilityUndefinedReason.NO_TRANSITIONS
    # Concentration is still defined over the realized windows.
    assert s.mean_gross_leverage.value == "1.0"
    assert s.stability_status is StabilityStatus.UNDEFINED
    assert s.status_reason is StabilityUndefinedReason.INSUFFICIENT_TRANSITIONS


def test_all_gaps_yields_no_realized_windows() -> None:
    windows = [_gap(0), _gap(1)]
    comp = analyze_stability(windows, min_transitions=2, context=_ctx())
    assert comp.windows == ()
    s = comp.summary
    # No realized windows: every concentration aggregate UNDEFINED, no divide-by-zero.
    for cell in (
        s.mean_gross_leverage,
        s.max_gross_leverage,
        s.mean_concentration_hhi,
        s.mean_effective_breadth,
    ):
        assert cell.reason is StabilityUndefinedReason.NO_REALIZED_WINDOWS
    # No transitions either.
    assert s.mean_turnover.reason is StabilityUndefinedReason.NO_TRANSITIONS
    assert s.stability_status is StabilityStatus.UNDEFINED


def test_repeated_computation_is_identical() -> None:
    windows = [
        _realized(0, ["0.5", "0.5"]),
        _realized(1, ["0.5", "-0.5"]),
        _realized(2, ["-0.5", "0.5"]),
    ]
    a = analyze_stability(windows, min_transitions=2, context=_ctx())
    b = analyze_stability(windows, min_transitions=2, context=_ctx())
    assert a == b
