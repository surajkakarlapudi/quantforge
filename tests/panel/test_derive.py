"""Deterministic + adversarial tests for the pure multi-period derivations (§3, §8).

Every derivation is a pure function of one filer's ``SeriesPoint`` list under the
pinned decimal context. These tests pin the four disciplines: UNDEFINED-preserving
(a bad endpoint poisons the derivation, recording *which*), exact decimal arithmetic,
divide-by-zero → a value (never Inf/NaN), and KNOWN-only populations for
``level_vs_history``. Insufficient-history is UNDEFINED with no bad-input pointer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quantforge.metrics.model import MetricStatus, UndefinedReason
from quantforge.metrics.version import MetricEngineVersion
from quantforge.panel.derive import Derivation, HistoryStat, SeriesPoint
from quantforge.panel.errors import PanelConfigurationError

CTX = MetricEngineVersion().decimal_context()


def _known(period_key: str, value: str) -> SeriesPoint:
    return SeriesPoint(period_key=period_key, is_known=True, value=Decimal(value))


def _undef(period_key: str) -> SeriesPoint:
    return SeriesPoint(period_key=period_key, is_known=False, value=None)


class TestGrowth:
    def test_growth_first_period_undefined_no_prior(self) -> None:
        out = Derivation.growth().apply([_known("p0", "100")], CTX)
        assert out[0].status is MetricStatus.UNDEFINED
        assert out[0].reason is UndefinedReason.MISSING_INPUT
        assert out[0].undefined_input_period_key is None  # insufficient history

    def test_growth_value(self) -> None:
        out = Derivation.growth().apply([_known("p0", "100"), _known("p1", "150")], CTX)
        assert out[1].status is MetricStatus.KNOWN
        assert out[1].value_numeric_str == "0.5"
        assert out[1].consumed_period_keys == ("p0", "p1")

    def test_growth_undefined_current_names_current(self) -> None:
        out = Derivation.growth().apply([_known("p0", "100"), _undef("p1")], CTX)
        assert out[1].status is MetricStatus.UNDEFINED
        assert out[1].undefined_input_period_key == "p1"

    def test_growth_undefined_prior_names_prior(self) -> None:
        out = Derivation.growth().apply([_undef("p0"), _known("p1", "150")], CTX)
        assert out[1].status is MetricStatus.UNDEFINED
        assert out[1].undefined_input_period_key == "p0"

    def test_growth_zero_prior_is_divide_by_zero(self) -> None:
        out = Derivation.growth().apply([_known("p0", "0"), _known("p1", "150")], CTX)
        assert out[1].status is MetricStatus.UNDEFINED
        assert out[1].reason is UndefinedReason.DIVIDE_BY_ZERO
        assert out[1].undefined_input_period_key == "p0"

    def test_growth_negative_prior_is_fine(self) -> None:
        out = Derivation.growth().apply(
            [_known("p0", "-100"), _known("p1", "-50")], CTX
        )
        # (-50 - -100) / -100 = 50 / -100 = -0.5
        assert out[1].value_numeric_str == "-0.5"


class TestAverageBalance:
    def test_average(self) -> None:
        out = Derivation.average_balance().apply(
            [_known("p0", "100"), _known("p1", "200")], CTX
        )
        assert out[1].value_numeric_str == "150"

    def test_first_period_undefined(self) -> None:
        out = Derivation.average_balance().apply([_known("p0", "100")], CTX)
        assert out[0].status is MetricStatus.UNDEFINED

    def test_undefined_endpoint_poisons(self) -> None:
        out = Derivation.average_balance().apply(
            [_undef("p0"), _known("p1", "200")], CTX
        )
        assert out[1].status is MetricStatus.UNDEFINED
        assert out[1].undefined_input_period_key == "p0"


class TestTtm:
    def test_ttm_sums_four_quarters(self) -> None:
        series = [
            _known("q1", "10"),
            _known("q2", "20"),
            _known("q3", "30"),
            _known("q4", "40"),
        ]
        out = Derivation.ttm().apply(series, CTX)
        # First three lack four-quarter history.
        assert all(c.status is MetricStatus.UNDEFINED for c in out[:3])
        assert out[3].status is MetricStatus.KNOWN
        assert out[3].value_numeric_str == "100"
        assert out[3].consumed_period_keys == ("q1", "q2", "q3", "q4")

    def test_ttm_rolls_forward(self) -> None:
        series = [_known(f"q{i}", str(i * 10)) for i in range(1, 6)]
        out = Derivation.ttm().apply(series, CTX)
        # q2..q5 = 20+30+40+50 = 140
        assert out[4].value_numeric_str == "140"

    def test_ttm_undefined_quarter_poisons_window(self) -> None:
        series = [
            _known("q1", "10"),
            _undef("q2"),
            _known("q3", "30"),
            _known("q4", "40"),
        ]
        out = Derivation.ttm().apply(series, CTX)
        assert out[3].status is MetricStatus.UNDEFINED
        assert out[3].undefined_input_period_key == "q2"


class TestLevelVsHistory:
    def test_median_difference(self) -> None:
        series = [
            _known("p0", "10"),
            _known("p1", "20"),
            _known("p2", "30"),
            _known("p3", "100"),
        ]
        out = Derivation.level_vs_history(window=3).apply(series, CTX)
        # prior window [10,20,30] median 20; current 100 → 100 - 20 = 80
        assert out[3].value_numeric_str == "80"

    def test_min_and_max(self) -> None:
        series = [_known("p0", "10"), _known("p1", "20"), _known("p2", "5")]
        out_min = Derivation.level_vs_history(window=2, stat=HistoryStat.MIN).apply(
            series, CTX
        )
        out_max = Derivation.level_vs_history(window=2, stat=HistoryStat.MAX).apply(
            series, CTX
        )
        # window [10,20]: min 10 → 5-10=-5; max 20 → 5-20=-15
        assert out_min[2].value_numeric_str == "-5"
        assert out_max[2].value_numeric_str == "-15"

    def test_insufficient_history_undefined(self) -> None:
        out = Derivation.level_vs_history(window=3).apply(
            [_known("p0", "10"), _known("p1", "20")], CTX
        )
        assert all(c.status is MetricStatus.UNDEFINED for c in out)

    def test_undefined_cells_excluded_from_population(self) -> None:
        # window has one UNDEFINED; median computed over the KNOWN survivor only.
        series = [_known("p0", "10"), _undef("p1"), _known("p2", "30")]
        out = Derivation.level_vs_history(window=2).apply(series, CTX)
        # prior window [p0=10, p1=UNDEF] → population {10}; median 10; 30-10=20
        assert out[2].value_numeric_str == "20"

    def test_all_prior_undefined_is_undefined(self) -> None:
        series = [_undef("p0"), _undef("p1"), _known("p2", "30")]
        out = Derivation.level_vs_history(window=2).apply(series, CTX)
        assert out[2].status is MetricStatus.UNDEFINED

    def test_current_undefined_poisons(self) -> None:
        series = [_known("p0", "10"), _known("p1", "20"), _undef("p2")]
        out = Derivation.level_vs_history(window=2).apply(series, CTX)
        assert out[2].status is MetricStatus.UNDEFINED
        assert out[2].undefined_input_period_key == "p2"

    def test_even_population_median_is_mean_of_middles(self) -> None:
        series = [
            _known("p0", "10"),
            _known("p1", "20"),
            _known("p2", "30"),
            _known("p3", "40"),
            _known("p4", "100"),
        ]
        out = Derivation.level_vs_history(window=4).apply(series, CTX)
        # window [10,20,30,40]: median (20+30)/2 = 25; 100-25 = 75
        assert out[4].value_numeric_str == "75"

    def test_non_positive_window_rejected(self) -> None:
        with pytest.raises(PanelConfigurationError):
            Derivation.level_vs_history(window=0)


class TestDerivationIdentity:
    def test_ids(self) -> None:
        assert Derivation.none().derivation_id == "none"
        assert Derivation.growth().derivation_id == "growth"
        assert Derivation.ttm().derivation_id == "ttm"
        assert Derivation.average_balance().derivation_id == "average_balance"
        assert (
            Derivation.level_vs_history(window=4, stat=HistoryStat.MEDIAN).derivation_id
            == "level_vs_history:median:4"
        )

    def test_level_vs_history_id_varies_by_stat_and_window(self) -> None:
        a = Derivation.level_vs_history(window=4, stat=HistoryStat.MIN).derivation_id
        b = Derivation.level_vs_history(window=8, stat=HistoryStat.MIN).derivation_id
        c = Derivation.level_vs_history(window=4, stat=HistoryStat.MAX).derivation_id
        assert a != b != c and a != c

    def test_none_apply_is_a_bug(self) -> None:
        # The engine skips the identity derivation; calling apply is a config error.
        with pytest.raises(PanelConfigurationError):
            Derivation.none().apply([_known("p0", "1")], CTX)


class TestRequiredPeriodType:
    def test_ttm_requires_duration(self) -> None:
        from quantforge.xbrl.contexts import PeriodType

        assert Derivation.ttm().required_period_type() is PeriodType.DURATION

    def test_others_require_nothing(self) -> None:
        assert Derivation.growth().required_period_type() is None
        assert Derivation.none().required_period_type() is None
