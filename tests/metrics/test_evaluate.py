"""Adversarial tests for the pure evaluator (metrics.md §4, §6.3, §13, §14).

The evaluator must fail closed *to a value* on every data condition and raise only
on our own configuration bug. Covered: correct arithmetic under the pinned decimal
context; the exact 1/3 rounding (Decision D5); zero-denominator → DIVIDE_BY_ZERO;
zero-numerator → KNOWN 0 (nil ≠ zero, but a real 0 is a value); any UNDEFINED input
poisons the whole metric with the first failing reason; byte-identical recompute;
and full provenance on both KNOWN and UNDEFINED results.
"""

from __future__ import annotations

from openfinance.availability.resolve import PointInTimeResolver
from openfinance.canonical.model import Fact
from openfinance.metrics.evaluate import MetricEvaluator
from openfinance.metrics.model import (
    MetricPeriod,
    MetricStatus,
    PitMetricValue,
    UndefinedReason,
)
from openfinance.metrics.registry import FormulaRegistry
from openfinance.metrics.resolve_input import MetricBoundary
from openfinance.metrics.version import MetricEngineVersion
from tests.metrics.builders import CIK, duration, instant, simple_world, utc

ACC = "0000320193-23-000106"
COMPANY = f"cik:{CIK:010d}"
AS_OF = utc("2023-11-05T21:30:00Z")
REG = FormulaRegistry()


def _instant_period() -> MetricPeriod:
    return MetricPeriod.instant("2023-09-30")


def _duration_period() -> MetricPeriod:
    return MetricPeriod.duration("2022-10-01", "2023-09-30")


def _pit(facts: list[Fact]) -> tuple[PointInTimeResolver, MetricBoundary]:
    return simple_world(facts), MetricBoundary.pit(AS_OF)


def _eval_pit(
    metric_key: str, facts: list[Fact], period: MetricPeriod
) -> PitMetricValue:
    resolver, boundary = _pit(facts)
    return MetricEvaluator().evaluate_pit(
        REG.get(metric_key), COMPANY, facts, resolver, period, boundary
    )


class TestArithmetic:
    def test_current_ratio_known(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "100"),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"
        assert m.unit == "pure"

    def test_working_capital_is_monetary(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "70"),
        ]
        m = _eval_pit("working_capital", facts, _instant_period())
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "130"
        assert m.unit == "USD"

    def test_quick_ratio_subtracts_inventory(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "InventoryNet", "50"),
            instant(ACC, "LiabilitiesCurrent", "100"),
        ]
        m = _eval_pit("quick_ratio", facts, _instant_period())
        assert m.value_numeric_str == "1.5"

    def test_gross_margin_duration(self) -> None:
        facts = [
            duration(ACC, "Revenues", "1000"),
            duration(ACC, "CostOfRevenue", "600"),
        ]
        m = _eval_pit("gross_margin", facts, _duration_period())
        assert m.value_numeric_str == "0.4"

    def test_one_third_rounds_half_even_at_prec_34(self) -> None:
        # 1/3 under precision 34, ROUND_HALF_EVEN (Decision D5).
        facts = [
            duration(ACC, "OperatingIncomeLoss", "1"),
            duration(ACC, "Revenues", "3"),
        ]
        m = _eval_pit("operating_margin", facts, _duration_period())
        assert m.value_numeric_str == "0." + "3" * 33 + "3"
        assert len(m.value_numeric_str.split(".")[1]) == 34


class TestZero:
    def test_zero_denominator_fails_closed(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "0"),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.status is MetricStatus.UNDEFINED
        assert m.reason is UndefinedReason.DIVIDE_BY_ZERO
        assert m.value_numeric_str is None

    def test_zero_numerator_is_known_zero(self) -> None:
        # A genuine 0 numerator is a value, not undefined (nil ≠ zero, invariant 25).
        facts = [
            duration(ACC, "OperatingIncomeLoss", "0"),
            duration(ACC, "Revenues", "1000"),
        ]
        m = _eval_pit("operating_margin", facts, _duration_period())
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "0"


