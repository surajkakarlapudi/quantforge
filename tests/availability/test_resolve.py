"""Adversarial tests for PIT / REVISED resolution (data-model §6, §KS).

Includes the **required** §KS.3 worked example (FY2019 $100M→$80M restatement),
the fail-closed availability gate (invariants 6, 9), the §6.3 total-order
selection and tiebreaks (invariant 16), as-of monotonicity (invariant 29), and the
structural PIT/REVISED separation that makes invariant 28 a type-level guarantee.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from openfinance.availability.errors import ModeError
from openfinance.availability.model import AvailabilityStatus
from openfinance.availability.resolve import (
    PitValue,
    PointInTimeResolver,
    RevisedValue,
)
from openfinance.availability.version import DatasetVersion
from tests.availability.builders import availability, revenue_fact

POLICY_ID = "sha256:policy"


def _utc(iso: str) -> datetime:
    from openfinance.availability.timestamps import parse_utc

    return parse_utc(iso)


def _ks3_setup() -> PointInTimeResolver:
    """The §KS.3 world: FY2019 revenue $100M (avail 2020-03-01), restated $80M
    (avail 2022-05-01), same obs_key, two filings."""
    original = revenue_fact(accession="0000320193-20-000001", value="100000000")
    restated = revenue_fact(accession="0000320193-22-000001", value="80000000")
    avail = {
        original.filing_id: availability(
            accession="0000320193-20-000001",
            timestamp="2020-03-01T21:30:00Z",
            status=AvailabilityStatus.DERIVED,
            policy_id=POLICY_ID,
        ),
        restated.filing_id: availability(
            accession="0000320193-22-000001",
            timestamp="2022-05-01T21:30:00Z",
            status=AvailabilityStatus.DERIVED,
            policy_id=POLICY_ID,
        ),
    }
    return PointInTimeResolver([original, restated], avail)


class TestKS3WorkedExample:
    def test_pit_2021_returns_original(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        result = resolver.knowledge_state_as_of(obs, _utc("2021-01-01T00:00:00Z"))
        assert isinstance(result, PitValue)
        assert result.is_known
        assert result.fact is not None
        assert result.fact.value_numeric_str == "100000000"

    def test_pit_2023_returns_restated(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        result = resolver.knowledge_state_as_of(obs, _utc("2023-01-01T00:00:00Z"))
        assert result.fact is not None
        assert result.fact.value_numeric_str == "80000000"

    def test_revised_returns_restated(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        dv = DatasetVersion(
            transformation_version_id="sha256:tv",
            availability_policy_ids=(POLICY_ID,),
            raw_document_ids=(),
            fact_ids=(),
        )
        result = resolver.revised_truth(obs, dv)
        assert isinstance(result, RevisedValue)
        assert result.fact is not None
        assert result.fact.value_numeric_str == "80000000"

    def test_pit_before_any_availability_is_unknown(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        result = resolver.knowledge_state_as_of(obs, _utc("2019-06-01T00:00:00Z"))
        assert not result.is_known
        assert result.fact is None

    def test_boundary_is_inclusive(self) -> None:
        # as_of exactly at the original's availability instant → knowable (<=).
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        result = resolver.knowledge_state_as_of(obs, _utc("2020-03-01T21:30:00Z"))
        assert result.fact is not None
        assert result.fact.value_numeric_str == "100000000"


class TestFailClosedGate:
    def test_unknown_availability_never_eligible(self) -> None:
        # A restatement with UNKNOWN availability must NOT supersede the base,
        # even at as_of = far future (invariant 9, 22).
        original = revenue_fact(accession="0000320193-20-000001", value="100000000")
        restated = revenue_fact(accession="0000320193-22-000001", value="80000000")
        avail = {
            original.filing_id: availability(
                accession="0000320193-20-000001",
                timestamp="2020-03-01T21:30:00Z",
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
            ),
            restated.filing_id: availability(
                accession="0000320193-22-000001",
                timestamp=None,
                status=AvailabilityStatus.UNKNOWN,
                policy_id=None,
            ),
        }
        resolver = PointInTimeResolver([original, restated], avail)
        result = resolver.knowledge_state_as_of(
            original.obs_key, _utc("2030-01-01T00:00:00Z")
        )
        # The unknown restatement is invisible; the base still wins.
        assert result.fact is not None
        assert result.fact.value_numeric_str == "100000000"

    def test_fact_without_availability_record_is_excluded(self) -> None:
        # A fact whose filing has no availability record is treated as unknown.
        orphan = revenue_fact(accession="0000320193-20-000001", value="100000000")
        resolver = PointInTimeResolver([orphan], {})
        result = resolver.knowledge_state_as_of(
            orphan.obs_key, _utc("2030-01-01T00:00:00Z")
        )
        assert not result.is_known

    def test_audit_path_surfaces_unknown_only_when_opted_in(self) -> None:
        restated = revenue_fact(accession="0000320193-22-000001", value="80000000")
        avail = {
            restated.filing_id: availability(
                accession="0000320193-22-000001",
                timestamp=None,
                status=AvailabilityStatus.UNKNOWN,
                policy_id=None,
            ),
        }
        resolver = PointInTimeResolver([restated], avail)
        assert resolver.all_observations(restated.obs_key) == []
        opted = resolver.all_observations(
            restated.obs_key, include_unknown_availability=True
        )
        assert len(opted) == 1


class TestMonotonicity:
    def test_eligible_set_grows_with_as_of(self) -> None:
        # Invariant 29: for T1 <= T2 the eligible set at T1 ⊆ that at T2.
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        early = resolver.eligible_history_as_of(obs, _utc("2021-01-01T00:00:00Z"))
        late = resolver.eligible_history_as_of(obs, _utc("2023-01-01T00:00:00Z"))
        early_ids = {o.fact.fact_id for o in early}
        late_ids = {o.fact.fact_id for o in late}
        assert early_ids <= late_ids
        assert len(early) == 1 and len(late) == 2

    def test_pit_result_invariant_to_future_observations(self) -> None:
        # A PIT(2021) answer is unchanged whether or not the 2022 restatement
        # exists in the store (past-closed).
        original = revenue_fact(accession="0000320193-20-000001", value="100000000")
        avail_orig = {
            original.filing_id: availability(
                accession="0000320193-20-000001",
                timestamp="2020-03-01T21:30:00Z",
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
            )
        }
        only_original = PointInTimeResolver([original], avail_orig)
        with_restatement = _ks3_setup()
        as_of = _utc("2021-01-01T00:00:00Z")
        a = only_original.knowledge_state_as_of(original.obs_key, as_of)
        b = with_restatement.knowledge_state_as_of(original.obs_key, as_of)
        assert a.fact is not None and b.fact is not None
        assert a.fact.value_numeric_str == b.fact.value_numeric_str == "100000000"


class TestTotalOrderSelection:
    def test_amendment_outranks_base_on_same_availability(self) -> None:
        # §6.3 step 3: when availability + acceptance tie, /A outranks base form.
        base = revenue_fact(accession="0000320193-20-000001", value="100000000")
        amendment = revenue_fact(accession="0000320193-20-000002", value="90000000")
        ts = "2020-03-01T21:30:00Z"
        avail = {
            base.filing_id: availability(
                accession="0000320193-20-000001",
                timestamp=ts,
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K",
                acceptance=ts,
            ),
            amendment.filing_id: availability(
                accession="0000320193-20-000002",
                timestamp=ts,
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K/A",
                acceptance=ts,
            ),
        }
        resolver = PointInTimeResolver([base, amendment], avail)
        result = resolver.knowledge_state_as_of(
            base.obs_key, _utc("2021-01-01T00:00:00Z")
        )
        assert result.fact is not None
        assert result.fact.value_numeric_str == "90000000"

    def test_later_availability_wins_over_amendment_flag(self) -> None:
        # Availability is the primary signal: a later-available base beats an
        # earlier-available /A.
        base = revenue_fact(accession="0000320193-22-000001", value="100000000")
        amendment = revenue_fact(accession="0000320193-20-000002", value="90000000")
        avail = {
            base.filing_id: availability(
                accession="0000320193-22-000001",
                timestamp="2022-05-01T21:30:00Z",
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K",
            ),
            amendment.filing_id: availability(
                accession="0000320193-20-000002",
                timestamp="2020-03-01T21:30:00Z",
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K/A",
            ),
        }
        resolver = PointInTimeResolver([base, amendment], avail)
        result = resolver.knowledge_state_as_of(
            base.obs_key, _utc("2023-01-01T00:00:00Z")
        )
        assert result.fact is not None
        assert result.fact.value_numeric_str == "100000000"

    def test_accession_desc_final_tiebreak_is_deterministic(self) -> None:
        # Identical availability/acceptance/form → accession desc decides.
        a = revenue_fact(accession="0000320193-20-000001", value="1")
        b = revenue_fact(accession="0000320193-20-000009", value="9")
        ts = "2020-03-01T21:30:00Z"
        avail = {
            a.filing_id: availability(
                accession="0000320193-20-000001",
                timestamp=ts,
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K",
                acceptance=ts,
            ),
            b.filing_id: availability(
                accession="0000320193-20-000009",
                timestamp=ts,
                status=AvailabilityStatus.DERIVED,
                policy_id=POLICY_ID,
                form="10-K",
                acceptance=ts,
            ),
        }
        resolver = PointInTimeResolver([a, b], avail)
        result = resolver.knowledge_state_as_of(a.obs_key, _utc("2021-01-01T00:00:00Z"))
        # Higher accession (…009) wins the descending tiebreak.
        assert result.fact is not None
        assert result.fact.value_numeric_str == "9"


class TestModeSeparation:
    def test_naive_as_of_rejected(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        with pytest.raises(ModeError, match="timezone-aware"):
            resolver.knowledge_state_as_of(obs, datetime(2021, 1, 1))  # naive

    def test_pit_and_revised_are_distinct_types(self) -> None:
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        dv = DatasetVersion(
            transformation_version_id="sha256:tv",
            availability_policy_ids=(POLICY_ID,),
            raw_document_ids=(),
            fact_ids=(),
        )
        pit = resolver.knowledge_state_as_of(obs, _utc("2023-01-01T00:00:00Z"))
        revised = resolver.revised_truth(obs, dv)
        assert type(pit) is PitValue
        assert type(revised) is RevisedValue
        assert not isinstance(revised, PitValue)  # cannot be consumed as PIT

    def test_revised_reinterpret_as_pit_reresolves(self) -> None:
        # The only bridge from REVISED to PIT re-runs the resolution at as_of;
        # it does not reuse the revised winner (invariant 28 — explicit conversion).
        resolver = _ks3_setup()
        obs = revenue_fact(accession="0000320193-20-000001", value="100000000").obs_key
        dv = DatasetVersion(
            transformation_version_id="sha256:tv",
            availability_policy_ids=(POLICY_ID,),
            raw_document_ids=(),
            fact_ids=(),
        )
        revised = resolver.revised_truth(obs, dv)  # $80M
        pit = revised.reinterpret_as_pit(resolver, _utc("2021-01-01T00:00:00Z"))
        assert isinstance(pit, PitValue)
        # Re-resolved at 2021 → the original $100M, NOT the revised $80M.
        assert pit.fact is not None
        assert pit.fact.value_numeric_str == "100000000"
