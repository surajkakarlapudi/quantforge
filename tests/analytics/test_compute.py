"""Pure statistic functions: hand-checked values, UNDEFINED preservation, determinism.

Covers proposal §J.3 / D4 / D5 / D7 / D11. Every expectation is computed by hand from a
small fixed vector so a silent formula change is caught. The functions are pure, so no
corpus is needed here — they take decimal-string vectors directly. Undefined statistics
must be first-class UNDEFINED with the right reason, never a fabricated ``0`` / ``NaN``
/ ``Inf`` and never a divide-by-zero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.analytics.compute import (
    absolute_statistics,
    parse_returns,
    relative_statistics,
    var_statistics,
)
from quantforge.analytics.errors import AnalyticsConfigurationError
from quantforge.analytics.model import (
    ABSOLUTE_KEYS,
    RELATIVE_KEYS,
    AnalyticsStatus,
    AnalyticsUndefinedReason,
    StatValue,
)
from quantforge.analytics.version import default_decimal_context


def _abs(returns: list[str], **kw: str) -> dict[str, StatValue]:
    ctx = default_decimal_context()
    kw.setdefault("risk_free_per_period", "0")
    kw.setdefault("periods_per_year", "1")
    cells = absolute_statistics(returns, context=ctx, **kw)
    return dict(cells)


def _rel(subject: list[str], benchmark: list[str], **kw: str) -> dict[str, StatValue]:
    ctx = default_decimal_context()
    kw.setdefault("risk_free_per_period", "0")
    kw.setdefault("periods_per_year", "1")
    cells = relative_statistics(subject, benchmark, context=ctx, **kw)
    return dict(cells)


def _known(cell: StatValue, expected: str) -> None:
    assert cell.status is AnalyticsStatus.KNOWN
    assert cell.value is not None
    assert Decimal(cell.value) == Decimal(expected)


def _undef(cell: StatValue, reason: AnalyticsUndefinedReason) -> None:
    assert cell.status is AnalyticsStatus.UNDEFINED
    assert cell.reason is reason


class TestParse:
    def test_non_decimal_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="valid decimal"):
            parse_returns(["oops"], context=default_decimal_context())

    def test_non_finite_fails_closed(self) -> None:
        with pytest.raises(AnalyticsConfigurationError, match="finite"):
            parse_returns(["Infinity"], context=default_decimal_context())

    def test_canonicalizes_under_context(self) -> None:
        parsed = parse_returns(["0.100", "-0.0"], context=default_decimal_context())
        assert [str(v) for v in parsed] == ["0.100", "0.0"]


class TestAbsoluteBlock:
    def test_returns_exactly_the_closed_key_set_sorted(self) -> None:
        out = _abs(["0.1", "-0.05", "0.2", "-0.1"])
        assert tuple(sorted(out)) == ABSOLUTE_KEYS
        assert tuple(out) == ABSOLUTE_KEYS  # already sorted

    def test_best_worst_and_positive_fraction(self) -> None:
        out = _abs(["0.1", "-0.05", "0.2", "-0.1"])
        _known(out["best_period_return"], "0.2")
        _known(out["worst_period_return"], "-0.1")
        _known(out["positive_period_fraction"], "0.5")

    def test_sortino_with_no_downside_is_zero_downside(self) -> None:
        # rf = 0, all returns >= 0 → no below-target observation → downside dev 0.
        out = _abs(["0.1", "0.1", "0.1"])
        _undef(out["sortino"], AnalyticsUndefinedReason.ZERO_DOWNSIDE)
        _known(out["downside_deviation"], "0")

    def test_constant_series_has_undefined_shape(self) -> None:
        out = _abs(["0.05", "0.05", "0.05"])
        _undef(out["skewness"], AnalyticsUndefinedReason.ZERO_VARIANCE)
        _undef(out["excess_kurtosis"], AnalyticsUndefinedReason.ZERO_VARIANCE)

    def test_flat_then_up_never_draws_down(self) -> None:
        out = _abs(["0.1", "0.1"])
        _undef(out["calmar"], AnalyticsUndefinedReason.NO_DRAWDOWN)
        _undef(
            out["max_drawdown_duration_periods"],
            AnalyticsUndefinedReason.NO_DRAWDOWN,
        )
        _undef(
            out["max_drawdown_recovery_periods"],
            AnalyticsUndefinedReason.NO_DRAWDOWN,
        )

    def test_drawdown_with_recovery(self) -> None:
        # curve: 1 → 0.5 → 1.0 → 1.1. Deepest dd = -0.5 at index 1 (peak index 0),
        # duration 1, recovers to peak (1.0) at index 2 → recovery 1.
        out = _abs(["-0.5", "1.0", "0.1"])
        _known(out["max_drawdown_duration_periods"], "1")
        _known(out["max_drawdown_recovery_periods"], "1")
        _known(out["calmar"], "0.4")  # mean(0.2)*ppy(1)/magnitude(0.5)

    def test_unrecovered_drawdown(self) -> None:
        # curve: 1 → 1.1 → 0.99. Peak at index 1, trough index 2, never regained.
        out = _abs(["0.1", "-0.1"])
        _known(out["max_drawdown_duration_periods"], "1")
        _undef(
            out["max_drawdown_recovery_periods"],
            AnalyticsUndefinedReason.UNRECOVERED_DRAWDOWN,
        )

    def test_annualization_scales_sortino(self) -> None:
        # ppy = 4 → sortino scales by sqrt(4) = 2 relative to ppy = 1. (Compared at 20
        # places: the two independently-rounded 34-digit values agree well within that.)
        base = _abs(["0.1", "-0.05", "0.2", "-0.1"], periods_per_year="1")
        scaled = _abs(["0.1", "-0.05", "0.2", "-0.1"], periods_per_year="4")
        base_value = base["sortino"].value
        scaled_value = scaled["sortino"].value
        assert base_value is not None and scaled_value is not None
        b = Decimal(base_value)
        s = Decimal(scaled_value)
        places = Decimal("1e-20")
        assert s.quantize(places) == (b * 2).quantize(places)


class TestRelativeBlock:
    def test_returns_exactly_the_closed_key_set_sorted(self) -> None:
        out = _rel(["0.1", "-0.05", "0.2"], ["0.05", "-0.1", "0.15"])
        assert tuple(out) == RELATIVE_KEYS

    def test_identical_series_beta_one_alpha_zero_correlation_one(self) -> None:
        v = ["0.1", "-0.05", "0.2", "-0.1"]
        out = _rel(v, v)
        _known(out["beta"], "1")
        _known(out["alpha"], "0")
        _known(out["correlation"], "1")
        _known(out["active_return"], "0")
        _undef(
            out["information_ratio"],
            AnalyticsUndefinedReason.ZERO_TRACKING_ERROR,
        )

    def test_doubled_series_beta_two_capture_two(self) -> None:
        bench = ["0.1", "-0.05", "0.2", "-0.1"]
        subject = ["0.2", "-0.1", "0.4", "-0.2"]
        out = _rel(subject, bench)
        _known(out["beta"], "2")
        _known(out["alpha"], "0")
        _known(out["up_capture"], "2")
        _known(out["down_capture"], "2")

    def test_flat_benchmark_is_zero_benchmark_variance(self) -> None:
        # A positive flat benchmark has no variance (beta/alpha/correlation undefined)
        # and no down periods (down_capture undefined), but its up periods still sum to
        # a non-zero denominator, so up_capture is a defined ratio.
        out = _rel(["0.1", "-0.05", "0.2"], ["0.05", "0.05", "0.05"])
        _undef(out["beta"], AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
        _undef(out["alpha"], AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
        _undef(out["correlation"], AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)
        _undef(out["down_capture"], AnalyticsUndefinedReason.ZERO_BENCHMARK_VARIANCE)

    def test_flat_subject_correlation_is_zero_variance(self) -> None:
        out = _rel(["0.05", "0.05", "0.05"], ["0.1", "-0.05", "0.2"])
        _undef(out["correlation"], AnalyticsUndefinedReason.ZERO_VARIANCE)

    def test_active_and_cumulative_active_return(self) -> None:
        # subject mean 0.0625, benchmark mean 0.0375 (from doubled fixture) → 0.025.
        bench = ["0.1", "-0.05", "0.2", "-0.1"]
        subject = ["0.2", "-0.1", "0.4", "-0.2"]
        out = _rel(subject, bench)
        _known(out["active_return"], "0.0375")
        # cum_subject = 1.2*0.9*1.4*0.8 - 1; cum_bench = 1.1*0.95*1.2*0.9 - 1.
        _known(out["cumulative_active_return"], "0.081")


class TestVar:
    def test_nearest_rank_on_fixed_vector(self) -> None:
        # 20 returns -0.10 .. 0.09 in 0.01 steps (ascending).
        returns = [f"{(-10 + i) / 100:.2f}" for i in range(20)]
        cells = var_statistics(
            returns, ["0.95", "0.90"], context=default_decimal_context()
        )
        by_conf = {c: (v, cv) for c, v, cv in cells}
        # c=0.95: k = ceil(0.05*20)=1; var = smallest = -0.10; cvar = mean(1) = -0.10.
        v95, cv95 = by_conf["0.95"]
        _known(v95, "-0.10")
        _known(cv95, "-0.10")
        # c=0.90: k = ceil(0.10*20)=2; var = 2nd smallest = -0.09; cvar avgs both.
        v90, cv90 = by_conf["0.90"]
        _known(v90, "-0.09")
        _known(cv90, "-0.095")

    def test_triples_sorted_by_confidence(self) -> None:
        returns = ["0.1", "-0.05", "0.2", "-0.1"]
        cells = var_statistics(
            returns, ["0.99", "0.90", "0.95"], context=default_decimal_context()
        )
        confidences = [c for c, _, _ in cells]
        assert confidences == sorted(confidences)


class TestDeterminism:
    def test_recompute_is_byte_identical(self) -> None:
        v = ["0.1", "-0.05", "0.2", "-0.1"]
        a = absolute_statistics(
            v,
            risk_free_per_period="0",
            periods_per_year="12",
            context=default_decimal_context(),
        )
        b = absolute_statistics(
            v,
            risk_free_per_period="0",
            periods_per_year="12",
            context=default_decimal_context(),
        )
        assert [(k, c.to_dict()) for k, c in a] == [(k, c.to_dict()) for k, c in b]