class TestPartialAvailability:
    def test_missing_input_poisons_metric(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", "200")]  # liabilities absent
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.status is MetricStatus.UNDEFINED
        assert m.reason is UndefinedReason.MISSING_INPUT

    def test_reason_mirrors_first_failing_input_in_order(self) -> None:
        # current_assets present, current_liabilities nil → the nil input's reason.
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", None, is_nil=True),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.reason is UndefinedReason.NIL_INPUT

    def test_nil_never_treated_as_zero(self) -> None:
        facts = [
            duration(ACC, "OperatingIncomeLoss", None, is_nil=True),
            duration(ACC, "Revenues", "1000"),
        ]
        m = _eval_pit("operating_margin", facts, _duration_period())
        assert m.status is MetricStatus.UNDEFINED
        assert m.reason is UndefinedReason.NIL_INPUT


class TestDeterminism:
    def test_recompute_is_byte_identical(self) -> None:
        facts = [
            duration(ACC, "NetIncomeLoss", "1"),
            duration(ACC, "Revenues", "7"),
        ]
        a = _eval_pit("net_margin", facts, _duration_period())
        b = _eval_pit("net_margin", facts, _duration_period())
        assert a.to_dict() == b.to_dict()
        assert a.metric_id == b.metric_id

    def test_metric_id_stable_and_prefixed(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "100"),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.metric_id.startswith("sha256:")


class TestMixedPeriod:
    def test_asset_turnover_duration_revenue_over_instant_assets(self) -> None:
        # DURATION revenue ÷ INSTANT ending assets (§6.4), same period_end.
        facts = [
            duration(ACC, "Revenues", "1000"),
            instant(ACC, "Assets", "500", period_end="2023-09-30"),
        ]
        m = _eval_pit("asset_turnover", facts, _duration_period())
        assert m.status is MetricStatus.KNOWN
        assert m.value_numeric_str == "2"

    def test_asset_turnover_missing_ending_assets(self) -> None:
        facts = [
            duration(ACC, "Revenues", "1000"),
            instant(ACC, "Assets", "500", period_end="2022-09-30"),  # wrong end
        ]
        m = _eval_pit("asset_turnover", facts, _duration_period())
        assert m.status is MetricStatus.UNDEFINED
        assert m.reason is UndefinedReason.MISSING_INPUT


class TestProvenanceCompleteness:
    def test_known_records_every_input_resolution(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "100"),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        names = {i.name for i in m.provenance.inputs}
        assert names == {"current_assets", "current_liabilities"}
        for i in m.provenance.inputs:
            assert i.status is MetricStatus.KNOWN
            assert i.selected_fact_id is not None

    def test_undefined_records_failing_input(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", "200")]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.provenance.result_status is MetricStatus.UNDEFINED
        assert m.provenance.result_reason is UndefinedReason.MISSING_INPUT
        # The failing operand is still audited (zero information loss, §15).
        failing = [i for i in m.provenance.inputs if i.status is MetricStatus.UNDEFINED]
        assert any(i.name == "current_liabilities" for i in failing)

    def test_boundary_recorded_in_provenance(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "200"),
            instant(ACC, "LiabilitiesCurrent", "100"),
        ]
        m = _eval_pit("current_ratio", facts, _instant_period())
        assert m.provenance.boundary_kind == "pit"
        assert m.provenance.boundary_value == "2023-11-05T21:30:00Z"


class TestDecimalContextSensitivity:
    def test_lower_precision_changes_engine_and_value(self) -> None:
        facts = [
            duration(ACC, "OperatingIncomeLoss", "1"),
            duration(ACC, "Revenues", "3"),
        ]
        resolver, boundary = _pit(facts)
        low = MetricEvaluator(MetricEngineVersion(decimal_precision=4))
        m = low.evaluate_pit(
            REG.get("operating_margin"),
            COMPANY,
            facts,
            resolver,
            _duration_period(),
            boundary,
        )
        assert m.value_numeric_str == "0.3333"
        # A different context ⇒ a different engine id folded into the metric_id.
        assert (
            m.metric_engine_version_id != MetricEngineVersion().metric_engine_version_id
        )
