"""Deterministic + adversarial tests for :class:`PeriodAxis` (locked §4, §5).

The axis is *part of the request* (never "all locally-ingested periods"), explicit,
ordered, de-duplicated, and content-addressed. These tests pin: the two generator
frequencies over both period kinds, calendar edge cases (leap Februaries,
quarter-end walks), the total-order materialization, duplicate/empty rejection, and
the D7 identity discipline (explicit-vs-generator never collide; a param change is a
new id; re-declaration reproduces).
"""

from __future__ import annotations

import pytest

from quantforge.metrics.model import MetricPeriod
from quantforge.panel.axis import PeriodAxis
from quantforge.panel.errors import PanelConfigurationError
from quantforge.xbrl.contexts import PeriodType


class TestExplicitAxis:
    def test_of_preserves_and_sorts_by_total_order(self) -> None:
        # Declared out of order; materialized in the §2 total order (by period_end).
        axis = PeriodAxis.of(
            [
                MetricPeriod.instant("2020-12-31"),
                MetricPeriod.instant("2018-12-31"),
                MetricPeriod.instant("2019-12-31"),
            ]
        )
        assert [p.period_end for p in axis] == [
            "2018-12-31",
            "2019-12-31",
            "2020-12-31",
        ]

    def test_empty_axis_fails_closed(self) -> None:
        with pytest.raises(PanelConfigurationError):
            PeriodAxis.of([])

    def test_duplicate_period_rejected(self) -> None:
        with pytest.raises(PanelConfigurationError):
            PeriodAxis.of(
                [MetricPeriod.instant("2020-12-31"), MetricPeriod.instant("2020-12-31")]
            )

    def test_len_and_iter(self) -> None:
        axis = PeriodAxis.of(
            [MetricPeriod.instant("2018-12-31"), MetricPeriod.instant("2019-12-31")]
        )
        assert len(axis) == 2
        assert len(list(axis)) == 2


class TestAnnualGenerator:
    def test_annual_instant_points(self) -> None:
        axis = PeriodAxis.annual(
            "2018-12-31", "2021-12-31", period_type=PeriodType.INSTANT
        )
        assert [p.period_end for p in axis] == [
            "2018-12-31",
            "2019-12-31",
            "2020-12-31",
            "2021-12-31",
        ]
        assert all(p.period_type is PeriodType.INSTANT for p in axis)
        assert all(p.period_start is None for p in axis)

    def test_annual_duration_spans_the_year(self) -> None:
        axis = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.DURATION
        )
        spans = [(p.period_start, p.period_end) for p in axis]
        assert spans == [
            ("2018-01-01", "2018-12-31"),
            ("2019-01-01", "2019-12-31"),
        ]

    def test_single_period_axis(self) -> None:
        axis = PeriodAxis.annual(
            "2020-12-31", "2020-12-31", period_type=PeriodType.INSTANT
        )
        assert len(axis) == 1

    def test_leap_february_end(self) -> None:
        # A Feb-29 year-over-year walk stays on month-end (2020 leap → 2021 non-leap).
        axis = PeriodAxis.annual(
            "2020-02-29", "2021-02-28", period_type=PeriodType.INSTANT
        )
        assert [p.period_end for p in axis] == ["2020-02-29", "2021-02-28"]


class TestQuarterlyGenerator:
    def test_quarterly_instant_walk_stays_on_quarter_ends(self) -> None:
        axis = PeriodAxis.quarterly(
            "2018-03-31", "2018-12-31", period_type=PeriodType.INSTANT
        )
        assert [p.period_end for p in axis] == [
            "2018-03-31",
            "2018-06-30",
            "2018-09-30",
            "2018-12-31",
        ]

    def test_quarterly_duration_spans_three_months(self) -> None:
        axis = PeriodAxis.quarterly(
            "2018-09-30", "2018-09-30", period_type=PeriodType.DURATION
        )
        (period,) = list(axis)
        assert period.period_start == "2018-07-01"
        assert period.period_end == "2018-09-30"


class TestGeneratorValidation:
    def test_start_after_end_fails(self) -> None:
        with pytest.raises(PanelConfigurationError):
            PeriodAxis.annual(
                "2021-12-31", "2018-12-31", period_type=PeriodType.INSTANT
            )

    def test_malformed_date_fails(self) -> None:
        with pytest.raises(PanelConfigurationError):
            PeriodAxis.annual(
                "not-a-date", "2018-12-31", period_type=PeriodType.INSTANT
            )

    def test_forever_period_type_rejected(self) -> None:
        with pytest.raises(PanelConfigurationError):
            PeriodAxis.annual(
                "2018-12-31", "2019-12-31", period_type=PeriodType.FOREVER
            )


class TestAxisIdentity:
    def test_redeclaration_reproduces_id(self) -> None:
        a = PeriodAxis.annual(
            "2018-12-31", "2021-12-31", period_type=PeriodType.INSTANT
        )
        b = PeriodAxis.annual(
            "2018-12-31", "2021-12-31", period_type=PeriodType.INSTANT
        )
        assert a.axis_id == b.axis_id

    def test_param_change_changes_id(self) -> None:
        a = PeriodAxis.annual(
            "2018-12-31", "2021-12-31", period_type=PeriodType.INSTANT
        )
        b = PeriodAxis.annual(
            "2018-12-31", "2020-12-31", period_type=PeriodType.INSTANT
        )
        assert a.axis_id != b.axis_id

    def test_period_type_change_changes_id(self) -> None:
        a = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.INSTANT
        )
        b = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.DURATION
        )
        assert a.axis_id != b.axis_id

    def test_annual_and_quarterly_never_collide(self) -> None:
        a = PeriodAxis.annual(
            "2018-12-31", "2018-12-31", period_type=PeriodType.INSTANT
        )
        q = PeriodAxis.quarterly(
            "2018-12-31", "2018-12-31", period_type=PeriodType.INSTANT
        )
        assert a.axis_id != q.axis_id

    def test_explicit_and_generator_never_collide(self) -> None:
        # An explicit list that expands to the same periods as a generator still has
        # a distinct id (identity is by declared form, not expansion) — D7.
        gen = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.INSTANT
        )
        explicit = PeriodAxis.of(
            [MetricPeriod.instant("2018-12-31"), MetricPeriod.instant("2019-12-31")]
        )
        assert gen.axis_id != explicit.axis_id

    def test_id_is_sha256_prefixed(self) -> None:
        axis = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.INSTANT
        )
        assert axis.axis_id.startswith("sha256:")

    def test_to_dict_round_trip_shape(self) -> None:
        axis = PeriodAxis.annual(
            "2018-12-31", "2019-12-31", period_type=PeriodType.DURATION
        )
        data = axis.to_dict()
        assert data["axis_id"] == axis.axis_id
        assert data["axis_kind"] == "annual"
        assert data["period_type"] == "duration"
        assert len(data["periods"]) == 2  # type: ignore[arg-type]
