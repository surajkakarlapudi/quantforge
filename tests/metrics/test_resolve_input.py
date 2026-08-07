"""Tests for §7 concept selection — the load-bearing resolution rule.

Covered: ordered first-present-wins selection (Decision D3), the discarded-
candidate audit trail, consolidated-only matching (a dimensional fact is ignored),
period alignment, and the fail-closed reason ladder (MISSING / NIL / NON_NUMERIC /
UNIT_MISMATCH). Selection matches by ``(taxonomy, local_name)`` — never a pre-built
obs_key — and resolves through the real Phase 5 resolver at a PIT boundary.
"""

from __future__ import annotations

from quantforge.canonical.taxonomy import Taxonomy
from quantforge.metrics.formula import ConceptCandidate, InputBinding
from quantforge.metrics.model import MetricPeriod, MetricStatus, UndefinedReason
from quantforge.metrics.resolve_input import MetricBoundary, resolve_input
from quantforge.metrics.units import UnitExpectation
from quantforge.xbrl.contexts import PeriodType
from tests.metrics.builders import avail, instant, resolver, simple_world, utc

ACC = "0000320193-23-000106"
FY_END = "2023-09-30"
AS_OF = utc("2023-11-05T21:30:00Z")


def _binding(
    *candidates: str,
    name: str = "x",
    kind: PeriodType = PeriodType.INSTANT,
    unit: UnitExpectation = UnitExpectation.MONETARY,
) -> InputBinding:
    return InputBinding(
        name=name,
        concept_candidates=tuple(
            ConceptCandidate(Taxonomy.US_GAAP, c) for c in candidates
        ),
        period_kind=kind,
        unit_expectation=unit,
    )


def _period() -> MetricPeriod:
    return MetricPeriod.instant(FY_END)


def _pit() -> MetricBoundary:
    return MetricBoundary.pit(AS_OF)


class TestSelection:
    def test_single_candidate_resolves(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", "100")]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.status is MetricStatus.KNOWN
        assert r.value is not None and str(r.value) == "100"
        assert r.resolution.selected_local_name == "AssetsCurrent"

    def test_first_present_candidate_wins(self) -> None:
        # Both present; the first in list order must be selected (Decision D3).
        facts = [
            instant(ACC, "Revenues", "500"),
            instant(ACC, "SalesRevenueNet", "999"),
        ]
        binding = _binding("Revenues", "SalesRevenueNet")
        r = resolve_input(binding, facts, simple_world(facts), _pit(), _period())
        assert r.resolution.selected_local_name == "Revenues"
        assert str(r.value) == "500"

    def test_falls_through_to_second_when_first_absent(self) -> None:
        facts = [instant(ACC, "SalesRevenueNet", "777")]
        binding = _binding("Revenues", "SalesRevenueNet")
        r = resolve_input(binding, facts, simple_world(facts), _pit(), _period())
        assert r.resolution.selected_local_name == "SalesRevenueNet"

    def test_discarded_candidates_recorded(self) -> None:
        # Both concepts are present as known facts; the audit lists both, selected
        # + discarded, so nothing is silently dropped (§9, Decision D3).
        facts = [
            instant(ACC, "Revenues", "500"),
            instant(ACC, "SalesRevenueNet", "999"),
        ]
        binding = _binding("Revenues", "SalesRevenueNet")
        r = resolve_input(binding, facts, simple_world(facts), _pit(), _period())
        assert set(r.resolution.present_candidates) == {
            "us-gaap:Revenues",
            "us-gaap:SalesRevenueNet",
        }


class TestConsolidatedOnly:
    def test_dimensional_fact_is_ignored(self) -> None:
        # Only a segmented fact exists → nothing consolidated → MISSING_INPUT.
        facts = [
            instant(
                ACC,
                "AssetsCurrent",
                "100",
                dimension=(
                    "us-gaap:StatementBusinessSegmentsAxis",
                    "us-gaap:ProductMember",
                ),
            ),
        ]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.status is MetricStatus.UNDEFINED
        assert r.resolution.reason is UndefinedReason.MISSING_INPUT

    def test_consolidated_selected_over_dimensional(self) -> None:
        facts = [
            instant(ACC, "AssetsCurrent", "100"),
            instant(
                ACC,
                "AssetsCurrent",
                "40",
                dimension=(
                    "us-gaap:StatementBusinessSegmentsAxis",
                    "us-gaap:ProductMember",
                ),
            ),
        ]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.status is MetricStatus.KNOWN
        assert str(r.value) == "100"


class TestPeriodAlignment:
    def test_instant_at_wrong_end_is_missing(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", "100", period_end="2022-09-30")]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.MISSING_INPUT

    def test_duration_requires_exact_span(self) -> None:
        from tests.metrics.builders import duration

        facts = [
            duration(
                ACC,
                "Revenues",
                "500",
                period_start="2021-10-01",
                period_end="2022-09-30",
            )
        ]
        binding = _binding("Revenues", kind=PeriodType.DURATION)
        period = MetricPeriod.duration("2022-10-01", "2023-09-30")
        r = resolve_input(binding, facts, simple_world(facts), _pit(), period)
        assert r.resolution.reason is UndefinedReason.MISSING_INPUT

    def test_duration_exact_span_matches(self) -> None:
        from tests.metrics.builders import duration

        facts = [duration(ACC, "Revenues", "500")]
        binding = _binding("Revenues", kind=PeriodType.DURATION)
        period = MetricPeriod.duration("2022-10-01", "2023-09-30")
        r = resolve_input(binding, facts, simple_world(facts), _pit(), period)
        assert r.status is MetricStatus.KNOWN


class TestFailClosedReasons:
    def test_missing_when_nothing_present(self) -> None:
        facts = [instant(ACC, "Liabilities", "1")]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.MISSING_INPUT

    def test_nil_input(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", None, is_nil=True)]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.NIL_INPUT

    def test_non_numeric_input(self) -> None:
        facts = [instant(ACC, "AssetsCurrent", None, value_text="see note")]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.NON_NUMERIC_INPUT

    def test_unit_mismatch_input(self) -> None:
        # Present, numeric, but shares where monetary is expected.
        facts = [instant(ACC, "AssetsCurrent", "100", unit="shares", currency=None)]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.UNIT_MISMATCH

    def test_reason_priority_nil_over_missing(self) -> None:
        # A nil fact is present for the concept → NIL wins over MISSING even though
        # no usable value was selected.
        facts = [instant(ACC, "AssetsCurrent", None, is_nil=True)]
        r = resolve_input(
            _binding("AssetsCurrent"), facts, simple_world(facts), _pit(), _period()
        )
        assert r.resolution.reason is UndefinedReason.NIL_INPUT


class TestBoundaryGate:
    def test_not_yet_public_is_missing(self) -> None:
        # Fact exists but only becomes available after the PIT as_of → not present.
        facts = [instant(ACC, "AssetsCurrent", "100")]
        avs = {
            facts[0].filing_id: avail(accession=ACC, timestamp="2024-01-01T00:00:00Z")
        }
        r = resolve_input(
            _binding("AssetsCurrent"), facts, resolver(facts, avs), _pit(), _period()
        )
        assert r.status is MetricStatus.UNDEFINED
        assert r.resolution.reason is UndefinedReason.MISSING_INPUT
        # Nothing was present at this boundary, so no candidate is audited as present.
        assert r.resolution.present_candidates == ()
