"""Adversarial tests for the availability deriver and policy selection.

Covers the derivation invariants (10 no-precede-acceptance, 11 retrieval upper
bound, 13 determinism), the fail-closed rule (§PA.3), the cutoff/next-business-day
behavior (§13 case 6), Decision 4 (derived/unknown only until dissemination
evidence is trusted), and §PA.2 policy selection (exactly-one-active, overlap is a
config error).
"""

from __future__ import annotations

import dataclasses

import pytest

from quantforge.availability.errors import PolicyConfigurationError
from quantforge.availability.model import AvailabilityStatus
from quantforge.availability.policy import derive, select_policy
from quantforge.availability.timestamps import parse_utc
from quantforge.availability.version import (
    AvailabilityPolicy,
    AvailabilityRule,
    PolicyConfidence,
    PolicyStatus,
    edgar_std_v1,
)
from tests.availability.builders import evidence

POLICY = edgar_std_v1()


class TestCutoffDerivation:
    def test_after_cutoff_rolls_to_next_business_day(self) -> None:
        # Thu 2024-08-01 22:03Z = 18:03 EDT (after 17:30) → Fri 2024-08-02 17:30 EDT.
        ev = evidence(
            accession="0000320193-24-000081",
            form="10-Q",
            acceptance="2024-08-01T22:03:34Z",
        )
        r = derive(ev, [POLICY])
        assert r.availability_status is AvailabilityStatus.DERIVED
        assert r.derived_public_availability_timestamp == "2024-08-02T21:30:00Z"

    def test_before_cutoff_same_business_day(self) -> None:
        # Thu 2024-05-02 15:00Z = 11:00 EDT (before 17:30) → same day 17:30 EDT.
        ev = evidence(
            accession="0000320193-24-000050", acceptance="2024-05-02T15:00:00Z"
        )
        r = derive(ev, [POLICY])
        assert r.derived_public_availability_timestamp == "2024-05-02T21:30:00Z"

    def test_weekend_acceptance_rolls_to_monday(self) -> None:
        # Sat 2024-08-03 12:00Z → next business day Monday 2024-08-05 17:30 EDT.
        ev = evidence(
            accession="0001318605-24-000010",
            form="10-K",
            acceptance="2024-08-03T12:00:00Z",
        )
        r = derive(ev, [POLICY])
        assert r.derived_public_availability_timestamp == "2024-08-05T21:30:00Z"

    def test_winter_cutoff_uses_est_offset(self) -> None:
        # Mon 2024-01-08 15:00Z = 10:00 EST (before cutoff) → same day 17:30 EST
        # = 22:30 UTC (winter offset differs from summer).
        ev = evidence(
            accession="0000320193-24-000001", acceptance="2024-01-08T15:00:00Z"
        )
        r = derive(ev, [POLICY])
        assert r.derived_public_availability_timestamp == "2024-01-08T22:30:00Z"


class TestInvariants:
    def test_derived_never_precedes_acceptance(self) -> None:
        # Every derived availability >= acceptance (invariant 10).
        for accept in [
            "2024-08-01T22:03:34Z",
            "2024-05-02T15:00:00Z",
            "2024-08-03T12:00:00Z",
            "2024-12-31T23:59:00Z",
        ]:
            ev = evidence(accession="0000320193-24-000081", acceptance=accept)
            r = derive(ev, [POLICY])
            assert r.derived_public_availability_timestamp is not None
            assert parse_utc(r.derived_public_availability_timestamp) >= parse_utc(
                accept
            )

    def test_retrieval_upper_bound_caps_derivation(self) -> None:
        # If the estimate would exceed retrieved_at, cap at retrieved_at (inv 11).
        # Accept just before midnight Fri → estimate rolls to Mon 17:30, but we
        # retrieved it Saturday: availability cannot exceed retrieval.
        ev = evidence(
            accession="0000320193-24-000081",
            acceptance="2024-08-02T22:00:00Z",  # Fri 18:00 EDT → rolls to Mon
            retrieved_at="2024-08-03T09:00:00Z",  # Sat morning
        )
        r = derive(ev, [POLICY])
        assert r.derived_public_availability_timestamp == "2024-08-03T09:00:00Z"
        assert parse_utc(r.derived_public_availability_timestamp) <= parse_utc(
            "2024-08-03T09:00:00Z"
        )

    def test_derivation_is_deterministic(self) -> None:
        ev = evidence(
            accession="0000320193-24-000081", acceptance="2024-08-01T22:03:34Z"
        )
        a = derive(ev, [POLICY])
        b = derive(ev, [POLICY])
        assert a.to_dict() == b.to_dict()

    def test_unknown_carries_no_timestamp_or_policy(self) -> None:
        ev = evidence(accession="0000320193-24-000081", acceptance=None)
        r = derive(ev, [POLICY])
        assert r.availability_status is AvailabilityStatus.UNKNOWN
        assert r.derived_public_availability_timestamp is None
        assert r.availability_policy_id is None


