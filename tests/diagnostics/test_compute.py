"""Pure diagnostics statistics: hand-checked values, UNDEFINED preservation,
determinism.

Covers locked §4 / §7 / D11. Every expectation is computed by hand from a small fixed
vector, so a silent formula change is caught. The functions are pure (they take
decimal-string vectors directly, read no store), so no corpus is needed here. An
undefined statistic must be a first-class UNDEFINED with the right reason, never a
fabricated ``0`` / ``NaN`` / ``Inf`` and never a divide-by-zero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.diagnostics.compute import (
    forward_return,
    ic_summary,
    pearson_ic,
    quantile_buckets,
    quantile_profile,
    rank_ic,
    top_minus_bottom,
)
from quantforge.diagnostics.errors import SignalDiagnosticsConfigurationError
from quantforge.diagnostics.model import (
    DiagnosticStatus,
    DiagnosticUndefinedReason,
    StatValue,
)
from quantforge.diagnostics.version import default_decimal_context

CTX = default_decimal_context()


def _known(cell: StatValue, expected: str) -> None:
    assert cell.status is DiagnosticStatus.KNOWN
    assert cell.value is not None
    assert Decimal(cell.value) == Decimal(expected)


def _undef(cell: StatValue, reason: DiagnosticUndefinedReason) -> None:
    assert cell.status is DiagnosticStatus.UNDEFINED
    assert cell.reason is reason


def _known_close(cell: StatValue, expected: Decimal, *, tol: str = "1e-28") -> None:
    """KNOWN cell whose value equals ``expected`` within ``tol``.

    Population Pearson divides ``cov`` by the product of two independent
    ``Decimal.sqrt`` results, so a mathematically exact ``1`` / ``-1`` can in principle
    land an ulp away. These tests assert the *statistic*, not the last rounding digit,
    so they compare the
    absolute difference against a small tolerance rather than for byte-equality.
    """
    assert cell.status is DiagnosticStatus.KNOWN
    assert cell.value is not None
    assert abs(Decimal(cell.value) - expected) <= Decimal(tol)


class TestForwardReturn:
    def test_simple_gain(self) -> None:
        assert forward_return("10", "11", context=CTX) == "0.1"

    def test_simple_loss(self) -> None:
        assert forward_return("10", "8", context=CTX) == "-0.2"

    def test_non_positive_base_is_none(self) -> None:
        # A non-positive base cannot form a meaningful return → dropped for return
        # (SD-4).
        assert forward_return("0", "5", context=CTX) is None
        assert forward_return("-1", "5", context=CTX) is None

    def test_non_finite_price_fails_closed(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="finite"):
            forward_return("Infinity", "5", context=CTX)


class TestPearsonIC:
    def test_perfect_positive(self) -> None:
        _known_close(
            pearson_ic(["1", "2", "3"], ["2", "4", "6"], context=CTX), Decimal(1)
        )

    def test_perfect_negative(self) -> None:
        _known_close(
            pearson_ic(["1", "2", "3"], ["6", "4", "2"], context=CTX), Decimal(-1)
        )

    def test_insufficient_pairs(self) -> None:
        _undef(
            pearson_ic(["1"], ["2"], context=CTX),
            DiagnosticUndefinedReason.INSUFFICIENT_PAIRS,
        )

    def test_constant_signal_is_zero_signal_variance(self) -> None:
        _undef(
            pearson_ic(["5", "5", "5"], ["1", "2", "3"], context=CTX),
            DiagnosticUndefinedReason.ZERO_SIGNAL_VARIANCE,
        )

    def test_constant_return_is_zero_return_variance(self) -> None:
        _undef(
            pearson_ic(["1", "2", "3"], ["5", "5", "5"], context=CTX),
            DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE,
        )

    def test_mismatched_lengths_fail_closed(self) -> None:
        with pytest.raises(SignalDiagnosticsConfigurationError, match="same length"):
            pearson_ic(["1", "2"], ["1"], context=CTX)


class TestRankIC:
    def test_monotonic_is_one_even_when_nonlinear(self) -> None:
        # Ranks are perfectly aligned though the values are nonlinear → Spearman 1.
        _known_close(
            rank_ic(["1", "2", "3"], ["1", "10", "1000"], context=CTX), Decimal(1)
        )

    def test_perfect_inversion_is_minus_one(self) -> None:
        _known_close(
            rank_ic(["1", "2", "3"], ["9", "8", "7"], context=CTX), Decimal(-1)
        )

    def test_ties_use_average_ranks(self) -> None:
        # Signals (1, 1, 2): the two tied 1s share rank (1+2)/2 = 1.5; the 2 gets 3.
        # Returns strictly increasing → rank_y = (1, 2, 3). rank_x = (1.5, 1.5, 3).
        # Pearson of (1.5,1.5,3) vs (1,2,3): cov and sx computed by hand →
        # mean_x = 2, mean_y = 2; dev_x = (-0.5,-0.5,1), dev_y = (-1,0,1).
        # cov = (0.5 + 0 + 1)/3 = 0.5; var_x = (0.25+0.25+1)/3 = 0.5; var_y = 2/3.
        # r = 0.5 / (sqrt(0.5)*sqrt(2/3)) = 0.5 / sqrt(1/3) = 0.5*sqrt(3).
        cell = rank_ic(["1", "1", "2"], ["10", "20", "30"], context=CTX)
        assert cell.status is DiagnosticStatus.KNOWN
        assert cell.value is not None
        expected = (Decimal("0.5") * Decimal(3).sqrt(CTX)).quantize(Decimal("1e-20"))
        assert Decimal(cell.value).quantize(Decimal("1e-20")) == expected

    def test_insufficient_pairs(self) -> None:
        _undef(
            rank_ic(["1"], ["2"], context=CTX),
            DiagnosticUndefinedReason.INSUFFICIENT_PAIRS,
        )


class TestQuantileBuckets:
    def test_floor_bucketing_orders_by_signal(self) -> None:
        # Four members, q=2 → floor(i*2/4): i=0,1 → bucket 0; i=2,3 → bucket 1.
        # Ordered by signal asc: (c1,1,0.0),(c2,2,0.1),(c3,3,0.2),(c4,4,0.3).
        members = [
            ("c4", "4", "0.3"),
            ("c1", "1", "0.0"),
            ("c3", "3", "0.2"),
            ("c2", "2", "0.1"),
        ]
        cells = quantile_buckets(members, 2, context=CTX)
        assert len(cells) == 2
        _known(cells[0], "0.05")  # mean(0.0, 0.1)
        _known(cells[1], "0.25")  # mean(0.2, 0.3)

    def test_tie_break_by_company_id(self) -> None:
        # Equal signals → ordered by company_id; q=2, n=2 → one per bucket.
        members = [("zzz", "5", "0.2"), ("aaa", "5", "0.1")]
        cells = quantile_buckets(members, 2, context=CTX)
        _known(cells[0], "0.1")  # aaa sorts first
        _known(cells[1], "0.2")

    def test_empty_bucket_when_fewer_members_than_quantiles(self) -> None:
        # n=2, q=3 → floor(i*3/2): i=0→0, i=1→1; bucket 2 empty.
        members = [("a", "1", "0.1"), ("b", "2", "0.2")]
        cells = quantile_buckets(members, 3, context=CTX)
        _known(cells[0], "0.1")
        _known(cells[1], "0.2")
        _undef(cells[2], DiagnosticUndefinedReason.EMPTY_BUCKET)

    def test_no_members_all_empty(self) -> None:
        cells = quantile_buckets([], 3, context=CTX)
        assert len(cells) == 3
        for cell in cells:
            _undef(cell, DiagnosticUndefinedReason.EMPTY_BUCKET)


class TestTopMinusBottom:
    def test_spread_is_top_minus_bottom(self) -> None:
        buckets = (StatValue.known("0.05"), StatValue.known("0.25"))
        _known(top_minus_bottom(buckets, context=CTX), "0.2")

    def test_empty_endpoint_is_empty_bucket(self) -> None:
        buckets = (
            StatValue.known("0.05"),
            StatValue.undefined(DiagnosticUndefinedReason.EMPTY_BUCKET),
        )
        _undef(
            top_minus_bottom(buckets, context=CTX),
            DiagnosticUndefinedReason.EMPTY_BUCKET,
        )


class TestQuantileProfile:
    def test_averages_known_across_dates(self) -> None:
        # Two dates, two buckets: bucket 0 = mean(0.0, 0.2) = 0.1; bucket 1 =
        # mean(0.1, 0.3) = 0.2.
        per_date: list[tuple[StatValue, ...]] = [
            (StatValue.known("0.0"), StatValue.known("0.1")),
            (StatValue.known("0.2"), StatValue.known("0.3")),
        ]
        spreads = [StatValue.known("0.1"), StatValue.known("0.1")]
        buckets, mean_spread = quantile_profile(per_date, spreads, 2, context=CTX)
        _known(buckets[0], "0.1")
        _known(buckets[1], "0.2")
        _known(mean_spread, "0.1")

    def test_bucket_known_on_no_date_is_empty(self) -> None:
        empty = StatValue.undefined(DiagnosticUndefinedReason.EMPTY_BUCKET)
        per_date: list[tuple[StatValue, ...]] = [(StatValue.known("0.1"), empty)]
        spreads = [StatValue.undefined(DiagnosticUndefinedReason.EMPTY_BUCKET)]
        buckets, mean_spread = quantile_profile(per_date, spreads, 2, context=CTX)
        _known(buckets[0], "0.1")
        _undef(buckets[1], DiagnosticUndefinedReason.EMPTY_BUCKET)
        _undef(mean_spread, DiagnosticUndefinedReason.NO_VALID_DATES)


class TestICSummary:
    def test_hand_computed_summary(self) -> None:
        # IC series (0.2, 0.4, -0.3): mean = 0.1; positives = 2 → hit_rate = 2/3.
        # var = ((0.1)^2 + (0.3)^2 + (-0.4)^2)/3 = (0.01+0.09+0.16)/3 = 0.26/3.
        series = [
            StatValue.known("0.2"),
            StatValue.known("0.4"),
            StatValue.known("-0.3"),
        ]
        mean, std, ratio, t_stat, hit_rate, n_valid = ic_summary(series, context=CTX)
        assert n_valid == 3
        _known(mean, "0.1")
        expected_std = (Decimal("0.26") / Decimal(3)).sqrt(CTX)
        assert std.value is not None
        assert Decimal(std.value).quantize(Decimal("1e-20")) == expected_std.quantize(
            Decimal("1e-20")
        )
        # ratio = mean/std; t_stat = ratio*sqrt(3).
        assert ratio.value is not None and t_stat.value is not None
        r = Decimal("0.1") / expected_std
        assert Decimal(ratio.value).quantize(Decimal("1e-18")) == r.quantize(
            Decimal("1e-18")
        )
        assert Decimal(t_stat.value).quantize(Decimal("1e-18")) == (
            r * Decimal(3).sqrt(CTX)
        ).quantize(Decimal("1e-18"))
        # hit_rate = 2/3 under the pinned context; compare to the context-computed value
        # rather than a hardcoded digit count.
        assert hit_rate.value is not None
        assert Decimal(hit_rate.value) == CTX.divide(Decimal(2), Decimal(3))

    def test_no_valid_dates_is_all_undefined(self) -> None:
        series = [
            StatValue.undefined(DiagnosticUndefinedReason.INSUFFICIENT_PAIRS),
        ]
        mean, std, ratio, t_stat, hit_rate, n_valid = ic_summary(series, context=CTX)
        assert n_valid == 0
        for cell in (mean, std, ratio, t_stat, hit_rate):
            _undef(cell, DiagnosticUndefinedReason.NO_VALID_DATES)

    def test_constant_ic_series_ratio_undefined(self) -> None:
        # A constant IC series has zero dispersion → ratio/t-stat undefined, never /0.
        series = [StatValue.known("0.2"), StatValue.known("0.2")]
        mean, std, ratio, t_stat, hit_rate, _n_valid = ic_summary(series, context=CTX)
        _known(mean, "0.2")
        _known(std, "0")
        _undef(ratio, DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE)
        _undef(t_stat, DiagnosticUndefinedReason.ZERO_RETURN_VARIANCE)
        _known(hit_rate, "1")


class TestDeterminism:
    def test_recompute_is_byte_identical(self) -> None:
        s = ["1", "2", "3", "4"]
        r = ["0.1", "0.3", "0.2", "0.4"]
        a = rank_ic(s, r, context=default_decimal_context())
        b = rank_ic(s, r, context=default_decimal_context())
        assert a.to_dict() == b.to_dict()