class TestFailClosed:
    def test_missing_acceptance_is_unknown(self) -> None:
        ev = evidence(
            accession="0000320193-24-000081", acceptance=None, filing_date="2024-08-02"
        )
        assert derive(ev, [POLICY]).availability_status is AvailabilityStatus.UNKNOWN

    def test_unparseable_acceptance_is_unknown(self) -> None:
        ev = evidence(accession="0000320193-24-000081", acceptance="not-a-date")
        assert derive(ev, [POLICY]).availability_status is AvailabilityStatus.UNKNOWN

    def test_pre_era_acceptance_is_unknown(self) -> None:
        # Before the policy's effective_from (2009) → out of scope → unknown.
        ev = evidence(
            accession="0000320193-05-000001", acceptance="2005-06-01T12:00:00Z"
        )
        assert derive(ev, [POLICY]).availability_status is AvailabilityStatus.UNKNOWN

    def test_never_falls_back_to_filing_date(self) -> None:
        # filing_date present but acceptance missing → still unknown, never
        # silently using the filing date (invariant 10 / §PA.3).
        ev = evidence(
            accession="0000320193-24-000081", acceptance=None, filing_date="2024-08-02"
        )
        r = derive(ev, [POLICY])
        assert r.derived_public_availability_timestamp is None


class TestDecision4NeverVerified:
    def test_initial_policy_never_verifies_even_with_dissemination(self) -> None:
        # Even if dissemination evidence exists, the initial policy does not trust
        # it → status stays DERIVED, never VERIFIED (Decision 4).
        ev = evidence(
            accession="0000320193-24-000081",
            acceptance="2024-08-01T22:03:34Z",
            dissemination="2024-08-01T22:10:00Z",
        )
        r = derive(ev, [POLICY])
        assert r.availability_status is AvailabilityStatus.DERIVED

    def test_future_policy_may_verify(self) -> None:
        # A hypothetical successor policy that trusts dissemination can reach
        # VERIFIED — proving the machinery exists but is gated by policy.
        trusting = AvailabilityPolicy(
            policy_id="edgar-std",
            policy_version="v2",
            effective_from="2009-01-01T00:00:00Z",
            effective_to=None,
            form_scope=("*",),
            rule_definition=AvailabilityRule(dissemination_evidence_trusted=True),
            status=PolicyStatus.PROVISIONAL,
            confidence=PolicyConfidence.HEURISTIC,
        )
        ev = evidence(
            accession="0000320193-24-000081",
            acceptance="2024-08-01T22:03:34Z",
            dissemination="2024-08-01T22:10:00Z",
        )
        r = derive(ev, [trusting])
        assert r.availability_status is AvailabilityStatus.VERIFIED
        # Verified still respects invariant 10 (>= acceptance).
        assert r.derived_public_availability_timestamp is not None
        assert parse_utc(r.derived_public_availability_timestamp) >= parse_utc(
            "2024-08-01T22:03:34Z"
        )


class TestPolicySelection:
    def test_exactly_one_matches(self) -> None:
        ev = evidence(
            accession="0000320193-24-000081", acceptance="2024-08-01T22:03:34Z"
        )
        assert select_policy(ev, [POLICY]) is POLICY

    def test_no_match_returns_none(self) -> None:
        ev = evidence(
            accession="0000320193-05-000001", acceptance="2005-06-01T12:00:00Z"
        )
        assert select_policy(ev, [POLICY]) is None

    def test_overlapping_active_scopes_is_config_error(self) -> None:
        # Two active/provisional policies both covering the same (form, era) is a
        # configuration error — we never arbitrate (§PA.2, fail closed).
        clash = dataclasses.replace(POLICY, notes="a clashing duplicate scope")
        ev = evidence(
            accession="0000320193-24-000081", acceptance="2024-08-01T22:03:34Z"
        )
        with pytest.raises(PolicyConfigurationError, match="overlapping"):
            select_policy(ev, [POLICY, clash])

    def test_unsupported_rule_kind_is_config_error(self) -> None:
        bad = AvailabilityPolicy(
            policy_id="edgar-std",
            policy_version="vX",
            effective_from="2009-01-01T00:00:00Z",
            effective_to=None,
            form_scope=("*",),
            rule_definition=AvailabilityRule(rule_kind="mystery-rule"),
            status=PolicyStatus.PROVISIONAL,
            confidence=PolicyConfidence.UNVALIDATED,
        )
        ev = evidence(
            accession="0000320193-24-000081", acceptance="2024-08-01T22:03:34Z"
        )
        with pytest.raises(PolicyConfigurationError, match="unsupported"):
            derive(ev, [bad])

    def test_form_scope_excludes_out_of_scope_form(self) -> None:
        scoped = dataclasses.replace(POLICY, form_scope=("8-K",))
        ev = evidence(
            accession="0000320193-24-000081",
            form="10-K",
            acceptance="2024-08-01T22:03:34Z",
        )
        # No policy covers 10-K → unknown (out of scope), not an error.
        assert derive(ev, [scoped]).availability_status is AvailabilityStatus.UNKNOWN
